# flask_app.py
import flask
from flask import Flask, jsonify, request, render_template_string
import os
import json
import uuid
import random
import time
import sys
import hashlib # For password hashing
from threading import Timer

# --- Flask App Setup ---
app = Flask(__name__)

# --- Configuration ---
ADMIN_PASSWORD = "14122" # Changed as requested
DATA_DIR = os.path.dirname(os.path.abspath(__file__)) # Simplified data dir
PLAYER_DATA_FILE = os.path.join(DATA_DIR, 'players.json')

# --- In-Memory Database & Game Data ---
DB = {
    "players": {}, # This will be loaded from players.json
    "online_users": {}, # {username: {"last_seen": timestamp, "activity": "Idle"}}
    "global_chat": [],
}
GAME_DATA = {
    "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {}
}

# --- Helper Functions ---
def hash_password(password):
    """Hashes a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()

def load_player_data():
    """Loads player data from the JSON file into memory."""
    try:
        if os.path.exists(PLAYER_DATA_FILE):
            with open(PLAYER_DATA_FILE, 'r') as f:
                DB["players"] = json.load(f)
            print("✅ Player data loaded successfully.")
        else:
            # Create the file if it doesn't exist
            with open(PLAYER_DATA_FILE, 'w') as f:
                json.dump({}, f)
            print("⚠️ players.json not found. Created a new empty player database.")
    except Exception as e:
        print(f"❌ ERROR: Could not load player data from '{PLAYER_DATA_FILE}': {e}")

def save_player_data():
    """Saves the current player data to the JSON file."""
    try:
        # Save a copy to prevent issues with concurrent modification during serialization
        players_to_save = DB["players"].copy()
        with open(PLAYER_DATA_FILE, 'w') as f:
            json.dump(players_to_save, f, indent=4)
    except Exception as e:
        print(f"❌ ERROR: Could not save player data to '{PLAYER_DATA_FILE}': {e}")

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

def send_global_event(event_data):
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": "Server", "msg": event_data, "is_server_msg": True})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)

def set_player_activity(username, activity):
    if username in DB["online_users"]:
        DB["online_users"][username]["activity"] = activity

# --- API Routes ---
@app.route('/')
def index():
    try: return render_template_string(open("index.html").read())
    except FileNotFoundError: return "<h1>Error: index.html not found.</h1>", 404

@app.route('/api/register', methods=['POST'])
def register():
    username = request.json.get('username')
    password = request.json.get('password')
    if not all([username, password]):
        return jsonify({"success": False, "message": "Username and password are required."}), 400
    if len(username) < 3 or len(username) > 20 or " " in username:
        return jsonify({"success": False, "message": "Username must be 3-20 characters with no spaces."}), 400
    if username.lower() in DB["players"]:
        return jsonify({"success": False, "message": "Username already taken."}), 400

    DB["players"][username.lower()] = {
        "password_hash": hash_password(password),
        "display_name": username,
        "clicks": 0, "money": 100, "skins": [], "cases": {}
    }
    save_player_data()
    return jsonify({"success": True, "message": "Registration successful! You can now log in."})

@app.route('/api/login', methods=['POST'])
def login():
    username = request.json.get('username', '').lower()
    password = request.json.get('password')
    player_record = DB["players"].get(username)

    if not player_record or player_record["password_hash"] != hash_password(password):
        return jsonify({"success": False, "message": "Invalid username or password."}), 401

    DB["online_users"][username] = {"last_seen": time.time(), "activity": "Just Logged In"}
    send_global_event(f"{player_record['display_name']} has joined.")
    return jsonify({"success": True, "player_data": player_record, "username": player_record['display_name']})

@app.route('/api/game_state', methods=['POST'])
def get_game_state():
    username = request.json.get('username', '').lower()
    if not username or username not in DB["online_users"]:
        return jsonify({"success": False, "message": "Not authenticated."}), 403

    DB["online_users"][username]["last_seen"] = time.time()
    set_player_activity(username, "Idle") # Default activity
    last_chat_id = request.json.get('last_chat_id', '0')
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_chat_id]

    current_time = time.time()
    online_players = {user: data for user, data in DB["online_users"].items() if current_time - data["last_seen"] < 30}
    if len(online_players) != len(DB["online_users"]):
        disconnected = set(DB["online_users"].keys()) - set(online_players.keys())
        for user in disconnected:
            display_name = DB["players"].get(user, {}).get("display_name", user)
            send_global_event(f"{display_name} has disconnected.")
    DB["online_users"] = online_players
    
    player_data = DB["players"].get(username)
    if player_data:
        player_data["display_name"] = DB["players"][username]["display_name"]

    return jsonify({"success": True, "new_global_messages": new_global_messages, "player_data": player_data})

@app.route('/api/click', methods=['POST'])
def handle_click():
    username = request.json.get('username', '').lower()
    if not username or username not in DB["players"]: return jsonify({"success": False}), 403
    set_player_activity(username, "Clicking")
    DB["players"][username]["clicks"] += 1
    DB["players"][username]["money"] += random.uniform(1.0, 2.5)
    # Save periodically instead of every click to reduce disk I/O
    if DB["players"][username]["clicks"] % 25 == 0:
        save_player_data()
    return jsonify({"success": True, "player_data": DB["players"][username]})

@app.route('/api/buy_case', methods=['POST'])
def buy_case():
    username = request.json.get('username', '').lower()
    case_name = request.json.get('case_name')
    quantity = int(request.json.get('quantity', 1))
    if not all([username, case_name, quantity > 0]) or username not in DB["players"]: return jsonify({"success": False}), 400
    set_player_activity(username, "In Shop")
    case_price = float(GAME_DATA["cases"].get(case_name, {}).get('price', 0))
    total_cost = case_price * quantity
    player = DB["players"][username]
    if player["money"] < total_cost: return jsonify({"success": False, "message": "Not enough money!"})
    player["money"] -= total_cost
    player["cases"][case_name] = player["cases"].get(case_name, 0) + quantity
    save_player_data()
    return jsonify({"success": True, "player_data": player})

@app.route('/api/open_case', methods=['POST'])
def open_case():
    username = request.json.get('username', '').lower()
    case_name = request.json.get('case_name')
    if not all([username, case_name]) or username not in DB["players"]: return jsonify({"success": False}), 400
    set_player_activity(username, "Opening Cases")
    player = DB["players"][username]
    if player["cases"].get(case_name, 0) < 1: return jsonify({"success": False, "message": "You don't have that case."})
    
    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return jsonify({"success": False, "message": "Invalid case data on server."}), 500
    
    case_skins = case_info["skins"]
    total_probability = sum(GAME_DATA["rarities"][GAME_DATA["all_skins"][skin]]["probability"] for skin in case_skins)
    roll = random.uniform(0, total_probability)
    cumulative_probability = 0
    item_won = None
    for skin in case_skins:
        rarity_name = GAME_DATA["all_skins"][skin]
        cumulative_probability += GAME_DATA["rarities"][rarity_name]["probability"]
        if roll <= cumulative_probability:
            chosen_rarity = rarity_name
            min_val, max_val = GAME_DATA["rarities"][chosen_rarity]["value_range"]
            item_won = {"id": str(uuid.uuid4()), "name": skin, "value": round(random.uniform(min_val, max_val), 2)}
            break
            
    if not item_won: return jsonify({"success": False, "message": "Could not determine item from case."}), 500

    player["cases"][case_name] -= 1
    player["skins"].append(item_won)
    display_name = player.get("display_name", username)
    send_global_event(f"{display_name} unboxed a {item_won['name']}!")
    save_player_data()
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

@app.route('/api/sell_skins', methods=['POST'])
def sell_skins():
    username = request.json.get('username', '').lower()
    skin_ids = request.json.get('skin_ids', [])
    if not all([username, skin_ids]) or username not in DB["players"]: return jsonify({"success": False}), 400
    set_player_activity(username, "Selling Skins")
    player = DB["players"][username]
    skins_to_sell = [s for s in player["skins"] if s["id"] in skin_ids]
    total_value = sum(s['value'] for s in skins_to_sell)
    player["skins"] = [s for s in player["skins"] if s["id"] not in skin_ids]
    player["money"] += total_value
    save_player_data()
    return jsonify({"success": True, "player_data": player, "value": total_value, "count": len(skins_to_sell)})

@app.route('/api/chat/global', methods=['POST'])
def handle_global_chat():
    username = request.json.get('username', '').lower()
    message = request.json.get('message')
    if not all([username, message]) or username not in DB["online_users"]: return jsonify({"success": False}), 400
    display_name = DB["players"].get(username, {}).get("display_name", username)
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": display_name, "msg": message, "is_server_msg": False})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)
    return jsonify({"success": True})

# --- Static Game Data Routes ---
@app.route('/api/game_data/cases')
def get_cases(): return jsonify(GAME_DATA["cases"])

@app.route('/api/game_data/skins')
def get_skins(): return jsonify(GAME_DATA["all_skins"])
    
@app.route('/api/game_data/rarities')
def get_rarities(): return jsonify(GAME_DATA["rarities"])

# --- Admin Routes ---
@app.route('/api/admin/data', methods=['POST'])
def get_admin_data():
    if request.json.get('password') != ADMIN_PASSWORD: return jsonify({"success": False}), 403
    
    # Create a more detailed online user list for the admin panel
    detailed_online_users = []
    for user_lower, data in DB["online_users"].items():
        player_record = DB["players"].get(user_lower, {})
        detailed_online_users.append({
            "username": player_record.get("display_name", user_lower),
            "activity": data.get("activity", "Unknown"),
            "money": player_record.get("money", 0),
            "clicks": player_record.get("clicks", 0),
            "skin_count": len(player_record.get("skins", [])),
            "case_count": sum(player_record.get("cases", {}).values())
        })

    return jsonify({"success": True, "online_players": detailed_online_users, "all_player_count": len(DB["players"])})

@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD: return jsonify({"success": False}), 403
    action, target_user_display = data.get('action'), data.get('target_user')
    
    target_user_lower = next((u for u, p in DB["players"].items() if p["display_name"] == target_user_display), None)
    if not target_user_lower:
        return jsonify({"success": False, "message": "Target user not found."})

    if action == 'kick' and target_user_lower in DB["online_users"]:
        del DB["online_users"][target_user_lower]
        send_global_event(f"{target_user_display} was kicked by an admin.")
        return jsonify({"success": True, "message": f"{target_user_display} kicked."})
        
    if action == 'give_money' and target_user_lower in DB["players"]:
        try:
            amount = int(data.get('amount', 0))
            DB["players"][target_user_lower]["money"] += amount
            save_player_data()
            send_global_event(f"{target_user_display} was granted ${amount:,} by an admin!")
            return jsonify({"success": True, "message": f"Gave ${amount:,} to {target_user_display}."})
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Invalid amount."})

    return jsonify({"success": False, "message": "Invalid action or user."})

if __name__ == '__main__':
    if not load_game_data(): sys.exit(1)
    load_player_data()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # For Gunicorn/production
    load_game_data()
    load_player_data()
