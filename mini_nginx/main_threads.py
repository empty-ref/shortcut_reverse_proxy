import logging
import selectors
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import LifoQueue

from mini_nginx.config import ProxyConfig
from mini_nginx.constants import DEFAULT_503_RESPONSE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UpstreamTarget:
    host: str
    port: int


class ThreadSafeRoundRobin:
    def __init__(self, targets: list[UpstreamTarget]) -> None:
        if not targets:
            raise ValueError('at least one upstream required')
        self._targets = targets
        self._idx = 0
        self._lock = threading.Lock()

    def next(self) -> UpstreamTarget:
        with self._lock:
            t = self._targets[self._idx]
            self._idx = (self._idx + 1) % len(self._targets)
            return t


class ThreadedUpstreamPool:
    def __init__(self, targets: list[UpstreamTarget], max_per_upstream: int) -> None:
        self._targets = targets
        self._queues = {target: LifoQueue(maxsize=max_per_upstream) for target in targets}
        self._max_per_upstream = max_per_upstream

    def acquire(self, target: UpstreamTarget, connect_timeout: float) -> socket.socket:
        queue = self._queues[target]
        while not queue.empty():
            sock = queue.get_nowait()
            if sock.fileno() != -1:
                sock.setblocking(False)
                return sock
            self._safe_close(sock)

        upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_sock.settimeout(connect_timeout)
        upstream_sock.connect((target.host, target.port))
        upstream_sock.settimeout(None)
        upstream_sock.setblocking(False)
        return upstream_sock

    def release(self, target: UpstreamTarget, sock: socket.socket, reusable: bool) -> None:
        if reusable and sock.fileno() != -1:
            try:
                self._queues[target].put_nowait(sock)
                return
            except Exception:
                pass
        self._safe_close(sock)

    @staticmethod
    def _safe_close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass


class SelectorProxyServer:
    def __init__(self, config: ProxyConfig) -> None:
        self.config = config
        self.targets = [UpstreamTarget(host=h, port=p) for h, p in config.upstreams]
        self.rr = ThreadSafeRoundRobin(self.targets)
        self.pool = ThreadedUpstreamPool(self.targets, config.max_conns_per_upstream)
        self.client_limiter = threading.BoundedSemaphore(config.max_client_conns)
        self.client_proxy_semaphore = threading.BoundedSemaphore(config.max_client_conns)
        self.executor = ThreadPoolExecutor(max_workers=config.max_client_conns)

    def serve_forever(self) -> None:
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        listen_sock.bind((self.config.listen_host, self.config.listen_port))
        listen_sock.listen()
        listen_sock.setblocking(False)

        selector = selectors.DefaultSelector()
        selector.register(listen_sock, selectors.EVENT_READ, data=None)
        logger.info('threaded proxy listening on %s:%s', self.config.listen_host, self.config.listen_port)

        try:
            while True:
                for key, _ in selector.select(timeout=1.0):
                    if key.data is None:
                        client_sock, client_addr = listen_sock.accept()
                        client_sock.setblocking(False)
                        self.executor.submit(self._handle_client, client_sock, client_addr)
        finally:
            selector.close()
            listen_sock.close()
            self.executor.shutdown(wait=True)

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple[str, int]) -> None:
        if not self.client_limiter.acquire(blocking=False):
            self._send_503_and_close(client_sock)
            return

        try:
            with self.client_proxy_semaphore:
                deadline = time.time() + self.config.total_timeout
                self._proxy_session(client_sock, client_addr, deadline)
        finally:
            self.client_limiter.release()

    def _proxy_session(self, client_sock: socket.socket, client_addr: tuple[str, int], deadline: float) -> None:
        target = self.rr.next()
        upstream_sock = None
        try:
            upstream_sock = self.pool.acquire(target, self.config.connect_timeout)
            self._bridge_bidirectional(client_sock, upstream_sock, deadline)
            self.pool.release(target, upstream_sock, reusable=True)
            upstream_sock = None
        except Exception as exc:
            logger.debug('client=%s upstream=%s:%s failed: %r', client_addr, target.host, target.port, exc)
            if upstream_sock is not None:
                self.pool.release(target, upstream_sock, reusable=False)
        finally:
            self._safe_close(client_sock)

    def _bridge_bidirectional(self, client_sock: socket.socket, upstream_sock: socket.socket, deadline: float) -> None:
        selector = selectors.DefaultSelector()
        selector.register(client_sock, selectors.EVENT_READ, data=upstream_sock)
        selector.register(upstream_sock, selectors.EVENT_READ, data=client_sock)
        sockets = (client_sock, upstream_sock)

        try:
            while True:
                if time.time() > deadline:
                    raise TimeoutError('session timeout')
                events = selector.select(timeout=0.1)
                if not events:
                    continue

                for key, _ in events:
                    src_sock = key.fileobj
                    dst_sock = key.data
                    data = src_sock.recv(64 * 1024)
                    if not data:
                        return
                    self._send_all_nonblocking(dst_sock, data, deadline)
        finally:
            selector.close()
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    @staticmethod
    def _send_all_nonblocking(dst_sock: socket.socket, data: bytes, deadline: float) -> None:
        view = memoryview(data)
        sent_total = 0
        while sent_total < len(data):
            if time.time() > deadline:
                raise TimeoutError('write timeout')
            try:
                sent = dst_sock.send(view[sent_total:])
                if sent == 0:
                    raise ConnectionError('socket closed during send')
                sent_total += sent
            except BlockingIOError:
                time.sleep(0.001)

    @staticmethod
    def _safe_close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass

    @staticmethod
    def _send_503_and_close(client_sock: socket.socket) -> None:
        try:
            client_sock.sendall(DEFAULT_503_RESPONSE)
        except OSError:
            pass
        finally:
            try:
                client_sock.close()
            except OSError:
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = ProxyConfig.from_yaml('config.yml')
    SelectorProxyServer(config).serve_forever()


if __name__ == '__main__':
    main()
