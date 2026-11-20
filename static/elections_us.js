"use strict";
/* Sanjaya v6.5 · Elections, United States: House, Senate, governors and president.
   Results as recorded; Sanjaya never calls a race. 2026 is read from Wikipedia while counting finishes. */
window.ATLASElectionsUS = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const KEY = "atlas.elections.us.v1";
  const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } })();
  const U = { office: saved.office || "H", cycle: saved.cycle || null, mode: saved.mode || "races", cat: null, res: {}, geo: null, pick: null, scope: saved.scope || "us",
    off: {}, timer: 0, offTimer: 0, error: "", body: null, seq: 0 };
  const remember = () => { try { localStorage.setItem(KEY, JSON.stringify({ office: U.office, cycle: U.cycle, scope: U.scope, mode: U.mode })); } catch (e) { /* storage off */ } };
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

  async function load(force = false, tick = false) {
    const k = key(), seq = ++U.seq;
    if (!U.res[k] || force || U.res[k].live?.pending || (tick && U.res[k].live)) {
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
    else if (r?.live) U.timer = setTimeout(() => { if (key() === k && U.body) load(false, true); }, r.live.ap?.enabled ? 125000 : 600000);   // keep counting races fresh
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
    const chg = Object.entries(r.change || {}).filter(([c]) => c !== "U").sort((a, b) => "DIOR".indexOf(a[0]) - "DIOR".indexOf(b[0]));
    if (r.previous) stats.push([chg.length ? chg.map(([c, n]) => `<span style="color:${PC[c]}">${c} ${n > 0 ? "+" : "−"}${Math.abs(n)}</span>`).join(" ") : "±0", `since ${r.previous.cycle}`]);
    return `<section class="elHead"><div><h2>${esc(r.label)}</h2><p class="fine">${U.office === "P" ? lead.map((p) => `${esc(p.candidate || PN[p.code])} (${p.code}) ${p.seats}`).join(" · ") : ""}</p></div>
        <div class="elStats">${stats.map(([v, l]) => `<div><b>${v}</b><span>${esc(l)}</span></div>`).join("")}</div></section>
      ${liveLine(r)}
      <div class="elTop"><div class="panel elChamber"><h3>${U.office === "P" ? "Electoral votes" : U.office === "G" ? "Governorships" : "Seats"}</h3>${U.office === "P" ? evBar(r) : chamber(r)}
          ${U.office === "S" || U.office === "G" ? `<p class="fine usChamberKey"><span class="usDotSolid"></span>won in ${U.cycle} <span class="usDotHollow"></span>elected earlier, not up${Object.keys(r.lean || {}).length ? ` <span class="usDotLean"></span>not yet called` : ""}</p>` : ""}</div>
        <div class="panel elBlocs"><h3>Parties</h3>${partyList(r)}</div></div>
      <div class="panel elMap usMap"><div class="elPanelBar"><h3>${U.office === "H" ? "Districts" : "States"}</h3>${U.office === "S" || U.office === "G" ? `<div class="filterTabs elMini" role="tablist" aria-label="What the map shows">${[["races", `${U.cycle} races`], ["whole", U.office === "S" ? "Whole Senate after it" : "All governors after it"]].map(([k, n]) => `<button class="choice ${U.mode === k ? "active" : ""}" data-us-mode="${k}" aria-pressed="${U.mode === k}">${esc(n)}</button>`).join("")}</div>` : `<span class="fine">${U.office === "H" ? "One tile per district, grouped by state. Tiles don't change when district lines are redrawn." : ""}</span>`}</div>
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
    const ap = l.ap || {};
    const btn = `<button class="choice elRefresh" data-us-refresh ${l.pending ? "disabled" : ""}>${l.pending ? "Reading…" : "Check now"}</button>`;
    const wp = `<a href="https://en.wikipedia.org/wiki/${encodeURIComponent(l.page.replace(/ /g, "_"))}" target="_blank" rel="noopener noreferrer">Wikipedia</a>`;
    let apText;
    if (ap.enabled && !ap.error) apText = `<b>Associated Press:</b> ${ap.races} race${ap.races === 1 ? "" : "s"}, read ${esc(ago(ap.fetched))}; checked again every two minutes while this page is open.`;
    else if (ap.enabled) apText = `<b>Associated Press:</b> ${esc(ap.error)}${ap.races ? ` Showing the last ${ap.races} races AP returned.` : ""}`;
    else apText = `<b>Associated Press:</b> not connected. AP's results and race calls need an AP Elections API key, which AP licenses to news organisations; Sanjaya cannot read them without one.`;
    const wpText = l.pending ? esc(l.step || `Reading ${l.page}`) + "…" : l.error && !l.wikipedia_races ? `${wp} could not be read (${esc(l.error)}).` :
      `${wp}: ${l.wikipedia_races ?? (r.seats || []).length} race${l.wikipedia_races === 1 ? "" : "s"}${ap.enabled ? " that AP did not return" : ""}, read ${esc(ago(l.fetched))}. Editors update it by hand, so it can trail the count by hours or days.`;
    const keyForm = ap.enabled ? `<button class="linkButton" data-us-apkey-clear>Remove AP key</button>` :
      `<form class="usApForm" data-us-apform><label><span>AP Elections API key</span><input type="password" name="k" autocomplete="off" spellcheck="false" placeholder="Paste your key"></label><button class="choice" type="submit">Connect AP</button><a href="https://developer.ap.org/ap-elections-api" target="_blank" rel="noopener noreferrer">How to get one</a></form>`;
    return `<div class="panel elNote usLive" role="status"><div class="usLiveText"><p>${apText}</p><p><b>Wikipedia:</b> ${wpText}</p>
      <p class="fine">A race is called only when the source calls it. Until then it is striped toward whoever is ahead. The key is kept on this computer and never shown again.</p>${keyForm}</div>${btn}</div>`;
  }

  // ---------------------------------------------------------------- charts
  function order(r) {
    // Called seats, then seats leaning the same way (not called), from left (D) to right (R); unknown in the middle.
    const seats = [], lean = r.lean || {};
    const called = Object.fromEntries(r.parties.filter((p) => p.code !== "U").map((p) => [p.code, p]));
    const push = (code, n, extra) => { for (let i = 0; i < n; i++) seats.push({ code, ...extra }); };
    for (const c of ["D", "I", "O"]) {
      const p = called[c];
      if (p) { const up = p.up != null ? p.up : p.seats; for (let i = 0; i < p.seats; i++) seats.push({ code: c, faded: U.office !== "H" && p.up != null && i >= up }); }
      push(c, lean[c] || 0, { lean: true });
    }
    push("U", lean["?"] || 0, { lean: true });
    push("R", lean.R || 0, { lean: true });
    const p = called.R;
    if (p) { const up = p.up != null ? p.up : p.seats; const f = []; for (let i = 0; i < p.seats; i++) f.push({ code: "R", faded: U.office !== "H" && p.up != null && i >= up }); seats.push(...f.reverse()); }
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
    pts.forEach((pt, i) => {
      const s = seats[i]; if (!s) return;
      dots += s.lean
        ? `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="${(dot * 0.86).toFixed(2)}" fill="${s.code === "U" ? "none" : `url(#usLean_${s.code})`}" stroke="${PC[s.code]}" stroke-width="1.3" stroke-dasharray="2 1.6"><title>${s.code === "U" ? "Not yet called, no count yet" : `Not yet called, ${esc(PN[s.code])} ahead`}</title></circle>`
        : s.faded
          ? `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="${(dot * 0.82).toFixed(2)}" fill="none" stroke="${PC[s.code]}" stroke-width="1.6"><title>${esc(PN[s.code])} · elected earlier, not up in ${U.cycle}</title></circle>`
          : `<circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="${dot.toFixed(2)}" fill="${PC[s.code]}"><title>${esc(PN[s.code])}${U.office !== "H" ? ` · won in ${U.cycle}` : ""}</title></circle>`;
    });
    const maj = r.majority;
    return `<svg class="elHemi" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(r.parties.map((p) => `${PN[p.code]} ${p.seats}`).join(", "))}">${leanDefs()}${dots}
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
    const lean = r.lean || {};
    const leanRows = Object.keys(lean).length ? `<li class="usLeanHead">Not yet called</li>${["D", "I", "O", "R", "?"].filter((c) => lean[c]).map((c) => `<li><div class="elBlocRow"><span class="elSw usLeanSw" style="--c:${c === "?" ? PC.U : PC[c]}"></span><b>${c === "?" ? "No count yet" : `${esc(PN[c])} ahead`}</b><span class="num">${lean[c]}</span><span class="num elShare">lean</span></div></li>`).join("")}` : "";
    const tally = Object.keys(lean).length ? `<p class="fine">${["D", "R"].map((c) => { const p = r.parties.find((x) => x.code === c); return `${PN[c]}: ${p ? p.seats : 0} called${lean[c] ? ` + ${lean[c]} ahead` : ""}`; }).join(" · ")}. ${r.majority} for a majority. Leads are not calls.</p>` : "";
    return `<ul class="elBlocList">${r.parties.filter((p) => p.code !== "U").map((p) => `<li><div class="elBlocRow"><span class="elSw" style="background:${PC[p.code]}"></span><b>${esc(p.candidate ? `${p.candidate} (${p.code})` : PN[p.code])}</b><span class="num">${p.seats}${r.change && r.change[p.code] ? ` <small class="${r.change[p.code] > 0 ? "up" : "down"}">${r.change[p.code] > 0 ? "+" : "−"}${Math.abs(r.change[p.code])}</small>` : ""}</span><span class="num elShare">${p.up != null ? `${p.up} won in ${U.cycle}` : p.share != null ? `${p.share}%` : ""}</span></div></li>`).join("")}${leanRows}</ul>${tally}
      ${r.previous ? `<p class="fine">Change is against the ${r.previous.cycle} ${U.office === "P" ? "election" : "result"} (${Object.entries(r.previous.parties).sort((a, b) => "DIOR".indexOf(a[0]) - "DIOR".indexOf(b[0])).map(([c, n]) => `${c} ${n}`).join(", ")}).</p>` : ""}
      ${r.popular_vote && U.office === "H" ? `<p class="fine">Popular vote for the House: ${Object.entries(r.popular_vote).filter(([, v]) => v >= 0.5).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${PN[k]} ${v}%`).join(", ")}. Uncontested seats have no votes counted.</p>` : ""}`;
  }

  // ---------------------------------------------------------------- maps
  // One meaning per look:
  //   solid party colour      won (lighter = closer race: under 5 pts, 5 to 15, over 15)
  //   party stripes, dashed   not yet called, striped toward whoever is ahead
  //   slate grey              no race for this office here this year (or, for old years, no data)
  const SLATE = "#34404C";
  const mix = (hex, t) => { const n = parseInt(hex.slice(1), 16); const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => Math.round(x + (255 - x) * t)); return `rgb(${c.join(",")})`; };
  const tint = (code, m) => { const base = PC[code] || PC.O; if (m == null) return base; return m < 5 ? mix(base, 0.45) : m < 15 ? mix(base, 0.22) : base; };
  const fillFor = (v) => { if (!v) return SLATE; if (!v.c) return leanUrl(v); return tint(v.p, v.m); };
  const shade = (v) => (v && v.c ? PC[v.p] || PC.O : SLATE);
  const alpha = () => 1;
  const splitDefs = () => { const pairs = ["DR", "DI", "IR", "DO", "OR", "IO"]; return `<defs>${pairs.map((p) => `<pattern id="usSplit_${p}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="10" fill="${PC[p[0]]}"/><rect x="5" width="5" height="10" fill="${PC[p[1]]}"/></pattern>`).join("")}</defs>`; };
  const wholeFill = (v) => {
    if (!v) return SLATE;
    const parts = (v.both || [v.p]).map((x) => (x === "U" ? (v.l || "U") : x));
    if (U.office === "G" || parts.length < 2 || parts[0] === parts[1]) return v.c || v.up === false ? PC[parts[0]] || PC.O : leanUrl(v);
    const pair = ["D", "I", "O", "R"].filter((c) => parts.includes(c)).join("");
    return pair.length === 2 ? `url(#usSplit_${pair})` : PC[parts[0]];
  };
  function stateMap(r) {
    const g = U.geo; if (!g) return `<p class="fine">Map unavailable.</p>`;
    const vals = r.map.values || {};
    let paths = "";
    for (const [st, rings] of Object.entries(g.states)) {
      const v = vals[st];
      const d = rings.map((ring) => { let s = ""; for (let i = 0; i < ring.length; i += 2) s += (i ? "L" : "M") + ring[i] + " " + ring[i + 1]; return s + "Z"; }).join("");
      const notUp = v && v.up === false;
      const whole = U.mode === "whole" && (U.office === "S" || U.office === "G");
      const fill = whole ? wholeFill(v) : notUp ? SLATE : fillFor(v);
      const uncalled = v && !v.c && !notUp;
      const sel = U.pick === st;
      const what = !v ? "no data" : notUp ? `no ${U.office === "S" ? "Senate" : "governor"} race in ${U.cycle}${whole ? `; held by ${(v.both || [v.p]).map((x) => PN[x]).join(" and ")}` : ""}` : v.c ? `${PN[v.p]}${v.m != null ? `, margin ${v.m} pts` : ""}` : `not yet called${v.l ? `, ${PN[v.l]} ahead` : ""}`;
      paths += `<path d="${d}" fill="${fill}" stroke="${sel ? "#fff" : uncalled ? "rgba(235,242,246,.7)" : "rgba(10,20,30,.9)"}" stroke-width="${sel ? 2 : uncalled ? 1 : 0.7}" data-us-state="${st}" ${uncalled ? 'stroke-dasharray="3 2"' : ""}><title>${esc(STN[st])} · ${esc(what)}</title></path>`;
    }
    const dc = vals.DC;
    if (dc && U.office === "P") paths += `<rect x="895" y="245" width="16" height="16" rx="3" fill="${fillFor(dc)}" data-us-state="DC"><title>District of Columbia</title></rect><text x="918" y="257" class="usMapLbl">DC</text>`;
    return `<svg viewBox="0 0 ${g.width} ${g.height}" class="usSvg" role="img" aria-label="Map of US states by result">${leanDefs()}${splitDefs()}${paths}</svg>`;
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
      out += `<polygon points="${hex(x, y)}" fill="${fillFor(v)}" stroke="${sel ? "#fff" : v && !v.c ? "rgba(230,240,245,.55)" : "none"}" stroke-width="${sel ? 2 : 1}" ${v && !v.c ? 'stroke-dasharray="2 2"' : ""} data-us-seat="${k}"><title>${esc(STN[st])} ${k.split("-")[1]}${v ? ` · ${v.c ? `${v.w || PN[v.p]} (${v.p})` : "not yet called"}${v.m != null ? `, ${v.m} pts` : ""}` : ""}</title></polygon>`;
    }
    let labels = "";
    for (const [st, pts] of Object.entries(byState)) {
      const x = pts.reduce((a, p) => a + p[0], 0) / pts.length, y = pts.reduce((a, p) => a + p[1], 0) / pts.length;
      if (pts.length >= 2) labels += `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" class="usTileLbl">${st}</text>`;
    }
    const W = 20 + w * maxC, H = 20 + rr * (maxR * 1.5 + 0.5);
    return `<svg viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}" class="usSvg" role="img" aria-label="House districts as tiles">${leanDefs()}${out}${labels}</svg>`;
  }
  function legend(r) {
    const codes = r.parties.map((p) => p.code).filter((c) => c !== "U");
    const lean = Object.keys(r.lean || {}).filter((c) => c !== "?");
    const whole = U.mode === "whole" && (U.office === "S" || U.office === "G");
    const swatch = (bg, label, cls = "") => `<span><i class="${cls}" style="${bg}"></i>${esc(label)}</span>`;
    const margin = U.office === "H" || U.office === "P" || !whole ? `<span class="usRamp">${codes.filter((c) => c === "D" || c === "R").map((c) => `<i style="background:${tint(c, 2)}"></i><i style="background:${tint(c, 10)}"></i><i style="background:${tint(c, 30)}"></i>`).join("<b></b>")}<em>closer → wider margin</em></span>` : "";
    return `<div class="usLegend">${codes.map((c) => swatch(`background:${PC[c]}`, `${PN[c]} ${whole ? "holds" : "won"}`)).join("")}
      ${whole && U.office === "S" ? swatch("background:repeating-linear-gradient(45deg,#3A78D4 0 4px,#D5483F 4px 8px)", "Split delegation") : ""}
      ${lean.map((c) => swatch(`--c:${PC[c]}`, `Not yet called, ${PN[c]} ahead`, "usLeanKey")).join("")}
      ${r.lean?.["?"] ? swatch(`--c:${PC.U}`, "Not yet called, no count yet", "usLeanKey") : ""}
      ${!whole && (U.office === "S" || U.office === "G") ? swatch(`background:${SLATE}`, `No race in ${U.cycle}`) : ""}
      ${margin}</div>
      <p class="fine usLegendNote">${whole ? (U.office === "S" ? `Each state's two senators after the ${U.cycle} election, including those elected earlier. Striped red and blue: one senator from each party.` : `Every governor after the ${U.cycle} round, including those elected earlier.`)
        : U.office === "S" || U.office === "G" ? `Only the ${U.cycle} races are coloured; grey states had no ${U.office === "S" ? "Senate" : "governor"} race that year. Switch to the other view to see the whole ${U.office === "S" ? "Senate" : "map"}.`
        : "Solid colour: won. Lighter: a closer race."} Stripes with a dashed edge mean a race is still being counted; they show who is ahead, not a call.</p>`;
  }
  // Diagonal stripes in a party's colour: the lean of a race that has not been called.
  const leanDefs = () => `<defs>${["D", "R", "I", "O", "U"].map((c) => `<pattern id="usLean_${c}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="${PC[c]}" fill-opacity=".16"/><rect width="2.6" height="6" fill="${PC[c]}" fill-opacity=".85"/></pattern>`).join("")}</defs>`;
  const leanUrl = (v) => `url(#usLean_${v.l && PC[v.l] ? v.l : "U"})`;

  function pickCard(r) {
    if (!U.pick) return `<p class="fine">Click a ${U.office === "H" ? "district" : "state"} for its result${U.office === "H" ? "" : " and to see who represents it below"}.</p>`;
    const list = U.office === "H" ? r.seats.filter((s) => `${s.state}-${s.seat}` === U.pick) : r.seats.filter((s) => s.state === U.pick && (U.office !== "S" || true));
    if (!list.length) return `<p class="fine">${esc(STN[U.pick.split("-")[0]] || U.pick)}: no race in this election.</p>`;
    return list.map((s) => {
      const c = (s.cands || []).filter((x) => x[0]);
      return `<div class="usPick"><h4>${esc(seatName(s))}${U.office === "S" ? ` <small>Class ${esc(s.seat)}${s.up === false ? `, elected ${s.cycle}` : ""}</small>` : ""}${U.office === "P" && s.ev ? ` <small>${s.ev} electoral vote${s.ev > 1 ? "s" : ""}</small>` : ""}</h4>
        <p class="fine">${s.called ? `${esc(s.winner || PN[s.party])} (${esc(s.party)})${s.unopposed ? " · unopposed" : s.margin != null ? ` · margin ${s.margin} pts` : ""}${s.previous && s.previous !== s.party ? ` · seat changed from ${esc(PN[s.previous])}` : ""}` :
          `Not yet called.${s.leader_party ? ` ${esc(s.leader || PN[s.leader_party])} (${esc(s.leader_party)}) is ahead${s.margin != null ? ` by ${s.margin} pts` : ""}.` : ""}${s.counted != null ? ` About ${Math.round(s.counted)}% of the expected vote counted.` : ""}${s.status && s.origin !== "ap" ? ` ${esc(s.status)}.` : s.status && /runoff/i.test(s.status) ? " Heading to a runoff." : ""}`}</p>
        ${c.length ? `<table class="elTable"><tbody>${c.map((x) => `<tr><td><span class="elSw" style="background:${PC[x[1]] || PC.O}"></span>${esc(x[0])} <small>${esc(x[1])}</small>${x[4] ? " ✓" : ""}</td><td class="num">${x[2] ? Number(x[2]).toLocaleString("en-US") : ""}</td><td class="num">${x[3] != null ? `${x[3]}%` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
        ${s.origin === "wikipedia" ? `<p class="fine">Source: Wikipedia, as edited when Sanjaya last read it.</p>` : s.origin === "ap" ? `<p class="fine">Source: Associated Press.</p>` : ""}</div>`;
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
      const t = e.target.closest("[data-us-office],[data-us-cycle],[data-us-mode],[data-us-state],[data-us-seat],[data-us-go],[data-us-refresh],[data-us-offrefresh],[data-us-apkey-clear],#usDownload");
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
      if (t.dataset.usMode) { U.mode = t.dataset.usMode; remember(); return draw(); }
      if (t.hasAttribute("data-us-refresh")) { t.disabled = true; return load(true); }
      if (t.hasAttribute("data-us-apkey-clear")) { A().api("/api/us/settings", "POST", { ap_key: "" }).then(() => load(true)); return; }
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
    b.addEventListener("submit", (e) => {
      const f = e.target.closest("[data-us-apform]"); if (!f) return;
      e.preventDefault();
      const k = f.querySelector("input").value.trim(); if (!k) return;
      f.querySelector("button").disabled = true;
      A().api("/api/us/settings", "POST", { ap_key: k }).then(() => load(true)).catch((err) => { f.insertAdjacentHTML("beforeend", `<span class="elError">${esc(err.message)}</span>`); f.querySelector("button").disabled = false; });
    });
    b.addEventListener("change", (e) => {
      if (e.target.id === "usScope") { U.scope = e.target.value; remember(); paintOfficials(); loadOfficials(); }
    });
  }

  return { mount, destroy };
})();
