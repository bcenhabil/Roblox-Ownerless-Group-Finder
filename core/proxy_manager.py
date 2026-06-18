import threading
import time
import requests
from .constants import PROXY_SOURCES, PROXY_REFRESH_INTERVAL
from .utils import parse_proxy_string

class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.lock = threading.Lock()
        self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
        self._fetch_proxies()

    def _fetch_proxies(self):
        new_proxies = []
        for url in PROXY_SOURCES:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '://' not in line:
                                line = 'http://' + line
                            try:
                                auth, addr = parse_proxy_string(line)
                                new_proxies.append((auth, addr))
                            except:
                                pass
                print(f"[ProxyManager] Fetched {len(new_proxies)} proxies from {url}")
            except Exception as e:
                print(f"[ProxyManager] Failed to fetch {url}: {e}")
        if new_proxies:
            with self.lock:
                self.proxies = new_proxies
            print(f"[ProxyManager] Total active proxies: {len(self.proxies)}")
        else:
            print("[ProxyManager] No proxies fetched.")

    def _refresh_loop(self):
        while True:
            time.sleep(PROXY_REFRESH_INTERVAL)
            self._fetch_proxies()

    def get_proxy(self):
        with self.lock:
            if not self.proxies:
                return None, None
            proxy = self.proxies.pop(0)
            self.proxies.append(proxy)
            return proxy
