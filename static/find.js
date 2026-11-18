"use strict";
/* Atlas v5.8 · A search bar on every article panel.
   Each panel searches its own articles by keywords, by meaning (the local language
   model), or both. When nothing held matches, Atlas fetches articles about the query
   from Google News into the panel's desk and searches again.
   Query syntax: words (most must match), "quoted phrases", commas for either topic. */
window.ATLASFind = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const panels = new Map(); // key -> options from the latest render
  const S = {};             // key -> { q, mode, seq, busy, data, fetch, shown, focus }
  const extra = new Map();  // entries the server sent that aren't in the page state
  let focus = null, typing = 0;
  const st = (k) => (S[k] ||= { q: "", mode: "auto", seq: 0, busy: false, data: null, fetch: null, shown: 20 });
  const MODES = [["auto", "Best available"], ["both", "Meaning + keywords"], ["meaning", "Meaning"], ["keywords", "Keywords"]];
  const MODE_SAID = { both: "by meaning and keywords", meaning: "by meaning", keywords: "by keywords" };
  const lm = () => A().state.state?.grouping?.mode === "meaning";

  async function post(path, body, seconds) {
    const res = await fetch(path, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(seconds * 1000) });
    const d = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok) throw Error(d?.error || `HTTP ${res.status}`);
    return d;
  }
  function register(key, opts) { panels.set(key, opts); }
  function bar(key, opts) {
    const s = st(key);
    const ph = `Search ${opts.label || "this panel"}: words, "a phrase", or topics separated by commas`;
    return `<form class="findBar ${opts.wide ? "wide" : ""}" data-findform="${esc(key)}" role="search" onsubmit="return false">
      <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>
      <input type="search" data-findq="${esc(key)}" value="${esc(s.q)}" placeholder="${esc(ph)}" aria-label="Search ${esc(opts.label || "this panel")}" autocomplete="off" spellcheck="false">
      <select data-findmode="${esc(key)}" aria-label="How to match" title="${lm() ? "How to match the query" : "The language model is off or loading: meaning search will fall back to keywords"}">
        ${MODES.map(([k, t]) => `<option value="${k}" ${s.mode === k ? "selected" : ""}>${t}</option>`).join("")}</select>
      ${opts.source === "reel" ? "" : `<button type="button" class="findAsk" data-askpanel="${esc(key)}" title="Ask a question about ${esc(opts.label || "this panel")}">Ask</button>`}</form>`;
  }

  // ---------------------------------------------------------------- searching
  function entryMap() {
    const m = new Map((A().state.state?.entries || []).map((e) => [e.id, e]));
    for (const [k, v] of extra) if (!m.has(k)) m.set(k, v);
    return m;
  }
  async function run(key, opts = {}) {
    const s = st(key), p = panels.get(key);
    if (!p) return;
    const q = s.q.trim();
    if (!q) { s.data = null; s.fetch = null; paint(key); return; }
    const seq = ++s.seq;
    s.busy = true; s.shown = 20;
    if (!opts.keepFetch) s.fetch = null;
    paint(key);
    try {
      const body = { q, mode: s.mode, limit: 120, source: p.source || "state" };
      if (body.source !== "reel") { body.ids = p.ids(); body.extra = s.fetch?.ids || []; }
      const d = await post("/api/find", body, 60);
      if (seq !== s.seq) return;
      for (const e of d.entries || []) extra.set(e.id, e);
      Object.assign(A().state.state.publishers ||= {}, d.publishers || {});
      s.data = d; s.error = "";
    } catch (e) {
      if (seq !== s.seq) return;
      s.data = null; s.error = e.message;
    }
    s.busy = false;
    paint(key);
    // Nothing held matches: look for articles about it on the web (once per query).
    if (s.data && !s.data.results.length && p.web !== false && !s.fetch) fetchWeb(key);
  }
  async function fetchWeb(key) {
    const s = st(key), p = panels.get(key), q = s.q.trim();
    if (!q || s.fetch?.busy) return;
    s.fetch = { busy: true, q };
    paint(key);
    try {
      const d = await post("/api/find/fetch", { q, desk: p.desk || "World" }, 90);
      if (s.q.trim() !== q) return;
      s.fetch = { ...d, busy: false, q };
      if (d.added) await A().hydrate();
      await run(key, { keepFetch: true });
    } catch (e) {
      if (s.q.trim() !== q) return;
      s.fetch = { busy: false, q, error: e.message, ids: [] };
      paint(key);
    }
  }

  // ---------------------------------------------------------------- drawing
  function why(r) {
    const parts = [];
    if (r.terms?.length) parts.push(`matches ${r.terms.map((t) => `<b>${esc(t)}</b>`).join(", ")}`);
    if (r.meaning != null && r.meaning >= 0.3) parts.push(`${Math.round(r.meaning * 100)}% similar in meaning`);
    return parts.length ? `<div class="findWhy">${parts.join(" · ")}</div>` : "";
  }
  function webBlock(key, s, p, n) {
    if (p.web === false) return n ? "" : `<p class="fine findWeb">${esc(p.webNote || "")}</p>`;
    const f = s.fetch;
    if (f?.busy) return `<p class="fine findWeb"><span class="findSpin" aria-hidden="true"></span>Fetching articles about “${esc(f.q)}” from Google News…</p>`;
    if (f?.error) return `<p class="fine findWeb findErr">Couldn't reach Google News: ${esc(f.error)}. <button class="linkButton" data-findweb="${esc(key)}">Try again</button></p>`;
    if (f) return `<p class="fine findWeb">Google News returned ${f.fetched} article${f.fetched === 1 ? "" : "s"} (${f.added} new to Atlas)${f.notes?.length ? `; ${f.notes.length} search${f.notes.length === 1 ? "" : "es"} failed` : ""}. They are filed under ${esc(p.desk || "World")} as “Search further”.</p>`;
    return n < 5 ? `<p class="fine findWeb">${n ? "Only a few matches." : ""} <button class="linkButton" data-findweb="${esc(key)}">Fetch articles about this from the web</button></p>` : `<p class="fine findWeb"><button class="linkButton" data-findweb="${esc(key)}">Fetch more from the web</button></p>`;
  }
  function paint(key) {
    const body = document.querySelector(`[data-findbody="${CSS.escape(key)}"]`);
    const p = panels.get(key), s = st(key);
    if (!body || !p) return;
    if (!body.dataset.orig) body.dataset.orig = "1", (body._orig = body.innerHTML);
    if (!s.q.trim()) { if (body._orig != null && body.classList.contains("finding")) { body.innerHTML = body._orig; body.classList.remove("finding"); } return; }
    body.classList.add("finding");
    const d = s.data;
    if (s.busy && !d) { body.innerHTML = `<div class="findHead"><span class="fine"><span class="findSpin" aria-hidden="true"></span>Searching…</span></div>`; return; }
    if (!d) { body.innerHTML = `<div class="findHead"><span class="fine findErr">Search failed: ${esc(s.error || "unknown error")}</span><button class="linkButton" data-findclear="${esc(key)}">Clear search</button></div>`; return; }
    const map = entryMap();
    const hits = d.results.map((r) => [r, map.get(r.id)]).filter(([, e]) => e);
    const shown = hits.slice(0, s.shown);
    const head = `<div class="findHead"><span>${hits.length ? `<b>${hits.length}</b> match${hits.length === 1 ? "" : "es"}` : "No matches"} for “${esc(s.q.trim())}” ${MODE_SAID[d.mode] || ""}<span class="fine"> · searched ${d.pool.toLocaleString()} ${esc(p.label || "items")}${s.busy ? " · updating…" : ""}</span></span>
      <button class="linkButton" data-findclear="${esc(key)}">Clear search</button></div>${d.note ? `<p class="fine findNote">${esc(d.note)}</p>` : ""}`;
    const list = shown.length ? p.wrap(shown.map(([r, e]) => `<div class="findHit">${why(r)}${p.item(e)}</div>`).join("")) : "";
    const more = hits.length > s.shown ? `<button class="linkButton findMore" data-findmore="${esc(key)}">Show ${Math.min(20, hits.length - s.shown)} more</button>` : "";
    // Articles Google News returned for this query that don't match it here (other wording, other language).
    const got = new Set(d.results.map((r) => r.id));
    const alsoWeb = (s.fetch?.ids || []).filter((i) => !got.has(i)).map((i) => map.get(i)).filter(Boolean).slice(0, 12);
    const also = alsoWeb.length ? `<h3 class="findAlso">Also returned by Google News for this search <span class="fine">worded differently, so not matched ${MODE_SAID[d.mode] || ""}</span></h3>${p.wrap(alsoWeb.map((e) => `<div class="findHit">${p.item(e)}</div>`).join(""))}` : "";
    body.innerHTML = head + list + more + also + webBlock(key, s, p, hits.length);
  }
  // Called after every page render: put active searches back.
  function apply() {
    for (const key of panels.keys()) {
      const body = document.querySelector(`[data-findbody="${CSS.escape(key)}"]`);
      if (!body) continue;
      if (!body.classList.contains("finding")) { body._orig = body.innerHTML; body.dataset.orig = "1"; }
      const s = st(key);
      if (s.q.trim()) { if (s.data || s.busy) paint(key); else run(key); }
    }
    if (focus) {
      const el = document.querySelector(`[data-findq="${CSS.escape(focus.key)}"]`);
      if (el && document.activeElement !== el) { el.focus(); try { el.setSelectionRange(focus.pos, focus.pos); } catch (e) { /* search inputs */ } }
    }
  }

  // ---------------------------------------------------------------- events
  document.addEventListener("input", (e) => {
    const key = e.target.dataset?.findq;
    if (key == null) return;
    const s = st(key);
    s.q = e.target.value;
    focus = { key, pos: e.target.selectionStart };
    clearTimeout(typing);
    typing = setTimeout(() => run(key), s.q.trim() ? 450 : 0);
  });
  document.addEventListener("keydown", (e) => {
    const key = e.target.dataset?.findq;
    if (key == null) return;
    if (e.key === "Enter") { e.preventDefault(); clearTimeout(typing); run(key); }
    if (e.key === "Escape" && e.target.value) { e.preventDefault(); e.target.value = ""; st(key).q = ""; run(key); }
  });
  document.addEventListener("focusout", (e) => { if (e.target.dataset?.findq != null) setTimeout(() => { if (!document.activeElement?.dataset?.findq) focus = null; }, 0); });
  document.addEventListener("change", (e) => {
    const key = e.target.dataset?.findmode;
    if (key == null) return;
    st(key).mode = e.target.value;
    if (st(key).q.trim()) run(key);
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-findclear],[data-findmore],[data-findweb]");
    if (!b) return;
    if (b.dataset.findclear != null) {
      const key = b.dataset.findclear;
      st(key).q = ""; st(key).fetch = null;
      const inp = document.querySelector(`[data-findq="${CSS.escape(key)}"]`);
      if (inp) inp.value = "";
      run(key);
    } else if (b.dataset.findmore != null) { st(b.dataset.findmore).shown += 20; paint(b.dataset.findmore); }
    else if (b.dataset.findweb != null) fetchWeb(b.dataset.findweb);
  });
  return { register, bar, apply, run, entry: (id) => entryMap().get(id), panel: (k) => panels.get(k), _S: S };
})();
