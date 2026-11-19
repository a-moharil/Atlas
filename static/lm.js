"use strict";
/* Sanjaya v5.1 · Language model settings: grouping by meaning (local multilingual
   embeddings) and optional model-written labels (local Ollama). */
window.ATLASLM = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  let data = null, pairs = null, timer = 0, alive = false;
  const EMB = {
    ready: ["Grouping by meaning", "good"], loading: ["Loading model", "warn"], installed: ["Installed, starting", "warn"],
    not_installed: ["Not installed · keyword mode", "bad"], error: ["Error · keyword mode", "bad"], not_checked: ["Starting", "warn"],
  };
  const LAB = { ready: ["Ready", "good"], model_missing: ["Model not pulled", "warn"], offline: ["Ollama not running", "bad"], not_checked: ["Not checked", "warn"] };
  function layout() {
    return `<div class="heroTitle"><div><h1>Language model</h1><p>Sanjaya can group stories by meaning instead of shared words, across English and Indian languages, using a small model that runs on this computer. It can also write short neutral labels for the top stories. Nothing is sent to an online AI service.</p></div></div><div id="lmBody"><p class="fine">Checking the model…</p></div>`;
  }
  const pill = (map, key) => { const [t, c] = map[key] || [key, "warn"]; return `<span class="statusPill ${c === "good" ? "good" : c === "bad" ? "bad" : "unknown"}">${esc(t)}</span>`; };
  function draw() {
    const el = document.querySelector("#lmBody");
    if (!el || !data) return;
    const e = data.embedding, s = data.settings, l = data.labels;
    const pct = e.articles ? Math.round((100 * e.embedded) / e.articles) : 0;
    const install = !e.installed
      ? `<div class="lmSteps"><b>Install the grouping model (once)</b><ol><li>Close Sanjaya.</li><li>Double-click <code>install_language_model.bat</code> in the Atlas folder (the repository keeps its original name) (macOS/Linux: <code>bash install_language_model.sh</code>).</li><li>Start Sanjaya again. The first start downloads about 220 MB, then it works offline.</li></ol></div>` : "";
    el.innerHTML = `<div class="twoEqual">
      <section class="panel"><div class="panelHeading"><h2>Grouping by meaning</h2>${pill(EMB, e.status)}</div>
        <p class="fine">${esc(e.model)} · ${e.dimensions} dimensions · multilingual · runs on the processor</p>
        ${install}
        ${e.installed ? `<div class="lmMeter"><div style="width:${pct}%"></div></div><p class="fine">${num(e.embedded)} of ${num(e.articles)} articles processed (${pct}%)${e.rate ? ` · about ${e.rate} per second` : ""}${data.busy ? " · working now" : ""}</p>` : ""}
        ${e.detail ? `<p class="fine">${esc(e.detail)}</p>` : ""}
        <div class="lmField"><label for="lmThr">Strictness <b id="lmThrVal">${Number(s.threshold).toFixed(2)}</b></label><input type="range" id="lmThr" min="0.60" max="0.90" step="0.01" value="${s.threshold}"><div class="leanLabel"><span>Looser: more merging</span><span>Stricter: fewer false merges</span></div></div>
        <div class="lmField"><label for="lmWin">Same story only if published within</label><select id="lmWin">${[24, 48, 72, 120, 168].map((h) => `<option value="${h}" ${+s.window_hours === h ? "selected" : ""}>${h < 72 ? h + " hours" : h / 24 + " days"}</option>`).join("")}</select></div>
        <div class="filters" style="margin-top:12px"><button class="action primary" id="lmSave">Save and regroup</button><button class="action" id="lmRun" ${e.installed ? "" : "disabled"}>Process new articles now</button></div>
        <p class="fine">Used now by the bias gauge, the emergency newsroom and Compare coverage. Articles not yet processed are grouped by keywords and marked as such.</p></section>
      <section class="panel"><div class="panelHeading"><h2>Story labels and summaries</h2>${pill(LAB, l.status)}</div>
        <p class="fine">A small local model writes a neutral label, a one-to-two sentence summary and a note on how outlets differ, for the top multi-outlet newsroom stories. It only sees the headlines and excerpts Sanjaya already holds. Everything it writes is marked Generated.</p>
        <label class="lmToggle"><input type="checkbox" id="lmLabels" ${s.labels_enabled === "1" ? "checked" : ""}> Write labels and summaries</label>
        <div class="lmField"><label for="lmModel">Model</label><select id="lmModel">${[["qwen2.5:1.5b", "qwen2.5:1.5b · recommended, about 1 GB, fast"], ["qwen2.5:3b", "qwen2.5:3b · better wording, about 2 GB, slower"], ["llama3.2:3b", "llama3.2:3b · about 2 GB"], ["gemma2:2b", "gemma2:2b · about 1.6 GB"]].map(([v, t]) => `<option value="${v}" ${s.ollama_model === v ? "selected" : ""}>${t}</option>`).join("")}${![
          "qwen2.5:1.5b", "qwen2.5:3b", "llama3.2:3b", "gemma2:2b"].includes(s.ollama_model) ? `<option selected value="${esc(s.ollama_model)}">${esc(s.ollama_model)}</option>` : ""}</select></div>
        ${l.detail ? `<p class="fine">${esc(l.detail)}</p>` : ""}${l.models?.length ? `<p class="fine">Installed in Ollama: ${l.models.map(esc).join(", ")}</p>` : ""}
        <div class="lmSteps"><b>Set up once</b><ol><li>Install Ollama from <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">ollama.com/download</a> and leave it running.</li><li>In a terminal run <code>ollama pull ${esc(s.ollama_model)}</code>.</li><li>Tick the box above, then Check Ollama.</li></ol></div>
        <div class="filters"><button class="action" id="lmCheck">Check Ollama</button><button class="action" id="lmWrite" ${l.status === "ready" && s.labels_enabled === "1" ? "" : "disabled"}>Write labels now</button><span class="fine">${num(l.stored)} labels stored</span></div></section></div>
      <section class="panel" style="margin-top:16px"><div class="panelHeading"><h2>Check the grouping on your news</h2><button class="linkButton" id="lmPairs">Load borderline pairs</button></div>
        <p class="fine">Pairs of headlines whose similarity is close to the strictness setting. If too many "joined" pairs are different events, raise strictness; if too many "kept apart" pairs are the same event, lower it.</p><div id="lmPairList">${pairsHTML()}</div></section>`;
  }
  function pairsHTML() {
    if (!pairs) return "";
    if (!pairs.ready) return '<p class="fine">Available once the grouping model is ready.</p>';
    if (!pairs.pairs.length) return '<p class="fine">No borderline pairs in recent articles.</p>';
    return `<div class="lmPairs">${pairs.pairs.map((p) => `<div class="lmPair ${p.joined ? "joined" : ""}"><span class="lmSim">${p.similarity.toFixed(2)}<small>${p.joined ? "joined" : "kept apart"}</small></span><div><p><b>${esc(p.a.source)}</b> ${esc(p.a.title)}</p><p><b>${esc(p.b.source)}</b> ${esc(p.b.title)}</p></div></div>`).join("")}</div>`;
  }
  async function load(ollama) {
    try {
      data = await A().api("/api/lm/status" + (ollama ? "?ollama=1" : ""));
      draw();
    } catch (e) {
      const el = document.querySelector("#lmBody");
      if (el) el.innerHTML = `<div class="empty"><b>Could not read model status</b><span class="fine">${esc(e.message)}</span></div>`;
    }
    clearTimeout(timer);
    if (alive && data && (data.busy || ["loading", "installed", "not_checked"].includes(data.embedding.status))) timer = setTimeout(() => load(false), 4000);
  }
  async function save(extra = {}) {
    const thr = document.querySelector("#lmThr")?.value, win = document.querySelector("#lmWin")?.value;
    await A().api("/api/lm/settings", "POST", { threshold: thr, window_hours: win, ...extra });
  }
  function onClick(ev) {
    const b = ev.target.closest("#lmSave,#lmRun,#lmCheck,#lmWrite,#lmPairs");
    if (!b) return false;
    (async () => {
      try {
        if (b.id === "lmSave") { await save(); A().tip("Saved. Stories regroup on the next page load."); A().hydrate(); pairs = null; }
        if (b.id === "lmRun") { await A().api("/api/lm/run", "POST", { labels: false }); A().tip("Processing new articles in the background."); }
        if (b.id === "lmCheck") { await load(true); return; }
        if (b.id === "lmWrite") { await A().api("/api/lm/run", "POST", { labels: true }); A().tip("Writing labels in the background. On a laptop processor each takes a few seconds."); }
        if (b.id === "lmPairs") { pairs = await A().api("/api/lm/borderline"); }
        await load(false);
      } catch (e) { A().tip(e.message); }
    })();
    return true;
  }
  function onChange(e) {
    if (e.target.id === "lmThr") { const v = document.querySelector("#lmThrVal"); if (v) v.textContent = Number(e.target.value).toFixed(2); return true; }
    if (e.target.id === "lmLabels" || e.target.id === "lmModel") {
      const lab = document.querySelector("#lmLabels").checked ? "1" : "0", model = document.querySelector("#lmModel").value;
      save({ labels_enabled: lab, ollama_model: model }).then(() => load(true)).catch((x) => A().tip(x.message));
      return true;
    }
    return e.target.id === "lmWin";
  }
  function mount() { alive = true; load(true); }
  function destroy() { alive = false; clearTimeout(timer); }
  return { layout, mount, destroy, onClick, onChange };
})();
