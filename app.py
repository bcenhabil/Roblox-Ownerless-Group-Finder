import json
import time
import threading
import sys
from flask import Flask, jsonify, render_template_string
from core.threads.group_scanner import group_scanner
from core.threads.log_processor import log_processor
from core.proxy_manager import ProxyManager
from core.constants import DEFAULT_RANGES
import os

app = Flask(__name__)

# Global stats
stats = {
    'scanned': 0,
    'found': 0,
    'recent': [],
    'status': 'Idle'
}

# Queues
log_queue = None
count_queue = None

def load_config():
    # Use environment variables if present, else fallback to config.json
    webhook_url = os.environ.get('WEBHOOK_URL', '')
    if not webhook_url:
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                webhook_url = config.get('webhook_url', '')
        except:
            pass
    return webhook_url

def start_scanner():
    global log_queue, count_queue, stats
    webhook_url = load_config()
    if not webhook_url:
        print("[ERROR] WEBHOOK_URL environment variable or config.json is required")
        return

    log_queue = threading.Queue()
    count_queue = threading.Queue()

    # Start log processor (webhook sender) – just prints to console for now, but also keeps queue
    def log_worker():
        while True:
            try:
                timestamp, group_info = log_queue.get(timeout=1)
                # Send to Discord via webhook
                from core.utils import make_embed, send_webhook
                embed = make_embed(group_info, timestamp)
                send_webhook(webhook_url, embed)
                # Update stats
                stats['found'] += 1
                stats['recent'].insert(0, {
                    'id': group_info['id'],
                    'name': group_info['name'],
                    'members': group_info['memberCount'],
                    'time': timestamp.isoformat()
                })
                if len(stats['recent']) > 50:
                    stats['recent'] = stats['recent'][:50]
            except:
                time.sleep(0.1)

    threading.Thread(target=log_worker, daemon=True).start()

    # Proxy manager (auto-fetch proxies)
    proxy_manager = ProxyManager()

    # Scanner (single-threaded, but uses its own internal threads)
    def scanner_worker():
        ranges = DEFAULT_RANGES  # or from config
        stats['status'] = 'Scanning'
        try:
            # We'll run the scanner in a loop; group_scanner will loop through all IDs
            # We need a version that runs indefinitely and updates stats
            # We'll use a modified scanner that updates count_queue
            from core.threads.group_scanner import group_scanner
            group_scanner(log_queue, count_queue, proxy_manager, 10, ranges, 5)  # chunk size 5 to reduce memory
        except Exception as e:
            print(f"Scanner error: {e}")
        finally:
            stats['status'] = 'Stopped'

    threading.Thread(target=scanner_worker, daemon=True).start()

    # Update stats from count_queue
    def stats_updater():
        while True:
            try:
                cnt = count_queue.get_nowait()
                stats['scanned'] += cnt
            except:
                pass
            time.sleep(0.5)

    threading.Thread(target=stats_updater, daemon=True).start()

# Dashboard route
@app.route('/')
def dashboard():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Roblox Ownerless Group Finder</title>
            <meta charset="UTF-8">
            <meta http-equiv="refresh" content="15">
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #fff; padding: 30px; }
                h1 { color: #ffd54f; }
                .card { background: #16213e; border-radius: 10px; padding: 20px; margin: 10px 0; }
                .stat { display: inline-block; margin-right: 40px; }
                .stat-label { color: #aaa; font-size: 0.9em; }
                .stat-value { font-size: 2em; font-weight: bold; }
                .green { color: #4caf50; }
                .blue { color: #42a5f5; }
                .orange { color: #ffa726; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
                th { background: #0f3460; }
                .badge { background: #2e7d32; padding: 2px 10px; border-radius: 12px; font-size: 0.8em; }
            </style>
        </head>
        <body>
            <h1>🔍 Roblox Ownerless Group Finder</h1>
            <div class="card">
                <div class="stat"><span class="stat-label">Status</span><br><span class="stat-value blue">{{ stats.status }}</span></div>
                <div class="stat"><span class="stat-label">Scanned</span><br><span class="stat-value orange">{{ stats.scanned }}</span></div>
                <div class="stat"><span class="stat-label">Found</span><br><span class="stat-value green">{{ stats.found }}</span></div>
            </div>

            <h2>📋 Recent Found Groups</h2>
            <table>
                <tr><th>Time</th><th>ID</th><th>Name</th><th>Members</th></tr>
                {% for g in stats.recent %}
                <tr>
                    <td>{{ g.time[:19] }}</td>
                    <td><a href="https://www.roblox.com/groups/{{ g.id }}" target="_blank">{{ g.id }}</a></td>
                    <td>{{ g.name }}</td>
                    <td>{{ g.members }}</td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
    ''', stats=stats)

@app.route('/stats')
def stats_json():
    return jsonify(stats)

if __name__ == '__main__':
    # Start scanner in background
    start_scanner()
    # Run Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
