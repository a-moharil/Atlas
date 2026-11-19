"use strict";
const $ = (q, root = document) => root.querySelector(q),
  $$ = (q, root = document) => Array.from(root.querySelectorAll(q));
const esc = (x) =>
  String(x ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const url = (x) => {
  try {
    const u = new URL(x);
    return /^https?:$/.test(u.protocol) ? u.href : "#";
  } catch {
    return "#";
  }
};
const fmt = (x) => {
  if (!x) return "Never";
  const d = new Date(x);
  return Number.isNaN(+d)
    ? "Unknown"
    : d.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Amsterdam",
      });
};
const ago = (x) => {
  if (!x) return "Never";
  let m = (Date.now() - Date.parse(x)) / 6e4;
  return !isFinite(m)
    ? "Unknown"
    : m < 2
      ? "now"
      : m < 60
        ? Math.floor(m) + "m ago"
        : m < 1440
          ? Math.floor(m / 60) + "h ago"
          : Math.floor(m / 1440) + "d ago";
};
const num = (x) => Number(x || 0).toLocaleString("en-GB");
const ROOT = {
  state: null,
  metrics: null,
  view: "room",
  search: "",
  bias: "all",
  font: 18,
  player: null,
  leaflet: null,
  live: [],
  mapLayers: {},
  basemap: "satellite",
  mapMode: "satellite",
  dateOffset: 1,
  fireLayer: false,
  effisFwi: false,
  effisBurn: false,
  earthLayer: false,
  eventsLayer: true,
  shakemap: null,
  geoResults: {},
  mapBusy: false,
  worldTab: "rest",
  worldArea: "all",
  indiaTab: "all",
  indiaDays: 7,
  indiaTopic: "all",
  indiaScope: "all",
  indiaCoverage: null,
  indiaSelected: null,
  indiaMap: null,
  indiaGeometry: null,
  indiaGeometryLabel: "",
  indiaBase: "street",
  satFailures: 0,
  satLoaded: 0,
  networkErrors: [],
  indiaGeoBusy: false,
  indiaStateFilter: "all",
  indiaCityFilter: "all",
  pubFilters: [],
  pbOpen: false,
  primaryFirst: true,
  paywallFilter: "all",
  indiaBoundary: true,
};
const pages = {
  room: ["Situation room", "Today at a glance"],
  news: ["World", "International reporting"],
  india: ["India", "National, regional and India-in-the-world"],
  technology: ["Technology", "Technology, science and industry"],
  finance: ["Finance and energy", "Markets, trade and energy"],
  emergency: ["Emergency newsroom", "Priority political and security updates"],
  media: ["Live TV and video", "Verified streams and broadcaster uploads"],
  earth: ["Earth watch", "Hazards, climate anomalies and live weather fields"],
  map: ["Satellite atlas", "Imagery and hazard layers"],
  investigate: ["India regional map", "Where Indian coverage is concentrated"],
  conflict: ["Conflict atlas", "Published maps, reporting and theatres"],
  geopolitics: ["Geopolitics", "Summits, blocs and diplomatic sources"],
  macro: ["Macroeconomics", "Indicators, trade and energy"],
  constellation: ["Article constellation", "Semantic map of retrieved reporting"],
  research: ["Research library", "Think tanks and scholarly metadata"],
  mygov: ["MyGov policy", "Ministries, schemes and research funding"],
  sources: ["Sources", "Publishers, bias, paywalls and your preferences"],
  radar: ["Research radar", "New ML research ranked against your own papers"],
  wiki: ["Wikipedia", "English Wikipedia, read inside Sanjaya"],
  about: ["Why Sanjaya", "The motivation behind this app"],
  lm: ["Language model", "Grouping by meaning and generated labels"],
  coverage: ["Coverage audit", "Retrieval health and history"],
  ccc: ["CCC archive", "Research archive"],
};
async function api(path, method = "GET", body) {
  let opt = { method, cache: "no-store", signal: AbortSignal.timeout(20000) };
  if (body !== undefined) {
    opt.headers = { "Content-Type": "application/json" };
    opt.body = JSON.stringify(body);
  }
  let res = await fetch(path, opt);
  let data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw Error(data?.error || `HTTP ${res.status}`);
  return data;
}
function tip(t) {
  $("#notify").textContent = t;
  $("#notify").classList.add("show");
  setTimeout(() => $("#notify").classList.remove("show"), 3600);
}
function sourceConfig(id) {
  // Articles found by the coverage graph's "Search further" belong to the desk they were searched from.
  if (String(id || "").startsWith("expand:")) return { id, name: "Search further", desk: String(id).slice(7), region: "Global", tier: "reporting" };
  return (
    ROOT.state?.registry?.feeds?.find((f) => f.id === id) ||
    ROOT.state?.registry?.channels?.find((f) => f.id === id) || {
      desk: "Research",
    }
  );
}
function desk(e) {
  if (e.medium === "paper") return "Research";
  if (e.medium === "video") return "Video";
  return sourceConfig(e.source_id).desk || "World";
}
function pubOf(e) {
  return ROOT.state?.publishers?.[e?.publisher] || null;
}
function prefOf(host) {
  return ROOT.state?.source_prefs?.[host] || "normal";
}
function orientation(e) {
  if (e.tier === "primary") return ["Official source", "primary"];
  if (e.medium === "paper") return ["Scholarly metadata", "unknown"];
  const p = pubOf(e);
  if (!p || p.lean === null || p.lean === undefined) return ["Not rated", "unknown"];
  return [p.lean_label, p.lean < 0 ? "left" : p.lean > 0 ? "right" : "center"];
}
// v6.0: the lean label on a card opens your calibration for that outlet (calibrate.js).
function leanTag(e, p, bias, cls) {
  if (e.tier === "primary" || e.medium === "paper" || !e.publisher || !window.ATLASLean) return cls !== "unknown" ? `<span class="tag ${cls}">${esc(bias)}</span>` : "";
  const yours = p?.lean_user;
  const label = cls === "unknown" ? "Not rated" : bias;
  return `<button class="tag leanTag ${cls} ${yours ? "yours" : ""}" data-leanedit="${esc(e.publisher)}" title="${yours ? `Your rating (published: ${esc(p.lean_original_label || "Not rated")}). Click to change.` : "Published rating. Click to calibrate it with your own reading."}">${esc(label)}${yours ? `<em>yours</em>` : ""}</button>`;
}
function initials(name) {
  const w = String(name || "?").replace(/^the\s+/i, "").split(/[\s·\-]+/).filter(Boolean);
  return (w.length > 1 ? w[0][0] + w[1][0] : (w[0] || "?").slice(0, 2)).toUpperCase();
}
function logoTag(p, size = "") {
  const mono = `<i>${esc(initials(p?.name))}</i>`;
  if (!p?.logo) return `<span class="pubLogo ${size}">${mono}</span>`;
  return `<span class="pubLogo ${size}"><img src="${esc(p.logo)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('i'),{textContent:'${esc(initials(p.name))}'}))"></span>`;
}
function pubBadge(p, fallbackName = "", size = "") {
  const prof = p || { name: fallbackName, masthead: "grotesk" };
  return `<span class="pub">${logoTag(prof, size)}<span class="pubName mast-${esc(prof.masthead || "grotesk")}">${esc(prof.name || fallbackName)}</span></span>`;
}
const PAYWALL = {
  free: ["Free", "free"], registration: ["Registration", "registration"], metered: ["Metered", "metered"],
  freemium: ["Some paywalled", "freemium"], hard: ["Paywall", "hard"], premium: ["Subscriber-only", "premium"],
};
function paywallTag(kind, note = "") {
  const v = PAYWALL[kind];
  if (!v) return "";
  const lock = kind === "free" ? "" : `<svg viewBox="0 0 12 12"><rect x="2" y="5.5" width="8" height="5.5" rx="1.2"/><path d="M4 5.5V4a2 2 0 0 1 4 0v1.5"/></svg>`;
  return `<span class="pw ${v[1]}" title="${esc(note || v[0])}">${lock}${v[0]}</span>`;
}
function gauge(story, lean) {
  const d = story?.dist || { left: 0, center: 0, right: 0, unrated: 0 };
  const rated = d.left + d.center + d.right;
  const r = 38, cx = 48, cy = 48, L = Math.PI * r;
  const arc = `M${cx - r},${cy} A${r},${r} 0 0 1 ${cx + r},${cy}`;
  let off = 0, segs = "";
  if (rated) {
    for (const [k, cls] of [["left", "g-l"], ["center", "g-c"], ["right", "g-r"]]) {
      const len = (L * d[k]) / rated;
      if (len > 0) segs += `<path d="${arc}" class="${cls}" fill="none" stroke-width="9" stroke-dasharray="${Math.max(len - 1.5, 0.5)} ${L}" stroke-dashoffset="${-off}"/>`;
      off += len;
    }
  }
  let needle = "";
  if (lean !== null && lean !== undefined) {
    const a = Math.PI - ((lean + 2) / 4) * Math.PI;
    const x = cx + Math.cos(a) * (r - 14), y = cy - Math.sin(a) * (r - 14);
    needle = `<line class="g-needle" x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/><circle class="g-hub" cx="${cx}" cy="${cy}" r="3"/>`;
  }
  const pct = (n) => (rated ? Math.round((100 * n) / rated) : 0);
  const n = story?.sources || 1;
  const how = story?.method === "meaning" ? `<i class="gm meaning" title="Grouped by meaning (local multilingual model)${story.similarity ? ", similarity " + story.similarity.toFixed(2) : ""}">by meaning</i>` : story?.method === "keywords" ? `<i class="gm" title="Grouped by shared headline words (keyword mode)">by keywords</i>` : "";
  const label = `<b>${n}</b> outlet${n === 1 ? "" : "s"}<br>${rated ? `L ${pct(d.left)} · C ${pct(d.center)} · R ${pct(d.right)}%` : "none rated"}${how ? "<br>" + how : ""}`;
  const title = `Coverage spread for this story: ${d.left} left-leaning, ${d.center} centre, ${d.right} right-leaning and ${d.unrated} unrated outlets. The needle marks this publisher's own rating. Outlet-level ratings (MBFC / AllSides), not a verdict on this article.`;
  return `<div class="gauge" title="${esc(title)}"><svg viewBox="0 0 96 54" aria-hidden="true"><path d="${arc}" class="g-track" fill="none" stroke-width="9"/>${segs}${needle}</svg><small>${label}</small></div>`;
}
function indiaRelevant(e) {
  let f = sourceConfig(e.source_id);
  return (
    e.region === "India" ||
    f.region === "India" ||
    /\b(india|indian|bharat|modi|new delhi|mumbai|bengaluru|bangalore|rbi|nifty|chennai|hyderabad|kolkata|karnataka|tamil nadu|maharashtra|kerala|gujarat)\b/i.test(
      (e.title || "") + " " + (e.summary || ""),
    )
  );
}
function localSource(e) {
  let f = sourceConfig(e.source_id);
  return Boolean(f.local_state || f.local_city);
}
function canonTitle(t) {
  return String(t || "")
    .toLowerCase()
    .replace(
      /\s*[-|]\s*(reuters|bbc news|the hindu|wion|cnn-news18|ndtv)\s*$/,
      "",
    )
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
// Syndicated copies collapse into one card, so removing a card removes every copy of that headline.
let copyIndex = { src: null, map: new Map() };
function headlineCopies(e) {
  const list = ROOT.state?.entries || [];
  if (copyIndex.src !== list) {
    const map = new Map();
    for (const x of list) {
      const t = canonTitle(x.title);
      if (t.length > 23) (map.get(t) || map.set(t, []).get(t)).push(x.id);
    }
    copyIndex = { src: list, map };
  }
  const t = canonTitle(e.title);
  return t.length > 23 ? copyIndex.map.get(t) || [e.id] : [e.id];
}
function uniqueStories(items) {
  let keys = new Set(),
    res = [];
  for (let e of items) {
    let t = canonTitle(e.title),
      k =
        t.length > 23
          ? "T:" +
            t +
            ":" +
            String(e.published || e.retrieved || "").slice(0, 10)
          : "U:" +
            String(e.url || "").replace(
              /([?&])(utm_[^=&]+|fbclid|gclid)=[^&]+/g,
              "$1",
            );
    if (keys.has(k)) continue;
    keys.add(k);
    res.push(e);
  }
  return res;
}
function stories(filter = "all", max = 25, opts = {}) {
  let l = (ROOT.state?.entries || []).filter((x) => x.medium === "article");
  if (filter === "india") {
    l = l.filter((x) => ["India", "World", "Policy"].includes(desk(x)) && indiaRelevant(x));
    if (ROOT.indiaTab === "local") l = l.filter(localSource);
    else if (ROOT.indiaTab === "national") l = l.filter((x) => !localSource(x) && desk(x) === "India");
    else if (ROOT.indiaTab === "international") l = l.filter((x) => !localSource(x) && ["World", "Policy"].includes(desk(x)));
  } else if (filter === "all") {
    l = l.filter((x) => ["World", "Policy"].includes(desk(x)));
    if (ROOT.worldTab === "rest") l = l.filter((x) => !indiaRelevant(x));
    else if (ROOT.worldTab === "india") l = l.filter(indiaRelevant);
  } else if (filter === "Finance") l = l.filter((x) => ["Finance", "Energy"].includes(desk(x)));
  else if (filter === "top") l = l.filter((x) => ["World", "Policy", "India", "Finance", "Research"].includes(desk(x)));
  else l = l.filter((x) => desk(x) === filter);
  if (filter === "all" && ROOT.worldArea !== "all") {
    let dictionary = {
      Europe: /\b(ukraine|russia|europ|germany|france|britain|poland|nato|italy|spain)\b/i,
      Africa: /\b(africa|nigeria|kenya|ethiopia|sudan|somalia|congo|morocco|south africa)\b/i,
      "Middle East": /\b(iran|israel|gaza|syria|yemen|lebanon|saudi|gulf|iraq|qatar|uae)\b/i,
      "East Asia": /\b(china|japan|korea|taiwan|hong kong|beijing|tokyo)\b/i,
      "Southeast Asia": /\b(asean|philippines|indonesia|vietnam|singapore|thailand|malaysia|myanmar)\b/i,
      "Central Asia": /\b(kazakhstan|uzbekistan|kyrgyzstan|turkmenistan|tajikistan|caucasus|azerbaijan|armenia|georgia)\b/i,
      Americas: /\b(united states|u\.s\.|america|canada|mexico|brazil|argentina|colombia|chile)\b/i,
      Oceania: /\b(australia|new zealand|pacific islands|fiji|samoa)\b/i,
    };
    l = l.filter((e) => sourceConfig(e.source_id).world_region === ROOT.worldArea || dictionary[ROOT.worldArea]?.test((e.title || "") + " " + (e.summary || "")));
  }
  if (filter === "india" && ROOT.indiaStateFilter !== "all")
    l = l.filter((e) => sourceConfig(e.source_id).local_state === ROOT.indiaStateFilter || (e.title || "").toLowerCase().includes(ROOT.indiaStateFilter.toLowerCase()));
  if (filter === "india" && ROOT.indiaCityFilter !== "all")
    l = l.filter((e) => sourceConfig(e.source_id).local_city === ROOT.indiaCityFilter || (e.title || "").toLowerCase().includes(ROOT.indiaCityFilter.toLowerCase()));
  if (ROOT.search) {
    let q = ROOT.search.toLowerCase();
    l = l.filter((x) => (x.title + " " + x.summary + " " + x.source + " " + (pubOf(x)?.name || "")).toLowerCase().includes(q));
  }
  if (ROOT.bias !== "all") l = l.filter((x) => orientation(x)[1] === ROOT.bias);
  if (ROOT.pubFilters.length && !opts.ignorePub) {
    const keep = new Set(ROOT.pubFilters);
    l = l.filter((x) => keep.has(x.publisher));
  }
  if (ROOT.paywallFilter === "open") l = l.filter((x) => ["free", "registration", "unknown", "freemium"].includes(x.paywall));
  if (window.ATLASWall) l = ATLASWall.visible(l);
  if (opts.raw) return l; // every article (no syndication collapse), for counts and the coverage graph
  l = uniqueStories(l);
  if (ROOT.primaryFirst) {
    const isP = (x) => (prefOf(x.publisher) === "primary" ? 0 : 1);
    l = l.map((x, i) => [x, i]).sort((a, b) => isP(a[0]) - isP(b[0]) || a[1] - b[1]).map((x) => x[0]);
  }
  return l.slice(0, max);
}
function excerpts(s, n = 155) {
  let v = (s || "").replace(/\s+/g, " ").trim();
  return v.length > n ? v.slice(0, n).replace(/\s+\S*$/, "") + "…" : v;
}
function graphPanel(ids, deskName) {
  ROOT.graphIds = ids;
  ROOT.graphDesk = deskName;
  return panel("Coverage graph", `<div id="cgHost" class="cgHost"><p class="fine">Mapping sources…</p></div>`, `<button class="linkButton" data-cgexpand="1">Expand</button>`);
}
// v5.8: every article panel gets its own search bar (see find.js). Falls back to the plain list.
function findWrap(key, html, opts) {
  const F = window.ATLASFind;
  if (!F) return html;
  F.register(key, opts);
  return F.bar(key, opts) + `<div class="findBody" data-findbody="${esc(key)}">${html}</div>`;
}
function videoCell(e) {
  const W = window.ATLASWall;
  return `<div class="videoCell">${W ? W.removeBtn(e.id, "Remove this video from the wall") : ""}<button class="videoTile" data-video="${esc(e.video_id)}" data-name="${esc(e.title)}"><div class="thumb" style="background-image:url('${esc(e.thumbnail || `https://i.ytimg.com/vi/${e.video_id}/hqdefault.jpg`)}')"></div><span class="over">${esc(e.channel || e.source)}</span><strong>${esc(e.title)}</strong><small class="fine">${esc(ago(e.published))}</small></button></div>`;
}
function paperRow(e) {
  const W = window.ATLASWall;
  return `<div class="paper"><strong>${esc(e.title)}</strong><p>${esc(e.summary)} · ${fmt(e.published)}</p><div class="paperFoot"><a target="_blank" rel="noopener noreferrer" href="${esc(url(e.url))}">Open paper metadata ↗</a>${W ? W.removeBtn(e.id) : ""}</div></div>`;
}
function panel(title, content, aside = "", id = "") {
  return `<section class="panel" ${id ? `id="${esc(id)}"` : ""}><div class="panelHeading"><h2>${esc(title)}</h2>${aside}</div>${content}</section>`;
}
function heading(title, subtitle, kicker = "") {
  const k = /[a-z]/.test(kicker) ? kicker : kicker.charAt(0) + kicker.slice(1).toLowerCase();
  return `<div class="heroTitle"><div>${k ? `<div class="over">${esc(k)}</div>` : ""}<h1>${esc(title)}</h1>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div></div>`;
}
function empty(title, msg) {
  return `<div class="empty"><b>${esc(title)}</b><span class="fine">${esc(msg)}</span></div>`;
}
function card(e, opts = {}) {
  const p = pubOf(e);
  const [bias, cls] = orientation(e);
  const isP = prefOf(e.publisher) === "primary";
  const brief = String(e.summary || "").trim();
  const paywall = paywallTag(e.paywall, e.paywall === "premium" ? "This article is marked subscriber-only by the publisher" : p?.paywall_note);
  return `<article class="story ${isP ? "isPrimary" : ""}">
 <div class="meta">${pubBadge(p, e.source)}<span class="when" title="${esc(fmt(e.published))}">${esc(ago(e.published || e.retrieved))}</span>${leanTag(e, p, bias, cls)}${p?.factual ? `<span class="tag" title="Factual reporting rating (${esc((p.raters || []).map((r) => r.provider).join(", ") || "rater")})">Factual: ${esc(p.factual)}</span>` : ""}${p?.state_media ? `<span class="tag">State media</span>` : ""}</div>
 <h3><a href="${esc(url(e.url))}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a></h3>
 <div class="storyBrief"><p>${esc(brief ? excerpts(brief, opts.short ? 150 : 255) : "The feed supplied no excerpt. Open the publisher's article for details.")}</p></div>
 <div class="storyAside">${opts.noGauge ? "" : gauge(e.story, p?.lean)}${paywall}</div>
 <div class="storyFoot"><button class="linkButton" data-story="${esc(e.id)}">Compare coverage</button><button class="linkButton" data-diffuse="${esc(e.id)}" title="Spread outward from this article: its story, related stories on any desk, and outlets that have not covered it">Diffuse</button><span class="tag">${esc(desk(e))}</span><a target="_blank" rel="noopener noreferrer" class="fine" href="${esc(url(e.url))}">Read at ${esc(p?.name || e.source)} ↗</a>${window.ATLASWall ? ATLASWall.removeBtn(headlineCopies(e)) : ""}</div>
</article>`;
}
const KIND_GROUP = (p) => (["government", "institution", "multilateral"].includes(p.kind) ? "Government and institutions"
  : ["research", "think tank", "analysis", "academic"].includes(p.kind) ? "Research and analysis"
  : p.country === "IN" ? "Indian outlets" : "International outlets");
function primaryStrip(items, filter = "top") {
  const prefs = ROOT.state?.source_prefs || {};
  const hosts = Object.keys(prefs).filter((h) => prefs[h] === "primary");
  if (!hosts.length)
    return `<div class="primaryBar"><div class="pbHead"><span class="lbl">Primary sources</span><span class="fine">None chosen yet.</span><button class="action" data-page="sources">Choose primary sources</button></div></div>`;
  const counts = {};
  for (const e of stories(filter, 1e6, { ignorePub: true, raw: true })) counts[e.publisher] = (counts[e.publisher] || 0) + 1;
  const pub = (h) => ROOT.state?.publishers?.[h] || { name: h, masthead: "grotesk", logo: "/api/publisher-logo?host=" + encodeURIComponent(h) };
  const sel = new Set(ROOT.pubFilters);
  const present = hosts.filter((h) => counts[h]).sort((a, b) => counts[b] - counts[a]);
  // At most eight chips, plus any selected source, so the bar stays on one or two lines.
  const shown = [...new Set([...present.slice(0, 8), ...hosts.filter((h) => sel.has(h))])];
  const more = hosts.length - shown.length;
  const chip = (h) => {
    const p = pub(h);
    return `<span class="primaryChip ${sel.has(h) ? "active" : ""} ${counts[h] ? "" : "none"}"><button class="pcMain" data-pubtoggle="${esc(h)}" aria-pressed="${sel.has(h)}" title="${sel.has(h) ? "Remove" : "Add"} ${esc(p.name)} ${sel.has(h) ? "from" : "to"} the selection">${logoTag(p)}<span class="pubName mast-${esc(p.masthead)}">${esc(p.name)}</span><span class="count">${num(counts[h] || 0)}</span></button><button class="pcOnly" data-pubonly="${esc(h)}" title="Show only ${esc(p.name)}">Only</button></span>`;
  };
  const selNames = [...sel].map((h) => pub(h).name);
  let panelHtml = "";
  if (ROOT.pbOpen) {
    const groups = {};
    for (const h of hosts) (groups[KIND_GROUP(pub(h))] ||= []).push(h);
    panelHtml = `<div class="pbPanel" id="pbPanel"><div class="pbPanelHead"><input id="pbSearch" type="search" placeholder="Find a primary source" aria-label="Find a primary source"><button class="linkButton" data-page="sources">Manage primary sources</button></div>
      ${Object.entries(groups).sort().map(([g, hs]) => `<div class="pbGroup"><h4>${esc(g)}</h4>${hs.sort((a, b) => (counts[b] || 0) - (counts[a] || 0) || pub(a).name.localeCompare(pub(b).name)).map((h) => {
        const p = pub(h);
        return `<div class="pbRow ${counts[h] ? "" : "none"}" data-pbname="${esc(p.name.toLowerCase())}"><label><input type="checkbox" data-pubtoggle="${esc(h)}" ${sel.has(h) ? "checked" : ""}>${logoTag(p)}<span>${esc(p.name)}</span></label><span class="fine">${counts[h] ? `${num(counts[h])} here` : "none on this page"}</span><button class="linkButton" data-pubonly="${esc(h)}">Only</button></div>`;
      }).join("")}</div>`).join("")}</div>`;
  }
  return `<div class="primaryBar"><div class="pbHead"><span class="lbl">Primary sources</span><span class="fine">${present.length} of ${hosts.length} on this page</span>
      <button class="choice ${ROOT.primaryFirst ? "active" : ""}" data-primaryfirst="1">Primary first</button>
      <button class="choice ${sel.size ? "" : "active"}" data-pubclear="1">All sources</button>
      ${sel.size ? `<span class="pbSel">Showing only ${esc(selNames.length > 2 ? selNames.length + " sources" : selNames.join(" and "))}</span>` : ""}
      <button class="pbMore" data-pbmore="1" aria-expanded="${ROOT.pbOpen}">${ROOT.pbOpen ? "Close list" : more ? `+${more} more` : "All primary sources"}</button></div>
    <div class="pbChips">${shown.map(chip).join("")}</div>${panelHtml}</div>`;
}
function kpi(label, val, desc) {
  return `<div class="kpi"><b class="mono">${esc(val)}</b><strong>${esc(label)}</strong><small>${esc(desc)}</small></div>`;
}
function telemetryBars() {
  let rows = (ROOT.metrics?.desk_distribution || []).filter(
    (x) => x.desk !== "Video",
  );
  let max = Math.max(1, ...rows.map((x) => x.records));
  return rows.length
    ? rows
        .map(
          (r) =>
            `<div class="hBar"><span>${esc(r.desk)}</span><div class="track"><div class="fill" style="width:${(100 * r.records) / max}%"></div></div><b>${num(r.records)}</b></div>`,
        )
        .join("")
    : empty(
        "No coverage recorded",
        "Counts appear only after the collector successfully retrieves records.",
      );
}
function orientationMix(items = null) {
  let vals = { left: 0, center: 0, right: 0, unknown: 0, primary: 0 };
  for (let x of (items || ROOT.state?.entries || []).filter((e) => e.medium === "article")) vals[orientation(x)[1]]++;
  let total = Object.values(vals).reduce((a, b) => a + b, 0);
  if (!total) return empty("No articles yet", "The mix appears once articles have been collected.");
  const names = { left: "Left-leaning", center: "Centre", right: "Right-leaning", unknown: "Not rated", primary: "Official" };
  const colors = { left: "var(--left)", center: "var(--center)", right: "var(--right)", unknown: "var(--unrated)", primary: "var(--glacier)" };
  return `<div class="biasBar">${Object.keys(vals).map((k) => `<span title="${esc(names[k])} ${vals[k]}" style="background:${colors[k]};width:${(100 * vals[k]) / total}%"></span>`).join("")}</div><div class="biasKey">${Object.keys(vals).map((k) => `<span><i style="background:${colors[k]}"></i>${esc(names[k])} ${num(vals[k])}</span>`).join("")}</div><p class="fine">Articles shown, grouped by their publisher's outlet-level rating. Not rated does not mean centrist.</p>`;
}
function registryBars() {
  let rows = (ROOT.metrics?.desk_distribution || []).filter(
    (x) => x.desk !== "Video",
  );
  let max = Math.max(1, ...rows.map((x) => x.feeds));
  return rows.length
    ? rows
        .map(
          (r) =>
            `<div class="hBar"><span>${esc(r.desk)}</span><div class="track"><div class="fill" title="${num(r.healthy)} last-check successful / ${num(r.feeds)} configured" style="width:${(100 * r.feeds) / max}%;background:rgba(190,228,240,.14)"><div style="width:${r.feeds ? (100 * r.healthy) / r.feeds : 0}%;background:var(--mint);height:100%;border-radius:8px"></div></div></div><b>${num(r.healthy)}/${num(r.feeds)}</b></div>`,
        )
        .join("") +
        '<p class="fine">Green: last check succeeded. Faint: configured but not confirmed working.</p>'
    : empty("No registered sources", "Registry entries unavailable.");
}
function publicationFrequency() {
  const src = (ROOT.metrics?.publication_by_source || [])
    .filter((x) => x.last_14d > 0)
    .slice(0, 14);
  if (!src.length)
    return empty(
      "No published dates available",
      "This chart will populate from actual article publication timestamps once feeds are retrieved.",
    );
  const max = Math.max(1, ...src.map((x) => x.last_14d));
  return (
    src
      .map(
        (x) =>
          `<div class="hBar" style="grid-template-columns:180px minmax(30px,1fr) 45px"><span title="${esc(x.name)}">${esc(excerpts(x.name, 28))}</span><div class="track"><div class="fill" style="width:${(100 * x.last_14d) / max}%;background:#4e8da0"></div></div><b>${num(x.last_14d)}</b></div>`,
      )
      .join("") +
    `<p class="fine">Counts within the last 14 days of retained, timestamped source items. Not publisher-wide output.</p>`
  );
}
function svgPlot() {
  let points = (ROOT.metrics?.timeline || []).slice(-72),
    w = 700,
    h = 208,
    p = { l: 38, r: 12, t: 16, b: 33 };
  if (!points.length)
    return empty(
      "No completed feed checks",
      "Start the server, then refresh to populate an actual historical collection graph.",
    );
  let max = Math.max(
    2,
    ...points.map((x) => Math.max(x.success + x.failed, x.new)),
  );
  let x = (i) =>
      points.length === 1
        ? w / 2
        : p.l + ((w - p.l - p.r) * i) / (points.length - 1),
    y = (v) => h - p.b - ((h - p.t - p.b) * v) / max;
  let grid = [0, 0.25, 0.5, 0.75, 1]
    .map(
      (v) =>
        `<line x1="${p.l}" y1="${y(max * v)}" x2="${w - p.r}" y2="${y(max * v)}" stroke="#e4ece9"/><text x="${p.l - 8}" y="${y(max * v) + 4}" text-anchor="end" class="chartAxis">${Math.round(max * v)}</text>`,
    )
    .join("");
  let paths = [
    ["success", "#1a806b"],
    ["failed", "#c37554"],
    ["new", "#3a7db1"],
  ]
    .map(
      ([key, col]) =>
        `<polyline fill="none" stroke="${col}" stroke-width="2.7" points="${points.map((d, i) => `${x(i)},${y(d[key] || 0)}`).join(" ")}"/>`,
    )
    .join("");
  let ticks = points
    .filter(
      (_, i) =>
        i === 0 ||
        i === Math.floor(points.length / 2) ||
        i === points.length - 1,
    )
    .map((d) => {
      let i = points.indexOf(d);
      return `<text x="${x(i)}" y="${h - 7}" text-anchor="middle" class="chartAxis">${esc(d.time.slice(5, 16).replace("T", " "))}</text>`;
    })
    .join("");
  return `<div class="chart"><svg role="img" aria-label="Verified source request history, successful, failed and newly ingested records" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}${paths}${points.map((d, i) => ["success", "failed", "new"].map((k, j) => `<circle cx="${x(i)}" cy="${y(d[k] || 0)}" r="4" fill="${["#1a806b", "#c37554", "#3a7db1"][j]}"><title>${esc(d.time)} · ${k}: ${d[k] || 0}</title></circle>`).join("")).join("")}${ticks}</svg></div><div class="chartKey"><span><i style="background:#1a806b"></i>Successful requests</span><span><i style="background:#c37554"></i>Failed requests</span><span><i style="background:#3a7db1"></i>New database records</span></div>`;
}
function dashboard() {
  let m = ROOT.metrics || {}, src = m.sources || [], healthy = src.filter((x) => x.last_result === "ok").length, run = m.latest_run || {};
  let lastRun = m.latest_run?.finished || m.latest_run?.started;
  const W = window.ATLASWall;
  const top = stories("top", 60);
  let lead = top.slice().sort((a, b) => (b.story?.sources || 1) - (a.story?.sources || 1))[0];
  let rest = top.filter((x) => x !== lead).slice(0, 7);
  const pool = W?.shuffled("room") ? stories("top", 400) : top;
  if (W?.shuffled("room")) {
    // A fresh deal: the lead comes from the widely covered stories, the list from everything held.
    const wide = pool.filter((x) => (x.story?.sources || 1) > 1);
    lead = W.arrange(wide.length ? wide : pool, "room", 1)[0];
    rest = W.arrange(pool.filter((x) => x !== lead), "room", 7);
  }
  const roomAside = `${W ? W.restoreLine() + W.dice("room", pool.length) : ""}`;
  const now = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  return `<div class="roomHead"><div><div class="over">${esc(now)}</div><h1>What the world is covering</h1></div><div class="roomStats">
   <div><b>${num(m.stored_entries)}</b><span>records held</span></div>
   <div><b>${num(healthy)}<em>/${num(m.configured_sources)}</em></b><span>feeds healthy</span></div>
   <div><b>${lastRun ? esc(ago(lastRun)) : "never"}</b><span>last collection</span></div></div></div>
  ${primaryStrip(top, "top")}
  <div class="two"><div class="stack">
   ${lead ? `<section class="leadStory panel">${card(lead)}</section>` : ""}
   ${panel(W?.shuffled("room") ? "A fresh deal" : "Most covered now", findWrap("room", rest.length ? `<div class="newsList">${rest.map((e) => card(e, { short: true })).join("")}</div>` : empty("No headlines yet", "Press Refresh feeds. Sanjaya never invents headlines."),
     { label: "headlines", desk: "World", ids: () => stories("top", 1e6, { raw: true, ignorePub: true }).map((e) => e.id), item: (e) => card(e, { short: true }), wrap: (h) => `<div class="newsList">${h}</div>` }), `<span class="panelTools">${roomAside}<button class="linkButton" data-page="news">Open World</button></span>`)}
  </div><div class="stack">
   ${panel("Earth watch", `<div id="roomEarth" class="roomEarth"><p class="fine">Loading hazard catalogue…</p></div>`, `<button class="linkButton" data-page="earth">Open</button>`)}
   ${panel("Political spread of today's coverage", orientationMix(top))}
   ${graphPanel(stories("top", 1e6, { raw: true, ignorePub: true }).map((e) => e.id), "World")}
   ${panel("Collection health", `<div class="smallStats"><span><b>${num(run.succeeded || 0)}</b> passed</span><span><b>${num(run.failed || 0)}</b> failed</span><span><b>${num(run.inserted || 0)}</b> new</span></div>${svgPlot()}`, `<button class="linkButton" data-page="coverage">Audit</button>`)}
   ${panel("Live TV", `<p class="fine">${(ROOT.state?.live_channels || []).filter((c) => c.state === "live").length} verified live streams · ${num(ROOT.state?.video_audit?.playable || 0)} playable uploads</p><button class="action" data-page="media">Open live wall</button>`)}
  </div></div>`;
}
async function roomEarth() {
  const el = $("#roomEarth");
  if (!el) return;
  try {
    const d = await api("/api/earth/hazards");
    if (!$("#roomEarth")) return;
    const ev = d.events || [];
    if (!ev.length) {
      el.innerHTML = `<p class="fine">${d.pending ? "Retrieving GDACS, NASA EONET and USGS…" : esc(d.error || "No events returned.")}</p>`;
      if (d.pending) setTimeout(roomEarth, 4000);
      return;
    }
    const sev = ev.filter((e) => ["red", "orange"].includes(e.level)).slice(0, 4);
    const india = d.india || [];
    el.innerHTML = `<div class="hzCounts">${Object.entries(d.counts || {}).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, n]) => `<span class="hz hz-${esc(k)}"><b>${num(n)}</b>${esc(k)}</span>`).join("")}</div>${sev.length ? `<div class="hzList">${sev.map((e) => `<a class="hzRow" href="${esc(url(e.url))}" target="_blank" rel="noopener noreferrer"><i class="lvl ${esc(e.level)}"></i><span>${esc(e.title)}</span><small>${esc(e.source)}</small></a>`).join("")}</div>` : ""}<p class="fine">${india.length ? `${india.length} active event${india.length === 1 ? "" : "s"} in or near India.` : "No active provider events inside India's bounding box."}</p>`;
  } catch (e) {
    el.innerHTML = `<p class="fine">Hazard feeds unavailable: ${esc(e.message)}</p>`;
  }
}
function newsDesk(filter) {
  let labels = {
    all: ["World", "International reporting. India-related stories are separated by default."],
    india: ["India", "National reporting, regional cities and India in global coverage."],
    Technology: ["Technology and science", "Technology policy, AI, semiconductors and engineering."],
    Finance: ["Finance, markets and energy", "India and global markets, trade, energy and macroeconomics."],
  };
  let [title, desc] = labels[filter];
  const W = window.ATLASWall, deskKey = "desk:" + filter;
  let current = stories(filter, 110);
  const deskPool = W?.shuffled(deskKey) ? stories(filter, 1000) : current;
  if (W?.shuffled(deskKey)) current = W.arrange(deskPool, deskKey, 110);
  let tabs =
    filter === "all"
      ? `<div class="filterTabs" aria-label="Global coverage"><button class="choice ${ROOT.worldTab === "rest" ? "active" : ""}" data-worldtab="rest">Rest of world</button><button class="choice ${ROOT.worldTab === "india" ? "active" : ""}" data-worldtab="india">India in world media</button><button class="choice ${ROOT.worldTab === "all" ? "active" : ""}" data-worldtab="all">Everything</button></div>`
      : filter === "india"
        ? `<div class="filterTabs" aria-label="India coverage"><button class="choice ${ROOT.indiaTab === "all" ? "active" : ""}" data-indiatab="all">All India</button><button class="choice ${ROOT.indiaTab === "national" ? "active" : ""}" data-indiatab="national">National</button><button class="choice ${ROOT.indiaTab === "local" ? "active" : ""}" data-indiatab="local">Cities and states</button><button class="choice ${ROOT.indiaTab === "international" ? "active" : ""}" data-indiatab="international">India abroad</button></div>`
        : "";
  let locFilters = "";
  if (filter === "all") {
    locFilters = `<label class="filterLabel">Region <select id="worldArea"><option value="all">All regions</option>${["Europe", "Africa", "Middle East", "East Asia", "Southeast Asia", "Central Asia", "Americas", "Oceania"].map((n) => `<option value="${esc(n)}" ${ROOT.worldArea === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`;
  }
  if (filter === "india") {
    let configs = (ROOT.state?.registry?.feeds || []).filter((x) => x.local_state), sts = [...new Set(configs.map((x) => x.local_state))].sort();
    let cts = [...new Set(configs.filter((x) => ROOT.indiaStateFilter === "all" || x.local_state === ROOT.indiaStateFilter).map((x) => x.local_city).filter(Boolean))].sort();
    locFilters = `<label class="filterLabel">State <select id="indiaStateFilter"><option value="all">All states</option>${sts.map((st) => `<option ${ROOT.indiaStateFilter === st ? "selected" : ""} value="${esc(st)}">${esc(st)}</option>`).join("")}</select></label><label class="filterLabel">City <select id="indiaCityFilter"><option value="all">All cities</option>${cts.map((c) => `<option ${ROOT.indiaCityFilter === c ? "selected" : ""} value="${esc(c)}">${esc(c)}</option>`).join("")}</select></label>`;
  }
  const blocked = Object.values(ROOT.state?.source_prefs || {}).filter((v) => v === "blocked").length;
  return (
    heading(title, desc) + primaryStrip(current, filter) + tabs +
    `<div class="filters">${locFilters}<select id="sourceBias" aria-label="Publisher lean"><option value="all">Any publisher lean</option>${[["left", "Left-leaning"], ["center", "Centre"], ["right", "Right-leaning"], ["unknown", "Not rated"], ["primary", "Official sources"]].map((x) => `<option value="${x[0]}" ${ROOT.bias === x[0] ? "selected" : ""}>${x[1]}</option>`).join("")}</select><select id="paywallFilter" aria-label="Paywall"><option value="all">Any access</option><option value="open" ${ROOT.paywallFilter === "open" ? "selected" : ""}>Hide paywalled</option></select></div>
     <div class="deskLine"><p class="fine">${W?.shuffled(deskKey) ? `${num(current.length)} headlines dealt at random from ${num(deskPool.length)}` : `${num(current.length)} distinct headlines`}${blocked ? ` · ${blocked} blocked publisher${blocked === 1 ? "" : "s"} hidden` : ""}. The gauge shows which side of the spectrum is covering each story.</p><span class="panelTools">${W ? W.restoreLine() + W.dice(deskKey, deskPool.length) : ""}</span></div>
     <div class="two"><div>${findWrap(deskKey, current.length ? `<div class="newsList">${current.map((e) => card(e)).join("")}</div>` : empty("No matching stories", "Try another tab or filter, or check Coverage audit for feed errors."),
       { label: `${title} articles`, desk: { all: "World", india: "India", Technology: "Technology", Finance: "Finance" }[filter] || "World", wide: true,
         ids: () => stories(filter, 1e6, { raw: true }).map((e) => e.id), item: (e) => card(e), wrap: (h) => `<div class="newsList">${h}</div>` })}</div>
     <aside class="stack">${panel("Political spread of this view", orientationMix(current))}${graphPanel(stories(filter, 1e6, { raw: true, ignorePub: true }).map((e) => e.id), { all: "World", india: "India", Technology: "Technology", Finance: "Finance" }[filter] || "World")}${panel("Reading the gauge", `<div class="gaugeDemo">${gauge({ sources: 8, dist: { left: 3, center: 3, right: 2, unrated: 0 } }, -1)}<p class="fine">Arcs show the share of left-leaning, centre and right-leaning outlets covering the same story in Sanjaya. The needle is this publisher's own rating. Ratings come from Media Bias/Fact Check and AllSides and describe outlets, not articles.</p></div>${window.ATLASLean ? ATLASLean.summary() : ""}`)}${panel("Source coverage", telemetryBars(), `<button data-page="coverage" class="linkButton">Audit</button>`)}</aside></div>`
  );
}
function sourceTable() {
  let rows = ROOT.metrics?.sources || [];
  return `<div class="tableWrap"><table class="auditTable"><thead><tr><th>Source / category</th><th>Last attempt</th><th>Result</th><th>Stored</th><th>Returned / new</th><th>Latency</th></tr></thead><tbody>${rows.map((x) => `<tr><td>${esc(x.name)}<small>${esc(x.desk)} · ${esc(x.mode)}</small></td><td>${ago(x.last_attempt)}<small>${x.last_attempt ? fmt(x.last_attempt) : "Never checked"}</small></td><td><span class="tdstatus ${x.last_result === "ok" ? "ok" : "error"}">${esc(x.last_result === "ok" ? "OK" : x.last_result === "never" ? "PENDING" : "ERROR")}</span>${x.error ? `<small title="${esc(x.error)}">${esc(excerpts(x.error, 90))}</small>` : ""}</td><td>${num(x.records)}</td><td>${num(x.last_returned)} / ${num(x.last_new)}</td><td>${x.latency_ms != null ? `${Math.round(x.latency_ms)}ms` : "—"}</td></tr>`).join("")}</tbody></table></div>`;
}
function audit() {
  let m = ROOT.metrics || {},
    r = m.latest_run || {},
    total = m.totals || {};
  return (
    heading(
      "Coverage & refresh audit",
      "Nothing on this page is simulated. Every plotted value comes from a completed SQLite ingestion attempt.",
      "OBSERVABILITY · TRANSPARENT DATA PROVENANCE",
    ) +
    `<div class="kpirow">${kpi("Tracked feeds", num(m.configured_sources), "Registered RSS, YouTube and research endpoints")}${kpi("Requests logged", num(total.attempts), "Recent completed attempted retrievals")}${kpi("Successful requests", num(total.succeeded), "Not equivalent to unique new stories")}${kpi("Failed requests", num(total.failed), "Investigate source errors below")}</div><div class="twoEqual">${panel("Refresh-history plot", svgPlot(), `<span class="fine">Latest 72 active minute buckets · UTC</span>`)}${panel("Retrieved records by desk", telemetryBars(), `<span class="fine">Locally retained entries</span>`)}</div><div class="twoEqual" style="margin-top:18px">${panel("Registered source coverage & latest health", registryBars(), `<span class="fine">Successful / registered</span>`)}${panel("Publication frequency · last 14 days", publicationFrequency(), `<span class="fine">Only dated retrieved records</span>`)}</div><div class="panel" style="margin-top:18px"><div class="panelHeading"><h2>Collection runs</h2><span class="fine">Started → finished · fresh checks</span></div>${(m.runs || []).length ? `<div class="tableWrap"><table class="auditTable"><thead><tr><th>Started</th><th>Completed</th><th>State</th><th>Passed</th><th>Failed</th><th>Returned</th><th>New</th></tr></thead><tbody>${m.runs.map((x) => `<tr><td>${fmt(x.started)}</td><td>${fmt(x.finished)}</td><td>${esc(x.status)}</td><td>${num(x.succeeded)}</td><td>${num(x.failed)}</td><td>${num(x.returned)}</td><td>${num(x.inserted)}</td></tr>`).join("")}</tbody></table></div>` : empty("No run history", "The backend will log each collection cycle after starting.")}</div><div class="panel" style="margin-top:18px">${panel("Per-source status & coverage", sourceTable()).replace('<section class="panel"', "<section").replace("</section>", "")}</div><div class="banner" style="margin-top:17px">${esc(m.method || "Metrics represent actual ingestion records; configured feeds do not establish successful connectivity.")}</div>`
  );
}
function media() {
  const live = ROOT.state?.live_channels || [];
  const on = live.filter((c) => c.state === "live" && /^[A-Za-z0-9_-]{11}$/.test(c.video_id || ""));
  const off = live.filter((c) => !on.includes(c));
  const W = window.ATLASWall;
  const allVideos = (ROOT.state?.entries || []).filter((e) => e.medium === "video" && e.video_id && !W?.isHidden(e.id));
  const videos = W ? W.arrange(allVideos, "videos", 24) : allVideos.slice(0, 24);
  const audit = ROOT.state?.video_audit || {};
  const hidden = (audit.pending || 0) + (audit.unavailable || 0) + (audit.blocked || 0);
  const tile = (c, verified) => `<div class="station"><div class="stationTop"><div><strong>${esc(c.name)}</strong></div><span class="stationStatus ${verified ? "live" : ""}">${verified ? "Live now" : "Recorded stream"}</span></div><div class="liveDisplay" style="background-image:url('https://i.ytimg.com/vi/${esc(verified ? c.video_id : c.fallback_id)}/hqdefault.jpg')"><button class="playBtn" aria-label="Play ${esc(c.name)}" ${verified ? `data-stream="${esc(c.id)}"` : `data-fallback="${esc(c.id)}"`}></button><div><b>${esc(excerpts(verified ? c.title || c.name : c.fallback_title || c.name, 90))}</b><p>${esc(c.description || c.region || "")}</p></div></div><div class="stationActions"><button class="action" data-openlive="${esc(c.id)}">Official page ↗</button><small>Checked ${esc(ago(c.checked))}</small></div></div>`;
  const recorded = off.filter((c) => c.fallback_playable && c.fallback_id);
  const quiet = off.filter((c) => !recorded.includes(c));
  return (
    heading("Live TV and video", "Only streams YouTube confirms are live, and uploads it confirms are public and embeddable, are shown.") +
    `<div class="filters"><button id="liveCheck" class="action primary"><svg><use href="#i-refresh"/></svg>Re-check live streams</button><button id="videoCheck" class="action">Re-verify uploads</button><span class="fine">${on.length} live · ${num(audit.playable || 0)} playable uploads${hidden ? ` · ${num(hidden)} hidden (${num(audit.pending || 0)} awaiting check, ${num((audit.unavailable || 0) + (audit.blocked || 0))} removed or not embeddable)` : ""}</span></div>
     ${on.length || recorded.length ? `<div class="liveWall">${on.map((c) => tile(c, true)).join("")}${recorded.map((c) => tile(c, false)).join("")}</div>` : `<div class="panel" style="margin-bottom:16px">${empty("No channel is verified live right now", "Sanjaya checks each broadcaster's official YouTube live page. Use Re-check, or open a channel's official page below.")}</div>`}
     ${quiet.length ? `<div class="panel" style="margin-bottom:16px"><div class="panelHeading"><h2>Not live right now</h2><span class="fine">No verified stream at last check</span></div><div class="offAir">${quiet.map((c) => `<button class="action" data-openlive="${esc(c.id)}">${esc(c.name)} ↗</button>`).join("")}</div></div>` : ""}
     <section class="panel reelPanel" id="reelHost" style="margin-bottom:16px"></section>
     ${panel("Recent broadcaster uploads", findWrap("videos", videos.length ? `<div class="videoRail">${videos.map(videoCell).join("")}</div>` : empty(hidden ? "Uploads are being verified" : "No uploads yet", hidden ? "Sanjaya only lists a video after YouTube confirms it can be played here. This runs after each collection." : "Video feeds need YouTube to be reachable from the server."),
       { label: "uploads", web: false, webNote: "Sanjaya can only collect videos from the broadcaster channels it follows.", ids: () => allVideos.map((e) => e.id), item: videoCell, wrap: (h) => `<div class="videoRail">${h}</div>` }), `<span class="panelTools"><span class="fine">Verified playable</span>${W ? W.dice("videos", allVideos.length) : ""}</span>`)}
     <div class="twoEqual" style="margin-top:16px">${panel("Play a YouTube link", `<div class="filters"><input id="videoUrl" class="field" style="flex:1" placeholder="https://youtube.com/watch?v=…"><button id="playCustom" class="action">Play</button></div><p class="fine">Plays through YouTube's privacy-enhanced embed. Availability and ads remain with the broadcaster.</p>`)}${panel("Social monitor", `<p class="fine">Public Bluesky posts, or a link out to an X profile.</p><div class="filters"><input id="socialName" style="flex:1" placeholder="Bluesky handle or @X username"><button id="openSocial" class="action">Open</button></div><div id="socialOutput" class="fine"></div>`)}</div>`
  );
}
function papers() {
  const W = window.ATLASWall;
  const all = (ROOT.state?.entries || []).filter((e) => e.medium === "paper" && !W?.isHidden(e.id));
  let ps = W ? W.arrange(all, "papers", 30) : all.slice(0, 30);
  return ps.length
    ? ps
        .map(
          paperRow,
        )
        .join("")
    : empty(
        "Papers not yet ingested",
        "OpenAlex queries update less often than reporting sources.",
      );
}
function research() {
  const W = window.ATLASWall;
  const allAnalysis = (ROOT.state?.entries || []).filter((e) => e.medium === "article" && ["analysis", "research", "primary"].includes(e.tier) && !W?.isHidden(e.id));
  let analysis = W ? W.arrange(allAnalysis, "analysis", 35) : allAnalysis.slice(0, 35);
  const paperCount = (ROOT.state?.entries || []).filter((e) => e.medium === "paper").length;
  return (
    heading(
      "Research & deep analysis",
      "Separate think-tank perspectives and scholarly metadata from high-frequency journalism.",
      "ORF · TAKSHASHILA · E-IR · OPENALEX",
    ) +
    `<div class="two"><div class="stack">${panel("Analysis, policy and institutional sources", findWrap("analysis", analysis.length ? `<div class="newsList">${analysis.map((e) => card(e)).join("")}</div>` : empty("Analysis feeds pending", "The configured think-tank RSS feeds have not yet returned entries."),
       { label: "analysis articles", desk: "Policy", ids: () => allAnalysis.map((e) => e.id), item: (e) => card(e), wrap: (h) => `<div class="newsList">${h}</div>` }), W ? `<span class="panelTools">${W.restoreLine()}${W.dice("analysis", allAnalysis.length)}</span>` : "")}</div><aside class="stack">${panel("Academic research", findWrap("papers", papers(), { label: "papers", web: false, webNote: "For new papers, search in Research radar.",
       ids: () => (ROOT.state?.entries || []).filter((e) => e.medium === "paper" && !W?.isHidden(e.id)).map((e) => e.id), item: paperRow, wrap: (h) => h }), W ? W.dice("papers", paperCount) : "")}${panel("How to interpret research", `<p class="fine">Academic credentials do not automatically establish neutrality. Evaluate assumptions, methods, evidence, funding and date. A paper's bibliographic metadata alone is not a full summary.</p>`)}</aside></div>`
  );
}
function ccc() {
  return (
    heading(
      "Continental Convergence Charter",
      "Retained as an optional, static research archive. The main platform does not automatically interpret every event through CCC.",
      "ARCHIVAL REFERENCE",
    ) +
    `<div class="panel"><h2>June 2025 manuscript</h2><p class="muted">The original framework is retained for historical comparison and controlled research. Further expansion is intentionally out of scope for the general monitoring platform.</p><a class="archiveLink" target="_blank" rel="noopener noreferrer" href="/CCC_June_2025.pdf">Open CCC manuscript (PDF) ↗</a><a class="archiveLink" href="/legacy_v2.html">Open original CCC research view ↗</a></div>`
  );
}
// Layered satellite map. We never manufacture heat fields from point locations.
function mapLayout() {
  return (
    heading("Satellite atlas", "Satellite basemaps and first-party hazard layers. India's boundary is drawn from Survey of India data on every basemap.") +
    `<div class="two" style="grid-template-columns:minmax(0,2.2fr) minmax(290px,.7fr)"><div class="stack"><div class="panel" style="padding:12px"><div class="filterTabs" style="margin-bottom:10px"><button class="choice ${ROOT.mapMode === "satellite" ? "active" : ""}" data-mapmode="satellite">Satellite</button><button class="choice ${ROOT.mapMode === "street" ? "active" : ""}" data-mapmode="street">Street</button><button class="choice ${ROOT.mapMode === "nasa" ? "active" : ""}" data-mapmode="nasa">NASA composite</button><button class="choice ${ROOT.mapMode === "daily" ? "active" : ""}" data-mapmode="daily">NASA daily image</button></div><div class="mapFrame" style="height:620px"><canvas id="satCanvas" class="nativeTileCanvas" aria-label="Pan-and-zoom satellite map. Drag to pan, scroll to zoom."></canvas><div class="nativeMapTools"><button id="satZoomIn" title="Zoom in">+</button><button id="satZoomOut" title="Zoom out">−</button><button id="satTileRetry" title="Retry failed tiles">↻</button></div><div id="mapFallback" class="mapEmpty" hidden><div><strong>Map providers unreachable</strong><p>Tiles come from Esri, OpenStreetMap and NASA through the local server. Check the server's internet access.</p><a href="https://worldview.earthdata.nasa.gov/" target="_blank" rel="noopener noreferrer" class="action">NASA Worldview ↗</a></div></div><div class="mapOverlayInfo" id="mapInfo">Provider-attributed imagery.</div></div></div>${panel("About these layers", `<p class="fine"><strong>Satellite:</strong> Esri World Imagery. <strong>Street:</strong> OpenStreetMap, whose borders follow on-the-ground control; Sanjaya overlays India's official boundary (Survey of India, via DataMeet) so the national outline is correct on every basemap.</p><p class="fine"><strong>Thermal anomalies:</strong> NASA GIBS VIIRS hotspots, not fire intensity. <strong>Shaking:</strong> USGS ShakeMap contours where published.</p><p class="fine">For wind, rain, temperature and ocean currents, use <button class="linkButton" data-page="earth">Earth watch</button>.</p>`)}</div><aside class="satControls">${panel("Focus", `<div class="mapPick">${[["world", "World"], ["india", "India"], ["europe", "Europe"], ["gulf", "Gulf"], ["indo", "Indo-Pacific"]].map((x) => `<button data-mapfocus="${x[0]}">${x[1]}</button>`).join("")}</div><label class="fine" style="display:flex;gap:8px;align-items:center;margin-top:12px"><input type="checkbox" id="indiaBoundary" ${ROOT.indiaBoundary !== false ? "checked" : ""}> Official India boundary (Survey of India)</label>`)}${panel("Environmental layers", `<div class="layerBlock"><strong>Satellite measurements</strong><label><input type="checkbox" id="fireRaster" ${ROOT.fireLayer ? "checked" : ""}> NASA VIIRS thermal anomalies</label></div><div class="layerBlock"><strong>Event geometry</strong><label><input id="fireDanger" type="checkbox" ${ROOT.effisFwi ? "checked" : ""}> EFFIS fire-weather index (Europe)</label><label><input id="burnScar" type="checkbox" ${ROOT.effisBurn ? "checked" : ""}> EFFIS burned area (Europe)</label><label><input id="eventPolygon" type="checkbox" ${ROOT.eventsLayer ? "checked" : ""}> NASA EONET wildfire polygons</label><label><input id="quakePins" type="checkbox" ${ROOT.earthLayer ? "checked" : ""}> USGS earthquake epicentres</label></div><div class="layerBlock"><strong>Acquisition date</strong><select id="rasterDate" class="field" style="width:100%">${[0, 1, 2, 3, 4, 5, 6].map((i) => `<option value="${i}" ${ROOT.dateOffset === i ? "selected" : ""}>${i === 0 ? "Today (may be incomplete)" : i + " day" + (i > 1 ? "s" : "") + " ago"}</option>`).join("")}</select></div><div class="smallStats" style="margin-top:12px"><button id="mapRefresh" class="action">Update hazards</button><button id="mapDiagnose" class="action">Test tiles</button></div><div id="mapHealth" class="fine">No tile requests yet.</div><pre id="mapDiagnostics" class="mapDiagnostics" aria-live="polite"></pre><p id="mapCatalogStatus" class="fine"></p>`)}${panel("USGS earthquakes", `<div id="quakeList">${empty("Loading", "USGS catalogue pending.")}</div><p id="shakemapState" class="fine"></p>`)}</aside></div>`
  );
}
const MODULES = { emergency: ["ATLASEmergency", "emergency.js"], earth: ["ATLASEarth", "earth_watch.js"], sources: ["ATLASSources", "sources.js"], lm: ["ATLASLM", "lm.js"], radar: ["ATLASRadar", "radar.js"], wiki: ["ATLASWiki", "wiki.js"], about: ["ATLASAbout", "about.js"], conflict: ["ATLASConflict", "conflict_watch.js"], mygov: ["ATLASMyGov", "mygov.js"], constellation: ["ATLASConstellation", "article_constellation.js"], investigate: ["IndiaInvestigation", "india_investigation.js"], geopolitics: ["ATLASResearch", "expert_panels.js"], macro: ["ATLASResearch", "expert_panels.js"] };
function pageError(v, err) {
  const mod = MODULES[v];
  const missing = mod && !window[mod[0]];
  const msg = missing ? `The page script ${mod[1]} did not load in this browser, so ${pages[v][0]} cannot be drawn.` : `${pages[v][0]} hit an error while drawing: ${err?.message || err}`;
  console.error("[Sanjaya]", msg, err);
  return `<div class="panel pageFail"><h2>${esc(pages[v][0])} could not be shown</h2><p>${esc(msg)}</p>${err?.stack ? `<pre class="mapDiagnostics">${esc(String(err.stack).split("\n").slice(0, 4).join("\n"))}</pre>` : ""}<p class="fine">${missing ? "Hard-refresh the page (Ctrl+Shift+R). If this stays, check that the file exists in the static folder and that a browser extension is not blocking it." : "Other pages are unaffected. Please send this message along with a screenshot."}</p><button class="action" data-page="${esc(v)}">Try again</button></div>`;
}
function safeMount(v, fn) {
  setTimeout(() => {
    const fail = (e) => {
      if (ROOT.view === v) $("#main").innerHTML = pageError(v, e);
    };
    try {
      const r = fn();
      if (r && typeof r.catch === "function") r.catch(fail);
    } catch (e) {
      fail(e);
    }
  }, 20);
}
function render() {
  let main = $("#main"), v = ROOT.view;
  for (const f of [() => window.ATLASTileMap?.unmount(), () => window.ATLASConflict?.destroy(), () => window.ATLASConstellation?.destroy(), () => window.ATLASEarth?.destroy(), () => window.ATLASLM?.destroy(), () => window.ATLASRadar?.destroy(), () => window.IndiaInvestigation?.destroy()])
    try { f(); } catch (e) { console.warn("[Sanjaya] cleanup", e); }
  $("#pageTitle").textContent = pages[v][0];
  $("#pageKicker").textContent = pages[v][1];
  document.title = pages[v][0] + " · Sanjaya";
  $$(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === v));
  main.dataset.view = v;
  const mod = MODULES[v];
  if (mod && !window[mod[0]]) {
    main.innerHTML = pageError(v);
    return;
  }
  let content;
  try {
    content =
      v === "room" ? dashboard() : v === "news" ? newsDesk("all") : v === "india" ? newsDesk("india") : v === "technology" ? newsDesk("Technology") : v === "finance" ? newsDesk("Finance")
      : v === "map" ? mapLayout() : v === "investigate" ? IndiaInvestigation.layout(ROOT) : v === "constellation" ? ATLASConstellation.layout() : v === "media" ? media()
      : v === "coverage" ? audit() : v === "research" ? research() : v === "earth" ? ATLASEarth.layout() : v === "sources" ? ATLASSources.layout() : v === "lm" ? ATLASLM.layout() : v === "radar" ? ATLASRadar.layout() : v === "wiki" ? ATLASWiki.layout() : v === "about" ? ATLASAbout.layout()
      : ["geopolitics", "macro", "mygov", "emergency", "conflict"].includes(v) ? `<div class="pageLoading">Loading ${esc(pages[v][0])}…</div>` : ccc();
  } catch (e) {
    main.innerHTML = pageError(v, e);
    return;
  }
  main.innerHTML = content;
  ensureRefreshControl();
  if (v === "room") setTimeout(roomEarth, 30);
  if (["room", "news", "india", "technology", "finance"].includes(v)) setTimeout(() => window.ATLASGraph?.attach(ROOT), 40);
  if (v === "emergency") safeMount(v, () => window.ATLASEmergency.mount());
  if (v === "conflict") safeMount(v, () => window.ATLASConflict.mount());
  if (v === "mygov") safeMount(v, () => window.ATLASMyGov.mount());
  if (v === "map") setTimeout(() => window.ATLASTileMap?.mount(ROOT), 50);
  if (v === "earth") safeMount(v, () => window.ATLASEarth.mount(ROOT));
  if (v === "sources") safeMount(v, () => window.ATLASSources.mount(ROOT));
  if (v === "lm") safeMount(v, () => window.ATLASLM.mount());
  if (v === "radar") safeMount(v, () => window.ATLASRadar.mount());
  if (v === "wiki") safeMount(v, () => window.ATLASWiki.mount());
  if (v === "constellation") setTimeout(() => window.ATLASConstellation?.attach(), 30);
  if (v === "investigate") setTimeout(() => IndiaInvestigation.mount(ROOT), 50);
  if (["geopolitics", "macro"].includes(v)) safeMount(v, () => window.ATLASResearch.mount(v));
  window.ATLASFind?.apply();
  if (v === "media") setTimeout(() => { try { window.ATLASReel?.mount(); } catch (e) { console.warn("[Sanjaya] reel", e); } }, 30);
  else window.ATLASReel?.unmount?.();
}
function ensureRefreshControl() {
  const r = ROOT.metrics?.latest_run;
  const label = $("#syncLabel");
  if (label && ROOT.metrics)
    label.textContent = ROOT.metrics.server_polling ? `Collecting · ${r?.attempted || 0} checked · ${r?.inserted || 0} new` : `Updated ${ago(ROOT.metrics.last_cycle)}`;
}
document.addEventListener("atlas:wall", () => {
  if (["room", "news", "india", "technology", "finance", "research", "media"].includes(ROOT.view)) render();
});
window.ATLAS = { state: ROOT, hydrate: () => hydrate(false), ensureRefreshControl, card, pubBadge, logoTag, gauge, paywallTag, api, esc, tip, desk, ago, play: playYouTube, go: (v) => go(v) };
function go(v) {
  if (!pages[v]) return;
  ROOT.view = v;
  ROOT.search = "";
  ROOT.bias = "all";
  ROOT.pubFilters = [];
  ROOT.pbOpen = false;
  $("#storyPanel").hidden = true;
  $("#navSide").classList.remove("open");
  window.location.hash = v;
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
}
function applyHealth(ok) {
  $("#serverLED").className = "led " + (ok ? "good" : "error");
  $("#serverState").textContent = ok ? "Server connected" : "Server unreachable";
  $("#serverBadge").className = "statusPill " + (ok ? "good" : "bad");
  $("#serverBadge").textContent = ok ? "Online" : "Offline";
  let m = ROOT.metrics || {};
  $("#sourcesBadge").textContent = (m.sources || []).filter((x) => x.last_result === "ok").length + " feeds healthy";
  $("#articlesBadge").textContent = num(m.stored_entries) + " records";
  const g = ROOT.state?.grouping, gb = $("#groupingBadge");
  if (gb && g) {
    gb.hidden = false;
    gb.className = "statusPill " + (g.mode === "meaning" ? "good" : "unknown");
    gb.textContent = g.mode === "meaning" ? "Grouped by meaning" : "Keyword mode";
    gb.title = g.note || (g.mode === "meaning" ? "Stories grouped by a local multilingual model" : "Stories grouped by shared headline words. Open Language model to enable grouping by meaning.");
  }
  $("#lastCycle").textContent = "Last collection " + ago(m.last_cycle);
  if (!ok) $("#syncLabel").textContent = "Cannot reach the local server";
  else ensureRefreshControl();
}
let heartbeat = null,
  storybusy = false;
async function hydrate(first = false) {
  try {
    let responses = await Promise.all([api("/api/state"), api("/api/metrics")]);
    ROOT.state = responses[0];
    ROOT.metrics = responses[1];
    applyHealth(true);
    ensureRefreshControl();
    if (
      first ||
      ![
        "media",
        "map",
        "investigate",
        "geopolitics",
        "macro",
        "constellation",
        "mygov",
        "emergency",
        "conflict",
        "earth",
        "sources",
        "lm",
        "radar",
        "wiki",
        "about",
      ].includes(ROOT.view)
    )
      render();
    else if (ROOT.view === "emergency") window.ATLASEmergency?.refreshIfStale();
    else if (ROOT.view === "conflict") window.ATLASConflict?.refreshIfStale();
    else if (ROOT.view === "mygov") window.ATLASMyGov?.refreshIfStale();
    else if (["geopolitics", "macro"].includes(ROOT.view))
      window.ATLASResearch?.refreshIfStale(ROOT.view);
    else if (ROOT.view === "constellation")
      window.ATLASConstellation?.refreshIfStale();
    else if (ROOT.view === "media") updateLiveStatuses();
    else if (ROOT.view === "sources") window.ATLASSources?.refreshIfStale?.();
    else if (ROOT.view === "investigate")
      IndiaInvestigation.refreshIfStale(ROOT);
    return true;
  } catch (e) {
    applyHealth(false);
    if (first)
      $("#main").innerHTML = empty(
        "Unable to reach local server",
        `The HTML user interface requires Python server.py running at this address. ${e.message}`,
      );
    return false;
  }
}
function updateLiveStatuses() {
  for (let c of ROOT.state?.live_channels || []) {
    let x = $(`[data-live-status="${c.id}"]`);
    if (x)
      x.textContent =
        c.state === "live" ? "● LIVE VERIFIED" : "○ LIVE UNVERIFIED";
  }
}
async function refresh() {
  let b = $("#refreshNow");
  b.disabled = true;
  b.textContent = "Starting…";
  try {
    let out = await api("/api/refresh", "POST", {});
    tip(
      out.started
        ? "Collector started. New source attempts will appear in the audit."
        : "Collection already running. See coverage audit.",
    );
    setTimeout(() => hydrate(), 1400);
  } catch (e) {
    tip("Refresh request failed: " + e.message);
  } finally {
    setTimeout(() => {
      b.disabled = false;
      b.innerHTML = '<svg><use href="#i-refresh"/></svg>Refresh feeds';
    }, 3500);
  }
}
function parseVideo(s) {
  let t = String(s || "").trim();
  if (/^[a-zA-Z0-9_-]{11}$/.test(t)) return t;
  try {
    let u = new URL(t);
    if (u.hostname === "youtu.be") return u.pathname.split("/")[1];
    if (!/youtube(-nocookie)?\.com$/.test(u.hostname.replace(/^www\./, "")))
      return "";
    if (u.pathname.startsWith("/live/") || u.pathname.startsWith("/shorts/"))
      return u.pathname.split("/")[2];
    return u.searchParams.get("v") || "";
  } catch {
    return "";
  }
}
function playYouTube(videoId, label, verified = false, channel = null) {
  if (!/^[a-zA-Z0-9_-]{11}$/.test(videoId || "")) {
    tip("Cannot verify playable YouTube ID; open publisher channel.");
    return;
  }
  const f = document.createElement("iframe");
  f.src = window.ATLASPlayer
    ? ATLASPlayer.embedUrl(videoId)
    : `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&playsinline=1&controls=1&rel=0`;
  f.title = label;
  f.allow =
    "autoplay; encrypted-media; fullscreen; picture-in-picture; web-share";
  f.allowFullscreen = true;
  f.referrerPolicy = "strict-origin-when-cross-origin";
  let dock = $("#playerDock");
  $("#playerContent").replaceChildren(f);
  $("#playerLabel").textContent = label;
  $("#playerCaption").textContent = verified
    ? "Verified at last channel check. Live status may change; YouTube maintains the stream."
    : "Video playback, not verified live. Provider may end or block the stream.";
  dock.classList.remove("minimised");
  dock.hidden = false;
  window.ATLASPlayer?.dock(f, { videoId, label, verified, channel });
}
async function brief(id) {
  if (storybusy) return;
  storybusy = true;
  $("#storyPanel").hidden = false;
  $("#storyContent").innerHTML = '<p class="fine">Gathering coverage…</p>';
  try {
    let a = (ROOT.state?.entries || []).find((e) => e.id === id);
    let x = await api("/api/brief?id=" + encodeURIComponent(id));
    const p = x.publisher || pubOf(a) || {};
    const d = a?.story?.dist;
    const scale = [-2, -1, 0, 1, 2].map((v) => `<i class="${v === p.lean ? "on " : ""}${v < 0 ? "l" + -v : v > 0 ? "r" + v : "l0"}"></i>`).join("");
    $("#storyContent").innerHTML = `<div class="drawerTop">${pubBadge(p, x.source, "lg")}<button class="closeIcon" data-close="true">Close</button></div>
    <h2>${esc(x.title)}</h2><div class="tagline">${paywallTag(x.paywall || a?.paywall, p.paywall_note)}<span class="tag">${esc(fmt(a?.published))}</span><span class="tag">${esc(desk(a || {}))}</span></div>
    <div class="section"><h3>What the feed says</h3><p>${esc(x.digest || "No excerpt was supplied. Read the original before drawing conclusions.")}</p></div>
    <div class="section"><h3>Who is covering it</h3><p class="fine">${x.grouping === "meaning" ? "Matched by meaning with the local multilingual model; percentages are similarity to this article." : "Keyword mode: matched by shared headline words. Turn on grouping by meaning under Language model."}</p>${d ? `<div class="biasBar">${[["left", "var(--left)"], ["center", "var(--center)"], ["right", "var(--right)"], ["unrated", "var(--unrated)"]].map(([k, c]) => `<span style="background:${c};width:${(100 * d[k]) / Math.max(1, d.left + d.center + d.right + d.unrated)}%"></span>`).join("")}</div><div class="biasKey"><span><i style="background:var(--left)"></i>Left ${d.left}</span><span><i style="background:var(--center)"></i>Centre ${d.center}</span><span><i style="background:var(--right)"></i>Right ${d.right}</span><span><i style="background:var(--unrated)"></i>Not rated ${d.unrated}</span></div>` : ""}
     ${(x.related || []).length ? x.related.map((r) => `<div class="related">${logoTag(r.publisher)}<div><a href="${esc(url(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a><p class="fine">${r.similarity ? `<span class="simTag">${Math.round(r.similarity * 100)}% match</span> ` : ""}<span class="mast-${esc(r.publisher?.masthead || "grotesk")}">${esc(r.publisher?.name || r.source)}</span> · ${esc(r.publisher?.lean_label || "Not rated")}${r.publisher?.paywall && r.publisher.paywall !== "free" ? " · " + esc(PAYWALL[r.publisher.paywall]?.[0] || "") : ""}</p></div></div>`).join("") : `<p class="fine">No other publisher in Sanjaya has a closely matching headline yet.</p>`}</div>
    <div class="section"><h3>About ${esc(p.name || x.source)}</h3><div class="leanScale">${scale}</div><div class="leanLabel"><span>Left</span><span>Centre</span><span>Right</span></div>
     <p><strong>${esc(p.lean_label || "Not rated")}</strong>${(p.raters || []).length ? ` · ${p.raters.map((r) => `${esc(r.provider)}: ${esc(r.rating)}`).join(" · ")}` : ""}${p.factual ? ` · Factual reporting: ${esc(p.factual)}` : ""}${p.questionable ? " · flagged questionable by MBFC" : ""}</p>
     ${p.ownership ? `<p class="fine">Ownership: ${esc(p.ownership)}</p>` : ""}${p.rating_caveat ? `<p class="fine">${esc(p.rating_caveat)}</p>` : ""}<p class="fine">Access: ${esc(p.paywall_label || "Not classified")}${p.paywall_note ? " — " + esc(p.paywall_note) : ""}</p>
     ${p.rating_url ? `<a href="${esc(url(p.rating_url))}" target="_blank" rel="noopener noreferrer">Rating methodology ↗</a>` : ""}
     <p class="fine">Ratings describe the outlet on a US-derived left/right axis and map imperfectly onto Indian politics. They are not a verdict on this article.</p></div>
    <div class="section"><a class="action primary" href="${esc(url(a?.url))}" target="_blank" rel="noopener noreferrer">Read the original ↗</a></div>`;
  } catch (e) {
    $("#storyContent").innerHTML = '<button class="closeIcon" data-close="true">Close</button><p>' + esc(e.message) + "</p>";
  } finally {
    storybusy = false;
  }
}

async function doSocial() {
  let s = $("#socialName")?.value.trim() || "",
    out = $("#socialOutput");
  if (!s) return;
  if (s.includes(".bsky.social") || s.includes(".bsky.network")) {
    out.textContent = "Retrieving public Bluesky posts…";
    try {
      let x = await api(
        "/api/social?handle=" + encodeURIComponent(s.replace("@", "")),
      );
      out.innerHTML =
        (x.posts || [])
          .slice(0, 12)
          .map(
            (p) =>
              `<div class="paper"><strong>${esc(p.name || s)}</strong><p>${esc(p.text)}</p><a target="_blank" rel="noopener noreferrer" href="${esc(url(p.url))}">Original post ↗</a></div>`,
          )
          .join("") || "No public posts found.";
    } catch (e) {
      out.textContent = e.message;
    }
  } else {
    let u = s.replace(/^@/, "").replace(/[^a-zA-Z0-9_]/g, "");
    out.innerHTML = `X profiles may require login. <a target="_blank" rel="noopener noreferrer" href="https://x.com/${u}">Open @${esc(u)} on X ↗</a>`;
  }
}
window.addEventListener("hashchange", () => {
  let hash = location.hash.slice(1);
  if (pages[hash] && hash !== ROOT.view) go(hash);
});
document.addEventListener("click", async (ev) => {
  let b = ev.target.closest("button,[data-close]");
  if (!b) return;
  if (window.ATLASGraph?.onClick(b)) return;
  if (b.dataset.page) {
    go(b.dataset.page);
    return;
  }
  if (b.dataset.pubtoggle !== undefined) {
    const h = b.dataset.pubtoggle;
    ROOT.pubFilters = ROOT.pubFilters.includes(h) ? ROOT.pubFilters.filter((x) => x !== h) : [...ROOT.pubFilters, h];
    render();
    return;
  }
  if (b.dataset.pubonly !== undefined) {
    ROOT.pubFilters = [b.dataset.pubonly];
    render();
    return;
  }
  if (b.dataset.pubclear !== undefined) {
    ROOT.pubFilters = [];
    render();
    return;
  }
  if (b.dataset.pbmore !== undefined) {
    ROOT.pbOpen = !ROOT.pbOpen;
    render();
    if (ROOT.pbOpen) $("#pbSearch")?.focus();
    return;
  }
  if (b.dataset.primaryfirst) {
    ROOT.primaryFirst = !ROOT.primaryFirst;
    render();
    return;
  }
  if (ROOT.view === "sources" && window.ATLASSources?.onClick(ev)) return;
  if (ROOT.view === "earth" && window.ATLASEarth?.onClick(ev)) return;
  if (ROOT.view === "lm" && window.ATLASLM?.onClick(ev)) return;
  if (ROOT.view === "radar" && window.ATLASRadar?.onClick(ev)) return;
  if (b.id === "videoCheck") {
    tip("Re-verifying uploads with YouTube. Results appear after the check finishes.");
    await api("/api/verify-videos", "POST", {}).catch((e) => tip(e.message));
    setTimeout(hydrate, 6000);
    return;
  }
  if (b.id === "menuToggle") {
    $("#navSide").classList.toggle("open");
    return;
  }
  if (b.id === "fontMore" || b.id === "fontLess") {
    ROOT.font = Math.max(
      16,
      Math.min(26, ROOT.font + (b.id === "fontMore" ? 2 : -2)),
    );
    document.documentElement.style.setProperty("--font", ROOT.font + "px");
    try {
      localStorage.setItem("atlas_font", ROOT.font);
    } catch (_) {}
    return;
  }
  if (b.id === "refreshNow" || b.id === "pageRefresh") {
    refresh();
    return;
  }
  if (b.dataset.story) {
    brief(b.dataset.story);
    return;
  }
  if (b.dataset.close) {
    $("#storyPanel").hidden = true;
    return;
  }
  if (b.id === "playerClose") {
    $("#playerDock").hidden = true;
    $("#playerContent").replaceChildren();
    return;
  }
  if (b.id === "playerMin") {
    $("#playerDock").classList.toggle("minimised");
    return;
  }
  if (b.id === "liveCheck") {
    tip("Requesting official channel checks. Status may remain unverified.");
    await api("/api/refresh-live", "POST", {}).catch((e) => tip(e.message));
    setTimeout(hydrate, 3500);
    return;
  }
  if (b.dataset.stream) {
    let c = (ROOT.state?.live_channels || []).find(
      (c) => c.id === b.dataset.stream,
    );
    if (c?.state === "live")
      playYouTube(c.video_id, c.name + " · Live verified", true, c);
    return;
  }
  if (b.dataset.openlive) {
    let c = (ROOT.state?.live_channels || []).find(
      (c) => c.id === b.dataset.openlive,
    );
    if (c) window.open(url(c.official_live), "_blank", "noopener,noreferrer");
    return;
  }
  if (b.dataset.fallback) {
    let c = (ROOT.state?.live_channels || []).find(
      (c) => c.id === b.dataset.fallback,
    );
    if (c)
      playYouTube(
        c.fallback_id,
        c.name + " · Unverified archived stream",
        false,
      );
    return;
  }
  if (b.dataset.video) {
    playYouTube(b.dataset.video, b.dataset.name || "News video", false);
    return;
  }
  if (b.id === "playCustom") {
    let id = parseVideo($("#videoUrl").value);
    if (!id) tip("Enter a valid YouTube watch/live URL");
    else playYouTube(id, "Selected YouTube video", false);
    return;
  }
  if (b.id === "openSocial") {
    doSocial();
    return;
  }
  if (ROOT.view === "constellation" && window.ATLASConstellation?.onClick(ev))
    return;
  if (b.dataset.worldtab) {
    ROOT.worldTab = b.dataset.worldtab;
    render();
    return;
  }
  if (b.dataset.indiatab) {
    ROOT.indiaTab = b.dataset.indiatab;
    render();
    return;
  }
  if (
    ROOT.view === "investigate" &&
    window.IndiaInvestigation?.onClick(ev, ROOT)
  )
    return;
  if (b.dataset.mapmode) {
    ROOT.mapMode = b.dataset.mapmode;
    window.ATLASTileMap?.sync(ROOT);
    $$("[data-mapmode]").forEach((x) =>
      x.classList.toggle("active", x.dataset.mapmode === ROOT.mapMode),
    );
    return;
  }
  if (b.dataset.mapfocus) {
    window.ATLASTileMap?.focusOn(b.dataset.mapfocus);
    return;
  }
  if (b.id === "mapRefresh") {
    window.ATLASTileMap?.loadCatalogs();
    return;
  }
  if (b.id === "satTileRetry") {
    window.ATLASTileMap?.retry();
    return;
  }
  if (b.id === "satZoomIn" || b.id === "satZoomOut") {
    window.ATLASTileMap?.zoomBy(b.id === "satZoomIn" ? 1 : -1);
    return;
  }
  if (b.dataset.shakeNative !== undefined) {
    window.ATLASTileMap?.showShakeMap(Number(b.dataset.shakeNative));
    return;
  }
  if (b.id === "mapDiagnose") {
    window.ATLASTileMap?.diagnostics();
    return;
  }
  if (b.dataset.shake) {
    window.ATLASTileMap?.showShakeMap(b.dataset.shake);
    return;
  }
});
document.addEventListener("click", (e) => {
  if (
    ROOT.view === "investigate" &&
    e.target.closest("[data-indiastate]:not(button)")
  )
    IndiaInvestigation.onClick(e, ROOT);
});
document.addEventListener("change", (e) => {
  if (ROOT.view === "constellation" && window.ATLASConstellation?.onChange(e))
    return;
  if (
    ROOT.view === "investigate" &&
    window.IndiaInvestigation?.onChange(e, ROOT)
  )
    return;
  let a = e.target;
  if (a.id === "sourceBias") {
    ROOT.bias = a.value;
    render();
  }
  if (a.id === "paywallFilter") {
    ROOT.paywallFilter = a.value;
    render();
  }
  if (a.id === "indiaBoundary") {
    ROOT.indiaBoundary = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (ROOT.view === "earth" && window.ATLASEarth?.onChange?.(e)) return;
  if (ROOT.view === "sources" && window.ATLASSources?.onChange?.(e)) return;
  if (ROOT.view === "lm" && window.ATLASLM?.onChange?.(e)) return;
  if (ROOT.view === "radar" && window.ATLASRadar?.onChange?.(e)) return;
  if (a.dataset?.pubtoggle !== undefined && a.type === "checkbox") {
    const h = a.dataset.pubtoggle;
    ROOT.pubFilters = a.checked ? [...new Set([...ROOT.pubFilters, h])] : ROOT.pubFilters.filter((x) => x !== h);
    render();
    return;
  }
  if (a.id === "worldArea") {
    ROOT.worldArea = a.value;
    render();
  }
  if (a.id === "indiaStateFilter") {
    ROOT.indiaStateFilter = a.value;
    ROOT.indiaCityFilter = "all";
    render();
  }
  if (a.id === "indiaCityFilter") {
    ROOT.indiaCityFilter = a.value;
    render();
  }
  if (a.id === "fireRaster") {
    ROOT.fireLayer = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (a.id === "fireDanger") {
    ROOT.effisFwi = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (a.id === "burnScar") {
    ROOT.effisBurn = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (a.id === "eventPolygon") {
    ROOT.eventsLayer = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (a.id === "quakePins") {
    ROOT.earthLayer = a.checked;
    window.ATLASTileMap?.sync(ROOT);
  }
  if (a.id === "rasterDate") {
    ROOT.dateOffset = Number(a.value);
    window.ATLASTileMap?.sync(ROOT);
  }
});
let typing;
document.addEventListener("input", (e) => {
  if (e.target.id === "pbSearch") {
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll(".pbRow").forEach((r) => (r.hidden = !!q && !r.dataset.pbname.includes(q)));
    document.querySelectorAll(".pbGroup").forEach((g) => (g.hidden = ![...g.querySelectorAll(".pbRow")].some((r) => !r.hidden)));
    return;
  }
  if (ROOT.view === "sources" && window.ATLASSources?.onInput?.(e)) return;
  if (ROOT.view === "lm" && e.target.id === "lmThr") return window.ATLASLM?.onChange?.(e);
  if (e.target.id === "newsSearch") {
    let q = e.target.value;
    clearTimeout(typing);
    typing = setTimeout(() => {
      ROOT.search = q;
      let el = e.target;
      let pos = el.selectionStart;
      render();
      let fresh = $("#newsSearch");
      if (fresh) {
        fresh.focus();
        fresh.setSelectionRange(pos, pos);
      }
    }, 360);
  }
});
document.addEventListener("keydown", (e) => {
  if (ROOT.view === "radar" && window.ATLASRadar?.onKey?.(e)) return;
  if (e.key === "Escape" && !$("#storyPanel").hidden)
    $("#storyPanel").hidden = true;
});
async function bootstrap() {
  let hash = location.hash.slice(1);
  if (pages[hash]) ROOT.view = hash;
  try {
    ROOT.font = Math.max(
      16,
      Math.min(26, Number(localStorage.getItem("atlas_font") || 18)),
    );
  } catch (_) {}
  document.documentElement.style.setProperty("--font", ROOT.font + "px");
  await hydrate(true);
  heartbeat = setInterval(() => hydrate(false), 15000);
}
bootstrap();
