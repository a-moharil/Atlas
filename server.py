#!/usr/bin/env python3
"""India & World Observatory — local-first geopolitical research server.

Only built-in Python packages. No scraper, no credentials required for RSS.
The external network is used only by the running server. Data is persisted to SQLite.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import atlas_plus
import atlas_v3
import india_intel
import expert_research
import article_clusters
import tile_gateway
import content_cleanup
import mygov
import emergency
import conflict_watch
import retrieval_jobs
import publishers
import video_check
import earth_watch
import logos
import semantic
import lm_labels
import research_radar
import coverage_graph
import geo_video
import find
import wiki
import ask
import elections
import elections_data
import officials
import forecast
import pulse
import us_elections
import us_elections_data
import us_officials
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
REGISTRY = json.loads((ROOT / 'source_registry.json').read_text(encoding='utf-8'))
PROFILES = json.loads((STATIC / 'publisher_profiles.json').read_text(encoding='utf-8'))
DB_FILE = Path(os.environ.get('OBS_DB', str(ROOT / 'observatory.sqlite3')))
REFRESH_SECONDS = max(300, int(os.environ.get('OBS_REFRESH_SECONDS', str(REGISTRY['refresh_minutes'] * 60))))
USER_AGENT = 'IndiaWorldResearchObservatory/1.0 (+research dashboard; feed reader)'
MAX_XML_BYTES = 2_500_000
SKIP_NETWORK = os.environ.get('OBS_SKIP_NETWORK') == '1'
NETWORK_TIMEOUT = 12
NEWS_LIMIT = 4000
STATE_LOCK = threading.RLock()
FETCH_RUNNING = False
LAST_CYCLE = None
LIVE_CHECK_LOCK = threading.Lock()
LIVE_REFRESH_SECONDS = max(300, int(os.environ.get("ATLAS_LIVE_REFRESH_SECONDS", "900")))
LAST_LIVE_CHECK = 0.0


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def db_connect():
    con = sqlite3.connect(DB_FILE, timeout=12)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout = 12000')
    return con


def init_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with closing(db_connect()) as con:
        con.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source TEXT NOT NULL,
            tier TEXT NOT NULL, region TEXT NOT NULL, medium TEXT NOT NULL,
            title TEXT NOT NULL, url TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '',
            published TEXT, retrieved TEXT NOT NULL, video_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_entries_published ON entries(published DESC);
        CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source_id);
        CREATE TABLE IF NOT EXISTS feeds_status (
            id TEXT PRIMARY KEY, attempted TEXT, success TEXT, state TEXT,
            count INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS live_channel_status (
            id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'unknown',
            checked TEXT, last_verified TEXT, video_id TEXT,
            title TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS custom_feeds (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
            tier TEXT NOT NULL, region TEXT NOT NULL, site TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS annotations (
            entry_id TEXT PRIMARY KEY, starred INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watch_terms (
            term TEXT PRIMARY KEY, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wall_hidden (
            entry_id TEXT PRIMARY KEY, created TEXT NOT NULL
        );
        ''')
        cols={r[1] for r in con.execute('PRAGMA table_info(entries)')}
        if 'author' not in cols: con.execute("ALTER TABLE entries ADD COLUMN author TEXT NOT NULL DEFAULT ''")
        if 'origin_host' not in cols: con.execute("ALTER TABLE entries ADD COLUMN origin_host TEXT NOT NULL DEFAULT ''")
        atlas_plus.init_geo(con)
        atlas_v3.init(con)
        content_cleanup.init(con)
        emergency.init(con)
        publishers.init(con)
        video_check.init(con)
        semantic.init(con)
        lm_labels.init(con)
        research_radar.init(con)
        con.commit()
    publishers.set_feeds(all_feed_configs())
    content_cleanup.EXTRA_FILTER=publishers.visibility_clause


def clean_text(value):
    if not value:
        return ''
    plain = re.sub(r'<[^>]+>', ' ', html.unescape(str(value)))
    plain = re.sub(r'\s+', ' ', plain).strip()
    return plain[:900]


def normalize_date(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        pass
    try:
        d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        return None


def localname(tag):
    return tag.rsplit('}', 1)[-1].lower()


def child_text(elem, *names):
    for candidate in elem:
        if localname(candidate.tag) in names:
            return ''.join(candidate.itertext()).strip()
    return ''


def parse_feed(content: bytes, source: dict, medium='article'):
    """Parse conventional RSS 2.0 or Atom (including YouTube's Atom feeds)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f'Not valid RSS/Atom XML: {exc}') from exc
    records = []
    video_mode = medium == 'video'
    items = [node for node in root.iter() if localname(node.tag) in ('item', 'entry')]
    for node in items[:60]:
        title = clean_text(child_text(node, 'title'))[:320]
        link = ''
        for item in node:
            if localname(item.tag) == 'link':
                if item.attrib.get('href'):
                    if not link or item.attrib.get('rel', 'alternate') == 'alternate':
                        link = item.attrib['href']
                else:
                    link = (item.text or '').strip() or link
        if not link:
            link = child_text(node, 'guid', 'id')
        pub = normalize_date(child_text(node, 'pubdate', 'published', 'updated', 'date', 'issued'))
        summary = clean_text(child_text(node, 'description', 'summary', 'content'))[:500]
        author = clean_text(child_text(node, 'author', 'creator'))[:150]
        origin = ''
        for item in node:
            if localname(item.tag) == 'source' and item.attrib.get('url'):
                origin = publishers.host_of(item.attrib['url'])
                break
        video_id = child_text(node, 'videoid') if video_mode else None
        if video_mode and not video_id:
            match = re.search(r'(?:youtu\.be/|[?&]v=|/watch/)([\w-]{11})', link)
            video_id = match.group(1) if match else None
        if video_mode and video_id:
            link = 'https://www.youtube.com/watch?v=' + video_id
        if not title or not link.startswith(('https://', 'http://')):
            continue
        # Prevent presentation-layer script injection: frontend only uses textContent.
        uid = hashlib.sha256((source['id'] + '\n' + link).encode()).hexdigest()[:24]
        records.append(dict(id=uid, source_id=source['id'], source=source['name'],
                            tier=source.get('tier', 'reporting'), region=source.get('region', 'Global'),
                            medium=medium, title=title, url=link, summary=summary,
                            published=pub, retrieved=utc_now(), video_id=video_id, author=author, origin_host=origin))
    return records


# Only shipped provider hosts may rely on an explicitly configured HTTPS proxy's
# DNS when local DNS is unavailable. User-added feeds retain public-IP validation.
PROXY_PROVIDER_HOSTS={urllib.parse.urlparse(f.get('url','')).hostname for f in REGISTRY['feeds']} | earth_watch.HOSTS | {
 'www.arcgis.com','www.pib.gov.in','pib.gov.in','api.worldbank.org','comtradeapi.un.org','api.openalex.org','www.youtube.com',
 'eonet.gsfc.nasa.gov','earthquake.usgs.gov','api.open-meteo.com',
 'public.api.bsky.app','static.geodataviewer.com'}

def validate_external_url(url, allow_http=False):
    """Disallow local/private target URLs for user-defined RSS and redirects."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in (('https', 'http') if allow_http else ('https',)) or not p.hostname or p.username or p.password:
        raise ValueError('A public HTTPS feed URL is required.')
    if p.port not in (None, 443, 80 if allow_http else 443):
        raise ValueError('Only standard HTTPS ports are allowed.')
    host = p.hostname.lower()
    if host in ('localhost', 'localhost.localdomain') or host.endswith(('.local', '.internal', '.test')):
        raise ValueError('Local addresses are not permitted.')
    try:
        resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        for item in resolved:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                raise ValueError('RSS URL resolves to a non-public IP address.')
    except socket.gaierror as exc:
        if host in PROXY_PROVIDER_HOSTS and urllib.request.getproxies().get('https'):
            return url
        raise ValueError(f'Cannot resolve feed host: {host}') from exc
    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_external_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicRecordRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_external_url(newurl, allow_http=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


STATE_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 '
            'Sanjaya/6.5 (+https://github.com/a-moharil/Atlas)')


def fetch_public_record(url, max_bytes=60_000_000, timeout=45):
    """State election results sites: many sit behind firewalls that refuse requests without browser-like headers,
    and a few still serve plain HTTP. Same public-address checks as every other fetch; errors name the HTTP status."""
    validate_external_url(url, allow_http=True)
    req = urllib.request.Request(url, headers={'User-Agent': STATE_UA, 'Accept-Language': 'en-US,en;q=0.9',
                                               'Accept': 'text/html,application/xhtml+xml,application/json,text/csv,text/plain,*/*;q=0.8'})
    try:
        with urllib.request.build_opener(PublicRecordRedirectHandler()).open(req, timeout=timeout) as res:
            block = res.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise OSError(f'HTTP {exc.code} {exc.reason or ""}'.strip()) from None
    except urllib.error.URLError as exc:
        raise OSError(f'not reachable ({exc.reason})') from None
    if len(block) > max_bytes:
        raise ValueError('response larger than 60 MB')
    return block


def fetch_bytes(url, max_bytes=MAX_XML_BYTES, timeout=None):
    validate_external_url(url)
    opener = urllib.request.build_opener(SafeRedirectHandler())
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                              'Accept': 'application/rss+xml, application/atom+xml, application/xml, application/json, */*'})
    with opener.open(req, timeout=timeout or NETWORK_TIMEOUT) as res:
        block = res.read(max_bytes + 1)
    if len(block) > max_bytes:
        raise ValueError('Source response exceeded size limit')
    return block


def research_fetch(url, max_bytes=MAX_XML_BYTES):
    # Background worker only; longer read budget does not block local HTTP requests.
    for attempt in range(2):
        try:return fetch_bytes(url,max_bytes,timeout=30)
        except (TimeoutError, urllib.error.URLError, OSError):
            if attempt:raise
            time.sleep(0.5)


def all_feed_configs():
    result = list(REGISTRY['feeds'])
    with closing(db_connect()) as con:
        for row in con.execute('SELECT * FROM custom_feeds ORDER BY name'):
            result.append({**dict(row), 'mode': 'Custom HTTPS RSS'})
    publishers.set_feeds(result)
    return result


def persist_records(rows):
    if not rows:
        return 0
    with closing(db_connect()) as con:
        # Classify once on ingestion. Active genre blocks prevent NEW matching
        # documents from entering the archive; existing records stay recoverable.
        active_genres=content_cleanup.active(con)
        blocked_hosts=publishers.blocked_hosts(con)
        accepted=[]
        skipped=[]
        for entry in rows:
            entry.setdefault('origin_host','')
            if entry['origin_host'] and entry['origin_host'] in blocked_hosts:
                continue
            genre=content_cleanup.classify(entry.get('title',''),entry.get('summary','')) if entry.get('medium')=='article' else ''
            if genre in active_genres:
                skipped.append((entry['id'],entry['source_id'],genre,utc_now()))
                continue
            accepted.append({**entry,'genre':genre})
        rows=accepted
        if skipped:
            con.executemany('INSERT OR IGNORE INTO cleanup_skips(item_id,source_id,genre,first_seen) VALUES(?,?,?,?)',skipped)
            con.commit()
        if not rows:return 0
        known = {r[0] for r in con.execute('SELECT id FROM entries WHERE id IN ('+','.join('?' for x in rows)+')',[x['id'] for x in rows])}
        con.executemany('''INSERT INTO entries(id,source_id,source,tier,region,medium,title,url,summary,published,retrieved,video_id,author,genre,origin_host)
            VALUES(:id,:source_id,:source,:tier,:region,:medium,:title,:url,:summary,:published,:retrieved,:video_id,:author,:genre,:origin_host)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,
                retrieved=excluded.retrieved,published=COALESCE(excluded.published, entries.published),author=excluded.author,genre=excluded.genre,origin_host=CASE WHEN excluded.origin_host!='' THEN excluded.origin_host ELSE entries.origin_host END''', rows)
        # Keep finite history, never fabricate current records.
        con.execute('''DELETE FROM entries WHERE id NOT IN (
            SELECT id FROM entries ORDER BY COALESCE(published,retrieved) DESC LIMIT 14000)''')
        con.commit()
        return sum(x["id"] not in known for x in rows)


def write_status(source_id, success=False, count=0, error=''):
    now = utc_now()
    with closing(db_connect()) as con:
        con.execute('''INSERT INTO feeds_status(id,attempted,success,state,count,error)
            VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            attempted=excluded.attempted,
            success=CASE WHEN excluded.state='ok' THEN excluded.success ELSE feeds_status.success END,
            state=excluded.state,count=excluded.count,error=excluded.error''',
                    (source_id, now, now if success else None, 'ok' if success else 'error', count, error[:260]))
        con.commit()


def fetch_source(source, medium='article',run_id=None):
    start_ts=utc_now()
    start_mon=time.monotonic()
    returned=0; inserted=0; error=''; success=False
    try:
        rows = parse_feed(fetch_bytes(source['url']), source, medium)
        if not rows:
            raise ValueError('Feed returned no usable items (source may have changed).')
        if source.get('isw'):
            for row in rows:row['summary']=''  # Store discovery metadata only, not copied reports.
        returned=len(rows)
        inserted=persist_records(rows)
        write_status(source['id'],success=True,count=returned)
        success=True
        return returned
    except Exception as exc:
        error=f'{type(exc).__name__}: {str(exc)[:180]}'
        write_status(source['id'],error=error)
        return 0
    finally:
        atlas_v3.record(db_connect,run_id,source['id'],start_ts,utc_now(),success,returned,inserted,error,1000*(time.monotonic()-start_mon))


def fetch_openalex(query):
    from_date = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    params = urllib.parse.urlencode(dict(search=query['query'], filter=f'from_publication_date:{from_date}',
                                          sort='publication_date:desc', per_page=15,
                                          select='id,title,doi,publication_date,authorships,primary_location,open_access,cited_by_count'))
    response = json.loads(fetch_bytes('https://api.openalex.org/works?' + params, 2_000_000).decode('utf-8'))
    rows = []
    for work in response.get('results', []):
        if not work.get('title'):
            continue
        authors = ', '.join(a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])[:4])
        doi = work.get('doi') or work.get('id') or ''
        url = doi if doi.startswith('https://') else str(work.get('id', ''))
        rows.append(dict(id=hashlib.sha256((query['id'] + url).encode()).hexdigest()[:24],
                         source_id='openalex_' + query['id'], source='OpenAlex · ' + query['name'],
                         tier='research', region='India' if query['id'] == 'india' else 'Global',
                         medium='paper', title=clean_text(work['title'])[:320], url=url,
                         summary=(authors + (' · ' if authors else '') +
                                  f"Citations: {work.get('cited_by_count', 0)}" +
                                  (" · OA" if (work.get('open_access') or {}).get('is_oa') else ''))[:500],
                         published=normalize_date(str(work.get('publication_date', '')) + 'T00:00:00Z'),
                         retrieved=utc_now(), video_id=None, author=authors[:150]))
    persist_records(rows)
    write_status('openalex_' + query['id'], success=True, count=len(rows))


def fetch_papers(scope="all"):
    for query in REGISTRY['research']:
        if scope=="mygov" and not query["id"].startswith("mygov_"):continue
        try:
            fetch_openalex(query)
        except Exception as exc:
            write_status('openalex_' + query['id'], error=f'{type(exc).__name__}: {str(exc)[:180]}')


def refresh_cycle(force_local=False, claimed=False, scope="all"):
    global FETCH_RUNNING, LAST_CYCLE
    with STATE_LOCK:
        if FETCH_RUNNING and not claimed:
            return
        FETCH_RUNNING = True
    run_id = None
    try:
        run_id = atlas_v3.run_start(db_connect,utc_now)
        sources = all_feed_configs()
        with closing(db_connect()) as con:blocked=publishers.blocked_hosts(con)
        sources=[f for f in sources if not publishers.feed_blocked(f,blocked)]
        if scope=="mygov":sources=[f for f in sources if f.get("mygov")]
        elif scope=="conflict":sources=[f for f in sources if f.get("isw")]
        elif scope=="emergency":
            with closing(db_connect()) as con:source_rules=emergency.rules(con)
            sources=[f for f in sources if not emergency.blocked(emergency.source_info(f),source_rules) and f.get('desk') in ('World','India','Policy','Finance','Energy','Conflict')]
            sources.sort(key=lambda f:0 if emergency.source_info(f)['family'] in ('wires','broadcast') else 1)
        # Local regional discovery is rate-limited separately. Forced user refresh
        # can bypass the hourly cadence; failed requests remain auditable.
        if not force_local:
            with closing(db_connect()) as con:
                checks={r['id']:r['attempted'] for r in con.execute('SELECT id,attempted FROM feeds_status')}
            due=[]
            for f in sources:
                if f.get('local_city') or f.get('local_state'):
                    t=checks.get(f['id'])
                    try: elapsed=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds() if t else 999999
                    except Exception: elapsed=999999
                    if elapsed<3600:continue
                due.append(f)
            sources=due
        if scope=='all':sources += [{**c, 'tier': 'video', 'url': 'https://www.youtube.com/feeds/videos.xml?channel_id=' + c['channel_id']} for c in REGISTRY['channels']+geo_reel_channels(extra_only=True)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pending = [pool.submit(fetch_source, f, 'video' if 'channel_id' in f else 'article', run_id) for f in sources]
            for future in concurrent.futures.as_completed(pending):
                try: future.result()
                except Exception: pass
        # Current /live status is checked separately from Atom upload feeds.
        if scope=="all":
            refresh_live_channels()
            verify_videos()
        threading.Thread(target=lm_work,daemon=True,name='lm-work').start()
        if not SKIP_NETWORK:radar_tick()
        # Papers refresh only once per 12 hours (or when there is no successful paper fetch).
        with closing(db_connect()) as con:
            sample = con.execute("SELECT success FROM feeds_status WHERE id='openalex_india'").fetchone()
        last = sample['success'] if sample else None
        if scope in ("all","mygov") and (force_local or last is None or (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last.replace('Z', '+00:00'))).total_seconds() > 43200):
            fetch_papers(scope)
        # Environmental layers have independent, transparent source timestamps.
        with closing(db_connect()) as con:
            atlas_plus.init_geo(con)
            geo_check=con.execute("SELECT MAX(retrieved) AS latest FROM geo_layers").fetchone()
        geo_last=geo_check['latest'] if geo_check else None
        if scope=="all" and (geo_last is None or (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(geo_last.replace('Z','+00:00'))).total_seconds() > 1800):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as geo_pool:
                list(geo_pool.map(lambda name: atlas_plus.fetch_one_layer(name,fetch_bytes,db_connect,utc_now), atlas_plus.LAYER_SOURCES))
    finally:
        try:
            if run_id is not None:atlas_v3.run_finish(db_connect, run_id, utc_now)
        finally:
            with STATE_LOCK:
                LAST_CYCLE = utc_now()
                FETCH_RUNNING = False


def start_refresh(force_local=False, scope="all"):
    global FETCH_RUNNING
    with STATE_LOCK:
        if FETCH_RUNNING:
            return False
        FETCH_RUNNING=True
        threading.Thread(target=refresh_cycle,kwargs={'force_local':force_local,'claimed':True,'scope':scope},daemon=True,name='feed-refresh').start()
        return True


def poll_loop():
    if os.environ.get('OBS_SKIP_NETWORK') != '1':
        start_refresh()
    while True:
        time.sleep(REFRESH_SECONDS)
        if os.environ.get('OBS_SKIP_NETWORK') != '1':
            start_refresh()


# The official /live endpoint is inspected, not a third-party stream mirror.
# YouTube sometimes serves consent, anti-bot or cached pages. In such cases the
# status stays "unverified" and the broadcaster's official page is offered.
def parse_official_live_page(payload: bytes, final_url: str) -> dict:
    page = payload.decode('utf-8', errors='replace')
    # isLiveNow (not isLiveContent) distinguishes a presently active stream
    # from a replay of an old live broadcast.
    is_live = (bool(re.search(r'"isLiveNow"\s*:\s*true', page, re.I)) or
               bool(re.search(r'"isLive"\s*:\s*true', page, re.I) and
                    re.search(r'"isLiveContent"\s*:\s*true', page, re.I)))
    if not is_live:
        return dict(state='unverified', video_id=None, title='', reason='No positively verified live stream in broadcaster response')
    # Derive the ID only from official watch URL, page/player fields, or a canonical tag.
    parsed = urllib.parse.urlparse(final_url)
    video_id = urllib.parse.parse_qs(parsed.query).get('v', [''])[0] if parsed.path == '/watch' else ''
    if not re.fullmatch(r'[\w-]{11}', video_id):
        for expr in (r'"videoDetails"\s*:\s*\{.{0,1500}?"videoId"\s*:\s*"([\w-]{11})"',
                     r'<link[^>]+rel="canonical"[^>]+href="https://www\.youtube\.com/watch\?v=([\w-]{11})"',
                     r'"videoId"\s*:\s*"([\w-]{11})"'):
            match=re.search(expr, page, re.S)
            if match: video_id=match.group(1);break
    if not re.fullmatch(r'[\w-]{11}', video_id):
        return dict(state='unverified', video_id=None, title='', reason='Live flag found, but no verified watch ID')
    title_match=re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',page)
    return dict(state='live', video_id=video_id, title=html.unescape(title_match.group(1))[:160] if title_match else 'Live coverage', reason='Official YouTube live page reports active broadcast')


def inspect_official_live(channel: dict) -> dict:
    url='https://www.youtube.com/channel/'+channel['channel_id']+'/live'
    validate_external_url(url)
    opener=urllib.request.build_opener(SafeRedirectHandler())
    req=urllib.request.Request(url,headers={
      'User-Agent':'Mozilla/5.0 (compatible; ATLASLiveChannelCheck/1.0)',
      'Accept':'text/html,application/xhtml+xml', 'Accept-Language':'en-US,en;q=0.8'})
    with opener.open(req, timeout=NETWORK_TIMEOUT) as response:
        buf=response.read(3_200_001)
        final=response.geturl()
    if len(buf)>3_200_000: raise ValueError('YouTube page exceeds safety limit')
    return parse_official_live_page(buf,final)


def refresh_live_channels(force=False):
    global LAST_LIVE_CHECK
    if not LIVE_CHECK_LOCK.acquire(blocking=False): return False
    try:
        if not force and time.monotonic()-LAST_LIVE_CHECK<LIVE_REFRESH_SECONDS:
            return False
        LAST_LIVE_CHECK=time.monotonic()
        def check(config):
            try:
                result=inspect_official_live(config)
                return config['id'],result,None
            except Exception as exc:
                return config['id'],{},f'{type(exc).__name__}: {str(exc)[:160]}'
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(check,REGISTRY.get('live_channels',[])))
        with closing(db_connect()) as con:
            for key,result,err in results:
                now=utc_now()
                if err:
                    # A failed network check cannot establish that a stream ended.
                    con.execute('''INSERT INTO live_channel_status(id,state,checked,error) VALUES(?, 'unverified', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET state='unverified',checked=excluded.checked,error=excluded.error,
                    video_id=NULL,title='' ''',(key,now,err))
                else:
                    state=result['state']; vid=result.get('video_id'); title=result.get('title','')
                    con.execute('''INSERT INTO live_channel_status(id,state,checked,last_verified,video_id,title,error)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state,checked=excluded.checked,
                    last_verified=CASE WHEN excluded.state='live' THEN excluded.checked ELSE live_channel_status.last_verified END,
                    video_id=excluded.video_id,title=excluded.title,error=excluded.error''',
                    (key,state,now,now if state=='live' else None,vid,title,'' if state=='live' else result.get('reason','')))
            con.commit()
        return True
    finally:
        LIVE_CHECK_LOCK.release()


LM_BUSY=threading.Lock()
_GRAPH_STATE = {'t': 0.0, 'entries': None}
GRAPH_DESKS = {'World', 'India', 'Policy', 'Technology', 'Finance', 'Energy'}


def graph_entries():
    """Entries exactly as the page sees them (same story groups and publishers), cached for 30 s."""
    if _GRAPH_STATE['entries'] is None or time.time() - _GRAPH_STATE['t'] > 30:
        _GRAPH_STATE.update(t=time.time(), entries=read_state()['entries'])
    return _GRAPH_STATE['entries']


def graph_pref():
    with closing(db_connect()) as con:
        prefs = publishers.prefs(con)
    return lambda h: prefs.get(h, '')


def search_further(terms, gaps, desk):
    """Fetch new articles for a diffused story through Google News: one open query, then one per
    outlet that has not covered it. New articles join the seed's desk and are embedded in the background."""
    terms = [re.sub(r'[^\w\s\-.]', ' ', str(t))[:60].strip() for t in terms if str(t).strip()][:5]
    if not terms:
        raise ValueError('No search terms for this story.')
    gaps = [g for g in gaps if re.fullmatch(r'[a-z0-9.-]{3,80}', str(g))][:3]
    desk = desk if desk in GRAPH_DESKS else 'World'
    r = fetch_google(coverage_graph.search_queries(terms, gaps), desk)
    r.pop('ids', None)
    return r


def fetch_google(queries, desk):
    """Run Google News RSS searches; new articles join the desk as 'Search further' records."""
    source = {'id': f'expand:{desk}', 'name': 'Search further', 'tier': 'reporting', 'region': 'Global', 'desk': desk}
    added, fetched, notes, ids = 0, 0, [], []
    for q in queries:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'})
        try:
            rows = parse_feed(fetch_bytes(url), source, 'article')
            for r in rows:  # Google News appends " - Publisher"; the publisher is kept separately
                r['title'] = coverage_graph.clean_title(r.get('title', ''))
            fetched += len(rows)
            added += persist_records(rows) or 0
            ids += [r['id'] for r in rows]
        except Exception as exc:
            notes.append(f'{q[:40]}…: {type(exc).__name__}')
    _GRAPH_STATE['entries'] = None
    if added:
        threading.Thread(target=lm_work, kwargs={'label': False}, daemon=True, name='lm-expand').start()
    return {'queries': len(queries), 'fetched': fetched, 'added': added, 'notes': notes, 'ids': list(dict.fromkeys(ids))}


def _single(e):
    """Publisher details for an article that isn't in the page's current state (no story group)."""
    h = publishers.entry_host(e)
    pr = publishers.profile(h, (e.get('source') or '').split(' · ')[0])
    lean = pr.get('lean')
    e['publisher'] = h
    e['paywall'] = publishers.article_paywall(e, h)
    e['story'] = {'id': e['id'], 'sources': 1, 'articles': 1, 'method': 'single', 'similarity': None,
                  'dist': {'left': int(lean is not None and lean < 0), 'center': int(lean == 0), 'right': int(lean is not None and lean > 0), 'unrated': int(lean is None)}}
    return pr


WIKI_UA = 'Sanjaya/5.9 (local news and research dashboard; https://github.com/a-moharil/Atlas)'


def wiki_get(url, max_bytes=2_000_000, timeout=20):
    """Wikipedia asks API clients for an identifying User-Agent."""
    validate_external_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': WIKI_UA, 'Accept': 'application/json, text/html'})
    with urllib.request.build_opener(SafeRedirectHandler()).open(req, timeout=timeout) as res:
        block = res.read(max_bytes + 1)
    if len(block) > max_bytes:
        raise ValueError('Wikipedia response exceeded size limit')
    return block


def ask_question(data):
    """Retrieve sources for a question and start a local Ollama answer (see ask.py)."""
    q = re.sub(r'\s+', ' ', str(data.get('question', ''))).strip()[:600]
    if len(q) < 3:
        raise ValueError('Type a question.')
    state = {e['id']: e for e in graph_entries()}
    ids = [str(i)[:40] for i in (data.get('ids') or [])][:20000]
    pool = {i: state[i] for i in (ids or list(state)) if i in state}
    use_meaning = semantic.ready()
    qv = (semantic.embed_texts([q], DB_FILE.parent / 'model_cache') or [None])[0] if use_meaning else None
    mode = 'both' if qv is not None else 'keywords'
    sims = {}
    if qv is not None:
        for i, v in semantic.vectors(db_connect, list(pool)).items():
            sims[i] = float(v @ qv)
    docs = [(i, e.get('title', ''), e.get('summary', ''), e.get('source', '')) for i, e in pool.items()]
    ranked = ask.rank_loose(q, docs, mode, sims)
    per, articles = {}, []
    for r in ranked:  # at most two articles per outlet, eight in all
        e = pool[r['id']]
        h = e.get('publisher') or e.get('source')
        if per.get(h, 0) >= 2:
            continue
        per[h] = per.get(h, 0) + 1
        prof = publishers.profile(e.get('publisher', '')) if e.get('publisher') else {}
        articles.append({'id': e['id'], 'title': e.get('title', ''), 'summary': e.get('summary', ''), 'url': e.get('url', ''),
                         'published': e.get('published') or e.get('retrieved'), 'source': e.get('source', ''),
                         'outlet': prof.get('name') or e.get('source', ''), 'publisher': e.get('publisher', '')})
        if len(articles) >= 8:
            break
    passages = []
    title = str(data.get('wiki') or '').strip()
    wiki_note = ''
    if title:
        try:
            ps = wiki.passages(wiki.plain_text(title, wiki_get, db_connect))[:400]
            pdocs = [(str(n), '', p['text'], p['section']) for n, p in enumerate(ps)]
            psims = {}
            if qv is not None and ps:
                for n, v in enumerate(semantic.embed_texts([p['text'] for p in ps[:200]], DB_FILE.parent / 'model_cache') or []):
                    psims[str(n)] = float(v @ qv)
            order = [int(r['id']) for r in ask.rank_loose(q, pdocs, mode, psims)][:4]
            if ps and 0 not in order:
                order = [0] + order[:3]  # the lead is always offered
            page_name = title.replace('_', ' ')
            passages = [{'page': page_name, 'section': ps[n]['section'], 'text': ps[n]['text'],
                         'url': f"{wiki.BASE}/wiki/{urllib.parse.quote(wiki.norm_title(title))}"} for n in order]
        except Exception as exc:
            wiki_note = f'Could not read the Wikipedia page ({type(exc).__name__}).'
    with closing(db_connect()) as con:
        cfg = semantic.settings(con)
    url = cfg.get('ollama_url') or lm_labels.DEFAULT_URL
    model = cfg.get('ask_model') or cfg.get('ollama_model') or lm_labels.DEFAULT_MODEL
    out = {'question': q, 'mode': mode, 'model': model, 'wiki_note': wiki_note,
           'sources': {'atlas': articles, 'wikipedia': passages}, 'searched': len(pool)}
    if not articles and not passages:
        return {**out, 'status': 'no_sources'}
    status = lm_labels.check(url, model)
    if status['status'] != 'ready':
        return {**out, 'status': 'no_model', 'error': status['detail'], 'models': status.get('models', [])}
    job = ask.start(q, articles, passages, url, model)
    return {**out, 'status': 'writing', 'job': job['id']}


def find_articles(data):
    """Rank a panel's articles (or the reel's videos) for a query. See find.py for the query syntax."""
    groups = find.parse(data.get('q', ''))
    if not groups:
        raise ValueError('Type one or more keywords.')
    want = str(data.get('mode', 'auto'))
    if want not in ('auto', 'keywords', 'meaning', 'both'):
        want = 'auto'
    limit = max(5, min(200, int(data.get('limit') or 60)))
    extra_rows, directory = [], {}
    if data.get('source') == 'reel':
        vids = geo_reel(data.get('hours', 24), 'news')['videos']
        pool = {v['id']: {**v, 'medium': 'video', 'summary': '', 'source': v['channel']} for v in vids}
    else:
        state = {e['id']: e for e in graph_entries()}
        ids = [str(i)[:40] for i in (data.get('ids') or [])][:20000]
        extra = [str(i)[:40] for i in (data.get('extra') or [])][:400]
        pool = {i: state[i] for i in (ids or list(state)) if i in state}
        missing = [i for i in extra if i not in state]
        for i in extra:
            if i in state:
                pool[i] = state[i]
        if missing:
            with closing(db_connect()) as con:
                condition, values = content_cleanup.where_visible(con)
                for r in con.execute(f"SELECT * FROM entries WHERE {condition} AND id IN ({','.join('?' for _ in missing)})", (*values, *missing)):
                    e = dict(r)
                    directory[publishers.entry_host(e)] = _single(e)
                    pool[e['id']] = e
                    extra_rows.append(e)
    docs = [(i, e.get('title', ''), e.get('summary', ''), e.get('source', '')) for i, e in pool.items()]
    usable = semantic.ready() and want != 'keywords'
    mode = ('both' if usable else 'keywords') if want == 'auto' else want
    note = ''
    if mode in ('meaning', 'both') and not usable:
        note = 'The language model is off or still loading, so this search used keywords only.'
        mode = 'keywords'
    sims = {}
    if mode in ('meaning', 'both'):
        qv = semantic.embed_texts([' '.join(g) for g in groups], DB_FILE.parent / 'model_cache') or []
        vecs = semantic.vectors(db_connect, [i for i in pool if not str(i).startswith('geo')]) if data.get('source') != 'reel' else {}
        todo = [i for i in pool if i not in vecs][:600]
        if todo and qv:
            for i, v in zip(todo, semantic.embed_texts([semantic.clean(pool[i].get('title', ''), pool[i].get('summary', '')) for i in todo], DB_FILE.parent / 'model_cache') or []):
                vecs[i] = v
        if qv:
            for i, v in vecs.items():
                sims[i] = max(float(v @ q) for q in qv)
        else:
            note, mode = 'The language model could not embed the query, so this search used keywords only.', 'keywords'
    results = find.rank(groups, docs, mode, sims, limit)
    keep = {r['id'] for r in results}
    if data.get('source') == 'reel':
        extra_rows = list(pool.values())
    return {'mode': mode, 'groups': groups, 'results': results, 'pool': len(pool), 'note': note,
            'entries': extra_rows if data.get('source') != 'reel' else [e for e in extra_rows if e['id'] in keep], 'publishers': directory,
            'semantic': semantic.ready()}


def radar_tick(force=False):
    """Keep the research radar fresh in the background. Each source has its own schedule
    (retrieval_jobs skips any that are not due), so calling this often is cheap."""
    try:
        return research_radar.run_jobs(retrieval_jobs.request,research_fetch,db_connect,DB_FILE.parent/'model_cache',DB_FILE.parent/'research_cache',force)
    except Exception as exc:
        print('[radar]',type(exc).__name__,str(exc)[:200]);return {}


def lm_work(label=True):
    """Embed new articles, then (if switched on) label top newsroom groups. Background only."""
    if not LM_BUSY.acquire(blocking=False):return
    try:
        try:semantic.embed_pending(db_connect,DB_FILE.parent/'model_cache')
        except Exception as exc:
            with semantic.LOCK:semantic.STATE.update(status='error',detail=f'{type(exc).__name__}: {str(exc)[:240]}')
        if not label:return
        with closing(db_connect()) as con:cfg=semantic.settings(con)
        if cfg.get('labels_enabled')!='1':return
        try:
            data=emergency_payload(24)
            groups=[g['records'] for g in data.get('groups',[])[:16]]
            lm_labels.run(groups,db_connect,cfg.get('ollama_url',lm_labels.DEFAULT_URL),cfg.get('ollama_model',lm_labels.DEFAULT_MODEL))
        except Exception as exc:
            lm_labels.STATE['detail']=f'Labelling failed: {type(exc).__name__}: {str(exc)[:200]}'
    finally:
        LM_BUSY.release()


def emergency_payload(hours):
    feeds=all_feed_configs()
    with closing(db_connect()) as con:
        condition,values=content_cleanup.where_visible(con)
        records=[dict(r) for r in con.execute(f"SELECT * FROM entries WHERE medium='article' AND {condition} ORDER BY published DESC LIMIT 14000",values)]
        statuses={r['id']:dict(r) for r in con.execute('SELECT * FROM feeds_status')}
        rules=emergency.rules(con);version=con.execute('SELECT version FROM emergency_settings WHERE id=1').fetchone()[0]
        cfg=semantic.settings(con)
    matcher=None;mode='keywords';note='Language model not installed or not ready; grouped by headline keywords.'
    if semantic.ready():
        recent=[r['id'] for r in records[:2500]]
        vecs=semantic.vectors(db_connect,recent)
        if len(vecs)>=max(1,int(len(recent)*cfg['coverage_min'])):
            matcher=semantic.Matcher(vecs,cfg['threshold']);mode='meaning';note=''
        else:note=f'Language model is still processing articles ({len(vecs)} of {len(recent)} recent); grouped by headline keywords meanwhile.'
    data=emergency.payload(records,feeds,statuses,rules,version,hours,matcher=matcher)
    data['grouping']={'mode':mode,'note':note,'threshold':cfg['threshold'],'model':semantic.MODEL if mode=='meaning' else None,
        'by_meaning':matcher.used if matcher else 0,'by_keywords':matcher.fallback if matcher else None}
    with closing(db_connect()) as con:
        labels=lm_labels.cached(con,[lm_labels.group_key(g['records']) for g in data.get('groups',[])])
    for g in data.get('groups',[]):
        lab=labels.get(lm_labels.group_key(g['records']))
        if lab:g['generated']={k:lab[k] for k in ('label','summary','differences','model','created')}
    return data


def geo_reel_channels(extra_only=False):
    """Channels for the geopolitics reel: its own list, plus included existing channels."""
    cfg=REGISTRY.get('geo_reel',{})
    extra=[{**c,'geo_reel':True} for c in cfg.get('channels',[])]
    if extra_only:return extra
    inc=set(cfg.get('include',[]))
    return extra+[c for c in REGISTRY['channels'] if c['id'] in inc]


def verify_videos(limit=60):
    """oEmbed-check recent uploads and configured fallback streams (bounded, background).
    Reel videos from the last 30 hours go first, so the reel fills quickly after a refresh."""
    reel=[c['id'] for c in geo_reel_channels()]
    since=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    marks=','.join('?' for _ in reel) or "''"
    with closing(db_connect()) as con:
        first=[r['video_id'] for r in con.execute(f"SELECT video_id FROM entries WHERE medium='video' AND video_id IS NOT NULL AND source_id IN ({marks}) AND COALESCE(published,retrieved)>=? ORDER BY COALESCE(published,retrieved) DESC LIMIT 200",(*reel,since))]
        ids=first+[r['video_id'] for r in con.execute("SELECT video_id FROM entries WHERE medium='video' AND video_id IS NOT NULL AND source_id NOT LIKE 'geo\\_%' ESCAPE '\\' ORDER BY COALESCE(published,retrieved) DESC LIMIT 120")]
    ids=[c.get('fallback_id') for c in REGISTRY.get('live_channels',[]) if c.get('fallback_id')]+ids
    try:return video_check.verify(ids,db_connect,fetch_bytes,utc_now,limit)
    except Exception as exc:
        print('video verification failed:',exc);return 0


VIDEO_STATES={}

def live_channels_state():
    with closing(db_connect()) as con:
        rows={r['id']:dict(r) for r in con.execute('SELECT * FROM live_channel_status')}
        VIDEO_STATES.clear();VIDEO_STATES.update(video_check.states(con))
    out=[]
    for config in REGISTRY.get('live_channels',[]):
        status=rows.get(config['id'],{})
        # Never describe old cached status as live indefinitely.
        is_fresh=False
        if status.get('checked'):
            try: is_fresh=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(status['checked'].replace('Z','+00:00'))).total_seconds()<LIVE_REFRESH_SECONDS+300
            except Exception: pass
        live=status.get('state')=='live' and is_fresh
        fb=VIDEO_STATES.get(config.get('fallback_id') or '',{})
        out.append({**config,'state':'live' if live else 'unverified',
                    'fallback_playable':fb.get('state')=='playable','fallback_title':fb.get('title',''),
                    'checked':status.get('checked'),'last_verified':status.get('last_verified'),
                    'video_id':status.get('video_id') if live else None,
                    'title':status.get('title') if live else '',
                    'reason':('Verified on broadcaster live page' if live else (status.get('error') or 'Live status not verified'))})
    return out


