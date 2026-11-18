"""Geopolitics reel: recent news videos from global broadcasters.

Picks uploads from the last 24 hours (by default) from international news channels,
keeps news only (no shorts, sport, entertainment or lifestyle), scores each title for
geopolitical relevance, and interleaves channels so one broadcaster can't fill the reel.
Only videos YouTube confirms are public and embeddable are offered, and videos that
failed to play in this browser are left out.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import OrderedDict

# Not news, whatever the channel.
NOT_NEWS = [
    r'#shorts?\b', r'\bshorts?\b', r'\bpodcast\b', r'\btrailer\b', r'\bteaser\b', r'\bmusic video\b', r'\bconcert\b',
    r'\brecipe\b', r'\bcooking\b', r'\btravel guide\b', r'\bfashion\b', r'\bred carpet\b', r'\bcelebrit(y|ies)\b',
    r'\bmovie\b', r'\bfilm review\b', r'\bbox office\b', r'\boscars?\b', r'\bgrammys?\b', r'\bhoroscope\b', r'\basmr\b',
    r'\bunboxing\b', r'\bquiz\b', r'\bgiveaway\b', r'\bsubscribe\b', r'\bfootball\b', r'\bsoccer\b', r'\bcricket\b',
    r'\bpremier league\b', r'\bchampions league\b', r'\bworld cup\b', r'\bolympics?\b', r'\bformula (1|one)\b', r'\bf1\b',
    r'\btennis\b', r'\bwimbledon\b', r'\bnba\b', r'\bnfl\b', r'\bgolf\b', r'\brugby\b', r'\bmatch highlights\b',
    r'\bpress conference after\b.*\bmatch\b', r'\bweather forecast\b', r'\blifestyle\b', r'\bbehind the scenes\b',
]
NOT_NEWS_RE = re.compile('|'.join(NOT_NEWS), re.I)

# Geopolitical signal. Two points for strong terms, one for broader ones.
STRONG = [
    'war', 'warfare', 'ceasefire', 'truce', 'invasion', 'missile', 'missiles', 'airstrike', 'airstrikes', 'drone strike',
    'troops', 'military', 'army', 'navy', 'nuclear', 'sanctions', 'nato', 'united nations', 'security council',
    'summit', 'diplomacy', 'diplomat', 'diplomats', 'diplomatic', 'foreign minister', 'foreign secretary',
    'secretary of state', 'defence minister', 'defense secretary', 'treaty', 'annexation', 'coup', 'insurgency',
    'militants', 'hostage', 'hostages', 'border clash', 'peace talks', 'peace deal', 'geopolitic', 'tariff', 'tariffs',
    'trade war', 'embargo', 'iaea', 'enrichment', 'g7', 'g20', 'brics', 'sco', 'asean', 'opec', 'refugees',
]
BROAD = [
    'president', 'prime minister', 'chancellor', 'government', 'election', 'elections', 'parliament', 'protest',
    'protests', 'border', 'attack', 'strike', 'strikes', 'conflict', 'crisis', 'talks', 'deal', 'minister', 'kremlin',
    'white house', 'pentagon', 'state department', 'eu', 'european union', 'un', 'embassy', 'spy', 'cyberattack',
    'ukraine', 'russia', 'china', 'taiwan', 'iran', 'israel', 'gaza', 'west bank', 'lebanon', 'hezbollah', 'hamas',
    'houthi', 'houthis', 'yemen', 'syria', 'iraq', 'afghanistan', 'pakistan', 'india', 'kashmir', 'north korea',
    'south korea', 'japan', 'philippines', 'south china sea', 'red sea', 'hormuz', 'sudan', 'ethiopia', 'somalia',
    'sahel', 'mali', 'niger', 'congo', 'libya', 'venezuela', 'cuba', 'mexico', 'turkey', 'saudi', 'qatar', 'egypt',
    'moscow', 'kyiv', 'kiev', 'beijing', 'tehran', 'jerusalem', 'washington', 'brussels', 'putin', 'zelensky',
    'xi jinping', 'netanyahu', 'modi', 'trump', 'erdogan', 'khamenei', 'kim jong',
]


GEO_MIN = 2  # one strong term, or two broader ones


def _terms_re(terms):
    return re.compile(r'\b(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')\b', re.I)


STRONG_RE, BROAD_RE = _terms_re(STRONG), _terms_re(BROAD)


def classify(title: str, summary: str = '') -> dict:
    """Return {'news': bool, 'geo': int, 'terms': [...]} for one video."""
    title = title or ''
    text = f'{title} {(summary or "")[:300]}'
    if NOT_NEWS_RE.search(title):
        return {'news': False, 'geo': 0, 'terms': []}
    strong = {m.group(1).lower() for m in STRONG_RE.finditer(text)}
    broad = {m.group(1).lower() for m in BROAD_RE.finditer(text)} - strong
    return {'news': True, 'geo': 2 * len(strong) + len(broad), 'terms': sorted(strong) + sorted(broad)}


def _when(row):
    t = row.get('published') or row.get('retrieved') or ''
    try:
        return dt.datetime.fromisoformat(t.replace('Z', '+00:00'))
    except Exception:
        return None


def interleave(items, key=lambda x: x['source_id']):
    """Round-robin across channels, newest first within each channel."""
    queues = OrderedDict()
    for it in items:
        queues.setdefault(key(it), []).append(it)
    out = []
    while queues:
        for k in list(queues):
            out.append(queues[k].pop(0))
            if not queues[k]:
                del queues[k]
    return out


def select(rows, states, channels, hours=24, geo_only=True, now=None, hidden=()):
    """Choose reel videos.

    rows: entry dicts (medium video) with id, source_id, title, summary, video_id, published.
    states: video_id -> video_status row. channels: source_id -> channel config.
    Returns (videos, counts) where counts explain what was left out.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=hours)
    counts = {'recent': 0, 'not_news': 0, 'not_geopolitics': 0, 'awaiting_check': 0, 'not_playable': 0, 'removed': 0}
    seen, keep = set(), []
    for r in rows:
        if r.get('source_id') not in channels or not r.get('video_id'):
            continue
        when = _when(r)
        if not when or when < cutoff or when > now + dt.timedelta(hours=1):
            continue
        if r['video_id'] in seen:
            continue
        seen.add(r['video_id'])
        counts['recent'] += 1
        if r['id'] in hidden:
            counts['removed'] += 1
            continue
        c = classify(r.get('title', ''), r.get('summary', ''))
        if not c['news']:
            counts['not_news'] += 1
            continue
        if geo_only and c['geo'] < GEO_MIN:
            counts['not_geopolitics'] += 1
            continue
        st = states.get(r['video_id']) or {}
        if st.get('state') != 'playable':
            counts['awaiting_check' if not st or st.get('state') == 'error' else 'not_playable'] += 1
            continue
        ch = channels[r['source_id']]
        keep.append({'id': r['id'], 'video_id': r['video_id'], 'title': r.get('title', ''), 'source_id': r['source_id'],
                     'channel': ch.get('name', r.get('source', '')), 'region': ch.get('region', ''),
                     'published': r.get('published') or r.get('retrieved'), 'thumbnail': st.get('thumbnail') or
                     f"https://i.ytimg.com/vi/{r['video_id']}/hqdefault.jpg", 'geo': c['geo'], 'terms': c['terms'][:6]})
    keep.sort(key=lambda v: v['published'] or '', reverse=True)
    return interleave(keep), counts
