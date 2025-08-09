# flask_app.py
import flask
from flask import Flask, jsonify, request, render_template_string
import os
import json
import uuid
import random
import time
import sys

# --- Flask App Setup ---
app = Flask(__name__)

# --- Configuration ---
ADMIN_PASSWORD = "supersecretadminpassword123" # CHANGE THIS!
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# --- In-Memory Database & Game Data ---
DB = {
    "players": {},
    "online_users": {},
    "global_chat": [],
}
GAME_DATA = {
    "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {}
}

def load_game_data():
    """Loads all static game data from the JSON files into memory."""
    try:
        with open(os.path.join(DATA_DIR, "rarities.json"), 'r') as f: GAME_DATA["rarities"] = json.load(f)
        with open(os.path.join(DATA_DIR, "ranks.json"), 'r') as f: GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
        with open(os.path.join(DATA_DIR, "skins.json"), 'r') as f: GAME_DATA["all_skins"] = json.load(f)
        with open(os.path.join(DATA_DIR, "cases.json"), 'r') as f: GAME_DATA["cases"] = json.load(f)
        print("✅ Game data loaded successfully.")
        return True
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not load game data from '{DATA_DIR}': {e}")
        return False

# --- Helper Functions ---
def send_global_event(event_data):
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": "Server", "msg": event_data, "is_server_msg": True})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)

def open_single_case_logic(case_name):
    """Ported directly from your game. Determines what skin is unboxed."""
    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return None
    case_skins = case_info["skins"]
    total_probability = sum(GAME_DATA["rarities"][GAME_DATA["all_skins"][skin]]["probability"] for skin in case_skins)
    roll = random.uniform(0, total_probability)
    cumulative_probability = 0
    for skin in case_skins:
        rarity_name = GAME_DATA["all_skins"][skin]
        cumulative_probability += GAME_DATA["rarities"][rarity_name]["probability"]
        if roll <= cumulative_probability:
            chosen_rarity = rarity_name
            min_val, max_val = GAME_DATA["rarities"][chosen_rarity]["value_range"]
            return {"id": str(uuid.uuid4()), "name": skin, "value": round(random.uniform(min_val, max_val), 2)}
    return None

# --- API Routes ---
@app.route('/')
def index():
    try: return render_template_string(open("index.html").read())
    except FileNotFoundError: return "<h1>Error: index.html not found.</h1>", 404

@app.route('/api/login', methods=['POST'])
def login():
    username = request.json.get('username')
    if not username or len(username) < 3 or len(username) > 20 or " " in username:
        return jsonify({"success": False, "message": "Username must be 3-20 characters with no spaces."}), 400
    if username.lower() == "server":
        return jsonify({"success": False, "message": "Invalid username."}), 400
    if username not in DB["players"]:
        DB["players"][username] = {"clicks": 0, "money": 100, "skins": [], "cases": {}}
    DB["online_users"][username] = time.time()
    send_global_event(f"{username} has joined.")
    return jsonify({"success": True, "player_data": DB["players"][username]})

@app.route('/api/game_state', methods=['POST'])
def get_game_state():
    username = request.json.get('username')
    if not username or username not in DB["online_users"]:
        return jsonify({"success": False, "message": "Not authenticated."}), 403
    DB["online_users"][username] = time.time()
    last_chat_id = request.json.get('last_chat_id', '0')
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_chat_id]
    current_time = time.time()
    online_players = {user: ts for user, ts in DB["online_users"].items() if current_time - ts < 30}
    if len(online_players) != len(DB["online_users"]):
        disconnected = set(DB["online_users"].keys()) - set(online_players.keys())
        for user in disconnected: send_global_event(f"{user} has disconnected.")
    DB["online_users"] = online_players
    return jsonify({"success": True, "online_players": list(online_players.keys()), "new_global_messages": new_global_messages, "player_data": DB["players"].get(username)})