def geo_reel(hours='24',scope='geo'):
    try:hours=max(1,min(72,int(hours)))
    except Exception:hours=24
    chans={c['id']:c for c in geo_reel_channels()}
    since=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=hours+1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    marks=','.join('?' for _ in chans) or "''"
    with closing(db_connect()) as con:
        rows=[dict(r) for r in con.execute(f'''SELECT id,source_id,source,title,summary,video_id,published,retrieved FROM entries
            WHERE medium='video' AND video_id IS NOT NULL AND source_id IN ({marks})
            AND COALESCE(published,retrieved)>=? ORDER BY COALESCE(published,retrieved) DESC LIMIT 1500''',(*chans,since))]
        states=video_check.states(con)
        hidden={r[0] for r in con.execute('SELECT entry_id FROM wall_hidden')}
        status={r['id']:dict(r) for r in con.execute('SELECT * FROM feeds_status')}
    videos,counts=geo_video.select(rows,states,chans,hours,scope!='news',hidden=hidden)
    channels=[{'id':k,'name':c['name'],'region':c.get('region',''),'state':status.get(k,{}).get('state') or 'not fetched yet',
               'error':status.get(k,{}).get('error') or '','videos':sum(1 for v in videos if v['source_id']==k)} for k,c in chans.items()]
    return {'videos':videos[:120],'counts':counts,'channels':channels,'hours':hours,'scope':'news' if scope=='news' else 'geo','time':utc_now()}


