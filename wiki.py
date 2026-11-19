"""English Wikipedia inside Sanjaya: search, read, and plain text for the Ask drawer.

Uses Wikipedia's public APIs (no key):
  - search:   https://en.wikipedia.org/w/api.php?action=query&list=search
  - article:  https://en.wikipedia.org/api/rest_v1/page/html/{title}   (Parsoid HTML)
  - summary:  https://en.wikipedia.org/api/rest_v1/page/summary/{title}
  - text:     https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1

Article HTML is cleaned with an allowlist before it reaches the page: no scripts, styles,
event handlers or unknown attributes; Wikipedia links become in-Sanjaya links; element ids
are prefixed so they can't collide with Sanjaya's own. Responses are cached in SQLite so
pages read once stay readable offline (stale copies are served when Wikipedia is unreachable).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

BASE = 'https://en.wikipedia.org'
TTL_HOURS = {'search': 6, 'page': 24 * 3, 'summary': 24 * 3, 'text': 24 * 3}
MAX_HTML = 6_000_000

ALLOWED = {
    'p', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'b', 'strong', 'i', 'em', 'sup', 'sub',
    'a', 'blockquote', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'figure', 'figcaption',
    'img', 'span', 'div', 'section', 'br', 'hr', 'cite', 'small', 'abbr', 'code', 'pre', 'q', 's', 'u', 'bdi', 'wbr',
}
VOID = {'img', 'br', 'hr', 'wbr'}
DROP_WITH_CONTENT = {'script', 'style', 'link', 'meta', 'noscript', 'iframe', 'object', 'embed', 'form', 'input',
                     'button', 'select', 'textarea', 'svg', 'math', 'template', 'audio', 'video', 'source', 'base', 'title', 'head'}
# Wikipedia furniture that doesn't read well outside Wikipedia.
DROP_CLASSES = {'mw-editsection', 'navbox', 'navbox-styles', 'vertical-navbox', 'sistersitebox', 'metadata', 'ambox',
                'noprint', 'mw-empty-elt', 'mbox-small', 'portalbox', 'side-box', 'mw-authority-control', 'authority-control',
                'catlinks', 'mw-kartographer-maplink', 'ext-phonos', 'reflist-lower-alpha', 'mw-references-wrap--hidden'}
KEEP_CLASSES = {'infobox', 'wikitable', 'thumb', 'hatnote', 'reference', 'references', 'reflist', 'mw-references-wrap',
                'infobox-label', 'infobox-data', 'infobox-header', 'infobox-above', 'infobox-image', 'infobox-caption',
                'mw-heading', 'gallery', 'quotebox', 'sidebar', 'tright', 'tleft', 'mw-default-size'}
NAMESPACES = {'File', 'Image', 'Category', 'Special', 'Help', 'Wikipedia', 'Template', 'Portal', 'Talk', 'User', 'Draft',
              'Module', 'MediaWiki', 'Book', 'TimedText', 'Template_talk', 'User_talk', 'Wikipedia_talk', 'File_talk'}
TITLE_RE = re.compile(r"^[^#<>\[\]{}|]{1,250}$")


def norm_title(t: str) -> str:
    t = re.sub(r'\s+', ' ', str(t or '')).strip().replace(' ', '_')
    if not TITLE_RE.match(t.replace('_', ' ')):
        raise ValueError('That is not a valid Wikipedia title.')
    return t[:1].upper() + t[1:]


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = {k.lower(): (v or '') for k, v in attrs}
        classes = set(a.get('class', '').split())
        if self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        if tag in DROP_WITH_CONTENT or classes & DROP_CLASSES or a.get('role') == 'navigation' or 'display:none' in a.get('style', '').replace(' ', ''):
            if tag not in VOID:
                self.skip = 1
            return
        if tag not in ALLOWED:
            return
        keep = []
        if a.get('id'):
            keep.append(('id', 'wk-' + re.sub(r'[^\w\-.:]', '_', a['id'])[:120]))
        cls = ' '.join(sorted(classes & KEEP_CLASSES))
        if cls:
            keep.append(('class', 'wk-' + cls.replace(' ', ' wk-')))
        if tag == 'a':
            keep += _link(a.get('href', ''), a.get('rel', ''))
            if a.get('title'):
                keep.append(('title', a['title'][:200]))
        elif tag == 'img':
            src = a.get('src', '')
            src = 'https:' + src if src.startswith('//') else src
            if not re.match(r'^https://upload\.wikimedia\.org/', src):
                return
            keep += [('src', src), ('alt', a.get('alt', '')[:300]), ('loading', 'lazy'), ('decoding', 'async')]
            for k in ('width', 'height'):
                if a.get(k, '').isdigit():
                    keep.append((k, a[k]))
        elif tag in ('td', 'th'):
            for k in ('colspan', 'rowspan'):
                if a.get(k, '').isdigit():
                    keep.append((k, a[k]))
            if a.get('scope') in ('row', 'col', 'rowgroup', 'colgroup'):
                keep.append(('scope', a['scope']))
        attrs_s = ''.join(f' {k}="{html.escape(v, quote=True)}"' for k, v in keep)
        self.out.append(f'<{tag}{attrs_s}>')
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID and self.stack and self.stack[-1] == tag.lower() and not self.skip:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag not in VOID:
                self.skip -= 1
            return
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f'</{t}>')
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self):
        while self.stack:
            self.out.append(f'</{self.stack.pop()}>')
        return ''.join(self.out)


def _link(href: str, rel: str):
    href = html.unescape(href or '').strip()
    if re.match(r'^(\./|/wiki/)', href):
        target = urllib.parse.unquote(re.sub(r'^(\./|/wiki/)', '', href))
        page, _, frag = target.partition('#')
        if page.split(':')[0] in NAMESPACES and ':' in page:
            # Special:, File:, Help: and other namespaces: open on Wikipedia instead
            return [('href', f'{BASE}/wiki/{urllib.parse.quote(target)}'), ('target', '_blank'), ('rel', 'noopener noreferrer')]
        out = [('href', f'{BASE}/wiki/{urllib.parse.quote(page)}'), ('data-wiki', page.replace('_', ' '))]
        if frag:
            out.append(('data-wikifrag', 'wk-' + frag))
        return out
    if href.startswith('#'):
        return [('href', '#'), ('data-wikijump', 'wk-' + re.sub(r'[^\w\-.:]', '_', href[1:])[:120])]
    if href.startswith('//'):
        href = 'https:' + href
    if re.match(r'^https?://', href):
        return [('href', href), ('target', '_blank'), ('rel', 'noopener noreferrer')]
    return []


def clean_html(raw: str) -> str:
    """Allowlist-clean Parsoid HTML; keep the <body> only."""
    m = re.search(r'<body[^>]*>(.*)</body>', raw, re.S | re.I)
    p = _Clean()
    p.feed(m.group(1) if m else raw)
    p.close()
    return p.result()


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', '', s or ''))


# ---------------------------------------------------------------- cache


def init(con):
    con.execute('CREATE TABLE IF NOT EXISTS wiki_cache(key TEXT PRIMARY KEY, fetched TEXT NOT NULL, body TEXT NOT NULL)')
    con.commit()


def _cached(db_connect, key, kind, fetch, now=None):
    """Fresh cache, else fetch, else stale cache. Returns (body, info)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    from contextlib import closing
    with closing(db_connect()) as con:
        init(con)
        row = con.execute('SELECT fetched,body FROM wiki_cache WHERE key=?', (key,)).fetchone()
    if row:
        age = now - dt.datetime.fromisoformat(row[0])
        if age < dt.timedelta(hours=TTL_HOURS[kind]):
            return row[1], {'cached': True, 'fetched': row[0], 'stale': False}
    try:
        body = fetch()
    except Exception as exc:
        if row:
            return row[1], {'cached': True, 'fetched': row[0], 'stale': True, 'error': f'{type(exc).__name__}'}
        raise
    stamp = now.isoformat(timespec='seconds')
    with closing(db_connect()) as con:
        con.execute('INSERT INTO wiki_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET fetched=excluded.fetched,body=excluded.body',
                    (key, stamp, body))
        con.execute("DELETE FROM wiki_cache WHERE key NOT IN (SELECT key FROM wiki_cache ORDER BY fetched DESC LIMIT 400)")
        con.commit()
    return body, {'cached': False, 'fetched': stamp, 'stale': False}


