"""Read tables out of Wikipedia article HTML (the action=parse output), stdlib only.

Handles what Wikipedia tables actually do: rowspan and colspan, header rows, row headers in <th>,
hidden sort keys, footnote markers, nested tables, line breaks inside a cell, portrait images.
Each table comes back with the section heading it sits under, so "Ministers of State" can be told
apart from "Cabinet Ministers".
"""
from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser

MONTHS = ('january february march april may june july august september october november december').split()
_MON = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?'
DATE = re.compile(r'(\d{1,2})\s+' + _MON + r'\s+(\d{4})', re.I)
DATE_US = re.compile(_MON + r'\s+(\d{1,2}),\s+(\d{4})', re.I)


def _month(m):
    return [x[:3] for x in MONTHS].index(m.lower()[:3]) + 1
SKIP_TAGS = {'style', 'script', 'sup'}
BLOCK = {'br', 'p', 'li', 'div', 'ul', 'ol', 'dd', 'dt'}


def iso_date(text):
    m = DATE.search(text or '')
    if m:
        return f'{int(m.group(3)):04d}-{_month(m.group(2)):02d}-{int(m.group(1)):02d}'
    m = DATE_US.search(text or '')
    if m:
        return f'{int(m.group(3)):04d}-{_month(m.group(1)):02d}-{int(m.group(2)):02d}'
    return None


def _title_from_href(href):
    if not href or not href.startswith('/wiki/'):
        return None
    t = urllib.parse.unquote(href[6:].split('#')[0]).replace('_', ' ')
    if ':' in t.split(' ')[0] and t.split(':')[0] in ('File', 'Image', 'Help', 'Wikipedia', 'Template', 'Category', 'Special', 'Portal', 'Talk'):
        return None
    return t


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []          # finished top-level tables
        self.heading = ''         # last h2/h3/h4 text
        self.h2 = ''
        self._hbuf = None
        self._htag = None
        self.depth = 0            # table nesting depth
        self.table = None
        self.row = None
        self.cell = None
        self.skip = 0             # inside footnotes, styles, hidden spans
        self._stack = []          # tags that opened a skip

    # -- helpers
    def _hidden(self, tag, a):
        cls = a.get('class') or ''
        style = (a.get('style') or '').replace(' ', '').lower()
        return tag in SKIP_TAGS or 'display:none' in style or 'sortkey' in cls or 'mw-editsection' in cls or 'reference' in cls.split()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip:
            if tag not in ('br', 'img', 'meta', 'link', 'wbr', 'hr', 'input'):
                self._stack.append(tag)
                self.skip += 1
            return
        if self._hidden(tag, a):
            if tag not in ('br', 'img', 'meta', 'link', 'wbr', 'hr', 'input'):
                self.skip = 1; self._stack = [tag]
            return
        if tag in ('h2', 'h3', 'h4') and self.depth == 0:
            self._hbuf, self._htag = [], tag
            return
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                self.table = {'heading': self.heading, 'section': self.h2, 'rows': [], 'class': a.get('class') or ''}
            return
        if self.depth != 1:
            if self.cell is not None and tag in BLOCK:
                self.cell['text'].append('\n')
            return
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            def num(v):
                try:
                    return max(1, min(200, int(re.sub(r'\D', '', v or '1') or 1)))
                except ValueError:
                    return 1
            self.cell = {'tag': tag, 'rowspan': num(a.get('rowspan')), 'colspan': num(a.get('colspan')),
                         'text': [], 'links': [], 'img': None, 'file': None}
        elif self.cell is not None:
            if tag in BLOCK:
                self.cell['text'].append('\n')
            elif tag == 'a':
                href = a.get('href') or ''
                t = _title_from_href(href)
                if t:
                    self.cell['links'].append(t)
                elif href.startswith('/wiki/File:') and not self.cell['file']:
                    self.cell['file'] = urllib.parse.unquote(href[6:])
            elif tag == 'img' and not self.cell['img']:
                src = a.get('src') or ''
                if src.startswith('//'):
                    src = 'https:' + src
                w = int(re.sub(r'\D', '', a.get('width') or '0') or 0)
                if src.startswith('https://upload.wikimedia.org/') and w >= 30:
                    self.cell['img'] = src

    def handle_endtag(self, tag):
        if self.skip:
            if self._stack and self._stack[-1] == tag:
                self._stack.pop(); self.skip -= 1
            elif tag in self._stack:
                while self._stack and self._stack[-1] != tag:
                    self._stack.pop(); self.skip -= 1
                if self._stack:
                    self._stack.pop(); self.skip -= 1
            return
        if self._hbuf is not None and tag == self._htag:
            text = re.sub(r'\s+', ' ', ''.join(self._hbuf)).strip()
            self.heading = text
            if tag == 'h2':
                self.h2 = text
            self._hbuf = self._htag = None
            return
        if tag == 'table' and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.table is not None:
                self.tables.append(self.table); self.table = None
            return
        if self.depth != 1:
            return
        if tag in ('td', 'th') and self.cell is not None and self.row is not None:
            c = self.cell
            txt = ''.join(c['text'])
            lines = [re.sub(r'\s+', ' ', x).strip() for x in txt.split('\n')]
            c['lines'] = [x for x in lines if x]
            c['text'] = ' '.join(c['lines'])
            self.row.append(c); self.cell = None
        elif tag == 'tr' and self.row is not None and self.table is not None:
            if self.cell is not None:
                self.handle_endtag(self.cell['tag'])
            self.table['rows'].append(self.row); self.row = None

    def handle_data(self, data):
        if self.skip:
            return
        if self._hbuf is not None:
            self._hbuf.append(data)
        elif self.cell is not None:
            self.cell['text'].append(data)


