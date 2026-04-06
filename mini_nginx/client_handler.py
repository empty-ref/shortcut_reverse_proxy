import asyncio
import contextlib
import logging
import time

from mini_nginx.config import ProxyConfig
from mini_nginx.constants import DEFAULT_502_RESPONSE, DEFAULT_504_RESPONSE
from mini_nginx.upstream_pool import UpstreamPool
from mini_nginx.utils.http_io import pipe_chunked_body, pipe_exact, pipe_until_eof, read_headers, write_all
from mini_nginx.utils.http_parser import (
    get_content_length,
    is_chunked_response,
    parse_request_head,
    parse_response_head,
    should_keep_alive,
)
from mini_nginx.utils.http_rules import response_must_not_have_body
import uuid

logger = logging.getLogger(__name__)


async def send_response(writer: asyncio.StreamWriter, data: bytes) -> None:
    writer.write(data)
    await writer.drain()


async def read_client_request(
    client_reader: asyncio.StreamReader, read_timeout: float
) -> tuple[bytes, str, str, dict[str, str]]:
    request_head = await read_headers(client_reader, timeout=read_timeout)
    method, path, headers = parse_request_head(request_head)

    return request_head, method, path, headers


async def forward_request_body(
    client_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    headers: dict[str, str],
) -> None:
    content_length = get_content_length(headers)
    if content_length == 0:
        return

    await pipe_exact(src_reader=client_reader, dst_writer=upstream_writer, nbytes=content_length)


async def forward_response(
    upstream_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    method: str,
    read_timeout: float,
    write_timeout: float,
) -> tuple[str, int, int, dict[str, str], bool]:
    response_head = await read_headers(upstream_reader, timeout=read_timeout)
    response_version, status_code, response_headers = parse_response_head(response_head)

    await write_all(client_writer, response_head, timeout=write_timeout)
    if response_must_not_have_body(method, status_code):
        response_bytes = 0
        response_is_delimited = True
    elif is_chunked_response(response_headers):
        response_bytes = await pipe_chunked_body(
            src_reader=upstream_reader,
            dst_writer=client_writer,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
        )
        response_is_delimited = True
    else:
        response_content_length = get_content_length(response_headers)
        if response_content_length > 0:
            response_bytes = await pipe_exact(
                src_reader=upstream_reader,
                dst_writer=client_writer,
                nbytes=response_content_length,
                read_timeout=read_timeout,
                write_timeout=write_timeout,
            )
            response_is_delimited = True
        else:
            response_bytes = await pipe_until_eof(
                src_reader=upstream_reader,
                dst_writer=client_writer,
                read_timeout=read_timeout,
                write_timeout=write_timeout,
            )
            response_is_delimited = False

    return response_version, status_code, response_bytes, response_headers, response_is_delimited


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    config: ProxyConfig,
    pool: UpstreamPool,
) -> None:

    started = time.perf_counter()
    req_uuid = uuid.uuid4()
    logger.info(f'request {req_uuid}: start')
    upstream = upstream_writer = None

    try:
        request_head, method, path, headers = await read_client_request(client_reader, config.read_timeout)
        upstream = await pool.acquire_upstream()
        logger.info(f'request {req_uuid}: acquire upstream {upstream.host}:{upstream.port}')

        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(upstream.host, upstream.port),
            timeout=config.connect_timeout,
        )

        await write_all(upstream_writer, request_head, timeout=config.write_timeout)

        await forward_request_body(client_reader=client_reader, upstream_writer=upstream_writer, headers=headers)

        await forward_response(
            upstream_reader=upstream_reader,
            client_writer=client_writer,
            method=method,
            read_timeout=config.read_timeout,
            write_timeout=config.write_timeout,
        )
    except Exception as e:
        logger.exception(f'error while processing client {e}')
        with contextlib.suppress(Exception):
            await send_response(client_writer, DEFAULT_502_RESPONSE)

    finally:
        if upstream_writer is not None:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

        client_writer.close()
        with contextlib.suppress(Exception):
            await client_writer.wait_closed()

        if upstream is not None:
            pool.release_upstream(upstream)

    logger.info(f'request {req_uuid} DONE - {(time.perf_counter() - started) * 1000} ms.')
