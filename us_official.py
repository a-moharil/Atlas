"""2026 vote counts read from each state's own election-results site (all 50 states and DC).

Election results are public records: every state publishes its count for free. This module reads those counts and
nothing else. No news agency's data or race calls are used. A state count never calls a race; calls come from
Wikipedia's results tables (see us_live) and are kept only when the state's count agrees on who is ahead.

States publish in different ways, so each entry in SOURCES says where to look:
  feeds  data files whose format is known (California's API, Arizona's JSON export, Minnesota's text files,
         North Carolina's results zip, Florida's election-night file);
  page   the state's official results page. When a feed is missing or fails, the page is read for links to
         the results system behind it (Clarity, Enhanced Voting, or a CSV/JSON/ZIP file for this election),
         and as a last resort for results tables on the page itself.
A state whose page offers nothing readable is listed as "open the state's page" with a link.

  ev     Enhanced Voting's public results API (Washington, Utah, Virginia, Georgia, Arizona):
         <site>/results/public/api/elections/<state>/<yyyymmdd>/data, whose metadata also says whether the
         results are official (certified).
Any entry can be corrected without code: put {"XX": {"page": "...", "feeds": ["..."]}} in
election_data/us/state_sources.json.

Readers: Clarity summary.json; a general JSON reader (any object holding a list of candidates with votes);
delimited text (comma, tab, semicolon, pipe) with columns found by name or given per state; ZIP archives of
those; HTML results tables.
"""
from __future__ import annotations

import csv
import html as _html
import io
import json
import re
import threading
import time
import urllib.parse
import zipfile
from html.parser import HTMLParser

from us_elections_data import OUT, STATES

DATES = {2026: '2026-11-03'}
TTL = 30 * 60
AT_LARGE = {'AK', 'DE', 'ND', 'SD', 'VT', 'WY'}
MN_COLS = {'contest': 4, 'district': 5, 'candidate': 7, 'party': 10, 'reporting': 11, 'precincts': 12, 'votes': 13, 'county': 1}
CA_HOUSE = 52

