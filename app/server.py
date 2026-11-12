"""Loopback-only local panel. No external service or API key required."""
import argparse
import json
import mimetypes
import secrets
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from library import Library, ROOT
from discovery import DiscoveryJobs

LIB = Library()
DISCOVERY = DiscoveryJobs(LIB)
TOKEN = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def local_request(self):
        host = self.headers.get('Host', '')
        return host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def send(self, status, body, mime='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local_request():
            return self.send(403, {'error': 'Acesso permitido apenas pelo painel local.'})
        parsed = urllib.parse.urlparse(self.path)
        args = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        path = parsed.path
        try:
            if path == '/api/meta':
                return self.send(200, {'app': 'trilhoteca', 'token': TOKEN, 'stats': LIB.stats(), 'projects': LIB.projects()})
            if path == '/api/search':
                return self.send(200, LIB.search(args.get('project_id'), args.get('query', ''), args.get('kind', 'all'),
                    args.get('credit', 'all'), args.get('favorites') == 'true', limit=100,
                    function=args.get('function') or None, no_voice=True if args.get('no_voice')=='true' else None,
                    duration_max=float(args['duration_max']) if args.get('duration_max') else None,
                    allow_unknown=args.get('allow_unknown')=='true'))
            if path == '/api/discovery':
                return self.send(200, {'job': DISCOVERY.status(), 'candidates': DISCOVERY.candidates(), 'stats': LIB.stats()})
            if path.startswith('/api/asset/'):
                return self.send(200, LIB.details(path.rsplit('/', 1)[1], args.get('project_id')))
            if path.startswith('/api/audio/'):
                aid = path.rsplit('/', 1)[1]
                a = LIB.asset(aid)
                ok, reason = LIB.eligible(a, LIB.project(args.get('project_id')))
                if not ok:
                    return self.send(403, {'error': reason})
                # Audio GET does not download: /api/preview prepares the cache first.
                with LIB.db() as db:
                    row = db.execute('SELECT path FROM downloads WHERE asset_id=?', (aid,)).fetchone()
                if not row or not Path(row['path']).is_file():
                    return self.send(404, {'error': 'Prepare a prévia antes de ouvir.'})
                return self.audio(Path(row['path']))
            static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
            if path in static:
                f = ROOT / 'static' / static[path]
                return self.send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            return self.send(404, {'error': 'Não encontrado.'})
        except (ValueError, OSError) as e:
            return self.send(400, {'error': str(e)})

    def audio(self, path):
        size = path.stat().st_size
        start, end = 0, size - 1
        requested = self.headers.get('Range')
        if requested:
            try:
                import re
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                if not match or not any(match.groups()):
                    raise ValueError()
                if not match[1]:
                    start = max(0, size - int(match[2]))
                else:
                    start = int(match[1])
                    end = min(size - 1, int(match[2])) if match[2] else size - 1
                if start < 0 or start >= size or start > end:
                    raise ValueError()
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'audio/mpeg')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'private, max-age=3600')
        if requested:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start)
            remaining = end - start + 1
            try:
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        if not self.local_request() or self.headers.get('X-Trilhoteca-Token') != TOKEN:
            return self.send(403, {'error': 'Reabra o painel local para continuar.'})
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.send(403, {'error': 'Origem inválida.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 1024 * 1024:
                raise ValueError('Pedido inválido.')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Pedido inválido.')
            if self.path == '/api/project':
                result = LIB.set_project(payload.get('name', ''), payload.get('usage'), payload.get('monetized'),
                                         payload.get('sponsored'), payload.get('project_id'))
            elif self.path == '/api/preview':
                result = LIB.preview(payload['asset_id'], payload.get('project_id'))
            elif self.path == '/api/deliver':
                result = LIB.deliver(payload['asset_ids'], payload.get('project_id'), payload.get('assets_dir') or None)
            elif self.path == '/api/feedback':
                result = LIB.feedback(payload['asset_id'], payload['value'])
            elif self.path == '/api/discovery/start':
                result = DISCOVERY.start(payload.get('mode', 'tracks'))
            else:
                return self.send(404, {'error': 'Não encontrado.'})
            self.send(200, result)
        except (ValueError, KeyError, OSError) as e:
            self.send(400, {'error': str(e)})
        except Exception as e:
            self.send(500, {'error': 'Não foi possível concluir. Tente novamente; os arquivos já entregues foram preservados.', 'detail': type(e).__name__})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=17846)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    print(f'Trilhoteca aberta em http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
