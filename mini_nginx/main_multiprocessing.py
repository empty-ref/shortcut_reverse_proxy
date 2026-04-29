import logging
import multiprocessing as mp
import socket

from mini_nginx.config import ProxyConfig
from mini_nginx.main_threads import SelectorProxyServer


def _worker(config: ProxyConfig) -> None:
    socket.setdefaulttimeout(None)
    server = SelectorProxyServer(config)
    server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = ProxyConfig()
    workers = max(1, mp.cpu_count())

    processes: list[mp.Process] = []
    for _ in range(workers):
        p = mp.Process(target=_worker, args=(config,), daemon=False)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == '__main__':
    main()
