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

# --- Flask App Setup ---
app = Flask(__name__)

# --- Configuration ---
ADMIN_PASSWORD = "14122" 
ADMIN_USERNAME = "clace" # Define the main admin username
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'Case Clicker Inc')
INDEX_FILE_PATH = os.path.join(BASE_DIR, 'index.html')
PLAYER_DATA_FILE = os.path.join(DATA_DIR, 'players.json')

# --- In-Memory Database & Game Data ---
DB = {
    "players": {},
    "online_users": {},
    "global_chat": [],
    "private_chats": {} # To store private messages
}
GAME_DATA = {
    "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {}
}

# --- Helper Functions ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_player_data():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if os.path.exists(PLAYER_DATA_FILE):
            with open(PLAYER_DATA_FILE, 'r') as f:
                DB["players"] = json.load(f)
            # Ensure admin user exists and has the admin role
            if ADMIN_USERNAME.lower() in DB["players"]:
                DB["players"][ADMIN_USERNAME.lower()]['role'] = 'admin'
            print("✅ Player data loaded.")
        else:
            with open(PLAYER_DATA_FILE, 'w') as f:
                json.dump({}, f)
            print("⚠️ players.json not found. Created a new empty file.")
    except Exception as e:
        print(f"❌ ERROR loading player data: {e}")

def save_player_data():
    try:
        with open(PLAYER_DATA_FILE, 'w') as f:
            json.dump(DB["players"], f, indent=4)
    except Exception as e:
        print(f"❌ ERROR saving player data: {e}")

def load_game_data():
    try:
        with open(os.path.join(DATA_DIR, "rarities.json"), 'r') as f: GAME_DATA["rarities"] = json.load(f)
        with open(os.path.join(DATA_DIR, "ranks.json"), 'r') as f: GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
        with open(os.path.join(DATA_DIR, "skins.json"), 'r') as f: GAME_DATA["all_skins"] = json.load(f)
        with open(os.path.join(DATA_DIR, "cases.json"), 'r') as f: GAME_DATA["cases"] = json.load(f)
        print("✅ Game data loaded.")
        return True
    except Exception as e:
        print(f"❌ FATAL ERROR loading game data from '{DATA_DIR}': {e}")
        return False

def get_player_rank(clicks):
    current_rank = {"name": "No Rank"}
    for rank_id in sorted(GAME_DATA["ranks"].keys(), reverse=True):
        if clicks >= GAME_DATA["ranks"][rank_id]["clicks_needed"]:
            current_rank = GAME_DATA["ranks"][rank_id]
            break
    return current_rank

def set_player_activity(username, activity):
    if username in DB["online_users"]:
        DB["online_users"][username]["activity"] = activity

# --- API Routes ---
@app.route('/')
def index():
    try: return render_template_string(open(INDEX_FILE_PATH).read())
    except FileNotFoundError: return f"<h1>Error: {INDEX_FILE_PATH} not found.</h1>", 404

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
        "clicks": 0, "money": 100, "skins": [], "cases": {},
        "role": "player" # Default role
    }
    # Make the predefined user an admin upon registration
    if username.lower() == ADMIN_USERNAME.lower():
        DB["players"][username.lower()]['role'] = 'admin'
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
    # No longer announce joins in global chat
    return jsonify({"success": True, "player_data": player_record, "username": player_record['display_name']})

@app.route('/api/game_state', methods=['POST'])
def get_game_state():
    username = request.json.get('username', '').lower()
    if not username or username not in DB["online_users"]:
        return jsonify({"success": False, "message": "Not authenticated."}), 403
    DB["online_users"][username]["last_seen"] = time.time()
    set_player_activity(username, "Idle")
    
    player_data = DB["players"].get(username)
    if not player_data:
        return jsonify({"success": False, "message": "Player data not found."}), 404
        
    player_data["rank"] = get_player_rank(player_data.get("clicks", 0))

    current_time = time.time()
    online_players_dict = {}
    for user, data in DB["online_users"].items():
        if current_time - data["last_seen"] < 30:
            display_name = DB["players"].get(user, {}).get("display_name", user)
            online_players_dict[user] = {"display_name": display_name}
    DB["online_users"] = {u: d for u, d in DB["online_users"].items() if current_time - d["last_seen"] < 30}

    return jsonify({
        "success": True, 
        "player_data": player_data,
        "online_players": list(online_players_dict.values())
    })

@app.route('/api/click', methods=['POST'])
def handle_click():
    username = request.json.get('username', '').lower()
    if not username or username not in DB["players"]: return jsonify({"success": False}), 403
    set_player_activity(username, "Clicking")
    player = DB["players"][username]
    
    current_rank_info = get_player_rank(player["clicks"])
    clicks_per_click = current_rank_info.get("base_clicks", 1)

    player["clicks"] += clicks_per_click
    player["money"] += random.uniform(1.0, 2.5) * clicks_per_click
    if player["clicks"] % 25 == 0:
        save_player_data()
    return jsonify({"success": True, "player_data": player})