SOURCES = {
    'AL': {'page': 'https://www.sos.alabama.gov/alabama-votes/voter/election-information'},
    'AK': {'page': 'https://www.elections.alaska.gov/election-results/'},
    'AZ': {'page': 'https://azsos.gov/pressazsosgov', 'ev': ['https://results.arizona.vote', 'arizona'],
           'feeds': ['https://app.enhancedvoting.com/cdn/results/Arizona/export-{mmddyy}GeneralElection.json']},
    'AR': {'page': 'https://www.sos.arkansas.gov/elections/research/election-results'},
    'CA': {'page': 'https://electionresults.sos.ca.gov/',
           'feeds': ['https://api.sos.ca.gov/returns/governor'] +
                    [f'https://api.sos.ca.gov/returns/us-rep/district/{n}' for n in range(1, CA_HOUSE + 1)]},
    'CO': {'page': 'https://www.coloradosos.gov/pubs/elections/Results/'},
    'CT': {'page': 'https://electionhistory.ct.gov/'},
    'DE': {'page': 'https://elections.delaware.gov/results/'},
    'DC': {'page': 'https://electionresults.dcboe.org/'},
    'FL': {'page': 'https://results.elections.myflorida.com/',
           'feeds': ['https://fldoselectionfiles.elections.myflorida.com/enightfilespublic/{yyyymmdd}_ElecResultsFL.txt'],
           'columns': {'contest': 'OfficeDesc', 'district': 'Juris1num', 'first': 'CanNameFirst', 'last': 'CanNameLast',
                       'party': 'PartyCode', 'votes': 'CanVotes', 'reporting': 'PrecinctsReporting', 'precincts': 'Precincts'}},
    'GA': {'page': 'https://results.sos.ga.gov/', 'ev': ['https://results.sos.ga.gov', 'georgia'],
           'feeds': ['https://app.enhancedvoting.com/cdn/results/Georgia/export-{mmddyy}GeneralElection.json']},
    'HI': {'page': 'https://elections.hawaii.gov/election-results/'},
    'ID': {'page': 'https://voteidaho.gov/election-results/'},
    'IL': {'page': 'https://www.elections.il.gov/electionoperations/ElectionVoteTotals.aspx'},
    'IN': {'page': 'https://enr.indianavoters.in.gov/'},
    'IA': {'page': 'https://sos.iowa.gov/elections/results/'},
    'KS': {'page': 'https://sos.ks.gov/elections/election-results.html'},
    'KY': {'page': 'https://elect.ky.gov/results/'},
    'LA': {'page': 'https://voterportal.sos.la.gov/graphical'},
    'ME': {'page': 'https://www.maine.gov/sos/cec/elec/results/'},
    'MD': {'page': 'https://elections.maryland.gov/elections/results_data/'},
    'MA': {'page': 'https://electionstats.state.ma.us/'},
    'MI': {'page': 'https://mielections.us/election/results/'},
    'MN': {'page': 'https://electionresults.sos.mn.gov/',
           'feeds': ['https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/ushouse.txt',
                     'https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/ussenate.txt',
                     'https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/allracesbycounty.txt'],
           'columns': MN_COLS},
    'MS': {'page': 'https://www.sos.ms.gov/elections-voting/election-results'},
    'MO': {'page': 'https://enr.sos.mo.gov/'},
    'MT': {'page': 'https://electionresults.mt.gov/'},
    'NE': {'page': 'https://electionresults.nebraska.gov/'},
    'NV': {'page': 'https://silverstateelection.nv.gov/'},
    'NH': {'page': 'https://www.sos.nh.gov/elections/elections/election-results'},
    'NJ': {'page': 'https://www.nj.gov/state/elections/election-night-results.shtml'},
    'NM': {'page': 'https://electionresults.sos.nm.gov/'},
    'NY': {'page': 'https://nyenr.elections.ny.gov/'},
    'NC': {'page': 'https://er.ncsbe.gov/',
           'feeds': ['https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{yyyy_mm_dd}/results_pct_{yyyymmdd}.zip']},
    'ND': {'page': 'https://results.sos.nd.gov/'},
    'OH': {'page': 'https://liveresults.ohiosos.gov/'},
    'OK': {'page': 'https://results.okelections.gov/'},
    'OR': {'page': 'https://results.oregonvotes.gov/'},
    'PA': {'page': 'https://www.electionreturns.pa.gov/'},
    'RI': {'page': 'https://elections.ri.gov/elections/results/'},
    'SC': {'page': 'https://www.scvotes.gov/election-results'},
    'SD': {'page': 'https://electionresults.sd.gov/'},
    'TN': {'page': 'https://sos.tn.gov/elections/results'},
    'TX': {'page': 'https://electionresults.sos.state.tx.us/results.html'},
    'UT': {'page': 'https://electionresults.utah.gov/', 'ev': ['https://electionresults.utah.gov', 'utah']},
    'VT': {'page': 'https://electionarchive.vermont.gov/'},
    'VA': {'page': 'https://enr.elections.virginia.gov/', 'ev': ['https://enr.elections.virginia.gov', 'virginia']},
    'WA': {'page': 'https://results.votewa.gov/', 'ev': ['https://results.votewa.gov', 'washington']},
    'WV': {'page': 'https://sos.wv.gov/elections/Pages/ElectionResults.aspx'},
    'WI': {'page': 'https://elections.wi.gov/elections/election-results'},
    'WY': {'page': 'https://sos.wyo.gov/Elections/State/Results.aspx'},
}

CLARITY = re.compile(r'https?://results\.enr\.clarityelections\.com/([A-Z]{2})/(?:([A-Za-z_\-]+)/)?(\d{4,7})', re.I)
ENHANCED = re.compile(r'https?://app\.enhancedvoting\.com/cdn/results/[^"\'\s<>]+?\.json', re.I)
DATAFILE = re.compile(r'href=["\']([^"\']+?\.(?:csv|txt|json|zip|xml|tsv))["\']', re.I)
SKIP_NAME = re.compile(r'write[- ]?ins?\b|under\s*votes?|over\s*votes?|^blank|^total|registered voters|ballots cast|^times (over|blank)', re.I)


# ------------------------------------------------------------------ contests and parties
def party_code(text):
    t = re.sub(r'[^a-z ]', ' ', (text or '').lower()).strip()
    if not t:
        return 'O'
    if re.search(r'\b(dem|democrat|democratic|dfl|d)\b', t):
        return 'D'
    if re.search(r'\b(rep|republican|gop|r)\b', t):
        return 'R'
    if re.search(r'\b(ind|independent|npa|no party|unaffiliated|una|np|nonpartisan|non partisan|i)\b', t):
        return 'I'
    return 'O'