def read_state():
    live=live_channels_state()
    with closing(db_connect()) as con:
        condition,values=content_cleanup.where_visible(con)
        # Reel-only broadcaster uploads stay out of the desks, story groups and upload rail.
        entries = [dict(r) for r in con.execute(f'''SELECT * FROM entries WHERE {condition} AND source_id NOT LIKE 'geo\\_%' ESCAPE '\\' ORDER BY
            CASE WHEN published IS NULL THEN 1 ELSE 0 END,
            COALESCE(published,retrieved) DESC LIMIT ?''',( *values,NEWS_LIMIT))]
        statuses = {r['id']: dict(r) for r in con.execute('SELECT * FROM feeds_status')}
        notes = {r['entry_id']: dict(r) for r in con.execute('SELECT * FROM annotations')}
        terms = [r['term'] for r in con.execute('SELECT term FROM watch_terms ORDER BY created DESC')]
        prefs = publishers.prefs(con)
        wall_hidden = [r[0] for r in con.execute('SELECT entry_id FROM wall_hidden ORDER BY created DESC LIMIT 20000')]
    # Only videos that YouTube confirms are public and embeddable are offered.
    audit={'playable':0,'pending':0,'unavailable':0,'blocked':0}
    kept=[]
    for e in entries:
        if e['medium']=='video':
            st=VIDEO_STATES.get(e.get('video_id') or '',{})
            state=st.get('state')
            if state=='playable':
                audit['playable']+=1;e['thumbnail']=st.get('thumbnail','');e['channel']=st.get('author','')
            elif state in ('unavailable','invalid'):audit['unavailable']+=1;continue
            elif state=='blocked':audit['blocked']+=1;continue
            else:audit['pending']+=1;continue
        kept.append(e)
    entries=kept
    with closing(db_connect()) as con:lm_cfg=semantic.settings(con)
    meaning,grouping_mode,grouping_note=semantic.story_groups(entries,db_connect,lm_cfg)
    directory=publishers.enrich(entries,meaning)
    for host in publishers.OVERRIDES:  # outlets you've calibrated, for the list of your ratings
        if host not in directory:directory[host]=publishers.profile(host)
    for host in prefs:  # primary/blocked publishers always resolve to a full identity
        if host not in directory:directory[host]=publishers.profile(host)
    return dict(entries=entries, status=statuses, notes=notes, watch_terms=terms, video_audit=audit,
                publishers=directory, source_prefs=prefs, wall_hidden=wall_hidden, lean_overrides=publishers.OVERRIDES, publisher_method=publishers.DATA['method'],
                grouping={'mode':grouping_mode,'note':grouping_note or ('Stories grouped by meaning with '+semantic.MODEL if grouping_mode=='meaning' else ''),'status':semantic.status().get('status')},
                registry=dict(feeds=all_feed_configs(),channels=REGISTRY['channels'],research=REGISTRY['research']),
                publisher_profiles=PROFILES, geo=atlas_plus.geo_state(db_connect),
                live_channels=live,
                meta=dict(server_time=utc_now(), last_cycle=LAST_CYCLE, refreshing=FETCH_RUNNING,
                          refresh_seconds=REFRESH_SECONDS, snapshot_date='2026-11-15'))