@app.route('/api/click', methods=['POST'])
def handle_click():
    username = request.json.get('username')
    if not username or username not in DB["players"]: return jsonify({"success": False}), 403
    DB["players"][username]["clicks"] += 1
    DB["players"][username]["money"] += random.uniform(1.0, 2.5)
    return jsonify({"success": True, "player_data": DB["players"][username]})

@app.route('/api/buy_case', methods=['POST'])
def buy_case():
    username = request.json.get('username')
    case_name = request.json.get('case_name')
    quantity = int(request.json.get('quantity', 1))
    if not all([username, case_name, quantity > 0]) or username not in DB["players"]: return jsonify({"success": False}), 400
    case_price = GAME_DATA["cases"].get(case_name, {}).get('price', 0)
    total_cost = case_price * quantity
    player = DB["players"][username]
    if player["money"] < total_cost: return jsonify({"success": False, "message": "Not enough money!"})
    player["money"] -= total_cost
    player["cases"][case_name] = player["cases"].get(case_name, 0) + quantity
    return jsonify({"success": True, "player_data": player})

@app.route('/api/open_case', methods=['POST'])
def open_case():
    username = request.json.get('username')
    case_name = request.json.get('case_name')
    if not all([username, case_name]) or username not in DB["players"]: return jsonify({"success": False}), 400
    player = DB["players"][username]
    if player["cases"].get(case_name, 0) < 1: return jsonify({"success": False, "message": "You don't have that case."})
    item_won = open_single_case_logic(case_name)
    if not item_won: return jsonify({"success": False, "message": "Invalid case data on server."})
    player["cases"][case_name] -= 1
    player["skins"].append(item_won)
    send_global_event(f"{username} unboxed a {item_won['name']}!")
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

@app.route('/api/sell_skins', methods=['POST'])
def sell_skins():
    username = request.json.get('username')
    skin_ids = request.json.get('skin_ids', [])
    if not all([username, skin_ids]) or username not in DB["players"]: return jsonify({"success": False}), 400
    player = DB["players"][username]
    skins_to_sell = [s for s in player["skins"] if s["id"] in skin_ids]
    total_value = sum(s['value'] for s in skins_to_sell)
    player["skins"] = [s for s in player["skins"] if s["id"] not in skin_ids]
    player["money"] += total_value
    return jsonify({"success": True, "player_data": player, "value": total_value, "count": len(skins_to_sell)})

@app.route('/api/chat/global', methods=['POST'])
def handle_global_chat():
    sender, message = request.json.get('username'), request.json.get('message')
    if not all([sender, message]) or sender not in DB["online_users"]: return jsonify({"success": False}), 400
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": sender, "msg": message, "is_server_msg": False})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)
    return jsonify({"success": True})

@app.route('/api/game_data/cases')
def get_cases(): return jsonify(GAME_DATA["cases"])

@app.route('/api/game_data/skins')
def get_skins(): return jsonify(GAME_DATA["all_skins"])
    
@app.route('/api/game_data/rarities')
def get_rarities(): return jsonify(GAME_DATA["rarities"])

@app.route('/api/admin/data', methods=['POST'])
def get_admin_data():
    if request.json.get('password') != ADMIN_PASSWORD: return jsonify({"success": False}), 403
    return jsonify({"success": True, "all_data": DB})

@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD: return jsonify({"success": False}), 403
    action, target_user = data.get('action'), data.get('target_user')
    if action == 'kick' and target_user in DB["online_users"]:
        del DB["online_users"][target_user]
        send_global_event(f"{target_user} was kicked by an admin.")
        return jsonify({"success": True, "message": f"{target_user} kicked."})
    if action == 'give_money' and target_user in DB["players"]:
        amount = int(data.get('amount', 0))
        DB["players"][target_user]["money"] += amount
        send_global_event(f"{target_user} was granted ${amount:,} by an admin!")
        return jsonify({"success": True, "message": f"Gave ${amount:,} to {target_user}."})
    return jsonify({"success": False, "message": "Invalid action or user."})

if __name__ == '__main__':
    if not load_game_data(): sys.exit(1)
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    load_game_data()
