from ..utils import send_webhook, make_embed
import time

def log_processor(queue, webhook_url):
    while True:
        try:
            timestamp, group_info = queue.get(timeout=1)
            embed = make_embed(group_info, timestamp)
            send_webhook(webhook_url, embed)
            print(f"[{timestamp}] Sent webhook for: {group_info['name']} (ID: {group_info['id']})")
        except:
            time.sleep(0.1)