def get_social(handle):
    # Bluesky AppView public, unauthenticated; only public posts returned.
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{2,99}', handle):
        raise ValueError('Enter a public Bluesky handle such as example.bsky.social.')
    url = 'https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?' + urllib.parse.urlencode({'actor': handle, 'limit': 20})
    data = json.loads(fetch_bytes(url, 500_000).decode('utf-8'))
    out = []
    for item in data.get('feed', []):
        post = item.get('post') or {}
        record = post.get('record') or {}
        author = post.get('author') or {}
        uri = post.get('uri', '')
        rkey = uri.rsplit('/', 1)[-1]
        h = author.get('handle', handle)
        out.append(dict(text=str(record.get('text', ''))[:1000],
                        date=record.get('createdAt', ''), name=author.get('displayName', h),
                        handle=h, url=f'https://bsky.app/profile/{urllib.parse.quote(h)}/post/{urllib.parse.quote(rkey)}'))
    return out


from analysis_api import analyse_full_text, compare_feed_excerpts

class Handler(BaseHTTPRequestHandler):
    server_version = 'IndiaWorldObservatory/1.0'

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} [{self.log_date_time_string()}] {fmt % args}')

    def send_payload(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get('Content-Length', '0'))
        if n > (600_000 if self.path.split('?')[0] in ('/api/find', '/api/ask') else 30_000):
            raise ValueError('Request is too large.')
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}

    def serve_file(self, rel):
        if rel == '/':
            path = STATIC / 'index.html'
        else:
            clean = urllib.parse.unquote(rel).lstrip('/')
            path = (STATIC / clean).resolve()
            if not path.is_relative_to(STATIC.resolve()):
                self.send_error(403); return
        if not path.is_file():
            self.send_error(404); return
        ext = path.suffix.lower()
        mime = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8',
                '.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.geojson':'application/geo+json; charset=utf-8',
                '.svg':'image/svg+xml','.pdf':'application/pdf','.png':'image/png','.ico':'image/x-icon','.jpg':'image/jpeg'}.get(ext, 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(path.stat().st_size))
        self.end_headers()
        with open(path, 'rb') as f: self.wfile.write(f.read())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path.startswith('/api/map-tile/'):
                parts=parsed.path.split('/')
                if len(parts)!=7:
                    return self.send_payload({'error':'Invalid tile URL'},400)
                _,api_name,tile_name,provider,z,x,y=parts
                try:
                    day=params.get('day',[None])[0]
                    data,kind=tile_gateway.get_tile(provider,int(z),int(x),int(y),day)
                    self.send_response(200)
                    self.send_header('Content-Type',kind)
                    self.send_header('Cache-Control','public, max-age=60')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('X-ATLAS-Layer',provider)
                    self.send_header('Content-Length',str(len(data)))
                    self.end_headers();self.wfile.write(data)
                except (ValueError,KeyError) as e:
                    self.send_payload({'error':str(e)},400)
                except Exception as e:
                    self.send_payload({'error':'Provider request failed','provider':provider,'detail':str(e)[:200]},502)
                return
            if parsed.path == '/api/lm/status':
                with closing(db_connect()) as con:
                    cfg=semantic.settings(con);semantic.init(con)
                    total=con.execute("SELECT COUNT(*) FROM entries WHERE medium='article'").fetchone()[0]
                    embedded=con.execute('SELECT COUNT(*) FROM embeddings WHERE model=?',(semantic.MODEL,)).fetchone()[0]
                    labels=con.execute('SELECT COUNT(*) FROM story_labels').fetchone()[0]
                st=semantic.status()
                if st['status']=='not_checked':st['status']='ready' if semantic.ready() else ('installed' if semantic.available() else 'not_installed')
                lab=lm_labels.check(cfg.get('ollama_url',lm_labels.DEFAULT_URL),cfg.get('ollama_model',lm_labels.DEFAULT_MODEL)) if params.get('ollama',['0'])[0]=='1' else dict(lm_labels.STATE)
                return self.send_payload({'embedding':{**st,'installed':semantic.available(),'embedded':embedded,'articles':total,'model':semantic.MODEL,'dimensions':semantic.DIM},
                    'settings':{**cfg,'labels_enabled':cfg.get('labels_enabled','0'),'ollama_url':cfg.get('ollama_url',lm_labels.DEFAULT_URL),'ollama_model':cfg.get('ollama_model',lm_labels.DEFAULT_MODEL)},
                    'labels':{**lab,'stored':labels},'busy':LM_BUSY.locked()})
            if parsed.path == '/api/radar':
                # Research radar: each source is a cached background job with its own schedule; the page polls while they run.
                force=params.get('refresh',['0'])[0]=='1';mc=DB_FILE.parent/'model_cache'
                try:days=max(1,min(30,int(params.get('days',['7'])[0])))
                except ValueError:days=7
                jobs=radar_tick(force)
                data=research_radar.overview(db_connect,mc,days=days)
                data['sources']={k:{x:v.get(x) for x in ('pending','error','last_checked','cache_state','data_status','fetched','added','held','found','notes','resolved','note','keyed')} for k,v in jobs.items()}
                data['openml']={k:(jobs.get('openml') or {}).get(k) or [] for k in ('datasets','tasks')}
                data['models']=(jobs.get('huggingface') or {}).get('models') or []
                data['deadlines']={k:(jobs.get('deadlines') or {}).get(k) for k in ('conferences','upcoming','source')}
                with closing(db_connect()) as con:data['digest']=research_radar.digest_get(con)
                return self.send_payload(data)
            if parsed.path == '/api/radar/search':
                g=lambda k,d='':params.get(k,[d])[0]
                try:days=max(1,min(30,int(g('days','7'))))
                except ValueError:days=7
                try:mn=float(g('min','0') or 0)
                except ValueError:mn=0.0
                f={'lane':g('lane'),'cat':g('cat'),'min':mn,'source':g('source'),'saved':g('saved'),'hf':g('hf')=='1'}
                mode=g('mode','auto') if g('mode','auto') in ('auto','keyword','semantic') else 'auto'
                return self.send_payload(research_radar.search(db_connect,DB_FILE.parent/'model_cache',g('q')[:500],mode,f,days))
            if parsed.path == '/api/radar/themes':
                try:days=max(1,min(30,int(params.get('days',['7'])[0])))
                except ValueError:days=7
                return self.send_payload(research_radar.themes(db_connect,DB_FILE.parent/'model_cache',days=days))
            if parsed.path == '/api/radar/queue':
                with closing(db_connect()) as con:
                    research_radar.init(con);return self.send_payload({'queue':research_radar.queue_list(con)})
            if parsed.path == '/api/radar/bibtex':
                ids=[x for x in params.get('ids',[''])[0].split(',') if x]
                with closing(db_connect()) as con:
                    research_radar.init(con);body=research_radar.bibtex(con,ids or None).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','application/x-bibtex; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="atlas-reading-queue.bib"')
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                return
            if parsed.path == '/api/lm/borderline':
                with closing(db_connect()) as con:
                    cfg=semantic.settings(con);condition,values=content_cleanup.where_visible(con)
                    rows=[dict(r) for r in con.execute(f"SELECT id,title,source,published,retrieved,medium FROM entries WHERE medium='article' AND {condition} ORDER BY COALESCE(published,retrieved) DESC LIMIT 900",values)]
                return self.send_payload({'pairs':semantic.borderline(db_connect,rows,cfg['threshold'],cfg['window_hours']),'threshold':cfg['threshold'],'ready':semantic.ready()})
            if parsed.path == '/api/sources':
                feeds=all_feed_configs()
                with closing(db_connect()) as con:
                    counts={r[0]:r[1] for r in con.execute("SELECT source_id,COUNT(*) FROM entries WHERE medium='article' GROUP BY source_id")}
                    counts.update({'origin:'+r[0]:r[1] for r in con.execute("SELECT origin_host,COUNT(*) FROM entries WHERE origin_host!='' GROUP BY origin_host")})
                    statuses={r['id']:dict(r) for r in con.execute('SELECT * FROM feeds_status')}
                    data=publishers.directory(feeds,statuses,counts,con)
                return self.send_payload({'publishers':data,'method':publishers.DATA['method'],'paywall_levels':publishers.DATA['paywall_levels'],'version':publishers.DATA['version']})
            if parsed.path == '/api/publisher-logo':
                host=publishers.norm_host(params.get('host',[''])[0][:120])
                allowed=set(publishers.PUBLISHERS)|{h for h in publishers.FEED_HOST.values() if not h.startswith('feed:')}
                try:
                    data,mime=logos.get(host,allowed,DB_FILE.parent/'logo_cache',fetch_bytes)
                except (LookupError,ValueError) as exc:
                    return self.send_payload({'error':str(exc)},404)
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','public, max-age=604800')
                self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'")
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if parsed.path == '/api/earth/hazards':
                return self.send_payload(retrieval_jobs.request('earth-hazards',lambda:earth_watch.hazards(research_fetch),DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1',ttl=900))
            if parsed.path == '/api/earth/climate':
                return self.send_payload(retrieval_jobs.request('earth-climate',lambda:earth_watch.climate(research_fetch),DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1',ttl=6*3600))
            if parsed.path == '/api/earth/field':
                region=params.get('region',['global'])[0];layer=params.get('layer',['atmosphere'])[0]
                if region not in earth_watch.REGIONS or layer not in ('atmosphere','ocean'):raise ValueError('Unknown field request')
                return self.send_payload(retrieval_jobs.request(f'earth-field:{region}:{layer}',lambda:earth_watch.field(region,research_fetch,layer),DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1',ttl=5400))
            if parsed.path == '/api/map-provider-status':
                return self.send_payload({'providers':tile_gateway.stats(),'checked':utc_now()})
            if parsed.path == '/api/cleanup':
                with closing(db_connect()) as con:return self.send_payload(content_cleanup.snapshot(con))
            if parsed.path == '/api/clusters':
                mode=params.get('mode',['semantic'])[0]
                focus=params.get('focus',['all'])[0]
                domain=params.get('domain',['all'])[0]
                sources=params.get('sources',[''])[0][:300]
                query=params.get('q',[''])[0][:90]
                try:
                    days=int(params.get('days',['30'])[0]);limit=int(params.get('limit',['450'])[0])
                    with closing(db_connect()) as con:
                        condition,values=content_cleanup.where_visible(con)
                        rows=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE medium IN ('article','paper') AND {condition} ORDER BY COALESCE(published,retrieved) DESC LIMIT 6000",values)]
                    return self.send_payload(article_clusters.cluster_payload(rows,all_feed_configs(),focus,domain,sources,days,limit,query,mode))
                except (ValueError,TypeError) as exc:
                    return self.send_payload({'error':str(exc)},400)
            if parsed.path == '/api/india-boundaries':
                # Bundled, offline: Survey of India-derived state/UT polygons (DataMeet, 36 units,
                # Ladakh & J&K as Union Territories, external boundary as per Government of India).
                geo=json.loads((STATIC/'data'/'india_states_soi.geojson').read_text(encoding='utf-8'))
                return self.send_payload({'geometry':geo,'source':'Survey of India state boundaries via DataMeet (datameet/maps · States/Admin2)',
                    'licence':'DataMeet maps repository, MIT / CC-BY; boundaries as published by Survey of India',
                    'boundary_note':'Simplified for screen display. External boundary follows the official map of India (Survey of India).'})
            if parsed.path == '/api/india-coverage':
                days=int(params.get('days',['7'])[0]); topic=params.get('topic',['all'])[0]
                scope=params.get('scope',['all'])[0]
                if topic not in ('all',*india_intel.TOPICS): raise ValueError('Unknown topic filter')
                if scope not in ('all','explicit'): raise ValueError('Unknown location confidence filter')
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    rows=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE medium='article' AND {condition} ORDER BY COALESCE(published,retrieved) DESC LIMIT 14000",values)]
                return self.send_payload(india_intel.india_coverage(rows,all_feed_configs(),days,topic,scope))
            if parsed.path == '/api/nasa-availability':
                return self.send_payload(retrieval_jobs.request('nasa-availability',tile_gateway.nasa_capabilities,DB_FILE.parent/'research_cache'))
            if parsed.path in ('/api/emergency','/api/conflict'):
                feeds=all_feed_configs()
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    records=[dict(r) for r in con.execute(f"SELECT * FROM entries WHERE medium='article' AND {condition} ORDER BY published DESC LIMIT 14000",values)]
                    statuses={r['id']:dict(r) for r in con.execute('SELECT * FROM feeds_status')}
                    if parsed.path=='/api/emergency':
                        hours=int(params.get('hours',['24'])[0])
                        if hours not in (6,12,24,48):raise ValueError('Invalid emergency window')
                        return self.send_payload(emergency_payload(hours))
                return self.send_payload(conflict_watch.payload(records,feeds,statuses,int(params.get('days',['30'])[0])))
            if parsed.path=='/api/conflict-map-status':
                return self.send_payload(retrieval_jobs.request('isw-map-metadata',lambda:conflict_watch.check_maps(fetch_bytes),DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1'))
            if parsed.path == '/api/mygov':
                days=int(params.get('days',['30'])[0])
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    entries=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE {condition} ORDER BY COALESCE(published,retrieved) DESC LIMIT 14000",values)]
                    statuses={r['id']:dict(r) for r in con.execute('SELECT * FROM feeds_status')}
                return self.send_payload(mygov.payload(entries,all_feed_configs(),statuses,days))
            if parsed.path == '/api/expert-geopolitics':
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    records=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE medium='article' AND {condition} ORDER BY COALESCE(published,retrieved) DESC LIMIT 2500",values)]
                return self.send_payload(expert_research.geopolitics(records))
            if parsed.path == '/api/expert-trade':
                reporter=params.get('reporter',['IND'])[0].upper()
                partner=params.get('partner',['USA'])[0].upper()
                year=int(params.get('year',['2024'])[0])
                flow=params.get('flow',['X'])[0].upper()
                return self.send_payload(retrieval_jobs.request(f'trade:{reporter}:{partner}:{year}:{flow}',lambda:expert_research.trade_preview(reporter,partner,year,flow,research_fetch),DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1'))
            if parsed.path == '/api/expert-macro':
                indicator=params.get('indicator',['NY.GDP.MKTP.KD.ZG'])[0]
                countries=params.get('countries',['IND,USA,CHN'])[0].split(',')
                if indicator not in expert_research.INDICATORS or not 1<=len(set(countries))<=8 or any(c not in expert_research.COUNTRIES for c in countries):raise ValueError('Invalid indicator or country selection')
                force=params.get('refresh',['0'])[0]=='1'
                def retrieve():
                    expert_research.CACHE.pop((indicator,tuple(sorted(set(countries)))),None)
                    return expert_research.macro_data(indicator,countries,research_fetch)
                return self.send_payload(retrieval_jobs.request('macro:'+indicator+':'+','.join(sorted(set(countries))),retrieve,DB_FILE.parent/'research_cache',force))
            if parsed.path == '/api/state': return self.send_payload(read_state())
            if parsed.path == '/api/metrics': return self.send_payload(atlas_v3.metrics(db_connect,all_feed_configs(),REGISTRY['channels'],REGISTRY['research'],LAST_CYCLE,FETCH_RUNNING))
            if parsed.path == '/api/map-health':
                # Fixed, allowlisted remote map resources. This is a server-side probe;
                # browser-side tile failures are recorded independently in the UI.
                # Test actual image bytes, never mistake a WMS GetCapabilities XML for a working layer.
                requested=params.get('day',[None])[0]
                try:
                    from datetime import date as _date,timedelta as _timedelta
                    day=requested or (_date.today()-_timedelta(days=2)).isoformat()
                except Exception:day=None
                tests=[('esri_satellite','esri',3,5,3,None),
                       ('nasa_viirs_fire','nasa',3,5,3,day),
                       ('nasa_viirs_daily','nasa_daily',3,5,3,day),
                       ('nasa_blue_marble','nasa_base',3,5,3,None)]
                def probe(item):
                    name,provider,z,x,y,obs=item;started=time.monotonic()
                    try:
                        data,format_=tile_gateway.get_tile(provider,z,x,y,obs,timeout=5)
                        return {'id':name,'success':True,'image_valid':True,'bytes':len(data),
                                'mime_type':format_,'date':obs,'latency_ms':int((time.monotonic()-started)*1000)}
                    except Exception as e:
                        return {'id':name,'success':False,'image_valid':False,'date':obs,
                                'error':type(e).__name__+': '+str(e)[:240],
                                'latency_ms':int((time.monotonic()-started)*1000)}
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    status=list(pool.map(probe,tests))
                return self.send_payload({'checked':utc_now(),'probes':status,
                    'note':'These probes verify real tile bytes, not just service metadata. A transparent thermal tile can be a valid image without any detected fire. Rendering and regional coverage require separate checks.'})
            if parsed.path == '/api/map-geojson':
                layer=params.get('layer',[''])[0]
                return self.send_payload(atlas_v3.map_catalog(layer,fetch_bytes))
            if parsed.path == '/api/shakemap':
                detail=params.get('detail',[''])[0]
                return self.send_payload(atlas_v3.shakemap(detail,fetch_bytes))
            if parsed.path == '/api/live-channels': return self.send_payload({'channels':live_channels_state(),'time':utc_now()})
            if parsed.path == '/api/elections/catalog':
                return self.send_payload(elections.catalog())
            if parsed.path == '/api/elections/result':
                try:return self.send_payload(elections.result(params.get('id',[''])[0][:80]))
                except LookupError as e:return self.send_payload({'error':str(e)},404)
            if parsed.path == '/api/elections/officials':
                try:scope=officials.parse_scope(params.get('scope',['IN'])[0][:80])[1]
                except ValueError as e:return self.send_payload({'error':str(e)},400)
                getter=lambda u:wiki_get(u,6_000_000,timeout=60 if 'wikidata' in u else 30)
                return self.send_payload(officials.request(scope,getter,DB_FILE.parent/'research_cache',params.get('refresh',['0'])[0]=='1'))
            if parsed.path == '/api/elections/forecast':
                st=params.get('state',[''])[0][:60];force=params.get('refresh',['0'])[0]=='1'
                if not st:return self.send_payload(forecast.national())
                return self.send_payload(forecast.for_state(st,hidden=elections.hidden_kinds(st),force=force))
            if parsed.path == '/api/elections/pulse':
                st=params.get('state',[''])[0][:60];force=params.get('refresh',['0'])[0]=='1'
                return self.send_payload(pulse.for_scope(st,news_db=DB_FILE,hidden=elections.hidden_kinds(st or None),force=force))
            if parsed.path.startswith('/api/us/'):
                getter=lambda u:wiki_get(u,6_000_000,timeout=60 if 'wikidata' in u else 30)
                force=params.get('refresh',['0'])[0]=='1'
                if parsed.path == '/api/us/catalog':return self.send_payload(us_elections.catalog())
                if parsed.path == '/api/us/geo':
                    if not us_elections.ready():return self.send_payload({'error':'Download the US results first.'},409)
                    return self.send_payload(us_elections.geo())
                if parsed.path == '/api/us/result':
                    if not us_elections.ready():return self.send_payload({'error':'Download the US results first.'},409)
                    which=params.get('refresh',[''])[0]
                    try:return self.send_payload(us_elections.result(params.get('office',['H'])[0][:1],int(params.get('cycle',['2024'])[0][:4]),getter,
                                                                     which in ('1','wiki'),fetch_public_record,force_states=which in ('1','states')))
                    except ValueError as e:return self.send_payload({'error':str(e)},400)
                if parsed.path == '/api/us/officials':
                    try:return self.send_payload(us_officials.request(params.get('scope',['us'])[0][:20],getter,DB_FILE.parent/'research_cache',force))
                    except ValueError as e:return self.send_payload({'error':str(e)},400)
                return self.send_payload({'error':'Not found'},404)
            if parsed.path == '/api/elections/geo':
                try:return self.send_payload(elections.geo(params.get('layer',['ac'])[0],params.get('state',[''])[0][:60]))
                except (LookupError,ValueError) as e:return self.send_payload({'error':str(e)},404)
            if parsed.path == '/api/wiki/search':
                try:return self.send_payload(wiki.search(params.get('q',[''])[0],wiki_get,db_connect))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
                except Exception as e:return self.send_payload({'error':f'Wikipedia could not be reached ({type(e).__name__}).'},502)
            if parsed.path == '/api/wiki/page':
                try:return self.send_payload(wiki.page(params.get('title',[''])[0],wiki_get,db_connect))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
                except urllib.error.HTTPError as e:return self.send_payload({'error':'Wikipedia has no article with that title.' if e.code==404 else f'Wikipedia answered {e.code}.'},404 if e.code==404 else 502)
                except Exception as e:return self.send_payload({'error':f'Wikipedia could not be reached ({type(e).__name__}).'},502)
            if parsed.path.startswith('/api/ask/job/'):
                j=ask.get(parsed.path.rsplit('/',1)[-1][:20])
                return self.send_payload(j) if j else self.send_payload({'error':'No such answer.'},404)
            if parsed.path == '/api/ask/models':
                with closing(db_connect()) as con:cfg=semantic.settings(con)
                url=cfg.get('ollama_url') or lm_labels.DEFAULT_URL;model=cfg.get('ask_model') or cfg.get('ollama_model') or lm_labels.DEFAULT_MODEL
                st=lm_labels.check(url,model)
                return self.send_payload({'model':model,'status':st['status'],'detail':st['detail'],'models':st.get('models',[])})
            if parsed.path == '/api/geo-reel':
                return self.send_payload(geo_reel(params.get('hours',['24'])[0],params.get('scope',['geo'])[0]))
            if parsed.path == '/api/brief':
                key=params.get('id',[''])[0][:100]
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    item=con.execute(f'SELECT * FROM entries WHERE id=? AND {condition}',(key,*values)).fetchone()
                    if item is None:return self.send_payload({'error':'Article not found'},404)
                    e=dict(item); word=set(re.findall(r'[a-z]{5,}',(e['title'] or '').lower()))-{'which','there','their','after','about','india','world','says','amid','could','would'}
                    candidates=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE medium='article' AND id != ? AND {condition} ORDER BY published DESC LIMIT 350",(key,*values))]
                sem=semantic.related(e['id'],db_connect,[e]+candidates) if semantic.ready() else None
                if sem is not None:
                    related=[]
                    for score,r in sem:r=dict(r);r['similarity']=score;related.append(r)
                    match_mode='meaning'
                else:
                    related=sorted(candidates,key=lambda r:len(word.intersection(set(re.findall(r'[a-z]{5,}',r['title'].lower())))),reverse=True)
                    related=[r for r in related if len(word.intersection(set(re.findall(r'[a-z]{5,}',r['title'].lower()))))>=2]
                    match_mode='keywords'
                digest=atlas_plus.source_digest(e,related)
                sims={r['id']:r.get('similarity') for r in related}
                for r in digest.get('related',[]):r['similarity']=sims.get(r.get('id'))
                digest['grouping']=match_mode
                host=publishers.entry_host(e);digest['publisher']=publishers.profile(host,e['source'].split(' · ')[0])
                digest['paywall']=publishers.article_paywall(e,host)
                for r in digest.get('related',[]):
                    rh=publishers.entry_host(r) if r.get('source_id') else publishers.host_of(r.get('url',''))
                    r['publisher']=publishers.profile(rh,str(r.get('source','')).split(' · ')[0])
                return self.send_payload(digest)
            if parsed.path == '/api/social':
                handle = params.get('handle', [''])[0].strip()
                return self.send_payload(dict(handle=handle, posts=get_social(handle)))
            if parsed.path == '/api/health': return self.send_payload({'ok': True, 'time': utc_now(), 'refreshing': FETCH_RUNNING})
            return self.serve_file(parsed.path)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_payload({'error': str(exc)}, 400)
        except Exception as exc:
            return self.send_payload({'error': f'{type(exc).__name__}: {exc}'}, 502)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self.read_json()
            if path == '/api/cleanup':
                with closing(db_connect()) as con:
                    content_cleanup.apply(con,data.get('enabled'),utc_now())
                    result=content_cleanup.snapshot(con)
                return self.send_payload({'ok':True,**result})
            if path == '/api/lm/settings':
                with closing(db_connect()) as con:
                    for k,v in (data or {}).items():semantic.set_setting(con,str(k)[:40],str(v)[:120])
                return self.send_payload({'ok':True})
            if path == '/api/lm/run':
                threading.Thread(target=lm_work,kwargs={'label':bool(data.get('labels',True))},daemon=True,name='lm-work').start()
                return self.send_payload({'started':True})
            if path == '/api/graph':
                ids=[str(x)[:40] for x in (data.get('ids') or [])][:coverage_graph.MAX_PAGE]
                return self.send_payload(coverage_graph.overview(graph_entries(),ids,db_connect,publishers.profile,graph_pref()))
            if path == '/api/video/player-error':
                vid=str(data.get('video_id',''))[:11]
                with closing(db_connect()) as con:ok=video_check.report_player_error(con,vid,data.get('code'),utc_now())
                return self.send_payload({'ok':ok})
            if path == '/api/us/download':
                started=us_elections_data.start(lambda u:fetch_bytes(u,max_bytes=30_000_000,timeout=300))
                return self.send_payload({'started':started,**us_elections_data.status()})
            if path == '/api/elections/download':
                started=elections_data.start(lambda u,timeout=None:fetch_bytes(u,max_bytes=60_000_000,timeout=timeout or 600))
                return self.send_payload({'started':started,**elections_data.status()})
            if path == '/api/ask':
                try:return self.send_payload(ask_question(data))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
            if path == '/api/ask/settings':
                try:
                    with closing(db_connect()) as con:semantic.set_setting(con,'ask_model',str(data.get('model','')))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
                return self.send_payload({'ok':True})
            if path == '/api/find':
                try:return self.send_payload(find_articles(data))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
            if path == '/api/find/fetch':
                groups = find.parse(data.get('q', ''))
                if not groups:
                    return self.send_payload({'error': 'Type one or more keywords.'}, 400)
                desk = data.get('desk') if data.get('desk') in GRAPH_DESKS else 'World'
                return self.send_payload(fetch_google(find.web_queries(groups, int(data.get('days') or 7)), desk))
            if path == '/api/graph/diffuse':
                try:days=max(1,min(14,int(data.get('days',7))))
                except (TypeError,ValueError):days=7
                try:return self.send_payload(coverage_graph.diffuse(graph_entries(),str(data.get('seed',''))[:40],db_connect,publishers.profile,days,pref_of=graph_pref()))
                except LookupError as e:return self.send_payload({'error':str(e)},404)
            if path == '/api/graph/search-further':
                try:return self.send_payload(search_further(data.get('terms') or [],data.get('gaps') or [],str(data.get('desk','World'))))
                except ValueError as e:return self.send_payload({'error':str(e)},400)
            if path == '/api/radar/related':
                try:
                    return self.send_payload(research_radar.related_work(data.get('text',''),db_connect,research_fetch,DB_FILE.parent/'model_cache'))
                except ValueError as e:
                    return self.send_payload({'error':str(e)},400)
            if path == '/api/radar/queue':
                with closing(db_connect()) as con:
                    research_radar.init(con)
                    try:return self.send_payload({'queue':research_radar.queue_action(con,data)})
                    except ValueError as e:return self.send_payload({'error':str(e)},400)
            if path == '/api/radar/fingerprint':
                with closing(db_connect()) as con:
                    research_radar.init(con)
                    try:
                        if data.get('action')=='remove':
                            fid=str(data.get('id',''));con.execute('DELETE FROM radar_fingerprint WHERE id=?',(fid,));con.execute('DELETE FROM radar_vecs WHERE id=?',('fp:'+fid,))
                        else:research_radar.fp_add(con,str(data.get('ref',''))[:600])
                        con.commit()
                    except ValueError as e:return self.send_payload({'error':str(e)},400)
                    fps=research_radar.fingerprint(con)
                retrieval_jobs.request('radar-fingerprint',lambda:research_radar.resolve_fingerprint(db_connect,research_fetch,DB_FILE.parent/'model_cache'),DB_FILE.parent/'research_cache',True,ttl=7*86400)
                return self.send_payload({'fingerprint':[{k:f.get(k) for k in ('id','kind','ref','title','year','url','status','detail')} for f in fps]})
            if path == '/api/radar/watch':
                with closing(db_connect()) as con:
                    research_radar.init(con)
                    try:w=research_radar.watch_action(con,data)
                    except ValueError as e:return self.send_payload({'error':str(e)},400)
                retrieval_jobs.request('radar-keywords',research_radar.job_specs(research_fetch,db_connect,DB_FILE.parent/'model_cache')['keywords'][1],DB_FILE.parent/'research_cache',True,ttl=3600)
                return self.send_payload({'watch':w})
            if path == '/api/radar/settings':
                key=str(data.get('openalex_key','')).strip()
                if key and not re.fullmatch(r'[A-Za-z0-9_\-]{8,80}',key):return self.send_payload({'error':'That does not look like an OpenAlex API key.'},400)
                with closing(db_connect()) as con:
                    research_radar.init(con);research_radar.set_meta(con,'openalex_key',key);con.commit()
                return self.send_payload({'openalex_key':bool(key)})
            if path == '/api/radar/probe':
                return self.send_payload({'checks':research_radar.probe(research_fetch,db_connect)})
            if path == '/api/radar/digest':
                if research_radar.DIGEST.get('status')=='running':return self.send_payload({'started':False,'status':'running'})
                with closing(db_connect()) as con:cfg=semantic.settings(con)
                url=cfg.get('ollama_url') or lm_labels.DEFAULT_URL;model=cfg.get('ollama_model') or lm_labels.DEFAULT_MODEL
                threading.Thread(target=research_radar.digest_run,args=(db_connect,DB_FILE.parent/'model_cache',url,model,lm_labels._call),daemon=True,name='radar-digest').start()
                return self.send_payload({'started':True,'status':'running'})
            if path == '/api/wall':
                # Removing an article from the wall only hides it from display panels;
                # it stays in the database, in coverage counts and in Compare coverage.
                ids=[str(x)[:100] for x in (data.get('ids') or []) if str(x).strip()][:400]
                with closing(db_connect()) as con:
                    if data.get('clear'):
                        con.execute('DELETE FROM wall_hidden')
                    elif data.get('hidden',True):
                        con.executemany('INSERT OR IGNORE INTO wall_hidden(entry_id,created) VALUES(?,?)',[(i,utc_now()) for i in ids])
                    else:
                        con.executemany('DELETE FROM wall_hidden WHERE entry_id=?',[(i,) for i in ids])
                    con.commit()
                    hidden=[r[0] for r in con.execute('SELECT entry_id FROM wall_hidden ORDER BY created DESC LIMIT 20000')]
                return self.send_payload({'ok':True,'wall_hidden':hidden})
            if path == '/api/lean':
                lean=data.get('lean')
                lean='reset' if lean=='reset' else None if lean in (None,'none','') else lean
                try:
                    with closing(db_connect()) as con:
                        overrides=publishers.set_lean(con,str(data.get('host',''))[:130],lean,str(data.get('note','')),utc_now())
                except ValueError as e:return self.send_payload({'error':str(e)},400)
                _GRAPH_STATE['entries']=None
                return self.send_payload({'ok':True,'lean_overrides':overrides})
            if path == '/api/source-pref':
                with closing(db_connect()) as con:
                    publishers.set_pref(con,str(data.get('host',''))[:130],str(data.get('state','')),utc_now())
                    prefs=publishers.prefs(con)
                return self.send_payload({'ok':True,'source_prefs':prefs})
            if path == '/api/verify-videos':
                threading.Thread(target=verify_videos,kwargs={'limit':120},daemon=True,name='video-verify').start()
                return self.send_payload({'started':True})
            if path == '/api/compare-excerpts':
                key=str(data.get('id',''))[:100]
                with closing(db_connect()) as con:
                    condition,values=content_cleanup.where_visible(con)
                    article=con.execute(f'SELECT * FROM entries WHERE id=? AND {condition}',(key,*values)).fetchone()
                    if article is None: raise ValueError('Article not found')
                    main=dict(article)
                    candidates=[dict(x) for x in con.execute(f"SELECT * FROM entries WHERE medium='article' AND id!=? AND {condition} ORDER BY published DESC LIMIT 350",(key,*values))]
                words=set(re.findall(r'[a-z]{5,}',main['title'].lower()))-{'which','there','their','about','after','could','would','india','world'}
                related=sorted(candidates,key=lambda x:len(words.intersection(re.findall(r'[a-z]{5,}',x['title'].lower()))),reverse=True)
                related=[x for x in related if x['source_id']!=main['source_id'] and len(words.intersection(re.findall(r'[a-z]{5,}',x['title'].lower())))>=2]
                return self.send_payload(compare_feed_excerpts([main]+related[:4]))
            if path == '/api/analyse-text':
                return self.send_payload(analyse_full_text(data))
            if path == '/api/refresh-live':
                threading.Thread(target=refresh_live_channels,kwargs={'force':True},daemon=True,name='live-channel-check').start()
                return self.send_payload({'started':True,'note':'Official broadcaster status check requested. No status is assumed until verified.'})
            if path=='/api/emergency-sources':
                with closing(db_connect()) as con:
                    emergency.update(con,all_feed_configs(),data.get('scope'),data.get('key'),data.get('excluded'),data.get('version'))
                return self.send_payload({'ok':True})
            if path in ('/api/emergency-refresh','/api/conflict-refresh'):
                return self.send_payload({'started':start_refresh(force_local=True,scope='emergency' if path=='/api/emergency-refresh' else 'conflict'),'refreshing':FETCH_RUNNING})
            if path == '/api/mygov-refresh':
                return self.send_payload({'started':start_refresh(force_local=True,scope='mygov'),'refreshing':FETCH_RUNNING})
            if path == '/api/refresh':
                return self.send_payload({'started': start_refresh(force_local=True), 'refreshing': True})
            if path == '/api/annotation':
                eid = str(data.get('entry_id',''))[:100]
                if not re.fullmatch('[a-zA-Z0-9_-]{8,100}', eid): raise ValueError('Invalid entry ID.')
                note = str(data.get('note',''))[:3000]
                starred = 1 if data.get('starred') else 0
                with closing(db_connect()) as con:
                    con.execute('INSERT INTO annotations VALUES(?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET starred=excluded.starred,note=excluded.note,updated=excluded.updated', (eid,starred,note,utc_now()))
                    con.commit()
                return self.send_payload({'ok': True})
            if path == '/api/watch':
                term = str(data.get('term','')).strip().lower()[:90]
                if not (2 <= len(term) <= 90): raise ValueError('Watch terms require 2–90 characters.')
                with closing(db_connect()) as con:
                    if data.get('delete'):
                        con.execute('DELETE FROM watch_terms WHERE term=?', (term,))
                    else:
                        con.execute('INSERT OR IGNORE INTO watch_terms VALUES (?,?)', (term,utc_now()))
                    con.commit()
                return self.send_payload({'ok': True})
            if path == '/api/source':
                name = str(data.get('name','')).strip()[:90]
                url = str(data.get('url','')).strip()
                tier = str(data.get('tier','analysis'))
                region = str(data.get('region','Global'))
                if not name or tier not in ('primary','reporting','analysis','research') or region not in ('Global','India','Europe','Asia','Indo-Pacific','West Asia'):
                    raise ValueError('Specify a source name, valid category and valid region.')
                validate_external_url(url)
                sid = 'custom_' + hashlib.sha256(url.encode()).hexdigest()[:12]
                site = f'{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).hostname}'
                with closing(db_connect()) as con:
                    con.execute('INSERT OR REPLACE INTO custom_feeds VALUES(?,?,?,?,?,?)',(sid,name,url,tier,region,site))
                    con.commit()
                return self.send_payload({'ok': True, 'id': sid})
            return self.send_payload({'error': 'Unknown API route'},404)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_payload({'error': str(exc)},400)
        except Exception as exc:
            return self.send_payload({'error':f'{type(exc).__name__}: {exc}'},502)


def main():
    parser = argparse.ArgumentParser(description='Live geopolitical intelligence dashboard, local first')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1', help='Bind localhost by default; public exposure requires a reverse proxy/authentication')
    args = parser.parse_args()
    init_db()
    threading.Thread(target=poll_loop, daemon=True, name='auto-poll').start()
    threading.Thread(target=lm_work, daemon=True, name='lm-work').start()
    if not SKIP_NETWORK:radar_tick()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        print(f'\nIndia & World Observatory | http://{args.host}:{args.port}/')
        print('The backend checks feeds on startup and every', int(REFRESH_SECONDS/60), 'minutes while running.')
        print('Articles and notes persist in', DB_FILE)
        print('Press Ctrl+C to stop.\n')
        try: server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt: print('\nStopped.')

if __name__ == '__main__': main()
