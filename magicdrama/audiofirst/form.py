"""Loopback-only input form. Saves brief/uploads locally, never credentials or paid jobs."""
import argparse
import base64
import json
import copy
import io
from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from .core import validate_brief, write_json

MAX_BODY = 30 * 1024 * 1024


def save_form(payload, root):
    brief = copy.deepcopy(payload['brief']); validate_brief(brief)
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    if (root/'brief.json').exists():raise ValueError('Brief already saved; use a fresh output folder')
    uploads = payload.get('uploads', {})
    sources=[(c,c['id']) for c in brief['characters']]+[(e,'environment-'+e['id']) for e in brief.get('environments',[]) if e.get('image')]
    if len({uid for _,uid in sources})!=len(sources):raise ValueError('Reference upload IDs collide')
    pending=[]
    for c,upload_id in sources:
        if c['image']['mode'] != 'upload': continue
        raw = base64.b64decode(uploads.get(upload_id, ''), validate=True)
        if len(raw) > 5*1024*1024: raise ValueError('Maximum 5 MiB per reference image')
        suffix = '.png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if raw.startswith(b'\xff\xd8\xff') else '.webp' if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP' else None
        if not suffix: raise ValueError('Upload PNG, JPEG or WebP images only')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if min(image.size)<64 or image.width*image.height>16_000_000:
                    raise ValueError('Reference dimensions must be at least 64px and at most 16 megapixels')
                image.verify()
        except (OSError,Image.DecompressionBombError) as error:
            raise ValueError('Unreadable reference image') from error
        path = root / 'uploads' / (upload_id + suffix)
        pending.append((path,raw));c['image']['path']=str(path.resolve())
    for path,raw in pending:
        path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
    write_json(root / 'brief.json', brief)
    return {'brief_path': str((root/'brief.json').resolve()), 'paid_requests': 0,
            'next': 'python audiofirst.py run --brief ' + str((root/'brief.json').resolve()) + ' --out NEW_RUN_DIRECTORY'}


def serve(output, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') != '127.0.0.1:' + str(port): self.send_error(403); return
            if self.path != '/': self.send_error(404); return
            raw = Path(__file__).with_name('input.html').read_bytes()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(raw)
        def do_POST(self):
            # Exact Origin prevents an unrelated website using the loopback service.
            if self.headers.get('Host') != '127.0.0.1:' + str(port): self.send_error(403); return
            if self.path != '/brief' or self.headers.get('Origin') != 'http://127.0.0.1:' + str(port):
                self.send_error(403); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY: raise ValueError('Request too large')
                if (Path(output)/'brief.json').exists(): raise ValueError('Brief already saved; restart with a fresh output folder')
                result = save_form(json.loads(self.rfile.read(size)), output)
                raw = json.dumps(result).encode(); self.send_response(200)
            except (ValueError, KeyError, TypeError) as e:
                raw = json.dumps({'error': str(e)}).encode(); self.send_response(400)
            self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(raw)
        def log_message(self, *args): pass
    print('Input form: http://127.0.0.1:' + str(port), flush=True)
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out', required=True); p.add_argument('--port', type=int, default=8765)
    a=p.parse_args(); serve(a.out, a.port)
