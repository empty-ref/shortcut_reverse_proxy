import asyncio
import contextlib
import logging
import time

from mini_nginx.config import ProxyConfig
from mini_nginx.constants import DEFAULT_502_RESPONSE, DEFAULT_504_RESPONSE
from mini_nginx.upstream_pool import UpstreamPool
from mini_nginx.utils.http_io import (
    ClientClosedConnection,
    pipe_chunked_body,
    pipe_exact,
    pipe_until_eof,
    read_headers,
    write_all,
)
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
) -> tuple[bytes, str, str, str, dict[str, str]]:
    request_head = await read_headers(client_reader, timeout=read_timeout)
    method, path, version, headers = parse_request_head(request_head)

    return request_head, method, path, version, headers


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
    try:
        while True:
            started = time.perf_counter()
            req_uuid = uuid.uuid4()
            logger.debug('request %s: start', req_uuid)
            stage = 'read_client_request'

            upstream = upstream_reader = upstream_writer = None
            upstream_reusable = False
            try:
                request_head, method, path, request_version, headers = await read_client_request(
                    client_reader, config.read_timeout
                )
                stage = 'acquire_upstream_connection'
                upstream, upstream_reader, upstream_writer = await pool.acquire_connection(config.connect_timeout)
                logger.debug('request %s: acquire upstream %s:%s path=%s', req_uuid, upstream.host, upstream.port, path)

                stage = 'write_request_head'
                await write_all(upstream_writer, request_head, timeout=config.write_timeout)
                stage = 'forward_request_body'
                await forward_request_body(
                    client_reader=client_reader, upstream_writer=upstream_writer, headers=headers
                )

                stage = 'forward_response'
                response_version, _, _, response_headers, response_is_delimited = await forward_response(
                    upstream_reader=upstream_reader,
                    client_writer=client_writer,
                    method=method,
                    read_timeout=config.read_timeout,
                    write_timeout=config.write_timeout,
                )

                client_wants_keep_alive = should_keep_alive(request_version, headers)
                upstream_allows_keep_alive = should_keep_alive(response_version, response_headers)
                keep_alive = client_wants_keep_alive and upstream_allows_keep_alive and response_is_delimited
                upstream_reusable = upstream_allows_keep_alive and response_is_delimited
                if not keep_alive:
                    break
            except ClientClosedConnection:
                logger.debug('request %s: client closed keep-alive connection', req_uuid)
                break
            except (ConnectionError, asyncio.IncompleteReadError) as e:
                logger.warning(
                    'request %s connection closed at stage=%s type=%s error=%r', req_uuid, stage, type(e).__name__, e
                )
                break
            except Exception as e:
                logger.exception(
                    'request %s failed at stage=%s type=%s error=%r', req_uuid, stage, type(e).__name__, e
                )
                with contextlib.suppress(Exception):
                    await send_response(client_writer, DEFAULT_502_RESPONSE)
                break
            finally:
                if upstream is not None and upstream_reader is not None and upstream_writer is not None:
                    await pool.release_connection(
                        upstream=upstream,
                        reader=upstream_reader,
                        writer=upstream_writer,
                        reusable=upstream_reusable,
                    )

                logger.debug('request %s DONE - %.3f ms.', req_uuid, (time.perf_counter() - started) * 1000)
    finally:
        client_writer.close()
        with contextlib.suppress(Exception):
            await client_writer.wait_closed()
