"""Elections data pack: downloaded once on first use, like the language model.

What it fetches (all from GitHub, so it works wherever Sanjaya can reach GitHub):

  * Constituency boundaries from DataMeet (CC BY 2.5 India / CC0):
      - Assembly constituencies (India_AC shapefile, scraped from the ECI)
      - Lok Sabha constituencies (2019, simplified)
  * Candidate-level results:
      - TCPD Lok Dhaba archive (Trivedi Centre for Political Data, Ashoka University):
        all assembly elections to May 2023 and Lok Sabha to 2019
      - in-rolls/eci_results (from ECI statistical reports, TCPD layout):
        Lok Sabha 2024 and assemblies November 2023 to May 2026

The country and state outlines are NOT part of the pack: Sanjaya already ships the
Survey of India outline (static/data/india_outline_soi.geojson) and every India
map is drawn inside it.

Output (folder election_data/, git-ignored):
  elections.sqlite3          elections, seats, party totals
  geo/ac_<State>.json        simplified assembly constituencies + hex layout
  geo/pc.json                simplified Lok Sabha constituencies + hex layout
  manifest.json              what was built, when, from which sources
"""
import csv
import difflib
import gzip
import io
import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

import geo_shapes as G

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'election_data'
RAW = DATA / 'raw'
GEO = DATA / 'geo'
DB = DATA / 'elections.sqlite3'
MANIFEST = DATA / 'manifest.json'
PACK_VERSION = 1

DM = 'https://raw.githubusercontent.com/datameet/maps/master/'
TCPD = 'https://raw.githubusercontent.com/tcpd/tcpd-ld-data-archive/main/downloads/All_States/'
INR = 'https://raw.githubusercontent.com/in-rolls/eci_results/main/data/release/'

SOURCES = [
    # (file name, url, approximate MB, what, licence)
    ('India_AC.shp', DM + 'assembly-constituencies/India_AC.shp', 6.3, 'Assembly constituency boundaries', 'DataMeet, CC BY 2.5 India'),
    ('India_AC.dbf', DM + 'assembly-constituencies/India_AC.dbf', 5.7, 'Assembly constituency attributes', 'DataMeet, CC BY 2.5 India'),
    ('india_pc_2019_simplified.geojson', DM + 'parliamentary-constituencies/india_pc_2019_simplified.geojson', 1.9, 'Lok Sabha constituency boundaries', 'DataMeet / Arun Ganesh, CC0'),
    ('All_States_AE.csv.gz', TCPD + 'All_States_AE.csv.gz', 17.2, 'Assembly results to May 2023', '"TCPD Indian Elections Data v2.0", Trivedi Centre for Political Data, Ashoka University (free and open use, cite)'),
    ('All_States_GE.csv.gz', TCPD + 'All_States_GE.csv.gz', 3.3, 'Lok Sabha results to 2019', '"TCPD Indian Elections Data v2.0", Trivedi Centre for Political Data, Ashoka University (free and open use, cite)'),
    ('AE_2023_2026.csv.gz', INR + 'AE_2023_2026.csv.gz', 1.0, 'Assembly results, Nov 2023 to May 2026', 'in-rolls/eci_results from ECI reports, MIT'),
    ('GE_2024.csv.gz', INR + 'GE_2024.csv.gz', 0.3, 'Lok Sabha 2024 results', 'in-rolls/eci_results from ECI reports, MIT'),
]
ATTRIBUTION = ('Results: TCPD Lok Dhaba (Trivedi Centre for Political Data, Ashoka University) and '
               'in-rolls/eci_results, both from Election Commission of India statistical reports. '
               'Constituency maps: DataMeet community maps. India boundary: Survey of India.')

FIRST_YEAR = 2008      # constituencies changed with the 2008 delimitation; older results don't map

