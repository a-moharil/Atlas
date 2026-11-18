"use strict";
/* Atlas v5.9 · Wikipedia (English): search, read inside Atlas, see what Atlas holds on
   the same topic, and ask about the page. Links between articles stay in Atlas. */
window.ATLASWiki = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const KEY = "atlas.wiki.v1";
  const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } })();
  const S = { q: saved.q || "", results: null, suggestion: "", searching: false, error: "", page: null, loading: false, back: [], held: null, seq: 0 };
  const remember = () => { try { localStorage.setItem(KEY, JSON.stringify({ q: S.q, title: S.page?.title || "" })); } catch (e) { /* storage off */ } };
  const el = (s) => document.querySelector(s);
  let typing = 0;

  function layout() {
    return `<div class="wkPage"><div class="heroTitle"><div><h1>Wikipedia</h1><p>Search and read English Wikipedia inside Atlas, next to the articles Atlas holds on the same topic.</p></div></div>
      <form class="wkSearch" role="search" onsubmit="return false"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/></svg>
        <input id="wkQ" type="search" value="${esc(S.q)}" placeholder="Search Wikipedia" aria-label="Search Wikipedia" autocomplete="off"><button class="action primary" id="wkGo">Search</button></form>
      <div class="wkBody"><div id="wkMain" class="wkMain"></div><aside id="wkSide" class="wkSide"></aside></div></div>`;
  }
  function mount() {
    draw();
    if (!S.page && saved.title && !S.loading) open(saved.title, { quiet: true });
    else if (!S.page && !S.results && S.q) search(S.q);
  }

  async function search(q) {
    q = (q || "").trim();
    S.q = q; remember();
    if (q.length < 2) { S.results = null; draw(); return; }
    const seq = ++S.seq;
    S.searching = true; S.error = ""; draw();
    try {
      const d = await A().api(`/api/wiki/search?q=${encodeURIComponent(q)}`);
      if (seq !== S.seq) return;
      S.results = d.results; S.suggestion = d.suggestion || ""; S.stale = d.stale;
      S.page = null;
    } catch (e) { if (seq === S.seq) S.error = e.message; }
    S.searching = false; draw();
  }
  async function open(title, opts = {}) {
    if (!title) return;
    if (S.page && !opts.fromBack) S.back.push(S.page.title);
    S.loading = true; S.error = ""; draw();
    try {
      const d = await A().api(`/api/wiki/page?title=${encodeURIComponent(title)}`);
      S.page = d; S.held = null; remember();
      draw();
      if (opts.frag) setTimeout(() => el(`#${CSS.escape(opts.frag)}`)?.scrollIntoView({ block: "start" }), 50);
      else window.scrollTo({ top: 0 });
      held(d.title, d.aliases || []);
    } catch (e) { S.error = e.message; if (opts.quiet) S.page = null; }
    S.loading = false; draw();
  }
  // Atlas articles on the same topic, through the panel search.
  async function held(title, aliases) {
    // The title or any bolded alias (commas mean "either").
    const q = [title, ...aliases.filter((x) => x.toLowerCase() !== title.toLowerCase())].map((x) => x.replace(/,/g, " ")).join(", ");
    try {
      const d = await fetch("/api/find", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q, mode: "auto", limit: 8 }) }).then((r) => r.json());
      if (S.page?.title !== title) return;
      const map = new Map((A().state.state?.entries || []).map((e) => [e.id, e]));
      S.held = { mode: d.mode, list: (d.results || []).map((r) => map.get(r.id)).filter(Boolean) };
    } catch (e) { S.held = { list: [], error: e.message }; }
    drawSide();
  }

  function draw() {
    const main = el("#wkMain");
    if (!main) return;
    const inp = el("#wkQ");
    if (inp && document.activeElement !== inp) inp.value = S.q;
    if (S.loading && !S.page) { main.innerHTML = `<div class="pageLoading">Opening the article…</div>`; drawSide(); return; }
    if (S.page) {
      const p = S.page;
      main.innerHTML = `<article class="wkArticle">
        <div class="wkTools">${S.back.length ? `<button class="linkButton" data-wkback="1">Back to ${esc(S.back[S.back.length - 1])}</button>` : ""}${S.results ? `<button class="linkButton" data-wkresults="1">Search results</button>` : ""}
          <span class="wkToolsEnd"><button class="action" data-askwiki="${esc(p.title)}">Ask about this page</button><a class="linkButton" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">Open on Wikipedia ↗</a></span></div>
        <header class="wkHead">${p.thumbnail ? `<img src="${esc(p.thumbnail)}" alt="" class="wkThumb">` : ""}<div><h2>${esc(p.title)}</h2>${p.description ? `<p class="wkDesc">${esc(p.description)}</p>` : ""}
          <p class="fine">From English Wikipedia${p.stale ? " · offline copy saved " + esc(A().ago(p.fetched)) : p.cached ? " · saved copy" : ""} · text under CC BY-SA 4.0</p></div></header>
        ${S.loading ? `<p class="fine">Opening…</p>` : ""}${S.error ? `<p class="fine wkErr">${esc(S.error)}</p>` : ""}
        <div class="wkContent">${p.html}</div></article>`;
    } else if (S.results || S.searching || S.error) {
      main.innerHTML = `${S.searching ? `<p class="fine">Searching Wikipedia…</p>` : ""}${S.error ? `<div class="empty"><b>Wikipedia search failed</b><span class="fine">${esc(S.error)}</span></div>` : ""}
        ${S.suggestion ? `<p class="fine">Did you mean <button class="linkButton" data-wksearch="${esc(S.suggestion)}">${esc(S.suggestion)}</button>?</p>` : ""}
        ${S.results ? (S.results.length ? `<ol class="wkResults">${S.results.map((r) => `<li><button class="wkHit" data-wiki="${esc(r.title)}"><b>${esc(r.title)}</b><span>${esc(r.snippet)}…</span><small class="fine">${(r.words || 0).toLocaleString()} words</small></button></li>`).join("")}</ol>` : `<div class="empty"><b>No Wikipedia articles found</b><span class="fine">Try fewer or different words.</span></div>`) : ""}`;
    } else {
      main.innerHTML = `<div class="empty"><b>Search English Wikipedia</b><span class="fine">Articles open here, and links between them stay in Atlas. Pages you've read stay readable offline.</span></div>`;
    }
    drawSide();
  }
  function drawSide() {
    const side = el("#wkSide");
    if (!side) return;
    if (!S.page) { side.innerHTML = ""; return; }
    const h = S.held;
    side.innerHTML = `<section class="panel"><div class="panelHeading"><h2>Held in Atlas</h2>${h?.mode ? `<span class="fine">by ${h.mode === "both" ? "meaning and keywords" : h.mode}</span>` : ""}</div>
      ${!h ? `<p class="fine">Looking for related articles…</p>` : h.list.length ? `<div class="newsList">${h.list.map((e) => A().card(e, { short: true })).join("")}</div>` : `<p class="fine">Atlas doesn't hold articles about “${esc(S.page.title)}”. Search a desk to fetch some from the web.</p>`}</section>`;
  }

  function onClick(ev) {
    const t = ev.target.closest("[data-wiki],[data-wikijump],[data-wkback],[data-wkresults],[data-wksearch],#wkGo,[data-askwiki]");
    if (!t || !t.closest(".wkPage")) return false;
    if (t.id === "wkGo") { search(el("#wkQ").value); return true; }
    if (t.dataset.askwiki) { window.ATLASAsk?.open({ wiki: t.dataset.askwiki }); return true; }
    ev.preventDefault();
    if (t.dataset.wikijump) { el(`#${CSS.escape(t.dataset.wikijump)}`)?.scrollIntoView({ block: "center" }); return true; }
    if (t.dataset.wkback) { open(S.back.pop(), { fromBack: true }); return true; }
    if (t.dataset.wkresults) { S.page = null; S.back = []; draw(); return true; }
    if (t.dataset.wksearch) { search(t.dataset.wksearch); return true; }
    if (t.dataset.wiki) {
      if (S.page && t.dataset.wiki.replace(/_/g, " ") === S.page.title && t.dataset.wikifrag) { el(`#${CSS.escape(t.dataset.wikifrag)}`)?.scrollIntoView({ block: "start" }); return true; }
      open(t.dataset.wiki, { frag: t.dataset.wikifrag });
      return true;
    }
    return false;
  }
  document.addEventListener("input", (e) => {
    if (e.target.id !== "wkQ") return;
    clearTimeout(typing);
    const q = e.target.value;
    typing = setTimeout(() => search(q), 500);
  });
  document.addEventListener("keydown", (e) => { if (e.target.id === "wkQ" && e.key === "Enter") { e.preventDefault(); clearTimeout(typing); search(e.target.value); } });
  document.addEventListener("click", (ev) => { if (A()?.state?.view === "wiki" && onClick(ev)) ev.stopPropagation(); }, true);
  return { layout, mount, open, current: () => S.page?.title || "" };
})();
