"""2026 vote counts read from each state's own election-results site (all 50 states and DC).

Election results are public records: every state publishes its count for free. This module reads those counts and
nothing else. No news agency's data or race calls are used. A state count never calls a race on its own; calls come
from Wikipedia's results tables (see us_live) and stand only when the state's count agrees, or from the state's own
certification.

Where each state publishes, and in what format, was researched state by state (docs/STATE_RESULT_SOURCES_2026.md).
SOURCES records the outcome with one `kind` per entry:

  clarity      Clarity ENR (CO, IA, SC, WV): <site>/<eid>/current_ver.txt -> <ver>/json/en/summary.json; the
               election id is pinned, or found by date in <site>/elections.json (served gzipped).
  ev_export    Enhanced Voting media export (AZ, GA, UT): one JSON file, results.ballotItems[].ballotOptions[].
  ev_api       Enhanced Voting public API (VA, ID, WA, UT): <base>/results/public/api/elections/<jur>/<id>/data,
               whose `election.isOfficialResults` says whether the count is certified.
  files        delimited text, ZIP or JSON rows read by column name (CA API, MN, NC, FL, SD, AK, DE).
  ri, oregon, la, nd, ct, vt, indiana, ohio, pa
               one small reader per state format (JSON).
  results_sw   the ASP.NET "Results SW" pages shared by NE, NM and MT; ks, il, hi, html for the other pages.
  page         a results page whose links lead to the data (NJ county Clarity sites, TX).
  blocked / unavailable / later / norace
               nothing is fetched: the state refuses scripts, publishes no machine-readable count, publishes only
               certified files after the count, or holds no House, Senate or governor race (DC).

Nothing here gets around a bot check, captcha, login or access gate. Any entry can be corrected without code in
election_data/us/state_sources.json, e.g. {"XX": {"page": "...", "feeds": ["..."]}}.
"""
from __future__ import annotations

import csv
import gzip
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
HI_COLS = {'contest': 1, 'candidate': 15, 'votes': 20, 'reporting': 13, 'precincts': 12}
CA_HOUSE = 52
CLARITY_CDN = 'https://results.enr.clarityelections.com'

