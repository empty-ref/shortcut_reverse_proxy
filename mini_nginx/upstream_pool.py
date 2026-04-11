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
    idle_connections: asyncio.LifoQueue[tuple[asyncio.StreamReader, asyncio.StreamWriter]]


class UpstreamPool:
    def __init__(self, upstreams: list[tuple[str, int]], max_conns_per_upstream: int = 100):
        if not upstreams:
            raise ValueError('UpstreamPool requires at least one upstream')

        self.upstreams = [
            Upstream(
                host=host,
                port=port,
                semaphore=asyncio.Semaphore(max_conns_per_upstream),
                idle_connections=asyncio.LifoQueue(maxsize=max_conns_per_upstream),
            )
            for host, port in upstreams
        ]
        self._next_index = 0
        self._lock = asyncio.Lock()

    async def _acquire_upstream(self) -> Upstream:
        async with self._lock:
            upstream = self.upstreams[self._next_index]
            self._next_index = (self._next_index + 1) % len(self.upstreams)
        await upstream.semaphore.acquire()
        return upstream

    async def acquire_connection(
        self, connect_timeout: float
    ) -> tuple[Upstream, asyncio.StreamReader, asyncio.StreamWriter]:
        upstream = await self._acquire_upstream()
        try:
            while True:
                try:
                    reader, writer = upstream.idle_connections.get_nowait()
                except asyncio.QueueEmpty:
                    break

                if writer.is_closing() or reader.at_eof():
                    await self._close_writer(writer)
                    continue

                return upstream, reader, writer

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(upstream.host, upstream.port),
                timeout=connect_timeout,
            )
            return upstream, reader, writer
        except Exception:
            upstream.semaphore.release()
            raise

    async def release_connection(
        self,
        upstream: Upstream,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        reusable: bool,
    ) -> None:
        try:
            if reusable and not writer.is_closing() and not reader.at_eof():
                try:
                    upstream.idle_connections.put_nowait((reader, writer))
                    return
                except asyncio.QueueFull:
                    pass

            await self._close_writer(writer)
        finally:
            upstream.semaphore.release()

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
