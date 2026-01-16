import os
import time
import json
import random
import psutil
import multiprocessing
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from playwright.sync_api import sync_playwright
from fake_useragent import UserAgent

app = Flask(__name__)
app.config['SECRET_KEY'] = 'infra_audit_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
ua = UserAgent()

# Global state for the persistent swarm
manager = multiprocessing.Manager()
swarm_status = manager.list()

# --- Dashboard UI ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sovereign | Infrastructure Audit Platform</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        :root { --primary: #00d4ff; --bg: #0a0b10; --card: #161b22; --text: #c9d1d9; }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; }
        .sidebar { width: 320px; background: var(--card); border-right: 1px solid #30363d; padding: 25px; }
        .main { flex-grow: 1; padding: 25px; display: flex; flex-direction: column; overflow: hidden; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 6px; text-align: center; }
        .stat-val { font-size: 1.5em; color: var(--primary); font-weight: bold; }
        .feed { flex-grow: 1; background: #000; border: 1px solid #30363d; border-radius: 6px; padding: 15px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85em; }
        input, select, button { width: 100%; padding: 12px; margin-top: 10px; background: #0d1117; border: 1px solid #30363d; color: #fff; border-radius: 4px; }
        button { background: var(--primary); color: #000; font-weight: bold; cursor: pointer; border: none; transition: 0.2s; }
        button:hover { opacity: 0.8; }
        .log-entry { margin-bottom: 5px; border-left: 2px solid var(--primary); padding-left: 10px; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>Audit Control</h2>
        <label>Target Infrastructure URL</label>
        <input type="text" id="url" placeholder="https://api.internal.net">
        <label>Swarm Magnitude</label>
        <input type="number" id="count" value="5">
        <button onclick="deploy()">Initiate Swarm</button>
        <hr style="border: 0.5px solid #30363d; margin: 20px 0;">
        <div id="resource_stats">
            <label>CPU Usage: <span id="cpu_val">0%</span></label>
            <label>RAM Usage: <span id="ram_val">0%</span></label>
        </div>
    </div>
    <div class="main">
        <div class="stats-grid">
            <div class="stat-card"><div>Active Instances</div><div class="stat-val" id="active_count">0</div></div>
            <div class="stat-card"><div>Success Rate</div><div class="stat-val" id="success_rate">100%</div></div>
            <div class="stat-card"><div>Uptime</div><div class="stat-val" id="uptime">00:00</div></div>
        </div>
        <div id="feed" class="feed"></div>
    </div>
    <script>
        const socket = io();
        socket.on('telemetry', (data) => {
            document.getElementById('cpu_val').innerText = data.cpu + '%';
            document.getElementById('ram_val').innerText = data.ram + '%';
            document.getElementById('active_count').innerText = data.active;
        });
        socket.on('log', (data) => {
            const feed = document.getElementById('feed');
            feed.innerHTML = `<div class="log-entry">[${new Date().toLocaleTimeString()}] ${data.msg}</div>` + feed.innerHTML;
        });
        async function deploy() {
            await fetch('/deploy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    url: document.getElementById('url').value,
                    count: document.getElementById('count').value
                })
            });
        }
    </script>
</body>
</html>
"""

# --- Worker Engine ---
def audit_worker(worker_id, url, swarm_status):
    """Persistent worker simulating an authenticated human user."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            
            # Load session from vault if available
            vault_path = f"vault/session_{worker_id}.json"
            context = browser.new_context(user_agent=ua.random)
            if os.path.exists(vault_path):
                with open(vault_path, 'r') as f:
                    context.add_cookies(json.load(f))
            
            page = context.new_page()
            socketio.emit('log', {'msg': f"Worker {worker_id}: Initializing session..."})
            
            while True:
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    # Probabilistic Interaction Module
                    # 1. Randomized Scrolling
                    for _ in range(random.randint(3, 7)):
                        page.mouse.wheel(0, random.randint(300, 800))
                        time.sleep(random.uniform(1, 3))
                    
                    # 2. Non-linear Mouse Paths (Simulated)
                    page.mouse.move(random.randint(0, 1000), random.randint(0, 1000))
                    time.sleep(random.uniform(0.5, 2))
                    
                    socketio.emit('log', {'msg': f"Worker {worker_id}: Interaction cycle complete."})
                    time.sleep(random.randint(10, 30)) # Jitter between cycles
                except Exception as e:
                    socketio.emit('log', {'msg': f"Worker {worker_id}: Cycle failed, retrying..."})
                    time.sleep(5)
    except Exception as e:
        socketio.emit('log', {'msg': f"Worker {worker_id}: Critical failure."})

# --- Flask Routes ---
@app.route('/')
def index(): return render_template_string(DASHBOARD_HTML)

@app.route('/health-check')
def health(): return jsonify({"status": "healthy", "workers": len(multiprocessing.active_children())})

@app.route('/deploy', methods=['POST'])
def deploy():
    data = request.json
    count = int(data.get('count', 1))
    for i in range(count):
        p = multiprocessing.Process(target=audit_worker, args=(i+1, data['url'], swarm_status))
        p.daemon = True # Ensures workers stay active
        p.start()
    return jsonify({"status": "swarm_initiated"})

def telemetry_broadcaster():
    while True:
        socketio.emit('telemetry', {
            'cpu': psutil.cpu_percent(),
            'ram': psutil.virtual_memory().percent,
            'active': len(multiprocessing.active_children()) - 1 # Exclude broadcaster
        })
        time.sleep(2)

if __name__ == '__main__':
    # Start telemetry in a separate thread
    import threading
    threading.Thread(target=telemetry_broadcaster, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=3000)
  
