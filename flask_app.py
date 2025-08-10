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
DB = { 
    "players": {}, 
    "online_users": {}, 
    "chats": {
        "global": [],
        "staff": []
        # Private chats will be stored as "user1-user2": []
    },
    "server_state": {} 
}
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
    ADJECTIVES = ["Silent", "Shadow", "Rogue", "Quantum", "Cosmic", "Vex", "Zero", "Apex", "Iron", "Cyber"]
    NOUNS = ["Spectre", "Hunter", "Reaper", "Phantom", "Glitch", "Warden", "Nexus", "Vortex", "Bot", "Unit"]
    return f"{random.choice(ADJECTIVES)}{random.choice(NOUNS)}{random.randint(100, 999)}"

def update_ai_players():
    ai_players = [name for name, data in DB["players"].items() if data.get("role") == "ai"]
    if not ai_players: return
    for _ in range(min(10, len(ai_players))):
        player_name = random.choice(ai_players)
        player = DB["players"][player_name]
        player["clicks"] += random.randint(100, 1500)
        player["money"] += random.randint(200, 3000)
        player["time_played"] += random.randint(60, 300)
        if random.random() < 0.1:
            player["cases_opened"] += random.randint(1, 5)

def save_players_data():
    if PLAYERS_FILE:
        update_ai_players()
        with open(PLAYERS_FILE, 'w') as f:
            json.dump(DB["players"], f, indent=4)

