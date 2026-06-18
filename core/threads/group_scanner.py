from ..utils import parse_batch_response, make_http_socket, shutdown_socket
from json import loads as json_loads
from zlib import decompress
from datetime import datetime, timezone
import socket
import time

GROUP_API = "groups.roblox.com"
GROUP_API_ADDR = (socket.gethostbyname(GROUP_API), 443)

def group_scanner(log_queue, count_queue, proxy_manager, timeout, gid_ranges, chunk_size=5):
    # Generate IDs on the fly (no huge list)
    def id_generator(ranges):
        for start, end in ranges:
            for gid in range(start, end):
                yield str(gid).encode()

    id_gen = id_generator(gid_ranges)
    tracked = set()

    while True:
        chunk = []
        try:
            for _ in range(chunk_size):
                chunk.append(next(id_gen))
        except StopIteration:
            break

        if not chunk:
            break

        # Get proxy
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
            time.sleep(0.5)
            continue

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
                shutdown_socket(sock)
                continue

            body = resp.split(b"\r\n\r\n", 1)[1]
            try:
                body = decompress(body, -15)
            except:
                pass

            owner_status = parse_batch_response(body, chunk_size)

            for gid in chunk:
                if gid not in owner_status:
                    continue
                if gid not in tracked:
                    if owner_status[gid]:
                        tracked.add(gid)
                    continue
                if owner_status[gid]:
                    continue

                # No owner – fetch details
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

                tracked.add(gid)

        except Exception:
            pass
        finally:
            shutdown_socket(sock)

        # Update scanned count
        count_queue.put(chunk_size)
        # Small delay to avoid CPU overload
        time.sleep(0.02)
