import logging
import multiprocessing as mp
import socket

from mini_nginx.config import ProxyConfig
from mini_nginx.main_threads import SelectorProxyServer


def _worker(config: ProxyConfig) -> None:
    # Allow multiple workers to bind the same listen address.
    socket.setdefaulttimeout(None)
    server = SelectorProxyServer(config)
    server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = ProxyConfig.from_yaml('config.yml')
    workers = max(1, mp.cpu_count())

    # For REUSEPORT mode, every worker creates its own listening socket.
    # macOS supports SO_REUSEPORT for this pattern.
    processes: list[mp.Process] = []
    for _ in range(workers):
        p = mp.Process(target=_worker, args=(config,), daemon=False)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == '__main__':
    main()
