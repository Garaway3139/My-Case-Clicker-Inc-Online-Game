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
DB = { "players": {}, "online_users": {}, "global_chat": [], "server_state": {}, "private_messages": {} }
GAME_DATA = { "rarities": {}, "ranks": {}, "all_skins": {}, "cases": {} }

# --- Utility Functions ---
def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def find_file(filename, search_path):
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def generate_ai_gamertag():
    """Generates a random AI gamertag."""
    ADJECTIVES = ["Silent", "Shadow", "Rogue", "Quantum", "Cosmic", "Vex", "Zero", "Apex", "Iron", "Cyber"]
    NOUNS = ["Spectre", "Hunter", "Reaper", "Phantom", "Glitch", "Warden", "Nexus", "Vortex", "Bot", "Unit"]
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    number = random.randint(100, 999)
    return f"{adj}{noun}{number}"

def update_ai_players():
    """Called periodically to simulate AI player progress."""
    ai_players = [name for name, data in DB["players"].items() if data.get("role") == "ai"]
    if not ai_players:
        return
    for _ in range(min(5, len(ai_players))):
        player_name = random.choice(ai_players)
        player = DB["players"][player_name]
        player["clicks"] += random.randint(100, 1500)
        player["money"] += random.randint(200, 3000)
        player["time_played"] += random.randint(60, 300)
        if random.random() < 0.1:
            player["cases_opened"] += random.randint(1, 5)
            player["monthly_cases_opened"] +=1

