(() => {
  "use strict";
  const $ = (q) => document.querySelector(q),
    E = (x) =>
      String(x ?? "").replace(
        /[&<>"']/g,
        (c) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[c],
      );
  const link = (u, t) => {
    try {
      let v = new URL(u);
      return /^https?:$/.test(v.protocol)
        ? `<a href="${E(v.href)}" target="_blank" rel="noopener noreferrer">${E(t)} ↗</a>`
        : "";
    } catch {
      return "";
    }
  };
  const S = {
    tab: "desk",
    data: null,
    hours: 24,
    topic: "all",
    region: "all",
    priority: "all",
    query: "",
    sourceQuery: "",
    family: "all",
    paused: false,
    motion: true,
    loading: false,
    busy: false,
    error: "",
    notice: "",
    fetched: 0,
    fresh: new Set(),
    seen: null,
    expanded: new Set(),
  };
  const fmt = (x) => {
    if (!x) return "Never";
    const d = new Date(x);
    return Number.isNaN(+d)
      ? "Unknown"
      : d.toLocaleString("en-GB", {
          timeZone: "Europe/Berlin",
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        });
  };
  const W = () => window.ATLASWall;
  // A story removed from the wall stays removed while most of its articles are ones the reader removed.
  const removed = (g) => {
    const w = W();
    if (!w) return false;
    const n = (g.records || []).filter((r) => w.isHidden(r.id)).length;
    return n > 0 && n * 2 >= (g.records || []).length;
  };
  const filtered = () => {
    const l = (S.data?.groups || []).filter(
      (g) =>
        !removed(g) &&
        (S.topic === "all" || (g.topics || []).includes(S.topic)) &&
        (S.region === "all" || (g.regions || []).includes(S.region)) &&
        (S.priority === "all" || g.lead.priority === S.priority) &&
        (!S.query ||
          g.records.some((r) =>
            (String(r.title || "") + " " + String(r.summary || "") + " " + String(r.source || ""))
              .toLowerCase()
              .includes(S.query.toLowerCase()),
          )),
    );
    return W() ? W().arrange(l, "newsroom", Infinity, (g) => g.id) : l;
  };
  const note = (t) => `<div class="nr-note">${t}</div>`;
  const ago = (x) => {
    const m = (Date.now() - Date.parse(x)) / 6e4;
    return !isFinite(m) ? "" : m < 2 ? "just now" : m < 60 ? Math.floor(m) + " min ago" : m < 1440 ? Math.floor(m / 60) + " h ago" : Math.floor(m / 1440) + " d ago";
  };
  const AT = () => window.ATLAS;
  let index = { src: null, map: new Map() };
  const entryOf = (r) => {
    const list = AT()?.state?.state?.entries || [];
    if (index.src !== list) index = { src: list, map: new Map(list.map((e) => [e.id, e])) };
    return index.map.get(r?.id);
  };
  const pubFor = (r) => {
    const e = entryOf(r);
    const p = e && AT()?.state?.state?.publishers?.[e.publisher];
    return p && p.name ? p : { name: String(r?.publisher_name || r?.source || "Unknown outlet").split(" · ")[0], masthead: "grotesk", lean: null };
  };
  const safe = (fn, label) => {
    try {
      return fn();
    } catch (e) {
      console.warn("[Emergency newsroom] skipped " + label, e);
      return "";
    }
  };
  function spread(g) {
    const seen = new Map();
    for (const r of g.records) { const p = pubFor(r); if (!seen.has(p.name)) seen.set(p.name, p.lean); }
    const d = { left: 0, center: 0, right: 0, unrated: 0 };
    for (const v of seen.values()) d[v === null || v === undefined ? "unrated" : v < 0 ? "left" : v > 0 ? "right" : "center"]++;
    return { sources: seen.size, dist: d };
  }
  function card(g, lead = false) {
    const r = g.lead, p = pubFor(r), A = AT();
    const hi = r.priority === "Priority 1";
    const seenOutlets = new Set([p.name]);
    const others = g.records.filter((x) => {
      const n = pubFor(x).name;
      if (x === r || seenOutlets.has(n)) return false;
      seenOutlets.add(n);
      return true;
    }).slice(0, lead ? 6 : 3);
    return `<article class="nr-card ${lead ? "nr-lead" : ""} ${hi ? "nr-p1" : ""} ${S.fresh.has(g.id) && r.age_hours <= 3 ? "nr-new" : ""}">
      <div class="nr-top">${A ? A.pubBadge(p, r.source) : E(r.source)}<span class="nr-age">${E(ago(r.published))}</span>${W() ? W().removeBtn(g.records.map((x) => x.id), "Remove this story from the wall") : ""}</div>
      <div class="nr-labels"><span class="nr-label ${hi ? "high" : ""}">${hi ? "Read first" : "Priority"}</span>${r.publisher_breaking && r.age_hours <= 3 ? '<span class="nr-label breaking">Publisher says breaking</span>' : ""}${(g.topics || []).map((t) => `<span class="nr-chip">${E(t)}</span>`).join("")}</div>
      ${g.generated ? `<div class="nr-gen"><span class="nr-genTag" title="Written by ${E(g.generated.model)} on this computer from the headlines below. Can contain mistakes.">Generated</span><b>${E(g.generated.label)}</b></div>` : ""}
      <h2><a href="${E(r.url)}" target="_blank" rel="noopener noreferrer">${E(r.title)}</a></h2>
      <p>${E(r.summary && r.summary !== r.title ? r.summary : "No publisher excerpt. Read the original before drawing conclusions.")}</p>
      <div class="nr-foot">${A ? A.gauge(spread(g), p.lean) : ""}<div class="nr-also">${others.length ? `<small>Also reporting</small>${others.map((x) => `<a href="${E(x.url)}" target="_blank" rel="noopener noreferrer" title="${E(x.title)}">${A ? A.logoTag(pubFor(x)) : ""}<span>${E(pubFor(x).name)}</span></a>`).join("")}` : `<small>Only one outlet so far</small>`}</div></div>
      ${g.generated ? `<details class="nr-genBox" ${lead ? "open" : ""}><summary>Generated summary</summary><p>${E(g.generated.summary)}</p>${g.generated.differences ? `<p class="nr-meta">How outlets differ: ${E(g.generated.differences)}</p>` : ""}<p class="nr-meta">Written by ${E(g.generated.model)} from ${g.records.length} headlines and excerpts. Not publisher text; check the originals.</p></details>` : ""}
      <details><summary>Why this surfaced</summary><p class="nr-meta">${(r.reasons || []).map(E).join(" · ")}. Priority is a reading order, not verified severity. Similar-headline groups can occasionally join separate events.</p></details>
    </article>`;
  }
  function desk() {
    const groups = filtered(), counts = {};
    (S.data?.groups || []).forEach((g) => (g.topics || []).forEach((t) => (counts[t] = (counts[t] || 0) + 1)));
    const regions = [...new Set((S.data?.groups || []).flatMap((g) => g.regions || []))].sort();
    const timeline = groups.slice().sort((a, b) => b.latest.localeCompare(a.latest)).slice(0, 14);
    return `<div class="nr-controls"><div class="nr-issue-strip"><button class="nr-issue ${S.topic === "all" ? "active" : ""}" data-nr-topic="all"><b>${(S.data?.groups || []).length}</b>All issues</button>${Object.entries(counts).map(([t, n]) => `<button class="nr-issue ${S.topic === t ? "active" : ""}" data-nr-topic="${E(t)}"><b>${n}</b>${E(t)}</button>`).join("")}</div>
      <div class="nr-filters"><select id="nrHours" aria-label="Window">${[6, 12, 24, 48].map((h) => `<option value="${h}" ${S.hours === h ? "selected" : ""}>Last ${h} hours</option>`).join("")}</select><select id="nrPriority" aria-label="Priority"><option value="all">All priorities</option><option value="Priority 1" ${S.priority === "Priority 1" ? "selected" : ""}>Read first only</option><option value="Priority 2" ${S.priority === "Priority 2" ? "selected" : ""}>Priority only</option></select><select id="nrRegion" aria-label="Source region"><option value="all">All source regions</option>${regions.map((r) => `<option ${S.region === r ? "selected" : ""}>${E(r)}</option>`).join("")}</select><input id="nrQuery" type="search" value="${E(S.query)}" placeholder="Issue, country or publisher"><button id="nrReset" class="action">Reset</button>${W() ? `<span class="panelTools">${W().restoreLine()}${W().dice("newsroom", groups.length)}</span>` : ""}</div></div>
    ${groups.length ? `<div class="nr-board"><div class="nr-main">${safe(() => card(groups[0], true), "lead")}<div class="nr-grid">${groups.slice(1, 25).map((g) => safe(() => card(g), g?.id)).join("")}</div></div>
      <aside class="nr-rail"><h2>Timeline</h2><ol>${timeline.map((g) => safe(() => `<li class="${g.lead.priority === "Priority 1" ? "p1" : ""}"><time>${E(fmt(g.latest).split(", ").pop())}</time><a href="${E(g.lead.url)}" target="_blank" rel="noopener noreferrer">${E(g.lead.title)}</a><span>${E(pubFor(g.lead).name)} · ${g.publisher_count} outlet${g.publisher_count === 1 ? "" : "s"}</span></li>`, "timeline")).join("")}</ol></aside></div>`
      : `<div class="nr-empty"><h2>No priority updates in this window</h2><p>Widen the window, clear filters or refresh. An empty board does not mean nothing major happened.</p>${(S.data?.groups || []).some(removed) ? `<p>${(S.data.groups || []).filter(removed).length} stor${(S.data.groups || []).filter(removed).length === 1 ? "y is" : "ies are"} hidden because you removed them from the wall. ${W() ? W().restoreLine() : ""}</p>` : ""}<button data-nr-tab="sources" class="action">Check source coverage</button></div>`}
    <p class="nr-meta" style="margin-top:18px">${E(S.data?.method || "")} ${S.data?.truncated ? "Showing up to 80 groups from the top 700 candidates. " : ""}Undated records omitted: ${S.data?.rejections?.undated || 0}.</p>`;
  }
  function toggle(scope, key, name, total, enabled) {
    return `<label><input type="checkbox" data-nr-scope="${scope}" data-nr-key="${E(key)}" data-partial="${enabled > 0 && enabled < total}" ${enabled === total ? "checked" : ""} ${S.busy ? "disabled" : ""} aria-label="Include ${E(name)}"></label>`;
  }
  function sources() {
    const d = S.data,
      all = d?.families || [],
      q = S.sourceQuery.toLowerCase();
    const families = all
      .filter((f) => S.family === "all" || f.id === S.family)
      .map((f) => ({
        ...f,
        publishers: f.publishers
          .map((p) => ({
            ...p,
            feeds: p.feeds.filter(
              (x) =>
                !q ||
                (x.name + " " + p.name + " " + f.name + " " + x.region)
                  .toLowerCase()
                  .includes(q),
            ),
          }))
          .filter((p) => p.feeds.length),
      }))
      .filter((f) => f.publishers.length);
    return `${note("Publishers you block in <b>Sources</b> are removed everywhere, including here. The switches below are an extra, newsroom-only layer.")}${note("These controls affect <b>Emergency Newsroom only</b>. Other ATLAS panels and the underlying archive retain their sources. Parent choices apply to new feeds in that group; a specific publisher or feed can override a parent. Family labels describe source type, not political orientation or factual reliability.")}<div class="nr-grid">${all
      .map(
        (f) =>
          `<section class="nr-cluster"><strong>${f.enabled} / ${f.total}</strong><h3>${E(f.name)}</h3><small>feeds included · ${f.publishers.length} publisher groups</small><div class="nr-chips">${f.publishers
            .slice(0, 6)
            .map((p) => `<span class="nr-chip">${E(p.name)}</span>`)
            .join(
              "",
            )}</div><button class="action" data-nr-family="${f.id}">Configure cluster</button></section>`,
      )
      .join(
        "",
      )}</div><div class="nr-controls" style="margin-top:20px"><label>Find a publisher or feed<input type="search" id="nrSourceQuery" value="${E(S.sourceQuery)}" placeholder="Reuters, BBC, India…"></label><label>Source family<select id="nrFamily"><option value="all">All families</option>${all.map((f) => `<option value="${f.id}" ${S.family === f.id ? "selected" : ""}>${E(f.name)}</option>`).join("")}</select></label><button class="action" data-nr-all="include" ${S.busy ? "disabled" : ""}>Include all</button><button class="action" data-nr-all="exclude" ${S.busy ? "disabled" : ""}>Exclude all</button></div><p class="nr-meta">Checked = included. A dash means partial inclusion. Changes save immediately and are reversible.</p><div class="nr-source-tree">${families.map((f) => `<details data-nr-open="${E(f.id)}" ${S.expanded.has(f.id) || q || S.family !== "all" ? "open" : ""}><summary>${toggle("family", f.id, f.name, f.total, f.enabled)}${E(f.name)}<small>${f.enabled}/${f.total} included</small></summary>${f.publishers.map((p) => `<details data-nr-open="${E(p.id)}" ${S.expanded.has(p.id) || q ? "open" : ""}><summary>${toggle("publisher", p.id, p.name, p.total, p.enabled)}${E(p.name)}<small>${p.enabled}/${p.total}</small></summary>${p.feeds.map((x) => `<div class="nr-feed ${x.excluded ? "nr-excluded" : ""}">${toggle("feed", x.id, x.name, 1, x.excluded ? 0 : 1)}<div><b>${E(x.name)}</b><small>${E(x.region)} · ${E(x.desk)} · ${E(x.mode)} · last check ${fmt(x.attempted)}</small><small class="${x.state === "error" ? "nr-fail" : ""}">${E(x.state)} ${E(x.error || "")}</small></div></div>`).join("")}</details>`).join("")}</details>`).join("") || '<div class="nr-empty">No matching source groups.</div>'}</div>`;
  }
  function render() {
    const view = window.ATLAS?.state?.view;
    if (view ? view !== "emergency" : location.hash !== "#emergency") return;
    try {
      draw();
    } catch (e) {
      console.error("Emergency newsroom render failed", e);
      const el = $("#main");
      if (el) el.innerHTML = `<div class="nr"><header class="nr-head"><div><h1>Emergency newsroom</h1></div></header><div class="nr-empty"><h2>The newsroom could not be drawn</h2><p>${E(e && e.message ? e.message : String(e))}</p><p class="nr-meta">${E((e && e.stack ? e.stack : "").split("\n").slice(0, 3).join(" · "))}</p><button id="nrReload" class="action">Try again</button></div></div>`;
    }
  }
  function draw() {
    const d = S.data,
      h = d?.health || {},
      el = $("#main");
    if (!el) return;
    el.innerHTML = `<div class="nr ${S.motion ? "" : "nr-nomotion"}"><header class="nr-head"><div><h1>Emergency newsroom</h1><p>The developments to read first, who is reporting them and how widely. A research briefing, not a warning service.</p></div><div class="nr-buttons"><button id="nrRefresh" class="action primary"><svg><use href="#i-refresh"/></svg>Refresh news</button><button id="nrPause" class="action">${S.paused ? "Resume auto-update" : "Pause auto-update"}</button><button id="nrMotion" class="action">Highlights ${S.motion ? "on" : "off"}</button></div></header>
    <div class="nr-status"><span class="nr-pulse ${S.paused ? "paused" : ""}"></span><span>${S.paused ? "Auto-update paused" : S.loading ? "Checking the index…" : "Checked " + fmt(d?.checked)}</span><span><b>${h.enabled ?? 0}</b> feeds in</span><span><b>${h.excluded ?? 0}</b> excluded here</span><span><b>${h.successful ?? 0}</b> healthy</span>${d?.grouping ? `<button class="nr-mode ${d.grouping.mode === "meaning" ? "on" : ""}" data-page="lm" title="${E(d.grouping.note || "Groups formed by a local multilingual model at strictness " + d.grouping.threshold)}">${d.grouping.mode === "meaning" ? "Grouped by meaning" : "Keyword mode"}</button>` : ""}<span class="spacer"></span><div class="nr-tabs"><button data-nr-tab="desk" class="${S.tab === "desk" ? "active" : ""}">Priority desk</button><button data-nr-tab="sources" class="${S.tab === "sources" ? "active" : ""}">Newsroom sources</button></div></div>
    ${S.error ? note(`<span class="nr-fail">${E(S.error)}</span> <button id="nrReload" class="action">Retry</button>`) : ""}${S.notice ? note(E(S.notice)) : ""}${d ? (S.tab === "sources" ? sources() : desk()) : '<div class="nr-empty">Loading the news index…</div>'}</div>`;
    document
      .querySelectorAll('[data-partial="true"]')
      .forEach((x) => (x.indeterminate = true));
    document.querySelectorAll("[data-nr-open]").forEach((x) =>
      x.addEventListener("toggle", () => {
        x.open
          ? S.expanded.add(x.dataset.nrOpen)
          : S.expanded.delete(x.dataset.nrOpen);
      }),
    );
  }
  async function load(force = false) {
    if (S.loading || S.busy || (!force && S.paused)) return;
    if (!force && Date.now() - S.fetched < 14000) return;
    S.loading = true;
    try {
      const r = await fetch("/api/emergency?hours=" + S.hours, {
          cache: "no-store",
          signal: AbortSignal.timeout(15000),
        }),
        d = await r.json();
      if (!r.ok) throw Error(d.error || "Index request failed");
      const ids = new Set(d.groups.map((g) => g.id));
      S.fresh = new Set(S.seen ? [...ids].filter((x) => !S.seen.has(x)) : []);
      S.seen = ids;
      S.data = d;
      S.fetched = Date.now();
      S.error = "";
    } catch (e) {
      S.error = e.message;
    } finally {
      S.loading = false;
      render();
    }
  }
  async function apply(scope, key, excluded) {
    if (S.busy || !S.data) return;
    S.busy = true;
    S.error = "";
    let failure = "";
    render();
    try {
      const r = await fetch("/api/emergency-sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope,
            key,
            excluded,
            version: S.data.source_version,
          }),
          signal: AbortSignal.timeout(10000),
        }),
        d = await r.json();
      if (!r.ok) throw Error(d.error || "Could not save source choices");
      S.notice = "Source choices saved for this newsroom.";
    } catch (e) {
      failure = e.message;
    } finally {
      S.busy = false;
      await load(true);
      if (failure) {
        S.error = failure;
        S.notice = "";
        render();
      }
    }
  }
  async function refresh() {
    try {
      const r = await fetch("/api/emergency-refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
          signal: AbortSignal.timeout(10000),
        }),
        d = await r.json();
      if (!r.ok) throw Error(d.error || "Refresh failed");
      S.notice = d.started
        ? "News collection started. Priority sources are checked first; results appear as requests finish."
        : "A collection is already running. No duplicate collection was started.";
      render();
      setTimeout(() => load(true), 2000);
    } catch (e) {
      S.error = e.message;
      render();
    }
  }
  document.addEventListener("atlas:wall", () => render());
  document.addEventListener("click", (e) => {
    let b = e.target.closest(
      "[data-nr-tab],[data-nr-topic],[data-nr-family],[data-nr-all],#nrReset,#nrRefresh,#nrReload,#nrPause,#nrMotion",
    );
    if (!b) return;
    if (b.dataset.nrTab) {
      S.tab = b.dataset.nrTab;
      render();
    } else if (b.dataset.nrTopic) {
      S.topic = b.dataset.nrTopic;
      render();
    } else if (b.dataset.nrFamily) {
      S.family = b.dataset.nrFamily;
      S.expanded.add(S.family);
      render();
    } else if (b.dataset.nrAll)
      apply("all", "all", b.dataset.nrAll === "exclude");
    else if (b.id === "nrReset") {
      Object.assign(S, {
        topic: "all",
        region: "all",
        priority: "all",
        query: "",
      });
      render();
    } else if (b.id === "nrPause") {
      S.paused = !S.paused;
      render();
      if (!S.paused) load(true);
    } else if (b.id === "nrMotion") {
      S.motion = !S.motion;
      render();
    } else if (b.id === "nrRefresh") refresh();
    else if (b.id === "nrReload") load(true);
  });
  document.addEventListener("change", (e) => {
    const x = e.target;
    if (x.dataset.nrScope)
      apply(x.dataset.nrScope, x.dataset.nrKey, !x.checked);
    else if (x.id === "nrHours") {
      S.hours = Number(x.value);
      load(true);
    } else {
      const m = {
        nrRegion: "region",
        nrPriority: "priority",
        nrFamily: "family",
      };
      if (m[x.id]) {
        S[m[x.id]] = x.value;
        render();
      }
    }
  });
  let typing;
  document.addEventListener("input", (e) => {
    if (["nrQuery", "nrSourceQuery"].includes(e.target.id)) {
      clearTimeout(typing);
      const id = e.target.id,
        v = e.target.value,
        pos = e.target.selectionStart;
      typing = setTimeout(() => {
        S[id === "nrQuery" ? "query" : "sourceQuery"] = v;
        render();
        const f = $("#" + id);
        if (f) {
          f.focus();
          f.setSelectionRange(pos, pos);
        }
      }, 250);
    }
  });
  window.ATLASEmergency = {
    mount: () => {
      render();
      load(true);
    },
    refreshIfStale: () => {
      if (!document.activeElement?.id?.startsWith("nr")) load();
    },
    state: S,
    render,
  };
})();
