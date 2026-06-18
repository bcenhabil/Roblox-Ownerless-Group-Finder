import json
import argparse
import multiprocessing as mp
import time
import sys
from core.threads.group_scanner import group_scanner
from core.threads.log_processor import log_processor
from core.proxy_manager import ProxyManager
from core.constants import DEFAULT_RANGES

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def worker(log_queue, count_queue, use_proxy, timeout, ranges, threads):
    """Wrapper that creates a ProxyManager inside each process."""
    proxy_manager = ProxyManager() if use_proxy else None
    group_scanner(log_queue, count_queue, proxy_manager, timeout, ranges, threads)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, help='Number of processes')
    parser.add_argument('--threads', type=int, help='Threads per process')
    parser.add_argument('--webhook-url', type=str, help='Discord webhook URL')
    parser.add_argument('--no-proxy', action='store_true', help='Disable proxy usage')
    args = parser.parse_args()

    config = load_config()

    webhook_url = args.webhook_url or config.get('webhook_url')
    if not webhook_url:
        print("[ERROR] webhook_url is required in config.json or via --webhook-url")
        sys.exit(1)

    workers = args.workers or config.get('workers', 4)
    threads = args.threads or config.get('threads', 50)
    ranges = config.get('scan_ranges', DEFAULT_RANGES)
    use_proxy = not args.no_proxy

    log_queue = mp.Queue()
    count_queue = mp.Queue()

    # Start log processor (webhook sender)
    log_proc = mp.Process(target=log_processor, args=(log_queue, webhook_url))
    log_proc.daemon = True
    log_proc.start()

    # Start scanner processes
    procs = []
    for _ in range(workers):
        p = mp.Process(
            target=worker,
            args=(log_queue, count_queue, use_proxy, 10, ranges, threads)
        )
        p.daemon = True
        p.start()
        procs.append(p)

    try:
        while True:
            time.sleep(5)
            scanned = 0
            while not count_queue.empty():
                scanned += count_queue.get()[1]
            if scanned:
                print(f"[STATS] Scanned {scanned} groups in last 5s")
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)

if __name__ == '__main__':
    mp.set_start_method('spawn', force=True)
    main()