def save_players_data():
    if PLAYERS_FILE:
        if random.random() < 0.25:
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
        for filename in required_game_files:
            path = find_file(filename, BASE_DIR)
            if path is None: return False
            file_paths[filename] = path
        with open(file_paths["rarities.json"], 'r') as f: GAME_DATA["rarities"] = json.load(f)
        with open(file_paths["ranks.json"], 'r') as f: GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
        with open(file_paths["skins.json"], 'r') as f: GAME_DATA["all_skins"] = json.load(f)
        with open(file_paths["cases.json"], 'r') as f: GAME_DATA["cases"] = json.load(f)
    except Exception as e:
        print(f"FATAL ERROR loading game data: {e}")
        return False

    PLAYERS_FILE = find_file("players.json", BASE_DIR) or os.path.join(BASE_DIR, 'players.json')
    try:
        with open(PLAYERS_FILE, 'r') as f: DB["players"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        DB["players"] = {}
    
    ai_player_count = sum(1 for p in DB["players"].values() if p.get("role") == "ai")
    TARGET_AI_COUNT = 100
    if ai_player_count < TARGET_AI_COUNT:
        print(f"Generating {TARGET_AI_COUNT - ai_player_count} new AI players...")
        for _ in range(TARGET_AI_COUNT - ai_player_count):
            ai_name = generate_ai_gamertag()
            while ai_name in DB["players"]: ai_name = generate_ai_gamertag()
            DB["players"][ai_name] = {
                "password_hash": "", "role": "ai", "clicks": random.randint(1000, 1000000), "money": random.randint(5000, 5000000),
                "skins": [], "cases": {}, "time_played": random.randint(3600, 360000), "money_spent": random.randint(1000, 1000000),
                "cases_opened": random.randint(10, 1000), "monthly_clicks": random.randint(100, 10000),
                "monthly_cases_opened": random.randint(1, 50), "is_chat_banned": True, "rank": random.randint(1, 18)
            }
    
    save_players_data()
    SERVER_STATE_FILE = find_file("server_state.json", BASE_DIR) or os.path.join(BASE_DIR, 'server_state.json')
    try:
        with open(SERVER_STATE_FILE, 'r') as f: DB["server_state"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        DB["server_state"] = {"last_monthly_reset": datetime.now().strftime("%Y-%m")}
        save_server_state()
    return True

def check_and_reset_monthly_leaderboards():
    current_month = datetime.now().strftime("%Y-%m")
    if DB["server_state"].get("last_monthly_reset") != current_month:
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
    valid_skins = [s for s in case_info["skins"] if s in GAME_DATA["all_skins"]]
    if not valid_skins: return None
    total_probability = sum(GAME_DATA["rarities"][GAME_DATA["all_skins"][skin]]["probability"] for skin in valid_skins)
    if total_probability == 0: return None
    roll = random.uniform(0, total_probability)
    cumulative_probability = 0
    for skin in valid_skins:
        rarity_name = GAME_DATA["all_skins"][skin]
        cumulative_probability += GAME_DATA["rarities"][rarity_name]["probability"]
        if roll <= cumulative_probability:
            min_val, max_val = GAME_DATA["rarities"][rarity_name]["value_range"]
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
            if DB["players"].get(username, {}).get("role") not in required_roles:
                return jsonify({"success": False, "message": "Permission denied."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    index_path = find_file("index.html", BASE_DIR)
    return render_template_string(open(index_path).read()) if index_path else ("<h1>index.html not found</h1>", 404)

@app.route('/api/signup', methods=['POST'])
def signup():
    username = request.json.get('username')
    password = request.json.get('password')
    if not all([username, password]): return jsonify({"success": False, "message": "Username and password are required."}), 400
    if len(username) < 3 or len(username) > 20 or " " in username: return jsonify({"success": False, "message": "Username must be 3-20 characters with no spaces."}), 400
    if username.lower() in {k.lower() for k in DB["players"]}: return jsonify({"success": False, "message": "Username already exists."}), 400
    
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
    
    banned_until = player.get('banned_until', 0)
    if banned_until > time.time():
        remaining_time_str = datetime.fromtimestamp(banned_until).strftime('%Y-%m-%d %H:%M:%S')
        return jsonify({"success": False, "message": f"You are banned until {remaining_time_str}."}), 403

    DB["online_users"][username] = {"last_seen": time.time(), "role": player.get("role", "player")}
    return jsonify({"success": True, "player_data": player})

@app.route('/api/game_state', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def get_game_state():
    username = request.json.get('username')
    DB["online_users"][username]["last_seen"] = time.time()
    DB["players"][username]["time_played"] = DB["players"][username].get("time_played", 0) + 2
    
    for user, data in list(DB["online_users"].items()):
        if time.time() - data["last_seen"] > 30: del DB["online_users"][user]
            
    last_chat_id = request.json.get('last_chat_id', '0')
    new_global_messages = [msg for msg in DB["global_chat"] if msg["id"] > last_chat_id]
    
    return jsonify({"success": True, "online_players": list(DB["online_users"].keys()), "new_global_messages": new_global_messages, "player_data": DB["players"].get(username)})

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
    
    case_price_str = GAME_DATA["cases"].get(case_name, {}).get('price', '0')
    total_cost = float(case_price_str) * quantity
    player = DB["players"][username]
    if player.get("money", 0) < total_cost: return jsonify({"success": False, "message": "Not enough money!"}), 400
    
    player["money"] -= total_cost
    player["money_spent"] = player.get("money_spent", 0) + total_cost
    player["cases"][case_name] = player["cases"].get(case_name, 0) + quantity
    save_players_data()
    return jsonify({"success": True, "player_data": player})

# Add other non-admin routes like open_case, sell_skins, etc. here...
# ... (Assuming they are the same as before for brevity)

# --- Admin & Staff Routes ---
@app.route('/api/admin/all_players')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_all_players():
    return jsonify({uname: {k:v for k,v in udata.items() if k != 'password_hash'} for uname, udata in DB["players"].items()})

@app.route('/api/admin/player/<target_username>')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_player_details(target_username):
    player = DB["players"].get(target_username)
    if not player: return jsonify({"success": False, "message": "Player not found."}), 404
    safe_data = {k:v for k,v in player.items() if k != 'password_hash'}
    safe_data['is_online'] = target_username in DB["online_users"]
    return jsonify({"success": True, "player": safe_data})

@app.route('/api/admin/update_player', methods=['POST'])
@role_required(['admin']) # Only admins can update player values directly
def admin_update_player():
    target_username = request.json.get('target_user')
    updates = request.json.get('updates')
    player = DB["players"].get(target_username)
    if not player: return jsonify({"success": False, "message": "Target user not found."}), 404
    for key, value in updates.items():
        if key in ["money", "clicks", "rank"]:
            try: player[key] = int(value)
            except (ValueError, TypeError): continue
    save_players_data()
    return jsonify({"success": True, "message": f"{target_username} updated."})

@app.route('/api/admin/ban_player', methods=['POST'])
@role_required(['moderator', 'admin'])
def ban_player():
    requester = DB["players"][request.json['username']]
    target_user = request.json.get('target_user')
    target_player = DB["players"].get(target_user)
    if not target_player: return jsonify({"success": False, "message": "Player not found."}), 404
    if target_player.get("role") == 'admin' or (target_player.get("role") == 'moderator' and requester['role'] != 'admin'):
        return jsonify({"success": False, "message": "Insufficient permissions."}), 403
    duration_seconds = request.json.get('duration_seconds')
    target_player['banned_until'] = (time.time() + duration_seconds) if duration_seconds else 4102444800
    if target_user in DB['online_users']: del DB['online_users'][target_user] # Kick them
    save_players_data()
    return jsonify({"success": True, "message": f"{target_user} has been banned."})

@app.route('/api/helpdesk/set_chat_ban', methods=['POST'])
@role_required(['helpdesk', 'moderator', 'admin'])
def set_chat_ban():
    # This route is simplified as full ban logic is now in ban_player
    target_username = request.json.get('target_user')
    is_banned = request.json.get('is_banned')
    DB["players"][target_username]["is_chat_banned"] = bool(is_banned)
    save_players_data()
    return jsonify({"success": True, "message": f"{target_username}'s chat status updated."})

@app.route('/api/admin/private_message', methods=['POST'])
@role_required(['helpdesk', 'moderator', 'admin'])
def private_message():
    sender, receiver, message = request.json.get('username'), request.json.get('target_user'), request.json.get('message')
    if not all([receiver, message]): return jsonify({"success": False, "message": "Receiver and message required."}), 400
    convo_key = "-".join(sorted([sender, receiver]))
    if convo_key not in DB['private_messages']: DB['private_messages'][convo_key] = []
    DB['private_messages'][convo_key].append({"id": str(uuid.uuid4()), "sender": sender, "msg": message, "timestamp": time.time()})
    DB['private_messages'][convo_key] = DB['private_messages'][convo_key][-50:]
    return jsonify({"success": True, "message": "Message sent."})


@app.route('/api/leaderboards')
def get_leaderboards():
    check_and_reset_monthly_leaderboards()
    eligible_players = [p for p in DB["players"].items() if p[1].get("role") not in ["admin", "moderator"]]
    
    def get_inv_value(p): return sum(s['value'] for s in p[1].get('skins', []))
    def get_highest_skin(p): return max((s['value'] for s in p[1].get('skins', [])), default=0)

    leaderboards = {}
    categories = {
        "most_clicks": lambda p: p[1].get('clicks', 0), "most_money": lambda p: p[1].get('money', 0),
        "inventory_value": get_inv_value, "highest_skin_value": get_highest_skin
    }
    for key, func in categories.items():
        sorted_players = sorted(eligible_players, key=func, reverse=True)
        leaderboards[key] = [{"username": p[0], "value": func(p)} for p in sorted_players[:100]]
    return jsonify(leaderboards)

# Game Data Routes
@app.route('/api/game_data/<data_type>')
def get_game_data(data_type):
    data_map = {"cases": "cases", "skins": "all_skins", "rarities": "rarities", "ranks": "ranks"}
    if data_type in data_map:
        return jsonify(GAME_DATA.get(data_map[data_type], {}))
    return jsonify({"success": False, "message": "Invalid data type"}), 404

@app.errorhandler(Exception)
def handle_uncaught_exceptions(e):
    print(f"!! Uncaught Exception: {e}", file=sys.stderr)
    return jsonify({"success": False, "message": "Internal Server Error."}), 500

if __name__ == '__main__':
    if not load_or_create_files(): sys.exit(1)
    app.run(host='0.0.0.0', port=5000)
else:
    load_or_create_files()