def grid(rows):
    """Expand rowspan/colspan so every row has one entry per column."""
    out, pending = [], {}     # col -> (cell, rows left)
    for row in rows:
        line, col, it = [], 0, iter(row)
        cell = next(it, None)
        while cell is not None or pending.get(col):
            if pending.get(col):
                c, left = pending[col]
                line.append(c)
                pending[col] = (c, left - 1) if left > 1 else None
                col += 1
                continue
            for k in range(cell['colspan']):
                line.append(cell)
                if cell['rowspan'] > 1:
                    pending[col] = (cell, cell['rowspan'] - 1)
                col += 1
            cell = next(it, None)
        out.append(line)
    return out


def tables(html):
    p = _Parser()
    p.feed(html or '')
    p.close()
    out = []
    for t in p.tables:
        g = grid(t['rows'])
        heads = []
        while g and all(c['tag'] == 'th' for c in g[0]) and len(heads) < 3:
            heads.append(g.pop(0))
        if not heads or not g:
            continue
        width = max(len(r) for r in heads)
        header = []
        for j in range(width):
            parts = []
            for h in heads:
                if j < len(h) and (not parts or h[j]['text'] != parts[-1]):
                    parts.append(h[j]['text'])
            header.append(' '.join(x for x in parts if x).strip())
        rows = [r for r in g if any(c['tag'] == 'td' for c in r)]
        out.append({'heading': t['heading'], 'section': t['section'], 'class': t['class'], 'header': header, 'rows': rows})
    return out


ROLE_COLS = {
    'name': ['officeholder', 'name', 'incumbent', 'minister', 'governor', 'lieutenant governor', 'administrator',
             'deputy chief minister', 'chief minister', 'mayor'],
    'portfolio': ['portfolio', 'department', 'ministry', 'designation', 'office'],
    'state': ['state/ut', 'state', 'union territory', 'state or ut'],
    'party': ['political party', 'party'],
    'took': ['took office', 'assumed office', 'term start', 'since', 'tenure', 'inauguration', 'date entered office', 'entered office'],
    'left': ['left office', 'term end'],
    'portrait': ['portrait', 'photo', 'image'],
}


def columns(header):
    """Map roles to candidate column indices by header text, best first. Earlier keywords win
    (Officeholder before Chief Minister); a split header such as Party | Party gives two candidates."""
    low = [h.lower() for h in header]
    out, used = {}, set()
    for role, words in ROLE_COLS.items():
        hits = []
        for w in words:
            for j, h in enumerate(low):
                ok = h == w or h.startswith(w + ' ') or h.startswith(w + '(') or (role in ('took', 'left') and w in h)
                if role == 'party' and 'chief minister' in h:
                    ok = False
                if ok and j not in used and j not in hits:
                    hits.append(j)
            if hits and role == 'name':
                break                           # the best name keyword only
        if hits:
            out[role] = hits
            used.update(hits if role != 'name' else hits[:1])
    if 'state' in out and out.get('portfolio') and low[out['portfolio'][0]].startswith('ministry'):
        out['ministry'] = out.pop('portfolio')   # a list of chief ministers: "Ministry" names the government
    return out


def records(table):
    """One dict per row: name, link, portfolios, party, since, left, state, portrait, ministry link."""
    cols = columns(table['header'])
    if 'name' not in cols:
        return []
    out = []
    for r in table['rows']:
        def cell(role):
            cands = [r[j] for j in cols.get(role, []) if j < len(r)]
            for c in cands:                      # a cell with text wins over a seal or portrait next to it
                if c['text']:
                    return c
            if role != 'name':
                for c in cands:
                    if c.get('img') or c['links']:
                        return c
            return cands[0] if cands else None
        n = cell('name')
        if not n or not n['text'] or n['text'].lower() in ('vacant', 'none', '—', '-'):
            continue
        name = re.sub(r'\[\w+\]', '', n['lines'][0] if n['lines'] else n['text']).strip()
        name = re.sub(r'^(Shri|Smt\.?|Dr\.?|Sri)\s+', '', name)
        if not re.search(r'[A-Za-z]', name) or len(name) > 60:
            continue
        left = cell('left')
        lt = (left['text'] if left else '').strip().lower()
        pic = cell('portrait')
        near = [r[j] for j in cols.get('name', []) if j < len(r) and r[j] is not n]
        img = (pic or {}).get('img') or n.get('img') or next((c['img'] for c in near if c.get('img')), None)
        file = (pic or {}).get('file') or n.get('file') or next((c['file'] for c in near if c.get('file')), None)
        port = cell('portfolio')
        ministry = cell('ministry')
        st = cell('state')
        party = cell('party')
        out.append({
            'name': name, 'link': n['links'][0] if n['links'] else None,
            'portfolios': [re.sub(r'\[\w+\]', '', x).strip() for x in (port['lines'] if port else []) if x.strip()],
            'party': (party['text'] if party else '') or None, 'party_link': (party['links'][0] if party and party['links'] else None),
            'since': iso_date(cell('took')['text']) if cell('took') else None,
            'current': not lt or lt.startswith('incumbent') or lt in ('present', '—', '-', ''),
            'state': (st['lines'][0] if st and st['lines'] else (st['text'] if st else None)),
            'img': img, 'file': file,
            'ministry': (ministry['links'][0] if ministry and ministry['links'] else None),
            'heading': table['heading'],
        })
    return out
