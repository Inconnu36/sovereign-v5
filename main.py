import os
import time
import json
import random
import psutil
import multiprocessing
import threading
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from playwright.sync_api import sync_playwright
from fake_useragent import UserAgent
from openai import OpenAI

# Initialize OpenAI client (requires OPENAI_API_KEY environment variable)
client = OpenAI()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sovereign_v5_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
ua = UserAgent()

# Global state
manager = multiprocessing.Manager()
swarm_status = manager.list()
task_queue = manager.Queue()

# --- Dashboard UI ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sovereign AI-Commander | Infrastructure Platform</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --primary: #00d4ff; --bg: #0a0b10; --card: #161b22; --text: #c9d1d9; --accent: #ff0055; }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; }
        .sidebar { width: 350px; background: var(--card); border-right: 1px solid #30363d; padding: 25px; display: flex; flex-direction: column; }
        .main { flex-grow: 1; padding: 25px; display: flex; flex-direction: column; overflow: hidden; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: #0d1117; border: 1px solid #30363d; padding: 15px; border-radius: 8px; text-align: center; }
        .stat-val { font-size: 1.5em; color: var(--primary); font-weight: bold; }
        .feed { flex-grow: 1; background: #000; border: 1px solid #30363d; border-radius: 8px; padding: 15px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85em; }
        .input-group { margin-bottom: 15px; }
        label { display: block; font-size: 0.8em; margin-bottom: 5px; color: #8b949e; }
        input, select, textarea, button { width: 100%; padding: 12px; background: #0d1117; border: 1px solid #30363d; color: #fff; border-radius: 6px; box-sizing: border-box; }
        textarea { height: 80px; resize: none; }
        button { background: var(--primary); color: #000; font-weight: bold; cursor: pointer; border: none; transition: 0.3s; margin-top: 10px; }
        button:hover { filter: brightness(1.2); }
        button.secondary { background: transparent; border: 1px solid var(--primary); color: var(--primary); }
        .log-entry { margin-bottom: 8px; border-left: 2px solid var(--primary); padding-left: 10px; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
        .ai-badge { background: var(--accent); color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.7em; font-weight: bold; margin-right: 5px; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2 style="color: var(--primary); margin-top: 0;">Sovereign V5</h2>
        <div class="input-group">
            <label>AI Global Command</label>
            <textarea id="ai_command" placeholder="e.g., 'Navigate to example.com and scroll down'"></textarea>
            <button onclick="sendAICommand()">Execute AI Command</button>
        </div>
        <hr style="border: 0.5px solid #30363d; margin: 20px 0;">
        <div class="input-group">
            <label>Manual Target URL</label>
            <input type="text" id="url" placeholder="https://example.com">
            <label>Swarm Magnitude</label>
            <input type="number" id="count" value="5">
            <button class="secondary" onclick="deploy()">Manual Swarm Initiation</button>
        </div>
        <div style="margin-top: auto;">
            <div id="resource_stats">
                <label>CPU: <span id="cpu_val">0%</span> | RAM: <span id="ram_val">0%</span></label>
            </div>
        </div>
    </div>
    <div class="main">
        <div class="stats-grid">
            <div class="stat-card"><div>Active Workers</div><div class="stat-val" id="active_count">0</div></div>
            <div class="stat-card"><div>Tasks in Queue</div><div class="stat-val" id="queue_count">0</div></div>
            <div class="stat-card"><div>Uptime</div><div class="stat-val" id="uptime">00:00</div></div>
        </div>
        <div id="feed" class="feed"></div>
    </div>
    <script>
        const socket = io();
        let startTime = Date.now();

        setInterval(() => {
            const diff = Math.floor((Date.now() - startTime) / 1000);
            const m = Math.floor(diff / 60).toString().padStart(2, '0');
            const s = (diff % 60).toString().padStart(2, '0');
            document.getElementById('uptime').innerText = `${m}:${s}`;
        }, 1000);

        socket.on('telemetry', (data) => {
            document.getElementById('cpu_val').innerText = data.cpu + '%';
            document.getElementById('ram_val').innerText = data.ram + '%';
            document.getElementById('active_count').innerText = data.active;
            document.getElementById('queue_count').innerText = data.queue;
        });

        socket.on('log', (data) => {
            const feed = document.getElementById('feed');
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `[${new Date().toLocaleTimeString()}] ${data.ai ? '<span class="ai-badge">AI</span>' : ''}${data.msg}`;
            feed.prepend(entry);
        });

        async function deploy() {
            const url = document.getElementById('url').value;
            const count = document.getElementById('count').value;
            await fetch('/deploy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ url, count })
            });
        }

        async function sendAICommand() {
            const command = document.getElementById('ai_command').value;
            if (!command) return;
            document.getElementById('ai_command').value = '';
            await fetch('/ai-command', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ command })
            });
        }
    </script>
</body>
</html>
"""

# --- AI Interpreter ---
def interpret_command(command):
    """Uses LLM to parse natural language into structured actions."""
    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[
                {"role": "system", "content": "You are an automation architect. Translate the user's command into a JSON list of actions. Supported actions: {'type': 'navigate', 'url': '...'}, {'type': 'scroll', 'direction': 'down/up'}, {'type': 'wait', 'seconds': 5}. Output ONLY the JSON list."},
                {"role": "user", "content": command}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content).get("actions", [])
    except Exception as e:
        print(f"AI Interpretation Error: {e}")
        return []

# --- Worker Engine ---
def audit_worker(worker_id, task_queue, swarm_status):
    """Persistent worker that executes tasks from the queue."""
    try:
        with sync_playwright() as p:
            # Use stealth-like args
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ])
            
            vault_path = f"vault/session_{worker_id}.json"
            context = browser.new_context(user_agent=ua.random)
            if os.path.exists(vault_path):
                with open(vault_path, 'r') as f:
                    try:
                        context.add_cookies(json.load(f))
                    except: pass
            
            page = context.newPage()
            socketio.emit('log', {'msg': f"Worker {worker_id}: Ready for tasks."})
            
            while True:
                task = task_queue.get() # Blocks until a task is available
                if task is None: break # Sentinel to stop worker
                
                actions = task.get('actions', [])
                socketio.emit('log', {'msg': f"Worker {worker_id}: Executing task with {len(actions)} actions."})
                
                try:
                    for action in actions:
                        if action['type'] == 'navigate':
                            page.goto(action['url'], wait_until="networkidle")
                        elif action['type'] == 'scroll':
                            dist = 500 if action.get('direction') == 'down' else -500
                            page.mouse.wheel(0, dist)
                        elif action['type'] == 'wait':
                            time.sleep(action.get('seconds', 2))
                    
                    socketio.emit('log', {'msg': f"Worker {worker_id}: Task complete."})
                except Exception as e:
                    socketio.emit('log', {'msg': f"Worker {worker_id}: Task failed: {str(e)}"})
                
                time.sleep(random.uniform(2, 5)) # Cooldown
                
            browser.close()
    except Exception as e:
        print(f"Worker {worker_id} Critical Error: {e}")

# --- Flask Routes ---
@app.route('/')
def index(): return render_template_string(DASHBOARD_HTML)

@app.route('/deploy', methods=['POST'])
def deploy():
    data = request.json
    url = data.get('url')
    count = int(data.get('count', 1))
    
    # Add a manual navigation task to the queue for each worker
    for _ in range(count):
        task_queue.put({'actions': [{'type': 'navigate', 'url': url}, {'type': 'scroll', 'direction': 'down'}]})
    
    return jsonify({"status": "tasks_queued"})

@app.route('/ai-command', methods=['POST'])
def ai_command():
    data = request.json
    command = data.get('command')
    
    # Interpret command in a separate thread to avoid blocking
    def process_ai():
        actions = interpret_command(command)
        if actions:
            socketio.emit('log', {'msg': f"AI interpreted command: {command}", 'ai': True})
            # Distribute task to all active workers (or just queue it)
            active_workers = len(multiprocessing.active_children()) - 1
            for _ in range(max(1, active_workers)):
                task_queue.put({'actions': actions})
        else:
            socketio.emit('log', {'msg': "AI failed to interpret command.", 'ai': True})

    threading.Thread(target=process_ai).start()
    return jsonify({"status": "ai_processing"})

def telemetry_broadcaster():
    while True:
        socketio.emit('telemetry', {
            'cpu': psutil.cpu_percent(),
            'ram': psutil.virtual_memory().percent,
            'active': len(multiprocessing.active_children()) - 1,
            'queue': task_queue.qsize()
        })
        time.sleep(2)

if __name__ == '__main__':
    # Start workers
    num_workers = 5 # Default swarm size
    for i in range(num_workers):
        p = multiprocessing.Process(target=audit_worker, args=(i+1, task_queue, swarm_status))
        p.daemon = True
        p.start()

    # Start telemetry
    threading.Thread(target=telemetry_broadcaster, daemon=True).start()
    
    socketio.run(app, host='0.0.0.0', port=3000)
