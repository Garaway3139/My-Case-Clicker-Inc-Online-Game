from flask import Flask, request, jsonify, send_from_directory
import json, time, random, hashlib
from pathlib import Path

app = Flask(__name__, static_folder='.', static_url_path='')

BASE_DIR = Path(__file__).parent

def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def load_json(name):
    p = BASE_DIR / name
    if not p.exists(): return {}
    with open(p,'r',encoding='utf-8') as f: return json.load(f)
def save_json(name,data):
    p = BASE_DIR / name
    with open(p,'w',encoding='utf-8') as f: json.dump(data,f,indent=4)

PLAYERS = load_json('players.json')
CASES = load_json('cases.json')
SKINS = load_json('skins.json')
RARITIES = load_json('rarities.json')
RANKS = load_json('ranks.json')
SKINSETS = load_json('skin_sets.json')

# Ensure default inventory and ranks
for uname,p in PLAYERS.items():
    p.setdefault('inventory', {'cases':{}, 'skins':[], 'favorites':[]})
    p.setdefault('sort_order', 'price_desc')
    role = p.get('role','player')
    if role in ('admin','mod'):
        p['rank'] = 50
    else:
        p['rank'] = max(1, int(p.get('rank', 1)))
save_json('players.json', PLAYERS)

online_users = {}

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or request.form
    username = data.get('username','').strip()
    password = data.get('password','').strip()
    if not username or not password:
        return jsonify({'success':False,'message':'Missing credentials'}),400
    if username not in PLAYERS:
        return jsonify({'success':False,'message':'User not found'}),404
    if PLAYERS[username].get('password_hash') != md5_hash(password):
        return jsonify({'success':False,'message':'Incorrect password'}),401
    online_users[username] = {'login_time': time.time(), 'last_action': time.time()}
    return jsonify({'success':True,'username':username,'role':PLAYERS[username].get('role','player')})

@app.route('/click', methods=['POST'])
def click():
    data = request.get_json() or {}
    username = data.get('username')
    if not username or username not in PLAYERS:
        return jsonify({'success':False,'message':'Invalid user'}),400
    p = PLAYERS[username]
    base_clicks = int(RANKS.get(str(p.get('rank',1)), {}).get('base_clicks',1))
    p['clicks'] = p.get('clicks',0) + base_clicks
    p['money'] = p.get('money',0) + max(1, int(base_clicks*0.1))
    online_users.setdefault(username, {})['last_action'] = time.time()
    save_json('players.json', PLAYERS)
    return jsonify({'success':True,'clicks':p['clicks'],'money':p['money']})

@app.route('/buy_case', methods=['POST'])
def buy_case():
    data = request.get_json() or {}
    username = data.get('username'); case_name = data.get('case_name'); qty = int(data.get('qty',1))
    if not username or username not in PLAYERS:
        return jsonify({'success':False,'message':'Invalid user'}),400
    if case_name not in CASES:
        return jsonify({'success':False,'message':'Invalid case'}),400
    p = PLAYERS[username]
    price = int(CASES[case_name].get('price',0)) * qty
    if p.get('money',0) < price:
        return jsonify({'success':False,'message':'Not enough money'}),402
    p['money'] -= price
    inv = p['inventory']
    inv['cases'][case_name] = inv['cases'].get(case_name,0) + qty
    save_json('players.json', PLAYERS)
    return jsonify({'success':True,'money':p['money'],'cases':inv['cases']})

@app.route('/open_case', methods=['POST'])
def open_case():
    data = request.get_json() or {}
    username = data.get('username'); case_name = data.get('case_name')
    if not username or username not in PLAYERS:
        return jsonify({'success':False,'message':'Invalid user'}),400
    inv = PLAYERS[username]['inventory']
    if inv['cases'].get(case_name,0) <= 0:
        return jsonify({'success':False,'message':'No such case'}),400
    skin = random.choice(CASES[case_name]['skins'])
    inv['cases'][case_name] -= 1
    if inv['cases'][case_name] <= 0:
        del inv['cases'][case_name]
    inv['skins'].append(skin)
    save_json('players.json', PLAYERS)
    return jsonify({'success':True,'skin':skin,'skins':inv['skins']})

@app.route('/get_skins', methods=['GET'])
def get_skins():
    username = request.args.get('username')
    if not username or username not in PLAYERS:
        return jsonify({'success':False,'message':'Invalid user'}),400
    p = PLAYERS[username]; inv = p['inventory']
    return jsonify({'success':True,'skins':inv['skins'],'favorites':inv['favorites'],'sort_order':p.get('sort_order','price_desc')})

@app.route('/set_sort_order', methods=['POST'])
def set_sort_order():
    data = request.get_json() or {}
    username = data.get('username'); order = data.get('order')
    if not username or username not in PLAYERS:
        return jsonify({'success':False,'message':'Invalid user'}),400
    PLAYERS[username]['sort_order'] = order
    save_json('players.json', PLAYERS)
    return jsonify({'success':True,'sort_order':order})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