SOURCES = {
    'AL': {'kind': 'unavailable', 'page': 'https://www.sos.alabama.gov/alabama-votes/voter/election-information',
           'why': "Alabama's results app has no data file to read; the state posts spreadsheets after certification."},
    'AK': {'kind': 'files', 'page': 'https://www.elections.alaska.gov/election-results/',
           'feeds': ['https://www.elections.alaska.gov/results/{yy}GENR/ENRbyPrecinct.csv'],
           'note': 'First-choice ranked-choice counts.'},
    'AZ': {'kind': 'ev_export', 'page': 'https://results.arizona.vote/',
           'feeds': ['https://app.enhancedvoting.com/cdn/results/Arizona/export-{mmddyy}GeneralElection.json']},
    'AR': {'kind': 'unavailable', 'page': 'https://arkansas.tally-enr.com/',
           'why': "Arkansas's 2026 results file has contest numbers but no contest names, so races can't be identified."},
    'CA': {'kind': 'files', 'page': 'https://electionresults.sos.ca.gov/',
           'feeds': ['https://api.sos.ca.gov/returns/governor'] +
                    [f'https://api.sos.ca.gov/returns/us-rep/district/{n}' for n in range(1, CA_HOUSE + 1)]},
    'CO': {'kind': 'clarity', 'page': 'https://www.coloradosos.gov/pubs/elections/Results/', 'site': f'{CLARITY_CDN}/CO', 'eid': '127407'},
    'CT': {'kind': 'ct', 'page': 'https://ctemspublic.pcctg.net/', 'base': 'https://ctemspublic.pcctg.net/ng-app/data'},
    'DE': {'kind': 'files', 'page': 'https://elections.delaware.gov/results/enr/GE{yyyy}.html',
           'feeds': ['https://elections.delaware.gov/results/enr/Election_StatewideResults_ID_GE{yyyy}.json'],
           'columns': {'contest': 'Contest Title', 'candidate': 'Candidate Name', 'party': 'Party Name', 'votes': 'Total Votes',
                       'reporting': 'Precincts Reported', 'precincts': 'Total Precincts'}},
    'DC': {'kind': 'norace', 'page': 'https://electionresults.dcboe.org/',
           'why': 'DC elects no voting House member, no senator and no governor.'},
    'FL': {'kind': 'files', 'page': 'https://results.elections.myflorida.com/',
           'feeds': ['https://flelectionfiles.floridados.gov/enightfilespublic/{yyyymmdd}_ElecResultsFL.txt'],
           'columns': {'contest': ['RaceName', 'OfficeDesc'], 'district': 'Juris1num', 'first': 'CanNameFirst', 'last': 'CanNameLast',
                       'party': 'PartyCode', 'votes': 'CanVotes', 'reporting': 'PrecinctsReporting', 'precincts': 'Precincts',
                       'county': ['CountyName', 'CountyCode']}},
    'GA': {'kind': 'ev_export', 'page': 'https://results.sos.ga.gov/results/public/Georgia/elections/11032026GeneralAndSpecialElection',
           'feeds': ['https://results.sos.ga.gov/cdn/results/Georgia/export-11032026GeneralAndSpecialElection.json']},
    'HI': {'kind': 'files', 'page': 'https://elections.hawaii.gov/election-results/',
           'feeds': ['https://files.hawaii.gov/elections/files/results/{yyyy}/General/summary.txt'], 'columns': HI_COLS},
    'ID': {'kind': 'ev_api', 'page': 'https://results.voteidaho.gov/results/public/id/elections/nov{yyyy}',
           'ev': ['https://results.voteidaho.gov', 'id'], 'ev_keys': ['nov{yyyy}']},
    'IL': {'kind': 'il', 'page': 'https://www.elections.il.gov/electionoperations/ElectionVoteTotals.aspx'},
    'IN': {'kind': 'indiana', 'page': 'https://enr.indianavoters.in.gov/', 'base': 'https://enr.indianavoters.in.gov/archive/{yyyy}General/data'},
    'IA': {'kind': 'clarity', 'page': 'https://sos.iowa.gov/elections/results/', 'site': f'{CLARITY_CDN}/IA', 'eid': '127077'},
    'KS': {'kind': 'ks', 'page': 'https://www.sos.ks.gov/elections/election-results.html',
           'feeds': ['https://www.sos.ks.gov/ent/national.html', 'https://www.sos.ks.gov/ent/statewide.html']},
    'KY': {'kind': 'blocked', 'page': 'https://elect.ky.gov/results/',
           'why': "Kentucky's results service sits behind an access gate (Acceptable Use Policy) that refuses automated reading."},
    'LA': {'kind': 'la', 'page': 'https://voterportal.sos.la.gov/graphical',
           'base': 'https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob={yyyymmdd}/'},
    'ME': {'kind': 'unavailable', 'page': 'https://www.maine.gov/sos/elections-voting/election-results-data',
           'why': 'Maine posts spreadsheets and ranked-choice reports per contest after the count, not a live count.'},
    'MD': {'kind': 'later', 'page': 'https://elections.maryland.gov/elections/archive/{yyyy}/election_data/',
           'why': 'Maryland publishes machine-readable results only with the certified count.'},
    'MA': {'kind': 'unavailable', 'page': 'https://electionstats.state.ma.us/',
           'why': 'Massachusetts has no election-night data feed; certified results are posted later.'},
    'MI': {'kind': 'unavailable', 'page': 'https://mielections.us/election/results/',
           'why': "Michigan has no statewide data feed (its results site does not answer scripts); counties publish separately."},
    'MN': {'kind': 'files', 'page': 'https://electionresults.sos.mn.gov/',
           'feeds': ['https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/ushouse.txt',
                     'https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/ussenate.txt',
                     'https://electionresultsfiles.sos.mn.gov/{yyyymmdd}/governor.txt'],
           'columns': MN_COLS},
    'MS': {'kind': 'later', 'page': 'https://www.sos.ms.gov/elections-voting/election-results',
           'why': 'Mississippi publishes its recap sheets after certification.'},
    'MO': {'kind': 'blocked', 'page': 'https://enr.sos.mo.gov/', 'why': "Missouri's results site answers scripts with a bot challenge."},
    'MT': {'kind': 'results_sw', 'page': 'https://electionresults.mt.gov/', 'base': 'https://electionresults.mt.gov/resultsSW.aspx',
           'types': ['FED', 'STATE'], 'eid_from': 'https://candidatefiling.mt.gov/candidatefiling/CandidateList.aspx',
           'note': 'May answer only US connections.'},
    'NE': {'kind': 'results_sw', 'page': 'https://electionresults.nebraska.gov/', 'base': 'https://electionresults.nebraska.gov/resultsSW.aspx',
           'types': ['SW', 'CG']},
    'NV': {'kind': 'blocked', 'page': 'https://silverstateelection.nv.gov/', 'why': "Nevada's results site answers scripts with a bot challenge."},
    'NH': {'kind': 'blocked', 'page': 'https://www.sos.nh.gov/elections/elections/election-results',
           'why': "New Hampshire's site refuses scripts and publishes no data feed."},
    'NJ': {'kind': 'page', 'page': 'https://www.nj.gov/state/elections/election-night-results.shtml',
           'note': 'New Jersey publishes statewide results as PDFs; counts are added up from county Clarity sites.'},
    'NM': {'kind': 'results_sw', 'page': 'https://electionresults.sos.nm.gov/', 'base': 'https://electionresults.sos.nm.gov/resultsSW.aspx',
           'types': ['FED', 'SW'], 'extra': 'text=All&'},
    'NY': {'kind': 'blocked', 'page': 'https://nyenr.elections.ny.gov/',
           'why': "New York's results site refuses scripts, and its data host has no list of contests."},
    'NC': {'kind': 'files', 'page': 'https://er.ncsbe.gov/',
           'feeds': ['https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{yyyy_mm_dd}/results_pct_{yyyymmdd}.zip']},
    'ND': {'kind': 'nd', 'page': 'https://resultsnd.sos.nd.gov/', 'base': 'https://api.resultsnd.sos.nd.gov', 'eid': '348'},
    'OH': {'kind': 'ohio', 'page': 'https://liveresults.ohiosos.gov/', 'base': 'https://liveresults.ohiosos.gov/Api/v1/Contest'},
    'OK': {'kind': 'blocked', 'page': 'https://results.okelections.gov/', 'why': "Oklahoma's results site refuses scripts."},
    'OR': {'kind': 'oregon', 'page': 'https://results.oregonvotes.gov/',
           'base': 'https://orresultswebservices.azureedge.us/ResultsAjax.svc/GetMapData', 'types': ['FED', 'SWPAR']},
    'PA': {'kind': 'pa', 'page': 'https://www.electionreturns.pa.gov/', 'base': 'https://www.electionreturns.pa.gov/api/ElectionReturn',
           'eid': '117', 'offices': [2, 3, 11]},
    'RI': {'kind': 'ri', 'page': 'https://www.ri.gov/election/results/',
           'feeds': ['https://rigov.s3.amazonaws.com/election/results/{yyyy}/general_election/statewide.json']},
    'SC': {'kind': 'clarity', 'page': 'https://www.enr-scvotes.org/SC/', 'site': f'{CLARITY_CDN}/SC', 'eid': '127300'},
    'SD': {'kind': 'files', 'page': 'https://electionresults.sd.gov/',
           'feeds': ['https://electionresults.sd.gov/resultsCSV.aspx?text=All&type=SWR&map=CTY'],
           'columns': {'contest': 'RaceName', 'candidate': 'CandidateName', 'party': 'PartyCode', 'votes': 'CandidateVotes',
                       'reporting': 'PrecinctsReporting'}},
    'TN': {'kind': 'blocked', 'page': 'https://sos.tn.gov/elections/results', 'why': "Tennessee's results site refuses scripts; results are PDFs."},
    'TX': {'kind': 'files', 'page': 'https://electionresults.sos.state.tx.us/results.html',
           'feeds': ['https://electionresults.sos.state.tx.us/results.html']},
    'UT': {'kind': 'ev_api', 'page': 'https://electionresults.utah.gov/results/public/Utah/elections/general{mmddyyyy}',
           'ev': ['https://electionresults.utah.gov', 'Utah'], 'ev_keys': ['general{mmddyyyy}'],
           'feeds': ['https://app.enhancedvoting.com/cdn/results/Utah/export-general{mmddyyyy}.json']},
    'VT': {'kind': 'vt', 'page': 'https://electionresults.vermont.gov/', 'base': 'https://static.electionresults.vermont.gov/elections'},
    'VA': {'kind': 'ev_api', 'page': 'https://enr.elections.virginia.gov/results/public/virginia/elections/{yyyy}-November-General',
           'ev': ['https://enr.elections.virginia.gov', 'virginia'], 'ev_keys': ['{yyyy}-November-General']},
    'WA': {'kind': 'ev_api', 'page': 'https://results.vote.wa.gov/results/{yyyymmdd}/',
           'ev': ['https://results.votewa.gov', 'washington'], 'ev_keys': ['{yyyymmdd}'],
           'feeds': ['https://results.vote.wa.gov/results/{yyyymmdd}/export/{yyyymmdd}_AllState.csv']},
    'WV': {'kind': 'clarity', 'page': 'https://sos.wv.gov/govotewv', 'site': f'{CLARITY_CDN}/WV', 'eid': '127496'},
    'WI': {'kind': 'blocked', 'page': 'https://elections.wi.gov/elections/election-results',
           'why': "Wisconsin's site answers scripts with a bot challenge; counties report results separately."},
    'WY': {'kind': 'unavailable', 'page': 'https://sos.wyo.gov/Elections/State/Results.aspx',
           'why': 'Wyoming publishes results as PDFs only.'},
}
NOFETCH = {'blocked', 'unavailable', 'later', 'norace'}

