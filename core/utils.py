from base64 import b64encode
from socket import socket
import ssl
import json
from datetime import datetime
import requests

def parse_proxy_string(proxy_str):
    proxy_str = proxy_str.rpartition("://")[2]
    auth, _, fields = proxy_str.rpartition("@")
    fields = fields.split(":", 2)
    if len(fields) == 2:
        hostname, port = fields
        if auth:
            auth = "Basic " + b64encode(auth.encode()).decode()
    elif len(fields) == 3:
        hostname, port, auth = fields
        auth = "Basic " + b64encode(auth.encode()).decode()
    else:
        raise ValueError(f"Invalid proxy format: {proxy_str}")
    return auth, (hostname.lower(), int(port))

def parse_batch_response(data, limit):
    status = {}
    try:
        parsed = json.loads(data.decode('utf-8'))
        for g in parsed.get('data', []):
            gid = str(g.get('id', ''))
            status[gid] = g.get('owner') is not None
    except:
        data = data if isinstance(data, bytes) else data.encode()
        idx = 10
        for _ in range(limit):
            id_start = data.find(b'"id":', idx)
            if id_start == -1:
                break
            idx = data.find(b',', id_start + 5)
            gid = data[id_start+5:idx]
            idx = data.find(b'"owner":', idx) + 8
            status[gid] = (data[idx] == 123)
            idx += 25
    return status

def send_webhook(url, embed):
    payload = {"embeds": [embed]}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[webhook] Error: {e}")

def make_embed(group_info, timestamp):
    # Fetch group icon
    icon_url = None
    try:
        thumb_resp = requests.get(
            f"https://thumbnails.roblox.com/v1/groups/icons?groupIds={group_info['id']}&size=150x150&format=Png",
            timeout=5
        )
        if thumb_resp.status_code == 200:
            data = thumb_resp.json()
            if data.get('data') and len(data['data']) > 0:
                icon_url = data['data'][0].get('imageUrl')
    except:
        pass

    embed = {
        "title": f"🎯 Ownerless Group Found!",
        "url": f"https://www.roblox.com/groups/{group_info['id']}",
        "color": 0x00ff00,
        "thumbnail": {"url": icon_url} if icon_url else {},
        "fields": [
            {"name": "ID", "value": str(group_info['id']), "inline": True},
            {"name": "Name", "value": group_info['name'], "inline": True},
            {"name": "Members", "value": str(group_info['memberCount']), "inline": True},
            {"name": "Joinable", "value": "✅ Public" if group_info.get('publicEntryAllowed') else "❌ Locked", "inline": True},
            {"name": "Owner", "value": "None (unclaimed)", "inline": True},
        ],
        "footer": {"text": "github.com/yourusername/roblox-ownerless-finder"},
        "timestamp": timestamp.isoformat()
    }
    return embed

def make_http_socket(addr, timeout, proxy_addr=None, proxy_headers=None, hostname=None):
    sock = socket()
    sock.settimeout(timeout)
    if proxy_addr:
        sock.connect(proxy_addr)
        connect = f"CONNECT {addr[0]}:{addr[1]} HTTP/1.1\r\nHost: {addr[0]}\r\n"
        if proxy_headers and 'Proxy-Authorization' in proxy_headers:
            connect += f"Proxy-Authorization: {proxy_headers['Proxy-Authorization']}\r\n"
        connect += "\r\n"
        sock.send(connect.encode())
        resp = sock.recv(4096)
        if b"200" not in resp:
            raise RuntimeError("Proxy connection failed")
    else:
        sock.connect(addr)
    ctx = ssl.create_default_context()
    sock = ctx.wrap_socket(sock, server_hostname=hostname or addr[0])
    return sock

def shutdown_socket(sock):
    try:
        sock.shutdown(2)
    except:
        pass
    try:
        sock.close()
    except:
        pass
