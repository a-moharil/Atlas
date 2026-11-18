"use strict";
/* Sanjaya v5.6 · Coverage graph.
   Overview: sources on this page as nodes. Solid lines = shared stories (co-coverage),
   dashed lines = similar topics (article-level matching by meaning). Click a source to see
   its stories and their articles. Diffuse spreads outward from one article: its story and
   sources, then related stories on any desk, and outlets that have not covered it yet.
   v5.6: the diffusion view is a story map (distance = difference in meaning, quarter = desk),
   a "who covered what" table grouped by lean, and a timeline tab. */
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
    const minor = (n) => n.lean == null && !n.primary && (n.kind === "unclassified" || !n.kind);
    ctx.font = "12px " + css("--font-sans", "system-ui");
    const circles = [];
    for (const n of d.nodes) {
      const [x, y] = P(n.id), r = radius(n);
      circles.push({ id: n.id, x, y, r });
      const near = !sel || n.id === sel || d.edges.some((e) => (e.a === sel && e.b === n.id) || (e.b === sel && e.a === n.id));
      // Unrated aggregators stay in the graph but step back visually.
      ctx.globalAlpha = (near ? 1 : 0.3) * (minor(n) && n.id !== sel ? 0.55 : 1);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = leanCol(n.lean, c); ctx.fill();
      if (n.primary) { ctx.lineWidth = 2; ctx.strokeStyle = c.amber; ctx.stroke(); }
      if (n.id === sel || n.id === hov) { ctx.lineWidth = 2; ctx.strokeStyle = c.glacier; ctx.beginPath(); ctx.arc(x, y, r + 3, 0, Math.PI * 2); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
    // Labels: selected and hovered first, then rated outlets by size; skip any label that would overlap.
    const order = [...d.nodes].sort((a, b) => (b.id === sel) - (a.id === sel) || (b.id === hov) - (a.id === hov) || minor(a) - minor(b) || b.articles - a.articles);
    const boxes = [], max = opts.labels || 8;
    const clash = (bx) => boxes.some((o) => bx.x < o.x + o.w && bx.x + bx.w > o.x && bx.y < o.y + o.h && bx.y + bx.h > o.y)
      || circles.some((ci) => ci.x + ci.r > bx.x && ci.x - ci.r < bx.x + bx.w && ci.y + ci.r > bx.y && ci.y - ci.r < bx.y + bx.h && !bx.own.includes(ci.id));
    let placed = 0;
    for (const n of order) {
      const forced = n.id === sel || n.id === hov;
      if (!forced && placed >= max) continue;
      const [x, y] = P(n.id), r = radius(n);
      const t = n.name.length > 22 ? n.name.slice(0, 21) + "…" : n.name, tw = ctx.measureText(t).width;
      const tries = [[x - tw / 2, y + r + 3], [x - tw / 2, y - r - 17], [x + r + 4, y - 7], [x - r - 4 - tw, y - 7]];
      let spot = null;
      for (const [bx, by] of tries) {
        const box = { x: bx - 2, y: by, w: tw + 4, h: 15, own: [n.id] };
        if (box.x < 2 || box.x + box.w > w - 2 || box.y < 2 || box.y + box.h > h - 2) continue;
        if (!clash(box)) { spot = box; break; }
      }
      if (!spot && forced) spot = { x: tries[0][0] - 2, y: tries[0][1], w: tw + 4, h: 15, own: [] };
      if (!spot) continue;
      boxes.push(spot); placed++;
      if (forced) { ctx.fillStyle = "rgba(4,14,21,.75)"; ctx.fillRect(spot.x, spot.y, spot.w, spot.h); }
      ctx.fillStyle = minor(n) && !forced ? c.ink2 : c.ink; ctx.textAlign = "left";
      ctx.lineWidth = 3; ctx.strokeStyle = "rgba(4,14,21,.85)"; ctx.lineJoin = "round"; ctx.strokeText(t, spot.x + 2, spot.y + 11);
      ctx.fillText(t, spot.x + 2, spot.y + 11);
    }
    canvas._hit = (mx, my) => d.nodes.find((n) => { const [x, y] = P(n.id); return Math.hypot(mx - x, my - y) <= radius(n) + 3; });
  }

  // ---------------------------------------------------------------- diffusion: shared bits
  const SECTORS = [
    { key: "World", desks: ["World", "Policy"], a0: -180, a1: -90 },
    { key: "Technology", desks: ["Technology", "Research", "Video"], a0: -90, a1: 0 },
    { key: "Finance", desks: ["Finance", "Energy"], a0: 0, a1: 90 },
    { key: "India", desks: ["India"], a0: 90, a1: 180 },
  ];
  const plural = (n, w) => `${num(n)} ${w}${n === 1 ? "" : "s"}`;
  const leanCls = (l) => (l == null ? "unrated" : l < 0 ? "left" : l > 0 ? "right" : "center");
  const LEAN_NAME = { "-2": "Left", "-1": "Lean left", "0": "Centre", "1": "Lean right", "2": "Right" };
  const leanName = (l) => (l == null ? "Not rated" : LEAN_NAME[String(l)] || "Rated");
  function desksOf(st, E) {
    const c = {};
    for (const id of st.articles) { const e = E.get(id); if (e && A().desk) { const d = A().desk(e); c[d] = (c[d] || 0) + 1; } }
    return Object.entries(c).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  }
  const sectorOf = (st, E) => { const d = desksOf(st, E)[0] || "World"; return SECTORS.find((s) => s.desks.includes(d)) || SECTORS[0]; };
  // The stories numbered on the map, in the matrix and in the list.
  function shownStories(v) {
    const d = v.data;
    return d.related.slice(0, v.showAll ? 16 : 8).map((st, i) => ({ ...st, n: String(i + 1), via: false }))
      .concat((d.via_sources || []).slice(0, 4).map((st, i) => ({ ...st, n: "abcd"[i], via: true })));
  }
  const simR = (sim, R) => Math.max(0.16 * R, Math.min(R, (R * (1 - Math.max(0, sim))) / 0.75));

  function drawMap(canvas, v) {
    const { ctx, w, h } = setup(canvas), c = COL(), E = entries();
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 46;
    ctx.font = "11px " + css("--font-sans", "system-ui");
    // Rings: distance from the centre is difference in meaning.
    for (const sim of [0.8, 0.6, 0.4]) {
      ctx.setLineDash([3, 5]); ctx.strokeStyle = "rgba(190,228,240,.16)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, simR(sim, R), 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = c.none; ctx.textAlign = "left"; ctx.fillText(Math.round(sim * 100) + "% similar", cx + 4, cy - simR(sim, R) - 4);
    }
    // Sectors: the desk a story mostly comes from.
    ctx.font = "12px " + css("--font-sans", "system-ui");
    for (const s of SECTORS) {
      const a = (s.a0 * Math.PI) / 180;
      ctx.strokeStyle = "rgba(190,228,240,.10)"; ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * 20, cy + Math.sin(a) * 20); ctx.lineTo(cx + Math.cos(a) * (R + 26), cy + Math.sin(a) * (R + 26)); ctx.stroke();
      const m = (((s.a0 + s.a1) / 2) * Math.PI) / 180;
      ctx.fillStyle = c.ink2; ctx.textAlign = "center"; ctx.fillText(s.key, cx + Math.cos(m) * (R + 30), cy + Math.sin(m) * (R + 30) + 4);
    }
    // Place stories: radius from similarity, angle spread within the sector, then nudge apart.
    const items = shownStories(v).map((st) => {
      const sec = sectorOf(st, E);
      return { st, sec, via: st.via, rad: st.via ? R * 0.98 : simR(st.similarity, R), size: st.via ? 5 : Math.min(18, 6 + 2.2 * Math.sqrt(st.sources.length)) };
    });
    for (const s of SECTORS) {
      const mine = items.filter((it) => it.sec === s).sort((a, b) => a.rad - b.rad);
      mine.forEach((it, i) => { it.ang = s.a0 + 12 + ((s.a1 - s.a0 - 24) * (i + 0.5)) / Math.max(1, mine.length); });
    }
    for (let k = 0; k < 40; k++) for (const a of items) for (const b of items) {
      if (a === b) continue;
      const ax = cx + Math.cos((a.ang * Math.PI) / 180) * a.rad, ay = cy + Math.sin((a.ang * Math.PI) / 180) * a.rad;
      const bx = cx + Math.cos((b.ang * Math.PI) / 180) * b.rad, by = cy + Math.sin((b.ang * Math.PI) / 180) * b.rad;
      if (Math.hypot(ax - bx, ay - by) < a.size + b.size + 6) { const push = a.ang < b.ang ? -1.5 : 1.5; a.ang = Math.max(a.sec.a0 + 4, Math.min(a.sec.a1 - 4, a.ang + push)); }
    }
    for (const it of items) { it.x = cx + Math.cos((it.ang * Math.PI) / 180) * it.rad; it.y = cy + Math.sin((it.ang * Math.PI) / 180) * it.rad; }
    // Faint links from the centre carry no extra meaning; keep them very light.
    for (const it of items) { ctx.strokeStyle = it.via ? "rgba(125,151,163,.12)" : "rgba(240,180,90,.16)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(it.x, it.y); ctx.stroke(); }
    ctx.beginPath(); ctx.arc(cx, cy, 13, 0, Math.PI * 2); ctx.fillStyle = "rgba(240,180,90,.3)"; ctx.fill(); ctx.strokeStyle = c.amber; ctx.lineWidth = 2; ctx.stroke();
    const boxes = [];
    const hit = (b) => boxes.some((o) => b.x < o.x + o.w && b.x + b.w > o.x && b.y < o.y + o.h && b.y + b.h > o.y);
    for (const it of items) boxes.push({ x: it.x - it.size, y: it.y - it.size, w: it.size * 2, h: it.size * 2 });
    for (const it of items) {
      const on = v.openStory === it.st.id;
      ctx.beginPath(); ctx.arc(it.x, it.y, it.size, 0, Math.PI * 2);
      ctx.fillStyle = it.via ? "rgba(125,151,163,.3)" : on ? "rgba(178,160,240,.75)" : "rgba(178,160,240,.4)"; ctx.fill();
      ctx.strokeStyle = it.via ? "rgba(125,151,163,.8)" : "rgba(178,160,240,.95)"; ctx.lineWidth = on ? 2.5 : 1; ctx.stroke();
      if (on) { ctx.strokeStyle = c.glacier; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(it.x, it.y, it.size + 4, 0, Math.PI * 2); ctx.stroke(); }
      ctx.fillStyle = it.via ? c.none : c.ink; ctx.font = "600 11px " + css("--font-sans", "system-ui"); ctx.textAlign = "center";
      ctx.fillText(it.st.n, it.x, it.y + 4);
    }
    // Short labels only for the closest stories, and only where they fit.
    ctx.font = "12px " + css("--font-sans", "system-ui");
    const labelled = items.filter((it) => !it.via).sort((a, b) => a.rad - b.rad).slice(0, 4);
    if (v.openStory) { const o = items.find((it) => it.st.id === v.openStory); if (o && !labelled.includes(o)) labelled.push(o); }
    for (const it of labelled) {
      const t = it.st.title.length > 34 ? it.st.title.slice(0, 33) + "…" : it.st.title, tw = ctx.measureText(t).width;
      const right = it.x >= cx;
      const b = { x: right ? it.x + it.size + 6 : it.x - it.size - 6 - tw, y: it.y - 8, w: tw, h: 16 };
      if (b.x < 4 || b.x + b.w > w - 4 || hit(b)) continue;
      boxes.push(b); ctx.textAlign = "left"; ctx.lineWidth = 3; ctx.strokeStyle = "rgba(4,14,21,.85)"; ctx.lineJoin = "round"; ctx.strokeText(t, b.x, it.y + 4);
      ctx.fillStyle = c.ink2; ctx.fillText(t, b.x, it.y + 4);
    }
    canvas._hit = (mx, my) => { const it = items.find((i) => Math.hypot(mx - i.x, my - i.y) <= i.size + 4); return it ? { story: it.st, label: `${it.st.n}. ${it.st.title}` } : Math.hypot(mx - cx, my - cy) < 15 ? { story: v.data.seed_story, label: v.data.seed_story.title } : null; };
  }

  function drawTimeline(canvas, v) {
    const { ctx, w, h } = setup(canvas), c = COL(), E = entries(), d = v.data;
    ctx.clearRect(0, 0, w, h);
    const rows = [{ ...d.seed_story, n: "", seed: true, similarity: 1 }, ...shownStories(v).filter((s) => !s.via)];
    const pts = [];
    for (const st of rows) for (const id of st.articles) { const e = E.get(id); if (e?.published) pts.push({ st, e, t: Date.parse(e.published) }); }
    if (!pts.length) { ctx.fillStyle = c.none; ctx.fillText("No dated articles.", 20, 30); canvas._hit = () => null; return; }
    const L = 56, Rt = 24, T = 26, B = 40;
    let t0 = Math.min(...pts.map((p) => p.t)), t1 = Math.max(Date.now(), ...pts.map((p) => p.t));
    if (t1 - t0 < 36e5 * 6) t0 = t1 - 36e5 * 6;
    const X = (t) => L + ((t - t0) / (t1 - t0)) * (w - L - Rt);
    const lo = Math.max(0, Math.min(...rows.map((r) => r.similarity)) - 0.05);
    const Y = (s) => T + ((1 - s) / (1 - lo || 1)) * (h - T - B);
    ctx.font = "11px " + css("--font-sans", "system-ui");
    // Axes: similarity up, time across.
    for (const s of [1, 0.8, 0.6, 0.4, 0.2].filter((s) => s >= lo)) {
      ctx.strokeStyle = "rgba(190,228,240,.08)"; ctx.beginPath(); ctx.moveTo(L, Y(s)); ctx.lineTo(w - Rt, Y(s)); ctx.stroke();
      ctx.fillStyle = c.none; ctx.textAlign = "right"; ctx.fillText(Math.round(s * 100) + "%", L - 8, Y(s) + 4);
    }
    const day = 864e5, start = new Date(t0); start.setHours(0, 0, 0, 0);
    const stepDays = Math.max(1, Math.ceil((t1 - t0) / day / 8));
    for (let t = start.getTime() + day; t <= t1; t += day * stepDays) {
      ctx.strokeStyle = "rgba(190,228,240,.08)"; ctx.beginPath(); ctx.moveTo(X(t), T); ctx.lineTo(X(t), h - B); ctx.stroke();
      ctx.fillStyle = c.none; ctx.textAlign = "center"; ctx.fillText(new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" }), X(t), h - B + 16);
    }
    ctx.textAlign = "left"; ctx.fillStyle = c.none; ctx.fillText("Similarity to this story", 6, 14);
    ctx.textAlign = "right"; ctx.fillText("Published", w - Rt, h - 6);
    const outlets = d.outlets || {};
    // Stories with near-equal similarity would sit on top of each other: nudge them apart.
    const ys = new Map();
    let last = -Infinity;
    for (const st of [...rows].sort((a, b) => b.similarity - a.similarity)) { const y = Math.max(Y(st.similarity), last + 15); ys.set(st, y); last = y; }
    if (last > h - B) { const k = (h - B - T) / (last - T); for (const [st, y] of ys) ys.set(st, T + (y - T) * k); }
    for (const st of rows) {
      const mine = pts.filter((p) => p.st === st).sort((a, b) => a.t - b.t);
      if (!mine.length) continue;
      const y = ys.get(st), on = v.openStory === st.id;
      ctx.strokeStyle = st.seed ? "rgba(240,180,90,.55)" : on ? "rgba(178,160,240,.8)" : "rgba(178,160,240,.35)"; ctx.lineWidth = on || st.seed ? 3 : 2;
      ctx.beginPath(); ctx.moveTo(X(mine[0].t), y); ctx.lineTo(X(mine[mine.length - 1].t), y); ctx.stroke();
      for (const p of mine) {
        p.x = X(p.t); p.y = y;
        ctx.beginPath(); ctx.arc(p.x, y, 4.5, 0, Math.PI * 2); ctx.fillStyle = leanCol(outlets[p.e.publisher]?.lean, c); ctx.fill();
        ctx.strokeStyle = "rgba(4,14,21,.8)"; ctx.lineWidth = 1; ctx.stroke();
      }
      ctx.fillStyle = st.seed ? c.amber : c.ink; ctx.font = "600 11px " + css("--font-sans", "system-ui"); ctx.textAlign = "right";
      ctx.fillText(st.seed ? "This" : st.n, X(mine[0].t) - 9, y + 4);
      ctx.font = "11px " + css("--font-sans", "system-ui");
    }
    canvas._hit = (mx, my) => {
      const p = pts.find((q) => q.x != null && Math.hypot(mx - q.x, my - q.y) < 7);
      return p ? { story: p.st.seed ? d.seed_story : p.st, label: `${outlets[p.e.publisher]?.name || p.e.source}: ${p.e.title}` } : null;
    };
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
      return `<li class="${open ? "open" : ""}"><button class="cgStory" data-cgstory="${esc(st.id)}" aria-expanded="${open}"><span>${esc(st.title)}</span><small>${plural(st.sources?.length || 0, "source")} · ${plural(arts.length || st.articles?.length || 0, "article")}</small></button>
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
    return `<div class="cgSel"><div class="cgSelHead"><b>${esc(n.name)}</b><span class="fine">${plural(n.articles, "article")} · ${n.stories === 1 ? "1 story" : num(n.stories) + " stories"}${partners.length ? ` · closest: ${esc(partners.join(", "))}` : ""}</span></div>
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
    if (S.view.mode === "diffuse" && S.view.data) (S.view.tab === "time" ? drawTimeline : drawMap)(cv, S.view);
    else if (S.view.mode === "overview" && S.data) drawOverview(cv, S.data, S.pos, { sel: S.sel, hover: S.hover, labels: 18 });
  }

  // ---------------------------------------------------------------- diffusion: lists and matrix
  const outletOf = (d, h) => d.outlets?.[h] || { name: A().state.state?.publishers?.[h]?.name || h, lean: null, known: false };
  const leanTag = (o) => `<span class="cgLean ${leanCls(o?.lean)}">${esc(leanName(o?.lean))}</span>`;
  function distOf(st, d) {
    const r = { left: 0, center: 0, right: 0, unrated: 0 };
    for (const h of st.sources) { const l = outletOf(d, h).lean; l == null ? r.unrated++ : l < 0 ? r.left++ : l > 0 ? r.right++ : r.center++; }
    return r;
  }
  const miniGauge = (st, d) => `<span class="cgMini" aria-hidden="true">${A().gauge({ dist: distOf(st, d), sources: st.sources.length }, null)}</span>`;
  function articleRows(st, d) {
    const E = entries();
    return `<ul class="cgArts">${st.articles.map((id) => E.get(id)).filter(Boolean).map((e) => {
      const o = outletOf(d, e.publisher);
      return `<li><div class="cgArtMeta">${A().logoTag(o, "xs")}<b>${esc(o.name)}</b>${leanTag(o)}${A().paywallTag(e.paywall === "premium" ? "premium" : o.paywall)}</div>
        <a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a><button class="linkButton" data-diffuse="${esc(e.id)}">Diffuse from here</button></li>`;
    }).join("")}</ul>`;
  }
  function storyRow(st, d, v, opts = {}) {
    const open = v.openStory === st.id, E = entries();
    const desks = [...new Set(st.articles.map((id) => E.get(id)).filter(Boolean).map((e) => A().desk(e)))];
    const meta = [plural(st.sources.length, "outlet"), plural(st.articles.length, "article")];
    if (!opts.seed && !st.via) meta.push(`${Math.round(100 * Math.max(0, st.similarity))}% similar`);
    return `<li class="${open ? "open" : ""} ${st.via ? "via" : ""}"><button class="cgStory rich" data-cgstory="${esc(st.id)}" aria-expanded="${open}">
        ${st.n ? `<span class="cgNum ${st.via ? "via" : ""}">${esc(st.n)}</span>` : `<span class="cgNum seed">This</span>`}
        <span class="cgStoryText"><span>${esc(st.title)}</span><small>${desks.map((x) => `<em class="cgDesk">${esc(x)}</em>`).join("")}${meta.join(" · ")}</small></span>${miniGauge(st, d)}</button>
      ${open ? articleRows(st, d) : ""}</li>`;
  }
  function matrix(v) {
    const d = v.data, cols = [{ ...d.seed_story, n: "This" }, ...shownStories(v).filter((s) => !s.via)];
    const gaps = new Set(d.gaps.map((g) => g.id));
    const hosts = [...new Set([...cols.flatMap((c) => c.sources), ...gaps])];
    const main = [], other = [];
    for (const h of hosts) { const o = outletOf(d, h); (o.known || o.primary ? main : other).push(h); }
    const rank = (h) => { const l = outletOf(d, h).lean; return l == null ? 9 : l; };
    const covers = (h) => cols.filter((c) => c.sources.includes(h)).length;
    main.sort((a, b) => rank(a) - rank(b) || covers(b) - covers(a) || outletOf(d, a).name.localeCompare(outletOf(d, b).name));
    other.sort((a, b) => covers(b) - covers(a));
    const cell = (h, c, i) => {
      const o = outletOf(d, h), cls = `${i === 0 ? "seedCol" : ""} ${v.openStory === c.id ? "on" : ""}`;
      if (c.sources.includes(h)) return `<td class="${cls}"><i class="cgCell ${leanCls(o.lean)}" title="${esc(o.name)} covered ${i ? "story " + c.n : "this story"}"></i></td>`;
      if (i === 0 && gaps.has(h)) return `<td class="${cls}"><i class="cgCell gap" title="${esc(o.name)} usually covers this kind of story but has not covered this one"></i></td>`;
      return `<td class="${cls}"></td>`;
    };
    const row = (h) => {
      const o = outletOf(d, h);
      return `<tr class="${v.sel === h ? "on" : ""}"><th scope="row"><button class="cgRowBtn" data-cgdsel="${esc(h)}" title="${esc(o.name)}: ${esc(leanName(o.lean))}">${A().logoTag(o, "xs")}<span>${esc(o.name)}</span></button></th>${cols.map((c, i) => cell(h, c, i)).join("")}</tr>`;
    };
    const otherSummary = other.length ? `<tr class="cgOther"><th scope="row"><button class="cgRowBtn" data-cgother="1" aria-expanded="${!!v.showOther}"><span>${v.showOther ? "Hide" : "Other outlets"} (${other.length})</span></button></th>${cols.map((c, i) => {
      const k = other.filter((h) => c.sources.includes(h)).length;
      return `<td class="${i === 0 ? "seedCol" : ""} ${v.openStory === c.id ? "on" : ""}">${k ? `<span class="cgCount">${k}</span>` : ""}</td>`;
    }).join("")}</tr>` : "";
    const groupRows = (list) => { let prev; return list.map((h) => { const l = outletOf(d, h).lean, g = l == null ? "Not rated" : leanName(l);
      const head = g !== prev ? `<tr class="cgGroup"><th scope="rowgroup" colspan="${cols.length + 1}"><i class="cgLeanDot ${leanCls(l)}"></i>${esc(g)}</th></tr>` : ""; prev = g; return head + row(h); }).join(""); };
    return `<section class="cgMatrixWrap"><h3>Who covered what <span class="fine">outlets grouped by lean; a dashed ring means the outlet usually covers this kind of story but has not covered this one</span></h3>
      <div class="cgMatrixScroll"><table class="cgMatrix"><thead><tr><th></th>${cols.map((c, i) => `<th scope="col" class="${i === 0 ? "seedCol" : ""} ${v.openStory === c.id ? "on" : ""}"><button data-cgstory="${esc(c.id)}" title="${esc(c.title)}">${esc(c.n)}</button></th>`).join("")}</tr></thead>
      <tbody>${groupRows(main)}${otherSummary}${v.showOther ? other.map(row).join("") : ""}</tbody></table></div></section>`;
  }
  function seedCard(v) {
    const d = v.data, st = d.seed_story, E = entries();
    const desks = [...new Set(st.articles.map((id) => E.get(id)).filter(Boolean).map((e) => A().desk(e)))];
    const firstTs = st.first || st.articles.map((id) => E.get(id)?.published).filter(Boolean).sort()[0];
    const dist = distOf(st, d);
    return `<div class="cgSeed">${A().gauge({ dist, sources: st.sources.length }, null)}
      <div class="cgSeedText"><span class="fine">Spreading out from</span><h3>${esc(st.title)}</h3>
        <p class="fine">${desks.map((x) => `<em class="cgDesk">${esc(x)}</em>`).join("")}${plural(st.sources.length, "outlet")} · ${plural(st.articles.length, "article")}${firstTs ? ` · first seen ${esc(new Date(firstTs).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))}` : ""}${d.gaps.length ? ` · ${plural(d.gaps.length, "outlet")} not covering it yet` : ""}</p></div>
      <button class="linkButton" data-cgstory="${esc(st.id)}">Show its articles</button></div>`;
  }
  function diffusionMain(v) {
    const d = v.data;
    if (v.busy && !d) return `<div class="pageLoading">Spreading out from this article…</div>`;
    if (v.error || !d) return `<div class="empty"><b>Could not diffuse</b><span class="fine">${esc(v.error || "")}</span></div>`;
    const tab = v.tab || "map";
    const caption = tab === "map"
      ? `Centre: this story. Distance from the centre shows how different a story is in meaning; the quarter shows its desk; size shows how many outlets carry it. Grey dots (a–d) share outlets but not meaning. Numbers match the list and the table.`
      : `Each line is one story, placed by how similar it is to this one. Dots are articles, coloured by the outlet's lean, placed by when they were published. Lines with nearly the same similarity are nudged apart.`;
    return `${seedCard(v)}<div class="cgTabs" role="tablist">${[["map", "Map and coverage"], ["time", "Timeline"]].map(([k, t]) => `<button role="tab" aria-selected="${tab === k}" class="${tab === k ? "on" : ""}" data-cgtab="${k}">${t}</button>`).join("")}</div>
      <canvas id="cgBig" class="cgBig diff" role="img" aria-label="${tab === "map" ? "Map of related stories" : "Timeline of related stories"}"></canvas>
      <div class="cgKey"><p class="fine">${caption}</p>${tab === "map" ? `<div class="cgLegend"><span><i class="cgDot seed"></i>This story</span><span><i class="cgDot rel"></i>Related in meaning</span><span><i class="cgDot via"></i>Shares outlets only</span></div>` : `<div class="cgLegend"><span><i class="cgDot l"></i>Left</span><span><i class="cgDot c"></i>Centre</span><span><i class="cgDot r"></i>Right</span><span><i class="cgDot n"></i>Not rated</span></div>`}</div>
      ${matrix(v)}`;
  }
  function diffusionSide() {
    const v = S.view, d = v.data;
    if (!d) return "";
    const shown = shownStories(v), rel = shown.filter((s) => !s.via), via = shown.filter((s) => s.via);
    const sel = v.sel ? (() => {
      const o = outletOf(d, v.sel), gap = d.gaps.some((g) => g.id === v.sel);
      const theirs = [{ ...d.seed_story }, ...shown].filter((st) => st.sources.includes(v.sel));
      return `<div class="cgSel"><div class="cgSelHead">${A().logoTag(o, "xs")}<b>${esc(o.name)}</b>${leanTag(o)}${A().paywallTag(o.paywall)}<span class="fine">${gap ? "Has not covered this story yet" : (theirs.length === 1 ? "1 story" : theirs.length + " stories") + " on this map"}</span></div>
        <div class="cgSelActions"><button class="linkButton" data-pubonly="${esc(v.sel)}">Show only this outlet on the page</button><button class="linkButton" data-cgdsel="">Clear</button></div></div>`;
    })() : "";
    const more = d.related.length > 8 ? `<button class="linkButton cgMore" data-cgmore="1">${v.showAll ? "Show fewer" : `Show ${d.related.length - 8} more`}</button>` : "";
    return `${sel}
      <section><h3>This story</h3><ul class="cgStories">${storyRow(d.seed_story, d, v, { seed: true })}</ul></section>
      <section><h3>Related stories <span class="fine">most similar first</span></h3>${rel.length ? `<ul class="cgStories">${rel.map((st) => storyRow(st, d, v)).join("")}</ul>${more}` : `<p class="fine">No closely related stories in the last ${d.days} days.</p>`}</section>
      ${via.length ? `<section><h3>Also from these outlets <span class="fine">share outlets, not meaning</span></h3><ul class="cgStories">${via.map((st) => storyRow(st, d, v)).join("")}</ul></section>` : ""}
      <section><h3>Not covering this yet</h3>${d.gaps.length ? `<p class="fine">Outlets that usually cover this kind of story but have not covered this one in Sanjaya.</p><div class="cgGaps">${d.gaps.map((g) => { const o = outletOf(d, g.id); return `<button class="cgGap ${v.sel === g.id ? "on" : ""}" data-cgdsel="${esc(g.id)}">${A().logoTag(o, "xs")}${esc(o.name)}<i class="cgLeanDot ${leanCls(o.lean)}"></i></button>`; }).join("")}</div>` : `<p class="fine">Every outlet that usually covers this kind of story already has it.</p>`}
        <div class="cgFurther"><button class="action primary" id="cgFurther" ${v.busy ? "disabled" : ""}>${v.busy ? "Searching…" : "Search further"}</button><span class="fine">Searches Google News for <b>${esc(d.terms.join(", "))}</b>${d.gaps.length ? `, including ${esc(d.gaps.slice(0, 3).map((g) => outletOf(d, g.id).name).join(", "))}` : ""}. New articles join the ${esc(v.desk)} desk.</span></div>
        ${v.msg ? `<p class="fine cgMsg">${esc(v.msg)}</p>` : ""}</section>`;
  }
  function drawOverlay() {
    const v = S.view;
    if (!v) return;
    const el = overlayEl();
    const diff = v.mode === "diffuse";
    const keep = [...el.querySelectorAll(".cgSide, .cgMain")].map((x) => x.scrollTop);
    const title = diff ? "Diffusion from one article" : "Coverage graph";
    const sub = diff ? (v.data ? `${esc(v.data.note)} Searched ${num(v.data.pool)} articles from the last ${v.data.days} days.` : "") : esc(S.data?.note || "");
    el.innerHTML = `<div class="cgDialog"><header class="cgHead"><div><h2>${title}</h2><p class="fine">${sub}</p></div>
        ${diff ? "" : edgeSwitch()}
        <button class="action" data-cgclose="1" aria-label="Close">Close</button></header>
      ${diff ? `<div class="cgBody diff"><div class="cgMain">${diffusionMain(v)}</div><aside class="cgSide">${diffusionSide()}</aside></div>`
        : `<div class="cgBody"><canvas id="cgBig" class="cgBig" role="img" aria-label="${title}"></canvas><aside class="cgSide">${legend()}${info()}</aside></div>`}</div>`;
    [...el.querySelectorAll(".cgSide, .cgMain")].forEach((x, i) => { if (keep[i]) x.scrollTop = keep[i]; });
    const cv = el.querySelector("#cgBig");
    if (!cv) return;
    drawOverlayCanvas();
    bindCanvas(cv, diff ? "diffuse" : "overlay");
  }
  function expand() {
    S.view = { mode: "overview" };
    drawOverlay();
    document.addEventListener("keydown", onKey, true);
  }
  async function diffuse(id, desk) {
    S.view = { mode: "diffuse", seed: id, data: null, busy: true, tab: (S.view?.tab) || "map", desk: desk || A().state.graphDesk || "World", openStory: "", sel: "" };
    drawOverlay();
    document.addEventListener("keydown", onKey, true);
    try { S.view.data = await A().api("/api/graph/diffuse", "POST", { seed: id, days: 7 });  }
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
        : `No new articles: all ${num(r.fetched)} results are already in Sanjaya.`;
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
    if (b.dataset.cgtab && S.view) { S.view.tab = b.dataset.cgtab; drawOverlay(); return true; }
    if (b.dataset.cgmore && S.view) { S.view.showAll = !S.view.showAll; drawOverlay(); return true; }
    if (b.dataset.cgother && S.view) { S.view.showOther = !S.view.showOther; drawOverlay(); return true; }
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
