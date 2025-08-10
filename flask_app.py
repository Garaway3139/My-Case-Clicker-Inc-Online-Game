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
DB = { 
    "players": {}, 
    "online_users": {}, 
    "chats": {
        "global": [],
        "staff": []
        # Private chats are stored dynamically, e.g., DB["chats"]["admin-player1"]
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
        player["clicks"] = player.get("clicks", 0) + random.randint(100, 1500)
        player["money"] = player.get("money", 0) + random.randint(200, 3000)
        player["time_played"] = player.get("time_played", 0) + random.randint(60, 300)
        if random.random() < 0.1:
            player["cases_opened"] = player.get("cases_opened", 0) + random.randint(1, 5)

def save_players_data():
    if PLAYERS_FILE:
        update_ai_players()
        with open(PLAYERS_FILE, 'w') as f:
            json.dump(DB["players"], f, indent=4)

def load_or_create_files():
    global PLAYERS_FILE, SERVER_STATE_FILE
    try:
        required_files = ["rarities.json", "ranks.json", "skins.json", "cases.json"]
        for filename in required_files:
            path = find_file(filename, BASE_DIR)
            if not path:
                raise FileNotFoundError(f"CRITICAL: Could not find '{filename}'")
            with open(path, 'r') as f:
                if filename == "ranks.json":
                    GAME_DATA["ranks"] = {int(k): v for k, v in json.load(f).items()}
                else:
                    key = filename.split('.')[0]
                    GAME_DATA[key] = json.load(f)
        GAME_DATA["all_skins"] = GAME_DATA.pop("skins")
    except Exception as e:
        print(f"FATAL ERROR loading game data: {e}", file=sys.stderr)
        return False

    PLAYERS_FILE = find_file("players.json", BASE_DIR) or os.path.join(BASE_DIR, 'players.json')
    try:
        with open(PLAYERS_FILE, 'r') as f:
            DB["players"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        DB["players"] = {}

    ai_player_count = sum(1 for p in DB["players"].values() if p.get("role") == "ai")
    TARGET_AI_COUNT = 100
    if ai_player_count < TARGET_AI_COUNT:
        print(f"Generating {TARGET_AI_COUNT - ai_player_count} new AI players...")
        for _ in range(TARGET_AI_COUNT - ai_player_count):
            ai_name = generate_ai_gamertag()
            while ai_name in DB["players"]:
                ai_name = generate_ai_gamertag()
            DB["players"][ai_name] = {
                "username": ai_name, "role": "ai", "clicks": random.randint(1000, 5000000), "money": random.randint(5000, 10000000),
                "skins": [], "cases": {}, "time_played": random.randint(3600, 360000), "money_spent": random.randint(1000, 1000000),
                "cases_opened": random.randint(10, 1000), "is_chat_banned": True, "rank": random.randint(1, 25)
            }
    
    # FIX: Boost top 10 AI for leaderboards
    all_ai = sorted([p for p in DB["players"].values() if p.get("role") == "ai"], key=lambda x: x.get('clicks', 0), reverse=True)
    for player in all_ai[:10]:
        player['money'] = player.get('money', 0) + random.randint(50_000_000, 100_000_000)
        player['clicks'] = player.get('clicks', 0) + random.randint(50_000_000, 100_000_000)

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
            user_role = DB["players"].get(username, {}).get("role")
            if user_role not in required_roles:
                return jsonify({"success": False, "message": "Permission denied."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- CORE GAME ROUTES ---
@app.route('/')
def index():
    path = find_file("index.html", BASE_DIR)
    return render_template_string(open(path).read()) if path else ("<h1>index.html not found</h1>", 404)

@app.route('/api/login', methods=['POST'])
def login():
    username, password = request.json.get('username'), request.json.get('password')
    player = DB["players"].get(username)
    if not player or player.get("password_hash") != md5_hash(password):
        return jsonify({"success": False, "message": "Invalid username or password."}), 401
    
    banned_until = player.get('banned_until', 0)
    if banned_until > time.time():
        message = "You are permanently banned." if banned_until > 4000000000 else f"You are banned until {datetime.fromtimestamp(banned_until).strftime('%Y-%m-%d %H:%M')}"
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
    
    response_chats = {"global": DB["chats"]["global"][-50:]}
    if DB["players"][username].get("role") in ['helpdesk', 'moderator', 'admin']:
        response_chats["staff"] = DB["chats"]["staff"][-50:]
    # This is a simple way to add private chats, a real app might fetch them on demand
    for key, chat in DB["chats"].items():
        if username in key.split('-') and key not in ["global", "staff"]:
            response_chats[key] = chat
            
    return jsonify({
        "success": True, 
        "online_players": list(DB["online_users"].keys()), 
        "chats": response_chats,
        "player_data": DB["players"].get(username)
    })

# FIX: Corrected the case opening logic
@app.route('/api/open_case', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def open_case():
    username, case_name = request.json.get('username'), request.json.get('case_name')
    player = DB["players"][username]
    if player.get("cases", {}).get(case_name, 0) < 1:
        return jsonify({"success": False, "message": "You don't have that case."}), 400

    case_info = GAME_DATA["cases"].get(case_name)
    if not case_info: return jsonify({"success": False, "message": "Server error: Invalid case data."}), 500
    
    valid_skins = {skin_name: GAME_DATA["rarities"][rarity] for skin_name, rarity in GAME_DATA["all_skins"].items() if skin_name in case_info["skins"]}
    if not valid_skins: return jsonify({"success": False, "message": "Server error: No valid skins found for this case."}), 500

    # Create a weighted list for random selection
    weighted_skins = []
    for skin_name, rarity_data in valid_skins.items():
        weight = int(rarity_data.get("probability", 0) * 1000) # Use integers for weighting
        weighted_skins.extend([skin_name] * weight)
    
    if not weighted_skins: return jsonify({"success": False, "message": "Server error: Could not determine item odds."}), 500

    chosen_skin_name = random.choice(weighted_skins)
    chosen_rarity = valid_skins[chosen_skin_name]
    min_val, max_val = chosen_rarity["value_range"]
    item_won = {"id": str(uuid.uuid4()), "name": chosen_skin_name, "value": round(random.uniform(min_val, max_val), 2)}
    
    player["cases"][case_name] -= 1
    player["cases_opened"] = player.get("cases_opened", 0) + 1
    player.setdefault("skins", []).append(item_won)
    save_players_data()
    return jsonify({"success": True, "player_data": player, "item_won": item_won})

# FIX: Corrected the leaderboard logic
@app.route('/api/leaderboards')
def get_leaderboards():
    # Filter out admins and moderators from the player list for leaderboards
    eligible_players = [p for p in DB["players"].values() if p.get("role") not in ["admin", "moderator"]]
    
    def get_inv_value(p): return sum(s.get('value', 0) for s in p.get('skins', []))
    def get_highest_skin(p): return max((s.get('value', 0) for s in p.get('skins', [])), default=0)

    leaderboards = {}
    categories = {
        "most_clicks": lambda p: p.get('clicks', 0), 
        "most_money": lambda p: p.get('money', 0),
        "inventory_value": get_inv_value, 
        "highest_skin_value": get_highest_skin,
        "most_cases_opened": lambda p: p.get('cases_opened', 0)
    }
    
    for key, func in categories.items():
        # Using .get() ensures that if a player is missing a key, it defaults to 0 and doesn't crash.
        sorted_players = sorted(eligible_players, key=func, reverse=True)
        # Add username to each player dict before sending
        leaderboards[key] = [{"username": list(DB['players'].keys())[list(DB['players'].values()).index(p)], "value": func(p)} for p in sorted_players[:100]]

    return jsonify(leaderboards)

# FIX: New unified chat endpoint
@app.route('/api/chat/send', methods=['POST'])
@role_required(['player', 'helpdesk', 'moderator', 'admin'])
def send_chat():
    sender = request.json.get('username')
    channel = request.json.get('channel')
    message = request.json.get('message')
    receiver = request.json.get('receiver') # For private messages

    if not all([channel, message]): return jsonify({"success": False, "message": "Missing channel or message."}), 400
    if DB["players"][sender].get("is_chat_banned"): return jsonify({"success": False, "message": "You are chat banned."}), 403

    msg_obj = {"id": str(uuid.uuid4()), "sender": sender, "msg": message, "timestamp": time.time()}

    if channel == "staff":
        if DB["players"][sender].get("role") not in ['helpdesk', 'moderator', 'admin']:
            return jsonify({"success": False, "message": "Not allowed in staff chat."}), 403
        DB["chats"]["staff"].append(msg_obj)
        DB["chats"]["staff"] = DB["chats"]["staff"][-100:]
    elif channel == "private":
        if not receiver: return jsonify({"success": False, "message": "Receiver not specified."}), 400
        # Create a unique, sorted key for the private conversation
        convo_key = "-".join(sorted([sender, receiver]))
        if convo_key not in DB["chats"]: DB["chats"][convo_key] = []
        DB["chats"][convo_key].append(msg_obj)
        DB["chats"][convo_key] = DB["chats"][convo_key][-100:]
    else: # Default to global
        DB["chats"]["global"].append(msg_obj)
        DB["chats"]["global"] = DB["chats"]["global"][-100:]
        
    return jsonify({"success": True})

# --- ADMIN ROUTES ---
@app.route('/api/admin/all_players')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_all_players():
    # Return a dictionary of players, excluding sensitive data
    return jsonify({uname: {k:v for k,v in udata.items() if k != 'password_hash'} for uname, udata in DB["players"].items()})

@app.route('/api/admin/player_details/<target_username>')
@role_required(['helpdesk', 'moderator', 'admin'])
def get_player_details(target_username):
    player = DB["players"].get(target_username)
    if not player: return jsonify({"success": False, "message": "Player not found."}), 404
    safe_data = {k:v for k,v in player.items() if k != 'password_hash'}
    safe_data['is_online'] = target_username in DB["online_users"]
    return jsonify({"success": True, "player": safe_data})

@app.route('/api/admin/update_player', methods=['POST'])
@role_required(['admin']) # Only full admins can update player values
def admin_update_player():
    target_user, updates = request.json.get('target_user'), request.json.get('updates')
    player = DB["players"].get(target_user)
    if not player: return jsonify({"success": False, "message": "User not found."})
    for key, value in updates.items():
        if key in ["money", "clicks", "rank"]:
            try: player[key] = int(value)
            except (ValueError, TypeError): continue
    save_players_data()
    return jsonify({"success": True, "message": f"{target_user} updated successfully."})

@app.route('/api/admin/set_ban', methods=['POST'])
@role_required(['moderator', 'admin'])
def set_ban():
    requester_role = DB["players"][request.json['username']]['role']
    target_user, ban_type, duration_hours = request.json.get('target_user'), request.json.get('ban_type'), request.json.get('duration_hours')
    player = DB["players"].get(target_user)
    if not player: return jsonify({"success": False, "message": "User not found."})
    if player.get('role') == 'admin' or (player.get('role') == 'moderator' and requester_role != 'admin'):
        return jsonify({"success": False, "message": "Insufficient permissions to ban this user."})
    
    if ban_type == "chat":
        player['is_chat_banned'] = not player.get('is_chat_banned', False)
        status = "banned from" if player['is_chat_banned'] else "unbanned from"
        message = f"Successfully {status} chat for {target_user}."
    elif ban_type == "server":
        if duration_hours:
            player['banned_until'] = time.time() + (int(duration_hours) * 3600)
            message = f"Successfully banned {target_user} for {duration_hours} hours."
        else: # Permanent
            player['banned_until'] = 4102444800 # Year 2100
            message = f"Successfully PERMANENTLY banned {target_user}."
        if target_user in DB['online_users']: del DB['online_users'][target_user] # Kick them if online
    else: return jsonify({"success": False, "message": "Invalid ban type."})
    
    save_players_data()
    return jsonify({"success": True, "message": message})


# --- Other routes like signup, click, buy_case are in the previous file and should be included ---
# For brevity, only the fixed/new routes are shown here.
# Make sure to have the full set of routes from the last working version.

if __name__ == '__main__':
    if not load_or_create_files(): sys.exit(1)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
else:
    load_or_create_files()
