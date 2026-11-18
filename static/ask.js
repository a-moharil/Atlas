"use strict";
/* Atlas v5.9 · Ask drawer, reachable from every page.
   Answers come from the local Ollama model, using only articles Atlas holds (the panel
   you're on, or everything) and the open Wikipedia page. Every sentence cites its source;
   sentences without one are marked. "Open in Google AI Mode" sends the question to Google
   in a new tab instead. */
window.ATLASAsk = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const el = (s) => document.querySelector(s);
  // The panel each page asks about by default (keys of its search bar).
  const VIEW_PANEL = { room: "room", news: "desk:all", india: "desk:india", technology: "desk:Technology", finance: "desk:Finance", research: "analysis", media: "videos" };
  const S = { open: false, scope: "panel", panelKey: null, wiki: "", items: [], models: null, busy: false, timer: 0, seq: 0, live: null };

  function context() {
    const view = A().state.view;
    const key = S.panelKey || VIEW_PANEL[view];
    const p = key && window.ATLASFind?.panel?.(key);
    const wikiTitle = S.noWiki ? "" : S.wiki || (view === "wiki" ? window.ATLASWiki?.current() : "");
    return { key, p, wikiTitle, label: p ? p.label : "" };
  }
  function shell() {
    const d = document.createElement("aside");
    d.id = "askDrawer"; d.className = "askDrawer"; d.hidden = true;
    d.setAttribute("role", "dialog"); d.setAttribute("aria-label", "Ask");
    document.body.appendChild(d);
    const top = document.querySelector(".topActions");
    if (top && !el("#askOpen")) top.insertAdjacentHTML("afterbegin", `<button id="askOpen" class="action askOpen" aria-haspopup="dialog" title="Ask a question about what Atlas holds"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5h12a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 16 14.5H9l-4 3v-3H4A1.5 1.5 0 0 1 2.5 13V6A1.5 1.5 0 0 1 4 4.5z"/><path d="M8 8.2a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9v.3M10 12.6v.1"/></svg>Ask</button>`);
  }
  function draw() {
    const d = el("#askDrawer");
    if (!d) return;
    const c = context();
    const scopeText = S.scope === "panel" && c.p ? `${c.label}` : "everything Atlas holds";
    d.innerHTML = `<header class="askHead"><div><h2>Ask</h2><p class="fine">Answers from ${esc(scopeText)}${c.wikiTitle ? ` and the Wikipedia page “${esc(c.wikiTitle)}”` : ""}, written by your local model. Every sentence cites its source.</p></div>
        <button class="action" data-askclose="1" aria-label="Close">Close</button></header>
      <div class="askScope" role="radiogroup" aria-label="What to search">
        ${c.p ? `<button role="radio" aria-checked="${S.scope === "panel"}" class="${S.scope === "panel" ? "on" : ""}" data-askscope="panel">This panel</button>` : ""}
        <button role="radio" aria-checked="${S.scope !== "panel" || !c.p}" class="${S.scope !== "panel" || !c.p ? "on" : ""}" data-askscope="all">Everything in Atlas</button>
        ${c.wikiTitle ? `<span class="askChip">+ Wikipedia: ${esc(c.wikiTitle)} <button data-askclearwiki="1" aria-label="Don't use this Wikipedia page">×</button></span>` : ""}
      </div>
      <form class="askForm" onsubmit="return false"><textarea id="askQ" rows="3" placeholder="For example: what are outlets reporting about the Red Sea shipping attacks?" aria-label="Your question"></textarea>
        <div class="askActions"><button class="action primary" id="askGo" ${S.busy ? "disabled" : ""}>${S.busy ? "Writing…" : "Ask"}</button>
          <a class="linkButton" id="askGoogle" target="_blank" rel="noopener noreferrer" href="https://www.google.com/search?udm=50">Open in Google AI Mode ↗</a></div>
        <p class="fine askModel" id="askModel">${modelLine()}</p></form>
      ${S.items.length ? `<div class="askListHead"><span class="fine">${S.items.length} answer${S.items.length === 1 ? "" : "s"}</span><button class="linkButton" data-askclearall="1">Clear all answers</button></div>` : ""}<div class="askList" id="askList">${S.items.map(item).join("")}</div>`;
    syncGoogle();
  }
  function modelLine() {
    const m = S.models;
    if (!m) return "Checking Ollama…";
    if (m.status === "offline") return `Ollama isn't running, so Atlas can only list sources. ${esc(m.detail || "")}`;
    const opts = [...new Set([m.model, ...(m.models || [])])];
    return `Model <select id="askModelSel" aria-label="Local model">${opts.map((x) => `<option ${x === m.model ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>${m.status === "model_missing" ? ` <span class="askWarn">not installed: run <code>ollama pull ${esc(m.model)}</code></span>` : ""}`;
  }
  function syncGoogle() {
    const a = el("#askGoogle"), q = el("#askQ")?.value.trim();
    if (a) a.href = "https://www.google.com/search?udm=50" + (q ? "&q=" + encodeURIComponent(q) : "");
  }

  // ---------------------------------------------------------------- answers
  const citeBtn = (it, id) => `<button class="askCite ${id[0] === "W" ? "w" : ""}" data-askcite="${esc(it.n)}:${esc(id)}" title="${esc(srcTitle(it, id))}">${esc(id)}</button>`;
  function srcTitle(it, id) {
    const s = id[0] === "A" ? it.sources?.atlas?.[+id.slice(1) - 1] : it.sources?.wikipedia?.[+id.slice(1) - 1];
    return !s ? "" : id[0] === "A" ? `${s.outlet}: ${s.title}` : `Wikipedia, ${s.page} · ${s.section}`;
  }
  function withCites(it, text) {
    return esc(text).replace(/\[((?:[AW]\d{1,2})(?:\s*[,;]\s*[AW]\d{1,2})*)\]/g, (m, ids) => ids.split(/[,;]/).map((x) => citeBtn(it, x.trim())).join(""));
  }
  function item(it) {
    let body;
    if (it.status === "writing" || it.status === "starting") body = `<div class="askAnswer">${withCites(it, it.text || "")}<span class="askCaret" aria-hidden="true"></span></div>`;
    else if (it.status === "done") body = `<div class="askAnswer">${(it.sentences || []).map((s) => `<span class="${s.cites.length ? "" : "askUncited"}" ${s.cites.length ? "" : 'title="No source cited for this sentence"'}>${withCites(it, s.text)}</span> `).join("")}</div>
        ${(it.sentences || []).some((s) => !s.cites.length) ? `<p class="fine askNote">Underlined sentences cite no source. Treat them with care.</p>` : ""}`;
    else if (it.status === "no_model") body = `<p class="fine askNote">Ollama isn't available (${esc(it.error || "")}). These are the sources Atlas would have used.</p>`;
    else if (it.status === "no_sources") body = `<p class="fine askNote">Atlas holds nothing that matches this question${it.scopeLabel ? ` in ${esc(it.scopeLabel)}` : ""}. Try “Everything in Atlas”, search a desk to fetch articles from the web, or open Google AI Mode.</p>`;
    else body = `<p class="fine askNote askErr">${esc(it.error || "Something went wrong.")}</p>`;
    const a = it.sources?.atlas || [], w = it.sources?.wikipedia || [];
    const src = a.length || w.length ? `<details class="askSources" ${it.status === "no_model" ? "open" : ""}><summary>Sources: ${a.length} from Atlas${w.length ? `, ${w.length} from Wikipedia` : ""}</summary><ol>
        ${a.map((s, i) => `<li id="ask-${it.n}-A${i + 1}"><b>A${i + 1}</b> <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a><small class="fine">${esc(s.outlet)} · ${esc(A().ago(s.published))}</small></li>`).join("")}
        ${w.map((s, i) => `<li id="ask-${it.n}-W${i + 1}"><b>W${i + 1}</b> <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.page)}</a><small class="fine">Wikipedia · ${esc(s.section)}</small><span class="askPassage">${esc(s.text.slice(0, 260))}…</span></li>`).join("")}</ol></details>` : "";
    return `<article class="askItem" data-askn="${it.n}"><div class="askItemHead"><h3>${esc(it.question)}</h3><button class="askRemove" data-askremove="${it.n}" title="Remove this answer" aria-label="Remove this answer: ${esc(it.question)}">×</button></div><p class="fine askMeta">${esc(it.model || "")}${it.mode ? ` · sources found by ${it.mode === "both" ? "meaning and keywords" : "keywords"}` : ""}${it.searched ? ` in ${it.searched.toLocaleString()} articles` : ""}</p>${body}${src}</article>`;
  }
  async function ask() {
    const q = el("#askQ")?.value.trim();
    if (!q || S.busy) return;
    const c = context();
    const it = { n: ++S.seq, question: q, status: "starting", text: "", scopeLabel: S.scope === "panel" && c.p ? c.label : "" };
    S.items.unshift(it); S.busy = true; draw();
    try {
      const body = { question: q, wiki: c.wikiTitle || "" };
      if (S.scope === "panel" && c.p) body.ids = c.p.ids();
      const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(90000) });
      const d = await res.json();
      if (!res.ok) throw Error(d.error || `HTTP ${res.status}`);
      Object.assign(it, { status: d.status, sources: d.sources, mode: d.mode, model: d.model, searched: d.searched, error: d.error || d.wiki_note || "" });
      if (!S.items.includes(it)) { S.busy = false; return; } // removed while waiting
      if (d.status === "writing") { S.live = it; poll(it, d.job); }
      else S.busy = false;
    } catch (e) { it.status = "error"; it.error = e.message; S.busy = false; }
    draw();
  }
  function poll(it, job) {
    clearTimeout(S.timer);
    S.timer = setTimeout(async () => {
      try {
        const j = await A().api(`/api/ask/job/${job}`);
        it.text = j.text; it.status = j.status === "error" ? "error" : j.status; it.error = j.error; it.sentences = j.sentences;
        if (!S.items.includes(it)) return; // removed while writing
        if (j.status === "writing") poll(it, job); else { S.busy = false; S.live = null; }
      } catch (e) { it.status = "error"; it.error = e.message; S.busy = false; }
      const list = el("#askList");
      if (list && S.items.includes(it)) { list.innerHTML = S.items.map(item).join(""); const b = el("#askGo"); if (b) { b.disabled = S.busy; b.textContent = S.busy ? "Writing…" : "Ask"; } }
    }, 450);
  }
  async function loadModels() {
    try { S.models = await A().api("/api/ask/models"); } catch (e) { S.models = { status: "offline", detail: e.message }; }
    const m = el("#askModel");
    if (m) m.innerHTML = modelLine();
  }

  // Removing an answer that is still being written stops following it (the local model
  // finishes in the background; its text is simply not shown).
  function stopLive(it) {
    if (S.live && (!it || S.live === it)) { clearTimeout(S.timer); S.live = null; S.busy = false; }
  }
  function remove(n) {
    const it = S.items.find((x) => x.n === n);
    if (!it) return;
    stopLive(it);
    if (S.busy && it.status === "starting") S.busy = false;
    S.items = S.items.filter((x) => x !== it);
    draw();
    el("#askQ")?.focus();
  }
  function clearAll() {
    stopLive();
    S.busy = false;
    S.items = [];
    draw();
    el("#askQ")?.focus();
  }

  // ---------------------------------------------------------------- open/close and events
  function open(opts = {}) {
    if (!el("#askDrawer")) shell();
    if (opts.panel) { S.panelKey = opts.panel; S.scope = "panel"; } else if (!opts.keepPanel) S.panelKey = null;
    S.noWiki = false;
    if (opts.wiki) S.wiki = opts.wiki;
    S.open = true;
    const d = el("#askDrawer");
    d.hidden = false;
    document.body.classList.add("askIsOpen");
    draw();
    loadModels();
    setTimeout(() => el("#askQ")?.focus(), 30);
  }
  function close() {
    S.open = false; S.wiki = "";
    const d = el("#askDrawer");
    if (d) d.hidden = true;
    document.body.classList.remove("askIsOpen");
    el("#askOpen")?.focus();
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#askOpen,[data-askpanel],[data-askclose],[data-askscope],[data-askclearwiki],#askGo,[data-askcite],[data-askremove],[data-askclearall]");
    if (!b) return;
    if (b.id === "askOpen") return S.open ? close() : open();
    if (b.dataset.askpanel) return open({ panel: b.dataset.askpanel });
    if (b.dataset.askclose) return close();
    if (b.dataset.askscope) { S.scope = b.dataset.askscope; return draw(); }
    if (b.dataset.askclearwiki) { S.wiki = ""; S.noWiki = true; return draw(); }
    if (b.id === "askGo") return ask();
    if (b.dataset.askremove) return remove(Number(b.dataset.askremove));
    if (b.dataset.askclearall) return clearAll();
    if (b.dataset.askcite) {
      const [n, id] = b.dataset.askcite.split(":");
      const li = el(`#ask-${n}-${id}`);
      if (li) { li.closest("details").open = true; li.scrollIntoView({ block: "nearest", behavior: "smooth" }); li.classList.add("flash"); setTimeout(() => li.classList.remove("flash"), 1200); }
    }
  });
  document.addEventListener("input", (e) => { if (e.target.id === "askQ") syncGoogle(); });
  document.addEventListener("keydown", (e) => {
    if (e.target.id === "askQ" && e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(); }
    if (e.key === "Escape" && S.open && e.target.closest?.("#askDrawer")) close();
  });
  document.addEventListener("change", async (e) => {
    if (e.target.id !== "askModelSel") return;
    try { await A().api("/api/ask/settings", "POST", { model: e.target.value }); } catch (err) { A().tip(err.message); }
    loadModels();
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", shell); else shell();
  return { open, close };
})();
