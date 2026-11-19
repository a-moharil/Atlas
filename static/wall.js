/* Sanjaya wall controls: a dice that re-deals the headlines in a panel, and
   "Remove from wall" for single articles. Removal only hides an article from
   display panels; it stays in the database, in coverage counts and in
   Compare coverage. Shuffles last until the page is reloaded or set back. */
(() => {
  "use strict";
  const E = (x) =>
    String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const seeds = {};
  let hiddenSet = null, hiddenSrc = null, undoTimer = 0;

  const state = () => window.ATLAS?.state?.state || {};
  function hiddenIds() {
    const list = state().wall_hidden || [];
    if (list !== hiddenSrc) { hiddenSrc = list; hiddenSet = new Set(list); }
    return hiddenSet;
  }
  const isHidden = (id) => hiddenIds().has(String(id));
  const visible = (list, idOf = (e) => e.id) => (list || []).filter((e) => !isHidden(idOf(e)));

  // Stable per-seed order, so the 60-second background refresh doesn't re-deal the wall.
  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
    return h >>> 0;
  }
  const seed = (key) => seeds[key] || 0;
  const shuffled = (key) => !!seeds[key];
  function arrange(list, key, n = Infinity, idOf = (e) => e.id) {
    const s = seeds[key];
    const l = s ? list.map((e) => [hash(String(idOf(e)) + ":" + s), e]).sort((a, b) => a[0] - b[0]).map((x) => x[1]) : list.slice();
    return l.slice(0, n);
  }
  const pips = { 1: [[12, 12]], 2: [[7.5, 7.5], [16.5, 16.5]], 3: [[7, 7], [12, 12], [17, 17]], 4: [[7.5, 7.5], [16.5, 7.5], [7.5, 16.5], [16.5, 16.5]], 5: [[7, 7], [17, 7], [12, 12], [7, 17], [17, 17]], 6: [[7.5, 6.5], [16.5, 6.5], [7.5, 12], [16.5, 12], [7.5, 17.5], [16.5, 17.5]] };
  function face(n) {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="none" stroke="currentColor" stroke-width="1.6"/>${pips[n].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.7" fill="currentColor"/>`).join("")}</svg>`;
  }
  // The dice for a panel. `pool` is how many headlines it deals from.
  function dice(key, pool) {
    const s = seeds[key];
    const n = s ? (s % 6) + 1 : 5;
    const title = `Shuffle: deal a different set of headlines${pool ? ` from the ${pool} held` : ""}`;
    return `<span class="wallDice"><button class="diceBtn ${s ? "on" : ""}" data-dice="${E(key)}" title="${E(title)}" aria-label="${E(title)}">${face(n)}</button>${s ? `<button class="linkButton diceReset" data-dicereset="${E(key)}" title="Back to the usual order">Usual order</button>` : ""}</span>`;
  }
  function removeBtn(ids, label = "Remove from wall") {
    const list = [].concat(ids).map(String);
    return `<button class="wallRemove" data-wallhide="${E(list.join("|"))}" title="${E(label)}. It stays in coverage counts and can be restored." aria-label="${E(label)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span>Remove</span></button>`;
  }
  // "N removed · Restore all" — shown only when something is hidden.
  function restoreLine() {
    const n = (state().wall_hidden || []).length;
    return n ? `<button class="linkButton wallRestore" data-wallrestore="1" title="Put every removed article back on the walls">${n} removed · Restore all</button>` : "";
  }

  const changed = () => document.dispatchEvent(new CustomEvent("atlas:wall"));
  async function save(body) {
    const r = await fetch("/api/wall", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(10000) });
    const d = await r.json();
    if (!r.ok) throw Error(d.error || "Could not save");
    const st = state();
    st.wall_hidden = d.wall_hidden || [];
    changed();
  }
  function bar(html) {
    let el = document.getElementById("wallBar");
    if (!el) {
      el = document.createElement("div");
      el.id = "wallBar";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    el.innerHTML = html;
    el.classList.add("show");
    clearTimeout(undoTimer);
    undoTimer = setTimeout(() => el.classList.remove("show"), 7000);
  }
  async function hide(ids) {
    const st = state();
    st.wall_hidden = [...new Set([...ids, ...(st.wall_hidden || [])])]; // instant, then confirm with the server
    changed();
    try {
      await save({ ids, hidden: true });
      bar(`<span>Removed from the wall</span><button data-wallundo="${E(ids.join("|"))}">Undo</button>`);
    } catch (e) {
      st.wall_hidden = (st.wall_hidden || []).filter((x) => !ids.includes(x));
      changed();
      bar(`<span>Could not remove: ${E(e.message)}</span>`);
    }
  }

  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-dice],[data-dicereset],[data-wallhide],[data-wallundo],[data-wallrestore]");
    if (!b) return;
    ev.preventDefault();
    ev.stopPropagation();
    if (b.dataset.dice) {
      const k = b.dataset.dice;
      let s;
      do s = 1 + Math.floor(Math.random() * 2 ** 30); while (s === seeds[k]);
      seeds[k] = s;
      changed();
      const again = document.querySelector(`[data-dice="${CSS.escape(k)}"]`);
      if (again) { again.classList.add("rolling"); again.focus({ preventScroll: true }); }
    } else if (b.dataset.dicereset) {
      delete seeds[b.dataset.dicereset];
      changed();
    } else if (b.dataset.wallhide) hide(b.dataset.wallhide.split("|"));
    else if (b.dataset.wallundo)
      save({ ids: b.dataset.wallundo.split("|"), hidden: false }).then(() => bar("<span>Restored</span>"), (e) => bar(`<span>${E(e.message)}</span>`));
    else if (b.dataset.wallrestore)
      save({ clear: true }).then(() => bar("<span>Every removed article is back on the walls</span>"), (e) => bar(`<span>${E(e.message)}</span>`));
  }, true);

  window.ATLASWall = { dice, removeBtn, restoreLine, arrange, visible, isHidden, shuffled, seed };
})();
