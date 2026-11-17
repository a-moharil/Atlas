/* ATLAS raster atlas v4.1: no Leaflet/CDN dependency for satellite pane.
   Requests fixed allowlisted server tile routes. Blank/failed imagery stays visibly failed.
   This engine never synthesizes physical measurements or impact surfaces. */
(() => {
  "use strict";
  const focus = {
    world: [18, 15, 2],
    india: [22, 79, 5],
    europe: [49, 27, 5],
    gulf: [26, 51, 6],
    indo: [8, 112, 4],
  };
  const SOURCE_MAX = {
    esri: 18,
    osm: 18,
    nasa_base: 9,
    nasa_daily: 9,
    nasa: 9,
    fwi: 9,
    burn: 9,
  };
  const SOURCE_LABEL = {
    esri: "Esri satellite imagery",
    osm: "OpenStreetMap street tiles",
    nasa_base: "NASA Blue Marble (historical composite)",
    nasa_daily: "NASA VIIRS daily true-colour (date-dependent)",
    nasa: "NASA VIIRS thermal anomalies",
    fwi: "Copernicus fire-weather index",
    burn: "Copernicus burned area",
  };
  const $ = (x) => document.querySelector(x);
  let view = null;
  function clamp(x, a, b) {
    return Math.max(a, Math.min(b, x));
  }
  function project(lat, lon, z) {
    const t = Math.pow(2, z) * 256,
      y = (clamp(lat, -85.0511, 85.0511) * Math.PI) / 180;
    return [
      ((lon + 180) / 360) * t,
      ((1 - Math.log(Math.tan(Math.PI / 4 + y / 2)) / Math.PI) / 2) * t,
    ];
  }
  function unproject(x, y, z) {
    const t = Math.pow(2, z) * 256;
    return [
      (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / t))) * 180) / Math.PI,
      (x / t) * 360 - 180,
    ];
  }
  function tileUrl(provider, z, x, y, day) {
    return (
      `/api/map-tile/${provider}/${z}/${x}/${y}` +
      (day ? `?day=${encodeURIComponent(day)}` : "")
    );
  }
  function eventName(x) {
    return String(
      x?.properties?.title || x?.properties?.place || "Geographic event",
    );
  }
  function updateStatus() {
    if (!view) return;
    const v = view,
      el = $("#mapHealth");
    if (!el) return;
    const currently = v.visibleStatus || {};
    const counts = Object.entries(currently)
      .map(
        ([k, s]) =>
          `${k}: ${s.ready || 0} shown · ${s.loading || 0} pending · ${s.failed || 0} failed`,
      )
      .join(" | ");
    const overzoom = v.enabled
      .filter((p) => v.zoom > SOURCE_MAX[p])
      .map(
        (p) =>
          `${SOURCE_LABEL[p]} imagery only to z${SOURCE_MAX[p]}, resampled at z${v.zoom}`,
      );
    el.textContent =
      (counts || "No tile requests yet.") +
      (overzoom ? " | " + overzoom.join("; ") : "");
    const info = $("#mapInfo");
    if (info)
      info.textContent = `${SOURCE_LABEL[v.kind]} · ${
        v.enabled
          .slice(1)
          .map((k) => SOURCE_LABEL[k])
          .join(" / ") || "No data overlays"
      } · requested ${v.day}${
        v.availability
          ? " · NASA available: " +
            Object.entries(v.availability)
              .map(
                ([k, d]) =>
                  k +
                  " " +
                  d.latest +
                  (v.day > d.latest ? " (latest available substituted)" : ""),
              )
              .join(", ")
          : " · NASA availability unverified"
      } · © Esri/Maxar/Earthstar; NASA GIBS; Copernicus EFFIS; © OSM. ${overzoom.length ? "Upscaling does not add spatial detail." : ""}`;
  }
  function size() {
    const v = view;
    if (!v) return;
    const rc = v.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    v.w = Math.max(2, rc.width);
    v.h = Math.max(2, rc.height);
    v.canvas.width = Math.round(v.w * dpr);
    v.canvas.height = Math.round(v.h * dpr);
    v.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  function center() {
    const v = view;
    return project(v.lat, v.lon, v.zoom);
  }
  function setCenter(px, py) {
    const v = view;
    const ll = unproject(px, py, v.zoom);
    v.lat = clamp(ll[0], -84, 84);
    v.lon = ((((ll[1] + 180) % 360) + 360) % 360) - 180;
  }
  function normX(x, z) {
    return ((x % 2 ** z) + 2 ** z) % 2 ** z;
  }
  function directUrl(prov, z, x, y, day) {
    if (prov === "esri")
      return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
    if (prov === "osm")
      return `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
    if (prov === "nasa") {
      const size = 40075016.68557849 / 2 ** z,
        x0 = -20037508.342789244 + x * size,
        y1 = 20037508.342789244 - y * size;
      return (
        "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?" +
        new URLSearchParams({
          SERVICE: "WMS",
          VERSION: "1.1.1",
          REQUEST: "GetMap",
          LAYERS: "VIIRS_SNPP_Thermal_Anomalies_375m_All",
          STYLES: "",
          FORMAT: "image/png",
          TRANSPARENT: "TRUE",
          WIDTH: 256,
          HEIGHT: 256,
          SRS: "EPSG:3857",
          BBOX: [x0, y1 - size, x0 + size, y1].join(","),
          TIME: day,
        })
      );
    }
    if (prov === "nasa_daily")
      return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${day}/GoogleMapsCompatible_Level9/${z}/${y}/${x}.jpeg`;
    return null;
  }
  function imageFor(prov, z, x, y, day) {
    const latest = view?.availability?.[prov]?.latest;
    if (latest && day > latest) day = latest;
    const v = view,
      k = `${prov}:${z}:${x}:${y}:${day || ""}`;
    let rec = v.images.get(k);
    if (!rec) {
      rec = {
        state: "deferred",
        image: null,
        when: Date.now(),
        fallbackTried: false,
      };
      v.images.set(k, rec);
    }
    if (rec.state !== "deferred" || v.active >= v.maxActive) return rec;
    v.active++;
    rec.state = "loading";
    const image = new Image();
    rec.image = image;
    let finished = false;
    const timer = setTimeout(() => {
      rec.image.onload = null;
      rec.image.onerror = null;
      rec.image.src = "";
      finish(false);
    }, 26000);
    function finish(ok) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (!view || view !== v) return;
      v.active = Math.max(0, v.active - 1);
      rec.state = ok ? "ready" : "error";
      const stat = v.status.get(prov);
      stat[ok ? "ok" : "failed"]++;
      requestDraw();
      updateStatus();
    }
    image.onload = () => finish(true);
    image.onerror = () => {
      const alternative = directUrl(prov, z, x, y, day);
      if (!rec.fallbackTried && alternative) {
        rec.fallbackTried = true;
        rec.direct = true;
        const alternate = new Image();
        alternate.crossOrigin = "anonymous";
        rec.image = alternate;
        alternate.onload = () => finish(true);
        alternate.onerror = () => finish(false);
        alternate.src = alternative;
      } else finish(false);
    };
    image.src = tileUrl(prov, z, x, y, day);
    if (v.images.size > 600) {
      for (const [key, value] of v.images) {
        if (v.images.size <= 450) break;
        if (value.state !== "loading" && value.state !== "deferred")
          v.images.delete(key);
      }
    }
    return rec;
  }
  function fallbackAncestor(ctx, v, prov, z, x, y, day, dx, dy, side) {
    for (let delta = 1; delta <= Math.min(z, 7); delta++) {
      const az = z - delta,
        scale = 2 ** delta,
        ax = Math.floor(x / scale),
        ay = Math.floor(y / scale);
      const k = `${prov}:${az}:${ax}:${ay}:${day || ""}`,
        it = v.images.get(k);
      if (it?.state !== "ready") continue;
      const crop = 256 / scale,
        sx = (((x % scale) + scale) % scale) * crop,
        sy = (((y % scale) + scale) % scale) * crop;
      try {
        ctx.drawImage(it.image, sx, sy, crop, crop, dx, dy, side + 1, side + 1);
        return true;
      } catch (_) {}
    }
    return false;
  }
  function snapshot() {
    const v = view;
    if (!v || v.w < 20 || v.h < 20) return;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(v.w);
      canvas.height = Math.round(v.h);
      canvas
        .getContext("2d")
        .drawImage(
          v.canvas,
          0,
          0,
          v.canvas.width,
          v.canvas.height,
          0,
          0,
          v.w,
          v.h,
        );
      v.lastFrame = {
        canvas,
        lat: v.lat,
        lon: v.lon,
        zoom: v.zoom,
        w: v.w,
        h: v.h,
      };
    } catch (_) {
      v.lastFrame = null;
    }
  }
  function renderSnapshot(ctx, cx, cy) {
    const v = view,
      s = v.lastFrame;
    if (!s) return;
    const factor = 2 ** (v.zoom - s.zoom),
      orig = project(s.lat, s.lon, v.zoom);
    const x = v.w / 2 + (orig[0] - cx) - (s.w * factor) / 2,
      y = v.h / 2 + (orig[1] - cy) - (s.h * factor) / 2;
    ctx.save();
    ctx.globalAlpha = 0.9;
    try {
      ctx.drawImage(s.canvas, x, y, s.w * factor, s.h * factor);
    } catch (_) {}
    ctx.restore();
  }
  function requestDraw() {
    const v = view;
    if (!v || v.ticking) return;
    v.ticking = true;
    requestAnimationFrame(() => {
      if (view === v) {
        v.ticking = false;
        draw();
      }
    });
  }
  function coastlines(ctx, cx, cy) {
    const v = view;
    if (!v.coasts?.length) return;
    ctx.save();
    ctx.strokeStyle = "rgba(151,195,204,.46)";
    ctx.lineWidth = 0.9;
    for (const ring of v.coasts) {
      ctx.beginPath();
      let seen = false;
      let old = null;
      for (
        let i = 0;
        i < ring.length;
        i += Math.max(1, Math.floor(ring.length / 440))
      ) {
        const [lon, lat] = ring[i];
        let [p, q] = project(lat, lon, v.zoom);
        let x = p - cx + v.w / 2,
          y = q - cy + v.h / 2;
        while (x < -v.w / 2) x += 256 * 2 ** v.zoom;
        while (x > 1.5 * v.w) x -= 256 * 2 ** v.zoom;
        if (!seen || Math.abs(x - (old?.[0] || x)) > v.w) {
          ctx.moveTo(x, y);
          seen = true;
        } else ctx.lineTo(x, y);
        old = [x, y];
      }
      ctx.stroke();
    }
    ctx.restore();
  }
  // Official boundary of India (Survey of India via DataMeet), drawn on every basemap so
  // tiles that show de-facto lines (e.g. OpenStreetMap) cannot misrepresent the outline.
  function indiaBoundary(ctx, cx, cy) {
    const v = view;
    if (!v.india?.length || v.showIndia === false) return;
    ctx.save();
    ctx.strokeStyle = "rgba(240,180,90,.95)";
    ctx.lineWidth = v.zoom >= 6 ? 2 : 1.4;
    ctx.shadowColor = "rgba(0,0,0,.6)";
    ctx.shadowBlur = 3;
    const world = 256 * 2 ** v.zoom;
    for (const ring of v.india) {
      for (const shift of [-world, 0, world]) {
        ctx.beginPath();
        ring.forEach(([lon, lat], i) => {
          const [p, q] = project(lat, lon, v.zoom);
          const x = p - cx + v.w / 2 + shift, y = q - cy + v.h / 2;
          i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.stroke();
      }
    }
    ctx.restore();
  }
  function drawGeometries(ctx, cx, cy) {
    const v = view;
    function pos(ll) {
      const p = project(ll[1], ll[0], v.zoom);
      let x = p[0] - cx + v.w / 2;
      while (x < -v.w / 2) x += 256 * 2 ** v.zoom;
      while (x > 1.5 * v.w) x -= 256 * 2 ** v.zoom;
      return [x, p[1] - cy + v.h / 2];
    }
    function line(coords, close) {
      if (!Array.isArray(coords) || !coords.length) return;
      ctx.beginPath();
      let first = true,
        prev = null;
      for (const ll of coords) {
        if (!Array.isArray(ll) || ll.length < 2) continue;
        let [x, y] = pos(ll);
        if (prev && Math.abs(x - prev[0]) > v.w * 0.9) {
          ctx.moveTo(x, y);
        } else if (first) {
          ctx.moveTo(x, y);
          first = false;
        } else ctx.lineTo(x, y);
        prev = [x, y];
      }
      if (close) ctx.closePath();
    }
    for (const f of v.polys) {
      const type = f.geometry?.type,
        co = f.geometry?.coordinates;
      if (!co) continue;
      ctx.save();
      ctx.strokeStyle = "#ffac62";
      ctx.fillStyle = "rgba(246,108,49,.18)";
      ctx.lineWidth = 1.9;
      const polygons =
        type === "Polygon" ? [co] : type === "MultiPolygon" ? co : [];
      for (const polygon of polygons) {
        for (const ring of polygon) {
          line(ring, true);
          ctx.fill();
          ctx.stroke();
        }
      }
      ctx.restore();
    }
    for (const f of v.shakemap) {
      const type = f.geometry?.type,
        co = f.geometry?.coordinates;
      if (!co) continue;
      ctx.save();
      const m = Number(f.properties?.value ?? f.properties?.mmi ?? 4);
      ctx.strokeStyle =
        m >= 8
          ? "#ed4657"
          : m >= 6
            ? "#fb9452"
            : m >= 4
              ? "#ffdd87"
              : "#a6e0c1";
      ctx.lineWidth = 2.4;
      if (type === "LineString") line(co, false);
      if (type === "MultiLineString") for (const c of co) line(c, false);
      if (type === "Polygon") for (const c of co) line(c, true);
      ctx.stroke();
      ctx.restore();
    }
    v.hits = [];
    if (v.quakesVisible) {
      for (const f of v.quakes) {
        let ll = f.geometry?.coordinates;
        if (!ll || ll.length < 2) continue;
        let [x, y] = pos(ll);
        if (x < 0 || x > v.w || y < 0 || y > v.h) continue;
        const m = Number(f.properties?.mag || 0);
        const r = clamp(3 + m * 0.9, 4, 11);
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(244,199,121,.88)";
        ctx.fill();
        ctx.lineWidth = 1.7;
        ctx.strokeStyle = "#27242b";
        ctx.stroke();
        v.hits.push({ x, y, r: r + 7, f });
      }
    }
  }
  function graticule(ctx, cx, cy) {
    const v = view;
    ctx.save();
    ctx.strokeStyle = "rgba(43,91,110,.14)";
    ctx.lineWidth = 0.7;
    for (let lon = -180; lon <= 180; lon += 30) {
      ctx.beginPath();
      for (let lat = -80; lat <= 80; lat += 4) {
        let [x, y] = project(lat, lon, v.zoom);
        x -= cx - v.w / 2;
        y -= cy - v.h / 2;
        if (lat === -80) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    for (let lat = -60; lat <= 75; lat += 15) {
      ctx.beginPath();
      for (let lon = -180; lon <= 180; lon += 4) {
        let [x, y] = project(lat, lon, v.zoom);
        x -= cx - v.w / 2;
        y -= cy - v.h / 2;
        if (lon === -180) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.restore();
  }
  function draw() {
    const v = view;
    if (!v) return;
    const ctx = v.ctx,
      w = v.w,
      h = v.h;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#07141c";
    ctx.fillRect(0, 0, w, h);
    const [cx, cy] = center();
    graticule(ctx, cx, cy);
    renderSnapshot(ctx, cx, cy);
    const visibleStatus = {},
      maxRequests = 85;
    let tiles = 0,
      readyBase = 0;
    for (const prov of v.enabled) {
      const sourceZ = Math.min(v.zoom, SOURCE_MAX[prov]);
      const factor = 2 ** (v.zoom - sourceZ),
        side = 256 * factor;
      const minx = Math.floor((cx - w / 2) / side),
        maxx = Math.floor((cx + w / 2) / side),
        miny = Math.max(0, Math.floor((cy - h / 2) / side)),
        maxy = Math.min(2 ** sourceZ - 1, Math.floor((cy + h / 2) / side));
      const per = { ready: 0, loading: 0, failed: 0 };
      visibleStatus[prov] = per;
      const day = ["nasa", "nasa_daily", "fwi", "burn"].includes(prov)
        ? v.day
        : null;
      for (let y = miny; y <= maxy; y++)
        for (let x = minx; x <= maxx; x++) {
          if (++tiles > maxRequests) continue;
          const xt = normX(x, sourceZ),
            dx = x * side - cx + w / 2,
            dy = y * side - cy + h / 2;
          const rec = imageFor(prov, sourceZ, xt, y, day);
          if (rec.state === "ready") {
            try {
              ctx.save();
              ctx.globalAlpha =
                prov === "fwi"
                  ? 0.55
                  : prov === "burn"
                    ? 0.84
                    : prov === "nasa"
                      ? 0.95
                      : 1;
              ctx.drawImage(rec.image, dx, dy, side + 1, side + 1);
              ctx.restore();
              per.ready++;
              if (prov === v.kind) readyBase++;
            } catch (e) {
              ctx.restore();
              per.failed++;
            }
          } else {
            per[rec.state === "error" ? "failed" : "loading"]++;
            if (prov === v.kind)
              fallbackAncestor(ctx, v, prov, sourceZ, xt, y, day, dx, dy, side);
          }
        }
    }
    if (readyBase > 0) v.lastFrame = null;
    if (readyBase === 0) {
      coastlines(ctx, cx, cy);
      ctx.save();
      ctx.fillStyle = "#cfe3ea";
      ctx.font = "600 15px 'Schibsted Grotesk', system-ui";
      ctx.fillText("Geographic context · awaiting satellite imagery", 18, 33);
      ctx.fillStyle = "#8aa1aa";
      ctx.font = "13px 'Schibsted Grotesk', system-ui";
      ctx.fillText(
        "No imagery is invented; check provider status below.",
        18,
        55,
      );
      ctx.restore();
    }
    v.visibleStatus = visibleStatus;
    indiaBoundary(ctx, cx, cy);
    drawGeometries(ctx, cx, cy);
    if (!v.statusUpdatePending) {
      v.statusUpdatePending = true;
      setTimeout(() => {
        if (view === v) {
          v.statusUpdatePending = false;
          updateStatus();
        }
      }, 250);
    }
  }
  function mount(root) {
    unmount();
    const canvas = $("#satCanvas");
    if (!canvas) return;
    const fl = focus.india;
    view = {
      root,
      canvas,
      ctx: canvas.getContext("2d"),
      lat: fl[0],
      lon: fl[1],
      zoom: fl[2],
      w: 10,
      h: 10,
      kind:
        root.mapMode === "street"
          ? "osm"
          : root.mapMode === "nasa"
            ? "nasa_base"
            : root.mapMode === "daily"
              ? "nasa_daily"
              : "esri",
      images: new Map(),
      active: 0,
      maxActive: 6,
      lastFrame: null,
      ticking: false,
      status: new Map(),
      day: date(root.dateOffset),
      enabled: [],
      polys: [],
      quakes: [],
      shakemap: [],
      hits: [],
      quakesVisible: false,
      coasts: [],
      drag: null,
    };
    view._obs = new ResizeObserver(size);
    view._obs.observe(canvas);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", wheel, { passive: false });
    sync(root);
    size();
    availability(view);
    fetch("/coastlines.json")
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => {
        if (view) {
          view.coasts = d;
          requestDraw();
        }
      })
      .catch(() => {});
    fetch("/data/india_outline_soi.geojson")
      .then((r) => (r.ok ? r.json() : null))
      .then((g) => {
        if (view && g)
          view.india = g.features.flatMap((f) =>
            (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates).map((poly) => poly[0]),
          );
        requestDraw();
      })
      .catch(() => {});
    loadCatalogs();
  }
  async function availability(v) {
    try {
      const r = await fetch("/api/nasa-availability", {
        signal: AbortSignal.timeout(8000),
      });
      const data = await r.json();
      if (view !== v) return;
      if (data.layers) {
        v.availability = data.layers;
        requestDraw();
        updateStatus();
      }
      if (data.pending)
        setTimeout(() => {
          if (view === v) availability(v);
        }, 2000);
    } catch (_) {}
  }
  function date(off) {
    let d = new Date();
    d.setUTCDate(d.getUTCDate() - Number(off || 0));
    return d.toISOString().slice(0, 10);
  }
  function sync(root) {
    if (!view) return;
    const v = view;
    let enabled = [
      root.mapMode === "street"
        ? "osm"
        : root.mapMode === "nasa"
          ? "nasa_base"
          : root.mapMode === "daily"
            ? "nasa_daily"
            : "esri",
    ];
    if (root.fireLayer) enabled.push("nasa");
    if (root.effisFwi) enabled.push("fwi");
    if (root.effisBurn) enabled.push("burn");
    v.day = date(root.dateOffset);
    v.kind = enabled[0];
    v.enabled = enabled;
    v.quakesVisible = root.earthLayer;
    v.polys = root.eventsLayer ? v.allPolys || [] : [];
    v.showIndia = root.indiaBoundary !== false;
    for (const p of enabled)
      if (!v.status.has(p)) v.status.set(p, { ok: 0, failed: 0 });
    requestDraw();
    updateStatus();
  }
  function focusOn(which) {
    if (!view) return;
    snapshot();
    const [lat, lon, z] = focus[which] || focus.world;
    Object.assign(view, { lat, lon, zoom: z });
    requestDraw();
  }
  function down(e) {
    const v = view;
    if (!v) return;
    v.canvas.setPointerCapture(e.pointerId);
    v.drag = { x: e.clientX, y: e.clientY, origin: center(), moved: false };
  }
  function move(e) {
    const v = view;
    if (!v?.drag) return;
    let dx = e.clientX - v.drag.x,
      dy = e.clientY - v.drag.y;
    if (Math.hypot(dx, dy) > 4) v.drag.moved = true;
    setCenter(v.drag.origin[0] - dx, v.drag.origin[1] - dy);
    requestDraw();
  }
  function up(e) {
    const v = view;
    if (!v?.drag) return;
    let moved = v.drag.moved;
    v.drag = null;
    if (!moved) {
      const p = v.canvas.getBoundingClientRect();
      const x = e.clientX - p.left,
        y = e.clientY - p.top;
      const hit = v.hits.find((h) => Math.hypot(h.x - x, h.y - y) < h.r);
      if (hit) selectQuake(hit.f);
    }
  }
  function wheel(e) {
    e.preventDefault();
    const v = view;
    if (!v) return;
    const next = clamp(v.zoom + (e.deltaY < 0 ? 1 : -1), 2, 16);
    if (next === v.zoom) return;
    const rect = v.canvas.getBoundingClientRect();
    let x = e.clientX - rect.left - v.w / 2,
      y = e.clientY - rect.top - v.h / 2;
    let c = center(),
      anchor = unproject(c[0] + x, c[1] + y, v.zoom);
    snapshot();
    v.zoom = next;
    let scaled = project(anchor[0], anchor[1], next);
    setCenter(scaled[0] - x, scaled[1] - y);
    requestDraw();
  }
  function zoomBy(d) {
    if (view) {
      snapshot();
      view.zoom = clamp(view.zoom + d, 2, 16);
      requestDraw();
    }
  }
  function selectQuake(f) {
    const l = $("#shakemapState");
    if (l)
      l.textContent = `${eventName(f)} · click ShakeMap in the catalogue to inspect an authoritative intensity field.`;
  }
  async function loadCatalogs() {
    const v = view;
    if (!v) return;
    const health = $("#mapCatalogStatus");
    if (health)
      health.textContent =
        "Retrieving NASA EONET / USGS geographic catalogues…";
    try {
      const results = await Promise.allSettled([
        fetch("/api/map-geojson?layer=wildfire_events").then((r) => r.json()),
        fetch("/api/map-geojson?layer=earthquakes").then((r) => r.json()),
      ]);
      if (view !== v) return;
      const a = results[0].status === "fulfilled" ? results[0].value : null,
        b = results[1].status === "fulfilled" ? results[1].value : null;
      v.allPolys = (a?.features || []).filter((f) =>
        ["Polygon", "MultiPolygon"].includes(f.geometry?.type),
      );
      v.quakes = (b?.features || []).filter(
        (f) => f.geometry?.type === "Point",
      );
      sync(v.root);
      if (health)
        health.textContent = `NASA: ${a?.status || "unavailable"} (${v.allPolys.length} polygon features) · USGS: ${b?.status || "unavailable"} (${v.quakes.length} earthquakes). Source events may be represented by points only.`;
      const list = $("#quakeList");
      if (list)
        list.innerHTML =
          v.quakes
            .slice(0, 12)
            .map(
              (f, i) =>
                `<div class="quakeRow"><span>${String(
                  f.properties?.title || "USGS event",
                )
                  .replace(/[<>&]/g, "")
                  .slice(
                    0,
                    75,
                  )}</span><button class="action" data-shake-native="${i}">Shaking field</button></div>`,
            )
            .join("") ||
          '<p class="fine">No current earthquake catalogue records.</p>';
    } catch (e) {
      if (health) health.textContent = "Catalogues unavailable: " + e.message;
    }
  }
  async function showShakeMap(value) {
    const v = view;
    if (!v) return;
    const f = Number.isInteger(value)
      ? v.quakes[value]
      : v.quakes.find((q) => q.properties?.detail === value);
    if (!f) return;
    const detail = f.properties?.detail;
    const s = $("#shakemapState");
    if (s) s.textContent = "Retrieving USGS ShakeMap intensity contours…";
    try {
      const res = await fetch(
        "/api/shakemap?detail=" + encodeURIComponent(detail),
      );
      const out = await res.json();
      if (!res.ok || out.status !== "ok") {
        if (s)
          s.textContent =
            out.reason || "This event has no available ShakeMap product";
        return;
      }
      if (view !== v) return;
      v.shakemap = out.features?.features || [];
      const coord = f.geometry.coordinates;
      v.lat = coord[1];
      v.lon = coord[0];
      v.zoom = 7;
      requestDraw();
      if (s)
        s.innerHTML = `${v.shakemap.length} official USGS contour features. <a href="${String(out.source || "https://earthquake.usgs.gov").replace(/"/g, "")}" target="_blank" rel="noopener noreferrer">Original ShakeMap product ↗</a>`;
    } catch (e) {
      if (s) s.textContent = "ShakeMap request failed: " + e.message;
    }
  }
  async function diagnostics() {
    const out = $("#mapHealth"),
      v = view;
    if (!v) return;
    const diagnosticDay = [
      v.day,
      ...Object.values(v.availability || {})
        .map((x) => x.latest)
        .filter(Boolean),
    ].sort()[0];
    try {
      out.textContent = "Inspecting actual server tile request outcomes…";
      const [a, b] = await Promise.all([
        fetch("/api/map-provider-status").then((r) => r.json()),
        fetch("/api/map-health?day=" + encodeURIComponent(diagnosticDay)).then(
          (r) => r.json(),
        ),
      ]);
      if (view !== v) return;
      const lines = (a.providers || []).map(
        (p) =>
          `${p.name}: ${p.success} tile successes, ${p.failed} failures${p.error ? " · latest: " + p.error : ""}`,
      );
      const checks = (b.probes || []).map(
        (p) =>
          `${p.id}: ${p.success ? "valid " + p.mime_type + " (" + p.bytes + " bytes)" : "image unavailable · " + p.error}`,
      );
      const target = $("#mapDiagnostics");
      if (target)
        target.textContent =
          "Probe date: " +
          diagnosticDay +
          " (requested " +
          v.day +
          ")\n" +
          lines.join("\n") +
          "\n" +
          checks.join("\n");
      out.textContent =
        "Provider diagnostics complete; see the results underneath the map.";
    } catch (e) {
      if (out) out.textContent = "Diagnostics failed: " + e.message;
    }
  }
  function retry() {
    if (!view) return;
    const v = view;
    for (const [k, item] of v.images)
      if (item.state === "error" || item.state === "deferred")
        v.images.delete(k);
    v.lastFrame = null;
    requestDraw();
    const out = $("#mapDiagnostics");
    if (out)
      out.textContent =
        "Manual retry requested. A failed provider has a 20-second retry cooldown; successful cached imagery remains.";
  }
  function inspect() {
    if (!view) return null;
    return {
      zoom: view.zoom,
      provider: view.kind,
      active: view.active,
      visible: view.visibleStatus,
      overzoom: view.enabled.filter((p) => view.zoom > SOURCE_MAX[p]),
      lat: view.lat,
      lon: view.lon,
    };
  }
  function unmount() {
    if (!view) return;
    try {
      view._obs.disconnect();
    } catch (e) {}
    view = null;
  }
  window.ATLASTileMap = {
    mount,
    unmount,
    sync,
    focusOn,
    loadCatalogs,
    showShakeMap,
    zoomBy,
    retry,
    diagnostics,
    inspect,
  };
})();
