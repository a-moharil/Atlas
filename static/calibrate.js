"use strict";
/* Sanjaya v6.0 · Calibrate the left-right gauge with your own reading.
   Click the lean label on any card to place that outlet yourself. Your rating replaces
   the published one everywhere on this computer (cards, gauges, political spread,
   coverage graph) and is always marked "yours"; the published rating stays visible
   and one click restores it. */
window.ATLASLean = (() => {
  const A = () => window.ATLAS;
  const esc = (s) => A().esc(s);
  const SCALE = [[-2, "Left"], [-1, "Lean left"], [0, "Centre"], [1, "Lean right"], [2, "Right"]];
  const name = (l) => (l == null ? "Not rated" : (SCALE.find((x) => x[0] === l) || [0, "Rated"])[1]);
  const S = { host: null, pick: undefined, note: "", mode: "edit", busy: false, back: null };
  const overrides = () => A().state.state?.lean_overrides || {};
  const prof = (h) => A().state.state?.publishers?.[h] || { name: h };

  function summary() {
    const n = Object.keys(overrides()).length;
    return `<p class="fine leanSummary">${n ? `You've placed ${n} outlet${n === 1 ? "" : "s"} yourself; cards mark them “yours”.` : "Disagree with a rating? Click the lean label on any card to place the outlet yourself."} ${n ? `<button class="linkButton" data-leanlist="1">Review your ratings</button>` : ""}</p>`;
  }
  function dialog() {
    let d = document.querySelector("#leanDialog");
    if (!d) {
      d = document.createElement("div");
      d.id = "leanDialog"; d.className = "leanOverlay"; d.hidden = true;
      document.body.appendChild(d);
    }
    return d;
  }
  function editView() {
    const p = prof(S.host), o = overrides()[S.host];
    const published = p.lean_user ? p.lean_original : p.lean;
    const pick = S.pick === undefined ? (o ? o.lean : published) : S.pick;
    const raters = (p.raters || []).map((r) => `${esc(r.provider)}: ${esc(r.rating)}`).join(" · ");
    return `<div class="leanBox" role="dialog" aria-modal="true" aria-labelledby="leanTitle">
      <header><div>${A().logoTag(p)}<h2 id="leanTitle">Where would you place ${esc(p.name || S.host)}?</h2></div><button class="action" data-leanclose="1" aria-label="Close">Close</button></header>
      <p class="fine">Published rating: <b>${esc(name(published))}</b>${raters ? ` (${raters})` : p.kind && p.kind !== "news" && p.kind !== "unclassified" ? " (institution, not rated by the raters)" : ""}.${o ? ` Your rating: <b>${esc(name(o.lean))}</b>.` : ""}</p>
      <div class="leanScale" role="radiogroup" aria-label="Your placement">
        ${SCALE.map(([v, t]) => `<button role="radio" aria-checked="${pick === v}" class="l${v + 2} ${pick === v ? "on" : ""}" data-leanpick="${v}">${t}${published === v ? `<small>published</small>` : ""}</button>`).join("")}
      </div>
      <button role="radio" aria-checked="${pick == null}" class="leanNone ${pick == null ? "on" : ""}" data-leanpick="none">Not rated: I don't want this outlet counted on either side${published == null ? " <small>published</small>" : ""}</button>
      <label class="leanNote">Why (optional, only for you)<textarea id="leanNote" rows="2" maxlength="300" placeholder="For example: its opinion pages lean right even though its reporting is rated centre.">${esc(S.note || o?.note || "")}</textarea></label>
      <p class="fine">Your rating replaces the published one everywhere in Sanjaya on this computer: card labels, gauges, the political spread and the coverage graph. Cards mark it “yours”, and the published rating stays one click away.</p>
      <div class="leanActions"><button class="action primary" data-leansave="1" ${S.busy ? "disabled" : ""}>Save my rating</button>
        ${o ? `<button class="action" data-leanreset="${esc(S.host)}">Use the published rating</button>` : ""}
        <span class="leanSpacer"></span>${Object.keys(overrides()).length ? `<button class="linkButton" data-leanlist="1">All your ratings (${Object.keys(overrides()).length})</button>` : ""}</div></div>`;
  }
  function listView() {
    const rows = Object.entries(overrides()).sort((a, b) => (prof(a[0]).name || a[0]).localeCompare(prof(b[0]).name || b[0]));
    return `<div class="leanBox wide" role="dialog" aria-modal="true" aria-labelledby="leanTitle">
      <header><div><h2 id="leanTitle">Your lean ratings</h2></div><button class="action" data-leanclose="1" aria-label="Close">Close</button></header>
      <p class="fine">Outlets you've placed yourself. Each replaces the published rating everywhere in Sanjaya on this computer.</p>
      ${rows.length ? `<table class="leanTable"><thead><tr><th>Outlet</th><th>Published</th><th>Yours</th><th>Why</th><th></th></tr></thead><tbody>
        ${rows.map(([h, o]) => { const p = prof(h); return `<tr><td>${A().logoTag(p, "xs")} ${esc(p.name || h)}</td><td>${esc(name(p.lean_user ? p.lean_original : p.lean))}</td><td><b>${esc(name(o.lean))}</b></td><td class="fine">${esc(o.note || "")}</td>
          <td><button class="linkButton" data-leanedit="${esc(h)}">Change</button> <button class="linkButton" data-leanreset="${esc(h)}">Reset</button></td></tr>`; }).join("")}</tbody></table>` : `<p>You haven't placed any outlets yet.</p>`}
      ${rows.length > 1 ? `<div class="leanActions"><button class="action" data-leanresetall="1">Reset all to published ratings</button></div>` : ""}</div>`;
  }
  function draw() {
    const d = dialog();
    d.innerHTML = S.mode === "list" ? listView() : editView();
    d.hidden = false;
    document.body.classList.add("leanOpen");
  }
  function open(host) { S.back = document.activeElement; S.host = host; S.pick = undefined; S.note = ""; S.mode = "edit"; draw(); setTimeout(() => document.querySelector("#leanDialog [data-leanpick].on, #leanDialog [data-leanpick]")?.focus(), 20); }
  function list() { S.back = S.back || document.activeElement; S.mode = "list"; draw(); setTimeout(() => document.querySelector("#leanDialog [data-leanclose]")?.focus(), 20); }
  function close() { const d = dialog(); d.hidden = true; d.innerHTML = ""; document.body.classList.remove("leanOpen"); S.back?.focus?.(); S.back = null; }
  async function send(host, lean, note) {
    S.busy = true;
    try {
      await A().api("/api/lean", "POST", { host, lean, note });
      await A().hydrate();
      return true;
    } catch (e) { A().tip(e.message); return false; } finally { S.busy = false; }
  }

  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-leanedit],[data-leanlist],[data-leanclose],[data-leanpick],[data-leansave],[data-leanreset],[data-leanresetall]");
    if (!b) { if (e.target.id === "leanDialog") close(); return; }
    e.preventDefault(); e.stopPropagation();
    if (b.dataset.leanedit) return open(b.dataset.leanedit);
    if (b.dataset.leanlist) return list();
    if (b.dataset.leanclose) return close();
    if (b.dataset.leanpick) { S.note = document.querySelector("#leanNote")?.value ?? S.note; S.pick = b.dataset.leanpick === "none" ? null : Number(b.dataset.leanpick); draw(); document.querySelector(`#leanDialog [data-leanpick="${b.dataset.leanpick}"]`)?.focus(); return; }
    if (b.dataset.leansave) {
      const p = prof(S.host), o = overrides()[S.host];
      const pick = S.pick === undefined ? (o ? o.lean : p.lean) : S.pick;
      const note = document.querySelector("#leanNote")?.value || "";
      if (await send(S.host, pick == null ? "none" : pick, note)) { A().tip(`Saved: ${p.name || S.host} is now “${name(pick)}” in Sanjaya.`); close(); }
      return;
    }
    if (b.dataset.leanreset) {
      const h = b.dataset.leanreset, p = prof(h);
      if (await send(h, "reset", "")) { A().tip(`${p.name || h} uses its published rating again.`); S.mode === "list" ? draw() : close(); }
      return;
    }
    if (b.dataset.leanresetall) {
      for (const h of Object.keys(overrides())) await A().api("/api/lean", "POST", { host: h, lean: "reset" }).catch(() => {});
      await A().hydrate(); draw();
    }
  }, true);
  document.addEventListener("keydown", (e) => {
    const d = document.querySelector("#leanDialog");
    if (!d || d.hidden) return;
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key === "Tab") { // keep focus inside the dialog
      const f = [...d.querySelectorAll("button,textarea,a[href]")].filter((x) => !x.disabled);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
    if (["ArrowLeft", "ArrowRight"].includes(e.key) && e.target.dataset?.leanpick) {
      const order = ["-2", "-1", "0", "1", "2"], i = order.indexOf(e.target.dataset.leanpick);
      if (i >= 0) { const n = order[Math.max(0, Math.min(4, i + (e.key === "ArrowRight" ? 1 : -1)))]; S.pick = Number(n); draw(); document.querySelector(`#leanDialog [data-leanpick="${n}"]`)?.focus(); e.preventDefault(); }
    }
  });
  return { open, list, summary };
})();
