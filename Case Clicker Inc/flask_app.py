# flask_app.py
import flask
from flask import Flask, jsonify, request, render_template_string
import os
import json
import uuid
import random
import time
import sys
import hashlib
from datetime import datetime

# --- Flask App Setup ---
app = Flask(__name__)

# --- Configuration ---
# The BASE_DIR is the root directory where this script is running.
# We will search for all .json files starting from here.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# We will determine the file paths dynamically in load_or_create_files()
PLAYERS_FILE = None
SERVER_STATE_FILE = None

# --- In-Memory Database & Game Data ---
DB = {
    "players": {},
    "online_users": {}, # {username: {last_seen: timestamp, role: '...'} }
    "global_chat": [],
    "server_state": {}
}
GAME_DATA = {
    "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {}
}

# --- Utility Functions ---
def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def find_file(filename, search_path):
    """Searches for a file in a directory and its subdirectories."""
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def save_players_data():
    """Saves the current players data to the JSON file."""
    if PLAYERS_FILE:
        with open(PLAYERS_FILE, 'w') as f:
            json.dump(DB["players"], f, indent=4)

def save_server_state():
    """Saves the server state (like leaderboard reset times)."""
    if SERVER_STATE_FILE:
        with open(SERVER_STATE_FILE, 'w') as f:
            json.dump(DB["server_state"], f, indent=4)

def load_or_create_files():
    """
    Finds all required .json files within the project directory and loads them.
    This is robust against different deployment folder structures.
    """
    global PLAYERS_FILE, SERVER_STATE_FILE
    
    # --- Find and Load Game Data ---
    try:
        required_game_files = ["rarities.json", "ranks.json", "skins.json", "cases.json"]
        file_paths = {}

        print(f"🔍 Starting search for data files in '{BASE_DIR}' and its subdirectories...")

        for filename in required_game_files:
            path = find_file(filename, BASE_DIR)
            if path is None:
                print(f"❌ FATAL ERROR: Could not find required file '{filename}' anywhere in the project directory.")
                print("Please ensure all .json files are present in your project repository.")
                return False
            file_paths[filename] = path
            print(f"  ✔️ Found '{filename}' at: {path}")

        with open(file_paths["rarities.json"], 'r') as f: GAME_DATA["rarities"] = json.load(f)
        with open(file_paths["ranks.json"], 'r') as f: GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
        with open(file_paths["skins.json"], 'r') as f: GAME_DATA["all_skins"] = json.load(f)
        with open(file_paths["cases.json"], 'r') as f: GAME_DATA["cases"] = json.load(f)
        print("✅ Game data loaded successfully.")

    except Exception as e:
        print(f"❌ FATAL ERROR: An error occurred while loading game data: {e}")
        return False

    # --- Find and Load Player/Server State Data ---
    PLAYERS_FILE = find_file("players.json", BASE_DIR)
    SERVER_STATE_FILE = find_file("server_state.json", BASE_DIR)

    if not PLAYERS_FILE:
        print("⚠️ Players file not found. Creating a new one in the root directory.")
        PLAYERS_FILE = os.path.join(BASE_DIR, 'players.json')
        default_players = {
            "admin": {"password_hash": md5_hash("admin"), "role": "admin", "clicks": 1000000, "money": 100000000, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 17},
            "moderator": {"password_hash": md5_hash("moderator"), "role": "moderator", "clicks": 500000, "money": 5000000, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 14},
            "helpdesk": {"password_hash": md5_hash("helpdesk"), "role": "helpdesk", "clicks": 1000, "money": 10000, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 6},
            "player1": {"password_hash": md5_hash("player1"), "role": "player", "clicks": 100, "money": 500, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 1},
            "player2": {"password_hash": md5_hash("player2"), "role": "player", "clicks": 100, "money": 500, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 1}
        }
        DB["players"] = default_players
        save_players_data()
    else:
        with open(PLAYERS_FILE, 'r') as f:
            DB["players"] = json.load(f)
    print(f"✅ Loaded {len(DB['players'])} players from {PLAYERS_FILE}")

    if not SERVER_STATE_FILE:
        print("⚠️ Server state file not found. Creating a new one.")
        SERVER_STATE_FILE = os.path.join(BASE_DIR, 'server_state.json')
        DB["server_state"] = {"last_monthly_reset": datetime.now().strftime("%Y-%m")}
        save_server_state()
    else:
        with open(SERVER_STATE_FILE, 'r') as f:
            DB["server_state"] = json.load(f)
    print(f"✅ Server state loaded from {SERVER_STATE_FILE}")
    
    return True


