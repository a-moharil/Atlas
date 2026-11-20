"""US elections pack: results for the House, Senate, governors and president, downloaded on first use.

Sources (downloaded, not shipped):
  - FiveThirtyEight election-results (CC BY 4.0): every House race since 1976 and Senate, governor and
    presidential races since the late 1990s, through 2024. FiveThirtyEight closed in 2025, so the archive ends there.
  - US state outlines from the Census Bureau's cartographic boundaries (public domain), via PublicaMundi's GeoJSON.
Results after 2024 come from Wikipedia at view time (us_live.py) and from us_elections_extra.json.

Builds election_data/us/: us_elections.sqlite3, geo.json (projected state outlines and House tiles), manifest.json.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'election_data' / 'us'
RAW = OUT / 'raw'
DB = OUT / 'us_elections.sqlite3'
PACK_VERSION = 1
BASE = 'https://raw.githubusercontent.com/fivethirtyeight/election-results/main/'
SOURCES = [
    ('house.csv', BASE + 'election_results_house.csv', 'FiveThirtyEight House results 1976–2024', 'CC BY 4.0'),
    ('senate.csv', BASE + 'election_results_senate.csv', 'FiveThirtyEight Senate results', 'CC BY 4.0'),
    ('governor.csv', BASE + 'election_results_gubernatorial.csv', 'FiveThirtyEight governor results', 'CC BY 4.0'),
    ('president.csv', BASE + 'election_results_presidential.csv', 'FiveThirtyEight presidential results by state', 'CC BY 4.0'),
    ('races.csv', BASE + 'races.csv', 'FiveThirtyEight race list (incumbent party, dates)', 'CC BY 4.0'),
    ('states.json', 'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json',
     'US state outlines (US Census Bureau, via PublicaMundi)', 'Public domain'),
]
ATTRIBUTION = ('US results 1976–2024: FiveThirtyEight election-results (CC BY 4.0). 2025–26 results: Wikipedia (CC BY-SA), '
               'as edited at the time of reading. State outlines: US Census Bureau.')

STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut',
    'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
    'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana',
    'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
    'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}
BY_NAME = {v: k for k, v in STATES.items()}
SPLIT_EV = {'M1': ('ME', 1), 'M2': ('ME', 2), 'N1': ('NE', 1), 'N2': ('NE', 2), 'N3': ('NE', 3)}
DEM = {'DEM', 'DFL', 'DNL', 'D'}
REP = {'REP', 'R'}
IND = {'IND', 'I', 'NPA', 'NON', 'UNA', 'NPP'}


def party_of(code):
    c = (code or '').upper()
    if c in DEM:
        return 'D'
    if c in REP:
        return 'R'
    if c in IND:
        return 'I'
    return 'O'


# ------------------------------------------------------------------ download job
_lock = threading.Lock()
_job = {'state': 'idle', 'step': '', 'done': 0, 'total': len(SOURCES), 'error': None}


def manifest():
    try:
        return json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def status():
    m = manifest()
    return {'ready': bool(m and m.get('version') == PACK_VERSION and DB.exists()), 'manifest': m, 'job': dict(_job),
            'download_mb': 9, 'sources': [{'what': w, 'licence': l} for _, _, w, l in SOURCES]}


def start(fetch_bytes):
    with _lock:
        if _job['state'] == 'running':
            return False
        _job.update(state='running', step='Starting', done=0, error=None)

    def work():
        try:
            build(fetch_bytes)
            _job.update(state='done', step='')
        except Exception as exc:
            _job.update(state='failed', error=f'{type(exc).__name__}: {exc}'[:300])
    threading.Thread(target=work, name='us-elections-pack', daemon=True).start()
    return True


def build(fetch_bytes=None, raw_dir=None):
    raw = Path(raw_dir) if raw_dir else RAW
    raw.mkdir(parents=True, exist_ok=True)
    for i, (name, url, what, _) in enumerate(SOURCES):
        _job.update(step=f'Downloading {what}', done=i)
        p = raw / name
        if p.exists() and p.stat().st_size > 0:
            continue
        if fetch_bytes is None:
            raise FileNotFoundError(f'{name} is missing and no downloader was given')
        data = fetch_bytes(url)
        if data[:200].lstrip().lower().startswith(b'<!doctype html') or data[:200].lstrip().lower().startswith(b'<html'):
            raise ValueError(f'{name}: got a web page instead of data')
        p.write_bytes(data)
    _job.update(step='Building the results database', done=len(SOURCES) - 1)
    races = read_races(raw)
    races += extra_races()
    OUT.mkdir(parents=True, exist_ok=True)
    write_db(races, OUT / 'us_elections.tmp.sqlite3')
    (OUT / 'us_elections.tmp.sqlite3').replace(DB)
    _job.update(step='Projecting the map')
    geo = build_geo(raw, races)
    (OUT / 'geo.json').write_text(json.dumps(geo, separators=(',', ':')), encoding='utf-8')
    (OUT / 'manifest.json').write_text(json.dumps({'version': PACK_VERSION, 'built': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                                                   'races': len(races), 'attribution': ATTRIBUTION}), encoding='utf-8')
    _job.update(done=len(SOURCES))


# ------------------------------------------------------------------ reading FiveThirtyEight
def _csv(raw, name):
    return csv.DictReader(io.StringIO((raw / name).read_text(encoding='utf-8')))


def _seat(office, row):
    s = (row.get('office_seat_name') or '').strip()
    if office == 'H':
        return s.replace('District ', '').strip() or '1'
    if office == 'S':
        return s.replace('Class ', '').strip()
    return ''


def read_races(raw):
    meta = {}
    for r in _csv(raw, 'races.csv'):
        meta[r['id']] = r
    out = []
    for office, name in (('H', 'house.csv'), ('S', 'senate.csv'), ('G', 'governor.csv'), ('P', 'president.csv')):
        groups = {}
        for r in _csv(raw, name):
            stage = r['stage']
            if stage not in ('general', 'runoff', 'jungle primary', 'recall'):
                continue
            st = r['state_abbrev']
            if not st:
                continue
            if office == 'P' and st in SPLIT_EV:
                st, dist = SPLIT_EV[st]
                seat = str(dist)
            elif office == 'P':
                seat = ''
            else:
                if st not in STATES:
                    continue
                seat = _seat(office, r)
            special = r['special'] == 'true' or stage == 'recall'
            key = (office, int(r['cycle']), st, seat, special)
            groups.setdefault(key, {}).setdefault(stage, []).append(r)
        for (office_, cycle, st, seat, special), stages in groups.items():
            stage = 'runoff' if 'runoff' in stages else 'general' if 'general' in stages else 'recall' if 'recall' in stages else 'jungle primary'
            rows = stages[stage]
            if stage == 'jungle primary' and not any(x['winner'] == 'true' for x in rows):
                continue
            rec = _race(office_, cycle, st, seat, special, stage, rows, meta)
            if rec:
                out.append(rec)
    return out


def _race(office, cycle, st, seat, special, stage, rows, meta):
    cands = {}
    for r in rows:
        key = r['candidate_id'] or r['candidate_name'] or r['alt_result_text'] or 'other'
        c = cands.setdefault(key, {'name': r['candidate_name'] or r['alt_result_text'] or 'Other', 'votes': 0, 'parties': [],
                                   'winner': False, 'unopposed': False})
        try:
            c['votes'] += int(float(r['votes'] or 0))
        except ValueError:
            pass
        c['parties'].append(r['ballot_party'])
        c['winner'] = c['winner'] or r['winner'] == 'true'
        c['unopposed'] = c['unopposed'] or r['unopposed'] == 'true'
    for c in cands.values():
        ps = [party_of(p) for p in c['parties']]
        c['party'] = 'D' if 'D' in ps else 'R' if 'R' in ps else 'I' if 'I' in ps else 'O'
    total = sum(c['votes'] for c in cands.values())
    ranked = sorted(cands.values(), key=lambda c: (-c['winner'], -c['votes']))
    win = ranked[0] if ranked and (ranked[0]['winner'] or ranked[0]['unopposed']) else None
    if not win:
        return None
    others = [c for c in ranked if c is not win and c['name'] != 'Other']
    run = max(others, key=lambda c: c['votes']) if others else None
    m = meta.get(rows[0]['race_id'], {})
    margin = round(100 * (win['votes'] - (run['votes'] if run else 0)) / total, 2) if total and win['votes'] else None
    pid = {'H': f'H-{cycle}-{st}-{seat}', 'S': f'S-{cycle}-{st}-{seat}', 'G': f'G-{cycle}-{st}', 'P': f'P-{cycle}-{st}' + (f'-{seat}' if seat else '')}[office]
    if special and office != 'P':
        pid += '-special'
    return {'id': pid, 'office': office, 'cycle': cycle, 'state': st, 'seat': seat, 'special': int(special), 'stage': stage,
            'date': m.get('date') or None, 'winner': win['name'], 'winner_party': win['party'],
            'runner': run['name'] if run else None, 'runner_party': run['party'] if run else None,
            'winner_votes': win['votes'] or None, 'runner_votes': run['votes'] if run else None, 'total': total or None,
            'margin_pct': margin, 'unopposed': int(win['unopposed'] or not run), 'incumbent_party': party_of(m.get('incumbent_party')) if m.get('incumbent_party') else None,
            'cands': json.dumps([[c['name'], c['party'], c['votes'], round(100 * c['votes'] / total, 2) if total else None, int(c is win)]
                                 for c in ranked[:8]]),
            'called': 1, 'origin': '538', 'source': rows[0].get('source') or ''}


def extra_races():
    """Reviewed results after FiveThirtyEight's archive ends (off-year governor races)."""
    try:
        data = json.loads((ROOT / 'us_elections_extra.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    out = []
    for r in data.get('races', []):
        rec = {'office': r['office'], 'cycle': r['cycle'], 'state': r['state'], 'seat': r.get('seat', ''), 'special': int(r.get('special', 0)),
               'stage': 'general', 'date': r.get('date'), 'winner': r['winner'], 'winner_party': r['party'], 'runner': r.get('runner'),
               'runner_party': r.get('runner_party'), 'winner_votes': None, 'runner_votes': None, 'total': None,
               'margin_pct': r.get('margin_pct'), 'unopposed': 0, 'incumbent_party': r.get('incumbent_party'),
               'cands': json.dumps([[r['winner'], r['party'], None, r.get('winner_pct'), 1]] + ([[r['runner'], r.get('runner_party'), None, r.get('runner_pct'), 0]] if r.get('runner') else [])),
               'called': 1, 'origin': 'file', 'source': r.get('source', '')}
        rec['id'] = {'G': f"G-{r['cycle']}-{r['state']}"}.get(r['office'], f"{r['office']}-{r['cycle']}-{r['state']}-{rec['seat']}")
        out.append(rec)
    return out


COLS = ['id', 'office', 'cycle', 'state', 'seat', 'special', 'stage', 'date', 'winner', 'winner_party', 'runner', 'runner_party',
        'winner_votes', 'runner_votes', 'total', 'margin_pct', 'unopposed', 'incumbent_party', 'cands', 'called', 'origin', 'source']


def write_db(races, path):
    if Path(path).exists():
        Path(path).unlink()
    con = sqlite3.connect(str(path))
    con.execute(f'CREATE TABLE races ({", ".join(c + (" TEXT PRIMARY KEY" if c == "id" else "") for c in COLS)})')
    con.execute('CREATE INDEX races_oc ON races(office, cycle)')
    seen = set()
    for r in races:
        if r['id'] in seen:
            continue
        seen.add(r['id'])
        con.execute(f'INSERT INTO races VALUES ({",".join("?" * len(COLS))})', [r.get(c) for c in COLS])
    con.commit(); con.close()


# ------------------------------------------------------------------ apportionment and electoral votes
def era_of(cycle):
    """Census whose apportionment a House election used: 2002-2010 -> 2000, 2012-2020 -> 2010, 2022-2030 -> 2020."""
    return ((cycle - 2) // 10) * 10


def apportionment(races):
    """House seats per state for each census era, counted from the districts that held elections."""
    seats = {}
    for r in races:
        if r['office'] != 'H':
            continue
        e = era_of(r['cycle'])
        try:
            d = int(r['seat'])
        except (TypeError, ValueError):
            continue
        cur = seats.setdefault(e, {})
        cur[r['state']] = max(cur.get(r['state'], 0), d)
    return seats


def electoral_votes(appt, cycle):
    """Presidential elections use the apportionment of the census two years before (2024 uses 2020)."""
    e = ((cycle - 1) // 10) * 10
    ap = appt.get(e) or {}
    ev = {s: n + 2 for s, n in ap.items()}
    if ev:
        ev['DC'] = 3
    return ev


# ------------------------------------------------------------------ map: projected states + House tiles
def _albers(lon, lat, lat1, lat2, lat0, lon0):
    r = math.radians
    n = (math.sin(r(lat1)) + math.sin(r(lat2))) / 2
    c = math.cos(r(lat1)) ** 2 + 2 * n * math.sin(r(lat1))
    rho0 = math.sqrt(c - 2 * n * math.sin(r(lat0))) / n
    rho = math.sqrt(max(0.0, c - 2 * n * math.sin(r(lat)))) / n
    th = n * r(lon - lon0)
    return rho * math.sin(th), rho0 - rho * math.cos(th)


def project(lon, lat, st):
    """Albers USA style: the lower 48 in one conic projection, Alaska shrunk and Hawaii moved into insets.
    Output in a 960 x 600 frame, y downward."""
    if st == 'AK':
        if lon > 0:
            lon -= 360
        x, y = _albers(lon, lat, 55, 65, 50, -154)
        return x * 1000, -y * 1000          # placed into its inset box by build_geo
    if st == 'HI':
        x, y = _albers(lon, lat, 8, 18, 3, -157)
        return x * 1000, -y * 1000
    x, y = _albers(lon, lat, 29.5, 45.5, 37.5, -96)
    return 480 + x * 1070, 270 - y * 1070


def _simplify(ring, tol):
    import elections_data as ED
    try:
        return ED.simplify(ring, tol) if len(ring) > 8 else ring
    except Exception:
        return ring


INSETS = {'AK': (28, 448, 210, 135), 'HI': (250, 500, 100, 70)}     # x, y, width, height in the 960 x 600 frame
INSET_FIT = {}


def _fit_insets(g):
    """Scale Alaska and Hawaii into fixed boxes in the lower left, keeping their shape."""
    for f in g['features']:
        st = BY_NAME.get(f['properties'].get('name'))
        if st not in INSETS:
            continue
        geom = f['geometry']
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        pts = [project(lon, lat, st) for poly in polys for lon, lat in poly[0]]
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        bx, by, bw, bh = INSETS[st]
        k = min(bw / ((x1 - x0) or 1), bh / ((y1 - y0) or 1))
        ox, oy = bx + (bw - k * (x1 - x0)) / 2, by + (bh - k * (y1 - y0)) / 2
        INSET_FIT[st] = (lambda x0, y0, k, ox, oy: (lambda x, y: (ox + (x - x0) * k, oy + (y - y0) * k)))(x0, y0, k, ox, oy)


def build_geo(raw, races):
    g = json.loads((raw / 'states.json').read_text(encoding='utf-8'))
    _fit_insets(g)
    states, cent = {}, {}
    for f in g['features']:
        st = BY_NAME.get(f['properties'].get('name'))
        if not st:
            continue
        geom = f['geometry']
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        rings, area_sum, cx, cy = [], 0.0, 0.0, 0.0
        for poly in polys:
            ring = [project(lon, lat, st) for lon, lat in poly[0]]
            if st in INSETS:
                ring = [INSET_FIT[st](x, y) for x, y in ring]
            ring = _simplify(ring, 0.6)
            if len(ring) < 4:
                continue
            a = 0.0
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                a += x1 * y2 - x2 * y1
            a = abs(a) / 2
            if a < 0.5:
                continue
            area_sum += a
            cx += a * sum(p[0] for p in ring) / len(ring); cy += a * sum(p[1] for p in ring) / len(ring)
            rings.append([round(v, 1) for p in ring for v in p])
        if rings:
            states[st] = rings
            cent[st] = (cx / area_sum, cy / area_sum)
    appt = apportionment(races)
    tiles = {}
    for era, ap in sorted(appt.items()):
        if sum(ap.values()) < 400:
            continue
        tiles[str(era)] = house_tiles(ap, cent)
    return {'width': 960, 'height': 600, 'states': states, 'centroids': {k: [round(a, 1), round(b, 1)] for k, (a, b) in cent.items()},
            'tiles': tiles, 'apportionment': {str(k): v for k, v in appt.items()}}


def house_tiles(ap, cent):
    """One hexagon per district, each state's hexes kept together around where the state is.
    A state's districts start from its centroid and spread to the nearest free cells (largest states first),
    so the tile map stays valid however the district lines are redrawn."""
    import elections_data as ED
    pts, ids = [], []
    for st, n in ap.items():
        if st not in cent:
            continue
        x, y = cent[st]
        r = 2.2 * math.sqrt(n)
        for k in range(n):
            a = k * 2.399963                          # golden-angle spiral so districts fan out from the centroid
            d = r * math.sqrt((k + 0.5) / n)
            pts.append((x + d * math.cos(a), -(y + d * math.sin(a))))
            ids.append(f'{st}-{k + 1}')
    lay = ED.hex_layout(pts, ids)
    return lay
