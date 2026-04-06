import asyncio
import contextlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Upstream:
    host: str
    port: int
    semaphore: asyncio.Semaphore


class UpstreamPool:
    def __init__(self, upstreams: list[tuple[str, int]], max_conns_per_upstream: int = 100):
        if not upstreams:
            raise ValueError('UpstreamPool requires at least one upstream')

        self.upstreams = [
            Upstream(
                host=host,
                port=port,
                semaphore=asyncio.Semaphore(max_conns_per_upstream),
            )
            for host, port in upstreams
        ]
        self._next_index = 0
        self._lock = asyncio.Lock()

    async def acquire_upstream(self) -> Upstream:
        async with self._lock:
            upstream = self.upstreams[self._next_index]
            self._next_index = (self._next_index + 1) % len(self.upstreams)
        await upstream.semaphore.acquire()
        return upstream

    def release_upstream(self, upstream: Upstream) -> None:
        upstream.semaphore.release()