def check_and_reset_monthly_leaderboards():
    """Checks if a new month has started and resets monthly stats if so."""
    current_month = datetime.now().strftime("%Y-%m")
    last_reset = DB["server_state"].get("last_monthly_reset")
    if last_reset != current_month:
        print(f"🎉 New month detected! Resetting monthly leaderboards from {last_reset} to {current_month}.")
        for player_data in DB["players"].values():
            player_data["monthly_clicks"] = 0
            player_data["monthly_cases_opened"] = 0
        DB["server_state"]["last_monthly_reset"] = current_month
        save_players_data()
        save_server_state()

def send_global_event(event_data):
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": "Server", "msg": event_data, "is_server_msg": True, "timestamp": time.time()})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)

def open_single_case_logic(case_name):
    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return None
    case_skins = case_info["skins"]
    total_probability = sum(GAME_DATA["rarities"][GAME_DATA["all_skins"][skin]]["probability"] for skin in case_skins if skin in GAME_DATA["all_skins"])
    if total_probability == 0: return None
    roll = random.uniform(0, total_probability)
    cumulative_probability = 0
    for skin in case_skins:
        if skin not in GAME_DATA["all_skins"]: continue
        rarity_name = GAME_DATA["all_skins"][skin]
        cumulative_probability += GAME_DATA["rarities"][rarity_name]["probability"]
        if roll <= cumulative_probability:
            chosen_rarity = rarity_name
            min_val, max_val = GAME_DATA["rarities"][chosen_rarity]["value_range"]
            return {"id": str(uuid.uuid4()), "name": skin, "value": round(random.uniform(min_val, max_val), 2)}
    return None

# --- Decorators for Role Checking ---
from functools import wraps

