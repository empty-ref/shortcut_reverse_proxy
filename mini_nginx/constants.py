CRLF = b'\r\n'
HEADER_END = b'\r\n\r\n'
READ_CHUNK_SIZE = 64 * 1024


DEFAULT_502_RESPONSE = b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'

DEFAULT_503_RESPONSE = b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'

DEFAULT_504_RESPONSE = b'HTTP/1.1 504 Gateway Timeout\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