def classify(title, state):
    """Contest title -> (office, seat, special), or None for any other contest."""
    t = re.sub(r'\s+', ' ', (title or '').lower())
    if not t or re.search(r'\bprimary\b|delegate|committee|\bstate (senat|rep|house)|precinct|board|council', t):
        return None
    special = bool(re.search(r'unexpired|special|short term|vacancy', t))
    if re.search(r'governor\s*(&|and)\s*l(ieu)?t', t):
        return 'G', '', special
    if re.search(r'l(ieu)?t\.?\s*(enant\s*)?gov', t):
        return None
    if re.search(r'\bgovernor\b', t):
        return 'G', '', special
    if re.search(r'(u\.?\s?s\.?|united states|federal)\s*senat', t):
        return 'S', '', special
    if re.search(r'(u\.?\s?s\.?|united states)\s*(house|rep|congress)|congressional|representative in congress|member of congress', t):
        m = re.search(r'district\s*(?:no\.?\s*|#\s*)?(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:congressional\s+)?district|\bcd\s*-?\s*(\d{1,2})\b', t)
        if m:
            return 'H', str(int(next(g for g in m.groups() if g))), special
        if 'at large' in t.replace('-', ' ') or state in AT_LARGE:
            return 'H', '1', special
    return None


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r'^\s*(-?\d[\d,]*(?:\.\d+)?)\s*%?\s*$', str(v or ''))
    return float(m.group(1).replace(',', '')) if m else None


# ------------------------------------------------------------------ readers: each returns a list of contests
# contest = {'title', 'cands': {(name, party): votes}, 'reporting': (counted, total) or None, 'pct': float or None}
def _contest(title):
    return {'title': title, 'cands': {}, 'reporting': None, 'pct': None}


def _add(c, name, party, votes):
    name = re.sub(r'\s+', ' ', str(name or '')).strip()
    if not name or SKIP_NAME.search(name) or votes is None:
        return
    k = (name, party_code(party))
    c['cands'][k] = c['cands'].get(k, 0) + votes


