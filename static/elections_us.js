"use strict";
/* Sanjaya v6.5 · Elections, United States: House, Senate, governors and president.
   Results as recorded; Sanjaya never calls a race. 2026 is read from Wikipedia while counting finishes. */
window.ATLASElectionsUS = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const KEY = "atlas.elections.us.v1";
  const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } })();
  const U = { office: saved.office || "H", cycle: saved.cycle || null, cat: null, res: {}, geo: null, pick: null, scope: saved.scope || "us",
    off: {}, timer: 0, offTimer: 0, error: "", body: null, seq: 0 };
  const remember = () => { try { localStorage.setItem(KEY, JSON.stringify({ office: U.office, cycle: U.cycle, scope: U.scope })); } catch (e) { /* storage off */ } };
  const OFF = { H: "House", S: "Senate", G: "Governors", P: "President" };
  const PN = { D: "Democratic", R: "Republican", I: "Independent", O: "Other", U: "Not yet called" };
  const PC = { D: "#3A78D4", R: "#D5483F", I: "#9575CD", O: "#8A96A3", U: "#4B5560" };
  const STN = { AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming" };
  const $ = (s) => (U.body ? U.body.querySelector(s) : null);
  const key = () => `${U.office}-${U.cycle}`;
  const res = () => U.res[key()];
  const longDate = (d) => { if (!d) return ""; const t = new Date(d); return isNaN(t) ? d : t.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }); };
  const ago = (t) => { if (!t) return ""; const m = Math.round((Date.now() / 1000 - t) / 60); return m < 2 ? "just now" : m < 90 ? `${m} min ago` : `${Math.round(m / 60)} h ago`; };
  const seatName = (s) => (U.office === "H" ? `${STN[s.state] || s.state} ${s.seat === "1" && isAtLarge(s.state) ? "at-large" : s.seat}` : U.office === "S" ? `${STN[s.state] || s.state}${s.special ? " (special)" : ""}` : U.office === "P" && s.seat ? `${STN[s.state]} district ${s.seat}` : STN[s.state] || s.state);
  const isAtLarge = (st) => { const ap = U.geo?.apportionment?.[eraKey()]; return ap ? ap[st] === 1 : false; };
  const eraKey = () => res()?.map?.era || "2020";

  // ---------------------------------------------------------------- lifecycle
  async function mount(body) {
    U.body = body;
    draw();
    if (!U.cat) await loadCatalog(); else if (!res()) load(); else draw();
  }
  function destroy() { clearTimeout(U.timer); clearTimeout(U.offTimer); U.body = null; }

  async function loadCatalog() {
    try { U.cat = await A().api("/api/us/catalog"); U.error = ""; } catch (e) { U.error = `The US elections index could not be read: ${e.message}`; }
    const job = U.cat?.pack?.job;
    if (job && job.state === "running") { clearTimeout(U.timer); U.timer = setTimeout(loadCatalog, 1200); draw(); return; }
    if (U.cat?.pack?.ready) {
      const o = U.cat.offices.find((x) => x.office === U.office) || U.cat.offices[0];
      U.office = o.office;
      if (!o.cycles.includes(Number(U.cycle))) U.cycle = o.cycles[0];
      if (!U.geo) { try { U.geo = await A().api("/api/us/geo"); } catch (e) { /* map optional */ } }
      return load();
    }
    draw();
  }

  async function load(force = false) {
    const k = key(), seq = ++U.seq;
    if (!U.res[k] || force || U.res[k].live?.pending) {
      if (!U.res[k]) draw();
      try {
        const r = await A().api(`/api/us/result?office=${U.office}&cycle=${U.cycle}${force ? "&refresh=1" : ""}`);
        if (seq !== U.seq && k !== key()) return;
        U.res[k] = r;
      } catch (e) { U.error = e.message; }
    }
    remember();
    draw();
    const r = U.res[k];
    clearTimeout(U.timer);
    if (r?.live?.pending) U.timer = setTimeout(() => { if (key() === k) load(false); }, 2500);   // Wikipedia read still running
    loadOfficials();
  }

  // ---------------------------------------------------------------- page
  function draw() {
    const b = U.body; if (!b) return;
    wire();                       // every view, including the download card, needs its click handler
    if (U.error && !U.cat) { b.innerHTML = `<div class="panel elNote">${esc(U.error)}</div>`; return; }
    if (!U.cat) { b.innerHTML = `<div class="pageLoading">Loading the US elections index…</div>`; return; }
    if (!U.cat.pack.ready) { b.innerHTML = packCard(); return; }
    const o = U.cat.offices.find((x) => x.office === U.office);
    const r = res();
    const top = window.scrollY;
    b.innerHTML = `<div class="elUS"><div class="elLevels filterTabs" role="tablist" aria-label="Office">${U.cat.offices.map((x) => `<button class="choice ${x.office === U.office ? "active" : ""}" data-us-office="${x.office}" role="tab" aria-selected="${x.office === U.office}">${esc(OFF[x.office])}</button>`).join("")}</div>
      <div class="elPicker">${o.cycles.map((c) => `<button class="choice ${Number(U.cycle) === c ? "active" : ""}" data-us-cycle="${c}" aria-pressed="${Number(U.cycle) === c}">${c}${o.live.includes(c) ? " <small>counting</small>" : ""}</button>`).join("")}</div>
      ${!r ? `<div class="pageLoading">Loading results…</div>` : view(r)}</div>`;
    window.scrollTo(0, top);
    wire();
  }

  const pctDone = (j) => Math.min(100, Math.round((100 * (j.done || 0)) / (j.total || 1)));
  function packCard() {
    const p = U.cat.pack || {}, j = p.job || {};
    const running = j.state === "running";
    return `<div class="panel elPack"><h2>Download the US results</h2>
      <p>Every House race since 1976 and every Senate, governor and presidential race since the late 1990s, with a map of the states. About ${esc(p.download_mb || 9)} MB, downloaded once and kept on this computer. Results after 2024 are read from Wikipedia when you look.</p>
      ${running ? `<div class="elProgress usProgress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pctDone(j)}" aria-label="Download progress"><i style="width:${Math.max(4, pctDone(j))}%"></i></div>
        <p class="usProgressText"><b>${pctDone(j)}%</b> <span>${esc(j.step || "Working…")}</span> <small>step ${Math.min((j.done || 0) + 1, j.total || 1)} of ${j.total || 1}</small></p>` : ""}
      ${j.state === "failed" ? `<p class="elError">${esc(j.error)}</p>` : ""}
      <button class="action primary" id="usDownload" ${running ? "disabled" : ""}>${running ? "Downloading…" : j.state === "failed" ? "Try again" : "Download US results"}</button>
      <details class="elSources"><summary>Sources and licences</summary><ul>${(p.sources || []).map((s) => `<li>${esc(s.what)}: ${esc(s.licence)}</li>`).join("")}</ul></details></div>`;
  }

  function view(r) {
    const lead = [...r.parties].filter((p) => p.code !== "U").sort((a, b) => b.seats - a.seats);
    const stats = [[r.seats_total, U.office === "P" ? "electoral votes" : U.office === "G" ? "governorships" : "seats"], [r.majority, U.office === "P" ? "to win" : "for a majority"]];
    if (r.up != null && U.office !== "H") stats.push([r.up, U.office === "G" ? "races this round" : "seats up"]);
    if (r.uncalled) stats.push([r.uncalled, "not yet called"]);
    if (r.flips?.length) stats.push([r.flips.length, "changed party"]);
    return `<section class="elHead"><div><h2>${esc(r.label)}</h2><p class="fine">${U.office === "P" ? lead.map((p) => `${esc(p.candidate || PN[p.code])} (${p.code}) ${p.seats}`).join(" · ") : ""}</p></div>
        <div class="elStats">${stats.map(([v, l]) => `<div><b>${v}</b><span>${esc(l)}</span></div>`).join("")}</div></section>
      ${liveLine(r)}
      <div class="elTop"><div class="panel elChamber"><h3>${U.office === "P" ? "Electoral votes" : U.office === "G" ? "Governorships" : "Seats"}</h3>${U.office === "P" ? evBar(r) : chamber(r)}</div>
        <div class="panel elBlocs"><h3>Parties</h3>${partyList(r)}</div></div>
      <div class="panel elMap usMap"><div class="elPanelBar"><h3>${U.office === "H" ? "Districts" : "States"}</h3><span class="fine">${U.office === "H" ? "One tile per district, grouped by state. Tiles don't change when district lines are redrawn." : U.office === "P" ? "Shade shows the margin." : "Faded: not up this year. Shade shows the margin."}</span></div>
        <div class="usMapWrap">${U.office === "H" ? tileMap(r) : stateMap(r)}</div>${legend(r)}
        <div id="usPick">${pickCard(r)}</div></div>
      ${tables(r)}
      <div class="elGov"><section class="panel elOfficials" id="usOfficials" aria-live="polite">${officialsPanel()}</section>
        <section class="panel"><h3>Next election</h3><p class="fine">Forecasts for US races come in a later step. As on the India page, they will run only when you ask.</p></section></div>
      <p class="fine elAttr">${(r.notes || []).map(esc).join(" ")} ${esc(r.attribution || "")}</p>`;
  }

  function liveLine(r) {
    const l = r.live;
    if (!l) return "";
    const btn = `<button class="choice elRefresh" data-us-refresh ${l.pending ? "disabled" : ""}>${l.pending ? "Reading…" : "Read again"}</button>`;
    const msg = l.pending ? `${esc(l.step || `Reading Wikipedia: ${l.page}`)}…` : l.error && !r.seats?.length ? `Wikipedia could not be read (${esc(l.error)}).` :
      `Results as listed on Wikipedia's <a href="https://en.wikipedia.org/wiki/${encodeURIComponent(l.page.replace(/ /g, "_"))}" target="_blank" rel="noopener noreferrer">${esc(l.page)}</a>, read ${esc(ago(l.fetched))}. Counting continues in some states; races Wikipedia does not list as decided are shown as not yet called.`;
    return `<div class="panel elNote usLive" role="status"><span>${msg}</span>${btn}</div>`;
  }

  // ---------------------------------------------------------------- charts
  function order(r) {
    const seats = [];
    const sorted = [...r.parties].sort((a, b) => "DIOUR".indexOf(a.code) - "DIOUR".indexOf(b.code));
    for (const p of sorted) {
      const up = p.up != null ? p.up : p.seats;
      for (let i = 0; i < p.seats; i++) seats.push({ code: p.code, faded: U.office !== "H" && p.up != null && i >= up });
    }
    return seats;
  }
  function chamber(r) {
    const N = r.seats_total, seats = order(r);
    const W = 640, H = 360, cx = W / 2, cy = 318, R1 = 270, R0 = 110;
    const rows = Math.max(2, Math.round(Math.sqrt(0.273 * N)));
    const radii = Array.from({ length: rows }, (_, i) => R0 + ((R1 - R0) * (i + 0.5)) / rows);
    const sum = radii.reduce((a, b) => a + b, 0);
    const counts = radii.map((rr) => Math.round((N * rr) / sum)); counts[rows - 1] += N - counts.reduce((a, b) => a + b, 0);
    const pts = [];
    radii.forEach((rr, i) => { const k = counts[i]; for (let j = 0; j < k; j++) { const a = Math.PI * (1 - (j + 0.5) / k); pts.push({ a, x: cx + rr * Math.cos(a), y: cy - rr * Math.sin(a) }); } });
    pts.sort((p, q) => q.a - p.a);
    const dot = Math.max(2.2, Math.min((Math.PI * sum) / N, (R1 - R0) / rows) * 0.42);
    let dots = "";
    pts.forEach((pt, i) => { const s = seats[i]; if (!s) return; dots += `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="${dot.toFixed(2)}" fill="${PC[s.code]}" ${s.faded ? 'opacity=".38"' : ""}><title>${esc(PN[s.code])}${s.faded ? " · not up this year" : ""}</title></circle>`; });
    const maj = r.majority;
    return `<svg class="elHemi" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(r.parties.map((p) => `${PN[p.code]} ${p.seats}`).join(", "))}">${dots}
      <line x1="${cx}" y1="${cy - R1 - 22}" x2="${cx}" y2="${cy - R0 + 18}" stroke="rgba(230,240,245,.5)" stroke-dasharray="3 4"/>
      <text x="${cx}" y="${cy + 6}" text-anchor="middle" class="elHemiNum">${maj}</text><text x="${cx}" y="${cy + 26}" text-anchor="middle" class="elHemiLbl">for a majority</text></svg>`;
  }
  function evBar(r) {
    const N = r.seats_total, sorted = [...r.parties].sort((a, b) => "DIOUR".indexOf(a.code) - "DIOUR".indexOf(b.code));
    let x = 0;
    const segs = sorted.map((p) => { const w = (100 * p.seats) / N; const s = `<span style="left:${x}%;width:${w}%;background:${PC[p.code]}" title="${esc(p.candidate || PN[p.code])}: ${p.seats}"></span>`; x += w; return s; }).join("");
    const pv = r.popular_vote || {};
    return `<div class="usEv"><div class="usEvBar">${segs}<i style="left:${(100 * r.majority) / N}%"></i></div>
      <div class="usEvNames">${sorted.map((p) => `<div><b style="color:${PC[p.code]}">${p.seats}</b><span>${esc(p.candidate || PN[p.code])}</span><small>${pv[p.code] != null ? `${pv[p.code]}% of the popular vote` : ""}</small></div>`).join("")}</div>
      <p class="fine">${r.majority} electoral votes to win.</p></div>`;
  }
  function partyList(r) {
    return `<ul class="elBlocList">${r.parties.map((p) => `<li><div class="elBlocRow"><span class="elSw" style="background:${PC[p.code]}"></span><b>${esc(p.candidate ? `${p.candidate} (${p.code})` : PN[p.code])}</b><span class="num">${p.seats}</span><span class="num elShare">${p.up != null ? `${p.up} this year` : p.share != null ? `${p.share}%` : ""}</span></div></li>`).join("")}</ul>
      ${r.popular_vote && U.office === "H" ? `<p class="fine">Popular vote for the House: ${Object.entries(r.popular_vote).filter(([, v]) => v >= 0.5).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${PN[k]} ${v}%`).join(", ")}. Uncontested seats have no votes counted.</p>` : ""}`;
  }

  // ---------------------------------------------------------------- maps
  const shade = (v) => { if (!v) return "rgba(120,130,140,.25)"; if (!v.c) return v.l ? PC[v.l] : PC.U; return PC[v.p] || PC.O; };
  const alpha = (v) => { if (!v || !v.c) return 0.35; if (v.m == null) return 0.85; return Math.min(1, 0.42 + Math.min(v.m, 30) / 30 * 0.58); };
  function stateMap(r) {
    const g = U.geo; if (!g) return `<p class="fine">Map unavailable.</p>`;
    const vals = r.map.values || {};
    let paths = "";
    for (const [st, rings] of Object.entries(g.states)) {
      const v = vals[st];
      const d = rings.map((ring) => { let s = ""; for (let i = 0; i < ring.length; i += 2) s += (i ? "L" : "M") + ring[i] + " " + ring[i + 1]; return s + "Z"; }).join("");
      const faded = v && v.up === false;
      const op = v ? (faded ? 0.22 : alpha(v)) : 0.12;
      const sel = U.pick === st;
      paths += `<path d="${d}" fill="${shade(v)}" fill-opacity="${op.toFixed(2)}" stroke="${sel ? "#fff" : "rgba(10,20,30,.9)"}" stroke-width="${sel ? 2 : 0.7}" data-us-state="${st}" ${v && !v.c ? 'stroke-dasharray="3 2"' : ""}><title>${esc(STN[st])}${v ? ` · ${v.c ? PN[v.p] : "not yet called"}${v.m != null ? `, margin ${v.m} pts` : ""}${faded ? " · not up" : ""}` : ""}</title></path>`;
    }
    const dc = vals.DC;
    if (dc && U.office === "P") paths += `<rect x="895" y="245" width="16" height="16" rx="3" fill="${shade(dc)}" fill-opacity="${alpha(dc)}" data-us-state="DC"><title>District of Columbia</title></rect><text x="918" y="257" class="usMapLbl">DC</text>`;
    return `<svg viewBox="0 0 ${g.width} ${g.height}" class="usSvg" role="img" aria-label="Map of US states by result">${paths}</svg>`;
  }
  function tileMap(r) {
    const g = U.geo; const t = g?.tiles?.[r.map.era]; if (!t) return `<p class="fine">No tile map for this apportionment.</p>`;
    const vals = r.map.values || {};
    const cells = Object.entries(t);
    const maxC = Math.max(...cells.map(([, c]) => c[0])) + 1.5, maxR = Math.max(...cells.map(([, c]) => c[1])) + 1;
    const rr = Math.min(940 / (maxC * Math.sqrt(3)), 580 / (maxR * 1.5 + 0.5));
    const w = Math.sqrt(3) * rr;
    const hex = (x, y) => Array.from({ length: 6 }, (_, i) => { const a = (Math.PI / 3) * i + Math.PI / 6; return `${(x + rr * 0.94 * Math.cos(a)).toFixed(1)},${(y + rr * 0.94 * Math.sin(a)).toFixed(1)}`; }).join(" ");
    let out = "", lastSt = "";
    const byState = {};
    for (const [k, [c, row]] of cells) {
      const st = k.split("-")[0], v = vals[k];
      const x = 10 + w * (c + (row % 2 ? 0.5 : 0)) + w / 2, y = 10 + rr + row * rr * 1.5;
      (byState[st] = byState[st] || []).push([x, y]);
      const sel = U.pick === k;
      out += `<polygon points="${hex(x, y)}" fill="${shade(v)}" fill-opacity="${alpha(v).toFixed(2)}" stroke="${sel ? "#fff" : v && !v.c ? "rgba(230,240,245,.55)" : "none"}" stroke-width="${sel ? 2 : 1}" ${v && !v.c ? 'stroke-dasharray="2 2"' : ""} data-us-seat="${k}"><title>${esc(STN[st])} ${k.split("-")[1]}${v ? ` · ${v.c ? `${v.w || PN[v.p]} (${v.p})` : "not yet called"}${v.m != null ? `, ${v.m} pts` : ""}` : ""}</title></polygon>`;
    }
    let labels = "";
    for (const [st, pts] of Object.entries(byState)) {
      const x = pts.reduce((a, p) => a + p[0], 0) / pts.length, y = pts.reduce((a, p) => a + p[1], 0) / pts.length;
      if (pts.length >= 2) labels += `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" class="usTileLbl">${st}</text>`;
    }
    const W = 20 + w * maxC, H = 20 + rr * (maxR * 1.5 + 0.5);
    return `<svg viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}" class="usSvg" role="img" aria-label="House districts as tiles">${out}${labels}</svg>`;
  }
  function legend(r) {
    const codes = r.parties.map((p) => p.code);
    return `<div class="usLegend">${codes.map((c) => `<span><i style="background:${PC[c]}"></i>${esc(PN[c])}</span>`).join("")}<span class="fine">Darker = wider margin${r.uncalled ? "; dashed outline = not yet called (tinted by the leader)" : ""}.</span></div>`;
  }

  function pickCard(r) {
    if (!U.pick) return `<p class="fine">Click a ${U.office === "H" ? "district" : "state"} for its result${U.office === "H" ? "" : " and to see who represents it below"}.</p>`;
    const list = U.office === "H" ? r.seats.filter((s) => `${s.state}-${s.seat}` === U.pick) : r.seats.filter((s) => s.state === U.pick && (U.office !== "S" || true));
    if (!list.length) return `<p class="fine">${esc(STN[U.pick.split("-")[0]] || U.pick)}: no race in this election.</p>`;
    return list.map((s) => {
      const c = (s.cands || []).filter((x) => x[0]);
      return `<div class="usPick"><h4>${esc(seatName(s))}${U.office === "S" ? ` <small>Class ${esc(s.seat)}${s.up === false ? `, elected ${s.cycle}` : ""}</small>` : ""}${U.office === "P" && s.ev ? ` <small>${s.ev} electoral vote${s.ev > 1 ? "s" : ""}</small>` : ""}</h4>
        <p class="fine">${s.called ? `${esc(s.winner || PN[s.party])} (${esc(s.party)})${s.unopposed ? " · unopposed" : s.margin != null ? ` · margin ${s.margin} pts` : ""}${s.previous && s.previous !== s.party ? ` · seat changed from ${esc(PN[s.previous])}` : ""}` : `Not yet called${s.status ? `: ${esc(s.status)}` : ""}`}</p>
        ${c.length ? `<table class="elTable"><tbody>${c.map((x) => `<tr><td><span class="elSw" style="background:${PC[x[1]] || PC.O}"></span>${esc(x[0])} <small>${esc(x[1])}</small>${x[4] ? " ✓" : ""}</td><td class="num">${x[2] ? Number(x[2]).toLocaleString("en-US") : ""}</td><td class="num">${x[3] != null ? `${x[3]}%` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
        ${s.origin === "wikipedia" ? `<p class="fine">From Wikipedia, as edited when Sanjaya last read it.</p>` : ""}</div>`;
    }).join("");
  }

  function tables(r) {
    const row = (s) => `<tr data-us-go="${U.office === "H" ? `${s.state}-${s.seat}` : s.state}"><td>${esc(seatName(s))}</td><td><span class="elSw" style="background:${PC[s.party]}"></span>${esc(s.winner || PN[s.party])}</td><td class="num">${s.margin != null ? `${s.margin} pts` : ""}</td>${s.from ? `<td>${esc(PN[s.from])} → ${esc(PN[s.party])}</td>` : ""}</tr>`;
    const close = r.closest || [], flips = r.flips || [];
    return `<div class="elTables">${close.length ? `<div class="panel"><h3>Closest races</h3><div class="tableWrap"><table class="elTable usClick"><thead><tr><th>Race</th><th>Winner</th><th class="num">Margin</th></tr></thead><tbody>${close.map(row).join("")}</tbody></table></div></div>` : ""}
      ${flips.length ? `<div class="panel"><h3>Changed party</h3><div class="tableWrap"><table class="elTable usClick"><thead><tr><th>Race</th><th>Winner</th><th class="num">Margin</th><th>Change</th></tr></thead><tbody>${flips.slice(0, 40).map(row).join("")}</tbody></table></div>${flips.length > 40 ? `<p class="fine">And ${flips.length - 40} more.</p>` : ""}</div>` : ""}</div>`;
  }

  // ---------------------------------------------------------------- in office now
  function loadOfficials(force = false) {
    const scope = U.scope;
    clearTimeout(U.offTimer);
    const cur = U.off[scope];
    if (cur && !cur.pending && !force) return paintOfficials();
    A().api(`/api/us/officials?scope=${encodeURIComponent(scope)}${force ? "&refresh=1" : ""}`).then((d) => {
      U.off[scope] = d; paintOfficials();
      if (d.pending && U.scope === scope) U.offTimer = setTimeout(() => loadOfficials(), 2000);
    }).catch((e) => { U.off[scope] = { error: e.message, people: [] }; paintOfficials(); });
    if (force) { U.off[scope] = { ...(cur || {}), pending: true }; paintOfficials(); }
  }
  function paintOfficials() { const o = $("#usOfficials"); if (o) { const t = o.querySelector(".elTimeline")?.scrollTop || 0; o.innerHTML = officialsPanel(); const tl = o.querySelector(".elTimeline"); if (tl) tl.scrollTop = t; } }
  function officialsPanel() {
    const d = U.off[U.scope];
    const opts = `<select id="usScope" aria-label="Whose office-holders"><option value="us">United States</option>${Object.entries(STN).filter(([k]) => k !== "DC").map(([k, n]) => `<option value="us-state:${k}" ${U.scope === `us-state:${k}` ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
    const head = `<div class="elPanelBar"><h3>In office now</h3><span class="elBarRight">${opts}<button class="choice elRefresh" data-us-offrefresh ${d?.pending ? "disabled" : ""}>${d?.pending ? "Updating…" : "Refresh"}</button></span></div>`;
    if (!d) return head + `<p class="fine elWait">Fetching current office-holders…</p>`;
    const people = d.people || [];
    let last = "", rows = "";
    const ini = (n) => String(n || "?").split(/\s+/).filter((w) => /^[A-Za-z]/.test(w)).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    for (const p of people) {
      if (p.group !== last) { rows += `<li class="elTlGroup">${esc(p.group)}</li>`; last = p.group; }
      const ph = p.photo?.src ? `<img src="${esc(p.photo.src)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-el-initials="${esc(ini(p.name))}">` : `<span class="elAv">${esc(ini(p.name))}</span>`;
      const links = (p.contacts || []).map((c) => `<a href="${esc(c.url)}" ${c.url.startsWith("http") ? 'target="_blank" rel="noopener noreferrer"' : ""}>${esc(c.label)}</a>`);
      if (p.wikipedia) links.push(`<a href="${esc(p.wikipedia)}" target="_blank" rel="noopener noreferrer">Wikipedia</a>`);
      rows += `<li class="elTlItem"><div class="elPhoto">${ph}</div><div class="elWho"><b>${esc(p.name)}</b><span class="elPos">${esc(p.position)}</span>
        <div class="elMeta">${p.party ? `<span class="elTag"><span class="elSw" style="background:${esc(p.party_color || "#8A96A3")}"></span>${esc(p.party)}</span>` : ""}${p.since ? `<span>Since ${esc(longDate(p.since))}</span>` : ""}</div>
        ${links.length ? `<div class="elLinks">${links.join("")}</div>` : ""}
        <div class="elCred">${[esc(p.source || ""), p.photo?.credit ? `<a href="${esc(p.photo.credit)}" target="_blank" rel="noopener noreferrer">${esc(p.photo.credit_label || "Photo")}</a>` : ""].filter(Boolean).join(" · ")}</div></div></li>`;
    }
    const icon = { running: "elStRun", done: "elStOk", empty: "elStNone", failed: "elStFail" };
    const steps = d.pending && d.steps?.length ? `<ol class="elSteps">${d.steps.map((s) => `<li class="${icon[s.state] || ""}"><span class="elStDot"></span>${esc(s.label)} <small>${esc(s.state)}${s.count != null && s.state === "done" ? ` · ${s.count}` : ""}</small></li>`).join("")}</ol>` : "";
    return head + steps + (people.length ? `<ol class="elTimeline">${rows}</ol>` : d.pending ? `<p class="fine elWait">Fetching…</p>` : `<p class="fine">${d.live_error ? "The sources could not be reached. Press Refresh to try again." : "No office-holders found."}</p>`) +
      `<p class="fine elOffFoot">${d.as_of ? `Checked ${esc(longDate(d.as_of.slice(0, 10)))} · ` : ""}${people.length} listed. Official contacts only: office websites, contact forms and Capitol office numbers. Members elected in November 2026 take office on 3 January 2027.</p>`;
  }

  // ---------------------------------------------------------------- events
  function wire() {
    const b = U.body; if (!b || b.dataset.usWired) return;
    b.dataset.usWired = "1";
    b.addEventListener("click", (e) => {
      if (!b.querySelector(".elUS") && !b.querySelector("#usDownload")) return;
      const t = e.target.closest("[data-us-office],[data-us-cycle],[data-us-state],[data-us-seat],[data-us-go],[data-us-refresh],[data-us-offrefresh],#usDownload");
      if (!t) return;
      if (t.id === "usDownload") {
        // Show progress at once; the server's own steps replace this within a second.
        U.cat.pack.job = { state: "running", step: "Starting the download", done: 0, total: (U.cat.pack.job?.total || 8) };
        draw();
        A().api("/api/us/download", "POST", {}).then(() => loadCatalog())
          .catch((err) => { U.cat.pack.job = { state: "failed", error: `The download could not start: ${err.message}` }; draw(); });
        return;
      }
      if (t.dataset.usOffice) { U.office = t.dataset.usOffice; const o = U.cat.offices.find((x) => x.office === U.office); if (!o.cycles.includes(Number(U.cycle))) U.cycle = o.cycles[0]; U.pick = null; return load(); }
      if (t.dataset.usCycle) { U.cycle = Number(t.dataset.usCycle); U.pick = null; return load(); }
      if (t.hasAttribute("data-us-refresh")) { t.disabled = true; return load(true); }
      if (t.hasAttribute("data-us-offrefresh")) { t.disabled = true; return loadOfficials(true); }
      const st = t.dataset.usState || t.dataset.usSeat || t.dataset.usGo;
      if (st) {
        U.pick = st;
        const s2 = st.split("-")[0];
        if (STN[s2] && s2 !== "DC") { U.scope = `us-state:${s2}`; remember(); }
        draw(); loadOfficials();
        $("#usPick")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    });
    b.addEventListener("change", (e) => {
      if (e.target.id === "usScope") { U.scope = e.target.value; remember(); paintOfficials(); loadOfficials(); }
    });
  }

  return { mount, destroy };
})();
