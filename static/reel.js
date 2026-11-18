"use strict";
/* Sanjaya v5.7 · Geopolitics reel (Live TV and video page).
   Plays recent news videos (last 24 hours) from international broadcasters one after
   another: news only, geopolitics by default. "Stop circulating" holds the current video;
   videos YouTube won't play here are skipped and not offered again. */
window.ATLASReel = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const KEY = "atlas.reel.v1";
  const prefs = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } })();
  const R = {
    data: null, list: [], idx: 0, cur: null, running: prefs.running !== false, advance: prefs.advance ?? 180, scope: prefs.scope || "geo",
    left: 0, state: -1, watch: null, tick: 0, poll: 0, loading: false, note: "", fetched: 0,
  };
  const savePrefs = () => { try { localStorage.setItem(KEY, JSON.stringify({ running: R.running, advance: R.advance, scope: R.scope })); } catch (e) { /* storage off */ } };
  const host = () => document.querySelector("#reelHost");
  const W = () => window.ATLASWall;
  const visible = () => R.list.filter((v) => !W()?.isHidden(v.id));
  const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  async function load() {
    if (R.loading) return;
    R.loading = true;
    try {
      const d = await A().api(`/api/geo-reel?hours=24&scope=${R.scope}`);
      R.data = d; R.fetched = Date.now();
      const curId = R.cur?.video_id;
      R.list = d.videos || [];
      const at = R.list.findIndex((v) => v.video_id === curId);
      R.idx = at >= 0 ? at : 0;
      R.note = "";
    } catch (e) {
      R.note = "Couldn't load the reel: " + e.message;
    }
    R.loading = false;
    draw();
    if (!R.cur && visible().length) play(R.idx, { quiet: true });
  }

  // ---------------------------------------------------------------- playback
  function stage() { return document.querySelector("#reelStage"); }
  function play(i, opts = {}) {
    const list = visible();
    if (!list.length) return;
    R.idx = ((i % list.length) + list.length) % list.length;
    const v = list[R.idx];
    R.cur = v; R.left = R.advance; R.state = -1;
    const st = stage();
    if (!st) return;
    let f = st.querySelector("iframe");
    if (f && R.watch?.ready && !opts.reload) {
      R.watch.command("loadVideoById", [{ videoId: v.video_id, startSeconds: opts.start || 0 }]);
    } else {
      R.watch?.stop();
      f = document.createElement("iframe");
      f.title = "Geopolitics reel";
      f.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
      f.allowFullscreen = true;
      f.referrerPolicy = "strict-origin-when-cross-origin";
      // Muted so browsers allow autoplay; unmute in the player and later videos stay unmuted.
      f.src = window.ATLASPlayer.embedUrl(v.video_id, { mute: R.watch?.muted !== false, start: opts.start || 0 });
      st.replaceChildren(f);
      R.watch = window.ATLASPlayer.watch(f, { onState, onError });
    }
    drawSide();
  }
  function onState(s) {
    R.state = s;
    if (s === 0 && R.running) next();
  }
  function onError(code) {
    const v = R.cur;
    if (!v) return;
    window.ATLASPlayer.report(v.video_id, code);
    R.list = R.list.filter((x) => x.video_id !== v.video_id);
    R.note = `Skipped "${v.title.slice(0, 70)}" from ${v.channel}: ${window.ATLASPlayer.errorText(code)}`;
    R.cur = null;
    draw();
    setTimeout(() => play(R.idx, { reload: true }), 1200);
  }
  function next() { play(R.idx + 1); }
  function prev() { play(R.idx - 1); }
  function everySecond() {
    if (!host()) return;
    if (R.running && R.advance > 0 && R.cur && (R.state === 1 || !R.watch?.ready)) {
      R.left -= 1;
      if (R.left <= 0) return next();
    }
    const c = document.querySelector("#reelCount");
    if (c) c.textContent = !R.running ? "Circulation stopped" : R.advance > 0 ? `Next in ${mmss(Math.max(0, R.left))}` : "Next when this video ends";
    const bar = document.querySelector("#reelProg");
    if (bar) bar.style.width = R.running && R.advance > 0 ? `${100 * (1 - Math.max(0, R.left) / R.advance)}%` : "0";
  }

  // ---------------------------------------------------------------- drawing
  function shell() {
    const adv = [[60, "1 minute"], [180, "3 minutes"], [300, "5 minutes"], [0, "the video ends"]];
    return `<div class="panelHeading"><h2>Geopolitics reel</h2><span class="fine" id="reelSub"></span></div>
      <div class="reelBar">
        <button class="action ${R.running ? "" : "primary"}" id="reelRun" aria-pressed="${!R.running}">${R.running ? "Stop circulating" : "Resume circulating"}</button>
        <button class="action" id="reelPrev">Previous</button><button class="action" id="reelNext">Next</button>
        <div class="cgSwitch" role="radiogroup" aria-label="Which videos">${[["geo", "Geopolitics"], ["news", "All news"]].map(([k, t]) => `<button role="radio" aria-checked="${R.scope === k}" class="${R.scope === k ? "on" : ""}" data-reelscope="${k}">${t}</button>`).join("")}</div>
        <label class="reelAdv fine">Next video after <select id="reelAdv">${adv.map(([s, t]) => `<option value="${s}" ${R.advance === s ? "selected" : ""}>${t}</option>`).join("")}</select></label>
        <button class="linkButton" id="reelPop">Open in floating player</button>
      </div>
      ${findBar()}
      <div class="reelBody"><div class="reelStageWrap"><div class="reelStage" id="reelStage"></div><div class="reelProg"><i id="reelProg"></i></div></div><aside class="reelSide" id="reelSide"></aside></div>
      <p class="fine reelFoot" id="reelFoot"></p>`;
  }
  // Search across every news video in the last 24 hours (not only the current filter).
  function findBar() {
    const F = window.ATLASFind;
    if (!F) return "";
    const opts = { label: "reel videos", source: "reel", web: false, webNote: "The reel only plays videos from the broadcasters it follows.",
      item: (v) => `<button class="reelItem" data-reelvid="${esc(v.id)}"><span class="reelThumb" style="background-image:url('${esc(v.thumbnail)}')"></span><span><b>${esc(v.channel)}</b><span>${esc(v.title)}</span><small class="fine">${esc(A().ago(v.published))}</small></span></button>`,
      wrap: (h) => `<div class="reelFindGrid">${h}</div>` };
    F.register("reel", opts);
    return `<div class="reelFind">${F.bar("reel", opts)}<div class="findBody" data-findbody="reel"></div></div>`;
  }
  function playVideo(v) {
    if (!v) return;
    let i = visible().findIndex((x) => x.video_id === v.video_id);
    if (i < 0) { R.list.splice(R.idx + 1, 0, v); i = visible().findIndex((x) => x.video_id === v.video_id); }
    play(i);
    document.querySelector("#reelStage")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function drawSide() {
    const side = document.querySelector("#reelSide");
    if (!side) return;
    const list = visible(), v = R.cur;
    const upcoming = [];
    for (let k = 1; k <= Math.min(6, list.length - 1); k++) upcoming.push([(R.idx + k) % list.length, list[(R.idx + k) % list.length]]);
    side.innerHTML = `${v ? `<div class="reelNow"><div class="reelNowTop"><b>${esc(v.channel)}</b><span class="fine">${esc(v.region)} · ${esc(A().ago(v.published))}</span><span class="fine reelPos">${R.idx + 1} of ${list.length}</span></div>
        <a href="https://www.youtube.com/watch?v=${esc(v.video_id)}" target="_blank" rel="noopener noreferrer">${esc(v.title)}</a>
        ${v.terms?.length ? `<div class="reelTerms">${v.terms.slice(0, 5).map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
        <span class="fine" id="reelCount"></span></div>` : ""}
      ${R.note ? `<p class="fine reelNote">${esc(R.note)}</p>` : ""}
      ${upcoming.length ? `<h3>Up next</h3><ul class="reelNext">${upcoming.map(([i, x]) => `<li><button class="reelItem" data-reelplay="${i}"><span class="reelThumb" style="background-image:url('${esc(x.thumbnail)}')"></span><span><b>${esc(x.channel)}</b><span>${esc(x.title)}</span><small class="fine">${esc(A().ago(x.published))}</small></span></button>${W() ? W().removeBtn(x.id, "Remove this video from the reel") : ""}</li>`).join("")}</ul>` : ""}`;
    everySecond();
  }
  function draw() {
    const h = host();
    if (!h) return;
    if (!h.querySelector("#reelStage")) h.innerHTML = shell();
    const d = R.data, list = visible();
    const sub = h.querySelector("#reelSub"), foot = h.querySelector("#reelFoot");
    if (!d) { sub.textContent = R.note || "Loading recent broadcaster videos…"; return; }
    const live = (d.channels || []).filter((c) => c.videos).length;
    sub.textContent = `${list.length} video${list.length === 1 ? "" : "s"} from the last ${d.hours} hours · ${live} of ${(d.channels || []).length} broadcasters · news only${R.scope === "geo" ? ", geopolitics" : ""}`;
    const c = d.counts || {};
    const out = [c.not_news && `${c.not_news} not news`, R.scope === "geo" && c.not_geopolitics && `${c.not_geopolitics} not about geopolitics`,
      c.awaiting_check && `${c.awaiting_check} waiting for YouTube's playability check`, c.not_playable && `${c.not_playable} won't play outside YouTube`, c.removed && `${c.removed} removed by you`].filter(Boolean);
    const failed = (d.channels || []).filter((x) => x.state === "error");
    const unfetched = (d.channels || []).filter((x) => x.state === "not fetched yet");
    foot.innerHTML = `${out.length ? `Left out: ${esc(out.join(", "))}. ` : ""}${failed.length ? `<span class="reelWarn" title="${esc(failed.map((x) => `${x.name}: ${x.error}`).join("\n"))}">Couldn't fetch ${esc(failed.map((x) => x.name).join(", "))}.</span> ` : ""}${unfetched.length ? `Not fetched yet: ${esc(unfetched.map((x) => x.name).join(", "))}. ` : ""}<span title="${esc((d.channels || []).map((x) => x.name).join(", "))}">${(d.channels || []).length} broadcasters</span>; channel IDs can be checked with <code>python tools/check_geo_channels.py</code>.`;
    if (!list.length) {
      R.cur = null; R.watch?.stop(); R.watch = null;
      const why = c.awaiting_check ? "Videos are waiting for YouTube's playability check. They usually appear within a few minutes of a refresh."
        : unfetched.length === (d.channels || []).length ? "The broadcaster feeds haven't been fetched yet. Use Refresh at the top of the page."
        : R.scope === "geo" ? "No geopolitical news videos in the last 24 hours. Try All news." : "No news videos in the last 24 hours.";
      h.querySelector("#reelStage").innerHTML = `<div class="reelEmpty"><b>Nothing to play yet</b><span class="fine">${esc(why)}</span></div>`;
    }
    drawSide();
  }

  // ---------------------------------------------------------------- lifecycle and events
  function mount() {
    const h = host();
    if (!h) return;
    h.innerHTML = shell();
    window.ATLASFind?.apply();
    if (!R.tick) R.tick = setInterval(everySecond, 1000);
    if (!R.poll) R.poll = setInterval(() => { if (host()) load(); }, 10 * 60 * 1000);
    const resumeAt = R.watch?.time || 0;
    R.watch?.stop(); R.watch = null;
    if (R.data && Date.now() - R.fetched < 10 * 60 * 1000) {
      draw();
      if (R.cur) { const i = visible().findIndex((v) => v.video_id === R.cur.video_id); play(i >= 0 ? i : R.idx, { reload: true, start: i >= 0 ? resumeAt : 0 }); }
      else if (visible().length) play(R.idx, { reload: true });
    } else { draw(); load(); }
  }
  function unmount() {
    R.watch?.stop(); R.watch = null;
    clearInterval(R.tick); clearInterval(R.poll); R.tick = R.poll = 0;
  }
  function setRunning(on) {
    R.running = on; R.left = R.advance; savePrefs();
    const b = document.querySelector("#reelRun");
    if (b) { b.textContent = on ? "Stop circulating" : "Resume circulating"; b.classList.toggle("primary", !on); b.setAttribute("aria-pressed", String(!on)); }
    everySecond();
  }
  function pauseForDock() {
    if (!host() || !R.watch) return;
    R.watch.command("pauseVideo");
    if (R.running) { setRunning(false); R.note = "Paused while the floating player is open. Resume circulating to continue."; drawSide(); }
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || !b.closest("#reelHost")) return;
    if (b.id === "reelRun") setRunning(!R.running);
    else if (b.id === "reelNext") next();
    else if (b.id === "reelPrev") prev();
    else if (b.id === "reelPop" && R.cur) { R.watch?.command("pauseVideo"); setRunning(false); A().play(R.cur.video_id, `${R.cur.channel} · ${R.cur.title.slice(0, 60)}`, false); }
    else if (b.dataset.reelplay) play(Number(b.dataset.reelplay));
    else if (b.dataset.reelvid) playVideo(window.ATLASFind?.entry(b.dataset.reelvid));
    else if (b.dataset.reelscope && b.dataset.reelscope !== R.scope) { R.scope = b.dataset.reelscope; savePrefs(); R.cur = null; host().innerHTML = shell(); window.ATLASFind?.apply(); R.watch?.stop(); R.watch = null; load(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id !== "reelAdv") return;
    R.advance = Number(e.target.value); R.left = R.advance; savePrefs(); everySecond();
  });
  return { mount, unmount, pauseForDock, load, _state: R };
})();
