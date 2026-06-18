import json
import time
import threading
import os
from flask import Flask, jsonify, render_template_string
from core.threads.group_scanner import group_scanner
from core.proxy_manager import ProxyManager
from core.constants import DEFAULT_RANGES
from core.utils import make_embed, send_webhook

app = Flask(__name__)

# Your webhook URL is set here directly
DEFAULT_WEBHOOK = "https://discord.com/api/webhooks/1367791217651220500/eWvP-ncpHXpEaB8smp-MvNakQGB1TjAXLQOmuWyZLL_7hE9NCEaby5v2lpHKkWIlrZ5j"

stats = {
    'scanned': 0,
    'found': 0,
    'recent': [],
    'status': 'Idle'
}

log_queue = None
count_queue = None

def load_webhook():
    # Use environment variable if set, else fallback to the default
    webhook = os.environ.get('WEBHOOK_URL')
    if webhook:
        return webhook
    return DEFAULT_WEBHOOK

def start_scanner():
    global log_queue, count_queue, stats
    webhook_url = load_webhook()
    if not webhook_url:
        print("[ERROR] No webhook URL available")
        stats['status'] = 'Error: No webhook'
        return

    print(f"[INFO] Using webhook: {webhook_url[:50]}...")
    log_queue = threading.Queue()
    count_queue = threading.Queue()

    # Log processor
    def log_worker():
        while True:
            try:
                timestamp, group_info = log_queue.get(timeout=1)
                embed = make_embed(group_info, timestamp)
                send_webhook(webhook_url, embed)
                stats['found'] += 1
                stats['recent'].insert(0, {
                    'id': group_info['id'],
                    'name': group_info['name'],
                    'members': group_info['memberCount'],
                    'time': timestamp.isoformat()
                })
                if len(stats['recent']) > 50:
                    stats['recent'] = stats['recent'][:50]
                print(f"[FOUND] {group_info['name']} (ID: {group_info['id']})")
            except:
                time.sleep(0.1)

    threading.Thread(target=log_worker, daemon=True).start()

    # Proxy manager
    try:
        proxy_manager = ProxyManager()
        print("[INFO] ProxyManager started")
    except Exception as e:
        print(f"[ERROR] ProxyManager: {e}")
        proxy_manager = None

    # Scanner
    def scanner_worker():
        try:
            stats['status'] = 'Starting...'
            print("[INFO] Scanner thread started")
            ranges = DEFAULT_RANGES
            print(f"[INFO] Scanning ranges: {ranges}")
            stats['status'] = 'Scanning'
            group_scanner(log_queue, count_queue, proxy_manager, 10, ranges, 10)
            stats['status'] = 'Stopped'
        except Exception as e:
            print(f"[ERROR] Scanner crashed: {e}")
            import traceback
            traceback.print_exc()
            stats['status'] = f'Error: {str(e)[:50]}'

    threading.Thread(target=scanner_worker, daemon=True).start()

    # Stats updater
    def stats_updater():
        while True:
            try:
                cnt = count_queue.get_nowait()
                stats['scanned'] += cnt
                if stats['scanned'] % 100 == 0:
                    print(f"[STATS] Scanned {stats['scanned']} groups so far")
            except:
                pass
            time.sleep(0.5)

    threading.Thread(target=stats_updater, daemon=True).start()

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
                .red { color: #ef5350; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
                th { background: #0f3460; }
            </style>
        </head>
        <body>
            <h1>🔍 Roblox Ownerless Group Finder</h1>
            <div class="card">
                <div class="stat"><span class="stat-label">Status</span><br><span class="stat-value {% if stats.status == 'Scanning' %}green{% elif stats.status == 'Error' %}red{% else %}blue{% endif %}">{{ stats.status }}</span></div>
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

@app.route('/health')
def health():
    return "OK", 200

if __name__ == '__main__':
    start_scanner()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
