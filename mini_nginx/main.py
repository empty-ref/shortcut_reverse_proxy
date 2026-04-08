import asyncio
import contextlib
import logging
import os

from mini_nginx.client_handler import handle_client
from mini_nginx.client_limiter import ClientLimiter
from mini_nginx.config import ProxyConfig
from mini_nginx.constants import DEFAULT_503_RESPONSE
from mini_nginx.upstream_pool import UpstreamPool

log_level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = ProxyConfig()
    pool = UpstreamPool(upstreams=[('127.0.0.1', 9001), ('127.0.0.1', 9002)])
    client_limiter = ClientLimiter(config.max_client_conns)

    async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info('peername')

        limit_acquired = await client_limiter.try_acquire()

        if not limit_acquired:
            logger.warning('client rejected by limit: active=%s', client_limiter.active)
            writer.write(DEFAULT_503_RESPONSE)
            with contextlib.suppress(Exception):
                await writer.drain()
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return

        logger.debug('client accepted: active=%s', client_limiter.active)

        try:
            await asyncio.wait_for(handle_client(reader, writer, config, pool), timeout=config.total_timeout)
        except asyncio.TimeoutError:
            logger.exception('total timeout exceeded peer=%s', peer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        except Exception as e:
            logger.exception(
                'client handler failed peer=%s type=%s error=%r',
                peer,
                type(e).__name__,
                e,
            )
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        finally:
            await client_limiter.release()
            logger.debug('client released: active=%s', client_limiter.active)

    server = await asyncio.start_server(
        client_connected_cb=client_connected, host=config.listen_host, port=config.listen_port
    )

    addr_list = ', '.join(str(sock.getsockname()) for sock in server.sockets or [])
    logger.info('proxy listening on %s', addr_list)

    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
