from flask import Flask, request, jsonify, send_from_directory
import os, json, time, random, hashlib
from pathlib import Path

app = Flask(__name__, static_folder='.', static_url_path='')

BASE_DIR = Path(__file__).parent

def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

# load json files
def load_json(name):
    p = BASE_DIR / name
    if not p.exists():
        return {}
    with open(p,'r',encoding='utf-8') as f:
        return json.load(f)

def save_json(name, data):
    p = BASE_DIR / name
    with open(p,'w',encoding='utf-8') as f:
        json.dump(data, f, indent=4)

PLAYERS_FILE = 'players.json'
RANKS_FILE = 'ranks.json'
CASES_FILE = 'cases.json'
SKINS_FILE = 'skins.json'
RARITIES_FILE = 'rarities.json'
SKINSETS_FILE = 'skin_sets.json'

players = load_json(PLAYERS_FILE)
ranks = load_json(RANKS_FILE)
cases = load_json(CASES_FILE)
skins = load_json(SKINS_FILE)
rarities = load_json(RARITIES_FILE)
skin_sets = load_json(SKINSETS_FILE)

# Migration: ensure inventory and sort_order and ranks default
for username, pdata in list(players.items()):
    pdata.setdefault('inventory', {'cases': {}, 'skins': [], 'favorites': []})
    pdata.setdefault('sort_order', 'price_desc')
    role = pdata.get('role','player')
    if role in ('admin','mod'):
        pdata['rank'] = pdata.get('rank', 50)
    else:
        r = pdata.get('rank', 1)
        if r == 0:
            pdata['rank'] = 1
        else:
            pdata['rank'] = r if isinstance(r,int) and r>=1 else 1
# Save migration
save_json(PLAYERS_FILE, players)

online_users = {}  # username -> {'login_time':..., 'last_action':...}

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username','').strip()
    password = data.get('password','').strip()
    if not username or not password:
        return jsonify({'success':False,'message':'Missing'}),400
    if username not in players:
        return jsonify({'success':False,'message':'User not found'}),404
    if players[username].get('password_hash') != md5_hash(password):
        return jsonify({'success':False,'message':'Incorrect password'}),401
    online_users[username] = {'login_time': time.time(), 'last_action': time.time()}
    return jsonify({'success':True,'username':username,'role':players[username].get('role','player')})

@app.route('/click', methods=['POST'])
def click():
    data = request.get_json() or {}
    username = data.get('username')
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    p = players[username]
    rank_idx = p.get('rank',1)
    base_clicks = 1
    try:
        base_clicks = int(ranks.get(str(rank_idx), {}).get('base_clicks', 1))
    except:
        base_clicks = 1
    p['clicks'] = p.get('clicks',0) + base_clicks
    p['money'] = p.get('money',0) + max(1, int(base_clicks*0.1))
    online_users.setdefault(username, {})['last_action'] = time.time()
    save_json(PLAYERS_FILE, players)
    return jsonify({'success':True,'clicks':p['clicks'],'money':p['money']})

@app.route('/buy_case', methods=['POST'])
def buy_case():
    data = request.get_json() or {}
    username = data.get('username')
    case_name = data.get('case_name')
    qty = int(data.get('qty',1))
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    if case_name not in cases:
        return jsonify({'success':False,'message':'Invalid case'}),400
    p = players[username]
    price = int(cases[case_name].get('price',0)) * qty
    if p.get('money',0) < price:
        return jsonify({'success':False,'message':'Not enough money'}),402
    p['money'] -= price
    inv = p.setdefault('inventory', {'cases':{},'skins':[],'favorites':[]})
    inv['cases'][case_name] = inv['cases'].get(case_name,0) + qty
    online_users.setdefault(username,{})['last_action'] = time.time()
    save_json(PLAYERS_FILE, players)
    return jsonify({'success':True,'money':p['money'],'cases':inv['cases']})

@app.route('/get_cases', methods=['GET'])
def get_cases():
    username = request.args.get('username')
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    inv = players[username].get('inventory',{})
    return jsonify({'success':True,'cases':inv.get('cases',{})})