def read_clarity(payload):
    out = []
    for item in payload if isinstance(payload, list) else payload.get('Contests', []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or 'C' not in item:
            continue
        c = _contest(item.get('C'))
        names, parties, votes = item.get('CH') or [], item.get('P') or [], item.get('V') or []
        for i, n in enumerate(names):
            _add(c, n, parties[i] if i < len(parties) else '', _num(votes[i]) if i < len(votes) else None)
        if _num(item.get('PR')) is not None and _num(item.get('TP')):
            c['reporting'] = (_num(item['PR']), _num(item['TP']))
        out.append(c)
    return out


NAME_KEYS = ('Name', 'name', 'candidateName', 'CandidateName', 'ballotName', 'BallotName', 'choiceName', 'ChoiceName',
             'Candidate', 'candidate', 'Choice', 'choice', 'fullName', 'FullName', 'displayName', 'title')
PARTY_KEYS = ('Party', 'party', 'partyCode', 'PartyCode', 'partyName', 'PartyName', 'politicalParty', 'partyAbbreviation')
TITLE_KEYS = ('raceTitle', 'RaceTitle', 'contestName', 'ContestName', 'ballotItemName', 'BallotItemName', 'officeName', 'OfficeName',
              'raceName', 'RaceName', 'Contest', 'contest', 'Race', 'race', 'Office', 'office', 'title', 'Title', 'name', 'Name')


def _votes_of(d):
    for k in ('Votes', 'votes', 'voteCount', 'VoteCount', 'totalVotes', 'TotalVotes', 'ballotsCast', 'BallotsCast', 'count', 'Count'):
        if k in d and _num(d[k]) is not None:
            return _num(d[k])
    for k, v in d.items():
        if 'vote' in k.lower() and 'percent' not in k.lower() and 'pct' not in k.lower() and _num(v) is not None:
            return _num(v)
    return None


def _cand_name(d):
    for k in NAME_KEYS:
        if isinstance(d.get(k), str) and d[k].strip():
            return d[k]
    first = next((d[k] for k in ('firstName', 'FirstName', 'first') if isinstance(d.get(k), str)), '')
    last = next((d[k] for k in ('lastName', 'LastName', 'last') if isinstance(d.get(k), str)), '')
    return f'{first} {last}'.strip()


def _cand_party(d):
    for k in PARTY_KEYS:
        v = d.get(k)
        if isinstance(v, dict):
            v = next((v[x] for x in ('abbreviation', 'code', 'name', 'Name') if isinstance(v.get(x), str)), '')
        if isinstance(v, str):
            return v
    return ''


def read_json(payload):
    """Any object holding a list of candidate-like objects (a name and a vote count) is a contest."""
    out = []

    def walk(o, ctx):
        if isinstance(o, list):
            for x in o:
                walk(x, ctx)
            return
        if not isinstance(o, dict):
            return
        title = next((o[k] for k in TITLE_KEYS if isinstance(o.get(k), str) and o[k].strip()), None)
        found = False
        for k, v in o.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and \
                    sum(1 for x in v if _cand_name(x) and _votes_of(x) is not None) >= max(1, len(v) // 2):
                c = _contest(title or ctx)
                for x in v:
                    _add(c, _cand_name(x), _cand_party(x), _votes_of(x))
                rep = o.get('Reporting') or o.get('reporting') or o.get('precinctsReportingText')
                m = re.search(r'([\d,]+)\s*of\s*([\d,]+)', str(rep or ''))
                if m:
                    c['reporting'] = (_num(m.group(1)), _num(m.group(2)))
                elif _num(o.get('precinctsReporting')) is not None and _num(o.get('precinctsTotal') or o.get('totalPrecincts')):
                    c['reporting'] = (_num(o['precinctsReporting']), _num(o.get('precinctsTotal') or o.get('totalPrecincts')))
                if c['title']:
                    out.append(c)
                found = True
        for k, v in o.items():
            if isinstance(v, (dict, list)) and not found:
                walk(v, title or ctx)
            elif isinstance(v, dict):
                walk(v, title or ctx)

    walk(payload, None)
    return out


def _find(header, *pats):
    for p in pats:
        for j, h in enumerate(header):
            if re.fullmatch(p, h.strip(), re.I):
                return j
    return None


def read_table(text, columns=None):
    """Delimited text with one row per candidate (per county or precinct, summed here)."""
    csv.field_size_limit(50_000_000)
    lines = text.splitlines()
    if not lines:
        return []
    sample = '\n'.join(lines[:20])
    delim = max(['\t', ';', '|', ','], key=lambda d: sample.count(d))
    rows = csv.reader(io.StringIO(text), delimiter=delim)
    cols = dict(columns or {})
    named = cols and all(isinstance(v, str) for v in cols.values())
    header = None
    if not cols or named:
        header = next(rows, [])
        if named:
            cols = {k: _find(header, re.escape(v)) for k, v in cols.items()}
        else:
            cols = {'contest': _find(header, r'contest( ?name| ?title)?', r'race( ?name)?', r'office( ?(name|desc|title))?', r'contest_name'),
                    'district': _find(header, r'district', r'juris1num'),
                    'candidate': _find(header, r'candidate( ?name)?', r'choice( ?name)?', r'name', r'ballot ?name'),
                    'party': _find(header, r'(choice )?party( ?code| ?abbr\w*)?', r'party( ?name)?', r'party_code'),
                    'votes': _find(header, r'total ?votes', r'votes', r'can ?votes', r'vote ?count', r'total'),
                    'precinct': _find(header, r'precinct( ?name)?'),
                    'first': _find(header, r'(can ?)?(name ?)?first( ?name)?'), 'last': _find(header, r'(can ?)?(name ?)?last( ?name)?')}
        if cols.get('contest') is None or cols.get('votes') is None or (cols.get('candidate') is None and cols.get('last') is None):
            return []
    by = {}
    total_rows = set()
    raw = []
    for r in rows:
        g = lambda k: r[cols[k]].strip() if cols.get(k) is not None and cols[k] < len(r) else ''
        title = g('contest')
        if not title or not re.search(r'senat|congress|represent|house|governor|\bcd\b', title, re.I):
            continue
        d = g('district')
        if d and not re.search(r'district|\bcd\b', title, re.I) and re.fullmatch(r'\d{1,2}', d):
            title = f'{title} District {int(d)}'
        name = g('candidate') or f"{g('first')} {g('last')}".strip()
        pre = g('precinct')
        raw.append((title, name, g('party'), _num(g('votes')), pre, g('reporting'), g('precincts'), g('county')))
        if pre.lower() == 'total':
            total_rows.add(title)
    seen_rep = {}
    for title, name, party, votes, pre, rep, pcts, county in raw:
        if title in total_rows and pre.lower() != 'total':
            continue                                  # a file with both totals and precincts: totals only
        c = by.setdefault(title, _contest(title))
        _add(c, name, party, votes)
        if _num(rep) is not None and _num(pcts):
            seen_rep[(title, county)] = (_num(rep), _num(pcts))
    for (title, _), rp in seen_rep.items():
        a, b = by[title]['reporting'] or (0, 0)
        by[title]['reporting'] = (a + rp[0], b + rp[1])
    return list(by.values())


class _Tables(HTMLParser):
    """Results tables with the text just before each one (the contest title on most results pages)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.recent, self.cur, self.row, self.cell, self.depth = [], [], None, None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                title = next((t for t in reversed(self.recent) if len(t) > 3 and not re.search(r'reporting|updated', t, re.I)), '')
                rep = next((m for m in (re.search(r'reporting:?\s*([\d.]+)\s*%', t, re.I) for t in self.recent) if m), None)
                self.cur = {'title': title, 'rows': [], 'pct': float(rep.group(1)) if rep else None}
        elif self.cur is not None and tag == 'tr':
            self.row = []
        elif self.cur is not None and tag in ('td', 'th'):
            self.cell = []
        elif tag == 'caption' and self.cur is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == 'table' and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.cur:
                self.tables.append(self.cur); self.cur = None; self.recent = []
        elif self.cur is not None and tag in ('td', 'th') and self.cell is not None and self.row is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        elif self.cur is not None and tag == 'caption' and self.cell is not None:
            self.cur['title'] = ' '.join(''.join(self.cell).split()) or self.cur['title']; self.cell = None
        elif self.cur is not None and tag == 'tr' and self.row is not None:
            self.cur['rows'].append(self.row); self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.cur is None and data.strip():
            self.recent = (self.recent + [' '.join(data.split())])[-6:]


def read_html(text):
    p = _Tables()
    try:
        p.feed(text)
    except Exception:
        return []
    out = []
    for t in p.tables:
        rows = [r for r in t['rows'] if r]
        if len(rows) < 2:
            continue
        header = [h.lower() for h in rows[0]]
        cj = next((j for j, h in enumerate(header) if re.search(r'candidate|choice|name', h)), None)
        vj = next((j for j, h in enumerate(header) if re.search(r'votes|ballots cast|total', h) and '%' not in h and 'percent' not in h), None)
        pj = next((j for j, h in enumerate(header) if 'party' in h), None)
        if cj is None or vj is None:
            continue
        c = _contest(t['title'])
        c['pct'] = t.get('pct')
        for r in rows[1:]:
            if max(cj, vj) < len(r):
                _add(c, r[cj], r[pj] if pj is not None and pj < len(r) else '', _num(r[vj]))
        out.append(c)
    return out


def contests_from(blob, columns=None):
    """Detect the format of a downloaded file and read its contests."""
    if blob[:2] == b'PK':
        out = []
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                if info.filename.lower().endswith(('.txt', '.csv', '.tsv', '.json')) and info.file_size < 400_000_000:
                    out += contests_from(z.read(info), columns)
        return out
    if blob[:2] in (b'\xff\xfe', b'\xfe\xff') or blob[1:200:2].count(0) > 50:
        text = blob.decode('utf-16', errors='replace')
    else:
        text = blob.decode('utf-8-sig', errors='replace')
    text = text.replace('\x00', '')
    s = text.lstrip()[:1]
    if s in '{[':
        try:
            payload = json.loads(text)
        except ValueError:
            return []
        if isinstance(payload, list) and payload and isinstance(payload[0], dict) and 'C' in payload[0] and 'CH' in payload[0]:
            return read_clarity(payload)
        return read_json(payload)
    if s == '<':
        return read_html(text)
    return read_table(text, columns)


# ------------------------------------------------------------------ contests -> races
def races_from(contests, state, cycle, source):
    best = {}
    for c in contests:
        cls = classify(c['title'], state)
        if not cls or not c['cands']:
            continue
        office, seat, special = cls
        rows = sorted(([n, p, int(v)] for (n, p), v in c['cands'].items()), key=lambda x: -x[2])
        total = sum(x[2] for x in rows)
        for x in rows:
            x.append(round(100 * x[2] / total, 2) if total else None)
            x.append(0)
        lead = rows[0]
        run = rows[1] if len(rows) > 1 else None
        rid = {'H': f'H-{cycle}-{state}-{seat}', 'S': f'S-{cycle}-{state}-{seat}', 'G': f'G-{cycle}-{state}'}[office]
        if special and office != 'S':
            rid += '-special'
        rep = c.get('reporting')
        counted = round(100 * rep[0] / rep[1], 1) if rep and rep[1] else c.get('pct')
        race = {'id': rid, 'office': office, 'cycle': cycle, 'state': state, 'seat': seat, 'special': int(special), 'stage': 'general',
                'date': DATES.get(cycle), 'winner': None, 'winner_party': None,
                'leader': lead[0] if total else None, 'leader_party': lead[1] if total else None,
                'runner': run[0] if run else None, 'runner_party': run[1] if run else None,
                'winner_votes': lead[2] or None, 'runner_votes': run[2] if run else None, 'total': total or None,
                'margin_pct': round(lead[3] - run[3], 2) if run and total else None, 'unopposed': int(len(rows) == 1),
                'incumbent_party': None, 'cands': json.dumps(rows[:8]), 'called': 0, 'counted_pct': counted,
                'counted_basis': 'precincts' if counted is not None else None,
                'status_text': f"{STATES.get(state, state)}'s count", 'origin': 'state', 'source': source}
        key = (rid, special)
        if key not in best or (race['total'] or 0) > (best[key]['total'] or 0):
            best[key] = race
    return list(best.values())


# ------------------------------------------------------------------ fetching one state
def _fill(url, cycle):
    d = DATES[cycle]
    y, m, dd = d.split('-')
    return url.format(yyyymmdd=f'{y}{m}{dd}', yyyy_mm_dd=f'{y}_{m}_{dd}', mmddyy=f'{m}{dd}{y[2:]}', yyyy=y)


def _clarity_contests(base, getter):
    base = base.rstrip('/') + '/'
    ver = getter(base + 'current_ver.txt').decode('utf-8', 'replace').strip()
    if not re.fullmatch(r'\d{1,9}', ver):
        raise ValueError('Clarity did not return a version number')
    return read_clarity(json.loads(getter(f'{base}{ver}/json/en/summary.json').decode('utf-8')))


EV_LINK = re.compile(r'(https?://[a-z0-9.\-]+)/results/public/(?:api/elections/)?([a-z][a-z\-]+)', re.I)


def _ev_contests(base, slug, cycle, getter):
    """Enhanced Voting: <base>/results/public/api/elections/<slug>/<election>/data. Returns (contests, certified)."""
    root = f"{base.rstrip('/')}/results/public/api/elections/{slug}"
    d = DATES[cycle].replace('-', '')
    keys = [d]
    try:
        listing = json.loads(getter(root).decode('utf-8'))
        for k in re.findall(r'"(?:id|key|slug|electionId|electionKey|electionDate|date)"\s*:\s*"([^"]+)"', json.dumps(listing)):
            if any(t in k for t in (d, DATES[cycle], d[4:] + d[2:4])) and k not in keys:
                keys.append(k)
    except Exception:
        pass
    last = None
    for k in keys:
        try:
            data = json.loads(getter(f'{root}/{k}/data').decode('utf-8'))
        except Exception as exc:
            last = exc
            continue
        certified = None
        try:
            meta = json.loads(getter(f'{root}/{k}').decode('utf-8'))
            certified = bool(meta.get('isOfficialResults')) if isinstance(meta, dict) else None
        except Exception:
            pass
        items = data.get('ballotItems', data) if isinstance(data, dict) else data
        if isinstance(items, list):            # county-local copies of statewide contests carry a parentId: skip them
            items = [b for b in items if not (isinstance(b, dict) and b.get('parentId'))]
        return read_json(items), certified
    raise last or LookupError('no election found')


def discover(page_html, page_url, cycle):
    """Links on a state's results page that lead to this election's data."""
    links = []
    best = {}
    for m in CLARITY.finditer(page_html):
        st, county, eid = m.group(1).upper(), m.group(2) or '', int(m.group(3))
        if best.get((st, county), 0) < eid:
            best[(st, county)] = eid           # newest election per site: Clarity ids increase over time
    statewide = {st for st, county in best if not county}
    for (st, county), eid in sorted(best.items()):
        if county and st in statewide:
            continue                            # the state's own site already totals its counties
        links.append(('clarity', f"https://results.enr.clarityelections.com/{st}/{county + '/' if county else ''}{eid}/"))
    links += [('file', u) for u in dict.fromkeys(ENHANCED.findall(page_html))]
    for base, slug in dict.fromkeys(EV_LINK.findall(page_html)):
        if slug.lower() not in ('api', 'elections'):
            links.append(('ev', f'{base}|{slug.lower()}'))
    d = DATES[cycle].replace('-', '')
    tokens = (d, DATES[cycle], d[4:] + d[2:4], d[4:] + d[:4], DATES[cycle].replace('-', '_'))
    for href in DATAFILE.findall(page_html):
        u = urllib.parse.urljoin(page_url, _html.unescape(href)).replace('http://', 'https://', 1)
        if any(t in u for t in tokens):
            links.append(('file', u))
    seen, out = set(), []
    for k, u in links:
        if u not in seen:
            seen.add(u); out.append((k, u))
    return out[:30]


def read_state(state, cycle, getter, spec=None):
    spec = spec or SOURCES[state]
    page = _fill(spec['page'], cycle)
    contests, used, tried = [], [], []
    counties = {}                               # county-run sites (New Jersey): their counts add up
    county_sites = {'found': 0, 'read': 0}
    certified = [None]

    def note(url, outcome):
        tried.append({'url': url.split('|')[0], 'result': outcome[:160]})

    def take(kind, url):
        county = kind == 'clarity' and CLARITY.match(url).group(2)
        if county:
            county_sites['found'] += 1
        try:
            if kind == 'clarity':
                got = _clarity_contests(url, getter)
            elif kind == 'ev':
                base, slug = url.split('|')
                got, cert = _ev_contests(base, slug, cycle, getter)
                if cert is not None:
                    certified[0] = cert
            else:
                got = contests_from(getter(url), spec.get('columns'))
        except Exception as exc:
            note(url, str(exc) or type(exc).__name__)
            return
        if not any(classify(c['title'], state) for c in got):
            note(url, 'read, but no House, Senate or governor contests in it')
            return
        note(url, 'read')
        used.append(url.split('|')[0])
        if county:
            county_sites['read'] += 1
            for c in got:
                acc = counties.setdefault(c['title'], _contest(c['title']))
                for k, v in c['cands'].items():
                    acc['cands'][k] = acc['cands'].get(k, 0) + v
        else:
            contests.extend(got)

    if spec.get('ev'):
        take('ev', '|'.join(spec['ev']))
    if not used:
        for f in spec.get('feeds', []):
            take('file', _fill(f, cycle))
    if not used:
        text = ''
        try:
            text = getter(page).decode('utf-8', 'replace')
        except Exception as exc:
            note(page, str(exc) or type(exc).__name__)
        found = discover(text, page, cycle) if text else []
        for kind, url in found:
            take(kind, url)
        if not used and text:
            got = read_html(text) if re.search(str(cycle), text) else []
            if any(classify(c['title'], state) for c in got):
                contests += got; used.append(page); note(page, 'read (tables on the page)')
            else:
                note(page, 'opened, but it links to no results data Sanjaya can read' +
                     (' (the page is probably built by JavaScript)' if len(re.sub(r'<script.*?</script>|<[^>]+>', '', text, flags=re.S).split()) < 400 else ''))
    partial = county_sites['found'] and county_sites['read'] < county_sites['found']
    races = races_from(contests + list(counties.values()), state, cycle, used[0] if used else page)
    for r in races:
        if certified[0]:
            r['certified'] = 1
            r['status_text'] = f"{STATES.get(state, state)}'s certified result"
        if partial and r['source'] and CLARITY.match(r['source'] or ''):
            r['counted_pct'], r['counted_basis'] = None, None
            r['status_text'] = f"Partial: {county_sites['read']} of {county_sites['found']} county sites read"
    reached = any(t['result'].startswith(('read', 'opened')) for t in tried)
    status = 'partial' if races and partial else 'read' if races else ('none' if reached else 'failed')
    err = next((t['result'] for t in reversed(tried) if not t['result'].startswith('read')), None)
    return {'state': state, 'status': status, 'races': races, 'page': page, 'used': used[:5], 'tried': tried[-12:],
            'error': None if races and not partial else err, 'certified': bool(certified[0]) if races else False,
            'counties': county_sites if county_sites['found'] else None, 'fetched': time.time()}


# ------------------------------------------------------------------ all states, in the background
_lock = threading.Lock()
_jobs = {}


def sources():
    out = {k: dict(v) for k, v in SOURCES.items()}
    try:
        extra = json.loads((OUT / 'state_sources.json').read_text(encoding='utf-8'))
        for st, v in extra.items():
            if st in out and isinstance(v, dict):
                out[st].update({k: v[k] for k in ('page', 'feeds', 'columns', 'ev') if k in v})
    except (OSError, ValueError):
        pass
    return out


def _file(cycle):
    return OUT / f'state_counts_{cycle}.json'


def request(cycle, getter, force=False, only=None):
    """State counts for a cycle: cached answer now, a background re-read when stale (or forced)."""
    if cycle not in DATES:
        return {'races': [], 'states': {}, 'pending': False, 'step': '', 'fetched': None, 'enabled': False}
    now = time.time()
    with _lock:
        job = _jobs.get(cycle)
        if job is None:
            job = {'states': {}, 't': 0, 'running': False, 'step': ''}
            try:
                saved = json.loads(_file(cycle).read_text(encoding='utf-8'))
                job.update(states=saved['states'], t=saved['t'])
            except (OSError, ValueError, KeyError):
                pass
            _jobs[cycle] = job
        due = force or not job['states'] or now - job['t'] > TTL
        if due and not job['running']:
            job.update(running=True, step='Reading state results sites')
            todo = [s for s in sources().items() if not only or s[0] in only]

            def work():
                try:
                    for i, (st, spec) in enumerate(todo, 1):
                        with _lock:
                            job['step'] = f'Reading {STATES.get(st, st)} ({i} of {len(todo)})'
                        try:
                            res = read_state(st, cycle, getter, spec)
                        except Exception as exc:          # one state never stops the rest
                            res = {'state': st, 'status': 'failed', 'races': [], 'page': spec.get('page'), 'used': [], 'tried': [],
                                   'error': f'{type(exc).__name__}: {exc}'[:160], 'fetched': time.time()}
                        with _lock:
                            job['states'][st] = res
                    t = time.time()
                    with _lock:
                        job['t'] = t
                        snap = json.dumps({'t': t, 'states': job['states']})
                    try:
                        _file(cycle).parent.mkdir(parents=True, exist_ok=True)
                        _file(cycle).write_text(snap, encoding='utf-8')
                    except OSError:
                        pass
                finally:
                    with _lock:
                        job['running'] = False
            threading.Thread(target=work, name=f'us-states-{cycle}', daemon=True).start()
        states = {k: dict(v) for k, v in job['states'].items()}
        out = {'pending': job['running'], 'step': job['step'] if job['running'] else '', 'fetched': job['t'] or None, 'enabled': True}
    out['races'] = [dict(r) for v in states.values() for r in v.get('races', [])]
    out['states'] = {k: {x: v.get(x) for x in ('status', 'page', 'used', 'error', 'fetched', 'tried', 'certified', 'counties')} | {'races': len(v.get('races', []))}
                     for k, v in states.items()}
    return out


def merge(wiki, state, name_of=lambda s: STATES.get(s, s)):
    """Wikipedia gives the call; the state's count gives the numbers. A call stands only if the count agrees."""
    by = {r['id']: dict(r) for r in wiki}
    for s in state:
        w = by.get(s['id'])
        if not w:
            by[s['id']] = _certify(dict(s))
            continue
        m = dict(w)
        for k in ('leader', 'leader_party', 'runner', 'runner_party', 'winner_votes', 'runner_votes', 'total', 'margin_pct',
                  'counted_pct', 'counted_basis', 'cands', 'unopposed'):
            m[k] = s.get(k)
        m['origin'], m['source'], m['wiki_status'] = 'wikipedia+state', s['source'], w.get('status_text')
        if w.get('called') and w.get('winner_party') and s.get('total'):
            if s.get('leader_party') == w['winner_party']:
                cands = json.loads(s['cands'])
                for c in cands:
                    c[4] = int(c[1] == w['winner_party'] and c[0] == s['leader'])
                m['cands'] = json.dumps(cands)
            else:
                m.update(called=0, winner=None, winner_party=None, certified=s.get('certified'),
                         status_text=f"Wikipedia lists {w.get('winner') or 'a winner'} ({w['winner_party']}), but {name_of(s['state'])}'s count "
                                     f"has {s.get('leader')} ({s.get('leader_party')}) ahead. Shown as not called until they agree")
        m['certified'] = s.get('certified')
        if s.get('certified'):
            m = _certify(m)                     # the certified count is the legal result, whatever Wikipedia says
        by[s['id']] = m
    return list(by.values())


def _certify(r):
    """A state's certified result is the official outcome: the leader in the certified count is the winner."""
    if r.get('certified') and r.get('leader_party') and r.get('total'):
        cands = json.loads(r['cands'])
        for c in cands:
            c[4] = int(c[0] == r['leader'] and c[1] == r['leader_party'])
        r.update(called=1, winner=r['leader'], winner_party=r['leader_party'], cands=json.dumps(cands),
                 status_text=f"{STATES.get(r['state'], r['state'])} certified the result")
    return r
