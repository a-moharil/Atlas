"use strict";
/* Atlas v5 · Earth watch.
   Live wind / temperature / rain / ocean-current fields (Open-Meteo grid, animated locally),
   natural-hazard events (GDACS, NASA EONET, USGS) and the global temperature anomaly
   (Copernicus Climate Pulse / ERA5). Nothing is drawn that a provider did not return. */
window.ATLASEarth = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const st = { region: "global", mode: "wind", india: "windy", kinds: new Set(), indiaOnly: false, sel: null };
  let fields = {}, hazards = null, climate = null, coast = null, india = null;
  let raf = 0, timers = [], particles = [], base = null, trail = null, ctx = null, view = null, alive = false;
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const BOX = { global: { lon: [-180, 180], lat: [-62, 76] }, india: { lon: [64, 101], lat: [4.5, 38.5] } };
  const KIND = {
    cyclone: ["Cyclones and storms", "#a99cf2"], flood: ["Floods", "#5d8ff0"], earthquake: ["Earthquakes", "#f0b45a"], wildfire: ["Wildfires", "#f06a5b"],
    volcano: ["Volcanoes", "#ff8a5c"], drought: ["Droughts", "#d9b37a"], heat: ["Temperature extremes", "#ff6f91"], ice: ["Sea and lake ice", "#bfe8f4"],
    dust: ["Dust and haze", "#c9b28f"], landslide: ["Landslides", "#9e8b73"], tsunami: ["Tsunamis", "#5ee0d0"], snow: ["Snow", "#e6f2f6"], water: ["Water colour", "#5ed3a4"], other: ["Other", "#8aa1aa"], manmade: ["Human-made", "#8aa1aa"],
  };
  const LEVEL = { red: "#f06a5b", orange: "#f0b45a", green: "#5ed3a4", observed: "#8fd9e8" };

  const WINDY = { wind: "wind", temp: "temp", rain: "rain", ocean: "currents" };
  function windyURL() {
    return "https://embed.windy.com/embed.html?type=map&location=coordinates&metricRain=default&metricTemp=default&metricWind=default&zoom=5&level=surface&lat=22.5&lon=80&product=ecmwf&overlay=" + (WINDY[st.mode] || "wind");
  }
  const useWindy = () => st.region === "india" && st.india === "windy";
  function syncWindy() {
    const host = document.querySelector(".ewMap"), fr = document.querySelector("#ewWindy"), sw = document.querySelector("#ewIndiaSrc");
    if (sw) sw.hidden = st.region !== "india";
    document.querySelectorAll("[data-ewindia]").forEach((x) => x.classList.toggle("active", x.dataset.ewindia === st.india));
    if (!host) return;
    host.classList.toggle("windyOn", useWindy());
    if (useWindy()) {
      if (fr.dataset.src !== windyURL()) { fr.src = windyURL(); fr.dataset.src = windyURL(); }
      const stamp = document.querySelector("#ewStamp"); if (stamp) stamp.textContent = "Windy · ECMWF model, about 9 km";
      const m = document.querySelector("#ewMethod"); if (m) m.textContent = "India view by Windy (ECMWF high-resolution forecast). Layers, time slider and basemap belong to Windy; its basemap may draw borders that differ from the official map of India. Switch to Atlas grid for the Survey of India outline and hazard markers.";
    }
  }
  function layout() {
    return `<div class="heroTitle"><div><h1>Earth watch</h1><p>Wind, temperature, rain and ocean currents right now, every hazard the global alert systems are tracking, and how far today's planet sits from its 1991–2020 normal.</p></div></div>
    <section class="panel ewStage">
      <div class="ewBar"><div class="filterTabs" style="margin:0">${[["wind", "Wind"], ["temp", "Temperature"], ["rain", "Rain"], ["ocean", "Ocean currents"]].map(([k, v]) => `<button class="choice ${st.mode === k ? "active" : ""}" data-ewmode="${k}">${v}</button>`).join("")}</div>
       <div class="filterTabs" style="margin:0">${[["global", "Globe"], ["india", "India"]].map(([k, v]) => `<button class="choice ${st.region === k ? "active" : ""}" data-ewregion="${k}">${v}</button>`).join("")}</div>
       <div class="filterTabs" id="ewIndiaSrc" style="margin:0" ${st.region === "india" ? "" : "hidden"}>${[["windy", "Windy · 9 km"], ["atlas", "Atlas grid"]].map(([k, v]) => `<button class="choice ${st.india === k ? "active" : ""}" data-ewindia="${k}">${v}</button>`).join("")}</div>
       <span class="spacer"></span><span id="ewStamp" class="fine">Loading field…</span><button class="action" id="ewRefresh">Refresh</button></div>
      <div class="ewMap"><iframe id="ewWindy" title="Windy weather map of India" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe><canvas id="ewBase"></canvas><canvas id="ewTrail"></canvas><div id="ewPins" class="ewPins"></div><div id="ewTip" class="mapTip" hidden></div><div id="ewLegend" class="ewLegend"></div></div>
      <p class="fine" id="ewMethod">Open-Meteo model analysis on a coarse grid; motion is interpolated for display only.</p>
    </section>
    <div class="two" style="margin-top:16px"><div class="stack">
      <section class="panel"><div class="panelHeading"><h2>Active hazards</h2><span id="ewHzStamp" class="fine"></span></div><div id="ewKinds" class="ewKinds"></div><label class="fine" style="display:flex;gap:8px;align-items:center;margin:4px 0 10px"><input type="checkbox" id="ewIndiaOnly" ${st.indiaOnly ? "checked" : ""}> Only in or near India</label><div id="ewList" class="ewList"><p class="fine">Retrieving GDACS, NASA EONET and USGS…</p></div></section>
     </div><div class="stack">
      <section class="panel"><div class="panelHeading"><h2>Planetary temperature</h2><a class="fine" href="https://pulse.climate.copernicus.eu/" target="_blank" rel="noopener noreferrer">Climate Pulse ↗</a></div><div id="ewClimate"><p class="fine">Retrieving Copernicus ERA5 series…</p></div></section>
      <section class="panel"><h2>Sources</h2><p class="fine">Fields: Open-Meteo forecast and marine APIs (current analysis). Hazards: GDACS (UN / European Commission JRC) alert levels, NASA EONET open events, USGS M4.5+ earthquakes. Climate: Copernicus Climate Change Service / ECMWF ERA5 daily global means. All are fetched by your Atlas server and cached; none require keys.</p></section>
     </div></div>`;
  }

  // ---------- projection ----------
  function proj() {
    const b = BOX[st.region], W = view.w, H = view.h;
    const midLat = (b.lat[0] + b.lat[1]) / 2, k = st.region === "india" ? Math.cos((midLat * Math.PI) / 180) : 1;
    const sx = W / ((b.lon[1] - b.lon[0]) * k), sy = H / (b.lat[1] - b.lat[0]);
    const s = Math.min(sx, sy), ox = (W - (b.lon[1] - b.lon[0]) * k * s) / 2, oy = (H - (b.lat[1] - b.lat[0]) * s) / 2;
    return { s, k, ox, oy, x: (lon) => ox + (lon - b.lon[0]) * k * s, y: (lat) => oy + (b.lat[1] - lat) * s, lon: (x) => b.lon[0] + (x - ox) / (k * s), lat: (y) => b.lat[1] - (y - oy) / s };
  }
  function sample(f, key, lon, lat) {
    if (!f) return null;
    const lats = f.lats, lons = f.lons, g = f[key];
    const dLat = lats[0] - lats[1], dLon = lons[1] - lons[0];
    let fy = (lats[0] - lat) / dLat;
    if (fy < 0 || fy > lats.length - 1) return null;
    let L = lon;
    if (st.region === "global") { while (L < lons[0]) L += 360; while (L >= lons[0] + 360) L -= 360; }
    let fx = (L - lons[0]) / dLon;
    const wrap = st.region === "global";
    if (!wrap && (fx < 0 || fx > lons.length - 1)) return null;
    const x0 = Math.floor(fx), y0 = Math.floor(fy), tx = fx - x0, ty = fy - y0;
    const at = (r, c) => { if (wrap) c = ((c % lons.length) + lons.length) % lons.length; return g[Math.min(r, lats.length - 1)]?.[Math.min(c, lons.length - 1)]; };
    const a = at(y0, x0), b = at(y0, x0 + 1), c = at(y0 + 1, x0), d = at(y0 + 1, x0 + 1);
    if ([a, b, c, d].some((v) => v === null || v === undefined)) {
      const any = [a, b, c, d].filter((v) => v !== null && v !== undefined);
      return any.length >= 2 ? any.reduce((p, q) => p + q, 0) / any.length : null;
    }
    return a * (1 - tx) * (1 - ty) + b * tx * (1 - ty) + c * (1 - tx) * ty + d * tx * ty;
  }

  // ---------- colour ramps ----------
  const lerp = (a, b, t) => a + (b - a) * t;
  function ramp(stops, t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < stops.length; i++) if (t <= stops[i][0]) {
      const [t0, c0] = stops[i - 1], [t1, c1] = stops[i], u = (t - t0) / (t1 - t0 || 1);
      return c0.map((v, j) => Math.round(lerp(v, c1[j], u)));
    }
    return stops[stops.length - 1][1];
  }
  const TEMP = [[0, [44, 72, 160]], [.3, [70, 150, 210]], [.5, [200, 232, 236]], [.68, [240, 200, 110]], [.84, [236, 120, 70]], [1, [190, 40, 60]]];
  const RAIN = [[0, [143, 217, 232]], [.4, [80, 140, 240]], [.75, [150, 110, 240]], [1, [240, 120, 220]]];
  const SPEED = [[0, [70, 140, 160]], [.35, [143, 217, 232]], [.7, [240, 230, 200]], [1, [240, 180, 90]]];

  // ---------- drawing ----------
  function drawBase() {
    const c = base.getContext("2d"), P = proj(), W = view.w, H = view.h, dpr = view.dpr;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const f = fields[fkey()];
    // scalar field as a smooth low-res image
    const key = st.mode === "temp" ? "temp" : st.mode === "rain" ? "precip" : st.mode === "ocean" ? "sst" : null;
    if (f && key && f[key]) {
      const cols = 220, rows = Math.round((cols * H) / W), img = c.createImageData(cols, rows);
      for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++) {
        const lon = P.lon((q / cols) * W), lat = P.lat((r / rows) * H);
        const v = sample(f, key, lon, lat);
        if (v === null) continue;
        let rgb, a = 150;
        if (key === "temp" || key === "sst") rgb = ramp(TEMP, (v + 25) / 70);
        else { if (v < 0.05) continue; rgb = ramp(RAIN, Math.sqrt(v / 8)); a = Math.min(220, 90 + v * 40); }
        const i = (r * cols + q) * 4; img.data[i] = rgb[0]; img.data[i + 1] = rgb[1]; img.data[i + 2] = rgb[2]; img.data[i + 3] = a;
      }
      const tmp = document.createElement("canvas"); tmp.width = cols; tmp.height = rows; tmp.getContext("2d").putImageData(img, 0, 0);
      c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high"; c.globalAlpha = .85; c.drawImage(tmp, 0, 0, W, H); c.globalAlpha = 1;
    }
    // coastlines
    if (coast) {
      c.strokeStyle = "rgba(190,228,240,.42)"; c.lineWidth = .8; c.beginPath();
      for (const ring of coast) {
        let prev = null;
        ring.forEach(([lon, lat], i) => {
          const x = P.x(lon), y = P.y(lat);
          if (!i || (prev !== null && Math.abs(lon - prev) > 180)) c.moveTo(x, y); else c.lineTo(x, y);
          prev = lon;
        });
      }
      c.stroke();
    }
    // official India boundary
    if (india) {
      c.strokeStyle = st.region === "india" ? "rgba(240,180,90,.9)" : "rgba(240,180,90,.7)"; c.lineWidth = st.region === "india" ? 1.4 : 1; c.beginPath();
      for (const poly of india) for (const ring of poly) ring.forEach(([lon, lat], i) => (i ? c.lineTo(P.x(lon), P.y(lat)) : c.moveTo(P.x(lon), P.y(lat))));
      c.stroke();
    }
    // graticule
    c.strokeStyle = "rgba(190,228,240,.06)"; c.lineWidth = 1; c.beginPath();
    const step = st.region === "india" ? 5 : 30, b = BOX[st.region];
    for (let lon = Math.ceil(b.lon[0] / step) * step; lon <= b.lon[1]; lon += step) { c.moveTo(P.x(lon), P.y(b.lat[0])); c.lineTo(P.x(lon), P.y(b.lat[1])); }
    for (let lat = Math.ceil(b.lat[0] / step) * step; lat <= b.lat[1]; lat += step) { c.moveTo(P.x(b.lon[0]), P.y(lat)); c.lineTo(P.x(b.lon[1]), P.y(lat)); }
    c.stroke();
    legend();
  }
  function legend() {
    const el = document.querySelector("#ewLegend"); if (!el) return;
    const bar = (stops, a, b, unit) => `<div class="ewRamp" style="background:linear-gradient(90deg,${stops.map(([t, c]) => `rgb(${c}) ${t * 100}%`).join(",")})"></div><div class="ewRampLbl"><span>${a}</span><span>${unit}</span><span>${b}</span></div>`;
    el.innerHTML = st.mode === "temp" ? bar(TEMP, "−25°", "45°", "2 m air °C") : st.mode === "rain" ? bar(RAIN, "0", "8+", "mm / hour") : st.mode === "ocean" ? bar(TEMP, "−25°", "45°", "sea surface °C") + bar(SPEED, "slow", "fast", "current") : bar(SPEED, "calm", "25+ m/s", "10 m wind");
  }
  function fkey() { return st.region + ":" + (st.mode === "ocean" ? "ocean" : "atmosphere"); }
  function seed(n) {
    const P = proj(); particles = [];
    for (let i = 0; i < n; i++) particles.push(spawn(P));
  }
  function spawn(P) { return { x: Math.random() * view.w, y: Math.random() * view.h, age: Math.floor(Math.random() * 90) }; }
  function step() {
    if (!alive) return;
    const f = fields[fkey()], c = trail.getContext("2d"), P = proj(), dpr = view.dpr;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.globalCompositeOperation = "destination-in"; c.fillStyle = "rgba(0,0,0,.92)"; c.fillRect(0, 0, view.w, view.h);
    c.globalCompositeOperation = "source-over";
    if (f && f.u) {
      const scale = (st.mode === "ocean" ? 0.09 : 0.022) * (st.region === "india" ? 0.32 : 1);
      c.lineWidth = st.region === "india" ? 1.5 : 1.25;
      for (const p of particles) {
        const lon = P.lon(p.x), lat = P.lat(p.y);
        const u = sample(f, "u", lon, lat), v = sample(f, "v", lon, lat);
        if (u === null || v === null || p.age++ > 110) { Object.assign(p, spawn(P), { age: 0 }); continue; }
        const sp = Math.hypot(u, v), nlon = lon + (u * scale) / Math.max(.2, Math.cos((lat * Math.PI) / 180)), nlat = lat + v * scale;
        const nx = P.x(nlon), ny = P.y(nlat);
        const col = ramp(SPEED, sp / (st.mode === "ocean" ? 3 : 22));
        c.strokeStyle = `rgba(${col},${Math.min(.95, .5 + sp / 25)})`;
        c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(nx, ny); c.stroke();
        p.x = nx; p.y = ny;
        if (p.x < 0 || p.x > view.w || p.y < 0 || p.y > view.h) Object.assign(p, spawn(P), { age: 0 });
      }
    }
    if (!REDUCED) raf = requestAnimationFrame(step);
  }
  function pins() {
    const el = document.querySelector("#ewPins"); if (!el || !view) return;
    const P = proj(), b = BOX[st.region];
    const ev = visibleEvents().filter((e) => e.lon >= b.lon[0] && e.lon <= b.lon[1] && e.lat >= b.lat[0] && e.lat <= b.lat[1]).slice(0, 400);
    el.innerHTML = ev.map((e, i) => {
      const col = KIND[e.kind]?.[1] || "#8aa1aa", ring = LEVEL[e.level] || "#8fd9e8", r = e.level === "red" ? 9 : e.level === "orange" ? 7.5 : 5.5;
      return `<button class="ewPin ${e.level === "red" ? "hot" : ""} ${st.sel === e.id ? "sel" : ""}" data-ewpin="${esc(e.id)}" style="left:${P.x(e.lon).toFixed(1)}px;top:${P.y(e.lat).toFixed(1)}px;--c:${col};--r:${ring};--s:${r * 2}px" aria-label="${esc(e.title)}"></button>`;
    }).join("");
  }
  function visibleEvents() {
    let ev = hazards?.events || [];
    if (st.indiaOnly) ev = ev.filter((e) => e.lat >= 4 && e.lat <= 38.5 && e.lon >= 64 && e.lon <= 101);
    if (st.kinds.size) ev = ev.filter((e) => st.kinds.has(e.kind));
    return ev;
  }
  function list() {
    const el = document.querySelector("#ewList"), kinds = document.querySelector("#ewKinds"), stamp = document.querySelector("#ewHzStamp");
    if (!el) return;
    if (!hazards?.events?.length) { el.innerHTML = `<p class="fine">${hazards?.pending ? "Retrieving GDACS, NASA EONET and USGS…" : esc(hazards?.error || "No events returned by the providers.")}</p>`; return; }
    if (stamp) stamp.textContent = Object.entries(hazards.providers || {}).map(([k, v]) => `${k}: ${v.state === "ok" ? v.count : "unavailable"}`).join(" · ");
    const counts = {}; for (const e of hazards.events) counts[e.kind] = (counts[e.kind] || 0) + 1;
    kinds.innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<button class="ewKind ${st.kinds.has(k) ? "on" : ""}" data-ewkind="${esc(k)}" style="--c:${KIND[k]?.[1] || "#8aa1aa"}"><i></i>${esc(KIND[k]?.[0] || k)}<b>${n}</b></button>`).join("");
    const ev = visibleEvents().slice().sort((a, b) => ({ red: 0, orange: 1 }[a.level] ?? 2) - ({ red: 0, orange: 1 }[b.level] ?? 2) || (b.time || "").localeCompare(a.time || "")).slice(0, 80);
    el.innerHTML = ev.length ? ev.map((e) => `<button class="ewRow ${st.sel === e.id ? "sel" : ""}" data-ewpin="${esc(e.id)}"><i class="lvl ${esc(e.level)}" style="--c:${KIND[e.kind]?.[1] || "#8aa1aa"}"></i><span><b>${esc(e.title)}</b><small>${esc([KIND[e.kind]?.[0] || e.kind, e.severity, e.time ? new Date(e.time + (e.time.length === 19 ? "Z" : "")).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "", e.source].filter(Boolean).join(" · "))}</small></span></button>`).join("") : '<p class="fine">No events match these filters.</p>';
  }
  function showEvent(id) {
    const e = (hazards?.events || []).find((x) => x.id === id), tip = document.querySelector("#ewTip");
    st.sel = id; pins(); list();
    if (!e || !tip) return;
    if (st.region === "global" || (e.lon >= 64 && e.lon <= 101 && e.lat >= 4 && e.lat <= 38.5)) {
      const P = proj();
      tip.hidden = false; tip.style.left = P.x(e.lon) + "px"; tip.style.top = P.y(e.lat) + "px";
      tip.innerHTML = `<b>${esc(e.title)}</b><br><span class="fine">${esc([e.severity, e.country].filter(Boolean).join(" · "))}</span><br><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer" style="pointer-events:auto">${esc(e.source)} report ↗</a>`;
    }
  }
  function climateHTML(d) {
    if (!d?.series) return `<p class="fine">${d?.pending ? "Retrieving Copernicus ERA5 series…" : esc(d?.error || "Climate Pulse unavailable.")}</p>`;
    const block = (key, title) => {
      const s = d.series[key]; if (!s) return "";
      const pts = s.points.slice(-730).filter((p) => p.anomaly !== null);
      if (!pts.length) return "";
      const W = 520, H = 150, pad = 26, lo = Math.min(-0.2, ...pts.map((p) => p.anomaly)), hi = Math.max(0.2, ...pts.map((p) => p.anomaly));
      const x = (i) => pad + ((W - pad - 6) * i) / (pts.length - 1 || 1), y = (v) => 8 + ((H - 26) * (hi - v)) / (hi - lo || 1);
      const line = pts.map((p, i) => `${x(i).toFixed(1)},${y(p.anomaly).toFixed(1)}`).join(" ");
      const area = `${x(0)},${y(0)} ${line} ${x(pts.length - 1)},${y(0)}`;
      const ticks = [0, Math.floor(pts.length / 2), pts.length - 1].map((i) => `<text x="${x(i)}" y="${H - 4}" text-anchor="middle" class="chartAxis">${esc(pts[i].date.slice(0, 7))}</text>`).join("");
      const L = s.latest;
      return `<div class="ewClim"><div class="ewClimHead"><div><b class="ewBig">${L.anomaly >= 0 ? "+" : ""}${(L.anomaly ?? 0).toFixed(2)}°C</b><span>${esc(title)} vs 1991–2020 on ${esc(L.date)}${L.status && L.status !== "final" ? " (preliminary)" : ""}</span></div><div class="ewClimSide"><span>${esc(L.value.toFixed(2))}°C absolute</span>${s.year_to_date_anomaly !== null ? `<span>${s.year_to_date_anomaly >= 0 ? "+" : ""}${s.year_to_date_anomaly.toFixed(2)}°C year to date</span>` : ""}</div></div>
       <svg viewBox="0 0 ${W} ${H}" class="ewSpark" role="img" aria-label="${esc(title)} anomaly, last two years"><defs><linearGradient id="g${key}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#f0b45a" stop-opacity=".45"/><stop offset="1" stop-color="#f0b45a" stop-opacity="0"/></linearGradient></defs><line x1="${pad}" x2="${W - 6}" y1="${y(0)}" y2="${y(0)}" stroke="rgba(190,228,240,.25)" stroke-dasharray="3 4"/><text x="${pad - 4}" y="${y(0) + 4}" text-anchor="end" class="chartAxis">0</text><text x="${pad - 4}" y="${y(hi) + 8}" text-anchor="end" class="chartAxis">+${hi.toFixed(1)}</text><polygon points="${area}" fill="url(#g${key})"/><polyline points="${line}" fill="none" stroke="#f0b45a" stroke-width="1.4"/>${ticks}</svg></div>`;
    };
    return block("air", "Global surface air") + block("sst", "Sea surface (60°S–60°N)") + `<p class="fine">${esc(d.method || "")}</p>`;
  }

  // ---------- data ----------
  async function loadField(force) {
    const key = fkey(), [region, layer] = key.split(":");
    const stamp = document.querySelector("#ewStamp");
    try {
      const d = await A().api(`/api/earth/field?region=${region}&layer=${layer}${force ? "&refresh=1" : ""}`);
      if (d.u) { fields[key] = d; if (stamp && fkey() === key) stamp.textContent = `${d.source} · ${d.time ? d.time.replace("T", " ") + " UTC" : ""}${d.pending ? " · updating" : ""}`; const m = document.querySelector("#ewMethod"); if (m) m.textContent = d.method; drawBase(); }
      else if (stamp && fkey() === key) stamp.textContent = d.pending ? "Fetching the live field from Open-Meteo…" : "Field unavailable: " + (d.error || "provider did not respond");
      if (d.pending && alive) timers.push(setTimeout(() => fkey() === key && loadField(false), 3500));
    } catch (e) { if (stamp) stamp.textContent = "Field unavailable: " + e.message; }
  }
  async function loadHazards(force) {
    try {
      hazards = await A().api("/api/earth/hazards" + (force ? "?refresh=1" : ""));
      list(); pins();
      if (hazards.pending && alive) timers.push(setTimeout(() => loadHazards(false), 4000));
    } catch (e) { hazards = { error: e.message }; list(); }
  }
  async function loadClimate(force) {
    try {
      climate = await A().api("/api/earth/climate" + (force ? "?refresh=1" : ""));
      const el = document.querySelector("#ewClimate"); if (el) el.innerHTML = climateHTML(climate);
      if (climate.pending && alive) timers.push(setTimeout(() => loadClimate(false), 4000));
    } catch (e) { const el = document.querySelector("#ewClimate"); if (el) el.innerHTML = `<p class="fine">${esc(e.message)}</p>`; }
  }
  async function statics() {
    if (!coast) try { coast = await (await fetch("/coastlines.json")).json(); } catch (_) {}
    if (!india) try {
      const g = await (await fetch("/data/india_outline_soi.geojson")).json();
      india = g.features.flatMap((f) => (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates));
    } catch (_) {}
  }
  function resize() {
    const host = document.querySelector(".ewMap"); if (!host) return;
    const w = host.clientWidth, h = host.clientHeight, dpr = Math.min(2, devicePixelRatio || 1);
    view = { w, h, dpr };
    for (const c of [base, trail]) { c.width = w * dpr; c.height = h * dpr; c.style.width = w + "px"; c.style.height = h + "px"; }
    drawBase(); seed(Math.round((w * h) / (st.region === "india" ? 260 : 330))); pins();
  }
  function restart() {
    cancelAnimationFrame(raf);
    syncWindy();
    if (useWindy()) return;
    trail.getContext("2d").clearRect(0, 0, trail.width, trail.height);
    resize();
    if (!fields[fkey()]) loadField(false);
    if (REDUCED) { for (let i = 0; i < 60; i++) step(); } else raf = requestAnimationFrame(step);
  }
  async function mount() {
    base = document.querySelector("#ewBase"); trail = document.querySelector("#ewTrail"); if (!base) return;
    alive = true;
    await statics();
    if (!alive) return;
    restart();
    loadHazards(false); loadClimate(false);
    window.addEventListener("resize", onResize);
  }
  let rz; function onResize() { clearTimeout(rz); rz = setTimeout(() => alive && restart(), 150); }
  function destroy() {
    alive = false; cancelAnimationFrame(raf); timers.forEach(clearTimeout); timers = []; window.removeEventListener("resize", onResize);
  }
  function onClick(ev) {
    const b = ev.target.closest("[data-ewmode],[data-ewregion],[data-ewindia],[data-ewpin],[data-ewkind],#ewRefresh");
    if (!b) return false;
    if (b.dataset.ewmode) { st.mode = b.dataset.ewmode; document.querySelectorAll("[data-ewmode]").forEach((x) => x.classList.toggle("active", x === b)); restart(); }
    else if (b.dataset.ewregion) { st.region = b.dataset.ewregion; document.querySelectorAll("[data-ewregion]").forEach((x) => x.classList.toggle("active", x === b)); document.querySelector("#ewTip").hidden = true; restart(); }
    else if (b.dataset.ewindia) { st.india = b.dataset.ewindia; restart(); }
    else if (b.dataset.ewpin) { if (useWindy()) { st.india = "atlas"; restart(); } showEvent(b.dataset.ewpin); }
    else if (b.dataset.ewkind) { const k = b.dataset.ewkind; st.kinds.has(k) ? st.kinds.delete(k) : st.kinds.add(k); list(); pins(); }
    else if (b.id === "ewRefresh") { loadField(true); loadHazards(true); loadClimate(true); A().tip("Requested fresh data from Open-Meteo, GDACS, NASA, USGS and Copernicus."); }
    return true;
  }
  function onChange(e) {
    if (e.target.id !== "ewIndiaOnly") return false;
    st.indiaOnly = e.target.checked; list(); pins(); return true;
  }
  function preset(region, mode) { st.region = region; st.mode = mode; }
  return { layout, mount, destroy, onClick, onChange, preset };
})();