# ---------------------------------------------------------------- API


def search(q, get, db_connect, limit=12):
    q = re.sub(r'\s+', ' ', str(q or '')).strip()[:200]
    if len(q) < 2:
        raise ValueError('Type at least two characters.')
    params = {'action': 'query', 'list': 'search', 'srsearch': q, 'srlimit': str(limit), 'format': 'json',
              'srprop': 'snippet|timestamp|wordcount', 'formatversion': '2', 'srinfo': 'suggestion'}
    url = f'{BASE}/w/api.php?' + urllib.parse.urlencode(params)
    body, info = _cached(db_connect, 'search:' + q.lower(), 'search', lambda: get(url).decode('utf-8'))
    d = json.loads(body)
    hits = [{'title': h['title'], 'snippet': strip_tags(h.get('snippet', '')), 'words': h.get('wordcount', 0),
             'updated': h.get('timestamp', '')} for h in d.get('query', {}).get('search', [])]
    return {'q': q, 'results': hits, 'suggestion': d.get('query', {}).get('searchinfo', {}).get('suggestion', ''), **info}


def page(title, get, db_connect):
    t = norm_title(title)
    enc = urllib.parse.quote(t, safe='')
    raw, info = _cached(db_connect, 'page:' + t, 'page', lambda: get(f'{BASE}/api/rest_v1/page/html/{enc}?redirect=true', MAX_HTML).decode('utf-8'))
    try:
        sbody, _ = _cached(db_connect, 'summary:' + t, 'summary', lambda: get(f'{BASE}/api/rest_v1/page/summary/{enc}?redirect=true').decode('utf-8'))
        s = json.loads(sbody)
    except Exception:
        s = {}
    real = re.search(r'<title>(.*?)</title>', raw, re.S)
    # Names the lead puts in bold ("The International Atomic Energy Agency (IAEA)") help find related news.
    aliases = []
    for para in re.findall(r'<p\b[^>]*>(.*?)</p>', raw, re.S)[:3]:
        bolds = [strip_tags(b).strip() for b in re.findall(r'<b>(.*?)</b>', para, re.S)]
        if bolds:
            aliases = [b for b in dict.fromkeys(bolds) if 1 < len(b) <= 60][:4]
            break
    return {'title': strip_tags(s.get('title') or (real.group(1) if real else t.replace('_', ' '))),
            'description': s.get('description', ''), 'extract': s.get('extract', ''),
            'thumbnail': (s.get('thumbnail') or {}).get('source', ''), 'url': f'{BASE}/wiki/{enc}',
            'html': clean_html(raw), 'revision': s.get('revision', ''), 'aliases': aliases, **info}


def plain_text(title, get, db_connect, max_chars=60_000) -> str:
    t = norm_title(title)
    params = {'action': 'query', 'prop': 'extracts', 'explaintext': '1', 'titles': t.replace('_', ' '), 'format': 'json',
              'formatversion': '2', 'redirects': '1'}
    body, _ = _cached(db_connect, 'text:' + t, 'text', lambda: get(f'{BASE}/w/api.php?' + urllib.parse.urlencode(params)).decode('utf-8'))
    pages = json.loads(body).get('query', {}).get('pages', [])
    return (pages[0].get('extract', '') if pages else '')[:max_chars]


def passages(text: str, words=110) -> list:
    """Split plain text into passages of about `words` words, keeping section names."""
    out, section = [], 'Introduction'
    for block in re.split(r'\n{1,}', text):
        block = block.strip()
        m = re.match(r'^=+\s*(.*?)\s*=+$', block)
        if m:
            section = m.group(1)
            continue
        if not block or section in ('References', 'External links', 'See also', 'Further reading', 'Notes', 'Sources', 'Bibliography'):
            continue
        ws = block.split()
        for i in range(0, len(ws), words):
            out.append({'section': section, 'text': ' '.join(ws[i:i + words])})
    return out