def role_required(required_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            username = request.json.get('username')
            if not username or username not in DB["online_users"]:
                return jsonify({"success": False, "message": "Authentication required."}), 401
            user_role = DB["players"].get(username, {}).get("role")
            if user_role not in required_roles:
                return jsonify({"success": False, "message": "Permission denied."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- API Routes ---
@app.route('/')
def index():
    try: 
        # Find index.html dynamically as well
        index_path = find_file("index.html", BASE_DIR)
        if not index_path:
             return "<h1>FATAL ERROR: index.html not found in project.</h1>", 404
        return render_template_string(open(index_path).read())
    except Exception as e:
        return f"<h1>Error loading page: {e}</h1>", 500


@app.route('/api/signup', methods=['POST'])
def signup():
    username = request.json.get('username')
    password = request.json.get('password')
    if not all([username, password]):
        return jsonify({"success": False, "message": "Username and password are required."}), 400
    if len(username) < 3 or len(username) > 20 or " " in username:
        return jsonify({"success": False, "message": "Username must be 3-20 characters with no spaces."}), 400
    if username.lower() in DB["players"]:
        return jsonify({"success": False, "message": "Username already exists."}), 400
    
    DB["players"][username] = {
        "password_hash": md5_hash(password),
        "role": "player",
        "clicks": 0, "money": 100, "skins": [], "cases": {},
        "time_played": 0, "money_spent": 0, "cases_opened": 0,
        "monthly_clicks": 0, "monthly_cases_opened": 0,
        "is_chat_banned": False, "rank": 0
    }
    save_players_data()
    send_global_event(f"Welcome to our new player, {username}!")
    return jsonify({"success": True, "message": "Account created successfully! You can now log in."})

@app.route('/api/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')
    player = DB["players"].get(username)
    if not player or player["password_hash"] != md5_hash(password):
        return jsonify({"success": False, "message": "Invalid username or password."}), 401
    
    DB["online_users"][username] = {"last_seen": time.time(), "role": player.get("role", "player")}
    send_global_event(f"{username} has joined.")
    return jsonify({"success": True, "player_data": player})

@app.route('/api/game_state', methods=['POST'])
def get_game_state():
    username = request.json.get('username')
    if not username or username not in DB["online_users"]:
        return jsonify({"success": False, "message": "Not authenticated."}), 401
    
    # Update player's time played and last seen
    if username in DB["players"]:
        DB["players"][username]["time_played"] = DB["players"][username].get("time_played", 0) + 3 # Approximating based on poll interval
    
    # Prune disconnected users
    current_time = time.time()
    online_users_snapshot = list(DB["online_users"].keys())
    for user in online_users_snapshot:
        if current_time - DB["online_users"][user]["last_seen"] > 30:
            del DB["online_users"][user]
            send_global_event(f"{user} has disconnected.")
            save_players_data() # Save on disconnect

    last_chat_id = request.json.get('last_chat_id', '0')
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_chat_id]
    
    return jsonify({
        "success": True, 
        "online_players": list(DB["online_users"].keys()), 
        "new_global_messages": new_global_messages, 
        "player_data": DB["players"].get(username)
    })

@app.route('/api/click', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def handle_click():
    username = request.json.get('username')
    player = DB["players"][username]
    player["clicks"] += 1
    player["monthly_clicks"] += 1
    player["money"] += random.uniform(1.0, 2.5)
    return jsonify({"success": True, "player_data": player})

@app.route('/api/buy_case', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def buy_case():
    username = request.json.get('username')
    case_name = request.json.get('case_name')
    quantity = int(request.json.get('quantity', 1))
    if not all([case_name, quantity > 0]): return jsonify({"success": False, "message": "Invalid request"}), 400
    
    case_price = GAME_DATA["cases"].get(case_name, {}).get('price', 0)
    total_cost = case_price * quantity
    player = DB["players"][username]
    if player["money"] < total_cost: return jsonify({"success": False, "message": "Not enough money!"})
    
    player["money"] -= total_cost
    player["money_spent"] += total_cost
    player["cases"][case_name] = player["cases"].get(case_name, 0) + quantity
    return jsonify({"success": True, "player_data": player})

@app.route('/api/open_case', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def open_case():
    username = request.json.get('username')
    case_name = request.json.get('case_name')
    if not case_name: return jsonify({"success": False, "message": "Invalid request"}), 400
    
    player = DB["players"][username]
    if player["cases"].get(case_name, 0) < 1: return jsonify({"success": False, "message": "You don't have that case."})
    
    item_won = open_single_case_logic(case_name)
    if not item_won: return jsonify({"success": False, "message": "Invalid case data on server."})
    
    player["cases"][case_name] -= 1
    player["cases_opened"] += 1
    player["monthly_cases_opened"] += 1
    player["skins"].append(item_won)
    send_global_event(f"{username} unboxed a {item_won['name']}!")
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

@app.route('/api/sell_skins', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def sell_skins():
    username = request.json.get('username')
    skin_ids = request.json.get('skin_ids', [])
    if not skin_ids: return jsonify({"success": False}), 400
    
    player = DB["players"][username]
    skins_to_sell = [s for s in player["skins"] if s["id"] in skin_ids]
    total_value = sum(s['value'] for s in skins_to_sell)
    player["skins"] = [s for s in player["skins"] if s["id"] not in skin_ids]
    player["money"] += total_value
    return jsonify({"success": True, "player_data": player, "value": total_value, "count": len(skins_to_sell)})

@app.route('/api/chat/global', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def handle_global_chat():
    sender, message = request.json.get('username'), request.json.get('message')
    if not message: return jsonify({"success": False}), 400
    
    if DB["players"][sender].get("is_chat_banned"):
        return jsonify({"success": False, "message": "You are currently banned from chat."}), 403

    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": sender, "msg": message, "is_server_msg": False, "timestamp": time.time()})
    if len(DB["global_chat"]) > 100: DB["global_chat"].pop(0)
    return jsonify({"success": True})

# --- Staff and Admin Routes ---
@app.route('/api/admin/all_players')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_all_players():
    # To prevent sending password hashes to the client, even staff
    safe_players = {}
    for uname, udata in DB["players"].items():
        safe_data = udata.copy()
        if "password_hash" in safe_data:
            del safe_data["password_hash"]
        safe_players[uname] = safe_data
    return jsonify(safe_players)


@app.route('/api/admin/update_player', methods=['POST'])
@role_required(['moderator', 'admin'])
def admin_update_player():
    requester_username = request.json.get('username')
    target_username = request.json.get('target_user')
    updates = request.json.get('updates')

    if not all([target_username, updates]):
        return jsonify({"success": False, "message": "Invalid request."}), 400

    requester_role = DB["players"][requester_username]["role"]
    target_player = DB["players"].get(target_username)

    if not target_player:
        return jsonify({"success": False, "message": "Target user not found."}), 404
    
    # Security: Mods cannot edit admins
    if target_player.get("role") == "admin" and requester_role == "moderator":
        return jsonify({"success": False, "message": "Moderators cannot edit Admins."}), 403

    # Apply updates
    for key, value in updates.items():
        # Admin-only updates
        if key == "role" and requester_role != 'admin':
            continue # Skip role changes if not admin
        
        # Type conversion
        if key in ["money", "clicks", "rank", "time_played", "money_spent", "cases_opened"]:
            try: value = int(value)
            except (ValueError, TypeError): continue
        elif key == "is_chat_banned":
            value = bool(value)

        target_player[key] = value

    save_players_data()
    send_global_event(f"{target_username}'s data was updated by {requester_username}.")
    return jsonify({"success": True, "message": f"{target_username} updated."})

@app.route('/api/helpdesk/set_chat_ban', methods=['POST'])
@role_required(['helpdesk', 'moderator', 'admin'])
def set_chat_ban():
    requester_username = request.json.get('username')
    target_username = request.json.get('target_user')
    is_banned = request.json.get('is_banned')

    target_player = DB["players"].get(target_username)
    if not target_player:
        return jsonify({"success": False, "message": "Target user not found."}), 404
    
    if target_player.get("role") in ["moderator", "admin"]:
         return jsonify({"success": False, "message": "Cannot ban staff members."}), 403

    target_player["is_chat_banned"] = bool(is_banned)
    save_players_data()
    status = "banned from chat" if is_banned else "unbanned from chat"
    send_global_event(f"{target_username} was {status} by {requester_username}.")
    return jsonify({"success": True, "message": f"{target_username} chat status updated."})

# --- Leaderboard Route ---
@app.route('/api/leaderboards')
def get_leaderboards():
    check_and_reset_monthly_leaderboards()
    
    all_players = list(DB["players"].items())
    
    def get_inv_value(p):
        return sum(s['value'] for s in p[1].get('skins', []))

    def get_highest_skin(p):
        skins = p[1].get('skins', [])
        return max(s['value'] for s in skins) if skins else 0

    leaderboards = {
        "most_clicks": sorted(all_players, key=lambda p: p[1].get('clicks', 0), reverse=True)[:10],
        "most_money": sorted(all_players, key=lambda p: p[1].get('money', 0), reverse=True)[:10],
        "most_time_played": sorted(all_players, key=lambda p: p[1].get('time_played', 0), reverse=True)[:10],
        "most_money_spent": sorted(all_players, key=lambda p: p[1].get('money_spent', 0), reverse=True)[:10],
        "inventory_value": sorted(all_players, key=get_inv_value, reverse=True)[:10],
        "highest_skin_value": sorted(all_players, key=get_highest_skin, reverse=True)[:10],
        "most_cases_opened": sorted(all_players, key=lambda p: p[1].get('cases_opened', 0), reverse=True)[:10],
        "monthly_clicks": sorted(all_players, key=lambda p: p[1].get('monthly_clicks', 0), reverse=True)[:10],
        "monthly_cases_opened": sorted(all_players, key=lambda p: p[1].get('monthly_cases_opened', 0), reverse=True)[:10],
    }

    # Sanitize data for frontend
    for category, board in leaderboards.items():
        if category == 'inventory_value':
             leaderboards[category] = [{"username": p[0], "value": get_inv_value(p)} for p in board]
        elif category == 'highest_skin_value':
             leaderboards[category] = [{"username": p[0], "value": get_highest_skin(p)} for p in board]
        else:
            key = category.replace("most_", "")
            if 'monthly' in key:
                key = key.replace("monthly_", "monthly_")
            leaderboards[category] = [{"username": p[0], "value": p[1].get(key, 0)} for p in board]

    return jsonify(leaderboards)

# --- Game Data Routes ---
@app.route('/api/game_data/cases')
def get_cases(): return jsonify(GAME_DATA["cases"])

@app.route('/api/game_data/skins')
def get_skins(): return jsonify(GAME_DATA["all_skins"])
    
@app.route('/api/game_data/rarities')
def get_rarities(): return jsonify(GAME_DATA["rarities"])

@app.route('/api/game_data/ranks')
def get_ranks(): return jsonify(GAME_DATA["ranks"])

if __name__ == '__main__':
    if not load_or_create_files(): 
        sys.exit(1)
    # Run initial check
    check_and_reset_monthly_leaderboards()
    # Use gunicorn in production
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # When run by gunicorn, load data
    if not load_or_create_files():
        # If loading fails, we should not continue.
        # This will cause gunicorn to stop the worker, which is the desired behavior.
        sys.exit(1)
    check_and_reset_monthly_leaderboards()