# Other routes (buy_case, open_case, sell_skins) remain largely the same...
@app.route('/api/buy_case', methods=['POST'])
def buy_case():
    username = request.json.get('username', '').lower()
    case_name = request.json.get('case_name')
    if not all([username, case_name]) or username not in DB["players"]: return jsonify({"success": False}), 400
    set_player_activity(username, "In Shop")
    case_price = float(GAME_DATA["cases"].get(case_name, {}).get('price', "0"))
    player = DB["players"][username]
    if player["money"] < case_price: return jsonify({"success": False, "message": "Not enough money!"})
    player["money"] -= case_price
    player["cases"][case_name] = player["cases"].get(case_name, 0) + 1
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
    # Announce valuable unboxings
    rarity = GAME_DATA["all_skins"][item_won['name']]
    if rarity in ["Legendary", "Immortal"]:
        DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": "Server", "msg": f"{display_name} just unboxed an incredible item: {item_won['name']}!", "is_server_msg": True})

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

# --- Chat Routes ---
@app.route('/api/chat/global', methods=['POST'])
def handle_global_chat():
    username = request.json.get('username', '').lower()
    message = request.json.get('message')
    if not all([username, message]) or username not in DB["online_users"]: return jsonify({"success": False}), 400
    display_name = DB["players"].get(username, {}).get("display_name", username)
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": display_name, "msg": message, "is_server_msg": False})
    return jsonify({"success": True})

@app.route('/api/chat/history', methods=['POST'])
def get_chat_history():
    # This single endpoint will fetch both global and private messages
    username = request.json.get('username', '').lower()
    last_global_id = request.json.get('last_global_id', '0')
    if not username or username not in DB["online_users"]: return jsonify({"success": False}), 403
    
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_global_id]
    
    return jsonify({"success": True, "global": new_global_messages})

# --- Static Game Data Routes ---
@app.route('/api/game_data/all')
def get_all_game_data():
    return jsonify(GAME_DATA)

# --- Admin Routes ---
@app.route('/api/admin/data', methods=['POST'])
def get_admin_data():
    password = request.json.get('password')
    if password != ADMIN_PASSWORD: return jsonify({"success": False}), 403
    
    detailed_online_users = []
    for user_lower, data in DB["online_users"].items():
        player_record = DB["players"].get(user_lower, {})
        detailed_online_users.append({
            "username": player_record.get("display_name", user_lower),
            "activity": data.get("activity", "Unknown"),
            "role": player_record.get("role", "player"),
            "money": player_record.get("money", 0),
            "clicks": player_record.get("clicks", 0)
        })
    return jsonify({"success": True, "online_players": detailed_online_users})

@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    data = request.json
    password = data.get('password')
    admin_user_lower = data.get('admin_user', '').lower()
    
    if password != ADMIN_PASSWORD: return jsonify({"success": False, "message": "Invalid Admin Password"}), 403
    
    admin_player = DB["players"].get(admin_user_lower)
    if not admin_player or admin_player.get('role') not in ['admin', 'moderator']:
        return jsonify({"success": False, "message": "You do not have permission to perform this action."}), 403

    action = data.get('action')
    target_user_display = data.get('target_user')
    target_user_lower = next((u for u, p in DB["players"].items() if p["display_name"] == target_user_display), None)
    if not target_user_lower:
        return jsonify({"success": False, "message": "Target user not found."})

    if action == 'kick':
        if target_user_lower in DB["online_users"]:
            del DB["online_users"][target_user_lower]
            return jsonify({"success": True, "message": f"{target_user_display} kicked."})
        return jsonify({"success": False, "message": "User is not online."})
        
    if action == 'give_money':
        try:
            amount = int(data.get('amount', 0))
            DB["players"][target_user_lower]["money"] += amount
            save_player_data()
            return jsonify({"success": True, "message": f"Gave ${amount:,} to {target_user_display}."})
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Invalid amount."})
    
    # Actions only the main admin can do
    if admin_player.get('role') != 'admin':
        return jsonify({"success": False, "message": "Only the main admin can manage roles."}), 403

    if action == 'set_role':
        new_role = data.get('role')
        if DB["players"][target_user_lower].get('role') == 'admin':
             return jsonify({"success": False, "message": "Cannot change the main admin's role."})
        if new_role in ['player', 'moderator']:
            DB["players"][target_user_lower]['role'] = new_role
            save_player_data()
            return jsonify({"success": True, "message": f"Set {target_user_display}'s role to {new_role}."})
        return jsonify({"success": False, "message": "Invalid role."})

    return jsonify({"success": False, "message": "Invalid action."})

if __name__ == '__main__':
    if not load_game_data(): sys.exit(1)
    load_player_data()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    load_game_data()
    load_player_data()