# Shapefile state names -> TCPD state keys.
SHP_STATE = {
    'ANDHRA PRADESH': 'Andhra_Pradesh', 'ARUNACHAL PRADESH': 'Arunachal_Pradesh', 'ASSAM': 'Assam', 'BIHAR': 'Bihar',
    'CHHATTISGARH': 'Chhattisgarh', 'DELHI': 'Delhi', 'GOA': 'Goa', 'GUJARAT': 'Gujarat', 'HARYANA': 'Haryana',
    'HIMACHAL PRADESH': 'Himachal_Pradesh', 'JAMMU & KASHMIR': 'Jammu_&_Kashmir', 'JHARKHAND': 'Jharkhand',
    'KARNATAKA': 'Karnataka', 'KERALA': 'Kerala', 'MADHYA PRADESH': 'Madhya_Pradesh', 'MAHARASHTRA': 'Maharashtra',
    'MANIPUR': 'Manipur', 'MEGHALAYA': 'Meghalaya', 'MIZORAM': 'Mizoram', 'NAGALAND': 'Nagaland', 'ORISSA': 'Odisha',
    'PUDUCHERRY': 'Puducherry', 'PUNJAB': 'Punjab', 'RAJASTHAN': 'Rajasthan', 'SIKKIM': 'Sikkim',
    'TAMIL NADU': 'Tamil_Nadu', 'TRIPURA': 'Tripura', 'UTTAR PRADESH': 'Uttar_Pradesh', 'UTTARKHAND': 'Uttarakhand',
    'UTTARAKHAND': 'Uttarakhand', 'WEST BENGAL': 'West_Bengal',
}
STATE_ALIASES = {'Orissa': 'Odisha', 'Pondicherry': 'Puducherry', 'Uttaranchal': 'Uttarakhand', 'NCT_of_Delhi': 'Delhi'}


def label(key):
    return key.replace('_', ' ').replace(' &', ' and')


def norm_state(s):
    s = (s or '').strip().replace(' ', '_')
    return STATE_ALIASES.get(s, s)


def norm_name(s):
    s = (s or '').lower().replace('(sc)', '').replace('(st)', '').replace('&', ' ')
    s = re.sub(r'\band\b', ' ', s)
    return re.sub(r'[^a-z]', '', s)


# ---------------------------------------------------------------- status and job
_job = {'state': 'idle', 'step': '', 'done': 0, 'total': 0, 'error': '', 'started': None}
_lock = threading.Lock()


def manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding='utf-8'))
    except Exception:
        return None


def status():
    m = manifest()
    with _lock:
        job = dict(_job)
    ready = bool(m and m.get('version') == PACK_VERSION and DB.exists())
    return {'ready': ready, 'manifest': m, 'job': job,
            'download_mb': int(round(sum(s[2] for s in SOURCES))),
            'sources': [{'what': s[3], 'licence': s[4], 'url': s[1]} for s in SOURCES],
            'attribution': ATTRIBUTION}


def _set(**kw):
    with _lock:
        _job.update(kw)


def start(fetch_bytes):
    """Begin downloading and building in the background. Safe to call twice."""
    with _lock:
        if _job['state'] == 'running':
            return False
        _job.update(state='running', step='Starting', done=0, total=len(SOURCES) + 4, error='', started=time.time())
    threading.Thread(target=_run, args=(fetch_bytes,), daemon=True).start()
    return True


def _run(fetch_bytes):
    try:
        build(fetch_bytes)
        _set(state='done', step='Ready')
    except Exception as e:  # report, never crash the server
        _set(state='failed', error=f'{type(e).__name__}: {e}')


