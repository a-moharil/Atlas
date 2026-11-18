"use strict";
/* Atlas v5.3 · Research radar: new ML research ranked against your own papers,
   the Vanschoren / AMOR/e lab, themes, related-work check, benchmarks, deadlines,
   reading queue and an optional weekly digest. All data stays on this computer. */
window.ATLASRadar = (() => {
  const A = () => window.ATLAS;
  const W = () => window.ATLASWall;
  const esc = (s) => A().esc(s);
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  const TABS = [
    ["foryou", "For you"], ["lab", "Vanschoren and AMOR/e"], ["themes", "Themes"], ["related", "Related-work check"],
    ["bench", "Benchmarks and datasets"], ["deadlines", "Deadlines"], ["queue", "Reading queue"], ["fingerprint", "Your papers"],
  ];
  const SRC = { fingerprint: "Your papers", keywords: "arXiv search", rss: "arXiv daily", huggingface: "Hugging Face", openalex: "OpenAlex", lab: "Lab trace", openml: "OpenML", deadlines: "Deadlines" };
  const SOURCE_NAME = { arxiv: "arXiv", hf: "Hugging Face", openalex: "OpenAlex" };
  const S = { tab: "foryou", days: 7, data: null, themes: null, themesDays: null, related: null, relatedText: "", queue: null, open: new Set(), busy: false,
    q: "", mode: "auto", f: { lane: "", cat: "", min: "", source: "", saved: "", hf: false }, results: null, searching: false, probe: null, probing: false };
  const filtering = () => !!(S.q.trim() || Object.values(S.f).some(Boolean));
  let timer = 0, alive = false;

  const plain = (s) => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  function when(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const h = (Date.now() - d) / 36e5;
    if (h < 1) return "just now";
    if (h < 24) return `${Math.round(h)} h ago`;
    if (h < 24 * 14) return `${Math.round(h / 24)} d ago`;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  const pct = (m) => Math.round(100 * Math.max(0, Math.min(1, m || 0)));
  const tier = (m) => (m >= 0.6 ? "hi" : m >= 0.45 ? "mid" : "lo");

  function layout() {
    return `<div class="heroTitle"><div><h1>Research radar</h1><p>New machine learning research ranked against your own papers, plus the Vanschoren and AMOR/e lab, this week's themes, benchmarks and conference deadlines. Everything is matched and stored on this computer.</p></div></div>
      <div id="rdBar" class="rdBar"></div>
      <div class="filterTabs rdTabs" role="tablist">${TABS.map(([k, v]) => `<button class="choice ${S.tab === k ? "active" : ""}" data-rdtab="${k}" role="tab" aria-selected="${S.tab === k}">${v}<span class="rdCount" data-rdcount="${k}"></span></button>`).join("")}</div>
      <div id="rdBody"><div class="pageLoading">Loading the research radar…</div></div>`;
  }

  // ---------------------------------------------------------------- shared bits
  function members() {
    return new Set((S.data?.trace?.lab_members || []).map(plain));
  }
  function authors(list, more) {
    const lab = members();
    const shown = (list || []).map((a) => (lab.has(plain(a)) ? `<b class="rdLabName" title="AMOR/e lab">${esc(a)}</b>` : esc(a)));
    return shown.join(", ") + (more ? ` and ${more} more` : "");
  }
  function paper(p, opts = {}) {
    const saved = S.data?.queue?.[p.id];
    const id = esc(p.id);
    const cats = (p.categories || []).slice(0, 3).map((c) => `<span class="rdCat">${esc(c)}</span>`).join("");
    return `<article class="rdPaper" data-paper="${id}">
      <div class="rdMeta">
        ${opts.noMatch ? "" : `<span class="rdMatch ${tier(p.match)}" title="Similarity to your closest paper">${pct(p.match)}% match</span>`}
        ${p.lab ? `<span class="rdLab" title="Joaquin Vanschoren or the AMOR/e lab">AMOR/e</span>` : ""}
        ${p.hf_upvotes ? `<span class="rdHf" title="Upvotes on Hugging Face daily papers">▲ ${num(p.hf_upvotes)} on Hugging Face</span>` : ""}
        ${opts.score != null ? `<span class="rdQScore" title="Similarity to your search">${pct(opts.score)}% similar to your search</span>` : ""}
        <span class="rdWhen">${esc(when(p.published))}</span>${p.source && p.source !== "arxiv" ? `<span class="rdSrcTag">${esc(SOURCE_NAME[p.source] || p.source)}</span>` : ""}${cats}${p.venue ? `<span class="rdVenue">${esc(p.venue)}</span>` : ""}
      </div>
      <h3><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a></h3>
      <p class="rdAuthors">${authors(p.authors, p.more_authors)}</p>
      ${p.nearest && !opts.noMatch && p.match >= 0.4 ? `<p class="rdNearest">Closest to your paper <i>${esc(p.nearest)}</i></p>` : ""}
      ${p.abstract ? `<details class="rdAbs"><summary>Abstract</summary><p>${esc(p.abstract)}</p></details>` : ""}
      <div class="rdActions">
        <button class="rdSave ${saved ? "on" : ""}" data-rdsave="${id}" ${saved ? "disabled" : ""}>${saved ? "In reading queue" : "Save to reading queue"}</button>
        ${p.pdf ? `<a class="fine" href="${esc(p.pdf)}" target="_blank" rel="noopener noreferrer">PDF ↗</a>` : ""}
        ${opts.noRemove || !W() ? "" : W().removeBtn(p.id, "Remove from the radar")}
      </div>
    </article>`;
  }
  function index() {
    // Every paper on screen, so "Save" can send the full record.
    const m = new Map();
    const add = (p) => p && m.set(p.id, p);
    S.data?.lanes?.forEach((l) => l.papers.forEach(add));
    S.data?.lab?.forEach(add);
    S.themes?.themes?.forEach((t) => t.papers.forEach(add));
    S.related?.recent?.forEach(add);
    S.related?.wider?.forEach(add);
    S.results?.results?.forEach(add);
    return m;
  }
  const empty = (title, text) => `<div class="empty"><b>${esc(title)}</b><span class="fine">${text}</span></div>`;

  // ---------------------------------------------------------------- status bar
  function bar() {
    const d = S.data, el = document.querySelector("#rdBar");
    if (!el || !d) return;
    const chips = Object.entries(d.sources || {}).map(([k, s]) => {
      const st = s.pending ? "busy" : s.error && !s.last_checked ? "bad" : s.error ? "warn" : "good";
      const tip = s.pending ? "Retrieving in the background" : s.error ? `Last attempt failed: ${s.error}` : s.last_checked ? `Updated ${when(new Date(s.last_checked * 1000).toISOString())}` : "Not yet retrieved";
      return `<span class="rdSrc ${st}" title="${esc(tip)}">${esc(SRC[k] || k)}</span>`;
    }).join("");
    el.innerHTML = `<span class="statusPill ${d.mode === "meaning" ? "good" : "unknown"}" title="${esc(d.note)}">${d.mode === "meaning" ? "Matched by meaning" : "Keyword mode"}</span>
      <span class="rdSources">${chips}</span>
      <span class="rdBarRight"><label class="fine" for="rdDays">Papers from the last</label>
      <select id="rdDays">${[[1, "day"], [3, "3 days"], [7, "7 days"], [14, "14 days"]].map(([v, t]) => `<option value="${v}" ${S.days === v ? "selected" : ""}>${t}</option>`).join("")}</select>
      <button class="action" id="rdRefresh" title="Fetch again from every source">Refresh sources</button></span>`;
    const q = Object.keys(d.queue || {}).length;
    document.querySelectorAll("[data-rdcount]").forEach((x) => {
      const k = x.dataset.rdcount;
      x.textContent = k === "queue" && q ? ` ${q}` : k === "lab" && d.lab?.length ? ` ${d.lab.length}` : "";
    });
  }

  // ---------------------------------------------------------------- tabs
  function digestPanel() {
    const g = S.data?.digest || {};
    const latest = g.latest;
    const running = g.status === "running";
    const body = latest?.text?.summary
      ? `<div class="rdDigest"><span class="nr-genTag">Generated</span><p>${esc(latest.text.summary)}</p>
          ${(latest.text.highlights || []).length ? `<ul>${latest.text.highlights.map((h) => `<li><a href="${esc(h.url)}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a><span class="fine"> ${esc(h.why)}</span></li>`).join("")}</ul>` : ""}
          <p class="fine">Week ${esc(latest.week)} · written by ${esc(latest.model)} on this computer from the titles and abstracts of the week's top matches. Check the papers before relying on it.</p></div>`
      : `<p class="fine">A short summary of the week's top matches, written by your local Ollama model. Nothing leaves this computer.</p>`;
    return `<section class="panel rdDigestPanel"><div class="panelHeading"><h2>Weekly digest</h2>
      <button class="action" id="rdDigest" ${running ? "disabled" : ""}>${running ? "Writing…" : latest?.week === g.week ? "Write again" : "Write this week's digest"}</button></div>
      ${body}${g.status === "error" ? `<p class="fine rdErr">${esc(g.detail)}</p>` : ""}</section>`;
  }
  function searchBar() {
    const d = S.data, f = S.f;
    const opt = (v, t, cur) => `<option value="${esc(v)}" ${String(cur) === String(v) ? "selected" : ""}>${esc(t)}</option>`;
    return `<section class="panel rdSearchPanel">
      <div class="rdSearch"><input id="rdQ" type="search" value="${esc(S.q)}" placeholder='Search: words, "a phrase", author:name, cat:cs.LG, -exclude, or describe an idea' aria-label="Search papers">
        <div class="rdModes" role="radiogroup" aria-label="Search mode">${[["auto", "Auto"], ["keyword", "Keyword"], ["semantic", "Semantic"]].map(([k, t]) => `<button class="${S.mode === k ? "on" : ""}" data-rdmode="${k}" role="radio" aria-checked="${S.mode === k}">${t}</button>`).join("")}</div>
        <button class="action primary" id="rdGo">${S.searching ? "Searching…" : "Search"}</button></div>
      <div class="rdFilters">
        <select data-rdf="lane" aria-label="Lane">${opt("", "All lanes", f.lane)}${(d.lanes || []).map((l) => opt(l.key, l.label, f.lane)).join("")}</select>
        <select data-rdf="cat" aria-label="Category">${opt("", "All categories", f.cat)}${(d.categories || []).map((c) => opt(c, c, f.cat)).join("")}</select>
        <select data-rdf="source" aria-label="Source">${[["", "All sources"], ["arxiv", "arXiv"], ["hf", "Hugging Face"], ["openalex", "OpenAlex (journals)"], ["lab", "Vanschoren and AMOR/e"]].map(([v, t]) => opt(v, t, f.source)).join("")}</select>
        <select data-rdf="min" aria-label="Minimum match">${[["", "Any match"], ["0.3", "30%+ match"], ["0.45", "45%+ match"], ["0.6", "60%+ match"]].map(([v, t]) => opt(v, t, f.min)).join("")}</select>
        <select data-rdf="saved" aria-label="Reading queue">${[["", "Saved or not"], ["saved", "In reading queue"], ["unsaved", "Not saved"]].map(([v, t]) => opt(v, t, f.saved)).join("")}</select>
        <label class="rdCheck"><input type="checkbox" data-rdf="hf" ${f.hf ? "checked" : ""}> On Hugging Face daily papers</label>
        ${filtering() ? `<button class="linkButton" id="rdClearSearch">Clear search and filters</button>` : ""}
      </div></section>`;
  }
  function results() {
    const r = S.results;
    if (!r) return `<div class="pageLoading">Searching…</div>`;
    const mode = r.mode === "semantic" ? "Semantic search" : r.mode === "keyword" ? "Keyword search" : "Filtered";
    const why = S.mode === "auto" && r.reason ? ` (Auto chose this because your search ${esc(r.reason)})` : "";
    const other = r.mode === "semantic" ? "keyword" : r.mode === "keyword" ? "semantic" : "";
    return `<div class="rdResHead"><b>${num(r.total)} result${r.total === 1 ? "" : "s"}</b><span class="fine">${mode}${why} over ${num(r.pool)} papers from the last ${r.days === 1 ? "day" : r.days + " days"}${r.mode === "filters" ? ", closest to your papers first" : ""}.</span>
        ${other && S.q.trim() ? `<button class="linkButton" data-rdmode="${other}">Run as ${other} search</button>` : ""}</div>
      ${r.note ? `<p class="fine rdNote">${esc(r.note)}</p>` : ""}
      ${r.results.length ? `<div class="rdList">${(W() ? W().visible(r.results) : r.results).map((p) => paper(p, { score: r.mode === "semantic" ? p.score : null })).join("")}</div>` : empty("Nothing matches", "Try fewer words, switch mode, widen the period or clear a filter.")}`;
  }
  function forYou() {
    const d = S.data;
    if (filtering()) return searchBar() + results();
    if (!d.held) return searchBar() + digestPanel() + empty(Object.values(d.sources || {}).some((s) => s.pending) ? "Collecting new papers" : "No papers yet", "The radar fetches recent arXiv papers in machine learning, AI, statistics, NLP, neural computing and software engineering. The first run takes a minute or two, longer while the language model processes the abstracts.");
    const lanes = d.lanes.map((l) => {
      const key = "radar:" + l.key;
      const pool = W() ? W().visible(l.papers) : l.papers;
      const shown = W() ? W().arrange(pool, key, 8) : pool.slice(0, 8);
      return `<section class="panel rdLane"><div class="panelHeading"><h2>${esc(l.label)}</h2><span class="panelTools"><span class="fine">${num(l.total)} new</span>${W() ? W().dice(key, pool.length) : ""}</span></div>
        ${shown.length ? `<div class="rdList">${shown.map((p) => paper(p)).join("")}</div>` : `<p class="fine">Nothing new in this lane for the selected period.</p>`}</section>`;
    }).join("");
    const bySrc = Object.entries(d.by_source || {}).map(([k, n]) => `${num(n)} ${SOURCE_NAME[k] || k}`).join(", ");
    return `${searchBar()}${digestPanel()}<p class="fine rdNote">${esc(d.note)} ${num(d.held)} papers from the last ${d.days === 1 ? "day" : d.days + " days"}. ${bySrc ? `(${bySrc}). ` : ""}Each lane shows the closest matches to your papers first; the dice deals from the top 40. ${W() ? W().restoreLine() : ""}</p>${lanes}`;
  }
  function lab() {
    const d = S.data, list = W() ? W().visible(d.lab || []) : d.lab || [];
    return `<section class="panel"><div class="panelHeading"><h2>${esc(d.trace?.name || "Lab")}</h2><a class="linkButton" href="${esc(d.trace?.lab_url || "#")}" target="_blank" rel="noopener noreferrer">Lab website ↗</a></div>
      <p class="fine">Papers with Joaquin Vanschoren as an author, from arXiv's author search and OpenAlex, newest first. Names of current AMOR/e members are in bold.</p>
      ${list.length ? `<div class="rdList">${list.map((p) => paper(p)).join("")}</div>` : empty(d.sources?.lab?.pending ? "Tracing the lab" : "No lab papers yet", d.sources?.lab?.error ? esc(d.sources.lab.error) : "Retrieved from arXiv and OpenAlex in the background.")}</section>`;
  }
  function themes() {
    const t = S.themes;
    if (!t || S.themesDays !== S.days) return `<div class="pageLoading">Grouping this period's papers into themes…</div>`;
    if (!t.themes.length) return empty("No themes yet", "Themes appear once enough papers have been collected (at least three papers on a topic).");
    return `<p class="fine rdNote">${esc(t.note)} ${num(t.papers)} papers grouped into topics; largest first. The label is made of phrases the papers share, not written by a model.</p>
      <div class="rdThemes">${t.themes.map((x) => `<section class="panel rdTheme">
        <div class="rdThemeHead"><h3>${esc(x.label || "Untitled theme")}</h3><span class="fine">${num(x.size)} papers${x.fresh ? ` · ${num(x.fresh)} in the last 48 h` : ""}</span></div>
        <div class="rdThemeMatch" title="Average similarity to your papers"><div style="width:${pct(x.match)}%"></div><span>${pct(x.match)}% average match</span></div>
        <ul>${x.papers.map((p) => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a><button class="linkButton rdMini" data-rdsave="${esc(p.id)}" ${S.data?.queue?.[p.id] ? "disabled" : ""}>${S.data?.queue?.[p.id] ? "Saved" : "Save"}</button></li>`).join("")}</ul>
      </section>`).join("")}</div>`;
  }
  function related() {
    const r = S.related;
    const results = r
      ? `<p class="fine rdNote">${esc(r.note)} Searched for: ${r.terms.map((t) => `<span class="rdCat">${esc(t)}</span>`).join(" ")}${r.notes?.length ? ` · ${esc(r.notes.join("; "))}` : ""}</p>
        <div class="twoEqual">
          <section class="panel"><div class="panelHeading"><h2>Recent, held by Atlas</h2><span class="fine">arXiv and lab papers from the last 30 days</span></div>
            ${r.recent.length ? `<div class="rdList">${r.recent.map((p) => paper(p, { noRemove: true })).join("")}</div>` : `<p class="fine">No close matches among recent papers.</p>`}</section>
          <section class="panel"><div class="panelHeading"><h2>Wider literature</h2><span class="fine">OpenAlex search, re-ranked on this computer</span></div>
            ${r.wider.length ? `<div class="rdList">${r.wider.map((p) => paper(p, { noRemove: true })).join("")}</div>` : `<p class="fine">No close matches in the OpenAlex results.</p>`}</section>
        </div>`
      : "";
    return `<section class="panel"><div class="panelHeading"><h2>Related-work check</h2></div>
      <p class="fine">Paste an abstract, a paragraph from your draft, or a paper you are reviewing. Atlas finds the closest recent papers it holds and searches OpenAlex for older work, then ranks both by similarity to your text. The text is matched on this computer and only search keywords are sent to OpenAlex.</p>
      <textarea id="rdText" class="rdText" rows="7" placeholder="Paste an abstract or a few paragraphs…">${esc(S.relatedText)}</textarea>
      <div class="filters" style="margin-top:10px"><button class="action primary" id="rdFind" ${S.busy ? "disabled" : ""}>${S.busy ? "Searching…" : "Find related work"}</button>${r ? `<button class="action" id="rdClear">Clear</button>` : ""}</div></section>${results}`;
  }
  function bench() {
    const o = S.data.openml || {}, m = S.data.models || [], src = S.data.sources || {};
    const n = (x) => (x == null ? "–" : num(x));
    return `<div class="twoEqual">
      <section class="panel"><div class="panelHeading"><h2>Newest OpenML datasets</h2><a class="linkButton" href="https://www.openml.org/search?type=data" target="_blank" rel="noopener noreferrer">OpenML ↗</a></div>
        ${o.datasets?.length ? `<table class="rdTable"><thead><tr><th>ID</th><th>Dataset</th><th>Rows</th><th>Features</th></tr></thead><tbody>${o.datasets.map((x) => `<tr><td>${esc(x.id)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.name)}</a>${x.version > 1 ? ` <span class="fine">v${esc(x.version)}</span>` : ""}</td><td>${n(x.instances)}</td><td>${n(x.features)}</td></tr>`).join("")}</tbody></table>` : empty(src.openml?.pending ? "Retrieving" : "No datasets yet", src.openml?.error ? esc(src.openml.error) : "From the OpenML API, refreshed daily.")}
      </section>
      <section class="panel"><div class="panelHeading"><h2>Newest OpenML tasks</h2></div>
        ${o.tasks?.length ? `<table class="rdTable"><thead><tr><th>Task</th><th>Type</th><th>Dataset</th></tr></thead><tbody>${o.tasks.map((x) => `<tr><td><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.id)}</a></td><td>${esc(x.type)}</td><td>${esc(x.dataset)}</td></tr>`).join("")}</tbody></table>` : `<p class="fine">No tasks yet.</p>`}
      </section></div>
      <section class="panel"><div class="panelHeading"><h2>Trending models on Hugging Face</h2><a class="linkButton" href="https://huggingface.co/models?sort=trending" target="_blank" rel="noopener noreferrer">Hugging Face ↗</a></div>
        ${m.length ? `<div class="rdModels">${m.map((x) => `<a class="rdModel" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(x.id)}</b><span class="fine">${esc([x.task, x.library].filter(Boolean).join(" · ") || "model")}</span><span class="fine">♥ ${n(x.likes)} · ↓ ${n(x.downloads)}</span></a>`).join("")}</div>` : empty(src.huggingface?.pending ? "Retrieving" : "No models yet", src.huggingface?.error ? esc(src.huggingface.error) : "Refreshed every few hours.")}
        <p class="fine">Papers on the radar that are also on Hugging Face's daily papers list show their upvotes.</p></section>`;
  }
  function deadlines() {
    const d = S.data.deadlines || {};
    const up = d.upcoming || [];
    const kind = (k) => ({ deadline: "Paper deadline", "abstract deadline": "Abstract deadline", "rebuttal deadline": "Rebuttal", "decision deadline": "Decisions" })[k] || k[0].toUpperCase() + k.slice(1);
    const due = (n) => (n < 0 ? "passed" : n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);
    const status = (n) => (n <= 7 ? "now" : n <= 45 ? "soon" : "past");
    const fmt = (iso) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
    const cards = up.length
      ? `<div class="ex-grid ex-events">${up.map((m) => `<article class="ex-event"><div class="ex-topline"><span class="ex-status ${status(m.days)}">${esc(due(m.days))}</span><span>${esc(m.conference)} ${esc(m.year || "")}</span></div>
          <div class="ex-date">${esc(kind(m.kind))}</div><h3>${esc(fmt(m.at))} <small class="fine">your time</small></h3>
          <p class="ex-location">${esc(m.local)} ${esc(m.timezone)} as published${m.place ? ` · ${esc(m.place)}` : ""}</p>${m.date ? `<p>Conference: ${esc(m.date)}</p>` : ""}
          <div class="ex-link">${m.link ? `<a href="${esc(m.link)}" target="_blank" rel="noopener noreferrer">Official site ↗</a>` : ""}</div></article>`).join("")}</div>`
      : empty("No upcoming dates", "None of the tracked conferences has announced dates in the dataset yet.");
    const confs = (d.conferences || []).map((c) => `<article class="ex-portal"><strong>${esc(c.name)}</strong>
        <small>${c.milestones?.length ? `${c.milestones.length} upcoming date${c.milestones.length === 1 ? "" : "s"}` : c.note ? esc(c.note) : `Next dates not announced yet${c.latest?.year ? ` (latest listed: ${esc(c.latest.year)})` : ""}`}</small>
        ${c.latest?.date ? `<p>${esc(c.latest.date)}${c.latest.place ? ` · ${esc(c.latest.place)}` : ""}</p>` : ""}
        ${c.latest?.link ? `<a href="${esc(c.latest.link)}" target="_blank" rel="noopener noreferrer">Official site ↗</a>` : ""}</article>`).join("");
    return `<section class="panel"><div class="panelHeading"><h2>Upcoming deadlines and decisions</h2><span class="fine">Shown in your time zone; deadlines are converted from the zone each conference publishes (AoE is UTC−12).</span></div>${cards}</section>
      <section class="panel"><div class="panelHeading"><h2>Tracked conferences</h2></div><div class="ex-portalgrid">${confs}</div>
      <p class="fine">Dates from the open <a href="https://github.com/ccfddl/ccf-deadlines" target="_blank" rel="noopener noreferrer">ccf-deadlines</a> dataset, refreshed daily. Always confirm on the official site before submitting.</p></section>`;
  }
  function queue() {
    const q = S.queue;
    if (!q) return `<div class="pageLoading">Loading your reading queue…</div>`;
    if (!q.length) return empty("Your reading queue is empty", "Use “Save to reading queue” on any paper. Saved papers stay even after they leave the radar.");
    const groups = [["to read", "To read"], ["reading", "Reading"], ["read", "Read"]];
    return `<section class="panel"><div class="panelHeading"><h2>Reading queue</h2><span class="panelTools"><a class="action" href="/api/radar/bibtex" download="atlas-reading-queue.bib">Export all as BibTeX</a><button class="action" id="rdBibSel">Export selected</button></span></div>
      <p class="fine">Notes save when you click outside the box. Everything stays in your Atlas database.</p>
      ${groups.map(([k, label]) => {
        const items = q.filter((x) => x.status === k);
        if (!items.length) return "";
        return `<h3 class="rdQHead">${label} <span class="fine">${items.length}</span></h3>${items.map((x) => {
          const p = x.paper;
          return `<article class="rdQItem"><label class="rdPick"><input type="checkbox" data-rdpick="${esc(x.id)}" aria-label="Select for export"></label>
            <div><h3><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.title)}</a></h3>
            <p class="rdAuthors">${authors((p.authors || []).slice(0, 8), Math.max(0, (p.authors || []).length - 8))}${p.published ? ` · ${esc(String(p.published).slice(0, 4))}` : ""}${p.venue ? ` · ${esc(p.venue)}` : ""}</p>
            <textarea class="rdNoteBox" data-rdnote="${esc(x.id)}" rows="2" placeholder="Notes…">${esc(x.note || "")}</textarea></div>
            <div class="rdQSide"><select data-rdstatus="${esc(x.id)}" aria-label="Reading status">${groups.map(([v, t]) => `<option value="${v}" ${x.status === v ? "selected" : ""}>${t}</option>`).join("")}</select>
            <button class="linkButton" data-rdunsave="${esc(x.id)}">Remove</button></div></article>`;
        }).join("")}`;
      }).join("")}</section>`;
  }
  function fingerprint() {
    const f = S.data.fingerprint || [];
    const st = { resolved: ["Found", "good"], pending: ["Looking up", "unknown"], not_found: ["Not found", "bad"], error: ["Lookup failed", "bad"] };
    return `<section class="panel"><div class="panelHeading"><h2>Your papers</h2><span class="fine">${f.filter((x) => x.status === "resolved").length} of ${f.length} found</span></div>
      <p class="fine">The radar ranks new research by similarity to these papers (title and abstract). Add drafts, preprints or papers you consider core to your area.</p>
      <div class="rdFp">${f.map((x) => {
        const [t, c] = st[x.status] || [x.status, "unknown"];
        return `<div class="rdFpRow"><span class="statusPill ${c}">${esc(t)}</span><div><b>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title || x.ref)}</a>` : esc(x.title || x.ref)}</b>
          <span class="fine">${esc(x.kind === "arxiv" ? "arXiv " + x.ref : x.kind === "doi" ? "DOI " + x.ref : "Title search")}${x.year ? ` · ${esc(x.year)}` : ""}${x.detail ? ` · ${esc(x.detail)}` : ""}</span></div>
          <button class="linkButton" data-rdfpremove="${esc(x.id)}" title="Stop matching against this paper">Remove</button></div>`;
      }).join("")}</div>
      <div class="rdFpAdd"><input id="rdFpRef" placeholder="arXiv link or ID, DOI, or exact paper title" aria-label="Paper to add"><button class="action primary" id="rdFpAdd">Add paper</button></div></section>
      ${watchPanel()}${sourcesPanel()}`;
  }

  function watchPanel() {
    const w = S.data.watch || { active: [], auto: [], added: [] };
    const chip = (t) => `<span class="rdChip ${w.added.includes(t) ? "mine" : ""}">${esc(t)}<button data-rdwatchdel="${esc(t)}" aria-label="Stop searching for ${esc(t)}" title="Stop searching for this">×</button></span>`;
    return `<section class="panel"><div class="panelHeading"><h2>Watch phrases</h2><span class="fine">${w.active.length} active</span></div>
      <p class="fine">Extracted from your papers. Atlas searches arXiv, Hugging Face and OpenAlex for these phrases every hour, newest first, then ranks what it finds by meaning. Phrases you add are outlined.</p>
      <div class="rdChips">${w.active.length ? w.active.map(chip).join("") : `<span class="fine">Phrases appear once your papers have been looked up.</span>`}</div>
      <div class="rdFpAdd"><input id="rdWatchAdd" placeholder="Add a phrase, e.g. loss landscape" aria-label="Phrase to add"><button class="action" id="rdWatchAddBtn">Add phrase</button><button class="linkButton" id="rdWatchReset">Reset to extracted</button></div></section>`;
  }
  function sourcesPanel() {
    const p = S.probe;
    return `<section class="panel"><div class="panelHeading"><h2>Sources</h2><button class="action" id="rdProbe" ${S.probing ? "disabled" : ""}>${S.probing ? "Testing…" : "Test sources"}</button></div>
      <p class="fine">All open: arXiv (daily listings and search), Hugging Face papers, OpenAlex (journals and proceedings), Crossref, OpenML and the ccf-deadlines dataset. “Test sources” sends one small request to each, from this computer.</p>
      ${p ? `<table class="rdTable rdProbeT"><tbody>${p.map((c) => `<tr><td><span class="statusPill ${c.ok ? "good" : "bad"}">${c.ok ? "Works" : "Problem"}</span></td><td><b>${esc(c.source)}</b></td><td>${esc(c.detail)}</td><td class="fine">${num(c.ms)} ms</td></tr>`).join("")}</tbody></table>` : ""}
      <div class="lmField"><label for="rdOaKey">OpenAlex API key <span class="fine">(optional, free at openalex.org; raises OpenAlex's daily allowance tenfold)</span></label>
        <div class="rdFpAdd"><input id="rdOaKey" type="password" autocomplete="off" placeholder="${S.data.openalex_key ? "A key is saved. Paste a new one to replace it" : "Paste your key"}"><button class="action" id="rdOaSave">Save key</button>${S.data.openalex_key ? `<button class="linkButton" id="rdOaClear">Remove key</button>` : ""}</div></div></section>`;
  }
  let searchSeq = 0;
  async function runSearch() {
    const seq = ++searchSeq;  // only the newest search may update the page
    S.searching = true; draw();
    const f = S.f, qs = new URLSearchParams({ q: S.q, mode: S.mode, days: S.days, lane: f.lane, cat: f.cat, min: f.min, source: f.source, saved: f.saved, hf: f.hf ? "1" : "" });
    let r;
    try { r = await A().api("/api/radar/search?" + qs.toString()); }
    catch (e) { r = { results: [], total: 0, pool: 0, mode: S.mode, note: e.message, days: S.days }; }
    if (seq !== searchSeq) return;
    S.results = r; S.searching = false; draw();
  }
  function draw() {
    const el = document.querySelector("#rdBody");
    if (!el || !S.data) return;
    bar();
    document.querySelectorAll("[data-rdtab]").forEach((b) => { b.classList.toggle("active", b.dataset.rdtab === S.tab); b.setAttribute("aria-selected", b.dataset.rdtab === S.tab); });
    const f = { foryou: forYou, lab, themes, related, bench, deadlines, queue, fingerprint }[S.tab] || forYou;
    const ta = document.querySelector("#rdText");
    if (ta) S.relatedText = ta.value;
    const active = document.activeElement?.id;
    el.innerHTML = f();
    if (active === "rdQ") { const q = document.querySelector("#rdQ"); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }
  }

  // ---------------------------------------------------------------- data
  async function load(refresh) {
    try {
      S.data = await A().api(`/api/radar?days=${S.days}${refresh ? "&refresh=1" : ""}`);
      if (S.tab === "themes" && S.themesDays !== S.days) loadThemes();
      if (S.tab === "queue" && !S.queue) loadQueue();
      if (filtering() && S.tab === "foryou" && !S.searching) runSearch();
      draw();
    } catch (e) {
      const el = document.querySelector("#rdBody");
      if (el) el.innerHTML = empty("Could not load the research radar", esc(e.message));
    }
    clearTimeout(timer);
    const busy = S.data && (Object.values(S.data.sources || {}).some((s) => s.pending) || S.data.digest?.status === "running");
    if (alive && busy) timer = setTimeout(() => load(false), 5000);
  }
  async function loadThemes() {
    const days = S.days;
    try { S.themes = await A().api(`/api/radar/themes?days=${days}`); S.themesDays = days; }
    catch (e) { S.themes = { themes: [], note: e.message, papers: 0 }; S.themesDays = days; }
    if (S.tab === "themes") draw();
  }
  async function loadQueue() {
    try { S.queue = (await A().api("/api/radar/queue")).queue; } catch (e) { A().tip(e.message); S.queue = []; }
    if (S.tab === "queue") draw();
  }
  function setQueue(q) {
    S.queue = q;
    S.data.queue = Object.fromEntries(q.map((x) => [x.id, x.status]));
  }

  function onClick(ev) {
    const b = ev.target.closest("[data-rdtab],#rdRefresh,#rdDigest,[data-rdsave],[data-rdunsave],#rdFind,#rdClear,#rdBibSel,#rdFpAdd,[data-rdfpremove],[data-rdmode],#rdGo,#rdClearSearch,[data-rdwatchdel],#rdWatchAddBtn,#rdWatchReset,#rdProbe,#rdOaSave,#rdOaClear");
    if (!b) return false;
    (async () => {
      try {
        if (b.dataset.rdmode) {
          S.mode = b.dataset.rdmode;
          if (S.q.trim()) await runSearch(); else draw();
        } else if (b.id === "rdGo") {
          S.q = document.querySelector("#rdQ")?.value || "";
          if (filtering()) await runSearch(); else { S.results = null; draw(); }
        } else if (b.id === "rdClearSearch") {
          S.q = ""; S.f = { lane: "", cat: "", min: "", source: "", saved: "", hf: false }; S.results = null; draw();
        } else if (b.dataset.rdwatchdel || b.id === "rdWatchAddBtn" || b.id === "rdWatchReset") {
          const body = b.id === "rdWatchReset" ? { action: "reset" } : b.id === "rdWatchAddBtn" ? { action: "add", phrase: document.querySelector("#rdWatchAdd")?.value || "" } : { action: "remove", phrase: b.dataset.rdwatchdel };
          S.data.watch = (await A().api("/api/radar/watch", "POST", body)).watch;
          if (body.action !== "remove") A().tip("Searching for the updated phrases in the background.");
          draw();
        } else if (b.id === "rdProbe") {
          S.probing = true; draw();
          try { S.probe = (await A().api("/api/radar/probe", "POST", {})).checks; } finally { S.probing = false; }
          draw();
        } else if (b.id === "rdOaSave" || b.id === "rdOaClear") {
          const key = b.id === "rdOaClear" ? "" : (document.querySelector("#rdOaKey")?.value || "").trim();
          if (b.id === "rdOaSave" && !key) return A().tip("Paste a key first.");
          S.data.openalex_key = (await A().api("/api/radar/settings", "POST", { openalex_key: key })).openalex_key;
          A().tip(key ? "OpenAlex key saved on this computer." : "OpenAlex key removed.");
          draw();
        } else if (b.dataset.rdtab) {
          S.tab = b.dataset.rdtab;
          if (S.tab === "themes" && S.themesDays !== S.days) loadThemes();
          if (S.tab === "queue") loadQueue();
          draw();
        } else if (b.id === "rdRefresh") {
          A().tip("Fetching again from every source in the background.");
          S.themes = null; S.themesDays = null;
          await load(true);
        } else if (b.id === "rdDigest") {
          await A().api("/api/radar/digest", "POST", {});
          A().tip("Writing the digest with your local model. This can take a minute on a laptop processor.");
          await load(false);
        } else if (b.dataset.rdsave) {
          const p = index().get(b.dataset.rdsave);
          if (!p) return;
          setQueue((await A().api("/api/radar/queue", "POST", { action: "add", paper: p })).queue);
          A().tip("Saved to your reading queue.");
          draw();
        } else if (b.dataset.rdunsave) {
          setQueue((await A().api("/api/radar/queue", "POST", { action: "remove", id: b.dataset.rdunsave })).queue);
          draw();
        } else if (b.id === "rdFind") {
          S.relatedText = document.querySelector("#rdText")?.value || "";
          S.busy = true; draw();
          try { S.related = await A().api("/api/radar/related", "POST", { text: S.relatedText }); }
          finally { S.busy = false; }
          draw();
        } else if (b.id === "rdClear") {
          S.related = null; S.relatedText = ""; draw();
        } else if (b.id === "rdBibSel") {
          const ids = [...document.querySelectorAll("[data-rdpick]:checked")].map((x) => x.dataset.rdpick);
          if (!ids.length) return A().tip("Tick the papers to export first.");
          const a = document.createElement("a");
          a.href = "/api/radar/bibtex?ids=" + encodeURIComponent(ids.join(","));
          a.download = "atlas-selection.bib";
          document.body.appendChild(a); a.click(); a.remove();
        } else if (b.id === "rdFpAdd") {
          const ref = document.querySelector("#rdFpRef")?.value || "";
          const r = await A().api("/api/radar/fingerprint", "POST", { action: "add", ref });
          S.data.fingerprint = r.fingerprint;
          A().tip("Looking the paper up in the background.");
          draw(); setTimeout(() => load(false), 2500);
        } else if (b.dataset.rdfpremove) {
          const r = await A().api("/api/radar/fingerprint", "POST", { action: "remove", id: b.dataset.rdfpremove });
          S.data.fingerprint = r.fingerprint;
          draw(); setTimeout(() => load(false), 800);
        }
      } catch (e) { S.busy = false; A().tip(e.message); draw(); }
    })();
    return true;
  }
  function onChange(e) {
    const t = e.target;
    if (t.id === "rdDays") { S.days = Number(t.value) || 7; S.themes = null; load(false); return true; }
    if (t.dataset.rdf) {
      S.f[t.dataset.rdf] = t.type === "checkbox" ? t.checked : t.value;
      S.q = document.querySelector("#rdQ")?.value || S.q;
      if (filtering()) runSearch(); else { S.results = null; draw(); }
      return true;
    }
    if (t.dataset.rdstatus) {
      A().api("/api/radar/queue", "POST", { action: "update", id: t.dataset.rdstatus, status: t.value }).then((r) => { setQueue(r.queue); draw(); }).catch((x) => A().tip(x.message));
      return true;
    }
    if (t.dataset.rdnote) {
      A().api("/api/radar/queue", "POST", { action: "update", id: t.dataset.rdnote, note: t.value }).then((r) => { setQueue(r.queue); A().tip("Note saved."); }).catch((x) => A().tip(x.message));
      return true;
    }
    return !!t.dataset.rdpick || ["rdText", "rdFpRef", "rdQ", "rdWatchAdd", "rdOaKey"].includes(t.id);
  }
  function onKey(e) {
    if (e.key === "Enter" && e.target.id === "rdFpRef") { e.preventDefault(); document.querySelector("#rdFpAdd")?.click(); return true; }
    if (e.key === "Enter" && e.target.id === "rdQ") { e.preventDefault(); document.querySelector("#rdGo")?.click(); return true; }
    if (e.key === "Enter" && e.target.id === "rdWatchAdd") { e.preventDefault(); document.querySelector("#rdWatchAddBtn")?.click(); return true; }
    if (e.key === "Escape" && e.target.id === "rdQ" && S.q) { e.preventDefault(); document.querySelector("#rdClearSearch")?.click(); return true; }
    return false;
  }
  const onWall = () => { if (alive) draw(); };
  function mount() { alive = true; document.addEventListener("atlas:wall", onWall); load(false); }
  function destroy() { alive = false; clearTimeout(timer); document.removeEventListener("atlas:wall", onWall); }
  return { layout, mount, destroy, onClick, onChange, onKey };
})();
