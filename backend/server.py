"""Run with python -m backend.server from the EdgeOps application directory."""
import argparse
import logging
from http.server import ThreadingHTTPServer
from pathlib import Path
from .http_handler import EdgeOpsHandler
from .repository import StateRepository


APP_ROOT = Path(__file__).resolve().parent.parent


def create_server(data_path, port=8765, frontend=None, host='127.0.0.1'):
    server = ThreadingHTTPServer((host, port), EdgeOpsHandler)
    server.daemon_threads = True
    server.repository = StateRepository(data_path)
    server.frontend = Path(frontend) if frontend is not None else APP_ROOT / 'frontend'
    return server


def main():
    parser = argparse.ArgumentParser(description='EdgeOps synthetic local fleet demo')
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1', '0.0.0.0'],
                        help='Use 0.0.0.0 only inside a container with loopback port publishing.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', type=Path, default=APP_ROOT / 'data' / 'edgeops.sqlite3')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be 1-65535')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    server = create_server(args.data, args.port, host=args.host)
    logging.getLogger('edgeops').info('Synthetic local demo at http://127.0.0.1:%s | SQLite: %s', args.port, args.data)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
