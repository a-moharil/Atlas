"use strict";
/* Sanjaya v5.7 · YouTube player helpers and the floating player.
   - Talks to YouTube embeds through the IFrame API's postMessage channel, so Sanjaya
     learns when a video won't play ("This video is unavailable") and can react.
   - The floating player can be dragged by its title bar, resized from its corner,
     maximised (button or double-click) and put into full screen. */
window.ATLASPlayer = (() => {
  const HOSTS = /^https:\/\/www\.youtube(-nocookie)?\.com$/;
  const watchers = new Map(); // contentWindow -> handlers
  let seq = 0;
  const ERR = {
    2: "YouTube rejected the request for this video.",
    5: "YouTube's player hit an error with this video.",
    100: "This video was removed or made private.",
    101: "The broadcaster doesn't allow this video to play outside YouTube, or it's blocked in your region.",
    150: "The broadcaster doesn't allow this video to play outside YouTube, or it's blocked in your region.",
  };
  const errorText = (code) => ERR[code] || "YouTube couldn't play this video here.";

  function embedUrl(videoId, opts = {}) {
    const q = new URLSearchParams({ autoplay: opts.autoplay === false ? "0" : "1", playsinline: "1", controls: "1", rel: "0", enablejsapi: "1", origin: location.origin });
    if (opts.mute) q.set("mute", "1");
    if (opts.start) q.set("start", String(Math.max(0, Math.floor(opts.start))));
    const path = opts.channel ? `live_stream?channel=${encodeURIComponent(opts.channel)}&` : `${videoId}?`;
    return `https://www.youtube-nocookie.com/embed/${path}${q}`;
  }
  // Ask the embed to report its events to this page.
  function watch(iframe, handlers) {
    const id = ++seq;
    const post = (msg) => { try { iframe.contentWindow?.postMessage(JSON.stringify({ ...msg, id, channel: "widget" }), "*"); } catch (e) { /* frame gone */ } };
    const hello = () => {
      post({ event: "listening" });
      for (const ev of ["onStateChange", "onError"]) post({ event: "command", func: "addEventListener", args: [ev] });
    };
    let tries = 0;
    const timer = setInterval(() => { if (++tries > 8 || h.ready) clearInterval(timer); else hello(); }, 700);
    iframe.addEventListener("load", () => { hello(); if (iframe.contentWindow) watchers.set(iframe.contentWindow, h); });
    const h = { id, ready: false, handlers, time: 0, muted: null,
      command: (func, args = []) => post({ event: "command", func, args }),
      stop: () => { clearInterval(timer); for (const [w, x] of watchers) if (x === h) watchers.delete(w); } };
    if (iframe.contentWindow) watchers.set(iframe.contentWindow, h);
    return h;
  }
  window.addEventListener("message", (ev) => {
    if (!HOSTS.test(ev.origin)) return;
    const h = watchers.get(ev.source);
    if (!h) return;
    let d;
    try { d = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data; } catch (e) { return; }
    if (!d || typeof d !== "object") return;
    h.ready = true;
    if (d.event === "onError") h.handlers.onError?.(Number(d.info));
    else if (d.event === "onStateChange") h.handlers.onState?.(Number(d.info));
    else if (d.event === "infoDelivery" && d.info) {
      if (typeof d.info.currentTime === "number") h.time = d.info.currentTime;
      if (typeof d.info.muted === "boolean") h.muted = d.info.muted;
      if (typeof d.info.playerState === "number") h.handlers.onState?.(d.info.playerState);
    }
  });
  function report(videoId, code) {
    if (!/^[A-Za-z0-9_-]{11}$/.test(videoId || "")) return;
    fetch("/api/video/player-error", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_id: videoId, code }) }).catch(() => {});
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  // ---------------------------------------------------------------- floating player
  const $ = (s) => document.querySelector(s);
  let dockWatch = null;
  const KEY = "atlas.player.v1";
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } };
  const save = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* storage off */ } };

  // Called by playYouTube once the iframe is in the dock.
  function dock(iframe, info) {
    dockWatch?.stop();
    const d = $("#playerDock");
    const link = info.channel?.official_live || `https://www.youtube.com/watch?v=${info.videoId}`;
    const cap = $("#playerCaption");
    if (cap && !cap.querySelector(".pOpen")) cap.insertAdjacentHTML("beforeend", ` <a class="pOpen" target="_blank" rel="noopener noreferrer" href="${esc(link)}">Open on YouTube ↗</a>`);
    else if (cap) cap.querySelector(".pOpen").href = link;
    let triedChannel = false;
    dockWatch = watch(iframe, {
      onError(code) {
        // A "verified live" ID can go stale when a broadcast ends: try the channel's current stream once.
        if (info.verified && info.channel?.channel_id && !triedChannel) {
          triedChannel = true;
          fetch("/api/refresh-live", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
          iframe.src = embedUrl("", { channel: info.channel.channel_id });
          $("#playerCaption").firstChild.textContent = "That stream has ended or is blocked. Trying the channel's current live stream… ";
          return;
        }
        if (!info.verified) report(info.videoId, code);
        showError(code, link, info);
      },
    });
    d.classList.remove("errored");
    window.ATLASReel?.pauseForDock?.();
  }
  function showError(code, link, info) {
    const box = $("#playerContent");
    if (!box) return;
    box.innerHTML = `<div class="pErr"><b>${esc(errorText(code))}</b><p>${info.verified ? "The channel may have ended its live broadcast. Sanjaya has asked for a fresh live check." : "Sanjaya won't offer this video again for a week."}</p>
      <div><a class="action primary" target="_blank" rel="noopener noreferrer" href="${esc(link)}">Watch on YouTube</a><button class="action" id="playerClose2">Close player</button></div></div>`;
    $("#playerDock").classList.add("errored");
    const cap = $("#playerCaption");
    if (cap?.firstChild) cap.firstChild.textContent = "YouTube couldn't play this here. ";
    box.querySelector("#playerClose2").onclick = () => $("#playerClose")?.click();
  }

  function clamp(d) {
    if (!d.classList.contains("moved") || d.classList.contains("maxed")) return;
    const r = d.getBoundingClientRect();
    const left = Math.min(Math.max(8, r.left), window.innerWidth - Math.min(r.width, window.innerWidth) - 8);
    const top = Math.min(Math.max(8, r.top), window.innerHeight - 48);
    d.style.left = left + "px"; d.style.top = top + "px";
  }
  function remember(d) { save({ left: d.style.left, top: d.style.top, width: d.style.width, moved: d.classList.contains("moved") }); }
  function setMax(d, on) {
    d.classList.toggle("maxed", on);
    const b = $("#playerMax");
    if (b) { b.setAttribute("aria-label", on ? "Restore player size" : "Maximise player"); b.title = on ? "Restore size" : "Maximise"; b.innerHTML = on ? ICON.restore : ICON.max; }
    if (on) d.classList.remove("minimised");
  }
  const ICON = {
    max: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/></svg>',
    restore: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="5" width="8.5" height="8.5" rx="1.2"/><path d="M5 5V2.8h8.2V11H11"/></svg>',
    full: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/></svg>',
    exit: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 2.5V6H2.5M13.5 6H10V2.5M10 13.5V10h3.5M2.5 10H6v3.5"/></svg>',
  };
  function setup() {
    const d = $("#playerDock"), bar = d?.querySelector(".playerBar");
    if (!d || !bar || d.dataset.enhanced) return;
    d.dataset.enhanced = "1";
    const btns = bar.querySelector("div");
    btns.insertAdjacentHTML("afterbegin", `<button id="playerMax" aria-label="Maximise player" title="Maximise">${ICON.max}</button><button id="playerFull" aria-label="Full screen" title="Full screen">${ICON.full}</button>`);
    $("#playerMin").title = "Minimise"; $("#playerClose").title = "Close";
    bar.title = "Drag to move · double-click to maximise";
    const saved = load();
    if (saved.moved && saved.left) { d.classList.add("moved"); d.style.left = saved.left; d.style.top = saved.top; }
    if (saved.width) d.style.width = saved.width;
    $("#playerMax").onclick = () => setMax(d, !d.classList.contains("maxed"));
    $("#playerFull").onclick = () => {
      if (document.fullscreenElement) document.exitFullscreen?.();
      else d.requestFullscreen?.().catch(() => setMax(d, true));
    };
    document.addEventListener("fullscreenchange", () => {
      const on = document.fullscreenElement === d;
      d.classList.toggle("full", on);
      $("#playerFull").innerHTML = on ? ICON.exit : ICON.full;
      $("#playerFull").setAttribute("aria-label", on ? "Exit full screen" : "Full screen");
      $("#playerFull").title = on ? "Exit full screen (Esc)" : "Full screen";
    });
    bar.addEventListener("dblclick", (e) => { if (!e.target.closest("button")) setMax(d, !d.classList.contains("maxed")); });
    // Drag by the title bar.
    bar.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button,a") || d.classList.contains("maxed") || d.classList.contains("full")) return;
      const r = d.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      d.classList.add("moved", "dragging"); d.style.left = r.left + "px"; d.style.top = r.top + "px";
      // Embedded players (this one, the reel, maps) would swallow the pointer: switch them off while dragging.
      document.body.classList.add("atlasDragging");
      const move = (m) => { d.style.left = m.clientX - dx + "px"; d.style.top = m.clientY - dy + "px"; clamp(d); };
      const up = () => {
        d.classList.remove("dragging"); document.body.classList.remove("atlasDragging");
        window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); remember(d);
      };
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); window.addEventListener("pointercancel", up);
      e.preventDefault();
    });
    // Keyboard: arrow keys move the player when the title bar has focus.
    bar.tabIndex = 0;
    bar.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 40 : 12, k = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (!k || d.classList.contains("maxed")) return;
      const r = d.getBoundingClientRect();
      d.classList.add("moved"); d.style.left = r.left + k[0] + "px"; d.style.top = r.top + k[1] + "px"; clamp(d); remember(d); e.preventDefault();
    });
    // Remember a corner resize.
    new ResizeObserver(() => { if (!d.hidden && !d.classList.contains("maxed") && !d.classList.contains("full") && d.style.width) remember(d); }).observe(d);
    window.addEventListener("resize", () => clamp(d));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && d.classList.contains("maxed") && !document.fullscreenElement && !document.querySelector("#cgOverlay") && $("#storyPanel")?.hidden !== false) setMax(d, false);
    });
    $("#playerClose").addEventListener("click", () => { dockWatch?.stop(); dockWatch = null; setMax(d, false); if (document.fullscreenElement === d) document.exitFullscreen?.(); d.classList.remove("errored"); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
  return { embedUrl, watch, report, errorText, dock };
})();
