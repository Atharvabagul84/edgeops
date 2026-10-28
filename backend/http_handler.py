"""HTTP adapter: input boundaries, JSON responses, and frontend static files."""
import json
import logging
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .release import with_release
from .validation import utc_time


LOGGER = logging.getLogger('edgeops.http')
MAX_BODY = 64 * 1024


class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class EdgeOpsHandler(BaseHTTPRequestHandler):
    server_version = 'EdgeOps/0.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format_string, *args):
        LOGGER.info(json.dumps(dict(client=self.client_address[0], request=format_string % args)))

    def _headers(self, status, content_type, length, attachment=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="edgeops-diagnostics.json"')
        self.end_headers()

    def _json(self, status, value, attachment=False):
        if 200 <= status < 300 and urlsplit(self.path).path.startswith('/api/'):
            value = with_release(value)
        payload = json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8')
        self._headers(status, 'application/json; charset=utf-8', len(payload), attachment)
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def _check_host(self):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        # Docker can publish the internal port under another loopback port.
        host = self.headers.get('Host', '')
        parsed = urlsplit('//' + host)
        if parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username is not None:
            raise RequestError(403, 'This demo accepts loopback hostnames only.')
        return host, allowed

    def _body(self):
        host, _ = self._check_host()
        origin = self.headers.get('Origin')
        if origin is not None and origin != f'http://{host}':
            raise RequestError(403, 'Cross-origin requests are disabled.')
        if self.headers.get('Transfer-Encoding'):
            raise RequestError(400, 'Chunked request bodies are unsupported.')
        if self.headers.get_content_type() != 'application/json':
            raise RequestError(415, 'Use Content-Type: application/json.')
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise RequestError(400, 'Invalid Content-Length.') from None
        if length < 0:
            raise RequestError(400, 'Content-Length is required.')
        if length > MAX_BODY:
            raise RequestError(413, 'Request body exceeds 64 KiB.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestError(400, 'Incomplete request body.')
        try:
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number.')))
        except (ValueError, UnicodeError, RecursionError):
            raise RequestError(400, 'Request must be valid UTF-8 JSON with finite numbers.') from None
        if not isinstance(value, dict):
            raise RequestError(400, 'Request body must be a JSON object.')
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16:
                raise RequestError(400, 'Request JSON nesting exceeds 16 levels.')
            if isinstance(item, (dict, list)):
                children = item.values() if isinstance(item, dict) else item
                pending.extend((child, depth + 1) for child in children)
        return value

    def _execute(self, action):
        try:
            self._check_host()
            action()
        except RequestError as error:
            self._json(error.status, dict(error=error.message))
        except ValueError as error:
            self._json(400, dict(error=str(error)))
        except sqlite3.Error:
            LOGGER.exception('Local state persistence failed')
            self._json(503, dict(error='Local storage is temporarily unavailable. Retry the request.'))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            LOGGER.warning('Client connection closed before request completed')
        except Exception:
            LOGGER.exception('Unexpected request failure')
            self._json(500, dict(error='Unexpected local server error. See server logs.'))

    def do_GET(self):
        self._execute(self._get)

    def do_HEAD(self):
        self._execute(self._get)

    def _get(self):
        path = urlsplit(self.path).path
        if path == '/cloud-config.json':
            self._json(200, dict(mode='local'))
        elif path == '/api/health':
            self._json(200, dict(status='ok', mode='local', demo=True, persistence='sqlite'))
        elif path in ('/api/state', '/api/export'):
            state = self.server.repository.read()
            if path == '/api/export':
                state.update(exportedAt=utc_time(), diagnosticNote='Synthetic local demonstration. No AWS resources connected.')
            self._json(200, state, attachment=path == '/api/export')
        elif path.startswith('/api/'):
            raise RequestError(404, 'API route not found.')
        else:
            self._static(path)

    def _static(self, path):
        root = self.server.frontend.resolve()
        relative = 'index.html' if path == '/' else unquote(path).lstrip('/')
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise RequestError(404, 'File not found.')
        payload = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        self._headers(200, mime, len(payload))
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def do_POST(self):
        self._execute(self._post)

    def _post(self):
        path = urlsplit(self.path).path
        body = self._body()
        repository = self.server.repository
        if path == '/api/tick':
            state = repository.command(dict(action='tick', steps=body.get('steps', 1)))
        elif path == '/api/actions':
            state = repository.command(body)
        elif path == '/api/reset':
            state = repository.command(dict(action='reset'))
        elif path == '/api/telemetry':
            state = repository.ingest(body.get('events'))
        else:
            raise RequestError(404, 'API route not found.')
        self._json(200, state)
