from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ProxyConfig:
    listen_host: str = '127.0.0.1'
    listen_port: int = 8080

    connect_timeout: float = 3.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    total_timeout: float = 6000.0
    # max_header_bytes: int = 64 * 1024
    # max_requests_per_client_connection: int = 100

    max_client_conns: int = 2000
    upstreams: list[tuple[str, int]] = field(default_factory=lambda: [('127.0.0.1', 9001), ('127.0.0.1', 9002)])
    max_conns_per_upstream: int = 2000

    # tcp_keepalive_idle: int = 30
    # tcp_keepalive_interval: int = 10
    # tcp_keepalive_count: int = 3

    @classmethod
    def from_yaml(cls, path: str = 'config.yml') -> 'ProxyConfig':
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with config_path.open('r', encoding='utf-8') as f:
            raw = yaml.safe_load(f) or {}

        upstreams_raw = raw.get('upstreams')
        upstreams: list[tuple[str, int]] = [('127.0.0.1', 9001), ('127.0.0.1', 9002)]
        if upstreams_raw:
            upstreams = [(str(item['host']), int(item['port'])) for item in upstreams_raw]

        return cls(
            listen_host=str(raw.get('listen_host', '127.0.0.1')),
            listen_port=int(raw.get('listen_port', 8080)),
            connect_timeout=float(raw.get('connect_timeout', 3.0)),
            read_timeout=float(raw.get('read_timeout', 15.0)),
            write_timeout=float(raw.get('write_timeout', 15.0)),
            total_timeout=float(raw.get('total_timeout', 30.0)),
            max_header_bytes=int(raw.get('max_header_bytes', 64 * 1024)),
            max_requests_per_client_connection=int(raw.get('max_requests_per_client_connection', 100)),
            max_client_conns=int(raw.get('max_client_conns', 20)),
            upstreams=upstreams,
            max_conns_per_upstream=int(raw.get('max_conns_per_upstream', 100)),
            tcp_keepalive_idle=int(raw.get('tcp_keepalive_idle', 30)),
            tcp_keepalive_interval=int(raw.get('tcp_keepalive_interval', 10)),
            tcp_keepalive_count=int(raw.get('tcp_keepalive_count', 3)),
        )