def load_or_create_files():
    global PLAYERS_FILE, SERVER_STATE_FILE
    try:
        for filename in ["rarities.json", "ranks.json", "skins.json", "cases.json"]:
            path = find_file(filename, BASE_DIR)
            if not path: raise FileNotFoundError(f"{filename} not found")
            with open(path, 'r') as f:
                if filename == "ranks.json":
                    GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
                else:
                    GAME_DATA[filename.split('.')[0]] = json.load(f)
        GAME_DATA["all_skins"] = GAME_DATA.pop("skins")
    except Exception as e:
        print(f"FATAL ERROR loading game data: {e}", file=sys.stderr)
        return False

    PLAYERS_FILE = find_file("players.json", BASE_DIR) or os.path.join(BASE_DIR, 'players.json')
    try:
        with open(PLAYERS_FILE, 'r') as f: DB["players"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        DB["players"] = {}

    ai_players = {k:v for k,v in DB["players"].items() if v.get("role") == "ai"}
    TARGET_AI_COUNT = 100
    if len(ai_players) < TARGET_AI_COUNT:
        for _ in range(TARGET_AI_COUNT - len(ai_players)):
            ai_name = generate_ai_gamertag()
            while ai_name in DB["players"]: ai_name = generate_ai_gamertag()
            DB["players"][ai_name] = {
                "role": "ai", "clicks": random.randint(1000, 5000000), "money": random.randint(5000, 10000000),
                "skins": [], "cases": {}, "time_played": random.randint(3600, 360000),
                "money_spent": random.randint(1000, 1000000), "cases_opened": random.randint(10, 1000),
                "is_chat_banned": True, "rank": random.randint(1, 25)
            }
    
    # Boost top 10 AI for leaderboards
    all_ai = sorted([p for p in DB["players"].values() if p.get("role") == "ai"], key=lambda x: x['clicks'], reverse=True)
    for i, player in enumerate(all_ai[:10]):
        player['money'] = random.randint(50_000_000, 100_000_000)
        player['clicks'] = random.randint(50_000_000, 100_000_000)

    save_players_data()
    return True

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

# --- CORE GAME ROUTES ---
@app.route('/')
def index():
    path = find_file("index.html", BASE_DIR)
    return render_template_string(open(path).read()) if path else ("index.html not found", 404)

@app.route('/api/login', methods=['POST'])
def login():
    username, password = request.json.get('username'), request.json.get('password')
    player = DB["players"].get(username)
    if not player or player.get("password_hash") != md5_hash(password):
        return jsonify({"success": False, "message": "Invalid username or password."}), 401
    
    banned_until = player.get('banned_until', 0)
    if banned_until > time.time():
        if banned_until > 4000000000: message = "You are permanently banned."
        else: message = f"You are banned until {datetime.fromtimestamp(banned_until).strftime('%Y-%m-%d %H:%M')}"
        return jsonify({"success": False, "message": message}), 403

    DB["online_users"][username] = {"last_seen": time.time(), "role": player.get("role", "player")}
    return jsonify({"success": True, "player_data": player})

@app.route('/api/game_state', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def get_game_state():
    username = request.json.get('username')
    DB["online_users"][username]["last_seen"] = time.time()
    for user, data in list(DB["online_users"].items()):
        if time.time() - data["last_seen"] > 30: del DB["online_users"][user]
    
    # This is a simplified chat update, a full implementation would track last seen message IDs per channel
    response_chats = {"global": DB["chats"]["global"][-50:], "staff": []}
    if DB["players"][username].get("role") in ['helpdesk', 'moderator', 'admin']:
        response_chats["staff"] = DB["chats"]["staff"][-50:]
    
    return jsonify({
        "success": True, 
        "online_players": list(DB["online_users"].keys()), 
        "chats": response_chats,
        "player_data": DB["players"].get(username)
    })

@app.route('/api/open_case', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def open_case():
    username, case_name = request.json.get('username'), request.json.get('case_name')
    player = DB["players"][username]
    if player.get("cases", {}).get(case_name, 0) < 1:
        return jsonify({"success": False, "message": "You don't have that case."})

    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return jsonify({"success": False, "message": "Invalid case data."})
    
    valid_skins = {s: GAME_DATA["rarities"][GAME_DATA["all_skins"][s]] for s in case_info["skins"] if s in GAME_DATA["all_skins"]}
    if not valid_skins: return jsonify({"success": False, "message": "No valid skins in this case."})

    total_prob = sum(r["probability"] for r in valid_skins.values())
    roll = random.uniform(0, total_prob)
    
    item_won = None
    cumulative_prob = 0
    for skin, rarity_data in valid_skins.items():
        cumulative_prob += rarity_data["probability"]
        if roll <= cumulative_prob:
            min_val, max_val = rarity_data["value_range"]
            item_won = {"id": str(uuid.uuid4()), "name": skin, "value": round(random.uniform(min_val, max_val), 2)}
            break
    
    if not item_won: return jsonify({"success": False, "message": "Error determining item."})

    player["cases"][case_name] -= 1
    player["cases_opened"] = player.get("cases_opened", 0) + 1
    player.setdefault("skins", []).append(item_won)
    save_players_data()
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

@app.route('/api/leaderboards')
def get_leaderboards():
    eligible_players = [p for p in DB["players"].values() if p.get("role") not in ["admin", "moderator"]]
    
    def get_inv_value(p): return sum(s.get('value', 0) for s in p.get('skins', []))
    def get_highest_skin(p): return max((s.get('value', 0) for s in p.get('skins', [])), default=0)

    leaderboards = {}
    categories = {
        "most_clicks": lambda p: p.get('clicks', 0), "most_money": lambda p: p.get('money', 0),
        "inventory_value": get_inv_value, "highest_skin_value": get_highest_skin,
        "most_cases_opened": lambda p: p.get('cases_opened', 0)
    }
    for key, func in categories.items():
        sorted_players = sorted(eligible_players, key=func, reverse=True)
        leaderboards[key] = [{"username": p.get('username', list(DB['players'].keys())[list(DB['players'].values()).index(p)]), "value": func(p)} for p in sorted_players[:100]]

    return jsonify(leaderboards)

@app.route('/api/chat/send', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def send_chat():
    sender, channel, message = request.json.get('username'), request.json.get('channel'), request.json.get('message')
    if not all([channel, message]): return jsonify({"success": False}), 400
    if DB["players"][sender].get("is_chat_banned"): return jsonify({"success": False, "message": "You are chat banned."}), 403

    msg_obj = {"id": str(uuid.uuid4()), "sender": sender, "msg": message, "timestamp": time.time()}
    
    if channel == "staff" and DB["players"][sender].get("role") not in ['helpdesk', 'moderator', 'admin']:
        return jsonify({"success": False, "message": "Not allowed in staff chat."}), 403
    
    if channel not in DB["chats"]: DB["chats"][channel] = []
    DB["chats"][channel].append(msg_obj)
    DB["chats"][channel] = DB["chats"][channel][-100:]
    return jsonify({"success": True})

# --- ADMIN ROUTES ---
@app.route('/api/admin/player_details/<target_username>')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_player_details(target_username):
    player = DB["players"].get(target_username)
    if not player: return jsonify({"success": False}), 404
    safe_data = {k:v for k,v in player.items() if k != 'password_hash'}
    safe_data['is_online'] = target_username in DB["online_users"]
    return jsonify({"success": True, "player": safe_data})

@app.route('/api/admin/update_player', methods=['POST'])
@role_required(['admin'])
def admin_update_player():
    target_user, updates = request.json.get('target_user'), request.json.get('updates')
    player = DB["players"].get(target_user)
    if not player: return jsonify({"success": False, "message": "User not found."})
    for key, value in updates.items():
        if key in ["money", "clicks", "rank"]: player[key] = int(value)
    save_players_data()
    return jsonify({"success": True, "message": f"{target_user} updated."})

@app.route('/api/admin/set_ban', methods=['POST'])
@role_required(['moderator', 'admin'])
def set_ban():
    requester_role = DB["players"][request.json['username']]['role']
    target_user, ban_type, duration_hours = request.json.get('target_user'), request.json.get('ban_type'), request.json.get('duration_hours')
    player = DB["players"].get(target_user)
    if not player: return jsonify({"success": False, "message": "User not found."})
    if player.get('role') == 'admin' or (player.get('role') == 'moderator' and requester_role != 'admin'):
        return jsonify({"success": False, "message": "Insufficient permissions."})
    
    if ban_type == "chat":
        player['is_chat_banned'] = not player.get('is_chat_banned', False)
        status = "banned from" if player['is_chat_banned'] else "unbanned from"
        message = f"{target_user} {status} chat."
    elif ban_type == "server":
        if duration_hours:
            player['banned_until'] = time.time() + (int(duration_hours) * 3600)
            message = f"{target_user} banned for {duration_hours} hours."
        else: # Permanent
            player['banned_until'] = 4102444800 
            message = f"{target_user} permanently banned."
        if target_user in DB['online_users']: del DB['online_users'][target_user]
    else: return jsonify({"success": False, "message": "Invalid ban type."})
    
    save_players_data()
    return jsonify({"success": True, "message": message})


# --- Other routes like signup, click, buy_case, etc. would go here ---
# They are omitted for brevity but are assumed to be the same as the previous version.
# Make sure to copy them back in from your last working file.

if __name__ == '__main__':
    if not load_or_create_files(): sys.exit(1)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    load_or_create_files()
