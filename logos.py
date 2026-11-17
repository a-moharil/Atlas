"""Publisher identity marks, fetched from the publisher's own site and cached locally.

Only hosts present in the publisher registry or configured feeds are allowed (no open
proxy). Order: the publisher's apple-touch-icon (usually its square logo), the icon
declared in its home page, then Google's and DuckDuckGo's favicon services. Bytes
are validated as a real image and cached for 30 days.
"""
from __future__ import annotations

import hashlib
import html.parser
import re
import threading
import time
import urllib.parse
from pathlib import Path

MAX = 400_000
TTL = 30 * 86400
FAIL_TTL = 6 * 3600
LOCKS = [threading.Lock() for _ in range(16)]
SIGS = ((b'\x89PNG', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'), (b'GIF8', 'image/gif'), (b'RIFF', 'image/webp'),
        (b'\x00\x00\x01\x00', 'image/x-icon'), (b'<svg', 'image/svg+xml'), (b'<?xml', 'image/svg+xml'))


def kind(data: bytes):
    head = data[:64].lstrip()
    for sig, mime in SIGS:
        if head.startswith(sig):
            if mime == 'image/webp' and b'WEBP' not in data[:16]:
                continue
            if mime == 'image/svg+xml' and (b'<script' in data.lower() or b'onload' in data.lower()):
                return None  # never serve active SVG
            return mime
    return None


class _Icons(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag != 'link':
            return
        a = dict(attrs)
        rel = (a.get('rel') or '').lower()
        if 'icon' in rel and a.get('href'):
            size = 0
            m = re.search(r'(\d+)x\d+', a.get('sizes') or '')
            if m:
                size = int(m.group(1))
            if 'apple-touch' in rel:
                size = max(size, 180)
            self.found.append((size, a['href']))


def candidates(host: str, fetch_bytes):
    base = f'https://{host}'
    yield base + '/apple-touch-icon.png'
    try:
        page = fetch_bytes(base + '/', 900_000).decode('utf-8', errors='ignore')
        p = _Icons()
        p.feed(page[:400_000])
        for size, href in sorted(p.found, reverse=True)[:3]:
            url = urllib.parse.urljoin(base + '/', href)
            if url.startswith('https://'):
                yield url
    except Exception:
        pass
    yield 'https://www.google.com/s2/favicons?' + urllib.parse.urlencode({'domain': host, 'sz': 128})
    yield f'https://icons.duckduckgo.com/ip3/{host}.ico'


def get(host: str, allowed: set, cache_dir: Path, fetch_bytes):
    if host not in allowed or not re.fullmatch(r'[a-z0-9][a-z0-9.\-]{1,120}', host):
        raise ValueError('Unknown publisher')
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(host.encode()).hexdigest()[:24]
    path, miss = cache_dir / (token + '.img'), cache_dir / (token + '.miss')
    with LOCKS[int(token[:2], 16) % len(LOCKS)]:
        if path.exists() and time.time() - path.stat().st_mtime < TTL:
            data = path.read_bytes()
            return data, kind(data) or 'application/octet-stream'
        if miss.exists() and time.time() - miss.stat().st_mtime < FAIL_TTL:
            raise LookupError('No logo available')
        for url in candidates(host, fetch_bytes):
            try:
                data = fetch_bytes(url, MAX)
            except Exception:
                continue
            mime = kind(data)
            if mime and len(data) > 120:
                path.write_bytes(data)
                miss.unlink(missing_ok=True)
                return data, mime
        miss.write_text(str(time.time()))
        raise LookupError('No logo available')
