from flask import Flask, request, jsonify, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash
import json
import time
import random
from pathlib import Path
import uuid

# --- App Setup ---
app = Flask(__name__, static_folder='.', static_url_path='')
# You must set a secret key for session management to work
app.secret_key = 'a-very-secret-key-that-you-should-change' 

# --- File Paths & Data Loading ---
BASE_DIR = Path(__file__).parent
CHAT_LOG_FILE = BASE_DIR / 'chat_log.json'

def load_json(name):
    p = BASE_DIR / name
    if not p.exists(): return {}
    try:
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_json(name, data):
    p = BASE_DIR / name
    with open(p, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

# Load game data once at startup
PLAYERS = load_json('players.json')
CASES = load_json('cases.json')
SKINS = load_json('skins.json')
RARITIES = load_json('rarities.json')
RANKS = load_json('ranks.json')

# --- Helper Functions ---
def get_skin_value(skin_name):
    rarity_name = SKINS.get(skin_name)
    if rarity_name:
        value_range = RARITIES.get(rarity_name, {}).get('value_range', [1, 1])
        return random.randint(value_range[0], value_range[1])
    return 1

# --- Main Route ---
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

# --- API Routes ---
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
    if username in PLAYERS:
        return jsonify({'success': False, 'message': 'Username already exists.'}), 409
    
    PLAYERS[username] = {
        "password_hash": generate_password_hash(password),
        "role": "player",
        "clicks": 0, "money": 0, "rank": 0,
        "cases": {}, "skins": [],
        "time_played": 0, "money_spent": 0, "cases_opened": 0,
        "is_chat_banned": False,
        "has_changed_username": False, "has_changed_password": False
    }
    save_json('players.json', PLAYERS)
    return jsonify({'success': True, 'message': 'Account created! You can now log in.'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    player = PLAYERS.get(username)

    # This is the corrected logic
    if not player or not player.get('password_hash') or not check_password_hash(player['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    session['username'] = username
    return jsonify({'success': True, 'player_data': player})

# --- Game Data Endpoints ---
@app.route('/api/game_data/<data_type>', methods=['GET'])
def get_game_data(data_type):
    data_map = {'cases': CASES, 'skins': SKINS, 'rarities': RARITIES, 'ranks': RANKS}
    return jsonify(data_map.get(data_type, {}))

@app.route('/api/game_state', methods=['POST'])
def game_state():
    if 'username' not in session: return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    username = session['username']
    data = request.get_json()
    last_chat_id = data.get('last_chat_id', '0')
    
    chat_log = load_json(CHAT_LOG_FILE)
    if not isinstance(chat_log, list): chat_log = []
    
    new_messages = [msg for msg in chat_log if msg['id'] > last_chat_id]

    return jsonify({
        'success': True,
        'player_data': PLAYERS.get(username, {}),
        'new_global_messages': new_messages
    })
    
# --- Gameplay Actions ---
@app.route('/api/click', methods=['POST'])
def click():
    if 'username' not in session: return jsonify({'success': False}), 401
    username = session['username']
    player = PLAYERS[username]
    rank_info = RANKS.get(str(player.get('rank', 0)), {})
    
    player['clicks'] = player.get('clicks', 0) + rank_info.get('base_clicks', 1)
    player['money'] = player.get('money', 0) + rank_info.get('base_clicks', 1)
    
    next_rank_id = str(player.get('rank', 0) + 1)
    if next_rank_id in RANKS and player['clicks'] >= RANKS[next_rank_id]['clicks_needed']:
        player['rank'] = int(next_rank_id)
        
    save_json('players.json', PLAYERS)
    return jsonify({'success': True, 'player_data': player})

@app.route('/api/buy_case', methods=['POST'])
def buy_case():
    if 'username' not in session: return jsonify({'success': False}), 401
    username = session['username']
    data = request.get_json()
    case_name = data['case_name']
    quantity = int(data.get('quantity', 1))

    player = PLAYERS[username]
    case_info = CASES.get(case_name)
    if not case_info: return jsonify({'success': False, 'message': 'Case not found'}), 404

    total_cost = int(case_info.get('price', '0')) * quantity
    if player.get('money', 0) < total_cost:
        return jsonify({'success': False, 'message': 'Not enough money'}), 400

    player['money'] -= total_cost
    player.setdefault('cases', {})[case_name] = player['cases'].get(case_name, 0) + quantity
    save_json('players.json', PLAYERS)
    return jsonify({'success': True, 'player_data': player})

@app.route('/api/open_case', methods=['POST'])
def open_case():
    if 'username' not in session: return jsonify({'success': False}), 401
    username = session['username']
    case_name = request.get_json()['case_name']
    
    player = PLAYERS[username]
    if player.get('cases', {}).get(case_name, 0) < 1:
        return jsonify({'success': False, 'message': 'You do not own that case'}), 400
        
    player['cases'][case_name] -= 1
    if player['cases'][case_name] == 0:
        del player['cases'][case_name]
        
    skin_name = random.choice(CASES.get(case_name, {}).get('skins', [None]))
    if not skin_name: return jsonify({'success': False, 'message': 'Case has no skins'}), 500
    
    new_skin = {"id": str(uuid.uuid4()), "name": skin_name, "value": get_skin_value(skin_name)}
    player.setdefault('skins', []).append(new_skin)
    save_json('players.json', PLAYERS)
    return jsonify({'success': True, 'player_data': player, 'item_won': new_skin})

@app.route('/api/sell_skins', methods=['POST'])
def sell_skins():
    if 'username' not in session: return jsonify({'success': False}), 401
    username = session['username']
    skin_ids_to_sell = request.get_json().get('skin_ids', [])
    
    player = PLAYERS[username]
    skins_to_keep = []
    sell_value = 0
    
    for skin in player.get('skins', []):
        if skin.get('id') in skin_ids_to_sell:
            sell_value += skin.get('value', 0)
        else:
            skins_to_keep.append(skin)
            
    player['skins'] = skins_to_keep
    player['money'] = player.get('money', 0) + sell_value
    save_json('players.json', PLAYERS)
    return jsonify({'success': True, 'player_data': player})

# --- Chat Endpoint ---
@app.route('/api/chat/global', methods=['POST'])
def send_global_chat():
    if 'username' not in session: return jsonify({'success': False}), 401
    username = session['username']
    message = request.get_json().get('message')
    if not message: return jsonify({'success': False, 'message': 'Empty message'}), 400
    
    chat_log = load_json(CHAT_LOG_FILE)
    if not isinstance(chat_log, list): chat_log = []
    
    new_msg = {'id': str(time.time()), 'sender': username, 'msg': message}
    chat_log.append(new_msg)
    save_json(CHAT_LOG_FILE, chat_log[-200:]) # Keep last 200 messages
    return jsonify({'success': True})

# --- Placeholder Endpoints ---
@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    return jsonify({'success': True, 'message': 'Profile updated successfully!'})

@app.route('/api/leaderboards', methods=['GET'])
def leaderboards():
    sorted_clicks = sorted(PLAYERS.items(), key=lambda item: item[1].get('clicks', 0), reverse=True)
    most_clicks_data = [{"username": u, "value": d.get('clicks', 0)} for u, d in sorted_clicks]
    return jsonify({"most_clicks": most_clicks_data, "most_money": [], "most_time_played": []})

@app.route('/api/admin/server_stats', methods=['POST'])
def server_stats():
    return jsonify({ "online_players": 0, "total_players": len(PLAYERS) })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
