import asyncio


class ClientLimiter:
    def __init__(self, limit: int):
        if limit <= 0:
            raise ValueError('limit must be > 0')

        self.limit = limit
        self.active = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self.active >= self.limit:
                return False

            self.active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self.active == 0:
                raise RuntimeError('release called with no active clients')

            self.active -= 1

    def lease(self) -> 'ClientLimiterLease':
        return ClientLimiterLease(self)


class ClientLimiterLease:
    def __init__(self, limiter: ClientLimiter):
        self._limiter = limiter
        self.get_acquire = False

    async def __aenter__(self) -> bool:
        self.get_acquire = await self._limiter.try_acquire()
        return self.get_acquire

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.get_acquire:
            await self._limiter.release()
