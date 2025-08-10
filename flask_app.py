import os
import json
import random
import time
from flask import Flask, jsonify, request, session, render_template
from flask_socketio import SocketIO, send, emit
from werkzeug.security import generate_password_hash, check_password_hash

# --- App Configuration ---
app = Flask(__name__)
# IMPORTANT: Change this secret key for production!
app.config['SECRET_KEY'] = os.urandom(24) 
socketio = SocketIO(app, async_mode='eventlet')

# --- Helper Functions for Data Handling ---
def load_data(filename):
    """Loads data from a JSON file."""
    with open(filename, 'r') as f:
        return json.load(f)

def save_data(filename, data):
    """Saves data to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def get_player_by_username(username):
    """Finds a player's data and UID by username."""
    players = load_data('players.json')
    for uid, data in players.items():
        if data['username'].lower() == username.lower():
            return uid, data
    return None, None

# --- Main Game Routes ---
@app.route('/')
def index():
    """Renders the main game page."""
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    """Handles new user registration."""
    data = request.get_json()
    username = data['username']
    password = data['password']
    
    players = load_data('players.json')
    
    # Check if username already exists
    if any(p['username'].lower() == username.lower() for p in players.values()):
        return jsonify({'success': False, 'message': 'Username already exists.'}), 409

    # Create new user
    uid = str(int(max(players.keys(), key=int)) + 1)
    new_user = {
        "username": username,
        "password": generate_password_hash(password),
        "clicks": 0,
        "money": 0.0,
        "rank": "1", # Start at Silver I (ID 1)
        "role": "player",
        "cases": {},
        "skins": [],
        "time_played": 0
    }
    players[uid] = new_user
    save_data('players.json', players)
    
    return jsonify({'success': True, 'message': 'Account created successfully!'})

@app.route('/login', methods=['POST'])
def login():
    """Handles user login."""
    data = request.get_json()
    username = data['username']
    password = data['password']
    
    uid, player_data = get_player_by_username(username)

    if player_data and check_password_hash(player_data['password'], password):
        session['uid'] = uid
        session['username'] = player_data['username']
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

@app.route('/logout')
def logout():
    """Logs the user out by clearing the session."""
    session.clear()
    return jsonify({'success': True})

@app.route('/get_game_data')
def get_game_data():
    """Provides all necessary data to start the game on the frontend."""
    if 'uid' not in session:
        return jsonify({'error': 'Not logged in'}), 401
        
    uid = session['uid']
    players = load_data('players.json')
    player_data = players.get(uid)

    if not player_data:
        session.clear()
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({
        'player_data': player_data,
        'ranks': load_data('ranks.json'),
        'cases': load_data('cases.json'),
        'skins': load_data('skins.json')
    })
    
# --- Gameplay API Routes ---
@app.route('/click', methods=['POST'])
def click():
    """Processes a player's click, updating stats and checking for rank-ups."""
    if 'uid' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    uid = session['uid']
    players = load_data('players.json')
    player = players[uid]
    ranks = load_data('ranks.json')
    
    current_rank_info = ranks[player['rank']]
    
    # Update stats
    player['clicks'] += 1
    player['money'] += current_rank_info['base_clicks']

    # Check for rank up
    next_rank_id = str(int(player['rank']) + 1)
    if next_rank_id in ranks and player['clicks'] >= ranks[next_rank_id]['clicks_needed']:
        player['rank'] = next_rank_id
    
    save_data('players.json', players)
    return jsonify({'money': player['money'], 'clicks': player['clicks'], 'rank': player['rank']})

@app.route('/buy_case', methods=['POST'])
def buy_case():
    """Handles a player buying a case from the shop."""
    if 'uid' not in session:
        return jsonify({'error': 'Not logged in'}), 401
        
    data = request.get_json()
    case_id = data['case_id']
    amount = int(data.get('amount', 1))

    uid = session['uid']
    players = load_data('players.json')
    player = players[uid]
    cases_data = load_data('cases.json')
    
    case_info = cases_data.get(case_id)
    if not case_info:
        return jsonify({'success': False, 'message': 'Case not found.'}), 404

    total_cost = case_info['price'] * amount
    if player['money'] < total_cost:
        return jsonify({'success': False, 'message': 'Not enough money.'}), 400

    # Process purchase
    player['money'] -= total_cost
    player['cases'][case_id] = player['cases'].get(case_id, 0) + amount
    
    save_data('players.json', players)
    return jsonify({'success': True, 'player_data': player})

@app.route('/open_case', methods=['POST'])
def open_case():
    """Handles opening a case and awarding a random skin."""
    if 'uid' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    case_id = request.get_json()['case_id']
    uid = session['uid']
    players = load_data('players.json')
    player = players[uid]

    if player['cases'].get(case_id, 0) < 1:
        return jsonify({'success': False, 'message': 'You do not own this case.'}), 400

    # Consume the case
    player['cases'][case_id] -= 1
    if player['cases'][case_id] == 0:
        del player['cases'][case_id]

    # Get a random skin from the case
    cases_data = load_data('cases.json')
    skins_data = load_data('skins.json')
    possible_skin_ids = cases_data[case_id]['skins']
    
    # Simple random choice - can be improved with weighted rarities
    won_skin_id = random.choice(possible_skin_ids)
    won_skin_info = skins_data[won_skin_id]

    # Add a unique instance of the skin to player inventory
    skin_instance = {
        "instance_id": f"skin_{int(time.time() * 1000)}_{random.randint(100, 999)}",
        "skin_id": won_skin_id,
        "name": won_skin_info['name'],
        "value": won_skin_info['value'],
        "rarity": won_skin_info['rarity']
    }
    player['skins'].append(skin_instance)
    
    save_data('players.json', players)
    return jsonify({'success': True, 'player_data': player, 'won_skin': skin_instance})

# --- Admin Routes ---
@app.route('/get_admin_data')
def get_admin_data():
    """Gets player data for the admin panel, excluding AI."""
    if 'uid' not in session or load_data('players.json')[session['uid']]['role'] not in ['admin', 'mod']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    players = load_data('players.json')
    # Filter out AI players
    human_players = {uid: data for uid, data in players.items() if data.get('role') != 'ai'}
    
    return jsonify(human_players)

@app.route('/update_player_role', methods=['POST'])
def update_player_role():
    if 'uid' not in session or load_data('players.json')[session['uid']]['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    target_uid = data['uid']
    new_role = data['role']

    players = load_data('players.json')
    if target_uid in players:
        players[target_uid]['role'] = new_role
        save_data('players.json', players)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Player not found.'}), 404

# --- Chat Functionality (SocketIO) ---
@socketio.on('connect')
def handle_connect():
    """Logs when a user connects to the chat."""
    if 'username' in session:
        print(f"User {session['username']} connected.")

@socketio.on('send_message')
def handle_send_message(data):
    """Broadcasts a message to all connected clients."""
    if 'username' in session:
        players = load_data('players.json')
        player_role = players.get(session['uid'], {}).get('role', 'player')
        
        msg_data = {
            'username': session['username'],
            'message': data['message'],
            'role': player_role
        }
        emit('receive_message', msg_data, broadcast=True)

# --- Main Execution ---
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
