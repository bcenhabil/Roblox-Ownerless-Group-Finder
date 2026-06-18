from ..utils import parse_batch_response, make_http_socket, shutdown_socket
from json import loads as json_loads
from zlib import decompress
from datetime import datetime, timezone
from time import time
import socket

GROUP_API = "groups.roblox.com"
GROUP_API_ADDR = (socket.gethostbyname(GROUP_API), 443)

def group_scanner(log_queue, count_queue, proxy_manager, timeout, gid_ranges, chunk_size):
    gid_list = [str(gid).encode() for r in gid_ranges for gid in range(r[0], r[1])]
    gid_list_len = len(gid_list)
    idx = 0
    tracked = set()

    while gid_list_len >= chunk_size:
        if proxy_manager:
            proxy_auth, proxy_addr = proxy_manager.get_proxy()
        else:
            proxy_auth, proxy_addr = None, None

        try:
            sock = make_http_socket(
                GROUP_API_ADDR, timeout, proxy_addr,
                {"Proxy-Authorization": proxy_auth} if proxy_auth else {},
                hostname=GROUP_API
            )
        except Exception:
            continue

        while True:
            chunk = [gid_list[(idx + n) % gid_list_len] for n in range(chunk_size)]
            idx += chunk_size

            try:
                sock.send(
                    b"GET /v2/groups?groupIds=" + b",".join(chunk) + b" HTTP/1.1\r\n"
                    b"Host: groups.roblox.com\r\n"
                    b"Accept-Encoding: deflate\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                resp = sock.recv(1048576)
                if not resp.startswith(b"HTTP/1.1 200"):
                    break

                body = resp.split(b"\r\n\r\n", 1)[1]
                try:
                    body = decompress(body, -15)
                except:
                    pass

                owner_status = parse_batch_response(body, chunk_size)

                for gid in chunk:
                    if gid not in owner_status:
                        gid_list.remove(gid)
                        gid_list_len -= 1
                        continue

                    if gid not in tracked:
                        if owner_status[gid]:
                            tracked.add(gid)
                        else:
                            gid_list.remove(gid)
                            gid_list_len -= 1
                        continue

                    if owner_status[gid]:
                        continue

                    # Group has no owner – get full details
                    sock.send(
                        b"GET /v1/groups/" + gid + b" HTTP/1.1\r\n"
                        b"Host: groups.roblox.com\r\n"
                        b"Connection: close\r\n"
                        b"\r\n"
                    )
                    resp = sock.recv(1048576)
                    if not resp.startswith(b"HTTP/1.1 200"):
                        break
                    body = resp.split(b"\r\n\r\n", 1)[1]
                    try:
                        body = decompress(body, -15)
                    except:
                        pass
                    try:
                        info = json_loads(body)
                    except:
                        break

                    # Check claimable: publicEntryAllowed, no owner, not locked
                    if (info.get("publicEntryAllowed") is True and
                        info.get("owner") is None and
                        not info.get("isLocked", False)):
                        group_data = {
                            "id": int(gid),
                            "name": info.get("name", "Unknown"),
                            "memberCount": info.get("memberCount", 0),
                            "publicEntryAllowed": info.get("publicEntryAllowed", False)
                        }
                        log_queue.put((datetime.now(timezone.utc), group_data))

                    gid_list.remove(gid)
                    gid_list_len -= 1
                    count_queue.put((time(), 1))

            except Exception:
                break

        shutdown_socket(sock)
