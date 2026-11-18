"""Verify that YouTube videos can actually be played inside ATLAS.

The collector stores upload records from broadcaster Atom feeds, but some of those
videos are later made private, deleted, region-blocked or have embedding disabled,
which leaves an empty player. YouTube's public oEmbed endpoint answers 200 only for
public, embeddable videos (401/403 = embedding disabled, 404/400 = unavailable).
Only videos with a recent 200 are offered for playback.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import urllib.error
import urllib.parse
from contextlib import closing

LOCK = threading.Lock()
RECHECK_OK_HOURS = 24
RECHECK_BAD_HOURS = 6
RECHECK_PLAYER_HOURS = 24 * 7
PLAYER_PREFIX = 'Player error'
# YouTube IFrame player error codes.
PLAYER_CODES = {2: 'invalid request', 5: 'HTML5 player error', 100: 'removed or private',
                101: 'not playable outside YouTube (owner setting or region)', 150: 'not playable outside YouTube (owner setting or region)'}
VALID = re.compile(r'[A-Za-z0-9_-]{11}')


def init(con):
    con.executescript('''CREATE TABLE IF NOT EXISTS video_status(
        video_id TEXT PRIMARY KEY, state TEXT NOT NULL, checked TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', thumbnail TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '')''')
    con.commit()


def oembed(video_id: str, fetch_bytes) -> dict:
    if not VALID.fullmatch(video_id or ''):
        return {'state': 'invalid', 'detail': 'Malformed video ID'}
    url = 'https://www.youtube.com/oembed?' + urllib.parse.urlencode(
        {'url': 'https://www.youtube.com/watch?v=' + video_id, 'format': 'json'})
    try:
        data = json.loads(fetch_bytes(url, 200_000).decode('utf-8'))
        thumb = data.get('thumbnail_url') or f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
        return {'state': 'playable', 'title': str(data.get('title', ''))[:200], 'author': str(data.get('author_name', ''))[:120],
                'thumbnail': thumb if thumb.startswith('https://i.ytimg.com/') else f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                'detail': 'Public and embeddable (YouTube oEmbed 200)'}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {'state': 'blocked', 'detail': 'Owner disabled embedding'}
        if exc.code in (400, 404):
            return {'state': 'unavailable', 'detail': 'Removed, private or never public'}
        return {'state': 'error', 'detail': f'HTTP {exc.code}'}
    except Exception as exc:  # network failures never mark a video as dead
        return {'state': 'error', 'detail': f'{type(exc).__name__}: {str(exc)[:120]}'}


def _due(row, now) -> bool:
    if row is None:
        return True
    try:
        age = (now - dt.datetime.fromisoformat(row['checked'].replace('Z', '+00:00'))).total_seconds() / 3600
    except Exception:
        return True
    if str(row['detail'] if 'detail' in row.keys() else '').startswith(PLAYER_PREFIX):
        return age > RECHECK_PLAYER_HOURS  # oEmbed can't see region blocks; trust the browser for a week
    return age > (RECHECK_OK_HOURS if row['state'] == 'playable' else RECHECK_BAD_HOURS)


def verify(ids, db_connect, fetch_bytes, utc_now, limit=60) -> int:
    """Check up to ``limit`` IDs that are due. Returns the number checked."""
    if not LOCK.acquire(blocking=False):
        return 0
    try:
        now = dt.datetime.now(dt.timezone.utc)
        with closing(db_connect()) as con:
            init(con)
            known = {r['video_id']: dict(r) for r in con.execute('SELECT * FROM video_status')}
        todo = [v for v in dict.fromkeys(ids) if VALID.fullmatch(v or '') and _due(known.get(v), now)][:limit]
        results = []
        for vid in todo:
            r = oembed(vid, fetch_bytes)
            if r['state'] == 'error' and vid in known:
                continue  # keep the last definite answer
            results.append((vid, r['state'], utc_now(), r.get('title', ''), r.get('author', ''), r.get('thumbnail', ''), r.get('detail', '')))
        if results:
            with closing(db_connect()) as con:
                con.executemany('''INSERT INTO video_status VALUES(?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET
                    state=excluded.state,checked=excluded.checked,title=CASE WHEN excluded.title!='' THEN excluded.title ELSE video_status.title END,
                    author=excluded.author,thumbnail=excluded.thumbnail,detail=excluded.detail''', results)
                con.commit()
        return len(results)
    finally:
        LOCK.release()


def report_player_error(con, video_id: str, code, now: str) -> bool:
    """Record that YouTube's player refused a video in this browser, so lists stop offering it."""
    if not VALID.fullmatch(video_id or ''):
        return False
    try:
        code = int(code)
    except Exception:
        code = 0
    init(con)
    state = 'unavailable' if code == 100 else 'blocked'
    detail = f"{PLAYER_PREFIX} {code}: {PLAYER_CODES.get(code, 'unknown')}"
    con.execute('''INSERT INTO video_status(video_id,state,checked,detail) VALUES(?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET
        state=excluded.state,checked=excluded.checked,detail=excluded.detail''', (video_id, state, now, detail))
    con.commit()
    return True


def states(con) -> dict:
    init(con)
    return {r['video_id']: dict(r) for r in con.execute('SELECT * FROM video_status')}
