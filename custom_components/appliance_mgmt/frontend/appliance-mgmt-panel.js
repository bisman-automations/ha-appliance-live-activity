/*
 * Appliances sidebar dashboard for Appliance Mgmt.
 *
 * One plain web component, no build step. The backend sends each appliance's
 * entities, recent cycles, maintenance alerts and picture
 * (appliance_mgmt/appliances); everything live (status, time left,
 * progress) comes straight from hass.states. Pictures are uploaded with Home
 * Assistant's image upload (/api/image/upload), like person pictures.
 */

const DOMAIN = "appliance_mgmt";
const DASH_KEY = "appliance-live-activity-dashboard"; // kept from before 2.0.0 so saved layouts stay
const OPEN_KEY = "appliance-live-activity-open";
const REFRESH_MS = 60000;
const ACTIVE = ["running", "paused", "delayed"];

const SHOWS = [
  { id: "all", label: "All appliances" },
  { id: "active", label: "Running now" },
  { id: "attention", label: "Needs attention" },
  { id: "idle", label: "Not running" },
];
const SORTS = [
  { id: "activity", label: "Running, then recent" },
  { id: "name", label: "Name" },
  { id: "type", label: "Type" },
];

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const minutesText = (minutes) => {
  const m = Math.max(0, Math.round(Number(minutes) || 0));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
};

const clockText = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};

