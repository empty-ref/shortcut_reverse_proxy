def parse_headers(header_lines: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_lines:
        if not line:
            continue
        if ':' not in line:
            raise ValueError(f'Bad header line: {line!r}')
        name, value = line.split(':', 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def parse_response_head(head: bytes) -> tuple[str, int, dict[str, str]]:

    text = head.decode('latin1')
    lines = text.split('\r\n')

    parts = lines[0].split(' ', 2)
    if len(parts) < 2:
        raise ValueError(f'Bad status line: {lines[0]!r}')

    return parts[0], int(parts[1]), parse_headers(lines[1:])


def parse_request_head(head: bytes) -> tuple[str, str, str, dict[str, str]]:
    text = head.decode('latin1')
    lines = text.split('\r\n')

    request_line = lines[0]
    parts = request_line.split(' ')

    method, path, version = parts
    return method, path, version, parse_headers(lines[1:])


def get_content_length(headers: dict[str, str]) -> int:
    value = headers.get('content-length')
    if value is None:
        return 0
    return int(value)


def is_chunked_response(headers: dict[str, str]) -> bool:
    value = headers.get('transfer-encoding', '')
    return 'chunked' in value.lower()


def has_connection_token(headers: dict[str, str], token: str) -> bool:
    value = headers.get('connection', '')
    tokens = [part.strip().lower() for part in value.split(',') if part.strip()]
    return token.lower() in tokens


def should_keep_alive(http_version: str, headers: dict[str, str]) -> bool:
    version = http_version.upper()
    if version == 'HTTP/1.1':
        return not has_connection_token(headers, 'close')
    if version == 'HTTP/1.0':
        return has_connection_token(headers, 'keep-alive')
    return False