# ---------------------------------------------------------------- build
def build(fetch_bytes=None, raw_dir=None):
    raw = Path(raw_dir) if raw_dir else RAW
    raw.mkdir(parents=True, exist_ok=True)
    GEO.mkdir(parents=True, exist_ok=True)
    for i, (name, url, mb, what, _lic) in enumerate(SOURCES):
        p = raw / name
        _set(step=f'Downloading {what} (~{mb} MB)', done=i)
        if p.exists() and p.stat().st_size > 0:
            continue
        if not fetch_bytes:
            raise RuntimeError(f'{name} is missing and no downloader was given')
        data = fetch_bytes(url, timeout=600)
        if not data or len(data) < 1000 or data[:15].lower().startswith(b'<!doctype html') or data[:6].lower() == b'<html>':
            raise RuntimeError(f'Download of {what} failed (GitHub may be rate-limiting; try again in a few minutes)')
        tmp = p.with_suffix(p.suffix + '.part')
        tmp.write_bytes(data)
        tmp.replace(p)
    n = len(SOURCES)
    _set(step='Reading results', done=n)
    elections, seats = read_results(raw)
    _set(step='Simplifying assembly constituency maps', done=n + 1)
    ac_states = build_ac_geo(raw, seats)
    _set(step='Simplifying Lok Sabha constituency maps', done=n + 2)
    build_pc_geo(raw)
    _set(step='Writing the elections database', done=n + 3)
    write_db(elections, seats)
    MANIFEST.write_text(json.dumps({
        'version': PACK_VERSION, 'built': time.strftime('%Y-%m-%d %H:%M'), 'elections': len(elections),
        'ac_states': ac_states, 'attribution': ATTRIBUTION,
        'sources': [{'file': s[0], 'url': s[1], 'licence': s[4]} for s in SOURCES]}, indent=1), encoding='utf-8')
    return len(elections)


def _num(x):
    try:
        return float(x) if x not in ('', None) else None
    except ValueError:
        return None


def _rows(path):
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace', newline='') as f:
        yield from csv.DictReader(f)


def read_results(raw):
    """Candidate rows -> elections and seats (winner, runner-up, totals) for general elections since 2008."""
    groups = {}   # (kind, state, year) -> {no: [candidate rows]}
    meta = {}
    files = [('AE', raw / 'All_States_AE.csv.gz'), ('GE', raw / 'All_States_GE.csv.gz'),
             ('AE', raw / 'AE_2023_2026.csv.gz'), ('GE', raw / 'GE_2024.csv.gz')]
    for kind, path in files:
        for r in _rows(path):
            if str(r.get('Poll_No', '0')).split('.')[0] not in ('0', ''):
                continue                                   # by-elections are not general results
            year = int(float(r['Year'] or 0))
            if year < FIRST_YEAR:
                continue
            state = norm_state(r['State_Name'])
            key = (kind, 'IN' if kind == 'GE' else state, year)
            no = int(float(r['Constituency_No'] or 0))
            seat_key = (state, no) if kind == 'GE' else no
            groups.setdefault(key, {}).setdefault(seat_key, []).append(r)
            meta.setdefault(key, int(float(r.get('month') or 0)))
    elections, seats = [], []
    for (kind, state, year), cons in groups.items():
        eid = f'GE-{year}' if kind == 'GE' else f'AE-{state}-{year}'
        n_seats = 0
        for seat_key, cands in cons.items():
            cands.sort(key=lambda c: int(float(c['Position'] or 999)))
            w = cands[0]
            if int(float(w['Position'] or 0)) != 1:
                continue
            n_seats += 1
            ru = next((c for c in cands[1:] if c['Party'] != 'NOTA'), None)
            st = seat_key[0] if kind == 'GE' else state
            no = seat_key[1] if kind == 'GE' else seat_key
            parties = {}
            for c in cands:
                parties[c['Party']] = parties.get(c['Party'], 0) + int(_num(c['Votes']) or 0)
            seats.append({
                'election': eid, 'state': st, 'no': no, 'name': (w['Constituency_Name'] or '').strip().title(),
                'type': w.get('Constituency_Type') or '', 'winner': (w['Candidate'] or '').strip().title(),
                'party': w['Party'], 'votes': int(_num(w['Votes']) or 0),
                'runner': (ru['Candidate'] or '').strip().title() if ru else '', 'runner_party': ru['Party'] if ru else '',
                'runner_votes': int(_num(ru['Votes']) or 0) if ru else 0,
                'valid': int(_num(w['Valid_Votes']) or 0), 'electors': int(_num(w['Electors']) or 0),
                'margin': int(_num(w['Margin']) or 0), 'margin_pct': _num(w['Margin_Percentage']),
                'turnout': _num(w['Turnout_Percentage']), 'n_cand': len([c for c in cands if c['Party'] != 'NOTA']),
                'party_votes': json.dumps(parties, separators=(',', ':')),
            })
        elections.append({'id': eid, 'kind': kind, 'state': state, 'year': year, 'month': meta[(kind, state, year)], 'seats': n_seats})
    return elections, seats


