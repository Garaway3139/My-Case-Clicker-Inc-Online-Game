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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYERS_FILE = None
SERVER_STATE_FILE = None

# --- In-Memory Database & Game Data ---
DB = { "players": {}, "online_users": {}, "global_chat": [], "server_state": {} }
GAME_DATA = { "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {} }

# --- Utility Functions ---
def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def find_file(filename, search_path):
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def update_ai_players():
    """Called periodically to simulate AI player progress."""
    ai_players = [name for name, data in DB["players"].items() if data.get("role") == "ai"]
    if not ai_players:
        return

    # Update a small fraction of AI players to simulate activity
    for _ in range(min(10, len(ai_players))): # Update up to 10 AI players at a time
        player_name = random.choice(ai_players)
        player = DB["players"][player_name]
        player["clicks"] += random.randint(100, 1500)
        player["money"] += random.randint(200, 3000)
        player["time_played"] += random.randint(60, 300)
        if random.random() < 0.1: # 10% chance to "open" a case
            player["cases_opened"] += random.randint(1, 5)
            player["monthly_cases_opened"] +=1


def save_players_data():
    if PLAYERS_FILE:
        if random.random() < 0.25: # 25% chance to update AI on any player save
            update_ai_players()
        with open(PLAYERS_FILE, 'w') as f:
            json.dump(DB["players"], f, indent=4)

def save_server_state():
    if SERVER_STATE_FILE:
        with open(SERVER_STATE_FILE, 'w') as f:
            json.dump(DB["server_state"], f, indent=4)

def load_or_create_files():
    global PLAYERS_FILE, SERVER_STATE_FILE
    
    try:
        required_game_files = ["rarities.json", "ranks.json", "skins.json", "cases.json"]
        file_paths = {}
        print(f"🔍 Starting search for data files in '{BASE_DIR}'...")
        for filename in required_game_files:
            path = find_file(filename, BASE_DIR)
            if path is None:
                print(f"❌ FATAL ERROR: Could not find '{filename}'.")
                return False
            file_paths[filename] = path
            print(f"  ✔️ Found '{filename}' at: {path}")

        with open(file_paths["rarities.json"], 'r') as f: GAME_DATA["rarities"] = json.load(f)
        with open(file_paths["ranks.json"], 'r') as f: GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
        with open(file_paths["skins.json"], 'r') as f: GAME_DATA["all_skins"] = json.load(f)
        with open(file_paths["cases.json"], 'r') as f: GAME_DATA["cases"] = json.load(f)
        print("✅ Game data loaded successfully.")
    except Exception as e:
        print(f"❌ FATAL ERROR loading game data: {e}")
        return False

    PLAYERS_FILE = find_file("players.json", BASE_DIR)
    SERVER_STATE_FILE = find_file("server_state.json", BASE_DIR)

    if not PLAYERS_FILE:
        PLAYERS_FILE = os.path.join(BASE_DIR, 'players.json')
    
    try:
        with open(PLAYERS_FILE, 'r') as f:
            DB["players"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("⚠️ Players file not found or corrupted. Creating a new one.")
        DB["players"] = {
            "admin": {"password_hash": "81dc9bdb52d04dc20036dbd8313ed055", "role": "admin", "clicks": 1000000, "money": 100000000, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 17, "has_changed_username": False, "has_changed_password": False},
            "player1": {"password_hash": "81dc9bdb52d04dc20036dbd8313ed055", "role": "player", "clicks": 100, "money": 500, "skins": [], "cases": {}, "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0, "is_chat_banned": False, "rank": 1, "has_changed_username": False, "has_changed_password": False}
        }
    
    # Check for and generate AI players if they don't exist
    ai_player_count = sum(1 for p in DB["players"].values() if p.get("role") == "ai")
    if ai_player_count < 1000:
        print(f"🤖 Found {ai_player_count} AI players. Generating {1000 - ai_player_count} more...")
        for i in range(ai_player_count, 1000):
            DB["players"][f"AI_Player_{i+1}"] = {
                "password_hash": "", "role": "ai",
                "clicks": random.randint(1000, 1000000), "money": random.randint(5000, 5000000),
                "skins": [], "cases": {}, "time_played": random.randint(3600, 360000),
                "money_spent": random.randint(1000, 1000000), "cases_opened": random.randint(10, 1000),
                "monthly_clicks": random.randint(100, 10000), "monthly_cases_opened": random.randint(1, 50),
                "is_chat_banned": True, "rank": random.randint(1, 18)
            }
    save_players_data()
    print(f"✅ Loaded {len(DB['players'])} total players from {PLAYERS_FILE}")

    if not SERVER_STATE_FILE:
        SERVER_STATE_FILE = os.path.join(BASE_DIR, 'server_state.json')
        DB["server_state"] = {"last_monthly_reset": datetime.now().strftime("%Y-%m")}
        save_server_state()
    else:
        with open(SERVER_STATE_FILE, 'r') as f:
            DB["server_state"] = json.load(f)
    print(f"✅ Server state loaded from {SERVER_STATE_FILE}")
    
    return True

def check_and_reset_monthly_leaderboards():
    current_month = datetime.now().strftime("%Y-%m")
    last_reset = DB["server_state"].get("last_monthly_reset")
    if last_reset != current_month:
        print(f"🎉 New month detected! Resetting monthly leaderboards.")
        for player_data in DB["players"].values():
            player_data["monthly_clicks"] = 0
            player_data["monthly_cases_opened"] = 0
        DB["server_state"]["last_monthly_reset"] = current_month
        save_players_data()
        save_server_state()

def send_global_event(event_data):
    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": "Server", "msg": event_data, "is_server_msg": True, "timestamp": time.time()})
    DB["global_chat"] = DB["global_chat"][-100:]

def open_single_case_logic(case_name):
    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return None
    case_skins = case_info["skins"]
    valid_skins = [s for s in case_skins if s in GAME_DATA["all_skins"]]
    if not valid_skins: return None
    
    total_probability = sum(GAME_DATA["rarities"][GAME_DATA["all_skins"][skin]]["probability"] for skin in valid_skins)
    if total_probability == 0: return None
    
    roll = random.uniform(0, total_probability)
    cumulative_probability = 0
    for skin in valid_skins:
        rarity_name = GAME_DATA["all_skins"][skin]
        cumulative_probability += GAME_DATA["rarities"][rarity_name]["probability"]
        if roll <= cumulative_probability:
            chosen_rarity = rarity_name
            min_val, max_val = GAME_DATA["rarities"][chosen_rarity]["value_range"]
            return {"id": str(uuid.uuid4()), "name": skin, "value": round(random.uniform(min_val, max_val), 2)}
    return None

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

@app.route('/')
def index():
    try: 
        index_path = find_file("index.html", BASE_DIR)
        if not index_path: return "<h1>FATAL ERROR: index.html not found.</h1>", 404
        return render_template_string(open(index_path).read())
    except Exception as e:
        return f"<h1>Error loading page: {e}</h1>", 500

@app.route('/api/signup', methods=['POST'])
def signup():
    username = request.json.get('username')
    password = request.json.get('password')
    if not all([username, password]): return jsonify({"success": False, "message": "Username and password are required."}), 400
    if len(username) < 3 or len(username) > 20 or " " in username: return jsonify({"success": False, "message": "Username must be 3-20 characters with no spaces."}), 400
    if username.lower() in DB["players"]: return jsonify({"success": False, "message": "Username already exists."}), 400
    
    DB["players"][username] = {
        "password_hash": md5_hash(password), "role": "player", "clicks": 0, "money": 100, "skins": [], "cases": {},
        "time_played": 0, "money_spent": 0, "cases_opened": 0, "monthly_clicks": 0, "monthly_cases_opened": 0,
        "is_chat_banned": False, "rank": 0, "has_changed_username": False, "has_changed_password": False
    }
    save_players_data()
    return jsonify({"success": True, "message": "Account created successfully! You can now log in."})

@app.route('/api/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')
    player = DB["players"].get(username)
    if not player or player["password_hash"] != md5_hash(password):
        return jsonify({"success": False, "message": "Invalid username or password."}), 401
    
    DB["online_users"][username] = {"last_seen": time.time(), "role": player.get("role", "player")}
    return jsonify({"success": True, "player_data": player})

@app.route('/api/game_state', methods=['POST'])
def get_game_state():
    username = request.json.get('username')
    if not username or username not in DB["online_users"]: return jsonify({"success": False, "message": "Not authenticated."}), 401
    
    DB["online_users"][username]["last_seen"] = time.time()
    if username in DB["players"]: DB["players"][username]["time_played"] = DB["players"][username].get("time_played", 0) + 2
    
    current_time = time.time()
    online_users_snapshot = list(DB["online_users"].keys())
    for user in online_users_snapshot:
        if current_time - DB["online_users"][user]["last_seen"] > 65:
            del DB["online_users"][user]
            save_players_data()

    last_chat_id = request.json.get('last_chat_id', '0')
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_chat_id]
    
    return jsonify({ "success": True, "online_players": list(DB["online_users"].keys()), "new_global_messages": new_global_messages, "player_data": DB["players"].get(username) })

@app.route('/api/update_profile', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def update_profile():
    username = request.json.get('username')
    current_password = request.json.get('current_password')
    new_username = request.json.get('new_username', '').strip()
    new_password = request.json.get('new_password', '').strip()
    player = DB["players"][username]

    if player["password_hash"] != md5_hash(current_password):
        return jsonify({"success": False, "message": "Incorrect current password."}), 403

    if new_username:
        if player.get("has_changed_username", False): return jsonify({"success": False, "message": "You have already changed your username once."}), 400
        if len(new_username) < 3 or len(new_username) > 20 or " " in new_username: return jsonify({"success": False, "message": "New username must be 3-20 characters with no spaces."}), 400
        if new_username.lower() in DB["players"]: return jsonify({"success": False, "message": "That username is already taken."}), 400
        
        DB["players"][new_username] = DB["players"].pop(username)
        DB["players"][new_username]["has_changed_username"] = True
        if username in DB["online_users"]: DB["online_users"][new_username] = DB["online_users"].pop(username)
        save_players_data()
        return jsonify({"success": True, "message": "Username changed! Please log in again.", "new_username": new_username})

    if new_password:
        if player.get("has_changed_password", False): return jsonify({"success": False, "message": "You have already changed your password once."}), 400
        player["password_hash"] = md5_hash(new_password)
        player["has_changed_password"] = True
        save_players_data()
        return jsonify({"success": True, "message": "Password changed successfully!"})

    return jsonify({"success": False, "message": "No changes requested."}), 400

@app.route('/api/click', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def handle_click():
    username = request.json.get('username')
    player = DB["players"][username]
    player["clicks"] = player.get("clicks", 0) + 1
    player["monthly_clicks"] = player.get("monthly_clicks", 0) + 1
    player["money"] = player.get("money", 0) + random.uniform(1.0, 2.5)
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
    if player.get("money", 0) < total_cost: return jsonify({"success": False, "message": "Not enough money!"})
    
    player["money"] -= total_cost
    player["money_spent"] = player.get("money_spent", 0) + total_cost
    if "cases" not in player: player["cases"] = {}
    player["cases"][case_name] = player["cases"].get(case_name, 0) + quantity
    save_players_data()
    return jsonify({"success": True, "player_data": player})

@app.route('/api/open_case', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def open_case():
    username = request.json.get('username')
    case_name = request.json.get('case_name')
    if not case_name: return jsonify({"success": False, "message": "Invalid request"}), 400
    
    player = DB["players"][username]
    if player.get("cases", {}).get(case_name, 0) < 1: return jsonify({"success": False, "message": "You don't have that case."})
    
    item_won = open_single_case_logic(case_name)
    if not item_won: return jsonify({"success": False, "message": "Invalid case data on server."})
    
    player["cases"][case_name] -= 1
    player["cases_opened"] = player.get("cases_opened", 0) + 1
    player["monthly_cases_opened"] = player.get("monthly_cases_opened", 0) + 1
    if "skins" not in player: player["skins"] = []
    player["skins"].append(item_won)
    send_global_event(f"{username} unboxed a {item_won['name']}!")
    save_players_data()
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

@app.route('/api/sell_skins', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def sell_skins():
    username = request.json.get('username')
    skin_ids = request.json.get('skin_ids', [])
    if not skin_ids: return jsonify({"success": False}), 400
    
    player = DB["players"][username]
    skins_to_sell = [s for s in player.get("skins", []) if s["id"] in skin_ids]
    total_value = sum(s['value'] for s in skins_to_sell)
    player["skins"] = [s for s in player.get("skins", []) if s["id"] not in skin_ids]
    player["money"] = player.get("money", 0) + total_value
    save_players_data()
    return jsonify({"success": True, "player_data": player, "value": total_value, "count": len(skins_to_sell)})

@app.route('/api/chat/global', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def handle_global_chat():
    sender, message = request.json.get('username'), request.json.get('message')
    if not message: return jsonify({"success": False}), 400
    
    if DB["players"][sender].get("is_chat_banned"):
        return jsonify({"success": False, "message": "You are currently banned from chat."}), 403

    DB["global_chat"].append({"id": str(uuid.uuid4()), "sender": sender, "msg": message, "is_server_msg": False, "timestamp": time.time()})
    DB["global_chat"] = DB["global_chat"][-100:]
    return jsonify({"success": True})

@app.route('/api/admin/all_players')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_all_players():
    safe_players = {}
    for uname, udata in DB["players"].items():
        safe_data = udata.copy()
        if "password_hash" in safe_data: del safe_data["password_hash"]
        safe_players[uname] = safe_data
    return jsonify(safe_players)

@app.route('/api/admin/server_stats')
@role_required(['admin'])
def get_server_stats():
    real_players = [p for p in DB["players"].values() if p.get("role") not in ["ai", None]]
    total_money = sum(p.get("money", 0) for p in real_players)
    total_clicks = sum(p.get("clicks", 0) for p in real_players)
    total_skins = sum(len(p.get("skins", [])) for p in real_players)
    
    stats = {
        "online_players": len(DB["online_users"]),
        "total_players": len(real_players),
        "total_server_money": total_money,
        "total_server_clicks": total_clicks,
        "total_skins_in_game": total_skins
    }
    return jsonify(stats)


@app.route('/api/admin/update_player', methods=['POST'])
@role_required(['moderator', 'admin'])
def admin_update_player():
    requester_username = request.json.get('username')
    target_username = request.json.get('target_user')
    updates = request.json.get('updates')
    if not all([target_username, updates]): return jsonify({"success": False, "message": "Invalid request."}), 400
    requester_role = DB["players"][requester_username]["role"]
    target_player = DB["players"].get(target_username)
    if not target_player: return jsonify({"success": False, "message": "Target user not found."}), 404
    if target_player.get("role") == "admin" and requester_role == "moderator": return jsonify({"success": False, "message": "Moderators cannot edit Admins."}), 403
    for key, value in updates.items():
        if key == "role" and requester_role != 'admin': continue
        if key in ["money", "clicks", "rank", "time_played", "money_spent", "cases_opened"]:
            try: value = int(value)
            except (ValueError, TypeError): continue
        elif key == "is_chat_banned": value = bool(value)
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
    if not target_player: return jsonify({"success": False, "message": "Target user not found."}), 404
    if target_player.get("role") in ["moderator", "admin"]: return jsonify({"success": False, "message": "Cannot ban staff members."}), 403
    target_player["is_chat_banned"] = bool(is_banned)
    save_players_data()
    status = "banned from chat" if is_banned else "unbanned from chat"
    send_global_event(f"{target_username} was {status} by {requester_username}.")
    return jsonify({"success": True, "message": f"{target_username} chat status updated."})

@app.route('/api/leaderboards')
def get_leaderboards():
    check_and_reset_monthly_leaderboards()
    all_players = [p for p in DB["players"].items() if p[1].get("role") != "ai"]
    ai_players = [p for p in DB["players"].items() if p[1].get("role") == "ai"]
    
    def get_inv_value(p): return sum(s['value'] for s in p[1].get('skins', []))
    def get_highest_skin(p):
        skins = p[1].get('skins', [])
        return max(s['value'] for s in skins) if skins else 0

    leaderboards = {}
    categories = {
        "most_clicks": (lambda p: p[1].get('clicks', 0)), "most_money": (lambda p: p[1].get('money', 0)),
        "most_time_played": (lambda p: p[1].get('time_played', 0)), "most_money_spent": (lambda p: p[1].get('money_spent', 0)),
        "inventory_value": get_inv_value, "highest_skin_value": get_highest_skin,
        "most_cases_opened": (lambda p: p[1].get('cases_opened', 0)), "monthly_clicks": (lambda p: p[1].get('monthly_clicks', 0)),
        "monthly_cases_opened": (lambda p: p[1].get('monthly_cases_opened', 0)),
    }

    for key, func in categories.items():
        sorted_players = sorted(all_players, key=func, reverse=True)
        sorted_ai = sorted(ai_players, key=func, reverse=True)
        
        full_board = []
        player_idx, ai_idx = 0, 0
        
        while len(full_board) < 1000 and (player_idx < len(sorted_players) or ai_idx < len(sorted_ai)):
            player_score = func(sorted_players[player_idx]) if player_idx < len(sorted_players) else -1
            ai_score = func(sorted_ai[ai_idx]) if ai_idx < len(sorted_ai) else -1

            if player_score >= ai_score:
                full_board.append(sorted_players[player_idx])
                player_idx += 1
            else:
                full_board.append(sorted_ai[ai_idx])
                ai_idx += 1
        
        leaderboards[key] = [{"username": p[0], "value": func(p)} for p in full_board[:1000]]

    return jsonify(leaderboards)

@app.route('/api/game_data/cases')
def get_cases(): return jsonify(GAME_DATA["cases"])
@app.route('/api/game_data/skins')
def get_skins(): return jsonify(GAME_DATA["all_skins"])
@app.route('/api/game_data/rarities')
def get_rarities(): return jsonify(GAME_DATA["rarities"])
@app.route('/api/game_data/ranks')
def get_ranks(): return jsonify(GAME_DATA["ranks"])

if __name__ == '__main__':
    if not load_or_create_files(): sys.exit(1)
    check_and_reset_monthly_leaderboards()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    if not load_or_create_files(): sys.exit(1)
    check_and_reset_monthly_leaderboards()


@app.route('/click', methods=['POST'])
def api_click():
    try:
        data = request.get_json(force=True, silent=True) or {}
        username = data.get('username')
        if not username or username not in DB['players']:
            return jsonify({'success': False, 'message': 'Invalid or missing username.'}), 400
        player = DB['players'][username]
        rank_idx = player.get('rank', 0)
        base = GAME_DATA.get('ranks', {}).get(rank_idx, {}).get('base_clicks', 1) if isinstance(rank_idx, int) else 1
        player['clicks'] = player.get('clicks', 0) + base
        player['money'] = player.get('money', 0) + max(1, int(base * 0.1))
        # update online_users last_action
        DB['online_users'].setdefault(username, {})['last_action'] = time.time()
        save_players_data()
        return jsonify({'success': True, 'clicks': player['clicks'], 'money': player['money']}), 200
    except Exception as e:
        print("ERROR in /click:", e)
        return jsonify({'success': False, 'message': 'Server error on click.'}), 500

@app.route('/buy_case', methods=['POST'])
def api_buy_case():
    try:
        data = request.get_json(force=True, silent=True) or {}
        username = data.get('username')
        case_name = data.get('case_name')
        qty = int(data.get('qty', 1))
        if not username or username not in DB['players']:
            return jsonify({'success': False, 'message': 'Invalid user.'}), 400
        if not case_name or case_name not in GAME_DATA.get('cases', {}):
            return jsonify({'success': False, 'message': 'Invalid case.'}), 400
        player = DB['players'][username]
        case_info = GAME_DATA['cases'][case_name]
        price = int(case_info.get('price', 0)) * qty
        if player.get('money', 0) < price:
            return jsonify({'success': False, 'message': 'Not enough money.'}), 402
        player['money'] -= price
        player_cases = player.setdefault('cases', {})
        player_cases[case_name] = player_cases.get(case_name, 0) + qty
        DB['online_users'].setdefault(username, {})['last_action'] = time.time()
        save_players_data()
        return jsonify({'success': True, 'money': player['money'], 'cases': player_cases}), 200
    except Exception as e:
        print("ERROR in /buy_case:", e)
        return jsonify({'success': False, 'message': 'Server error buying case.'}), 500

@app.route('/update_player', methods=['POST'])
def api_update_player():
    try:
        data = request.get_json(force=True, silent=True) or {}
        actor = data.get('actor')
        target = data.get('username')
        updates = data.get('updates', {})
        if not actor or actor not in DB['players'] or DB['players'][actor].get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Permission denied.'}), 403
        if not target or target not in DB['players']:
            return jsonify({'success': False, 'message': 'Target user not found.'}), 404
        player = DB['players'][target]
        allowed = {'money','clicks','rank','role','is_chat_banned'}
        for k,v in updates.items():
            if k in allowed:
                if k in ('money','clicks','rank'):
                    try:
                        player[k] = int(v)
                    except:
                        pass
                elif k == 'is_chat_banned':
                    player[k] = bool(v)
                else:
                    player[k] = v
        save_players_data()
        return jsonify({'success': True, 'player': player}), 200
    except Exception as e:
        print("ERROR in /update_player:", e)
        return jsonify({'success': False, 'message': 'Server error updating player.'}), 500

@app.route('/server_stats', methods=['GET'])
def api_server_stats():
    try:
        online = list(DB.get('online_users', {}).keys())
        total = len(DB.get('players', {}))
        active = []
        idle = []
        playing = []
        for u, info in DB.get('online_users', {}).items():
            last = info.get('last_action', info.get('login_time', 0))
            age = time.time() - last
            if age <= 10:
                playing.append(u)
            elif age <= 60:
                active.append(u)
            else:
                idle.append(u)
        return jsonify({'success': True, 'total_players': total, 'online_count': len(online), 'playing': playing, 'active': active, 'idle': idle}), 200
    except Exception as e:
        print("ERROR in /server_stats:", e)
        return jsonify({'success': False, 'message': 'Server error.'}), 500

@app.route('/get_player_stats/<username>', methods=['GET'])
def api_get_player_stats(username):
    try:
        if username not in DB['players']:
            return jsonify({'success': False, 'message': 'Player not found.'}), 404
        player = DB['players'][username]
        public = {k: player.get(k) for k in ['clicks','money','rank','role','skins','cases','time_played']}
        return jsonify({'success': True, 'player': public}), 200
    except Exception as e:
        print("ERROR in /get_player_stats:", e)
        return jsonify({'success': False, 'message': 'Server error.'}), 500

@app.route('/all_players', methods=['GET'])
def all_players():
    try:
        players = []
        for username, pdata in DB.get('players', {}).items():
            players.append({
                'username': username,
                'money': pdata.get('money',0),
                'clicks': pdata.get('clicks',0),
                'role': pdata.get('role','player')
            })
        return jsonify({'success': True, 'players': players}), 200
    except Exception as e:
        print("ERROR in /all_players:", e)
        return jsonify({'success': False, 'message': 'Server error'}), 500
