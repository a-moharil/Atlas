"""ATLAS v5 Earth watch: natural hazards, climate anomalies and live weather fields.

All sources are public, key-free and fetched only by the local server:

* GDACS (UN / EC Joint Research Centre) — alert-levelled cyclones, floods, earthquakes,
  droughts, volcanoes and wildfires.  https://www.gdacs.org/gdacsapi/swagger/index.html
* NASA EONET v3 — open natural events in every category (wildfires, severe storms,
  volcanoes, floods, landslides, dust & haze, sea & lake ice, temperature extremes).
* USGS — M4.5+ earthquakes in the past week.
* Copernicus Climate Change Service / ECMWF "Climate Pulse" — ERA5 daily global
  surface-air temperature and sea-surface temperature with 1991–2020 anomalies.
* Open-Meteo — current 10 m wind, 2 m temperature and precipitation on a coarse
  lat/lon grid (global and India), and optional ocean currents (marine API).
  Model analysis / forecast output, not station observations.

Nothing is interpolated into data that a provider did not return.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import urllib.parse

GDACS_URL = 'https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH'
GDACS_LATEST = 'https://www.gdacs.org/gdacsapi/api/events/geteventlist/latest'
EONET_URL = 'https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30&limit=400'
USGS_URL = 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson'
PULSE = {
    'air': 'https://sites.ecmwf.int/data/climatepulse/data/series/era5_daily_series_2t_global.csv',
    'sst': 'https://sites.ecmwf.int/data/climatepulse/data/series/era5_daily_series_sst_60S-60N_ocean.csv',
}
METEO = 'https://api.open-meteo.com/v1/forecast'
MARINE = 'https://marine-api.open-meteo.com/v1/marine'
HOSTS = {'www.gdacs.org', 'gdacs.org', 'eonet.gsfc.nasa.gov', 'earthquake.usgs.gov', 'sites.ecmwf.int',
         'api.open-meteo.com', 'marine-api.open-meteo.com'}

GDACS_KIND = {'EQ': 'earthquake', 'TC': 'cyclone', 'FL': 'flood', 'VO': 'volcano', 'DR': 'drought', 'WF': 'wildfire', 'TS': 'tsunami'}
EONET_KIND = {'wildfires': 'wildfire', 'severeStorms': 'cyclone', 'volcanoes': 'volcano', 'floods': 'flood',
              'landslides': 'landslide', 'dustHaze': 'dust', 'seaLakeIce': 'ice', 'tempExtremes': 'heat',
              'drought': 'drought', 'earthquakes': 'earthquake', 'snow': 'snow', 'waterColor': 'water', 'manmade': 'manmade'}
REGIONS = {
    'global': {'lat': (-60, 70, 10), 'lon': (-180, 165, 15)},
    'india': {'lat': (6, 38, 2), 'lon': (66, 100, 2)},
}


def _num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _point(geom):
    if not isinstance(geom, dict):
        return None
    c = geom.get('coordinates')
    t = geom.get('type')
    try:
        if t == 'Point':
            return float(c[0]), float(c[1])
        if t == 'Polygon':
            ring = c[0]
            return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        if t == 'MultiPolygon':
            ring = c[0][0]
            return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
    return None


def in_india(lat, lon):
    return 6 <= lat <= 37.5 and 68 <= lon <= 97.5


# ------------------------------------------------------------------ hazards

def parse_gdacs(data) -> list:
    out = []
    for f in (data or {}).get('features', [])[:400]:
        p = f.get('properties') or {}
        xy = _point(f.get('geometry'))
        if not xy:
            continue
        kind = GDACS_KIND.get(p.get('eventtype'), 'other')
        sev = p.get('severitydata') or {}
        url = (p.get('url') or {}).get('report') or 'https://www.gdacs.org/'
        out.append({'id': f"gdacs-{p.get('eventtype')}-{p.get('eventid')}", 'kind': kind, 'source': 'GDACS',
                    'title': str(p.get('name') or p.get('description') or kind.title())[:180],
                    'lon': round(xy[0], 3), 'lat': round(xy[1], 3), 'time': str(p.get('fromdate') or '')[:19],
                    'until': str(p.get('todate') or '')[:19], 'level': str(p.get('alertlevel') or '').lower() or 'green',
                    'severity': str(sev.get('severitytext') or '')[:180], 'country': str(p.get('country') or '')[:160],
                    'current': str(p.get('iscurrent')).lower() == 'true', 'url': url if url.startswith('https://') else 'https://www.gdacs.org/'})
    return out


def parse_eonet(data) -> list:
    out = []
    for e in (data or {}).get('events', [])[:500]:
        geo = e.get('geometry') or []
        if not geo:
            continue
        last = geo[-1]
        xy = _point(last)
        if not xy:
            continue
        cats = [c.get('id') for c in e.get('categories') or []]
        kind = EONET_KIND.get(cats[0] if cats else '', 'other')
        mag = _num(last.get('magnitudeValue'))
        src = (e.get('sources') or [{}])[0].get('url') or e.get('link') or 'https://eonet.gsfc.nasa.gov/'
        out.append({'id': 'eonet-' + str(e.get('id', ''))[:60], 'kind': kind, 'source': 'NASA EONET',
                    'title': str(e.get('title', ''))[:180], 'lon': round(xy[0], 3), 'lat': round(xy[1], 3),
                    'time': str(last.get('date', ''))[:19], 'level': 'observed',
                    'severity': f"{mag:g} {last.get('magnitudeUnit') or ''}".strip() if mag is not None else '',
                    'track': [[round(g['coordinates'][0], 2), round(g['coordinates'][1], 2)] for g in geo[-40:]
                              if g.get('type') == 'Point' and isinstance(g.get('coordinates'), list)] if kind == 'cyclone' else [],
                    'country': '', 'current': True, 'url': src if str(src).startswith('https://') else 'https://eonet.gsfc.nasa.gov/'})
    return out


def parse_usgs(data) -> list:
    out = []
    for f in (data or {}).get('features', [])[:300]:
        p = f.get('properties') or {}
        xy = _point(f.get('geometry'))
        mag = _num(p.get('mag'))
        if not xy or mag is None:
            continue
        t = ''
        if p.get('time'):
            t = dt.datetime.fromtimestamp(p['time'] / 1000, dt.timezone.utc).isoformat()[:19]
        level = 'red' if mag >= 7 else 'orange' if mag >= 6 else 'green'
        depth = None
        try:
            depth = float(f['geometry']['coordinates'][2])
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        out.append({'id': 'usgs-' + str(f.get('id', ''))[:40], 'kind': 'earthquake', 'source': 'USGS',
                    'title': str(p.get('title') or 'Earthquake')[:180], 'lon': round(xy[0], 3), 'lat': round(xy[1], 3),
                    'time': t, 'level': level, 'mag': mag, 'severity': f'M{mag:.1f}' + (f' · {depth:.0f} km deep' if depth is not None else ''),
                    'tsunami': bool(p.get('tsunami')), 'country': str(p.get('place') or '')[:160], 'current': True,
                    'url': str(p.get('url') or 'https://earthquake.usgs.gov/')})
    return out


def hazards(fetch_bytes, now=None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    q = urllib.parse.urlencode({'fromDate': (now - dt.timedelta(days=21)).date().isoformat(), 'toDate': now.date().isoformat(),
                                'alertlevel': 'Green;Orange;Red', 'eventlist': 'EQ;TC;FL;VO;DR;WF'})
    feeds, status = {}, {}
    for name, url, parser in (('GDACS', GDACS_URL + '?' + q, parse_gdacs), ('NASA EONET', EONET_URL, parse_eonet),
                              ('USGS', USGS_URL, parse_usgs)):
        try:
            feeds[name] = parser(json.loads(fetch_bytes(url, 6_000_000).decode('utf-8')))
            status[name] = {'state': 'ok', 'count': len(feeds[name])}
        except Exception as exc:
            if name == 'GDACS':
                try:
                    feeds[name] = parser(json.loads(fetch_bytes(GDACS_LATEST, 4_000_000).decode('utf-8')))
                    status[name] = {'state': 'ok', 'count': len(feeds[name]), 'note': 'latest-events endpoint'}
                    continue
                except Exception:
                    pass
            feeds[name] = []
            status[name] = {'state': 'error', 'error': f'{type(exc).__name__}: {str(exc)[:160]}'}
    events = feeds['GDACS'] + feeds['USGS'] + feeds['NASA EONET']
    # GDACS already relays significant USGS quakes: drop a USGS quake within 60 km / 2 h of a GDACS one.
    gq = [e for e in feeds['GDACS'] if e['kind'] == 'earthquake']
    keep = []
    for e in events:
        if e['source'] == 'USGS' and any(abs(e['lat'] - g['lat']) < .55 and abs(e['lon'] - g['lon']) < .55 and e['time'][:13] == g['time'][:13] for g in gq):
            continue
        keep.append(e)
    keep.sort(key=lambda e: e.get('time') or '', reverse=True)
    counts = {}
    for e in keep:
        counts[e['kind']] = counts.get(e['kind'], 0) + 1
    if not any(s['state'] == 'ok' for s in status.values()):
        return {'data_status': 'unavailable', 'error': 'No hazard provider responded', 'providers': status, 'events': []}
    return {'data_status': 'ok', 'checked': now.isoformat()[:19] + 'Z', 'events': keep, 'counts': counts, 'providers': status,
            'india': [e for e in keep if in_india(e['lat'], e['lon'])],
            'method': 'Events as published by GDACS, NASA EONET and USGS. Alert levels are the provider\'s own (GDACS green/orange/red; USGS level here is derived from magnitude only). Positions are centroids or the latest track point, not impact footprints.'}


# ------------------------------------------------------------------ climate pulse

def parse_pulse(text: str, keep_days=800) -> dict:
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    rows = list(csv.reader(lines))
    if len(rows) < 2:
        raise ValueError('Climate Pulse CSV has no rows')
    head = [h.strip().lower() for h in rows[0]]
    di = next(i for i, h in enumerate(head) if 'date' in h)
    vi = next(i for i, h in enumerate(head) if i != di and not h.startswith(('clim', 'ano', 'status')))
    ci = next((i for i, h in enumerate(head) if h.startswith('clim')), None)
    ai = next((i for i, h in enumerate(head) if h.startswith('ano') and ('91' in h or '1991' in h)), None)
    if ai is None:
        ai = next((i for i, h in enumerate(head) if h.startswith('ano')), None)
    pi = next((i for i, h in enumerate(head) if h.startswith('ano') and ('pi' in h or '1850' in h)), None)
    si = next((i for i, h in enumerate(head) if 'status' in h), None)
    pts = []
    for r in rows[1:]:
        try:
            pts.append({'date': r[di][:10], 'value': _num(r[vi]), 'clim': _num(r[ci]) if ci is not None else None,
                        'anomaly': _num(r[ai]) if ai is not None else None, 'preindustrial': _num(r[pi]) if pi is not None else None,
                        'status': (r[si].strip().lower() if si is not None and si < len(r) else '')})
        except IndexError:
            continue
    pts = [p for p in pts if p['value'] is not None]
    for p in pts:  # some vintages ship only the climatology column
        if p['anomaly'] is None and p['clim'] is not None:
            p['anomaly'] = round(p['value'] - p['clim'], 3)
    if not pts:
        raise ValueError('No numeric values in Climate Pulse CSV')
    full = pts
    pts = pts[-keep_days:]
    latest = pts[-1]
    year = latest['date'][:4]
    ytd = [p['anomaly'] for p in pts if p['date'].startswith(year) and p['anomaly'] is not None]
    record = max(full, key=lambda p: p['value'])
    return {'points': pts, 'latest': latest, 'year_to_date_anomaly': round(sum(ytd) / len(ytd), 3) if ytd else None,
            'record': {'date': record['date'], 'value': record['value']}}


def climate(fetch_bytes) -> dict:
    out, status = {}, {}
    for key, url in PULSE.items():
        try:
            out[key] = parse_pulse(fetch_bytes(url, 4_000_000).decode('utf-8', errors='replace'))
            status[key] = {'state': 'ok'}
        except Exception as exc:
            status[key] = {'state': 'error', 'error': f'{type(exc).__name__}: {str(exc)[:160]}'}
    if not out:
        return {'data_status': 'unavailable', 'error': 'Copernicus Climate Pulse unavailable', 'providers': status}
    return {'data_status': 'ok', 'series': out, 'providers': status,
            'source': 'Copernicus Climate Change Service / ECMWF · ERA5 via Climate Pulse',
            'source_url': 'https://pulse.climate.copernicus.eu/',
            'method': 'Daily ERA5 global-mean surface air temperature (2 m) and 60°S–60°N sea-surface temperature. Anomalies are versus the 1991–2020 daily climatology. Recent days are preliminary.'}


# ------------------------------------------------------------------ live fields

def grid(region):
    cfg = REGIONS[region]
    la0, la1, ls = cfg['lat']
    lo0, lo1, os_ = cfg['lon']
    lats = list(range(la1, la0 - 1, -ls))  # north → south rows
    lons = list(range(lo0, lo1 + 1, os_))
    return lats, lons


def _batches(points, n=100):
    for i in range(0, len(points), n):
        yield points[i:i + n]


def field(region, fetch_bytes, layer='atmosphere') -> dict:
    if region not in REGIONS:
        raise ValueError('Unknown region')
    if layer not in ('atmosphere', 'ocean'):
        raise ValueError('Unknown field layer')
    lats, lons = grid(region)
    pts = [(la, lo) for la in lats for lo in lons]
    values = []
    for chunk in _batches(pts):
        params = {'latitude': ','.join(str(p[0]) for p in chunk), 'longitude': ','.join(str(p[1]) for p in chunk), 'timezone': 'UTC'}
        if layer == 'atmosphere':
            params.update(current='temperature_2m,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover', wind_speed_unit='ms')
            url = METEO + '?' + urllib.parse.urlencode(params)
        else:
            params.update(current='ocean_current_velocity,ocean_current_direction,sea_surface_temperature,wave_height', cell_selection='sea')
            url = MARINE + '?' + urllib.parse.urlencode(params)
        data = json.loads(fetch_bytes(url, 3_000_000).decode('utf-8'))
        data = data if isinstance(data, list) else [data]
        if len(data) != len(chunk):
            raise ValueError('Open-Meteo returned a different number of locations')
        values += [d.get('current') or {} for d in data]
    nx = len(lons)
    rows = lambda key: [[_num(values[r * nx + c].get(key)) for c in range(nx)] for r in range(len(lats))]
    stamp = next((v.get('time') for v in values if v.get('time')), '')
    if layer == 'atmosphere':
        spd, dirn = rows('wind_speed_10m'), rows('wind_direction_10m')
        speed_key, unit = 'wind', 'm/s'
        extra = {'temp': rows('temperature_2m'), 'precip': rows('precipitation'), 'cloud': rows('cloud_cover')}
    else:
        spd, dirn = rows('ocean_current_velocity'), rows('ocean_current_direction')
        speed_key, unit = 'current', 'km/h'
        extra = {'sst': rows('sea_surface_temperature'), 'waves': rows('wave_height')}
    u, v = [], []
    for r in range(len(lats)):
        ur, vr = [], []
        for c in range(nx):
            s, d = spd[r][c], dirn[r][c]
            if s is None or d is None:
                ur.append(None); vr.append(None); continue
            rad = math.radians(d)
            if layer == 'atmosphere':  # meteorological "from" direction
                ur.append(round(-s * math.sin(rad), 2)); vr.append(round(-s * math.cos(rad), 2))
            else:  # oceanographic "towards" direction
                ur.append(round(s * math.sin(rad), 2)); vr.append(round(s * math.cos(rad), 2))
        u.append(ur); v.append(vr)
    valid = sum(x is not None for row in spd for x in row)
    if valid < len(pts) * (0.05 if layer == 'ocean' else 0.5):
        raise ValueError('Too few grid values returned')
    return {'data_status': 'ok', 'region': region, 'layer': layer, 'time': stamp, 'lats': lats, 'lons': lons,
            'u': u, 'v': v, 'speed': spd, 'unit': unit, 'kind': speed_key, **extra,
            'source': 'Open-Meteo' + (' Marine' if layer == 'ocean' else '') + ' · current model analysis',
            'source_url': 'https://open-meteo.com/',
            'method': f'{len(pts)} grid points at {REGIONS[region]["lat"][2]}° spacing. Particle motion is bilinearly interpolated between returned grid values for display only; it is model output, not observation.'}
