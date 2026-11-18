"use strict";
/* Atlas v5.5 · Coverage graph.
   Overview: sources on this page as nodes. Solid lines = shared stories (co-coverage),
   dashed lines = similar topics (article-level matching by meaning). Click a source to see
   its stories and their articles. Diffuse spreads outward from one article: its story and
   sources, then related stories on any desk, and outlets that have not covered it yet. */
window.ATLASGraph = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  const S = { key: "", data: null, pos: null, busy: false, edge: "both", sel: "", openStory: "", hover: "",
    view: null, // overlay: { mode: "overview" | "diffuse", seed, data, desk, busy, msg, openStory, sel }
  };
  let reqSeq = 0;

  // ---------------------------------------------------------------- helpers
  const css = (v, f) => getComputedStyle(document.documentElement).getPropertyValue(v).trim() || f;
  const COL = () => ({ left: css("--left", "#5d8ff0"), center: css("--center", "#d6dee2"), right: css("--right", "#e5625f"),
    none: css("--muted", "#7d97a3"), ink: css("--ink", "#e8f1f4"), ink2: css("--ink-2", "#b8cbd2"), line: "rgba(190,228,240,.18)",
    glacier: css("--glacier", "#8fd9e8"), amber: css("--amber", "#f0b45a"), mint: css("--mint", "#6fd6a6"), coral: css("--coral", "#f06a5b") });
  const leanCol = (l, c) => (l == null ? c.none : l < 0 ? c.left : l > 0 ? c.right : c.center);
  const entries = () => {
    const m = new Map();
    for (const e of A().state.state?.entries || []) m.set(e.id, e);
    return m;
  };
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return (h >>> 0) / 4294967295; }
  function wrap(ctx, text, max) {
    const words = String(text).split(/\s+/), lines = [];
    let cur = "";
    for (const w of words) { const t = cur ? cur + " " + w : w; if (ctx.measureText(t).width > max && cur) { lines.push(cur); cur = w; } else cur = t; }
    if (cur) lines.push(cur);
    return lines.slice(0, 3).map((l, i, a) => (i === 2 && a.length === 3 && words.length > 0 ? l : l));
  }

  // ---------------------------------------------------------------- overview layout (seeded, stable)
  function layout(d) {
    const n = d.nodes.length, P = d.nodes.map((x) => ({ x: hash(x.id) - 0.5, y: hash(x.id + "y") - 0.5, vx: 0, vy: 0 }));
    const ix = new Map(d.nodes.map((x, i) => [x.id, i]));
    const springs = d.edges.map((e) => [ix.get(e.a), ix.get(e.b), Math.max(e.co, e.topic * 0.7)]);
    for (let it = 0; it < 320; it++) {
      const t = 1 - it / 320;
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        let dx = P[i].x - P[j].x, dy = P[i].y - P[j].y, d2 = dx * dx + dy * dy + 1e-4;
        const f = 0.0016 / d2; P[i].vx += dx * f; P[i].vy += dy * f; P[j].vx -= dx * f; P[j].vy -= dy * f;
      }
      for (const [a, b, w] of springs) {
        const dx = P[b].x - P[a].x, dy = P[b].y - P[a].y, dist = Math.hypot(dx, dy) || 1e-3;
        const f = (dist - (0.32 - 0.22 * w)) * 0.05 * (0.4 + w);
        P[a].vx += (dx / dist) * f; P[a].vy += (dy / dist) * f; P[b].vx -= (dx / dist) * f; P[b].vy -= (dy / dist) * f;
      }
      for (const p of P) { p.vx -= p.x * 0.01; p.vy -= p.y * 0.01; p.x += p.vx * t; p.y += p.vy * t; p.vx *= 0.6; p.vy *= 0.6; }
    }
    const xs = P.map((p) => p.x), ys = P.map((p) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    return new Map(d.nodes.map((x, i) => [x.id, { x: (P[i].x - x0) / (x1 - x0 || 1), y: (P[i].y - y0) / (y1 - y0 || 1) }]));
  }

  // ---------------------------------------------------------------- canvas
  function setup(canvas) {
    const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(10, r.width * dpr); canvas.height = Math.max(10, r.height * dpr);
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w: r.width, h: r.height };
  }
  const radius = (n) => Math.min(22, 4 + Math.sqrt(n.articles) * 2.6);

  function drawOverview(canvas, d, pos, opts) {
    const { ctx, w, h } = setup(canvas), c = COL(), pad = 34;
    const P = (id) => { const p = pos.get(id); return [pad + p.x * (w - 2 * pad), pad + p.y * (h - 2 * pad)]; };
    ctx.clearRect(0, 0, w, h);
    const sel = opts.sel, hov = opts.hover;
    const touches = (e) => !sel || e.a === sel || e.b === sel;
    for (const e of d.edges) {
      const [ax, ay] = P(e.a), [bx, by] = P(e.b), dim = touches(e) ? 1 : 0.18;
      if ((S.edge === "both" || S.edge === "topic") && e.topic > 0.3) {
        ctx.setLineDash([3, 4]); ctx.strokeStyle = `rgba(143,217,232,${(0.15 + 0.5 * e.topic) * dim})`; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
      }
      if ((S.edge === "both" || S.edge === "co") && e.shared) {
        ctx.strokeStyle = `rgba(232,241,244,${(0.25 + 0.6 * e.co) * dim})`; ctx.lineWidth = 0.6 + 3.2 * e.co;
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      }
    }
    const labelled = new Set([...d.nodes].sort((a, b) => b.articles - a.articles).slice(0, opts.labels || 8).map((n) => n.id));
    if (sel) labelled.add(sel);
    if (hov) labelled.add(hov);
    ctx.font = "12px " + css("--font-sans", "system-ui");
    for (const n of d.nodes) {
      const [x, y] = P(n.id), r = radius(n);
      const near = !sel || n.id === sel || d.edges.some((e) => (e.a === sel && e.b === n.id) || (e.b === sel && e.a === n.id));
      ctx.globalAlpha = near ? 1 : 0.3;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = leanCol(n.lean, c); ctx.fill();
      if (n.primary) { ctx.lineWidth = 2; ctx.strokeStyle = c.amber; ctx.stroke(); }
      if (n.id === sel || n.id === hov) { ctx.lineWidth = 2; ctx.strokeStyle = c.glacier; ctx.beginPath(); ctx.arc(x, y, r + 3, 0, Math.PI * 2); ctx.stroke(); }
      if (labelled.has(n.id)) {
        ctx.fillStyle = c.ink; ctx.textAlign = "center";
        ctx.fillText(n.name.length > 22 ? n.name.slice(0, 21) + "…" : n.name, x, y + r + 13);
      }
      ctx.globalAlpha = 1;
    }
    canvas._hit = (mx, my) => d.nodes.find((n) => { const [x, y] = P(n.id); return Math.hypot(mx - x, my - y) <= radius(n) + 3; });
  }

  function drawDiffusion(canvas, v) {
    const { ctx, w, h } = setup(canvas), c = COL(), d = v.data;
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 30;
    const nodes = [], edges = [];
    const seed = { id: "story:" + d.seed_story.id, kind: "seed", x: cx, y: cy, r: 30, label: d.seed_story.title, story: d.seed_story };
    nodes.push(seed);
    const ring1 = [...d.seed_story.sources.map((h) => ({ h, gap: false })), ...d.gaps.map((g) => ({ h: g.id, gap: true }))];
    const srcInfo = new Map([...d.sources, ...d.gaps].map((s) => [s.id, s]));
    ring1.forEach((s, i) => {
      const a = (i / Math.max(1, ring1.length)) * Math.PI * 2 - Math.PI / 2;
      const info = srcInfo.get(s.h) || { id: s.h, name: s.h };
      const n = { id: "src:" + s.h, host: s.h, kind: s.gap ? "gap" : "source", x: cx + Math.cos(a) * R * 0.42, y: cy + Math.sin(a) * R * 0.42, r: 7, label: info.name, lean: info.lean };
      nodes.push(n); edges.push([seed, n, s.gap ? 0 : 1, s.gap]);
    });
    const outer = [...d.related.map((st) => ({ st, via: false })), ...(d.via_sources || []).map((st) => ({ st, via: true }))];
    const maxScore = Math.max(...outer.map((o) => o.st.score), 1e-9);
    const placed = new Map(nodes.filter((n) => n.host).map((n) => [n.host, n]));
    outer.forEach(({ st, via }, i) => {
      const a = (i / Math.max(1, outer.length)) * Math.PI * 2 - Math.PI / 2 + Math.PI / Math.max(2, outer.length);
      const n = { id: "story:" + st.id, kind: via ? "via" : "related", x: cx + Math.cos(a) * R * 0.86, y: cy + Math.sin(a) * R * 0.86, r: via ? 5 : 6 + 10 * (st.score / maxScore), label: st.title, story: st };
      nodes.push(n); edges.push([seed, n, st.score / maxScore, false]);
      for (const hst of st.sources) { const s = placed.get(hst); if (s) edges.push([n, s, 0.15, false]); }
    });
    for (const [a, b, wgt, dashed] of edges) {
      ctx.setLineDash(dashed ? [3, 4] : []);
      const story = a.kind === "seed" && b.kind === "related";
      if (a.kind === "seed" && b.kind === "via") { ctx.setLineDash([2, 5]); ctx.strokeStyle = "rgba(125,151,163,.35)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.setLineDash([]); continue; }
      ctx.strokeStyle = story ? `rgba(240,180,90,${0.2 + 0.7 * wgt})` : dashed ? "rgba(125,151,163,.6)" : `rgba(190,228,240,${0.12 + 0.4 * wgt})`;
      ctx.lineWidth = story ? 1 + 3 * wgt : 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.font = "12px " + css("--font-sans", "system-ui");
    for (const n of nodes) {
      const active = v.openStory && n.story && n.story.id === v.openStory, selSrc = v.sel && n.host === v.sel;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      if (n.kind === "seed") { ctx.fillStyle = "rgba(240,180,90,.22)"; ctx.fill(); ctx.strokeStyle = c.amber; ctx.lineWidth = 2; ctx.stroke(); }
      else if (n.kind === "related") { ctx.fillStyle = active ? "rgba(178,160,240,.55)" : "rgba(178,160,240,.28)"; ctx.fill(); ctx.strokeStyle = "rgba(178,160,240,.9)"; ctx.lineWidth = active ? 2 : 1; ctx.stroke(); }
      else if (n.kind === "via") { ctx.fillStyle = "rgba(125,151,163,.25)"; ctx.fill(); ctx.strokeStyle = "rgba(125,151,163,.7)"; ctx.lineWidth = 1; ctx.stroke(); }
      else if (n.kind === "gap") { ctx.setLineDash([3, 3]); ctx.strokeStyle = c.none; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]); }
      else { ctx.fillStyle = leanCol(n.lean, c); ctx.fill(); }
      if (selSrc) { ctx.strokeStyle = c.glacier; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 3, 0, Math.PI * 2); ctx.stroke(); }
      ctx.fillStyle = n.kind === "gap" ? c.none : c.ink; ctx.textAlign = "center";
      if (n.kind === "seed") { wrap(ctx, n.label, 170).forEach((l, i) => ctx.fillText(l, n.x, n.y + n.r + 14 + i * 14)); }
      else if (n.kind === "related" || n.kind === "via") { ctx.fillStyle = n.kind === "via" ? c.none : c.ink; const l = wrap(ctx, n.label, 130); l.slice(0, 2).forEach((t, i) => ctx.fillText(i === 1 && l.length > 2 ? t + "…" : t, n.x, n.y + n.r + 13 + i * 13)); }
      else ctx.fillText(n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label, n.x, n.y + n.r + 12);
    }
    canvas._hit = (mx, my) => nodes.find((n) => Math.hypot(mx - n.x, my - n.y) <= n.r + 4);
  }

  // ---------------------------------------------------------------- panel (on the page)
  function legend() {
    return `<div class="cgLegend"><span><i class="cgDot l"></i>Left</span><span><i class="cgDot c"></i>Centre</span><span><i class="cgDot r"></i>Right</span><span><i class="cgDot n"></i>Not rated</span><span><i class="cgRing"></i>Primary</span>
      <span><i class="cgLine solid"></i>Shared stories</span><span><i class="cgLine dash"></i>Similar topics</span></div>`;
  }
  function edgeSwitch() {
    return `<div class="cgSwitch" role="radiogroup" aria-label="Lines">${[["both", "Both"], ["co", "Shared stories"], ["topic", "Similar topics"]].map(([k, t]) => `<button class="${S.edge === k ? "on" : ""}" data-cgedge="${k}" role="radio" aria-checked="${S.edge === k}">${t}</button>`).join("")}</div>`;
  }
  function storyList(stories, host, openStory, max = 6) {
    const E = entries();
    if (!stories.length) return `<p class="fine">No stories.</p>`;
    return `<ul class="cgStories">${stories.slice(0, max).map((st) => {
      const open = openStory === st.id;
      const arts = (st.articles || []).map((id) => E.get(id)).filter(Boolean);
      return `<li class="${open ? "open" : ""}"><button class="cgStory" data-cgstory="${esc(st.id)}" aria-expanded="${open}"><span>${esc(st.title)}</span><small>${num(st.sources?.length || 0)} sources · ${num(arts.length || st.articles?.length || 0)} articles</small></button>
        ${open ? `<ul class="cgArts">${arts.map((e) => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a><span class="fine">${esc((A().state.state?.publishers?.[e.publisher] || {}).name || e.source)}</span><button class="linkButton" data-diffuse="${esc(e.id)}">Diffuse</button></li>`).join("")}</ul>` : ""}</li>`;
    }).join("")}</ul>`;
  }
  function info() {
    const d = S.data;
    if (!d) return "";
    if (!S.sel) return `<p class="fine cgHint">${esc(d.note)} ${num(d.nodes.length)} sources, ${num(d.articles)} articles. Click a source to see its stories; use Diffuse on any article to spread outward.</p>`;
    const n = d.nodes.find((x) => x.id === S.sel);
    if (!n) return "";
    const mine = Object.values(d.stories).filter((st) => st.sources.includes(n.id)).sort((a, b) => b.sources.length - a.sources.length);
    const partners = d.edges.filter((e) => e.a === n.id || e.b === n.id).map((e) => ({ id: e.a === n.id ? e.b : e.a, e }))
      .sort((a, b) => b.e.co + b.e.topic - (a.e.co + a.e.topic)).slice(0, 4).map((p) => d.nodes.find((x) => x.id === p.id)?.name).filter(Boolean);
    return `<div class="cgSel"><div class="cgSelHead"><b>${esc(n.name)}</b><span class="fine">${num(n.articles)} articles · ${num(n.stories)} stories${partners.length ? ` · closest: ${esc(partners.join(", "))}` : ""}</span></div>
      <div class="cgSelActions"><button class="linkButton" data-pubonly="${esc(n.id)}">Show only this source</button><button class="linkButton" data-pubtoggle="${esc(n.id)}">${A().state.pubFilters.includes(n.id) ? "Remove from selection" : "Add to selection"}</button><button class="linkButton" data-cgsel="">Clear</button></div>
      ${storyList(mine, n.id, S.openStory)}</div>`;
  }
  function panelHtml() {
    if (!S.data) return `<p class="fine">Mapping sources…</p>`;
    if (!S.data.nodes.length) return `<p class="fine">${esc(S.data.note || "No sources on this page yet.")}</p>`;
    return `${edgeSwitch()}<canvas class="cgCanvas" id="cgCanvas" aria-label="Graph of sources on this page" role="img"></canvas>${legend()}<div id="cgInfo">${info()}</div>`;
  }
  function drawPanel() {
    const host = document.querySelector("#cgHost");
    if (!host) return;
    host.innerHTML = panelHtml();
    const cv = host.querySelector("#cgCanvas");
    if (cv && S.data) { drawOverview(cv, S.data, S.pos, { sel: S.sel, hover: S.hover }); bindCanvas(cv, "panel"); }
  }
  function redrawPanelCanvas() {
    const cv = document.querySelector("#cgCanvas");
    if (cv && S.data) drawOverview(cv, S.data, S.pos, { sel: S.sel, hover: S.hover });
  }
  function bindCanvas(cv, where) {
    const xy = (ev) => { const r = cv.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    cv.onmousemove = (ev) => {
      const n = cv._hit?.(...xy(ev));
      cv.style.cursor = n ? "pointer" : "default";
      cv.title = n ? (n.name ? `${n.name}: ${n.articles} articles, ${n.stories} stories` : n.label || "") : "";
      if (where === "panel" || where === "overlay") {
        const id = n?.id || "";
        if (id !== S.hover) { S.hover = id; where === "panel" ? redrawPanelCanvas() : drawOverlayCanvas(); }
      }
    };
    cv.onclick = (ev) => {
      const n = cv._hit?.(...xy(ev));
      if (where === "diffuse") {
        if (!n) return;
        if (n.story) S.view.openStory = S.view.openStory === n.story.id ? "" : n.story.id;
        else if (n.host) S.view.sel = S.view.sel === n.host ? "" : n.host;
        drawOverlay();
        return;
      }
      S.sel = n ? (S.sel === n.id ? "" : n.id) : "";
      S.openStory = "";
      where === "panel" ? drawPanel() : drawOverlay();
    };
  }

  async function attach(ROOT) {
    const ids = ROOT.graphIds || [];
    const key = ids.length + ":" + ids.slice(0, 50).join(",") + ":" + ids.length;
    if (key === S.key && S.data) { drawPanel(); return; }
    S.key = key; S.sel = ""; S.openStory = "";
    if (!ids.length) { S.data = { nodes: [], edges: [], stories: {}, note: "No articles on this page yet." }; drawPanel(); return; }
    const seq = ++reqSeq;
    drawPanel();
    try {
      const d = await A().api("/api/graph", "POST", { ids: ids.slice(0, 600) });
      if (seq !== reqSeq) return;
      S.data = d; S.pos = layout(d);
    } catch (e) {
      if (seq !== reqSeq) return;
      S.data = { nodes: [], edges: [], stories: {}, note: "Could not map sources: " + e.message };
    }
    drawPanel();
    if (S.view?.mode === "overview") drawOverlay();
  }

  // ---------------------------------------------------------------- overlay (expanded view and diffusion)
  function overlayEl() {
    let el = document.querySelector("#cgOverlay");
    if (!el) {
      el = document.createElement("div");
      el.id = "cgOverlay"; el.className = "cgOverlay"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
      document.body.appendChild(el);
    }
    return el;
  }
  function close() {
    S.view = null;
    document.querySelector("#cgOverlay")?.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  function onKey(e) { if (e.key === "Escape") { e.stopPropagation(); close(); } }
  function drawOverlayCanvas() {
    const cv = document.querySelector("#cgBig");
    if (!cv || !S.view) return;
    if (S.view.mode === "diffuse" && S.view.data) drawDiffusion(cv, S.view);
    else if (S.view.mode === "overview" && S.data) drawOverview(cv, S.data, S.pos, { sel: S.sel, hover: S.hover, labels: 18 });
  }
  function diffusionSide() {
    const v = S.view, d = v.data, E = entries();
    if (v.busy && !d) return `<div class="pageLoading">Spreading out from this article…</div>`;
    if (v.error) return `<div class="empty"><b>Could not diffuse</b><span class="fine">${esc(v.error)}</span></div>`;
    const deskOf = (id) => { const e = E.get(id); return e && A().desk ? A().desk(e) : ""; };
    const desks = (st) => [...new Set(st.articles.map(deskOf).filter(Boolean))];
    const srcName = (h) => [...d.sources, ...d.gaps].find((s) => s.id === h)?.name || A().state.state?.publishers?.[h]?.name || h;
    const sel = v.sel ? `<div class="cgSel"><div class="cgSelHead"><b>${esc(srcName(v.sel))}</b><span class="fine">${d.gaps.some((g) => g.id === v.sel) ? "Has not covered this story yet" : "In this neighbourhood"}</span></div>
        <div class="cgSelActions"><button class="linkButton" data-pubonly="${esc(v.sel)}">Show only this source on the page</button><button class="linkButton" data-cgdsel="">Clear</button></div>
        ${storyList([d.seed_story, ...d.related, ...(d.via_sources || [])].filter((st) => st.sources.includes(v.sel)), v.sel, v.openStory)}</div>` : "";
    return `${sel}
      <section><h3>This story <span class="fine">${num(d.seed_story.articles.length)} articles from ${num(d.seed_story.sources.length)} sources</span></h3>${storyList([d.seed_story], "", v.openStory)}</section>
      <section><h3>Related stories <span class="fine">across desks, closest first</span></h3>${d.related.length ? `<ul class="cgStories">${d.related.map((st) => {
        const open = v.openStory === st.id, arts = st.articles.map((id) => E.get(id)).filter(Boolean);
        return `<li class="${open ? "open" : ""}"><button class="cgStory" data-cgstory="${esc(st.id)}" aria-expanded="${open}"><span>${esc(st.title)}</span><small>${desks(st).map((x) => `<em class="cgDesk">${esc(x)}</em>`).join("")} ${num(st.sources.length)} sources · ${Math.round(100 * Math.max(0, st.similarity))}% similar</small></button>
          ${open ? `<ul class="cgArts">${arts.map((e) => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a><span class="fine">${esc(srcName(e.publisher))}</span><button class="linkButton" data-diffuse="${esc(e.id)}">Diffuse from here</button></li>`).join("")}</ul>` : ""}</li>`;
      }).join("")}</ul>` : `<p class="fine">No closely related stories in the last ${d.days} days.</p>`}</section>
      ${(d.via_sources || []).length ? `<section><h3>Also from these outlets <span class="fine">reached through shared sources, not similar in meaning</span></h3>${storyList(d.via_sources, "", v.openStory, 6)}</section>` : ""}
      <section><h3>Not covering this yet</h3>${d.gaps.length ? `<p class="fine">Outlets that usually cover this kind of story but have not covered this one in Atlas.</p><div class="cgGaps">${d.gaps.map((g) => `<button class="cgGap" data-cgdsel="${esc(g.id)}">${esc(g.name)}</button>`).join("")}</div>` : `<p class="fine">Every outlet that usually covers this kind of story already has it.</p>`}
        <div class="cgFurther"><button class="action primary" id="cgFurther" ${v.busy ? "disabled" : ""}>${v.busy ? "Searching…" : "Search further"}</button><span class="fine">Searches Google News for <b>${esc(d.terms.join(", "))}</b>${d.gaps.length ? `, including ${esc(d.gaps.slice(0, 3).map((g) => g.name).join(", "))}` : ""}. New articles join the ${esc(v.desk)} desk.</span></div>
        ${v.msg ? `<p class="fine cgMsg">${esc(v.msg)}</p>` : ""}</section>`;
  }
  function drawOverlay() {
    const v = S.view;
    if (!v) return;
    const el = overlayEl();
    const title = v.mode === "diffuse" ? "Diffusion from one article" : "Coverage graph";
    const sub = v.mode === "diffuse" ? (v.data ? `${esc(v.data.note)} Searched ${num(v.data.pool)} articles from the last ${v.data.days} days.` : "") : esc(S.data?.note || "");
    el.innerHTML = `<div class="cgDialog"><header class="cgHead"><div><h2>${title}</h2><p class="fine">${sub}</p></div>
        ${v.mode === "overview" ? edgeSwitch() : `<div class="cgLegend"><span><i class="cgDot seed"></i>This story</span><span><i class="cgDot rel"></i>Related story</span><span><i class="cgDot via"></i>Same outlets only</span><span><i class="cgDot c"></i>Source covering it</span><span><i class="cgRing gap"></i>Not covering it</span></div>`}
        <button class="action" data-cgclose="1" aria-label="Close">Close</button></header>
      <div class="cgBody"><canvas id="cgBig" class="cgBig" role="img" aria-label="${title}"></canvas><aside class="cgSide">${v.mode === "diffuse" ? diffusionSide() : `${legend()}${info()}`}</aside></div></div>`;
    const cv = el.querySelector("#cgBig");
    drawOverlayCanvas();
    bindCanvas(cv, v.mode === "diffuse" ? "diffuse" : "overlay");
  }
  function expand() {
    S.view = { mode: "overview" };
    drawOverlay();
    document.addEventListener("keydown", onKey, true);
  }
  async function diffuse(id, desk) {
    S.view = { mode: "diffuse", seed: id, data: null, busy: true, desk: desk || A().state.graphDesk || "World", openStory: "", sel: "" };
    drawOverlay();
    document.addEventListener("keydown", onKey, true);
    try { S.view.data = await A().api("/api/graph/diffuse", "POST", { seed: id, days: 7 }); S.view.openStory = S.view.data.seed_story.id; }
    catch (e) { S.view.error = e.message; }
    S.view.busy = false;
    drawOverlay();
  }
  async function further() {
    const v = S.view;
    if (!v?.data) return;
    v.busy = true; v.msg = ""; drawOverlay();
    try {
      const r = await A().api("/api/graph/search-further", "POST", { terms: v.data.terms, gaps: v.data.gaps.map((g) => g.id), desk: v.desk });
      v.msg = r.added ? `Found ${num(r.added)} new article${r.added === 1 ? "" : "s"} (${num(r.fetched)} checked with ${num(r.queries)} searches). Updating the map…`
        : !r.fetched && r.notes?.length ? `Google News could not be reached (${r.notes.length} of ${r.queries} searches failed). Check the internet connection and try again.`
        : `No new articles: all ${num(r.fetched)} results are already in Atlas.`;
      drawOverlay();
      if (r.added) {
        await A().hydrate();
        await new Promise((ok) => setTimeout(ok, 4000)); // let the language model process the new articles
        const d = await A().api("/api/graph/diffuse", "POST", { seed: v.seed, days: 7 });
        if (S.view === v) { v.data = d; v.msg = `Added ${num(r.added)} new article${r.added === 1 ? "" : "s"} to the ${v.desk} desk.`; }
      }
    } catch (e) { v.msg = "Search further failed: " + e.message; }
    v.busy = false;
    if (S.view === v) drawOverlay();
  }

  // ---------------------------------------------------------------- events
  function onClick(b) {
    if (b.dataset.cgedge) { S.edge = b.dataset.cgedge; drawPanel(); if (S.view?.mode === "overview") drawOverlay(); return true; }
    if (b.dataset.cgexpand !== undefined) { expand(); return true; }
    if (b.dataset.cgclose !== undefined) { close(); return true; }
    if (b.dataset.cgsel !== undefined) { S.sel = b.dataset.cgsel; S.openStory = ""; drawPanel(); if (S.view?.mode === "overview") drawOverlay(); return true; }
    if (b.dataset.cgdsel !== undefined && S.view) { S.view.sel = S.view.sel === b.dataset.cgdsel ? "" : b.dataset.cgdsel; drawOverlay(); return true; }
    if (b.dataset.cgstory !== undefined) {
      if (S.view && b.closest("#cgOverlay")) {
        if (S.view.mode === "diffuse") S.view.openStory = S.view.openStory === b.dataset.cgstory ? "" : b.dataset.cgstory;
        else S.openStory = S.openStory === b.dataset.cgstory ? "" : b.dataset.cgstory;
        drawOverlay();
      } else { S.openStory = S.openStory === b.dataset.cgstory ? "" : b.dataset.cgstory; drawPanel(); }
      return true;
    }
    if (b.id === "cgFurther") { further(); return true; }
    if (b.dataset.diffuse) { diffuse(b.dataset.diffuse); return true; }
    return false;
  }
  window.addEventListener("resize", () => { redrawPanelCanvas(); drawOverlayCanvas(); });
  return { attach, diffuse, expand, close, onClick };
})();
