"""Small standard-library readers and simplifiers for map data.

Sanjaya avoids third-party geo libraries. This module reads ESRI shapefiles
(.shp polygons + .dbf attributes), turns Web Mercator metres into degrees,
simplifies rings (Douglas-Peucker) and quantises coordinates so a whole state's
constituencies fit in a few hundred kilobytes of JSON.
"""
import math
import struct

R_MERC = 6378137.0


def read_dbf(data):
    """Rows of a dBase III table as dicts (strings stripped, numbers parsed)."""
    n_rec, hdr_len, rec_len = struct.unpack('<xxxxIHH', data[:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b'\x00')[0].decode('latin-1').strip()
        ftype = chr(data[pos + 11])
        flen, fdec = data[pos + 16], data[pos + 17]
        fields.append((name, ftype, flen, fdec))
        pos += 32
    rows, off = [], hdr_len
    for _ in range(n_rec):
        rec = data[off:off + rec_len]
        off += rec_len
        if not rec or rec[0:1] == b'*':          # deleted record
            rows.append(None)
            continue
        row, p = {}, 1
        for name, ftype, flen, fdec in fields:
            raw = rec[p:p + flen]
            p += flen
            try:
                text = raw.decode('utf-8').strip()
            except UnicodeDecodeError:
                text = raw.decode('latin-1').strip()
            if ftype in 'NF':
                try:
                    row[name] = (float(text) if (fdec or '.' in text) else int(text)) if text else None
                except ValueError:
                    row[name] = None
            else:
                row[name] = text
        rows.append(row)
    return rows


def read_shp(data):
    """Polygon (type 5) and polyline (3) records as lists of rings [(x, y), ...]."""
    shapes, off = [], 100
    total = len(data)
    while off + 8 <= total:
        _, length = struct.unpack('>ii', data[off:off + 8])
        body = data[off + 8:off + 8 + length * 2]
        off += 8 + length * 2
        if len(body) < 4:
            shapes.append([])
            continue
        stype = struct.unpack('<i', body[:4])[0]
        if stype == 0:
            shapes.append([])
            continue
        if stype not in (3, 5, 13, 15, 23, 25):
            shapes.append([])
            continue
        n_parts, n_points = struct.unpack('<ii', body[36:44])
        parts = list(struct.unpack('<%di' % n_parts, body[44:44 + 4 * n_parts]))
        pts_off = 44 + 4 * n_parts
        coords = struct.unpack('<%dd' % (2 * n_points), body[pts_off:pts_off + 16 * n_points])
        rings = []
        for i, start in enumerate(parts):
            end = parts[i + 1] if i + 1 < n_parts else n_points
            rings.append([(coords[2 * k], coords[2 * k + 1]) for k in range(start, end)])
        shapes.append(rings)
    return shapes


def mercator_to_lonlat(x, y):
    lon = math.degrees(x / R_MERC)
    lat = math.degrees(2 * math.atan(math.exp(y / R_MERC)) - math.pi / 2)
    return lon, lat


def _perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify(ring, tol):
    """Iterative Douglas-Peucker; keeps first and last points."""
    n = len(ring)
    if n < 5 or tol <= 0:
        return list(ring)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0.0, -1
        a, b = ring[i], ring[j]
        for k in range(i + 1, j):
            d = _perp(ring[k], a, b)
            if d > best:
                best, idx = d, k
        if idx >= 0 and best > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(ring, keep) if k]


def ring_area(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return s / 2


def centroid(rings):
    """Area-weighted centroid of the largest ring (good enough for labels and hex placement)."""
    if not rings:
        return None
    ring = max(rings, key=lambda r: abs(ring_area(r)))
    a = ring_area(ring)
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return cx / (6 * a), cy / (6 * a)


def compact(rings, tol=0.004, min_area=1e-6, digits=4):
    """Simplify, drop slivers and round: [[lon, lat, lon, lat, ...], ...]."""
    out = []
    for r in rings:
        if len(r) < 4 or abs(ring_area(r)) < min_area:
            continue
        s = simplify(r, tol)
        if len(s) < 4:
            continue
        flat = []
        for x, y in s:
            flat += [round(x, digits), round(y, digits)]
        out.append(flat)
    if not out and rings:   # tiny constituency: keep its biggest ring unsimplified
        r = max(rings, key=lambda q: abs(ring_area(q)))
        out.append([round(v, digits) for p in r for v in p])
    return out


def geojson_rings(geom):
    """Outer and inner rings of a GeoJSON Polygon / MultiPolygon as lists of tuples."""
    if not geom:
        return []
    t, c = geom.get('type'), geom.get('coordinates') or []
    polys = [c] if t == 'Polygon' else c if t == 'MultiPolygon' else []
    return [[(p[0], p[1]) for p in ring] for poly in polys for ring in poly]