const whenText = (iso) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  const time = clockText(iso);
  if (d.toDateString() === today.toDateString()) return `Today ${time}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
  return `${d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} ${time}`;
};

const usable = (state) => state && !["unknown", "unavailable", ""].includes(state.state);

const STYLES = `
  :host {
    display: block; min-height: 100%;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
    --ala-card: var(--card-background-color, #fff);
    --ala-divider: var(--divider-color, #e0e0e0);
    --ala-muted: var(--secondary-text-color, #727272);
    --ala-radius: var(--ha-card-border-radius, 12px);
  }
  .toolbar {
    display: flex; align-items: center; gap: 4px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    position: sticky; top: 0; z-index: 2;
  }
  .title { font-size: 20px; font-weight: 400; margin-left: 4px; }
  main { max-width: 1200px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
  .tools { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 16px; }
  .tools[hidden] { display: none; }
  .tools label { display: inline-flex; align-items: center; gap: 8px; }
  input[type="text"], select {
    font: inherit; font-size: 15px; padding: 9px 12px; min-height: 42px; box-sizing: border-box;
    border-radius: 8px; border: 1px solid var(--ala-divider);
    background: var(--ala-card); color: inherit;
  }
  #search { flex: 1; min-width: 200px; max-width: 420px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
  .card {
    background: var(--ala-card); border: 1px solid var(--ala-divider); border-radius: var(--ala-radius);
    box-shadow: var(--ha-card-box-shadow, none); overflow: hidden; display: flex; flex-direction: column;
  }
  .pic {
    position: relative; height: 170px; display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, color-mix(in srgb, var(--c) 30%, var(--ala-card)), color-mix(in srgb, var(--c) 8%, var(--ala-card)));
  }
  .pic img { width: 100%; height: 100%; object-fit: cover; }
  .pic ha-icon { --mdc-icon-size: 84px; color: var(--c); }
  .chip {
    position: absolute; top: 10px; left: 10px; padding: 4px 10px; border-radius: 999px;
    font-size: 13px; font-weight: 500; background: rgba(0,0,0,.62); color: #fff;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .chip .dot { width: 8px; height: 8px; border-radius: 50%; background: #9e9e9e; }
  .chip.running .dot { background: #4caf50; }
  .chip.paused .dot, .chip.delayed .dot { background: #ff9800; }
  .chip.complete .dot { background: #03a9f4; }
  .chip.open .dot { background: #ff9800; }
  .body { padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 10px; flex: 1; }
  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .name { font-size: 18px; font-weight: 500; color: inherit; text-decoration: none; }
  .name:hover { text-decoration: underline; }
  .type { font-size: 13px; color: var(--ala-muted); white-space: nowrap; }
  .now { font-size: 15px; }
  .now .sub { color: var(--ala-muted); font-size: 13px; margin-top: 2px; }
  .bar { height: 8px; border-radius: 4px; background: var(--ala-divider); overflow: hidden; }
  .bar > div { height: 100%; background: var(--c); transition: width .6s ease; }
  .times { display: flex; justify-content: space-between; font-size: 13px; color: var(--ala-muted); }
  .alerts { display: flex; flex-direction: column; gap: 6px; }
  .alert {
    font-size: 14px; padding: 8px 10px; border-radius: 8px;
    background: color-mix(in srgb, var(--warning-color, #ff9800) 14%, transparent);
  }
  .alert.bad { background: color-mix(in srgb, var(--error-color, #db4437) 16%, transparent); }
  .facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .fact { font-size: 12px; color: var(--ala-muted); }
  .fact b { display: block; font-size: 15px; font-weight: 500; color: var(--primary-text-color); margin-top: 2px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: auto; padding-top: 4px; }
  button {
    font: inherit; font-size: 14px; cursor: pointer; min-height: 38px; padding: 6px 14px;
    border-radius: 19px; border: 1px solid var(--ala-divider); background: transparent; color: inherit;
  }
  button:hover:not(:disabled) { border-color: var(--primary-color); }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  button:disabled { opacity: .5; cursor: default; }
  .cycles { margin: 0; padding: 0; list-style: none; font-size: 14px; }
  .cycles li { display: flex; justify-content: space-between; padding: 6px 0; border-top: 1px solid var(--ala-divider); }
  .cycles li span:last-child { color: var(--ala-muted); }
  .note { font-size: 13px; min-height: 18px; }
  .note.error { color: var(--error-color, #db4437); }
  .empty { max-width: 520px; margin: 48px auto; text-align: center; color: var(--ala-muted); line-height: 1.5; }
  .error-box { color: var(--error-color, #db4437); margin-bottom: 12px; }
  @media (max-width: 420px) {
    main { padding: 12px; }
    .grid { grid-template-columns: 1fr; }
  }
`;

class ApplianceLiveActivityPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._appliances = null;
    this._isAdmin = false;
    this._error = "";
    this._notes = {};
    this._busy = new Set();
    this._lastGrid = "";
    this._statusKey = "";
    this._dash = { show: "all", sort: "activity", query: "" };
    this._open = new Set();
    try {
      const saved = JSON.parse(localStorage.getItem(DASH_KEY) || "{}");
      if (SHOWS.some((o) => o.id === saved.show)) this._dash.show = saved.show;
      if (SORTS.some((o) => o.id === saved.sort)) this._dash.sort = saved.sort;
      this._open = new Set(JSON.parse(localStorage.getItem(OPEN_KEY) || "[]"));
    } catch (err) {
      /* storage unavailable: the defaults */
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._build();
    if (first) this._load();
    this._watchStatuses();
    this._render();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._render(true);
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), REFRESH_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  async _load() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/appliances` });
      this._appliances = res.appliances;
      this._isAdmin = !!res.is_admin;
      this._error = "";
    } catch (err) {
      this._error = `Couldn't load the appliances: ${err?.message || err}`;
    }
    this._render(true);
  }

  // A cycle starting or ending changes recent cycles and alerts: reload them.
  _watchStatuses() {
    if (!this._appliances) return;
    const key = this._appliances.map((a) => this._hass.states[a.entities.status]?.state).join("|");
    if (this._statusKey && key !== this._statusKey) {
      clearTimeout(this._reloadTimer);
      this._reloadTimer = setTimeout(() => this._load(), 1500);
    }
    this._statusKey = key;
  }

  _saveDash() {
    try {
      localStorage.setItem(DASH_KEY, JSON.stringify({ show: this._dash.show, sort: this._dash.sort }));
      localStorage.setItem(OPEN_KEY, JSON.stringify([...this._open]));
    } catch (err) {
      /* not remembered, still works */
    }
  }

  _build() {
    if (this._built) return;
    this._built = true;
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="toolbar"><div class="menu"></div><div class="title">Appliances</div></div>
      <main>
        <div class="error-box" role="alert"></div>
        <div class="tools" hidden>
          <input type="text" id="search" placeholder="Search appliances" aria-label="Search appliances" autocomplete="off">
          <label>Show <select id="show">${SHOWS.map((o) => `<option value="${o.id}">${o.label}</option>`).join("")}</select></label>
          <label>Sort by <select id="sort">${SORTS.map((o) => `<option value="${o.id}">${o.label}</option>`).join("")}</select></label>
        </div>
        <div class="list"></div>
        <input type="file" id="file" accept="image/*" hidden>
      </main>`;
    const root = this.shadowRoot;
    root.getElementById("show").value = this._dash.show;
    root.getElementById("sort").value = this._dash.sort;
    root.addEventListener("click", (ev) => this._onClick(ev));
    root.addEventListener("change", (ev) => this._onChange(ev));
    root.getElementById("search").addEventListener("input", (ev) => {
      this._dash.query = ev.target.value.trim();
      this._render(true);
    });
  }

  // ------------------------------------------------------------- state

  _status(a) {
    return this._hass.states[a.entities.status]?.state || "idle";
  }

  _isActive(a) {
    return ACTIVE.includes(this._status(a));
  }

  // Door open, a leak or other alert, or a finished load waiting.
  _needsAttention(a) {
    const attrs = this._hass.states[a.entities.status]?.attributes || {};
    return a.alerts.length > 0 || attrs.leak_detected || attrs.vent_blocked || attrs.cooktop_on
      || (a.door && this._status(a) === "running") || (!a.door && this._status(a) === "complete");
  }

  _lastFinished(a) {
    return a.recent_cycles[0] ? new Date(a.recent_cycles[0].finished).getTime() : 0;
  }

  _shown() {
    const d = this._dash;
    const q = d.query.toLowerCase();
    const shows = {
      all: () => true,
      active: (a) => this._isActive(a) || (a.door && this._status(a) === "running"),
      attention: (a) => this._needsAttention(a),
      idle: (a) => !this._isActive(a),
    };
    const byName = (x, y) => x.name.localeCompare(y.name);
    const rank = (a) => (this._isActive(a) && !a.door ? 0 : this._needsAttention(a) ? 1 : 2);
    const sorts = {
      activity: (x, y) => rank(x) - rank(y) || this._lastFinished(y) - this._lastFinished(x) || byName(x, y),
      name: byName,
      type: (x, y) => x.type_name.localeCompare(y.type_name) || byName(x, y),
    };
    return this._appliances
      .filter((a) => (shows[d.show] || shows.all)(a))
      .filter((a) => !q || [a.name, a.type_name].some((v) => String(v).toLowerCase().includes(q)))
      .sort(sorts[d.sort] || sorts.activity);
  }

  // ------------------------------------------------------------- render

  _render(force = false) {
    if (!this._built || !this._hass) return;
    const menu = this.shadowRoot.querySelector(".menu");
    let button = menu.querySelector("ha-menu-button");
    if (!button) {
      button = document.createElement("ha-menu-button");
      menu.appendChild(button);
    }
    button.hass = this._hass;
    button.narrow = this._narrow;

    this.shadowRoot.querySelector(".error-box").textContent = this._error;
    const list = this.shadowRoot.querySelector(".list");
    const tools = this.shadowRoot.querySelector(".tools");
    let html;
    if (this._appliances === null) {
      html = this._error ? "" : `<div class="empty">Loading your appliances…</div>`;
    } else if (!this._appliances.length) {
      html = `<div class="empty"><h2>No appliances yet</h2><p>Add an appliance under Settings → Devices &amp; services → Appliance Mgmt.</p></div>`;
    } else {
      const shown = this._shown();
      html = shown.length
        ? `<div class="grid">${shown.map((a) => this._card(a)).join("")}</div>`
        : `<div class="empty"><h2>No appliances match</h2><p><button data-reset>Show all appliances</button></p></div>`;
    }
    tools.hidden = !this._appliances || this._appliances.length < 2;
    // Redraw only when something shown changed, so buttons don't flicker.
    if (force || html !== this._lastGrid) {
      this._lastGrid = html;
      list.innerHTML = html;
    }
  }

  _statusLine(a) {
    const st = this._hass.states;
    const status = this._status(a);
    const attrs = st[a.entities.status]?.attributes || {};
    if (a.door) {
      if (status === "running") {
        const open = attrs.open_minutes;
        return { chip: "Open", cls: "open", now: open ? `Open for ${minutesText(open)}` : "Open" };
      }
      return { chip: "Closed", cls: "idle", now: "Closed" };
    }
    const phase = attrs.phase && !["idle", "complete"].includes(String(attrs.phase).toLowerCase()) ? attrs.phase : "";
    switch (status) {
      case "running":
        return { chip: "Running", cls: "running", now: phase || "Running" };
      case "paused":
        return { chip: "Paused", cls: "paused", now: phase ? `Paused · ${phase}` : "Paused" };
      case "delayed":
        return { chip: "Delayed start", cls: "delayed", now: attrs.starts_at ? `Starts at ${clockText(attrs.starts_at)}` : "Waiting to start" };
      case "complete":
        return { chip: "Done", cls: "complete", now: a.recent_cycles[0] ? `Finished ${whenText(a.recent_cycles[0].finished).replace(/^Today /, "at ")}` : "Finished" };
      default:
        return { chip: "Idle", cls: "idle", now: a.recent_cycles[0] ? `Last run ${whenText(a.recent_cycles[0].finished)}` : "Idle" };
    }
  }

  _progress(a) {
    const st = this._hass.states;
    if (!["running", "paused"].includes(this._status(a)) || a.door) return "";
    const pct = Number(st[a.entities.progress]?.state);
    const left = st[a.entities.time_left];
    const finish = st[a.entities.finishes_at];
    const parts = [];
    if (usable(left) && Number(left.state) > 0) parts.push(`<span>${minutesText(left.state)} left</span>`);
    if (usable(finish)) parts.push(`<span>Done at ${clockText(finish.state)}</span>`);
    const bar = Number.isFinite(pct) && pct > 0
      ? `<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}" aria-label="${esc(a.name)} progress"><div style="width:${Math.min(100, pct)}%"></div></div>`
      : "";
    return `${bar}${parts.length ? `<div class="times">${parts.join("")}</div>` : ""}`;
  }

  _alerts(a) {
    const st = this._hass.states;
    const attrs = st[a.entities.status]?.attributes || {};
    const items = [];
    if (attrs.leak_detected) items.push(["Water leak detected", true]);
    if (attrs.vent_blocked) items.push(["Dryer vent may be blocked", false]);
    if (attrs.cooktop_on) items.push([`Cooktop on${attrs.cooktop_on_minutes ? ` for ${minutesText(attrs.cooktop_on_minutes)}` : ""}`, false]);
    if (attrs.probe_temperature) items.push([`Probe ${attrs.probe_temperature}°${attrs.probe_target ? ` of ${attrs.probe_target}°` : ""}`, false]);
    if (attrs.kitchen_timer_minutes) items.push([`Kitchen timer: ${minutesText(attrs.kitchen_timer_minutes)}`, false]);
    if (attrs.snoozed_until) items.push([`Reminders snoozed until ${clockText(attrs.snoozed_until)}`, false]);
    for (const text of a.alerts) items.push([text, /leak|warm/i.test(text)]);
    if (!items.length) return "";
    return `<div class="alerts">${items.map(([t, bad]) => `<div class="alert${bad ? " bad" : ""}">${esc(t)}</div>`).join("")}</div>`;
  }

  _facts(a) {
    const st = this._hass.states;
    const facts = [];
    for (const t of a.temperatures) {
      const s = st[t.entity_id];
      if (usable(s)) facts.push([t.zone === "fridge" ? "Fridge" : "Freezer", `${Math.round(Number(s.state))}${s.attributes.unit_of_measurement || "°"}`]);
    }
    if (!a.door) {
      const week = st[a.entities.cycles_week];
      if (usable(week)) facts.push(["This week", `${week.state} ${Number(week.state) === 1 ? "cycle" : "cycles"}`]);
      const avg = st[a.entities.average_cycle];
      if (usable(avg) && Number(avg.state) > 0) facts.push(["Usual cycle", minutesText(avg.state)]);
      if (a.recent_cycles[0]) facts.push(["Last cycle", minutesText(a.recent_cycles[0].minutes)]);
    }
    if (!facts.length) return "";
    return `<div class="facts">${facts.map(([k, v]) => `<div class="fact">${esc(k)}<b>${esc(v)}</b></div>`).join("")}</div>`;
  }

  _card(a) {
    const line = this._statusLine(a);
    const id = a.entry_id;
    const pic = a.image
      ? `<img src="${esc(a.image)}" alt="" loading="lazy">`
      : `<ha-icon icon="${esc(a.icon)}"></ha-icon>`;
    const open = this._open.has(id);
    const cycles = !a.door && a.recent_cycles.length
      ? `<button data-cycles="${esc(id)}" aria-expanded="${open}">${open ? "Hide recent cycles" : "Recent cycles"}</button>`
      : "";
    const busy = this._busy.has(id);
    const picButtons = this._isAdmin
      ? `<button data-pic="${esc(id)}" ${busy ? "disabled" : ""}>${a.image ? "Change picture" : "Add picture"}</button>
         ${a.image ? `<button data-unpic="${esc(id)}" ${busy ? "disabled" : ""}>Remove picture</button>` : ""}`
      : "";
    const update = a.entities.update_live_activity
      ? `<button data-update="${esc(a.entities.update_live_activity)}" data-id="${esc(id)}">Update Live Activity</button>`
      : "";
    const note = this._notes[id];
    return `<section class="card" style="--c:${esc(a.color || "#03a9f4")}" aria-label="${esc(a.name)}">
      <div class="pic">${pic}<span class="chip ${line.cls}"><span class="dot"></span>${esc(line.chip)}</span></div>
      <div class="body">
        <div class="head"><a class="name" href="${esc(a.link)}">${esc(a.name)}</a><span class="type">${esc(a.type_name)}</span></div>
        <div class="now">${esc(line.now)}</div>
        ${this._progress(a)}
        ${this._alerts(a)}
        ${this._facts(a)}
        ${open && cycles ? `<ul class="cycles">${a.recent_cycles.map((c) => `<li><span>${esc(whenText(c.finished))}</span><span>${minutesText(c.minutes)}</span></li>`).join("")}</ul>` : ""}
        <div class="actions">${update}${cycles}${picButtons}</div>
        ${note ? `<div class="note${note.error ? " error" : ""}" role="status">${esc(note.text)}</div>` : ""}
      </div>
    </section>`;
  }

  // ------------------------------------------------------------- events

  _onChange(ev) {
    const el = ev.target;
    if (el.id === "show" || el.id === "sort") {
      this._dash[el.id] = el.value;
      this._saveDash();
      this._render(true);
    } else if (el.id === "file" && el.files?.[0]) {
      const file = el.files[0];
      el.value = "";
      this._upload(this._picFor, file);
    }
  }

  _onClick(ev) {
    const el = ev.target.closest("button, a.name");
    if (!el) return;
    if (el.matches("a.name")) {
      // Navigate inside Home Assistant rather than reloading the page.
      ev.preventDefault();
      history.pushState(null, "", el.getAttribute("href"));
      window.dispatchEvent(new CustomEvent("location-changed"));
      return;
    }
    const ds = el.dataset;
    if ("reset" in ds) {
      this._dash = { ...this._dash, show: "all", query: "" };
      this.shadowRoot.getElementById("show").value = "all";
      this.shadowRoot.getElementById("search").value = "";
      this._saveDash();
      this._render(true);
    } else if (ds.cycles) {
      if (this._open.has(ds.cycles)) this._open.delete(ds.cycles);
      else this._open.add(ds.cycles);
      this._saveDash();
      this._render(true);
    } else if (ds.update) {
      this._press(ds.id, ds.update);
    } else if (ds.pic) {
      this._picFor = ds.pic;
      this.shadowRoot.getElementById("file").click();
    } else if (ds.unpic) {
      this._setImage(ds.unpic, null, "Picture removed.");
    }
  }

  _note(id, text, error = false) {
    this._notes[id] = { text, error };
    this._render(true);
    clearTimeout(this._noteTimers?.[id]);
    this._noteTimers = this._noteTimers || {};
    if (!error) this._noteTimers[id] = setTimeout(() => { delete this._notes[id]; this._render(true); }, 4000);
  }

  async _press(id, entityId) {
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
      this._note(id, "Live Activity sent again.");
    } catch (err) {
      this._note(id, `Couldn't update it: ${err?.message || err}`, true);
    }
  }

  async _upload(id, file) {
    if (!id) return;
    if (!file.type.startsWith("image/")) {
      this._note(id, "That isn't a picture. Pick a JPEG, PNG or similar image.", true);
      return;
    }
    this._busy.add(id);
    this._render(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await this._hass.fetchWithAuth("/api/image/upload", { method: "POST", body: form });
      if (res.status === 404) throw new Error("Home Assistant's image upload isn't loaded (it's part of default_config)");
      if (res.status === 413) throw new Error("the picture is too big");
      if (!res.ok) throw new Error(`upload failed (${res.status})`);
      const image = await res.json();
      await this._setImage(id, image.id, "Picture saved.");
    } catch (err) {
      this._note(id, `Couldn't save the picture: ${err?.message || err}`, true);
    } finally {
      this._busy.delete(id);
      this._render(true);
    }
  }

  async _setImage(id, imageId, done) {
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/image`, entry_id: id, image_id: imageId });
      // The old picture isn't used anywhere else: delete it.
      if (res.previous_image_id && res.previous_image_id !== imageId) {
        this._hass.callWS({ type: "image/delete", image_id: res.previous_image_id }).catch(() => {});
      }
      const appliance = this._appliances.find((a) => a.entry_id === id);
      if (appliance) {
        appliance.image = res.image;
        appliance.image_id = imageId;
      }
      this._note(id, done);
    } catch (err) {
      this._note(id, `Couldn't change the picture: ${err?.message || err}`, true);
    }
  }
}

if (!customElements.get("appliance-mgmt-panel")) {
  customElements.define("appliance-mgmt-panel", ApplianceLiveActivityPanel);
}
