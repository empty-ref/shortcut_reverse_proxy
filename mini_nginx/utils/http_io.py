import asyncio
import logging

from mini_nginx.constants import HEADER_END, READ_CHUNK_SIZE

logger = logging.getLogger(__name__)


async def read_headers(reader: asyncio.StreamReader, timeout: float) -> bytes:
    try:
        data = await asyncio.wait_for(reader.readuntil(HEADER_END), timeout=timeout)
    except asyncio.LimitOverrunError as e:
        raise ValueError('header section is too large') from e
    except asyncio.IncompleteReadError as e:
        raise ConnectionError('unexpected EOF while reading headers') from e

    return data


async def write_all(writer: asyncio.StreamWriter, data: bytes, timeout: float) -> None:
    writer.write(data)
    await asyncio.wait_for(writer.drain(), timeout=timeout)


async def pipe_exact(
    src_reader: asyncio.StreamReader,
    dst_writer: asyncio.StreamWriter,
    nbytes: int,
    read_timeout: float,
    write_timeout: float,
) -> None:

    total = 0
    while total < nbytes:
        to_read = min(READ_CHUNK_SIZE, nbytes - total)
        chunk = await asyncio.wait_for(src_reader.read(to_read), timeout=read_timeout)
        if not chunk:
            raise ConnectionError('Unexpected EOF while reading fixed-size body')

        dst_writer.write(chunk)
        await asyncio.wait_for(dst_writer.drain(), timeout=write_timeout)

        total += len(chunk)


async def pipe_chunked_body(
    src_reader: asyncio.StreamReader,
    dst_writer: asyncio.StreamWriter,
    read_timeout: float,
    write_timeout: float,
) -> int:
    total = 0

    while True:
        size_line = await asyncio.wait_for(src_reader.readuntil(b'\r\n'), timeout=read_timeout)
        dst_writer.write(size_line)
        await asyncio.wait_for(dst_writer.drain(), timeout=write_timeout)
        total += len(size_line)

        size_str = size_line[:-2].split(b';', 1)[0].strip()
        chunk_size = int(size_str, 16)

        if chunk_size == 0:
            while True:
                trailer_line = await asyncio.wait_for(src_reader.readuntil(b'\r\n'), timeout=read_timeout)
                dst_writer.write(trailer_line)
                await asyncio.wait_for(dst_writer.drain(), timeout=write_timeout)
                total += len(trailer_line)

                if trailer_line == b'\r\n':
                    return total

        chunk = await asyncio.wait_for(src_reader.readexactly(chunk_size + 2), timeout=read_timeout)
        dst_writer.write(chunk)
        await asyncio.wait_for(dst_writer.drain(), timeout=write_timeout)
        total += len(chunk)


async def pipe_until_eof(
    src_reader: asyncio.StreamReader,
    dst_writer: asyncio.StreamWriter,
    read_timeout: float,
    write_timeout: float,
) -> int:
    total = 0

    while True:
        chunk = await asyncio.wait_for(src_reader.read(READ_CHUNK_SIZE), timeout=read_timeout)
        if not chunk:
            break

        dst_writer.write(chunk)
        await asyncio.wait_for(dst_writer.drain(), timeout=write_timeout)
        total += len(chunk)

    return total