def write_db(elections, seats):
    tmp = DB.with_suffix('.tmp')
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript('''
      CREATE TABLE elections(id TEXT PRIMARY KEY, kind TEXT, state TEXT, year INT, month INT, seats INT);
      CREATE TABLE seats(election TEXT, state TEXT, no INT, name TEXT, type TEXT, winner TEXT, party TEXT, votes INT,
        runner TEXT, runner_party TEXT, runner_votes INT, valid INT, electors INT, margin INT, margin_pct REAL,
        turnout REAL, n_cand INT, party_votes TEXT);
      CREATE INDEX seats_e ON seats(election);''')
    con.executemany('INSERT INTO elections VALUES(:id,:kind,:state,:year,:month,:seats)', elections)
    con.executemany('INSERT INTO seats VALUES(:election,:state,:no,:name,:type,:winner,:party,:votes,:runner,:runner_party,'
                    ':runner_votes,:valid,:electors,:margin,:margin_pct,:turnout,:n_cand,:party_votes)', seats)
    con.commit()
    con.close()
    tmp.replace(DB)


# ---------------------------------------------------------------- geometry
def hex_layout(points, ids):
    """Equal-area hex cartogram: every seat gets one hexagon near its true position.

    points: [(x, y)] projected centroids; returns {id: [col, row]} on a pointy-top grid
    (odd rows shifted right by half a cell)."""
    n = len(points)
    if not n:
        return {}
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = sum(xs) / n, sum(ys) / n
    w, h = (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0
    # Spacing so that roughly n hexes cover the occupied area (centroids fill ~55% of the bbox).
    d = math.sqrt(w * h * 0.55 / n / 0.866) or 1.0
    rows = int(h / (d * 0.866)) + 6
    cols = int(w / d) + 6
    x0, y0 = min(xs) - 3 * d, max(ys) + 3 * d

    def cell_xy(c, r):
        return x0 + (c + (0.5 if r % 2 else 0)) * d, y0 - r * d * 0.866

    taken = set()
    order = sorted(range(n), key=lambda i: -math.hypot(xs[i] - cx, ys[i] - cy))   # border first keeps the outline
    out = {}
    for i in order:
        c0 = int(round((xs[i] - x0) / d))
        r0 = int(round((y0 - ys[i]) / (d * 0.866)))
        best, best_d = None, None
        for rad in range(0, max(rows, cols)):
            for r in range(r0 - rad, r0 + rad + 1):
                for c in range(c0 - rad, c0 + rad + 1):
                    if (c, r) in taken or max(abs(r - r0), abs(c - c0)) != rad:
                        continue
                    hx, hy = cell_xy(c, r)
                    dd = (hx - xs[i]) ** 2 + (hy - ys[i]) ** 2
                    if best_d is None or dd < best_d:
                        best, best_d = (c, r), dd
            if best is not None and rad >= 1:
                break
        taken.add(best)
        out[ids[i]] = list(best)
    # Normalise to start at 0,0 (keeping row parity so the odd-row offset stays right).
    mc = min(v[0] for v in out.values())
    mr = min(v[1] for v in out.values())
    mr -= mr % 2
    return {k: [v[0] - mc, v[1] - mr] for k, v in out.items()}


def _proj(lon, lat, lat0):
    return lon * math.cos(math.radians(lat0)), lat


def build_ac_geo(raw, seats):
    rows = G.read_dbf((raw / 'India_AC.dbf').read_bytes())
    shapes = G.read_shp((raw / 'India_AC.shp').read_bytes())
    by_state = {}
    for row, rings in zip(rows, shapes):
        if not row or not rings:
            continue
        st = SHP_STATE.get((row.get('ST_NAME') or '').strip().upper())
        if not st:
            continue
        no = int(row.get('AC_NO') or 0)
        if st == 'Andhra_Pradesh':            # pre-2014 numbering: 1-119 became Telangana, 120-294 are AP 1-175
            if no <= 119:
                st = 'Telangana'
            else:
                no -= 119
        ent = by_state.setdefault(st, {}).setdefault(no, {'no': no, 'name': (row.get('AC_NAME') or '').strip().title(), 'rings': []})
        ent['rings'].extend(rings)
    # Latest result names per state, to check the map matches the current delimitation.
    latest = {}
    for s in seats:
        if s['election'].startswith('AE-'):
            y = int(s['election'].rsplit('-', 1)[1])
            if y >= latest.get(s['state'], (0, {}))[0]:
                if y > latest.get(s['state'], (0, {}))[0]:
                    latest[s['state']] = (y, {})
                latest[s['state']][1][s['no']] = s['name']
    summary = {}
    for st, acs in by_state.items():
        items = []
        for no in sorted(acs):
            ent = acs[no]
            rings = ent['rings']
            c = G.centroid(rings)
            items.append({'no': no, 'name': ent['name'], 'c': [round(c[0], 4), round(c[1], 4)] if c else None,
                          'rings': G.compact(rings, tol=0.0025 if len(acs) > 100 else 0.0015)})
        lat0 = sum(i['c'][1] for i in items if i['c']) / max(1, len([i for i in items if i['c']]))
        pts = [_proj(i['c'][0], i['c'][1], lat0) for i in items if i['c']]
        ids = [i['no'] for i in items if i['c']]
        hexes = hex_layout(pts, ids)
        names = latest.get(st, (0, {}))[1]
        matched = sum(1 for i in items if names.get(i['no']) and _same_place(names[i['no']], i['name']))
        match = round(matched / max(1, len(names)), 3) if names else None
        GEO.mkdir(parents=True, exist_ok=True)
        (GEO / f'ac_{st}.json').write_text(json.dumps({
            'state': st, 'label': label(st), 'lat0': round(lat0, 3), 'items': items,
            'hex': {str(k): v for k, v in hexes.items()}, 'name_match_latest': match,
            'source': 'DataMeet assembly constituencies (scraped from ECI), CC BY 2.5 India'}, separators=(',', ':')), encoding='utf-8')
        summary[st] = {'constituencies': len(items), 'name_match_latest': match}
    return summary


def _same_place(a, b):
    """Same constituency under a different transliteration (Chaprauli / Chhaprauli)?"""
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def build_pc_geo(raw):
    gj = json.loads((raw / 'india_pc_2019_simplified.geojson').read_text(encoding='utf-8'))
    items = []
    for f in gj['features']:
        p = f.get('properties') or {}
        rings = G.geojson_rings(f.get('geometry'))
        c = G.centroid(rings)
        items.append({'state': norm_state(p.get('st_name') or ''), 'no': int(p.get('pc_no') or 0),
                      'name': (p.get('pc_name') or '').strip(), 'c': [round(c[0], 4), round(c[1], 4)] if c else None,
                      'rings': G.compact(rings, tol=0.006)})
    lat0 = 22.0
    keep = [i for i in items if i['c']]
    pts = [_proj(i['c'][0], i['c'][1], lat0) for i in keep]
    ids = [f"{i['state']}|{i['no']}" for i in keep]
    hexes = hex_layout(pts, ids)
    (GEO / 'pc.json').write_text(json.dumps({'lat0': lat0, 'items': items, 'hex': hexes,
                                             'source': 'DataMeet Lok Sabha constituencies 2019 (Arun Ganesh), CC0'},
                                            separators=(',', ':')), encoding='utf-8')
    return len(items)