CLARITY = re.compile(r'https?://results\.enr\.clarityelections\.com/([A-Z]{2})/(?:([A-Za-z_\-]+)/)?(\d{4,7})', re.I)
ENHANCED = re.compile(r'https?://app\.enhancedvoting\.com/cdn/results/[^"\'\s<>]+?\.json', re.I)
DATAFILE = re.compile(r'href=["\']([^"\']+?\.(?:csv|txt|json|zip|xml|tsv))["\']', re.I)
SKIP_NAME = re.compile(r'write[- ]?ins?\b|under\s*votes?|over\s*votes?|^blank|^total|vote totals|registered voters|ballots cast|'
                       r'^times (over|blank)|^none of these', re.I)
ORDINAL = {w: i for i, w in enumerate('first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth '
                                      'fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split(), 1)}
ROMAN = {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10}


# ------------------------------------------------------------------ contests and parties
def party_code(text):
    t = re.sub(r'[^a-z ]', ' ', (text or '').lower()).strip()
    if not t:
        return 'O'
    if re.search(r'\b(dem|democrat|democratic|dfl|d)\b', t):
        return 'D'
    if re.search(r'\b(rep|republican|gop|r)\b', t):
        return 'R'
    if re.search(r'\b(ind|independent|npa|no party|unaffiliated|una|np|nonpartisan|non partisan|i|nopty|non)\b', t):
        return 'I'
    return 'O'


PREFIX = re.compile(r'^\s*(?:\((?P<p1>[A-Z]{1,5})\)\s*|(?P<p2>DEM|REP|LIB|GRN|GRE|IND|CON|NPA|NON|WF|OTH)\s+|(?P<p3>D|R|L|I|i|G|C|UK|IND|LIB|REF)-(?=[A-Z]))')
SUFFIX = re.compile(r'\s*\((?P<s>DEM|REP|LIB|GRN|GRE|IND|NOPTY|NPA|NON|CON|Dem|Rep|Lib|Ind|Grn|D|R|L|G|I)\)\s*$')


def clean_candidate(name, party=''):
    """Strip the party marks some states put in the name ("REP Nancy Mace", "D-Adam Hamilton", "(D) CASE, Ed",
    "Steve Scalise (REP)", "David Perdue (I) (Rep)"). Returns (name, party), taking the party from the mark when the row
    has none."""
    n = re.sub(r'\s+', ' ', str(name or '')).strip()
    p = str(party or '').strip()
    m = PREFIX.match(n)
    if m:
        mark = m.group('p1') or m.group('p2') or m.group('p3')
        n = n[m.end():].strip()
        p = p or mark
    while True:
        m = SUFFIX.search(n)
        if not m:
            break
        if m.group('s') not in ('I',) or n.count('(') > 1:
            p = p or m.group('s')
        n = n[:m.start()].strip()
    n = re.sub(r'\s*\((?:I|i)\)\s*$', '', n)
    parts = [x.strip() for x in n.split(',')]
    if len(parts) == 2 and parts[1] and not re.fullmatch(r'(jr|sr|ii|iii|iv)\.?', parts[1], re.I) and ' ' not in parts[0].strip():
        n = f'{parts[1]} {parts[0]}'                        # "CASE, Ed" / "Begich, Nick" -> "Ed CASE" / "Nick Begich"
    return n, p


def _district(t, state):
    pats = [r'district\s*(?:no\.?\s*|#\s*)?(\d{1,2})\b',
            r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:congressional\s+)?district\b',
            r'\bcd\s*-?\s*(\d{1,2})\b']
    for p in pats:
        m = re.search(p, t)
        if m:
            return str(int(m.group(1)))
    m = re.search(r'(?:district|dist\.?)\s*,?\s*([ivx]{1,4})\b', t) or re.search(r'\b([ivx]{1,4})\s+district\b', t)
    if m and m.group(1) in ROMAN:
        return str(ROMAN[m.group(1)])
    m = re.search(r'\b(' + '|'.join(ORDINAL) + r')\s+(?:congressional\s+)?district\b', t)
    if m:
        return str(ORDINAL[m.group(1)])
    m = re.search(r'(?:representatives?|congress)\s*-?\s*(\d{1,2})\s*$', t)   # Kansas: "...House of Representatives 1"
    if m:
        return str(int(m.group(1)))
    m = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)\s+congress\b', t)            # Illinois: "1ST CONGRESS"
    if m:
        return str(int(m.group(1)))
    if 'at large' in t.replace('-', ' ') or state in AT_LARGE:
        return '1'
    return None


HOUSE = re.compile(r'(u\.?\s?s\.?|united states)\s*(house|rep|congress)|congressional|representatives? (in|to) (the )?(\d+\w* )?'
                   r'(united states )?congress|member of congress|member,?\s*(u\.?\s?s\.?\s*)?house of representatives|'
                   r'\b\d{1,2}(st|nd|rd|th)\s+congress\b')


def classify(title, state):
    """Contest title -> (office, seat, special), or None for any other contest."""
    t = re.sub(r'\s+', ' ', (title or '').lower()).strip()
    if not t or re.search(r'\bprimary\b|delegate|committee|\bstate (senat|rep|house)|precinct|board|council|- (rep|dem)$', t):
        return None
    special = bool(re.search(r'unexpired|special|short term|vacancy', t))
    if re.search(r'governor\s*(&|and|/)\s*l(ieu)?t', t):
        return 'G', '', special
    if re.search(r'l(ieu)?t\.?\s*(enant\s*)?gov', t):
        return None
    if re.search(r'\bgovernor\b', t):
        return 'G', '', special
    if re.search(r'(u\.?\s?s\.?|united states|federal)\s*senat', t):
        return 'S', '', special
    if HOUSE.search(t):
        d = _district(t, state)
        if d:
            return 'H', d, special
    return None


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or '').strip().lstrip('=').strip('"')
    m = re.match(r'^\s*(-?\d[\d,]*(?:\.\d+)?)\s*%?\s*$', s)
    return float(m.group(1).replace(',', '')) if m else None


def _pair(v):
    """'122/671', '0 of 779 (0%)' -> (122, 671)."""
    m = re.search(r'([\d,]+)\s*(?:/|of)\s*([\d,]+)', str(v or ''))
    return (_num(m.group(1)), _num(m.group(2))) if m else None


# ------------------------------------------------------------------ the contest record every reader returns
# contest = {'title', 'cands': {(name, party): votes}, 'reporting': (counted, total) or None, 'pct': float or None}
def _contest(title):
    return {'title': re.sub(r'\s+', ' ', str(title or '')).strip(), 'cands': {}, 'reporting': None, 'pct': None}


def _add(c, name, party, votes):
    name, party = clean_candidate(name, party)
    if not name or SKIP_NAME.search(name) or votes is None:
        return
    k = (name, party_code(party))
    c['cands'][k] = c['cands'].get(k, 0) + votes


def _rep_add(c, rep):
    if rep and rep[1]:
        a, b = c['reporting'] or (0, 0)
        c['reporting'] = (a + rep[0], b + rep[1])


