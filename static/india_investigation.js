"use strict";
/* State-level news coverage density drawn over the bundled Survey of India state map
 * (DataMeet). No external map library or tile provider is needed. */
window.IndiaInvestigation = (() => {
  let map = null,
    layer = null,
    base = null,
    selected = "",
    shapes = null,
    geomLabel = "",
    fetching = false,
    previousUpdate = 0,
    baseMode = "street",
    wind = "wind";
  const $ = (s) => document.querySelector(s),
    esc = (s) =>
      String(s ?? "").replace(
        /[&<>"']/g,
        (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
      );
  const num = (n) => Number(n || 0).toLocaleString("en-IN");
  const key = (s) =>
    String(s || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z]/g, "");
  const stateFor = (name, data) =>
    (data?.states || []).find((s) => key(s.name) === key(name)) || null;
  function layout(root) {
    return `<div class="heroTitle"><div><h1>India regional map</h1><p>Where collected Indian reporting is concentrated, state by state. Shading counts <strong>unique retrieved stories</strong> that name a place — not incidents, risk or hazard.</p></div></div>
 <div class="panel indiaMapPanel"><div class="panelHeading"><h2>Coverage density</h2><span id="indiaMapStatus" class="fine">Preparing boundaries…</span></div>
 <div class="filters"><label class="filterLabel">Window <select id="indiaDays"><option value="1" ${root.indiaDays === 1 ? "selected" : ""}>24 hours</option><option value="7" ${root.indiaDays === 7 ? "selected" : ""}>7 days</option><option value="30" ${root.indiaDays === 30 ? "selected" : ""}>30 days</option><option value="90" ${root.indiaDays === 90 ? "selected" : ""}>90 days</option></select></label>
 <label class="filterLabel">Topic <select id="indiaTopic">${[["all", "All topics"], ["politics", "Politics"], ["economy", "Economy"], ["weather", "Weather"], ["infrastructure", "Infrastructure"], ["technology", "Technology"], ["security", "Security"]].map(([v, t]) => `<option value="${v}" ${root.indiaTopic === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
 <label class="filterLabel">Attribution <select id="indiaScope"><option value="all" ${root.indiaScope === "all" ? "selected" : ""}>Place named or local feed</option><option value="explicit" ${root.indiaScope === "explicit" ? "selected" : ""}>Place named only</option></select></label>
 <button class="action" id="refreshIndia">Recalculate</button></div>
 <div class="indiaGeoLayout"><div><div class="mapFrame indiaFrame"><div id="indiaGeoMap" class="inMap" aria-label="India coverage density by state"></div><div id="indiaTip" class="mapTip" hidden></div><div id="indiaGeoBanner" class="indiaGeoBanner">Boundaries: Survey of India state map via DataMeet, bundled with Sanjaya.</div></div><div class="indiaHeatLegend"><span>Fewer stories</span>${RAMP.map((c) => `<i style="background:${c}"></i>`).join("")}<span>More stories</span></div></div>
 <aside class="indiaGeoSide"><div id="indiaCounts">Indexing places…</div><h3>Most covered</h3><div id="indiaStateButtons"></div></aside></div>
 <div class="indiaDetails" id="indiaDetails"><div class="empty"><b>Choose a state or union territory</b><span class="fine">Click the map or the list to read the stories behind its shade.</span></div></div></div>
 <div class="panel windyPanel" style="margin-top:16px"><div class="panelHeading"><h2>Weather over India</h2><span class="fine">Windy · ECMWF high-resolution forecast</span></div><div class="filters">${[["wind", "Wind"], ["rain", "Rain"], ["temp", "Temperature"]].map(([m, t]) => `<button class="choice ${wind === m ? "active" : ""}" data-indiawind="${m}">${t}</button>`).join("")}<span class="spacer"></span><button class="linkButton" data-indiawx="wind">Open in Earth watch</button><a class="fine" target="_blank" rel="noopener noreferrer" href="https://www.windy.com/?22.4,79.0,5">Windy ↗</a></div><iframe title="Windy weather map of India" id="indiaWindy" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" src="${windURL(wind)}"></iframe><p class="fine">Layers, time slider and basemap belong to Windy. Its basemap may draw borders that differ from the official map of India shown above.</p></div>
 <div class="panel" style="margin-top:16px"><h2>How to read this map</h2><p class="fine">States are assigned from headlines first, excerpts second and geographically scoped local feeds third (weaker evidence; exclude it with Attribution). One story can name several states. The surface reflects publisher distribution and RSS availability, not an objective count of events.</p><p class="fine">Boundaries are the Survey of India state map published by the DataMeet community (36 states and union territories, including Ladakh and Jammu and Kashmir as union territories, with the external boundary as shown on the official map of India). Simplified for screen display.</p></div>`;
  }
  const windURL = (layer) =>
    "https://embed.windy.com/embed.html?type=map&location=coordinates&metricRain=default&metricTemp=default&metricWind=default&zoom=5&level=surface&lat=22.5&lon=80&product=ecmwf&overlay=" +
    encodeURIComponent(layer || "wind");
  const RAMP = ["rgba(190,228,240,.08)", "#21566a", "#2f8a9c", "#8fd9e8", "#f0b45a", "#f06a5b"];
  async function geometry() {
    if (shapes) return shapes;
    let res = await fetch("/api/india-boundaries", { cache: "default" });
    if (!res.ok) throw Error("HTTP " + res.status);
    let data = await res.json();
    shapes = data.geometry;
    geomLabel = "Survey of India state boundaries · DataMeet · bundled";
    try { outline = (await (await fetch("/data/india_outline_soi.geojson")).json()).features[0].geometry; } catch (_) {}
    return shapes;
  }
  let outline = null;
  function destroy() {}
  function mount(root) {
    const host = $("#indiaGeoMap");
    if (!host) return;
    const st = $("#indiaMapStatus");
    geometry().then(() => { if ($("#indiaGeoMap")) { renderSvg(root); if (st) st.textContent = geomLabel; } })
      .catch((e) => { if (st) st.textContent = "Boundaries unavailable: " + e.message; });
    fetchDensity(root);
  }
  function setBase() {}
  function paint(root) { renderSvg(root); renderCounts(root); }
  const B = { lon0: 67.6, lon1: 98.2, lat0: 6, lat1: 37.4, k: Math.cos((22 * Math.PI) / 180) };
  const PX = (lon) => (lon - B.lon0) * B.k * 20, PY = (lat) => (B.lat1 - lat) * 20;
  function svgPath(geom) {
    let types = geom.type === "Polygon" ? [geom.coordinates] : geom.type === "MultiPolygon" ? geom.coordinates : [];
    return types.map((poly) => poly.map((ring) => ring.map(([lon, lat], i) => `${i ? "L" : "M"}${PX(lon).toFixed(1)},${PY(lat).toFixed(1)}`).join("") + "Z").join("")).join("");
  }
  function color(n, max) {
    if (!n) return RAMP[0];
    const t = n / Math.max(3, max);
    return t <= .15 ? RAMP[1] : t <= .35 ? RAMP[2] : t <= .6 ? RAMP[3] : t <= .85 ? RAMP[4] : RAMP[5];
  }
  function renderSvg(root) {
    let host = $("#indiaGeoMap");
    if (!host || !shapes) return;
    let d = root.indiaCoverage, max = Math.max(1, ...(d?.states || []).map((x) => x.count));
    const W = PX(B.lon1), H = PY(B.lat0);
    let html = `<svg role="img" aria-label="Coverage density by Indian state" viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}" preserveAspectRatio="xMidYMid meet">`;
    for (let f of (shapes.features || []).filter((f) => f.geometry)) {
      let n = f.properties?.name || "", st = stateFor(n, d), name = st?.name || n;
      html += `<path class="st ${selected === name ? "sel" : ""}" data-indiastate="${esc(name)}" data-count="${st?.count || 0}" d="${svgPath(f.geometry)}" fill="${color(st?.count || 0, max)}" tabindex="0"><title>${esc(name)} · ${num(st?.count)} stories</title></path>`;
    }
    if (outline) html += `<path class="outline" d="${svgPath(outline)}"/>`;
    for (const s of (d?.states || []).filter((x) => x.count && x.lat).sort((a, b) => b.count - a.count).slice(0, 10))
      html += `<text x="${PX(s.lon).toFixed(1)}" y="${PY(s.lat).toFixed(1)}" text-anchor="middle">${esc(s.name.length > 14 ? s.name.split(" ")[0] : s.name)} ${num(s.count)}</text>`;
    host.innerHTML = html + "</svg>";
    host.onmousemove = (ev) => {
      const p = ev.target.closest("path.st"), tip = $("#indiaTip");
      if (!tip) return;
      if (!p) { tip.hidden = true; return; }
      const r = host.getBoundingClientRect();
      tip.hidden = false; tip.style.left = ev.clientX - r.left + "px"; tip.style.top = ev.clientY - r.top + "px";
      tip.textContent = `${p.dataset.indiastate} · ${num(p.dataset.count)} stories`;
    };
    host.onmouseleave = () => { const t = $("#indiaTip"); if (t) t.hidden = true; };
  }
  function renderCounts(root) {
    let d = root.indiaCoverage || {},
      counts = d.counts || {},
      arr = (d.states || [])
        .filter((x) => x.count)
        .sort((a, b) => b.count - a.count);
    let n = $("#indiaCounts");
    if (n)
      n.innerHTML = `<div class="indiaStat"><strong>${num(counts.located_distinct_articles)}</strong><span>Distinct geo-attributed stories</span></div><div class="indiaStat"><strong>${num(counts.state_assignments)}</strong><span>Total state assignments</span></div><p class="fine">${num(counts.duplicate_stories)} repeated headlines collapsed · ${num(counts.unlocated)} not confidently located</p>`;
    let top = $("#indiaStateButtons");
    if (top)
      top.innerHTML =
        arr
          .slice(0, 18)
          .map(
            (x) =>
              `<button class="stateRow ${selected === x.name ? "selected" : ""}" data-indiastate="${esc(x.name)}"><span>${esc(x.name)}</span><b>${num(x.count)}</b></button>`,
          )
          .join("") ||
        '<p class="fine">No region-attributed articles in this period.</p>';
    if (selected) showDetails(root);
  }
  function select(name, root) {
    selected = name;
    renderSvg(root);
    renderCounts(root);
    $("#indiaDetails")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function showDetails(root) {
    let x = (root.indiaCoverage?.states || []).find((z) => z.name === selected),
      el = $("#indiaDetails");
    if (!el) return;
    if (!x || !x.count) {
      el.innerHTML = `<h3>${esc(selected)}</h3><p>No collected geographically attributable stories for these filters.</p>`;
      return;
    }
    el.innerHTML = `<div class="panelHeading"><h2>${esc(x.name)} · ${num(x.count)} distinct stories</h2><span class="fine">${num(x.headline)} headline · ${num(x.excerpt)} excerpt · ${num(x.source_scope)} local-feed assignment</span></div><p class="fine">Most frequently named cities: ${
      x.cities
        .slice(0, 8)
        .map((c) => esc(c.name) + " (" + num(c.count) + ")")
        .join(" · ") || "No named city in available excerpts"
    }</p><div class="newsList">${(x.records || [])
      .slice(0, 18)
      .map(
        (e) =>
          `<article class="story"><div class="meta"><strong>${esc(e.source)}</strong><span class="tag">${esc(e.basis)}</span></div><h3><a target="_blank" rel="noopener noreferrer" href="${encodeURI(e.url || "#")}">${esc(e.title)}</a></h3><div class="storyBrief"><p>${esc(e.summary ? e.summary.slice(0, 300) : "The feed supplied no excerpt.")}</p></div></article>`,
      )
      .join("")}</div>`;
  }
  async function fetchDensity(root) {
    if (fetching) return;
    fetching = true;
    let status = $("#indiaMapStatus");
    if (status) status.textContent = "Counting retrieved stories from SQLite…";
    try {
      let qs = new URLSearchParams({
        days: root.indiaDays || 7,
        topic: root.indiaTopic || "all",
        scope: root.indiaScope || "all",
      });
      let res = await fetch("/api/india-coverage?" + qs, { cache: "no-store" });
      if (!res.ok) throw Error("HTTP " + res.status);
      root.indiaCoverage = await res.json();
      previousUpdate = Date.now();
      if (shapes) paint(root);
      else renderCounts(root);
      let st = $("#indiaMapStatus");
      if (st && shapes) st.textContent = geomLabel;
    } catch (e) {
      if (status) status.textContent = "Density retrieval failed: " + e.message;
    } finally {
      fetching = false;
    }
  }
  async function refreshIfStale(root) {
    if (Date.now() - previousUpdate > 60000 && !fetching && $("#indiaGeoMap"))
      await fetchDensity(root);
  }
  function onClick(e, root) {
    let target = e.target.closest(
      "[data-indiastate],[data-indiawx],[data-indiawind],#refreshIndia",
    );
    if (!target) return false;
    if (target.dataset.indiastate) {
      select(target.dataset.indiastate, root);
      return true;
    }
    if (target.dataset.indiawx) {
      window.ATLASEarth?.preset("india", target.dataset.indiawx);
      window.ATLAS.go("earth");
      return true;
    }
    if (target.dataset.indiawind) {
      wind = target.dataset.indiawind;
      let iframe = $("#indiaWindy");
      if (iframe) iframe.src = windURL(wind);
      document
        .querySelectorAll("[data-indiawind]")
        .forEach((b) =>
          b.classList.toggle("active", b.dataset.indiawind === wind),
        );
      return true;
    }
    if (target.id === "refreshIndia") {
      fetchDensity(root);
      return true;
    }
    if (target.id === "indiaStreet" || target.id === "indiaSatellite") {
      baseMode = target.id === "indiaStreet" ? "street" : "satellite";
      setBase(root);
      return true;
    }
    return false;
  }
  function onChange(e, root) {
    let target = e.target;
    if (!["indiaDays", "indiaTopic", "indiaScope"].includes(target.id))
      return false;
    if (target.id === "indiaDays") root.indiaDays = Number(target.value);
    if (target.id === "indiaTopic") root.indiaTopic = target.value;
    if (target.id === "indiaScope") root.indiaScope = target.value;
    selected = "";
    root.indiaCoverage = null;
    fetchDensity(root);
    return true;
  }
  return { layout, mount, destroy, onClick, onChange, refreshIfStale };
})();