def pick_skin_from_case(case_name):
    case = cases.get(case_name)
    if not case:
        return None
    case_skins = case.get('skins',[])
    weights = []
    for s in case_skins:
        rname = skins.get(s)
        prob = rarities.get(rname, {}).get('probability', 0.01)
        weights.append(prob)
    total = sum(weights)
    if total <= 0:
        return random.choice(case_skins) if case_skins else None
    r = random.random()*total
    cum = 0
    for s,w in zip(case_skins,weights):
        cum += w
        if r <= cum:
            return s
    return case_skins[-1] if case_skins else None

@app.route('/open_case', methods=['POST'])
def open_case():
    data = request.get_json() or {}
    username = data.get('username')
    case_name = data.get('case_name')
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    inv = players[username].setdefault('inventory', {'cases':{},'skins':[],'favorites':[]})
    if inv['cases'].get(case_name,0) <= 0:
        return jsonify({'success':False,'message':'No such case in inventory'}),400
    skin = pick_skin_from_case(case_name)
    if not skin:
        return jsonify({'success':False,'message':'No skin available'}),500
    inv['cases'][case_name] -= 1
    if inv['cases'][case_name] <= 0:
        del inv['cases'][case_name]
    inv['skins'].append(skin)
    online_users.setdefault(username,{})['last_action'] = time.time()
    save_json(PLAYERS_FILE, players)
    return jsonify({'success':True,'skin':skin,'skins':inv['skins']})

@app.route('/get_skins', methods=['GET'])
def get_skins():
    username = request.args.get('username')
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    p = players[username]
    inv = p.get('inventory',{})
    skins_list = list(inv.get('skins',[]))
    sort_order = p.get('sort_order','price_desc')
    def skin_value(s):
        r = skins.get(s)
        vr = rarities.get(r, {}).get('value_range',[0,0])
        try:
            return (vr[0]+vr[1])/2
        except:
            return 0
    if sort_order == 'price_desc':
        skins_list.sort(key=lambda s: skin_value(s), reverse=True)
    elif sort_order == 'price_asc':
        skins_list.sort(key=lambda s: skin_value(s))
    elif sort_order == 'rarity':
        def rarity_sort(s):
            r = skins.get(s)
            return rarities.get(r, {}).get('sort_value', 0)
        skins_list.sort(key=rarity_sort, reverse=True)
    elif sort_order == 'az':
        skins_list.sort(key=lambda s: s.lower())
    elif sort_order == 'za':
        skins_list.sort(key=lambda s: s.lower(), reverse=True)
    return jsonify({'success':True,'skins':skins_list,'favorites':inv.get('favorites',[]),'sort_order':sort_order})

@app.route('/set_sort_order', methods=['POST'])
def set_sort_order():
    data = request.get_json() or {}
    username = data.get('username')
    order = data.get('order')
    if not username or username not in players:
        return jsonify({'success':False,'message':'Invalid user'}),400
    players[username]['sort_order'] = order
    save_json(PLAYERS_FILE, players)
    return jsonify({'success':True,'sort_order':order})

@app.route('/favorite_skin', methods=['POST'])
def favorite_skin():
    data = request.get_json() or {}
    username = data.get('username'); skin = data.get('skin')
    if not username or username not in players or not skin:
        return jsonify({'success':False,'message':'Invalid'}),400
    inv = players[username].setdefault('inventory', {'cases':{},'skins':[],'favorites':[]})
    if skin in inv.get('skins',[]):
        inv['skins'].remove(skin)
        inv['favorites'].append(skin)
        save_json(PLAYERS_FILE, players)
        return jsonify({'success':True})
    return jsonify({'success':False,'message':'Skin not owned'}),400

@app.route('/unfavorite_skin', methods=['POST'])
def unfavorite_skin():
    data = request.get_json() or {}
    username = data.get('username'); skin = data.get('skin')
    if not username or username not in players or not skin:
        return jsonify({'success':False,'message':'Invalid'}),400
    inv = players[username].setdefault('inventory', {'cases':{},'skins':[],'favorites':[]})
    if skin in inv.get('favorites',[]):
        inv['favorites'].remove(skin)
        inv['skins'].append(skin)
        save_json(PLAYERS_FILE, players)
        return jsonify({'success':True})
    return jsonify({'success':False,'message':'Skin not in favorites'}),400

@app.route('/all_players', methods=['GET'])
def all_players():
    out = []
    for u,p in players.items():
        out.append({'username':u,'role':p.get('role','player'),'money':p.get('money',0),'clicks':p.get('clicks',0)})
    return jsonify({'success':True,'players':out})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
