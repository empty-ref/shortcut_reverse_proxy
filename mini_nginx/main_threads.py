import logging

from mini_nginx.config import ProxyConfig
from mini_nginx.utils.threads_utils import SelectorProxyServer

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = ProxyConfig()
    SelectorProxyServer(config).serve_forever()


if __name__ == '__main__':
    main()
