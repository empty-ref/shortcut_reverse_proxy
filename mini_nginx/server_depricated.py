import asyncio
import contextlib
import logging
import socket

from mini_nginx.client_handler import handle_client
from mini_nginx.client_limiter import ClientLimiter
from mini_nginx.config import ProxyConfig
from mini_nginx.constants import DEFAULT_503_RESPONSE
from mini_nginx.upstream_pool import UpstreamPool

logger = logging.getLogger(__name__)


def configure_client_socket_keepalive(writer: asyncio.StreamWriter, config: ProxyConfig) -> None:
    sock = writer.get_extra_info('socket')
    if sock is None:
        return

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # macOS -  TCP_KEEPALIVE (seconds), Linux - TCP_KEEPIDLE.
        idle_opt = getattr(socket, 'TCP_KEEPIDLE', None)
        if idle_opt is None:
            idle_opt = getattr(socket, 'TCP_KEEPALIVE', None)
        if idle_opt is not None:
            sock.setsockopt(socket.IPPROTO_TCP, idle_opt, config.tcp_keepalive_idle)

        interval_opt = getattr(socket, 'TCP_KEEPINTVL', None)
        if interval_opt is not None:
            sock.setsockopt(socket.IPPROTO_TCP, interval_opt, config.tcp_keepalive_interval)

        count_opt = getattr(socket, 'TCP_KEEPCNT', None)
        if count_opt is not None:
            sock.setsockopt(socket.IPPROTO_TCP, count_opt, config.tcp_keepalive_count)
    except OSError:
        logger.exception('failed to configure client TCP keepalive')


async def create_proxy_server(config: ProxyConfig, pool: UpstreamPool) -> asyncio.base_events.Server:
    client_limiter = ClientLimiter(config.max_client_conns)

    async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client_addr = writer.get_extra_info('peername')
        configure_client_socket_keepalive(writer, config)

        async with client_limiter.lease() as acquired:
            if not acquired:
                logger.warning(
                    'client rejected: %s active=%s limit=%s', client_addr, client_limiter.active, client_limiter.limit
                )
                writer.write(DEFAULT_503_RESPONSE)
                with contextlib.suppress(Exception):
                    await writer.drain()
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                return

            logger.info(
                'client accepted: %s active=%s limit=%s', client_addr, client_limiter.active, client_limiter.limit
            )

            try:
                await asyncio.wait_for(handle_client(reader, writer, config, pool), timeout=config.total_timeout)
            except asyncio.TimeoutError:
                logger.exception('total timeout exceeded')
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
            finally:
                logger.info(
                    'client released: %s active=%s limit=%s', client_addr, client_limiter.active, client_limiter.limit
                )

    return await asyncio.start_server(
        client_connected_cb=client_connected,
        host=config.listen_host,
        port=config.listen_port,
    )