def _text(v):
    """Enhanced Voting names are lists of {languageId, text}; take the English one."""
    if isinstance(v, list):
        en = next((x.get('text') for x in v if isinstance(x, dict) and x.get('languageId') in ('en', 'EN')), None)
        return en or next((x.get('text') for x in v if isinstance(x, dict)), '')
    if isinstance(v, dict):
        return v.get('text') or _text(v.get('name'))
    return str(v or '')


# ------------------------------------------------------------------ general readers
def read_clarity(payload):
    out = []
    for item in payload if isinstance(payload, list) else payload.get('Contests', []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or 'C' not in item:
            continue
        c = _contest(item.get('C'))
        names, parties, votes = item.get('CH') or [], item.get('P') or [], item.get('V') or []
        for i, n in enumerate(names):
            _add(c, n, parties[i] if i < len(parties) else '', _num(votes[i]) if i < len(votes) else None)
        if _num(item.get('PR')) and _num(item.get('TP')):          # PR 0 can mean "not published" (South Carolina)
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
        v = d.get(k)
        if isinstance(v, list):
            v = _text(v)
        if isinstance(v, str) and v.strip():
            return v
    first = next((d[k] for k in ('firstName', 'FirstName', 'first') if isinstance(d.get(k), str)), '')
    last = next((d[k] for k in ('lastName', 'LastName', 'last') if isinstance(d.get(k), str)), '')
    return f'{first} {last}'.strip()


def _cand_party(d):
    for k in PARTY_KEYS:
        v = d.get(k)
        if isinstance(v, dict):
            v = next((v[x] for x in ('abbreviation', 'code', 'name', 'Name') if v.get(x)), '')
            v = _text(v) if isinstance(v, list) else v
        if isinstance(v, str):
            return v
    return ''


def _is_cand_list(v):
    if not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
        return False
    if any(isinstance(y, list) and y and isinstance(y[0], dict) for x in v for y in x.values()):
        return False                                         # a list of contests, not of candidates
    return sum(1 for x in v if _cand_name(x) and _votes_of(x) is not None) >= max(1, len(v) // 2)


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
        title = next((_text(o[k]) for k in TITLE_KEYS if o.get(k) and isinstance(o[k], (str, list)) and _text(o[k]).strip()), None)
        for k, v in o.items():
            if _is_cand_list(v):
                c = _contest(title or ctx)
                for x in v:
                    _add(c, _cand_name(x), _cand_party(x), _votes_of(x))
                rep = o.get('Reporting') or o.get('reporting') or o.get('precinctsReportingText')
                c['reporting'] = _pair(rep)
                if not c['reporting'] and _num(o.get('precinctsReporting')) is not None:
                    tot = _num(o.get('precinctsTotal') or o.get('totalPrecincts') or o.get('precinctsParticipating'))
                    c['reporting'] = (_num(o['precinctsReporting']), tot) if tot else None
                if c['title']:
                    out.append(c)
            elif isinstance(v, (dict, list)):
                walk(v, title or ctx)

    walk(payload, None)
    return out


def _norm(h):
    return re.sub(r'[_\s]+', ' ', str(h or '')).strip().lower()


def _find(header, *pats):
    hs = [_norm(h) for h in header]
    for p in pats:
        for j, h in enumerate(hs):
            if re.fullmatch(p, h, re.I):
                return j
    return None


AUTO = {'contest': (r'contest( ?name| ?title)?', r'race( ?name)?', r'office( ?(name|desc|title))?'),
        'district': (r'district', r'juris1num'),
        'candidate': (r'candidate( ?name)?', r'choice( ?name)?', r'name', r'ballot ?name', r'calc ?candidate'),
        'party': (r'(choice |contest )?party( ?code| ?abbr\w*)?', r'party( ?name)?'),
        'votes': (r'total ?votes', r'votes', r'can ?votes', r'candidate ?votes', r'vote ?count', r'calc ?candidate ?votes', r'total'),
        'precinct': (r'precinct( ?name)?', r'pct ?id'),
        'county': (r'county( ?name)?', r'jurisdiction ?name'),
        'reporting': (r'precincts ?reporting', r'precincts ?reported'),
        'precincts': (r'total ?precincts', r'precincts'),
        'first': (r'(can ?)?(name ?)?first( ?name)?',), 'last': (r'(can ?)?(name ?)?last( ?name)?',)}


def _columns(header, columns):
    if columns and all(isinstance(v, int) for v in columns.values()):
        return dict(columns)
    cols = {}
    for k, pats in AUTO.items():
        want = (columns or {}).get(k)
        if want is not None:
            names = want if isinstance(want, list) else [want]
            cols[k] = next((j for n in names for j in [_find(header, re.escape(_norm(n)))] if j is not None), None)
        else:
            cols[k] = _find(header, *pats)
    return cols


def read_rows(header, rows, columns=None):
    """Rows with one candidate each (per county or precinct: summed here). `header` may be None for headerless files
    whose columns are given by position."""
    cols = _columns(header or [], columns)
    if cols.get('contest') is None or cols.get('votes') is None or (cols.get('candidate') is None and cols.get('last') is None):
        return []
    by, total_rows, raw, seen_rep = {}, set(), [], {}
    for r in rows:
        g = lambda k: str(r[cols[k]]).strip() if cols.get(k) is not None and cols[k] < len(r) and r[cols[k]] is not None else ''
        title = re.sub(r'\s+', ' ', g('contest'))
        if not title or not re.search(r'senat|congress|represent|house|governor|\bcd\b', title, re.I):
            continue
        d = g('district')
        if d and not re.search(r'district|\bdist\b|\bcd\b', title, re.I) and re.fullmatch(r'\d{1,2}', d):
            title = f'{title} District {int(d)}'
        name = g('candidate') or f"{g('first')} {g('last')}".strip()
        pre = g('precinct')
        raw.append((title, name, g('party'), _num(g('votes')), pre, g('reporting'), g('precincts'), g('county')))
        if pre.lower() == 'total':
            total_rows.add(title)
    for title, name, party, votes, pre, rep, pcts, county in raw:
        if title in total_rows and pre.lower() != 'total':
            continue                                  # a file with both totals and precincts: totals only
        c = by.setdefault(title, _contest(title))
        _add(c, name, party, votes)
        pair = _pair(rep) if '/' in rep or ' of ' in rep else ((_num(rep), _num(pcts)) if _num(rep) is not None and _num(pcts) else None)
        if pair:
            seen_rep[(title, county)] = pair
    for (title, _), rp in seen_rep.items():
        _rep_add(by[title], rp)
    return list(by.values())


def read_table(text, columns=None):
    """Delimited text: comma, tab, semicolon or pipe, with or without a header."""
    lines = text.splitlines()
    if not lines:
        return []
    csv.field_size_limit(50_000_000)
    sample = '\n'.join(lines[:20])
    delim = max(['\t', ';', '|', ','], key=lambda d: sample.count(d))
    rows = csv.reader(io.StringIO(text), delimiter=delim)
    positional = columns and all(isinstance(v, int) for v in columns.values())
    header = None if positional else next(rows, [])
    return read_rows(header, rows, columns)


def read_records(records, columns=None):
    """JSON rows: a list of flat objects (Delaware), read like a table."""
    header = list(records[0].keys())
    return read_rows(header, ([rec.get(h) for h in header] for rec in records if isinstance(rec, dict)), columns)


class _Tables(HTMLParser):
    """Results tables with the text just before each one (the contest title on most results pages)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.recent, self.cur, self.row, self.cell, self.depth = [], [], None, None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                title = next((t for t in reversed(self.recent) if len(t) > 3 and not re.search(r'reporting|updated|download', t, re.I)), '')
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


def decode(blob):
    if blob[:2] == b'\x1f\x8b':
        blob = gzip.decompress(blob)                 # Clarity gzips some files without being asked
    if blob[:2] in (b'\xff\xfe', b'\xfe\xff') or blob[1:200:2].count(0) > 50:
        text = blob.decode('utf-16', errors='replace')
    else:
        text = blob.decode('utf-8-sig', errors='replace')
    return text.replace('\x00', '')


def load_json(blob):
    d = json.loads(decode(blob))
    while isinstance(d, str):                         # Pennsylvania: JSON inside a JSON string
        d = json.loads(d)
    return d


def contests_from(blob, columns=None):
    """Detect the format of a downloaded file and read its contests."""
    if blob[:2] == b'PK':
        out = []
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                if info.filename.lower().endswith(('.txt', '.csv', '.tsv', '.json')) and info.file_size < 400_000_000:
                    out += contests_from(z.read(info), columns)
        return out
    text = decode(blob)
    s = text.lstrip()[:1]
    if s in '{[':
        try:
            payload = json.loads(text)
        except ValueError:
            return []
        if isinstance(payload, list) and payload and isinstance(payload[0], dict) and 'C' in payload[0] and 'CH' in payload[0]:
            return read_clarity(payload)
        if isinstance(payload, list) and payload and isinstance(payload[0], dict) and not any(isinstance(v, (list, dict)) for v in payload[0].values()):
            return read_records(payload, columns)
        if isinstance(payload, dict) and isinstance(payload.get('results'), dict) and 'ballotItems' in payload['results']:
            return read_ev_items(payload['results']['ballotItems'])
        if isinstance(payload, dict) and isinstance(payload.get('ballotItems'), list):
            return read_ev_items(payload['ballotItems'])
        return read_json(payload)
    if s == '<':
        return read_html(text)
    if text.lstrip().startswith('"Format#'):
        text = text.split('\n', 1)[1] if '\n' in text else ''
    return read_table(text, columns)


# ------------------------------------------------------------------ Enhanced Voting
def read_ev_items(items):
    """Enhanced Voting ballot items, from the media export or the public API. County copies of statewide contests
    (parentId) are skipped."""
    out = []
    for b in items or []:
        if not isinstance(b, dict) or b.get('parentId'):
            continue
        c = _contest(_text(b.get('name')))
        opts = b.get('ballotOptions') or (b.get('summaryResults') or {}).get('ballotOptions') or []
        for o in opts:
            if not isinstance(o, dict):
                continue
            party = o.get('politicalParty') or _text((o.get('party') or {}).get('name') if isinstance(o.get('party'), dict) else o.get('party'))
            _add(c, _text(o.get('name')), party or '', _num(o.get('voteCount')))
        rs = b.get('reportingStatus') or {}
        if _num(rs.get('totalUnits')):
            c['reporting'] = (_num(rs.get('reportingUnits')) or 0, _num(rs['totalUnits']))
        elif _num(b.get('precinctsParticipating')):
            c['reporting'] = (_num(b.get('precinctsReporting')) or 0, _num(b['precinctsParticipating']))
        if c['title']:
            out.append(c)
    return out


def _ev_api(base, jur, keys, getter):
    """Returns (contests, certified, url)."""
    last = None
    for k in keys:
        url = f"{base.rstrip('/')}/results/public/api/elections/{jur}/{k}/data"
        try:
            data = load_json(getter(url))
        except Exception as exc:
            last = exc
            continue
        certified = None
        if isinstance(data, dict) and isinstance(data.get('election'), dict) and 'isOfficialResults' in data['election']:
            certified = bool(data['election']['isOfficialResults'])
        else:
            try:
                meta = load_json(getter(url[:-len('/data')]))
                certified = bool(meta.get('isOfficialResults')) if isinstance(meta, dict) else None
            except Exception:
                pass
        items = data.get('ballotItems', []) if isinstance(data, dict) else data
        return read_ev_items(items), certified, url
    raise last or LookupError('no election found')


# ------------------------------------------------------------------ Clarity
DATE_TOKENS = lambda cycle: (lambda y, m, d: (f'{m}/{d}/{y}', f'{int(m)}/{int(d)}/{y}', f'{y}-{m}-{d}', f'{y}{m}{d}'))(*DATES[cycle].split('-'))


def _clarity_eid(site, cycle, getter):
    """Find this election's id in the site's elections.json (any entry naming the election date)."""
    listing = load_json(getter(f"{site.rstrip('/')}/elections.json"))
    toks = DATE_TOKENS(cycle)

    def walk(o):
        if isinstance(o, dict):
            if any(any(t in str(v) for t in toks) for v in o.values() if isinstance(v, str)):
                for k in ('EID', 'eid', 'ElectionID', 'electionId', 'id', 'ID'):
                    if re.fullmatch(r'\d{4,7}', str(o.get(k) or '')):
                        return str(o[k])
            for v in o.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None
    eid = walk(listing)
    if not eid:
        raise LookupError("this election is not in the site's list of elections yet")
    return eid


def _clarity_contests(base, getter):
    base = base.rstrip('/') + '/'
    ver = decode(getter(base + 'current_ver.txt')).strip()
    if not re.fullmatch(r'\d{1,9}', ver):
        raise ValueError('Clarity did not return a version number')
    return read_clarity(load_json(getter(f'{base}{ver}/json/en/summary.json')))


# ------------------------------------------------------------------ one reader per state format
def read_ri(data):
    out = []
    for ct in (data or {}).get('contests', []):
        c = _contest(ct.get('name'))
        for x in ct.get('candidates', []):
            _add(c, x.get('name'), x.get('party_code'), _num(x.get('votes')))
        if _num(ct.get('precinct_count')):
            c['reporting'] = (_num(ct.get('precincts_reporting')) or 0, _num(ct['precinct_count']))
        out.append(c)
    return out


def read_oregon(data):
    rows = (data or {}).get('d', []) if isinstance(data, dict) else data
    state_rows = [r for r in rows if not r.get('CountyName')] or rows
    by = {}
    for r in state_rows:
        c = by.setdefault(r.get('RaceID') or r.get('RaceName'), _contest(r.get('RaceName')))
        _add(c, r.get('calcCandidate') or r.get('CandidateName'), (r.get('PartyName') or '').split(',')[0], _num(r.get('calcCandidateVotes')))
        if _num(r.get('TotalPrecincts')):
            c['reporting'] = ((_num(r.get('PrecinctsReporting')) or 0), _num(r['TotalPrecincts']))
    return list(by.values())


def read_la(races, votes):
    names = {}
    out = []
    rmap = {}
    for r in ((races or {}).get('Races') or {}).get('Race', []):
        rmap[r['ID']] = r
        for ch in r.get('Choice', []) or []:
            names[ch['ID']] = ch.get('Desc', '')
    for v in ((votes or {}).get('Races') or {}).get('Race', []):
        r = rmap.get(v.get('ID'))
        if not r:
            continue
        c = _contest(r.get('SpecificTitle') or r.get('GeneralTitle'))
        for ch in v.get('Choice', []) or []:
            _add(c, names.get(ch.get('ID'), ''), '', _num(ch.get('VoteTotal')))
        if _num(v.get('PrecinctsExpected')):
            c['reporting'] = (_num(v.get('PrecinctsReporting')) or 0, _num(v['PrecinctsExpected']))
        out.append(c)
    return out


def read_nd(contests, results):
    meta = ((contests or {}).get('response') or {}).get('contests') or {}
    out = []
    for cid, r in (((results or {}).get('response') or {}).get('contests') or {}).items():
        m = meta.get(cid) or meta.get(str(r.get('contestID'))) or {}
        c = _contest(m.get('contestName'))
        chs = m.get('choices') or {}
        for ch in r.get('choices', []):
            info = chs.get(str(ch.get('choiceID'))) or {}
            _add(c, info.get('name'), ch.get('partyID') or info.get('partyID'), _num(ch.get('totalVotes')))
        if _num(r.get('totalPrecincts')):
            c['reporting'] = (_num(r.get('precinctsReporting')) or 0, _num(r['totalPrecincts']))
        out.append(c)
    return out, bool((results or {}).get('isOfficial'))


def read_ct(lookup, data):
    offices = {}
    for o in lookup.get('officeList', []):
        for k, v in o.items():
            offices[str(k)] = v
    cands = {str(k): v for k, v in (lookup.get('candidateIds') or {}).items()}
    parties = {str(k): v for k, v in (lookup.get('partyIds') or {}).items()}
    out = []
    for oid, lines in ((data or {}).get('stateVotes') or {}).items():
        o = offices.get(str(oid)) or {}
        title = o.get('NM', '')
        if o.get('OT') == 'C' and o.get('D'):
            title = f"Representative in Congress District {o['D']}"
        c = _contest(title)
        merged = {}
        for line in lines:
            for cid, v in line.items():
                info = cands.get(str(cid)) or {}
                name = info.get('NM', '')
                party = (parties.get(str(info.get('P'))) or {}).get('CD', '')
                votes = _num(v.get('V')) or 0
                cur = merged.get(name)
                merged[name] = (party if not cur or votes > cur[2] else cur[0], (cur[1] if cur else 0) + votes, max(votes, cur[2] if cur else 0))
        for name, (party, votes, _) in merged.items():
            _add(c, name, party, votes)
        c['reporting'] = _pair((data.get('election') or {}).get('PR'))
        out.append(c)
    return out


def read_vt(files):
    out = []
    for f in files:
        for grp in (f or {}).get('d', []):
            for o in grp.get('o', []):
                c = _contest(o.get('on'))
                tally, party = {}, {}
                towns = o.get('cs') or []
                for town in towns:
                    for rc in town.get('rc', []):
                        cid = rc.get('cid')
                        tally[cid] = tally.get(cid, 0) + (_num(rc.get('vc')) or 0)
                        party[cid] = (rc.get('cn'), rc.get('pn', ''))
                for cid, v in tally.items():
                    _add(c, party[cid][0], party[cid][1], v)
                done = sum(1 for t in towns if _pair(t.get('distReported')) and _pair(t['distReported'])[0] >= _pair(t['distReported'])[1])
                if towns:
                    c['reporting'] = (done, len(towns))
                out.append(c)
    return out


def read_indiana(files):
    out = []
    for f in files:
        races = (((f or {}).get('Root') or {}).get('StatewideSummary') or {}).get('Race', [])
        for r in races if isinstance(races, list) else [races]:
            c = _contest(r.get('OFFICE_TITLE'))
            cs = (r.get('Candidates') or {}).get('Candidate', [])
            for x in cs if isinstance(cs, list) else [cs]:
                _add(c, x.get('NAME_ON_BALLOT'), x.get('PARTY'), _num(x.get('TOTAL')))
            out.append(c)
    return out


def read_ohio(details):
    out = []
    for d in details:
        c = _contest(d.get('contestDisplayName') or d.get('contestName'))
        rep = [0, 0]
        for row in d.get('contestList', []) or []:
            rep[0] += _num(row.get('reportedPrecincts')) or 0
            rep[1] += _num(row.get('totalPrecincts')) or 0
            for x in row.get('candidatesRunning', []) or []:
                _add(c, x.get('primaryCandidate'), x.get('candidateParty'), _num(x.get('vCount') if x.get('vCount') is not None else x.get('voteCount')))
        if rep[1]:
            c['reporting'] = tuple(rep)
        out.append(c)
    return out


def read_pa(data):
    out = []
    for office, groups in ((data or {}).get('Election') or {}).items():
        for group in groups if isinstance(groups, list) else [groups]:
            for inner in (group or {}).values():
                for race in inner if isinstance(inner, list) else [inner]:
                    if not isinstance(race, dict):
                        continue
                    district = str(race.get('District') or '')
                    c = _contest(f'{office} {district}' if district and district.lower() != 'statewide' else office)
                    for x in race.get('Candidates') or []:
                        _add(c, x.get('CandidateName'), x.get('PartyName'), _num(x.get('Votes')))
                    out.append(c)
    return out


def _strip_tags(s):
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def read_results_sw(text):
    """The ASP.NET "Results SW" pages used by Nebraska, New Mexico and Montana."""
    out = []
    for block in re.split(r'class="wrapper-inside wrapper-border"', text)[1:]:
        m = re.search(r'display-results-box-a[^>]*>\s*<h1>(.*?)</h1>', block, re.S)
        if not m:
            continue
        c = _contest(_strip_tags(m.group(1)))
        rep = re.search(r'Precincts Fully:\s*([\d,]+)\s*/\s*([\d,]+)', block)
        if rep:
            c['reporting'] = (_num(rep.group(1)), _num(rep.group(2)))
        for cm in re.finditer(r'display-results-box-d">\s*<h1>(.*?)</h1>\s*(?:<h2[^>]*>(.*?)</h2>)?.*?display-results-box-f">\s*<h1>(.*?)</h1>', block, re.S):
            _add(c, _strip_tags(cm.group(1)), _strip_tags(cm.group(2) or ''), _num(_strip_tags(cm.group(3))))
        out.append(c)
    return out


def read_ks(text):
    out = []
    for block in re.split(r"<div class='race'>", text)[1:]:
        m = re.search(r'<h3>(.*?)</h3>', block, re.S)
        if not m:
            continue
        c = _contest(_strip_tags(m.group(1)))
        c['reporting'] = _pair(re.search(r'Precincts Reporting:\s*([\d,]+ of [\d,]+)', block).group(1)) if re.search(r'Precincts Reporting:\s*[\d,]+ of [\d,]+', block) else None
        for cm in re.finditer(r"<div class='col-6'>\s*<p>(.*?)</p>\s*</div>\s*<div class='col-2'>\s*<p>(.*?)</p>", block, re.S):
            _add(c, _strip_tags(cm.group(1)), '', _num(_strip_tags(cm.group(2))))
        out.append(c)
    return out


def _page_date_ok(text, cycle, words=('GENERAL',)):
    y = DATES[cycle][:4]
    t = text.upper()
    return y in t and all(w in t for w in words)


# ------------------------------------------------------------------ fetching one state
def _fill(url, cycle):
    y, m, dd = DATES[cycle].split('-')
    return url.format(yyyymmdd=f'{y}{m}{dd}', yyyy_mm_dd=f'{y}_{m}_{dd}', mmddyy=f'{m}{dd}{y[2:]}', mmddyyyy=f'{m}{dd}{y}',
                      yyyy=y, yy=y[2:])


EV_LINK = re.compile(r'(https?://[a-z0-9.\-]+)/results/public/(?:api/elections/)?([a-z][a-z\-]+)', re.I)


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


def _short(exc):
    return (str(exc) or type(exc).__name__)[:160]


def read_state(state, cycle, getter, spec=None):
    spec = spec or SOURCES[state]
    kind = spec.get('kind', 'page')
    page = _fill(spec['page'], cycle)
    base_out = {'state': state, 'kind': kind, 'page': page, 'used': [], 'tried': [], 'races': [], 'certified': False,
                'counties': None, 'fetched': time.time(), 'note': spec.get('note')}
    if kind in NOFETCH:
        return {**base_out, 'status': kind, 'error': spec.get('why')}

    contests, used, tried = [], [], []
    counties = {}                               # county-run sites (New Jersey): their counts add up
    county_sites = {'found': 0, 'read': 0}
    certified = [None]

    def note(url, outcome):
        tried.append({'url': url.split('|')[0], 'result': outcome[:160]})

    def get(url):
        try:
            return getter(url)
        except Exception as exc:
            note(url, _short(exc))
            raise

    def keep(url, got, county=False):
        if not any(classify(c['title'], state) for c in got):
            note(url, 'read, but no House, Senate or governor contests in it')
            return False
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
        return True

    def attempt(fn, url):
        try:
            return fn()
        except Exception as exc:
            if not tried or tried[-1]['url'] != url.split('|')[0]:
                note(url, _short(exc))
            return None

    def take_file(url):
        got = attempt(lambda: contests_from(get(url), spec.get('columns')), url)
        return keep(url, got) if got is not None else False

    def take_clarity(url):
        county = bool(CLARITY.match(url) and CLARITY.match(url).group(2))
        if county:
            county_sites['found'] += 1
        got = attempt(lambda: _clarity_contests(url, get), url)
        return keep(url, got, county) if got is not None else False

    def take_ev(base, jur, keys):
        label = f'{base}/results/public/api/elections/{jur}/{keys[0] if keys else ""}/data'
        res = attempt(lambda: _ev_api(base, jur, keys, get), label)
        if res is None:
            return False
        got, cert, url = res
        if cert is not None:
            certified[0] = cert
        return keep(url, got)

    def take_json(url, reader):
        got = attempt(lambda: reader(load_json(get(url))), url)
        return keep(url, got) if got is not None else False

    if kind == 'clarity':
        site = spec['site']
        eid = spec.get('eid') or attempt(lambda: _clarity_eid(site, cycle, get), f'{site}/elections.json')
        if eid:
            take_clarity(f"{site.rstrip('/')}/{eid}/")
    elif kind == 'ev_api':
        take_ev(spec['ev'][0], spec['ev'][1], [_fill(k, cycle) for k in spec.get('ev_keys') or [DATES[cycle].replace('-', '')]])
        if not used:
            for f in spec.get('feeds', []):
                if take_file(_fill(f, cycle)):
                    break
    elif kind in ('ev_export', 'files'):
        for f in spec.get('feeds', []):
            take_file(_fill(f, cycle))
    elif kind == 'ri':
        for f in spec['feeds']:
            take_json(_fill(f, cycle), read_ri)
    elif kind == 'oregon':
        for t in spec['types']:
            take_json(f"{spec['base']}?type={t}&category=SW&raceID=0&osn=0&county=0&party=0", read_oregon)
    elif kind == 'la':
        b = _fill(spec['base'], cycle)
        races = attempt(lambda: load_json(get(b + 'RacesCandidates_Multiparish.htm')), b + 'RacesCandidates_Multiparish.htm')
        if races is not None:
            u = b + 'Votes_Multiparish.htm'
            got = attempt(lambda: read_la(races, load_json(get(u))), u)
            if got is not None:
                keep(u, got)
    elif kind == 'nd':
        b, e = spec['base'], spec['eid']
        cu = f'{b}/Contest/GetContestSearchList?cid=north-dakota&electionID={e}'
        meta = attempt(lambda: load_json(get(cu)), cu)
        if meta is not None:
            ru = f'{b}/Contest/GetContestResults?cId=north-dakota&electionID={e}&contestType=SW'
            res = attempt(lambda: read_nd(meta, load_json(get(ru))), ru)
            if res is not None:
                got, official = res
                certified[0] = official
                keep(ru, got)
    elif kind == 'ct':
        b = spec['base']
        u = f'{b}/Elections.json'
        lst = attempt(lambda: load_json(get(u)), u)
        if lst is not None:
            m, d, y = DATE_TOKENS(cycle)[0].split('/')
            eid = next((str(e.get('ID')) for e in lst if str(e.get('Name', '')).startswith(f'{m}/{d}/{y}')), None)
            if not eid:
                note(u, 'opened, but this election is not listed yet')
            else:
                ver = attempt(lambda: load_json(get(f'{b}/election/{eid}/Version.json')).get('Version'), f'{b}/election/{eid}/Version.json')
                if ver is not None:
                    lu = f'{b}/election/{eid}/{ver}/Lookupdata.json'
                    du = f'{b}/election/{eid}/{ver}/Electiondata.json'
                    lk = attempt(lambda: load_json(get(lu)), lu)
                    if lk is not None:
                        got = attempt(lambda: read_ct(lk, load_json(get(du))), du)
                        if got is not None:
                            keep(du, got)
    elif kind == 'vt':
        b = spec['base']
        u = f'{b}/elections.json'
        lst = attempt(lambda: load_json(get(u)), u)
        if lst is not None:
            toks = DATE_TOKENS(cycle)
            guid = None
            for e in (lst if isinstance(lst, list) else lst.get('elections') or lst.get('d') or []):
                s = json.dumps(e)
                if any(t in s for t in toks) and re.search(r'general', s, re.I):
                    guid = e.get('electionGuid') or e.get('guid') or next(iter(re.findall(r'[0-9a-f]{8}-[0-9a-f-]{27}', s)), None)
                    break
            if not guid:
                note(u, 'opened, but this election is not listed yet')
            else:
                mu = f'{b}/{guid}.json'
                meta = attempt(lambda: load_json(get(mu)), mu)
                if meta is not None:
                    paths = [meta.get(k, {}).get('path') for k in ('federal', 'stateWide') if (meta.get(k) or {}).get('path')]
                    urls = [f"{b}/{p.replace(chr(92), '/').split('/')[-1]}" for p in paths]
                    files = [x for x in (attempt(lambda u=u2: load_json(get(u)), u2) for u2 in urls) if x is not None]
                    if files:
                        keep(urls[0], read_vt(files))
    elif kind == 'indiana':
        b = _fill(spec['base'], cycle)
        st = attempt(lambda: load_json(get(f'{b}/settings.json')), f'{b}/settings.json')
        if st is not None:
            v = ((st.get('Root') or {}).get('VersionType')) or 'A'
            if (st.get('Root') or {}).get('Certified') == 'T':
                certified[0] = True
            urls = [f'{b}/OffCatC_{cat}_{v}.json' for cat in (1005, 1006, 1007)]
            files = [x for x in (attempt(lambda u=u2: load_json(get(u)), u2) for u2 in urls) if x is not None]
            if files:
                keep(urls[0], read_indiana(files))
    elif kind == 'ohio':
        b = spec['base']
        lu = f'{b}/getContestList'
        lst = attempt(lambda: load_json(get(lu)), lu)
        if lst is not None:
            groups = [g for ct in (lst if isinstance(lst, list) else []) for g in (ct.get('contestGroupings') or [])
                      if g.get('contestObjectId') and classify(g.get('displayName') or g.get('contestName'), state)]
            details = []
            for g in groups[:30]:
                q = urllib.parse.urlencode({'contestName': g.get('contestName') or '', 'contestObjectId': g['contestObjectId'],
                                            'resultsLevel': '', 'countyId': ''})
                du = f'{b}/GetContestDetailsObject?{q}'
                d = attempt(lambda u=du: load_json(get(u)), du)
                if d is not None:
                    details.append(d)
            if details:
                keep(lu, read_ohio(details))
            elif not groups:
                note(lu, 'opened, but it lists no House, Senate or governor contests')
    elif kind == 'pa':
        b = spec['base']
        for off in spec['offices']:
            for active in ('1', '0'):
                u = f"{b}/GetOfficeData?officeId={off}&methodName=GetOfficeData&electionid={spec['eid']}&electiontype=G&isactive={active}"
                d = attempt(lambda: load_json(get(u)), u)
                if d and d.get('Election'):
                    keep(u, read_pa(d))
                    break
    elif kind == 'results_sw':
        eid = ''
        if spec.get('eid_from'):
            y, m, d = DATES[cycle].split('-')
            html_ = attempt(lambda: decode(get(spec['eid_from'])), spec['eid_from'])
            mm = re.search(r'<option[^>]*value="(\d+)"[^>]*>[^<]*' + re.escape(f'{m}/{d}/{y}') + r'[^<]*General', html_ or '', re.I)
            if mm:
                eid = f'&eid={mm.group(1)}'
            elif html_ is not None:
                note(spec['eid_from'], 'opened, but this election is not listed yet')
        if not spec.get('eid_from') or eid:
            for t in spec['types']:
                u = f"{spec['base']}?{spec.get('extra', '')}type={t}&map=CTY{eid}"
                txt = attempt(lambda: decode(get(u)), u)
                if txt is None:
                    continue
                years = set(re.findall(r'\b(20[1-3]\d)\b', re.sub(r'<script.*?</script>', '', txt, flags=re.S)))
                if years and DATES[cycle][:4] not in years:
                    note(u, 'opened, but it shows another election')
                    continue
                keep(u, read_results_sw(txt))
    elif kind == 'ks':
        for u in spec['feeds']:
            txt = attempt(lambda: decode(get(u)), u)
            if txt is None:
                continue
            stamp = re.search(r"time-stamp'?\s*>\s*(\d{1,2})/(\d{1,2})/(\d{4})", txt)
            if stamp:
                import datetime as _dt
                seen = _dt.date(int(stamp.group(3)), int(stamp.group(1)), int(stamp.group(2)))
                if (_dt.date.fromisoformat(DATES[cycle]) - seen).days > 45:
                    note(u, 'opened, but it still shows an earlier election')
                    continue
            keep(u, read_ks(txt))
    elif kind == 'il':
        txt = attempt(lambda: decode(get(page)), page)
        if txt is not None:
            if _page_date_ok(txt, cycle, ('GENERAL',)) and re.search(rf'{DATES[cycle][:4]}\s+GENERAL', txt.upper()):
                keep(page, read_html(txt))
            else:
                note(page, 'opened, but it shows another election')
    if kind == 'page' or (not used and kind not in ('il',) and not tried):
        text = ''
        try:
            text = decode(get(page))
        except Exception:
            pass
        for k, url in discover(text, page, cycle) if text else []:
            if k == 'clarity':
                take_clarity(url)
            elif k == 'ev':
                b, j = url.split('|')
                take_ev(b, j, [DATES[cycle].replace('-', '')])
            else:
                take_file(url)
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
    return {**base_out, 'status': status, 'races': races, 'used': used[:5], 'tried': tried[-12:],
            'error': None if races and not partial else err, 'certified': bool(certified[0]) if races else False,
            'counties': county_sites if county_sites['found'] else None}


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


# ------------------------------------------------------------------ all states, in the background
_lock = threading.Lock()
_jobs = {}


def sources():
    out = {k: dict(v) for k, v in SOURCES.items()}
    try:
        extra = json.loads((OUT / 'state_sources.json').read_text(encoding='utf-8'))
        for st, v in extra.items():
            if st in out and isinstance(v, dict):
                out[st].update({k: v[k] for k in ('page', 'feeds', 'columns', 'ev', 'ev_keys', 'kind', 'site', 'eid', 'base') if k in v})
    except (OSError, ValueError):
        pass
    return out


def _file(cycle):
    return OUT / f'state_counts_{cycle}.json'


FIELDS = ('status', 'kind', 'page', 'used', 'error', 'fetched', 'tried', 'certified', 'counties', 'note')


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
    out['states'] = {k: {**{x: v.get(x) for x in FIELDS}, 'races': len(v.get('races', []))} for k, v in states.items()}
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
        m['origin'], m['source'], m['wiki_status'] = 'wikipedia+' + s.get('origin', 'state'), s['source'], w.get('status_text')
        if w.get('called') and w.get('winner_party') and s.get('total'):
            if s.get('leader_party') == w['winner_party']:
                cands = json.loads(s['cands'])
                for c in cands:
                    c[4] = int(c[1] == w['winner_party'] and c[0] == s['leader'])
                m['cands'] = json.dumps(cands)
            else:
                where = f"{name_of(s['state'])}'s count" if s.get('origin', 'state') == 'state' else 'news coverage of the count'
                m.update(called=0, winner=None, winner_party=None,
                         status_text=f"Wikipedia lists {w.get('winner') or 'a winner'} ({w['winner_party']}), but {where} "
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
