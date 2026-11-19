"use strict";
/* Sanjaya v6.3 · Elections. Results first: the parliament chart, an India map inside the
   Survey of India boundary, an equal-area hex map, and the tables behind them.
   Sanjaya presents results; it never calls a winner. */
window.ATLASElections = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const KEY = "atlas.elections.v1";
  const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } })();
  const S = {
    country: saved.country || "india", level: saved.level || "state", state: saved.state || "Uttar_Pradesh",
    id: saved.id || "", mapMode: saved.mapMode || "geo", colorBy: saved.colorBy || "party", group: saved.group || "alliance",
    cat: null, res: null, geo: {}, outline: null, states: null, coalition: new Set(), seat: null,
    loading: false, error: "", timer: 0, seq: 0,
  };
  const remember = () => { try { localStorage.setItem(KEY, JSON.stringify({ country: S.country, level: S.level, state: S.state, id: S.id, mapMode: S.mapMode, colorBy: S.colorBy, group: S.group })); } catch (e) { /* storage off */ } };
  const $ = (s) => document.querySelector(s);
  const fmtInt = (n) => (n == null ? "–" : Number(n).toLocaleString("en-IN"));
  const pct = (n, d = 1) => (n == null ? "–" : `${Number(n).toFixed(d)}%`);
  const signed = (n, d = 0, unit = "") => (n == null ? "" : `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n).toFixed(d)}${unit}`);
  const stateLabel = (k) => String(k || "").replace(/_/g, " ").replace(/ &/g, " and");

  // ---------------------------------------------------------------- shell
  function layout() {
    return `<div class="elPage"><div class="heroTitle"><div><h1>Elections</h1><p>Results as declared, drawn so the shape of a mandate is visible: who won, by how much, and how seats compare with votes.</p></div></div>
      <nav class="elCountries" aria-label="Country">${[["india", "India"], ["us", "United States"], ["israel", "Israel"]].map(([k, n]) => `<button class="choice ${S.country === k ? "active" : ""}" data-el-country="${k}" aria-pressed="${S.country === k}">${n}</button>`).join("")}</nav>
      <div id="elBody"></div></div>`;
  }
  async function mount() {
    draw();
    await loadCatalog();
    if (S.country === "india") choose();
  }
  function destroy() { clearTimeout(S.timer); hideTip(); }

  async function loadCatalog() {
    try { S.cat = await A().api("/api/elections/catalog"); S.error = ""; }
    catch (e) { S.error = `The elections index could not be read: ${e.message}`; }
    draw();
    const job = S.cat?.pack?.job;
    if (job && job.state === "running") { clearTimeout(S.timer); S.timer = setTimeout(loadCatalog, 1500); }
    else if (job && job.state === "done" && S.waitingForPack) { S.waitingForPack = false; choose(); }
  }

  // Pick a sensible election for the current level, then load it.
  function choose() {
    const c = S.cat; if (!c) return;
    let id = S.id;
    const known = (x) => x && ((c.national || []).some((e) => e.id === x) || (c.states || []).some((s) => s.elections.some((e) => e.id === x)) || (c.municipal || []).some((m) => m.id === x));
    const fits = (x) => x && ((S.level === "national" && x.startsWith("GE-")) || (S.level === "state" && x.startsWith(`AE-${S.state}-`)) || (S.level === "municipal" && x.startsWith("MC-")));
    if (!known(id) || !fits(id)) {
      if (S.level === "national") id = c.national?.[0]?.id;
      else if (S.level === "state") id = (c.states || []).find((s) => s.state === S.state)?.elections?.[0]?.id || c.states?.[0]?.elections?.[0]?.id;
      else id = c.municipal?.[0]?.id;
    }
    if (id) load(id); else { S.res = null; draw(); }
  }

  async function load(id) {
    S.id = id; S.seat = null; S.coalition = new Set(); remember();
    const seq = ++S.seq;
    S.loading = true; S.error = ""; draw();
    try {
      const r = await A().api(`/api/elections/result?id=${encodeURIComponent(id)}`);
      if (seq !== S.seq) return;
      S.res = r;
      if (r.kind === "AE") S.state = r.state;
      if (r.map?.available) await loadGeo(r);
    } catch (e) { if (seq === S.seq) { S.error = e.message; S.res = null; } }
    if (seq !== S.seq) return;
    S.loading = false; draw();
  }
  async function loadGeo(r) {
    const key = r.map.layer === "pc" ? "pc" : `ac:${r.map.state}`;
    if (!S.geo[key]) S.geo[key] = await A().api(r.map.layer === "pc" ? "/api/elections/geo?layer=pc" : `/api/elections/geo?layer=ac&state=${encodeURIComponent(r.map.state)}`);
    try {
      if (!S.outline) S.outline = (await (await fetch("/data/india_outline_soi.geojson")).json()).features[0].geometry;
      if (!S.states) S.states = await (await fetch("/data/india_states_soi.geojson")).json();
    } catch (e) { /* the map still draws; the boundary note says what is missing */ }
  }

  // ---------------------------------------------------------------- page body
  function draw() {
    const body = $("#elBody"); if (!body) return;
    document.querySelectorAll("[data-el-country]").forEach((b) => { const on = b.dataset.elCountry === S.country; b.classList.toggle("active", on); b.setAttribute("aria-pressed", on); });
    if (S.country !== "india") { body.innerHTML = planned(S.country); return; }
    const c = S.cat;
    body.innerHTML = `${blackoutBanner()}<div class="elLevels filterTabs" role="tablist" aria-label="Level">${[["national", "Lok Sabha"], ["state", "State assemblies"], ["municipal", "Municipal corporations"]].map(([k, n]) => `<button class="choice ${S.level === k ? "active" : ""}" data-el-level="${k}" role="tab" aria-selected="${S.level === k}">${n}</button>`).join("")}</div>
      ${!c ? `<div class="pageLoading">${S.error ? esc(S.error) : "Loading the elections index…"}</div>` : picker()}
      ${needsPack() ? packCard() : S.loading && !S.res ? `<div class="pageLoading">Loading results…</div>` : S.error ? `<div class="panel elNote">${esc(S.error)}</div>` : S.res ? view() : ""}`;
    if (S.res && !needsPack()) wire();
  }
  const needsPack = () => S.level !== "municipal" && S.cat && !S.cat.pack?.ready;

  function blackoutBanner() {
    const w = S.cat?.blackout || [];
    if (!w.length) return "";
    return `<div class="panel elBlackout" role="status"><b>Election Commission blackout in effect.</b> ${w.map((x) => `${esc(stateLabel(x.state))}: ${esc(x.hides.join(" and "))} hidden until ${esc(new Date(x.end).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }))}`).join("; ")}. <span class="fine">Representation of the People Act 1951, sections 126 and 126A.</span></div>`;
  }

  function picker() {
    const c = S.cat;
    if (S.level === "national") {
      const list = c.national || [];
      return list.length ? `<div class="elPicker">${list.map((e) => chip(e.id, String(e.year))).join("")}</div>` : "";
    }
    if (S.level === "state") {
      const st = (c.states || []).find((s) => s.state === S.state) || c.states?.[0];
      if (!st) return "";
      return `<div class="elPicker"><label class="elSelect"><span>State</span><select id="elState">${c.states.map((s) => `<option value="${esc(s.state)}" ${s.state === st.state ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select></label>${st.elections.map((e) => chip(e.id, String(e.year))).join("")}</div>`;
    }
    return `<div class="elPicker">${(c.municipal || []).map((m) => chip(m.id, m.city, m.short)).join("")}</div>`;
  }
  const chip = (id, text, sub) => `<button class="choice ${S.id === id ? "active" : ""}" data-el-id="${esc(id)}" aria-pressed="${S.id === id}">${esc(text)}${sub ? ` <small>${esc(sub)}</small>` : ""}</button>`;

  function packCard() {
    const p = S.cat.pack || {}, j = p.job || {};
    const running = j.state === "running";
    const bar = running && j.total ? `<div class="elProgress" role="progressbar" aria-valuemin="0" aria-valuemax="${j.total}" aria-valuenow="${j.done}"><i style="width:${Math.round((100 * j.done) / j.total)}%"></i></div><p class="fine">${esc(j.step || "")}</p>` : "";
    return `<div class="panel elPack"><h2>Download the election data</h2>
      <p>Results for the Lok Sabha and every state assembly since 2008, with constituency maps. About ${esc(p.download_mb || 36)} MB, downloaded once and kept on this computer, like the language model. Municipal corporations work without it.</p>
      ${bar}${j.state === "failed" ? `<p class="elError">${esc(j.error)}</p>` : ""}
      <button class="action primary" id="elDownload" ${running ? "disabled" : ""}>${running ? "Downloading…" : j.state === "failed" ? "Try again" : "Download election data"}</button>
      <details class="elSources"><summary>Sources and licences</summary><ul>${(p.sources || []).map((s) => `<li>${esc(s.what)}: ${esc(s.licence)}</li>`).join("")}</ul><p class="fine">The India boundary comes from the Survey of India and is already part of Sanjaya.</p></details></div>`;
  }

  function planned(k) {
    const t = k === "us"
      ? ["United States", "House of Representatives (435), Senate (100, a third up each cycle) and governors, with each seat shaded by margin and the Senate seats not up shown faded."]
      : ["Israel", "The 120-seat Knesset, elected from one nationwide list: vote share by party, the 3.25% threshold and the votes it discards, and a coalition builder to test 61-seat majorities."];
    return `<div class="panel elPlanned"><h2>${t[0]}</h2><p>${esc(t[1])}</p><p class="fine">This sub-panel comes after the Indian elections work, which is being built first for the 2027 state elections.</p></div>`;
  }

  // ---------------------------------------------------------------- one election
  function groups(r) {
    const byCode = new Map(r.parties.map((p) => [p.code, p]));
    const out = [], used = new Set();
    if (S.group === "alliance" && r.alliances?.length) {
      for (const a of r.alliances) {
        const members = a.parties.map((c) => byCode.get(c)).filter((p) => p && p.seats > 0).sort((x, y) => y.seats - x.seats);
        members.forEach((p) => used.add(p.code));
        if (members.length) out.push({ label: a.name, color: a.color, seats: a.seats, share: a.share, members });
      }
    }
    const rest = r.parties.filter((p) => p.seats > 0 && !used.has(p.code));
    const ind = rest.filter((p) => p.code === "IND");
    for (const p of rest.filter((p) => p.code !== "IND")) out.push({ label: p.name, color: p.color, seats: p.seats, share: p.share, members: [p] });
    for (const p of ind) out.push({ label: p.name, color: p.color, seats: p.seats, share: p.share, members: [p] });
    return out;
  }

  function view() {
    const r = S.res, muni = r.kind === "MC";
    const when = muni ? new Date(r.counted || r.polled).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) : String(r.year);
    const stats = [[fmtInt(r.seats_total), "seats"], [fmtInt(r.majority), "for a majority"]];
    if (r.turnout != null) stats.push([pct(r.turnout), muni ? "turnout" : "turnout (approx.)"]);
    if (!muni && r.flips?.length) stats.push([fmtInt(r.flips.length), `seats changed hands since ${r.previous?.year}`]);
    return `<section class="elHead"><div><h2>${esc(r.label)}</h2><p class="fine">${esc(when)}${r.previous ? ` · compared with ${esc(r.previous.label)}` : ""}${muni && r.authority ? ` · ${esc(r.authority)}` : ""}</p></div>
        <div class="elStats">${stats.map(([v, l]) => `<div><b>${v}</b><span>${esc(l)}</span></div>`).join("")}</div></section>
      ${r.status ? `<div class="panel elNote">${esc(r.status)}</div>` : ""}
      <div class="elTop"><div class="panel elChamber"><div class="elPanelBar"><h3>Seats</h3>${r.alliances?.length ? `<div class="filterTabs elMini">${[["alliance", "Alliances"], ["party", "Parties"]].map(([k, n]) => `<button class="choice ${S.group === k ? "active" : ""}" data-el-group="${k}">${n}</button>`).join("")}</div>` : ""}</div>
          <div id="elHemi">${hemicycle(r)}</div><div id="elCoalition" class="elCoalition" aria-live="polite">${coalitionLine()}</div></div>
        <div class="panel elBlocs"><h3>${r.alliances?.length && S.group === "alliance" ? "Alliances and parties" : "Parties"}</h3>${blocList(r)}<p class="fine">Click parties to test a coalition against the majority line.</p></div></div>
      ${muni ? municipalNotes(r) : `${mapPanel(r)}${tables(r)}`}
      <p class="fine elAttr">${esc(r.attribution || "")}${r.alliance_source ? ` Alliances: ${esc(r.alliance_source)}.` : ""}</p>
      <div class="panel elNext"><h3>Polls and projections</h3><p class="fine">Opinion polls, exit polls with each pollster's past record, and Sanjaya's projection ranges come next, before the 2027 round. Each will be hidden automatically during the Election Commission's blackout windows.</p></div>`;
  }

  function blocList(r) {
    let gs = groups(r);
    // Parties on their own with under 1% of seats and under 3% of the vote fold into one row, so big chambers stay readable.
    const small = gs.filter((g) => g.members.length === 1 && g.seats < Math.max(2, r.seats_total * 0.01) && (g.share == null || g.share < 3));
    if (small.length > 1) {
      const members = small.flatMap((g) => g.members);
      gs = gs.filter((g) => !small.includes(g));
      gs.push({ label: `Other parties and independents (${members.length})`, color: "rgba(190,228,240,.35)", seats: small.reduce((a, g) => a + g.seats, 0), share: small.every((g) => g.share == null) ? null : small.reduce((a, g) => a + (g.share || 0), 0), members });
    }
    const total = r.seats_total;
    return `<ul class="elBlocList">${gs.map((g) => `<li><div class="elBlocRow"><span class="elSw" style="background:${esc(g.color)}"></span><b>${esc(g.label)}</b><span class="num">${g.seats}</span>${g.share != null ? `<span class="num elShare">${pct(g.share)}</span>` : ""}</div>
      <div class="elBar"><i style="width:${(100 * g.seats) / total}%;background:${esc(g.color)}"></i>${g.share != null ? `<em style="left:${Math.min(100, g.share)}%" title="Vote share ${pct(g.share)}"></em>` : ""}</div>
      <div class="elChips">${g.members.map((p) => partyChip(p)).join("")}</div></li>`).join("")}</ul>
      ${r.parties.some((p) => p.share != null) ? `<p class="fine">Bar: share of seats. Tick: share of the vote.</p>` : ""}`;
  }
  const partyChip = (p) => `<button class="elParty ${S.coalition.has(p.code) ? "on" : ""}" data-el-party="${esc(p.code)}" aria-pressed="${S.coalition.has(p.code)}" title="${esc(p.name)}"><span class="elSw" style="background:${esc(p.color)}"></span>${esc(p.code)} <span class="num">${p.seats}</span></button>`;

  function coalitionLine() {
    const r = S.res; if (!r) return "";
    if (!S.coalition.size) return `<span class="fine">No coalition selected.</span>`;
    const seats = r.parties.filter((p) => S.coalition.has(p.code)).reduce((a, p) => a + p.seats, 0);
    const ok = seats >= r.majority;
    return `<b>${[...S.coalition].join(" + ")}</b>: ${seats} seats. ${ok ? `Crosses the majority of ${r.majority} by ${seats - r.majority + 1 > 0 ? seats - r.majority : 0}.` : `Short of ${r.majority} by ${r.majority - seats}.`} <button class="linkButton" data-el-clear>Clear</button>`;
  }

  // ---------------------------------------------------------------- parliament chart
  function hemicycle(r) {
    const gs = groups(r), N = r.seats_total;
    const W = 640, H = 360, cx = W / 2, cy = 318, R1 = 270, R0 = 110;
    const rows = Math.max(2, Math.round(Math.sqrt(0.273 * N)));
    const radii = Array.from({ length: rows }, (_, i) => R0 + ((R1 - R0) * (i + 0.5)) / rows);
    const sum = radii.reduce((a, b) => a + b, 0);
    const counts = radii.map((rr) => Math.round((N * rr) / sum));
    counts[rows - 1] += N - counts.reduce((a, b) => a + b, 0);
    const pts = [];
    radii.forEach((rr, i) => { const k = counts[i]; for (let j = 0; j < k; j++) { const a = Math.PI * (1 - (j + 0.5) / k); pts.push({ a, x: cx + rr * Math.cos(a), y: cy - rr * Math.sin(a) }); } });
    pts.sort((p, q) => q.a - p.a);
    const spacing = Math.min((Math.PI * sum) / N, (R1 - R0) / rows);
    const dot = Math.max(1.6, spacing * 0.42);
    const order = [];
    for (const g of gs) for (const p of g.members) for (let i = 0; i < p.seats; i++) order.push(p);
    const sel = S.coalition.size > 0;
    let dots = "";
    pts.forEach((pt, i) => {
      const p = order[i]; if (!p) return;
      const dim = sel && !S.coalition.has(p.code);
      dots += `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="${dot.toFixed(2)}" fill="${p.color}" ${dim ? 'opacity=".22"' : ""} data-el-tip="${esc(p.name)} · ${p.seats}"/>`;
    });
    // Seat-share arc outside, vote-share arc inside.
    const arc = (rad, a0, a1, color, w) => { const x0 = cx + rad * Math.cos(a0), y0 = cy - rad * Math.sin(a0), x1 = cx + rad * Math.cos(a1), y1 = cy - rad * Math.sin(a1); return `<path d="M${x0.toFixed(1)} ${y0.toFixed(1)}A${rad} ${rad} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}" fill="none" stroke="${color}" stroke-width="${w}"/>`; };
    let outer = "", inner = "", a = Math.PI;
    for (const g of gs) { const s = (g.seats / N) * Math.PI; outer += arc(R1 + 14, a, a - s, g.color, 5); a -= s; }
    const hasVotes = gs.some((g) => g.share != null);
    if (hasVotes) {
      a = Math.PI;
      for (const g of gs) { const s = ((g.share || 0) / 100) * Math.PI; inner += arc(R0 - 16, a, a - s, g.color, 5); a -= s; }
      if (a > 0.002) inner += arc(R0 - 16, a, 0, "rgba(190,228,240,.18)", 5);
    }
    const maj = `<line x1="${cx}" y1="${cy - R0 + 22}" x2="${cx}" y2="${cy - R1 - 24}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="3 3" opacity=".7"/><text x="${cx}" y="${cy - R1 - 30}" text-anchor="middle" class="elSvgLabel">Majority ${r.majority}</text>`;
    const legend = hasVotes ? `<text x="${cx}" y="${cy + 30}" text-anchor="middle" class="elSvgFine">Outer arc: seats · inner arc: votes${r.nota_votes ? " (grey: other parties, independents and NOTA)" : ""}</text>` : `<text x="${cx}" y="${cy + 30}" text-anchor="middle" class="elSvgFine">Outer arc: share of seats</text>`;
    return `<svg viewBox="0 0 ${W} ${H + 10}" role="img" aria-label="Parliament chart: ${N} seats, majority ${r.majority}"><title>${esc(r.label)}</title>${outer}${inner}${dots}${maj}${legend}</svg>`;
  }

  // ---------------------------------------------------------------- maps
  function mapPanel(r) {
    const m = r.map || {};
    const geoKey = m.layer === "pc" ? "pc" : `ac:${m.state}`;
    const g = S.geo[geoKey];
    const controls = `<div class="elMapBar"><div class="filterTabs elMini">${[["geo", "Map"], ["hex", "Equal-area hexes"]].map(([k, n]) => `<button class="choice ${S.mapMode === k ? "active" : ""}" data-el-mapmode="${k}" ${!m.available ? "disabled" : ""}>${n}</button>`).join("")}</div>
      <div class="filterTabs elMini">${[["party", "Winning party"], ["margin", "Margin"], ["flips", "Changed hands"]].map(([k, n]) => `<button class="choice ${S.colorBy === k ? "active" : ""}" data-el-color="${k}" ${!m.available || (k === "flips" && !r.previous) ? "disabled" : ""}>${n}</button>`).join("")}</div></div>`;
    let drawing = `<div class="empty"><b>No map for this election</b><span>${esc(m.note || "")}</span></div>`;
    if (m.available && g) drawing = S.mapMode === "hex" ? hexMap(r, g) : geoMap(r, g);
    return `<div class="elMapRow"><div class="panel elMap"><div class="elPanelBar"><h3>${r.kind === "GE" ? "Lok Sabha constituencies" : "Assembly constituencies"}</h3>${controls}</div>
      <div class="elMapFrame" id="elMapFrame">${drawing}</div>${m.available ? mapLegend(r) : ""}<p class="fine">${esc(m.note || "")}${S.mapMode === "hex" && m.available ? " Each hexagon is one seat, placed near its real location, so dense cities count as much as large rural seats." : ""}</p></div>
      <aside class="panel elSeat" id="elSeat">${seatCard()}</aside></div>`;
  }

  function mapLegend(r) {
    if (S.colorBy === "margin") return `<p class="elLegend"><span class="elRamp"></span> Darker: closer contest. Full colour: won by 20 points or more.</p>`;
    if (S.colorBy === "flips") return `<p class="elLegend">Coloured: seats that changed hands since ${esc(String(r.previous?.year || ""))}, in the new winner's colour. Grey: held.</p>`;
    return "";
  }
  const seatKey = (r, s) => (r.kind === "GE" ? `${s.state}|${s.no}` : String(s.no));
  // Seats not on the map get a key no map shape can have, so they never colour a wrong shape.
  const keyOf = (r, s) => s.geo || `x:${seatKey(r, s)}`;
  function seatIndex(r) {
    if (r._idx) return r._idx;
    const m = new Map(r.seats.map((s) => [keyOf(r, s), s]));
    const flips = new Map((r.flips || []).map((f) => [f[4] || `x:${r.kind === "GE" ? `${f[0]}|${f[1]}` : f[1]}`, f]));
    const colors = new Map(r.parties.map((p) => [p.code, p.color]));
    Object.defineProperty(r, "_idx", { value: { m, flips, colors }, enumerable: false });
    return r._idx;
  }
  function fillFor(r, s) {
    const { flips, colors } = seatIndex(r);
    if (!s) return "rgba(190,228,240,.06)";
    const c = colors.get(s.party) || "#8c969b";
    if (S.colorBy === "flips") return flips.has(keyOf(r, s)) ? c : "rgba(190,228,240,.10)";
    if (S.colorBy === "margin") {
      const m = s.margin_pct == null ? 20 : s.margin_pct;   // close seats pale, safe seats full
      const o = Math.max(0.18, Math.min(1, m / 20));
      return `color-mix(in srgb, ${c} ${Math.round(o * 100)}%, rgba(4,14,21,.9))`;
    }
    return c;
  }

  function projector(items, W, H, lat0) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    const k = Math.cos((lat0 * Math.PI) / 180);
    for (const it of items) for (const ring of it.rings) for (let i = 0; i < ring.length; i += 2) {
      const x = ring[i] * k, y = ring[i + 1];
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    const s = Math.min((W - 20) / (x1 - x0 || 1), (H - 20) / (y1 - y0 || 1));
    const ox = (W - s * (x1 - x0)) / 2, oy = (H - s * (y1 - y0)) / 2;
    return { f: (lon, lat) => [ox + (lon * k - x0) * s, oy + (y1 - lat) * s], h: Math.ceil(s * (y1 - y0) + 2 * oy) };
  }
  const ringPath = (ring, f) => { let d = ""; for (let i = 0; i < ring.length; i += 2) { const [x, y] = f(ring[i], ring[i + 1]); d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); } return d + "Z"; };
  const geomPath = (geom, f) => { if (!geom) return ""; const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.type === "MultiPolygon" ? geom.coordinates : []; let d = ""; for (const poly of polys) for (const ring of poly) d += ringPath(ring.flat(), f); return d; };

  function geoMap(r, g) {
    const W = 760, H = r.kind === "GE" ? 820 : 620;
    const lat0 = g.lat0 || 22;
    const { f, h } = projector(r.kind === "GE" && S.outline ? [{ rings: (S.outline.type === "Polygon" ? [S.outline.coordinates] : S.outline.coordinates).flat().map((ring) => ring.flat()) }] : g.items, W, H, lat0);
    const { m } = seatIndex(r);
    let paths = "";
    for (const it of g.items) {
      const key = r.kind === "GE" ? `${it.state}|${it.no}` : String(it.no);
      const s = m.get(key);
      const d = it.rings.map((ring) => ringPath(ring, f)).join("");
      paths += `<path d="${d}" fill="${fillFor(r, s)}" data-el-seat="${esc(key)}" class="elSeatShape${S.seat === key ? " sel" : ""}"/>`;
    }
    // Official boundary on top: India outline for the Lok Sabha, the state for an assembly.
    let boundary = "";
    if (r.kind === "GE" && S.outline) boundary = `<path d="${geomPath(S.outline, f)}" class="elBoundary"/>`;
    else if (S.states) {
      const st = S.states.features.find((x) => x.properties.name === stateLabel(r.state));
      if (st) boundary = `<path d="${geomPath(st.geometry, f)}" class="elBoundary"/>`;
    }
    return `<svg viewBox="0 0 ${W} ${Math.min(H, h)}" class="elGeo" role="img" aria-label="Map of ${esc(r.label)} by winning party">${paths}${boundary}</svg>`;
  }

  function hexMap(r, g) {
    const { m } = seatIndex(r);
    const cells = Object.entries(g.hex || {});
    if (!cells.length) return `<div class="empty"><b>No hex layout</b></div>`;
    let maxC = 0, maxR = 0;
    for (const [, [c, rr]] of cells) { if (c > maxC) maxC = c; if (rr > maxR) maxR = rr; }
    const W = 760, side = Math.min(W / ((maxC + 1.5) * Math.sqrt(3)), 640 / ((maxR + 1.5) * 1.5));
    const hw = Math.sqrt(3) * side, H = (maxR + 1.5) * 1.5 * side + side;
    const hex = (x, y) => { let d = ""; for (let i = 0; i < 6; i++) { const a = (Math.PI / 180) * (60 * i - 30); d += (i ? "L" : "M") + (x + side * 0.94 * Math.cos(a)).toFixed(1) + " " + (y + side * 0.94 * Math.sin(a)).toFixed(1); } return d + "Z"; };
    let out = "";
    for (const [key, [c, rr]] of cells) {
      const x = hw * (c + 0.5 + (rr % 2 ? 0.5 : 0)), y = side + rr * 1.5 * side;
      const s = m.get(key);
      out += `<path d="${hex(x, y)}" fill="${fillFor(r, s)}" data-el-seat="${esc(key)}" class="elSeatShape${S.seat === key ? " sel" : ""}"/>`;
    }
    return `<svg viewBox="0 0 ${Math.ceil(hw * (maxC + 2))} ${Math.ceil(H)}" class="elGeo" role="img" aria-label="Hex map of ${esc(r.label)}: one hexagon per seat">${out}</svg>`;
  }

  function seatCard() {
    const r = S.res; if (!r) return "";
    const { m, flips, colors } = seatIndex(r);
    const s = S.seat && m.get(S.seat);
    if (!s) {
      return `<h3>Seat details</h3><p class="fine">Hover or select a constituency on the map.</p>
        ${r.kind === "GE" ? "" : ""}<h4>Closest contests</h4><ol class="elClosest">${(r.closest || []).slice(0, 8).map((c) => `<li><button class="linkButton" data-el-pick="${esc(keyOf(r, c))}">${esc(c.name)}</button> <span class="fine">${esc(c.party)} over ${esc(c.runner_party)} by ${fmtInt(c.margin)}</span></li>`).join("")}</ol>`;
    }
    const f = flips.get(keyOf(r, s));
    return `<h3>${esc(s.name)}${s.type && s.type !== "GEN" ? ` <small>(${esc(s.type)})</small>` : ""}</h3><p class="fine">${r.kind === "GE" ? esc(stateLabel(s.state)) + " · " : ""}No. ${s.no}</p>
      ${s.unopposed ? `<p>Won unopposed by <b>${esc(s.party)}</b>; no poll was held.</p>` : `<div class="elDuel"><div><span class="elSw" style="background:${esc(colors.get(s.party) || "#8c969b")}"></span><b>${esc(s.winner)}</b><span>${esc(s.party)} · ${fmtInt(s.votes)} votes${s.share != null ? ` · ${pct(s.share)}` : ""}</span></div>
      <div><span class="elSw" style="background:${esc(colors.get(s.runner_party) || "#8c969b")}"></span><b>${esc(s.runner || "–")}</b><span>${esc(s.runner_party || "")}${s.runner ? " · runner-up" : ""}</span></div></div>
      <p>Margin <b>${fmtInt(s.margin)}</b> votes${s.margin_pct != null ? ` (${pct(s.margin_pct, 2)})` : ""}. Turnout ${pct(s.turnout)}.</p>`}
      ${f ? `<p class="fine">Changed hands: ${esc(f[2])} won it in ${r.previous.year}.</p>` : ""}<button class="linkButton" data-el-pick="">Back to closest contests</button>`;
  }

  // ---------------------------------------------------------------- tables
  function tables(r) {
    const prev = r.previous;
    const rows = r.parties.filter((p) => p.seats > 0 || p.share >= 1);
    const flipCount = {};
    const same = { ADAL: "ADS", ADS: "ADAL", AAP: "AAAP", AAAP: "AAP", AIADMK: "ADMK", ADMK: "AIADMK", TRS: "BRS", BRS: "TRS", JKNC: "JKN", JKN: "JKNC", NPP: "NPEP", NPEP: "NPP" };
    const now = new Set(r.parties.map((p) => p.code));
    const shown = (c) => (now.has(c) ? c : now.has(same[c]) ? same[c] : c);
    for (const f of r.flips || []) { const k = `${shown(f[2])} → ${f[3]}`; flipCount[k] = (flipCount[k] || 0) + 1; }
    const topFlips = Object.entries(flipCount).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return `<div class="elTables"><div class="panel"><h3>Parties</h3><div class="tableWrap"><table class="elTable"><thead><tr><th>Party</th><th class="num">Seats</th>${prev ? `<th class="num">vs ${prev.year}</th>` : ""}<th class="num">Vote share</th>${prev ? `<th class="num">vs ${prev.year}</th>` : ""}<th class="num">Contested</th></tr></thead>
      <tbody>${rows.map((p) => `<tr><td><span class="elSw" style="background:${esc(p.color)}"></span>${esc(p.name)} <small>${esc(p.code)}</small></td><td class="num">${p.seats}</td>${prev ? `<td class="num ${p.seat_change > 0 ? "up" : p.seat_change < 0 ? "down" : ""}">${signed(p.seat_change)}</td>` : ""}<td class="num">${pct(p.share)}</td>${prev ? `<td class="num">${p.share_change == null ? "new" : signed(p.share_change, 1, " pts")}</td>` : ""}<td class="num">${fmtInt(p.contested)}</td></tr>`).join("")}</tbody></table></div>
      <p class="fine">Vote share is of valid votes, including NOTA (${fmtInt(r.nota_votes)} votes). Parties under 1% with no seats are left out.</p></div>
      ${topFlips.length ? `<div class="panel"><h3>Seats that changed hands since ${prev.year}</h3><ul class="elFlips">${topFlips.map(([k, n]) => `<li><span>${esc(k)}</span><b class="num">${n}</b></li>`).join("")}</ul><p class="fine">Only constituencies whose name and number match across both elections are compared.</p></div>` : ""}</div>`;
  }

  function municipalNotes(r) {
    return `<div class="elTables"><div class="panel"><h3>Seats by party</h3><table class="elTable"><thead><tr><th>Party</th><th class="num">Seats</th><th class="num">Share of seats</th></tr></thead><tbody>${r.parties.map((p) => `<tr><td><span class="elSw" style="background:${esc(p.color)}"></span>${esc(p.name)} <small>${esc(p.code)}</small></td><td class="num">${p.seats}</td><td class="num">${pct((100 * p.seats) / r.seats_total)}</td></tr>`).join("")}</tbody></table>
      <p class="fine">State Election Commissions publish ward results separately; vote shares are not shown here.</p></div>
      <div class="panel"><h3>Notes and sources</h3>${r.note ? `<p>${esc(r.note)}</p>` : ""}${r.previous_note ? `<p><b>${r.previous_year}:</b> ${esc(r.previous_note)}</p>` : ""}<p class="fine">${esc(r.map?.note || "")}</p><ul class="elSourcesList">${(r.sources || []).map((u) => { let host = u; try { host = new URL(u).hostname.replace(/^www\./, ""); } catch (e) {} return `<li><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(host)} ↗</a></li>`; }).join("")}</ul></div></div>`;
  }

  // ---------------------------------------------------------------- tooltip + events
  let tip = null;
  function showTip(e, html) {
    if (!tip) { tip = document.createElement("div"); tip.className = "elTip"; document.body.appendChild(tip); }
    tip.innerHTML = html; tip.hidden = false;
    const x = Math.min(window.innerWidth - tip.offsetWidth - 12, e.clientX + 14), y = Math.min(window.innerHeight - tip.offsetHeight - 12, e.clientY + 14);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }

  function wire() {
    const frame = $("#elMapFrame");
    if (frame) {
      frame.onmousemove = (e) => {
        const k = e.target.closest?.("[data-el-seat]")?.dataset.elSeat;
        if (!k) return hideTip();
        const r = S.res, s = seatIndex(r).m.get(k);
        if (!s) return showTip(e, "No result for this constituency");
        showTip(e, `<b>${esc(s.name)}</b><br>${esc(s.party)}${s.unopposed ? " · unopposed" : ` · margin ${fmtInt(s.margin)}${s.margin_pct != null ? ` (${pct(s.margin_pct)})` : ""}`}`);
      };
      frame.onmouseleave = hideTip;
    }
    const hemi = $("#elHemi");
    if (hemi) {
      hemi.onmousemove = (e) => { const t = e.target.closest?.("[data-el-tip]")?.dataset.elTip; t ? showTip(e, esc(t)) : hideTip(); };
      hemi.onmouseleave = hideTip;
    }
  }
  function redrawChamber() {
    const h = $("#elHemi"); if (h) h.innerHTML = hemicycle(S.res);
    const c = $("#elCoalition"); if (c) c.innerHTML = coalitionLine();
    document.querySelectorAll("[data-el-party]").forEach((b) => { const on = S.coalition.has(b.dataset.elParty); b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  }

  document.addEventListener("click", (e) => {
    if (!document.querySelector(".elPage")) return;
    const t = e.target.closest("[data-el-country],[data-el-level],[data-el-id],[data-el-group],[data-el-mapmode],[data-el-color],[data-el-party],[data-el-seat],[data-el-pick],[data-el-clear],#elDownload");
    if (!t) return;
    const d = t.dataset;
    if (d.elCountry) { S.country = d.elCountry; remember(); draw(); if (S.country === "india" && !S.res) choose(); }
    else if (d.elLevel) { S.level = d.elLevel; remember(); S.res = null; choose(); draw(); }
    else if (d.elId) load(d.elId);
    else if (d.elGroup) { S.group = d.elGroup; remember(); draw(); }
    else if (d.elMapmode) { S.mapMode = d.elMapmode; remember(); draw(); }
    else if (d.elColor) { S.colorBy = d.elColor; remember(); draw(); }
    else if (d.elParty) { S.coalition.has(d.elParty) ? S.coalition.delete(d.elParty) : S.coalition.add(d.elParty); redrawChamber(); }
    else if ("elClear" in d) { S.coalition.clear(); redrawChamber(); }
    else if (d.elSeat !== undefined || d.elPick !== undefined) {
      S.seat = d.elSeat ?? d.elPick ?? null; if (!S.seat) S.seat = null;
      const card = $("#elSeat"); if (card) card.innerHTML = seatCard();
      document.querySelectorAll(".elSeatShape.sel").forEach((x) => x.classList.remove("sel"));
      if (S.seat) document.querySelectorAll(`[data-el-seat="${CSS.escape(S.seat)}"]`).forEach((x) => x.classList.add("sel"));
    }
    else if (t.id === "elDownload") {
      t.disabled = true; t.textContent = "Starting…"; S.waitingForPack = true;
      A().api("/api/elections/download", "POST", {}).then(loadCatalog).catch((err) => { S.error = err.message; draw(); });
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "elState") { S.state = e.target.value; remember(); choose(); }
  });

  return { layout, mount, destroy };
})();
