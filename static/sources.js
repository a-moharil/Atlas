"use strict";
/* Sanjaya v5 · Source library: every publisher Sanjaya reads, with its identity, outlet-level
   bias rating, factuality, ownership and paywall model. Primary publishers are promoted
   across the desks; blocked publishers are no longer fetched and are hidden everywhere. */
window.ATLASSources = (() => {
  let data = null, loaded = 0, busy = false;
  const st = { q: "", group: "news", lean: "all", access: "all" };
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  const GROUPS = [
    ["news", "News outlets"], ["primary", "Primary"], ["blocked", "Blocked"], ["research", "Think tanks and research"],
    ["official", "Official and institutions"], ["discovery", "Discovery feeds"], ["all", "Everything"],
  ];
  const groupOf = (p) =>
    p.host.startsWith("feed:") ? "discovery" : p.kind === "government" ? "official" : ["think-tank", "academic", "journal", "community"].includes(p.kind) ? "research" : "news";
  function layout() {
    return `<div class="heroTitle"><div><h1>Sources</h1><p>Every publisher Sanjaya reads. Mark the ones you trust as primary and they lead every desk; block one and Sanjaya stops fetching it and hides its stories everywhere, including the emergency newsroom.</p></div></div>
    <div class="srcToolbar"><input id="srcSearch" type="search" placeholder="Find a publisher" value="${esc(st.q)}"><div class="filterTabs" style="margin:0">${GROUPS.map(([k, v]) => `<button class="choice ${st.group === k ? "active" : ""}" data-srcgroup="${k}">${v}</button>`).join("")}</div>
     <select id="srcLean"><option value="all">Any lean</option><option value="left">Left-leaning</option><option value="center">Centre</option><option value="right">Right-leaning</option><option value="none">Not rated</option></select>
     <select id="srcAccess"><option value="all">Any access</option><option value="free">Free</option><option value="metered">Metered or partly paywalled</option><option value="hard">Hard paywall</option></select></div>
    <div id="srcBody"><p class="fine">Loading publishers…</p></div>
    <div class="panel" style="margin-top:22px"><h2>How these labels are made</h2><p class="fine" id="srcMethod"></p><p class="fine">Logos are fetched from each publisher's own site (or a favicon service) and cached locally. Names are set in open-licence typefaces chosen to echo each masthead's style; they are not the publishers' proprietary wordmarks.</p></div>`;
  }
  function leanClass(l) { return l === null || l === undefined ? "none" : l < 0 ? "left" : l > 0 ? "right" : "center"; }
  function cardHTML(p) {
    const pref = p.pref || "normal";
    const sub = [p.country, p.ownership].filter(Boolean).join(" · ") || (p.host.startsWith("feed:") ? "Google News discovery feed" : p.host);
    const lean = p.lean;
    const scale = [-2, -1, 0, 1, 2].map((v) => `<i class="${v === lean ? "on " : ""}${v < 0 ? "l" + -v : v > 0 ? "r" + v : "l0"}"></i>`).join("");
    const pw = A().paywallTag(p.paywall, p.paywall_note);
    return `<article class="srcCard ${pref}" data-host="${esc(p.host)}">
      <button class="srcHead" data-srcopen="${esc(p.host)}" title="Open ${esc(p.name)}">${A().logoTag(p, "lg")}<span><span class="pubName mast-${esc(p.masthead)}">${esc(p.name)}</span><small>${esc(sub)}</small></span></button>
      ${p.kind === "news" ? `<div><div class="leanScale" title="${esc((p.raters || []).map((r) => r.provider + ": " + r.rating).join(" · ") || "Not rated by MBFC or AllSides")}">${scale}</div><div class="leanLabel"><span>${esc(p.lean_label)}</span><span>${p.factual ? "Factual: " + esc(p.factual) : ""}</span></div></div>` : ""}
      <div class="srcFacts">${pw}${p.state_media ? '<span class="tag">State media</span>' : ""}${p.questionable ? '<span class="tag" title="Flagged questionable by Media Bias/Fact Check">MBFC: questionable</span>' : ""}<span class="tag">${num(p.records)} stories</span>${p.feeds.length ? `<span class="tag" title="${esc(p.feeds.map((f) => f.name + ": " + f.state).join("\n"))}">${p.healthy}/${p.feeds.length} feeds healthy</span>` : '<span class="tag">via aggregator</span>'}</div>
      <div class="srcActions"><button class="action star ${pref === "primary" ? "on" : ""}" data-srcpref="${pref === "primary" ? "normal" : "primary"}" data-srchost="${esc(p.host)}">${pref === "primary" ? "★ Primary" : "☆ Make primary"}</button><button class="action block ${pref === "blocked" ? "on" : ""}" data-srcpref="${pref === "blocked" ? "normal" : "blocked"}" data-srchost="${esc(p.host)}">${pref === "blocked" ? "Blocked · undo" : "Block"}</button></div>
    </article>`;
  }
  function filtered() {
    let list = data?.publishers || [];
    const q = st.q.trim().toLowerCase();
    if (q) list = list.filter((p) => (p.name + " " + p.host + " " + (p.ownership || "")).toLowerCase().includes(q));
    if (st.group === "primary") list = list.filter((p) => p.pref === "primary");
    else if (st.group === "blocked") list = list.filter((p) => p.pref === "blocked");
    else if (st.group !== "all") list = list.filter((p) => groupOf(p) === st.group);
    if (st.lean !== "all") list = list.filter((p) => leanClass(p.lean) === st.lean);
    if (st.access === "free") list = list.filter((p) => ["free", "registration"].includes(p.paywall));
    else if (st.access === "metered") list = list.filter((p) => ["metered", "freemium"].includes(p.paywall));
    else if (st.access === "hard") list = list.filter((p) => p.paywall === "hard");
    return list;
  }
  function draw() {
    const body = document.querySelector("#srcBody");
    if (!body || !data) return;
    const all = data.publishers;
    const list = filtered();
    const primary = all.filter((p) => p.pref === "primary"), blocked = all.filter((p) => p.pref === "blocked");
    const m = document.querySelector("#srcMethod");
    if (m) m.textContent = data.method;
    body.innerHTML = `<p class="fine">${num(all.filter((p) => groupOf(p) === "news").length)} news outlets · ${num(primary.length)} primary · ${num(blocked.length)} blocked · showing ${num(list.length)}</p>
      ${list.length ? `<div class="srcGrid">${list.map(cardHTML).join("")}</div>` : `<div class="empty"><b>No publishers match</b><span class="fine">${st.group === "primary" ? "Mark publishers as primary from the News outlets tab." : "Clear the search or pick another group."}</span></div>`}`;
  }
  async function load(force) {
    if (busy) return;
    busy = true;
    try {
      data = await A().api("/api/sources");
      loaded = Date.now();
      draw();
    } catch (e) {
      const body = document.querySelector("#srcBody");
      if (body) body.innerHTML = `<div class="empty"><b>Could not load publishers</b><span class="fine">${esc(e.message)}</span></div>`;
    } finally { busy = false; }
  }
  async function setPref(host, state) {
    try {
      const out = await A().api("/api/source-pref", "POST", { host, state });
      if (A().state.state) A().state.state.source_prefs = out.source_prefs;
      for (const p of data?.publishers || []) if (p.host === host) p.pref = state;
      draw();
      const name = (data?.publishers || []).find((p) => p.host === host)?.name || host;
      A().tip(state === "blocked" ? `Blocked ${name}. Its feeds are skipped and its stories hidden everywhere.` : state === "primary" ? `${name} is now a primary source.` : `${name} restored to normal.`);
      A().hydrate();
    } catch (e) { A().tip("Could not save: " + e.message); }
  }
  function openPublisher(host) {
    const p = (data?.publishers || []).find((x) => x.host === host);
    if (!p) return;
    const items = (A().state.state?.entries || []).filter((e) => e.publisher === host && e.medium === "article").slice(0, 30);
    const panel = document.querySelector("#storyPanel"), c = document.querySelector("#storyContent");
    panel.hidden = false;
    c.innerHTML = `<div class="drawerTop">${A().pubBadge(p, p.name, "lg")}<button class="closeIcon" data-close="true">Close</button></div>
     <div class="tagline">${A().paywallTag(p.paywall, p.paywall_note)}<span class="tag">${esc(p.lean_label)}</span>${p.factual ? `<span class="tag">Factual: ${esc(p.factual)}</span>` : ""}</div>
     <div class="section"><p class="fine">${esc([p.ownership, p.country].filter(Boolean).join(" · "))}</p><p class="fine">${esc(p.paywall_note || "")}</p>${(p.raters || []).length ? `<p class="fine">${p.raters.map((r) => esc(r.provider + ": " + r.rating)).join(" · ")}${p.rating_url ? ` · <a href="${esc(p.rating_url)}" target="_blank" rel="noopener noreferrer">methodology ↗</a>` : ""}</p>` : ""}</div>
     <div class="section"><h3>Latest from ${esc(p.name)}</h3>${items.length ? `<div class="newsList">${items.map((e) => A().card(e, { short: true })).join("")}</div>` : '<p class="fine">No stories from this publisher in the current window.</p>'}</div>
     <div class="section"><h3>Feeds</h3>${p.feeds.length ? p.feeds.map((f) => `<p class="fine"><b>${esc(f.name)}</b> · ${esc(f.state)}${f.error ? " · " + esc(f.error) : ""}</p>`).join("") : '<p class="fine">Seen only through Google News discovery feeds.</p>'}</div>`;
  }
  function onClick(ev) {
    const b = ev.target.closest("[data-srcgroup],[data-srcpref],[data-srcopen]");
    if (!b) return false;
    if (b.dataset.srcgroup) { st.group = b.dataset.srcgroup; document.querySelectorAll("[data-srcgroup]").forEach((x) => x.classList.toggle("active", x === b)); draw(); }
    else if (b.dataset.srcpref) setPref(b.dataset.srchost, b.dataset.srcpref);
    else if (b.dataset.srcopen) openPublisher(b.dataset.srcopen);
    return true;
  }
  function onChange(e) {
    if (e.target.id === "srcLean") { st.lean = e.target.value; draw(); return true; }
    if (e.target.id === "srcAccess") { st.access = e.target.value; draw(); return true; }
    return false;
  }
  let t;
  function onInput(e) {
    if (e.target.id !== "srcSearch") return false;
    clearTimeout(t); t = setTimeout(() => { st.q = e.target.value; draw(); }, 160);
    return true;
  }
  function mount() {
    const lean = document.querySelector("#srcLean"), acc = document.querySelector("#srcAccess");
    if (lean) lean.value = st.lean;
    if (acc) acc.value = st.access;
    if (data) draw();
    load();
  }
  function refreshIfStale() { if (Date.now() - loaded > 60000) load(); }
  return { layout, mount, onClick, onChange, onInput, refreshIfStale };
})();
