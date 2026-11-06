"use strict";
/* The control panel page. Plain JavaScript, no libraries. Everything that comes from the dashboard's files is put on the page as text (never as HTML). */

const framed = window.parent !== window;
let S = null;                 // what the server says (look, background, layout, cards, links)
let view = "look";
let lookW = null, bgW = null, layW = null;     // the changes in progress (not saved yet)
const root = document.getElementById("app");
const BLURS = ["none", "sm", "md", "lg", "xl", "2xl", "3xl"];
const VIEWS = [["look", "Look"], ["background", "Background"], ["layout", "Layout"], ["cards", "Cards"], ["links", "Links"]];

try { const v = sessionStorage.getItem("hlp-view"); if (v && VIEWS.some(x => x[0] === v)) view = v; } catch (e) { /* storage may be blocked */ }

// ---------------------------------------------------------------- small helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function add(el, ...kids) {
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const put = (el, ...kids) => { el.replaceChildren(); return add(el, ...kids); };
const clone = o => JSON.parse(JSON.stringify(o));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function send(msg) { if (framed) { try { window.parent.postMessage(Object.assign({ hlp: 1 }, msg), "*"); } catch (e) { /* no parent */ } } }

async function api(method, path, body, raw) {
  const opt = { method, credentials: "same-origin", headers: { "X-Panel": "1" } };
  if (raw) { opt.body = raw; opt.headers["Content-Type"] = "application/octet-stream"; }
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(path, opt); } catch (e) { throw new Error("The panel does not answer. Is the server on?"); }
  let js = {};
  try { js = await r.json(); } catch (e) { /* no body */ }
  if (r.status === 401 && path !== "/api/login") { S = null; showLogin(); throw new Error(js.error || "Please log in again."); }
  if (!r.ok) throw new Error(js.error || ("Something went wrong (" + r.status + ")."));
  return js;
}

let toastTimer = null;
function toast(msg, bad, action) {
  const t = document.getElementById("toast");
  t.className = "show" + (bad ? " bad" : "");
  put(t, h("span", {}, msg), action ? h("button", { class: "small", onclick: action[1] }, action[0]) : null);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ""; }, bad ? 7000 : 3800);
}
const fail = e => toast(e.message || String(e), true);

function confirmBox(title, text, yes, danger) {
  return new Promise(resolve => {
    const d = h("dialog", {}, h("h2", {}, title), h("p", {}, text),
      h("div", { class: "actions" },
        h("button", { onclick: () => { d.close(); resolve(false); } }, "Cancel"),
        h("button", { class: danger ? "danger" : "primary", onclick: () => { d.close(); resolve(true); } }, yes)));
    d.addEventListener("close", () => { d.remove(); resolve(false); });
    document.body.append(d);
    d.showModal();
  });
}

function askText(title, label, value) {
  // the browser's own prompt() is blocked inside the dashboard's frame, so the panel has its own
  return new Promise(resolve => {
    const inp = h("input", { type: "text", value: value || "", maxlength: 40, "aria-label": label });
    let done = false;
    const finish = v => { if (!done) { done = true; resolve(v); } d.close(); };
    inp.addEventListener("keydown", e => { if (e.key === "Enter") finish(inp.value.trim()); });
    const d = h("dialog", {}, h("h2", {}, title), h("div", { class: "field" }, h("label", {}, label), inp),
      h("div", { class: "actions" }, h("button", { onclick: () => finish(null) }, "Cancel"), h("button", { class: "primary", onclick: () => finish(inp.value.trim()) }, "OK")));
    d.addEventListener("close", () => { d.remove(); finish(null); });
    document.body.append(d);
    d.showModal();
    inp.focus();
    inp.select();
  });
}

function afterChange(reload) {
  return api("GET", "/api/state").then(s => {
    const y = window.scrollY;
    S = s;
    lookW = bgW = layW = null;
    render();
    window.scrollTo(0, y);
    if (reload && autoReload()) setTimeout(() => send({ type: "reload" }), 900);
  });
}
function autoReload() { try { return localStorage.getItem("hlp-auto") !== "0"; } catch (e) { return true; } }

// ---------------------------------------------------------------- icons
const MDI = ("home server router lan wifi network web earth cloud database harddisk folder file-document image camera music headphones movie youtube play television " +
  "gamepad-variant steam controller book school briefcase email calendar clock chart-line monitor-dashboard desktop-classic laptop cellphone tablet printer " +
  "shield-lock lock key account-circle cog tune wrench hammer palette brush cart shopping credit-card bank wallet cash heart star bookmark link-variant " +
  "github git code-tags console terminal docker memory chip lightning-bolt fire water weather-sunny moon-waning-crescent food coffee car airplane map-marker " +
  "newspaper rss message chat phone video podcast radio headset download upload sync backup-restore archive trash-can magnify information help alert " +
  "check-circle popcorn robot bug flask lightbulb leaf paw dumbbell run bike stethoscope hospital-box scale-balance gavel briefcase-search account-search " +
  "file-search domain office-building school-outline notebook pencil format-list-bulleted view-dashboard view-grid cube-outline puzzle application").split(" ");

function iconInfo(name) {
  name = (name || "").trim();
  if (!name) return null;
  if (/^https?:\/\//i.test(name)) return { url: name, cls: "" };
  let m = name.match(/^mdi-([a-z0-9-]+?)(?:-?#[0-9a-fA-F]{3,8})?$/);
  if (m) return { url: "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/" + m[1] + ".svg", cls: "mdi" };
  m = name.match(/^si-([a-z0-9-]+?)(?:-?#[0-9a-fA-F]{3,8})?$/);
  if (m) return { url: "https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/" + m[1] + ".svg", cls: "mdi" };
  m = name.match(/^([A-Za-z0-9._-]+)\.(svg|png)$/);
  if (m) return { url: "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/" + m[2] + "/" + m[1] + "." + m[2], cls: "" };
  return null;
}
function iconEl(name) {
  const i = iconInfo(name);
  const box = h("span", { class: "ico" });
  if (i) box.append(h("img", { src: i.url, class: i.cls, alt: "", loading: "lazy", referrerpolicy: "no-referrer", onerror: ev => ev.target.remove() }));
  return box;
}
function siteIcon(href) {
  try { return "https://www.google.com/s2/favicons?domain=" + new URL(href).hostname + "&sz=128"; } catch (e) { return ""; }
}
function pickIcon(current) {
  return new Promise(resolve => {
    const grid = h("div", { class: "picker" });
    const q = h("input", { type: "text", placeholder: "Search, for example: music, server, school", "aria-label": "Search icons" });
    const draw = () => {
      const t = q.value.trim().toLowerCase();
      put(grid, MDI.filter(n => !t || n.includes(t)).map(n =>
        h("button", { title: "mdi-" + n, onclick: () => { d.close(); resolve("mdi-" + n); } }, h("img", { src: iconInfo("mdi-" + n).url, alt: "", loading: "lazy" }), n)));
      if (!grid.children.length) grid.append(h("p", { class: "muted" }, "No icon with that word in this short list. You can type any icon name in the box instead."));
    };
    q.addEventListener("input", draw);
    const d = h("dialog", {}, h("h2", {}, "Choose an icon"), q, grid,
      h("p", { class: "muted small" }, "These are a few of the thousands of icons Homepage knows. You can also type a name such as ", h("b", {}, "plex.svg"), " or ", h("b", {}, "si-github"), " in the icon box."),
      h("div", { class: "actions" }, h("button", { onclick: () => { d.close(); resolve(current); } }, "Cancel")));
    d.addEventListener("close", () => { d.remove(); resolve(current); });
    document.body.append(d);
    draw();
    d.showModal();
    q.focus();
  });
}
function iconField(initial, getHref) {
  const inp = h("input", { type: "text", value: initial || "", placeholder: "mdi-home, plex.svg or a picture address", "aria-label": "Icon" });
  const prev = h("span", {});
  const redraw = () => put(prev, iconEl(inp.value));
  inp.addEventListener("input", redraw);
  redraw();
  const row = h("div", { class: "row tight" }, prev, h("div", { class: "grow" }, inp),
    h("button", { class: "small", type: "button", onclick: async () => { inp.value = await pickIcon(inp.value); redraw(); } }, "Choose…"),
    getHref ? h("button", { class: "small", type: "button", title: "Use the picture the website itself uses", onclick: () => {
      const u = siteIcon(getHref());
      if (!u) return toast("Type the address first.", true);
      inp.value = u; redraw();
    } }, "Use the site's icon") : null);
  return { input: inp, el: h("div", { class: "field" }, h("label", {}, "Icon"), row, h("div", { class: "hint" }, "Optional. Leave it empty for no icon.")) };
}

// ---------------------------------------------------------------- the login
function showLogin(passwordSet = true, msg = "") {
  const err = h("div", { class: "err", role: "alert" }, msg);
  const pw = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Password", placeholder: "Panel password" });
  const go = async () => {
    err.textContent = "";
    try { await api("POST", "/api/login", { password: pw.value }); await start(); }
    catch (e) { err.textContent = e.message; pw.select(); }
  };
  pw.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  put(root, h("div", { class: "login card" },
    h("h1", {}, "Customize your dashboard"),
    h("p", { class: "muted" }, "Type the control panel password. It is its own password (not the one for your other apps)."),
    passwordSet ? [pw, err, h("button", { class: "primary", onclick: go }, "Log in")] :
      h("p", {}, "No password is set yet. On the server, open a terminal and run: ", h("b", {}, "homelab panel password")),
    framed ? h("p", { class: "muted small" }, "If the login does not stay, your browser may block it inside the dashboard. ", h("a", { href: location.href, target: "_blank", rel: "noopener" }, "Open the panel in its own tab"), ".") : null));
  if (passwordSet) pw.focus();
}

// ---------------------------------------------------------------- the frame of the page
function render() {
  if (!S) return;
  try { sessionStorage.setItem("hlp-view", view); } catch (e) { /* storage may be blocked */ }
  const fns = { look: viewLook, background: viewBackground, layout: viewLayout, cards: viewCards, links: viewLinks };
  const auto = h("input", { type: "checkbox", checked: autoReload(), id: "auto", onchange: ev => { try { localStorage.setItem("hlp-auto", ev.target.checked ? "1" : "0"); } catch (e) { /* ignore */ } } });
  put(root,
    h("header", { class: "top" },
      h("div", { class: "grow" }, h("h1", {}, "Customize your dashboard"), h("div", { class: "sub" }, "Changes are saved to your dashboard files. Undo brings the last change back.")),
      h("button", { disabled: !S.undo, onclick: doUndo, title: S.undo ? "Undo: " + S.undo : "Nothing to undo" }, "↶ Undo" + (S.undo ? " (" + S.undo + ")" : "")),
      framed ? h("a", { class: "btn", href: location.href, target: "_blank", rel: "noopener" }, "Open in its own tab") : null,
      h("button", { class: "ghost", onclick: async () => { try { await api("POST", "/api/logout", {}); } catch (e) { /* already out */ } S = null; showLogin(); } }, "Log out")),
    h("nav", { class: "tabs", role: "tablist" }, VIEWS.map(([id, label]) =>
      h("button", { role: "tab", "aria-selected": String(view === id), onclick: () => { if (view !== id) { discardPreview(); view = id; render(); window.scrollTo(0, 0); } } }, label))),
    fns[view](),
    framed ? h("p", { class: "muted small" }, h("label", { for: "auto" }, auto, " Refresh the dashboard by itself after I change layout, cards or links")) : null);
  applyAccent();
}
function applyAccent() {
  const v = lookW || S.look.values;
  const [r, g, b] = rgb(v.accent);
  document.documentElement.style.setProperty("--accent", r + ", " + g + ", " + b);
}
async function doUndo() {
  try { const r = await api("POST", "/api/undo", {}); send({ type: "clear" }); toast("Undone: " + r.undone); await afterChange(true); } catch (e) { fail(e); }
}
function discardPreview() { send({ type: "clear" }); lookW = bgW = layW = null; }

function saveBar(dirty, onSave, onRevert, saveLabel, extra) {
  return h("div", { class: "savebar" },
    h("div", { class: "state" + (dirty ? " dirty" : "") }, dirty ? "You have changes that are not saved yet." : "Everything shown is saved."),
    extra || null,
    h("button", { disabled: !dirty, onclick: onRevert }, "Throw away"),
    h("button", { class: "primary", disabled: !dirty, onclick: onSave }, saveLabel || "Save"));
}

// ---------------------------------------------------------------- Look
function rgb(hex) { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ""); const n = m ? parseInt(m[1], 16) : 0; return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function lookCss(v) {
  const a = rgb(v.accent).join(", ");
  let css = "html body #inner_wrapper{--lk-accent:" + a + ";--lk-glass:" + rgb(v.glass).join(", ") + ";--lk-glass-a:" + (v.glassOpacity / 100) +
    ";--lk-radius:" + v.radius + "px;--lk-line:rgba(255,255,255," + (v.edge / 100) + ");--lk-side:" + v.side + "px;--lk-player-h:" + v.playerHeight + "px}";
  for (const [name, col] of Object.entries(v.tabs || {})) if (/^[A-Za-z0-9 _&-]+$/.test(name)) css += 'html[data-tab="' + name + '"] body #inner_wrapper{--lk-accent:' + rgb(col).join(", ") + "}";
  css += "@media (max-width:700px){html body #inner_wrapper{--lk-player-h:" + Math.max(240, v.playerHeight - 40) + "px}}";
  return css;
}
function lookPreview(quiet) {
  if (!quiet) send({ type: "css", css: lookCss(lookW) });
  const p = document.getElementById("mock");
  if (p) {
    p.style.setProperty("--pc", rgb(lookW.accent).join(", "));
    p.style.setProperty("--pg", rgb(lookW.glass).join(", "));
    p.style.setProperty("--pa", lookW.glassOpacity / 100);
    p.style.setProperty("--pr", Math.min(lookW.radius, 30) + "px");
    p.style.setProperty("--pe", lookW.edge / 100);
  }
  applyAccent();
}
function lookDirty() { return !same(lookNorm(lookW), lookNorm(S.look.values)); }
function lookNorm(v) { const o = clone(v); o.tabs = o.tabs || {}; return o; }

function viewLook() {
  const sv = S.look.values, def = S.look.defaults;
  if (!lookW) lookW = clone(sv);
  const L = lookW;
  const upd = (k, val) => { L[k] = val; lookPreview(); refreshBar(); };
  const bar = h("div", {});
  const refreshBar = () => put(bar, saveBar(lookDirty(), saveLook, () => { discardPreview(); render(); }, "Save this look",
    h("button", { onclick: resetLook }, "Back to the shipped look")));
  async function saveLook() {
    const out = clone(L);
    out.tabs = {};
    for (const [n, c] of Object.entries(L.tabs)) if (c !== def.tabs[n]) out.tabs[n] = c;
    try { await api("POST", "/api/look", { look: out }); toast("Look saved."); await afterChange(false); } catch (e) { fail(e); }
  }
  async function resetLook() {
    if (!await confirmBox("Back to the shipped look?", "The colours, glass and shapes go back to how the dashboard came. Your cards and layout stay as they are. Undo can bring this change back.", "Reset the look")) return;
    try { await api("POST", "/api/look/reset", {}); send({ type: "clear" }); toast("The shipped look is back."); await afterChange(true); } catch (e) { fail(e); }
  }
  function slider(label, key, lo, hi, step, unit, hint) {
    const val = h("span", { class: "val" }, L[key] + unit);
    const inp = h("input", { type: "range", min: lo, max: hi, step, value: L[key], "aria-label": label, oninput: ev => { val.textContent = ev.target.value + unit; upd(key, Number(ev.target.value)); } });
    return h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, label), val, inp), hint ? h("div", { class: "hint" }, hint) : null);
  }
  function colorField(label, key, hint, swatches) {
    const hex = h("input", { type: "text", value: L[key], maxlength: 7, "aria-label": label + " (hex code)", style: { maxWidth: "120px" } });
    const pick = h("input", { type: "color", value: L[key], "aria-label": label });
    const set = v => { L[key] = v; hex.value = v; pick.value = v; lookPreview(); refreshBar(); };
    pick.addEventListener("input", () => set(pick.value));
    hex.addEventListener("change", () => { if (/^#[0-9a-f]{6}$/i.test(hex.value.trim())) set(hex.value.trim().toLowerCase()); else hex.value = L[key]; });
    return h("div", { class: "field" }, h("div", { class: "lab" }, label),
      h("div", { class: "row" }, pick, hex, h("div", { class: "swatches" }, (swatches || []).map(c => h("button", { class: "swatch", style: { background: c }, title: c, "aria-label": "Use " + c, onclick: () => set(c) })))),
      hint ? h("div", { class: "hint" }, hint) : null);
  }
  const tabRows = S.look.tabNames.map(name => {
    const cur = () => L.tabs[name] || L.accent;
    const pick = h("input", { type: "color", value: cur(), "aria-label": "Colour of the tab " + name });
    pick.addEventListener("input", () => { L.tabs[name] = pick.value; lookPreview(); refreshBar(); });
    return h("div", { class: "row", style: { marginBottom: "6px" } }, pick, h("span", { class: "grow" }, name),
      h("button", { class: "small", onclick: () => { L.tabs[name] = L.accent; pick.value = L.accent; lookPreview(); refreshBar(); } }, "Same as main colour"));
  });
  const mock = h("div", { class: "preview", id: "mock" },
    h("div", { class: "mini-tabs" }, h("span", { class: "on" }, "Home"), h("span", {}, "Stats"), h("span", {}, "Links")),
    h("div", { class: "mini-cards" }, ["Navidrome", "Immich", "Beszel"].map(n => h("div", { class: "mini-card" }, h("b", {}, n), h("span", { class: "small muted" }, "Sample card"), h("i", {})))));
  setTimeout(() => { lookPreview(!lookDirty()); refreshBar(); }, 0);       // nothing is sent to the dashboard until something is changed
  return h("div", {},
    h("div", { class: "card" }, h("h2", {}, "Ready-made looks"), h("p", { class: "muted" }, "Pick one to try it. Nothing is saved until you press “Save this look”."),
      h("div", { class: "chips" }, S.look.presets.map(p => h("button", { class: "chip", onclick: () => {
        const base = clone(def); base.tabs = Object.assign({}, def.tabs);
        const pl = clone(p.look); const tabs = Object.assign({}, base.tabs, pl.tabs || {}); delete pl.tabs;
        lookW = Object.assign(base, pl, { tabs });
        render();
      } }, h("span", { class: "dot", style: { background: p.look.accent || def.accent } }), p.name)))),
    h("div", { class: "grid cols2" },
      h("div", { class: "card" }, h("h2", {}, "Colours"),
        colorField("Main colour", "accent", "The colour of the active tab, bars, icons and the edge of a card you point at.", ["#8ab4ff", "#5ec8ff", "#7ee0a0", "#ffa66b", "#ff8fb5", "#c9a0ff", "#ffd36b", "#c3cad6"]),
        colorField("Glass colour", "glass", "The tint of every card and tile.", ["#0d121e", "#06141f", "#07150d", "#1c0f12", "#1a0c16", "#111214"]),
        h("div", { class: "field" }, h("div", { class: "lab" }, "Colour of each tab"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "Each tab can have its own accent colour."), tabRows)),
      h("div", { class: "card" }, h("h2", {}, "Shapes and space"),
        slider("How solid the glass is", "glassOpacity", 0, 100, 1, "%", "Low shows the picture through the cards. High makes them solid."),
        slider("How round the corners are", "radius", 0, 40, 1, " px"),
        slider("Brightness of the card edge", "edge", 0, 40, 0.5, "%"),
        slider("Space at the left and right", "side", 0, 120, 2, " px"),
        slider("Height of the music player", "playerHeight", 240, 1000, 10, " px", "The player is on the Home tab.")),
    ),
    h("div", { class: "card" }, h("h2", {}, "Preview"), h("p", { class: "muted" }, framed ? "The dashboard around this panel changes while you move things, so you can see the real result." : "A small sample of how cards and tabs look."), mock),
    bar);
}

// ---------------------------------------------------------------- Background
function bgUrl(img) { return !img ? "" : (img.startsWith("/") && S.background.homepageUrl ? S.background.homepageUrl + img : (img.startsWith("/") ? "" : img)); }
function viewBackground() {
  const b = S.background;
  if (!bgW) bgW = { url: "", blur: b.blur || "none", saturate: b.saturate, brightness: b.brightness, opacity: b.opacity };
  const B = bgW;
  const pic = h("div", { class: "pic" });
  const drawPic = () => { const u = bgUrl(b.image); pic.style.backgroundImage = u ? 'url("' + u.replace(/"/g, "%22") + '")' : "none"; };
  drawPic();
  const bar = h("div", {});
  const dirty = () => B.url !== "" || B.blur !== (b.blur || "none") || B.saturate !== b.saturate || B.brightness !== b.brightness || B.opacity !== b.opacity;
  const refreshBar = () => put(bar, saveBar(dirty(), save, () => { discardPreview(); render(); }, "Save", h("button", { onclick: reset }, "Back to the shipped sliders")));
  const preview = () => { send({ type: "bg", image: B.url || b.image, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); refreshBar(); };
  async function save() {
    try { await api("POST", "/api/background", { url: B.url || undefined, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); toast("Background saved."); await afterChange(false); }
    catch (e) { fail(e); }
  }
  async function reset() {
    try { await api("POST", "/api/background/reset", {}); send({ type: "clear" }); toast("The sliders are back to the shipped values."); await afterChange(true); } catch (e) { fail(e); }
  }
  function slider(label, key, hint) {
    const val = h("span", { class: "val" }, B[key] + "%");
    return h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, label), val,
      h("input", { type: "range", min: 0, max: 100, step: 1, value: B[key], "aria-label": label, oninput: ev => { B[key] = Number(ev.target.value); val.textContent = B[key] + "%"; preview(); } })),
      h("div", { class: "hint" }, hint));
  }
  const blurVal = h("span", { class: "val" }, B.blur);
  const url = h("input", { type: "url", placeholder: "https://…", "aria-label": "Picture address" });
  const file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/gif,image/avif", hidden: true, onchange: upload });
  async function upload() {
    const f = file.files[0];
    if (!f) return;
    if (f.size > 14 * 1024 * 1024) return toast("That picture is bigger than 14 MB. Choose a smaller one.", true);
    toast("Sending the picture…");
    try {
      const r = await api("POST", "/api/background/upload", undefined, f);
      toast(r.restarting ? "Picture saved. The dashboard restarts for about 10 seconds…" : "Picture saved.");
      await afterChange(false);
      if (r.restarting) setTimeout(() => send({ type: "reload" }), 12000);
    } catch (e) { fail(e); }
  }
  setTimeout(refreshBar, 0);
  return h("div", {},
    h("div", { class: "grid cols2" },
      h("div", { class: "card" }, h("h2", {}, "The picture"), pic,
        h("div", { class: "row", style: { marginTop: "12px" } }, file, h("button", { class: "primary", onclick: () => file.click() }, "Upload a picture…")),
        h("p", { class: "hint muted small" }, "JPG, PNG, WebP, GIF or AVIF, up to 14 MB. After a new picture the dashboard restarts for about 10 seconds."),
        b.mounted === false ? h("p", { class: "small", style: { color: "var(--bad)" } }, "The dashboard cannot see its pictures folder yet, so an uploaded picture will not show. Run: sudo homelab-setup upgrade") : null,
        h("div", { class: "field", style: { marginTop: "12px" } }, h("label", {}, "Or use a picture from the web"), h("div", { class: "row" }, h("div", { class: "grow" }, url),
          h("button", { onclick: () => { B.url = url.value.trim(); if (!B.url) return toast("Type a web address first.", true); preview(); toast("Press Save to keep it."); } }, "Use this address")))),
      h("div", { class: "card" }, h("h2", {}, "How it looks behind the cards"),
        h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, "Blur"), blurVal,
          h("input", { type: "range", min: 0, max: 6, step: 1, value: BLURS.indexOf(B.blur) < 0 ? 2 : BLURS.indexOf(B.blur), "aria-label": "Blur",
            oninput: ev => { B.blur = BLURS[Number(ev.target.value)]; blurVal.textContent = B.blur; preview(); } })), h("div", { class: "hint" }, "none is sharp. 3xl is very soft.")),
        slider("Brightness", "brightness", "Low makes the picture darker, so the text is easy to read."),
        slider("Colour", "saturate", "Low turns the picture towards grey."),
        slider("Strength", "opacity", "How much of the picture shows through the dark cover."))),
    bar);
}

// ---------------------------------------------------------------- Layout
function viewLayout() {
  if (!layW) layW = clone(S.layout.tabs);
  const T = layW;
  const dirty = () => !same(T, S.layout.tabs);
  const bar = h("div", {});
  const refreshBar = () => put(bar, saveBar(dirty(), save, () => { layW = null; render(); }, "Save the layout"));
  async function save() {
    try { await api("POST", "/api/layout", { tabs: T.filter(t => t.groups.length) }); toast("Layout saved."); await afterChange(true); } catch (e) { fail(e); }
  }
  const tabNames = () => T.map(t => t.name);
  function moveTo(gi, ti, name) {
    const g = T[ti].groups.splice(gi, 1)[0];
    let dest = T.find(t => t.name === name);
    if (!dest) { dest = { name, groups: [] }; T.push(dest); }
    dest.groups.push(g);
    redraw();
  }
  function redraw() { const y = window.scrollY; put(board, T.map(tabCol)); window.scrollTo(0, y); refreshBar(); }
  let dragging = null;
  function drop(ti, at) {
    if (!dragging) return;
    const [fti, fgi] = dragging;
    const g = T[fti].groups.splice(fgi, 1)[0];
    let idx = at;
    if (fti === ti && fgi < at) idx -= 1;
    T[ti].groups.splice(Math.max(0, idx), 0, g);
    dragging = null;
    redraw();
  }
  function groupRow(g, ti, gi) {
    const row = h("div", { class: "grp", draggable: "true",
      ondragstart: ev => { dragging = [ti, gi]; ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", g.name); row.classList.add("drag"); },
      ondragend: () => row.classList.remove("drag"),
      ondragover: ev => { ev.preventDefault(); row.classList.add("over"); },
      ondragleave: () => row.classList.remove("over"),
      ondrop: ev => { ev.preventDefault(); row.classList.remove("over"); drop(ti, gi); } });
    const move = (d) => { const arr = T[ti].groups; const j = gi + d; if (j < 0 || j >= arr.length) return; [arr[gi], arr[j]] = [arr[j], arr[gi]]; redraw(); };
    const sel = h("select", { "aria-label": "Move " + g.name + " to a tab", onchange: async ev => {
      let v = ev.target.value;
      if (v === "__new") { v = (await askText("New tab", "Name of the new tab", "")) || ""; if (!v) return redraw(); if (tabNames().includes(v)) return moveTo(gi, ti, v); }
      if (v && v !== T[ti].name) moveTo(gi, ti, v);
    } }, tabNames().map(n => h("option", { value: n, selected: n === T[ti].name }, "Tab: " + n)), h("option", { value: "__new" }, "New tab…"));
    const icon = h("input", { class: "icon-in", type: "text", value: g.icon || "", placeholder: "icon", "aria-label": "Icon of " + g.name, onchange: ev => { g.icon = ev.target.value.trim(); redraw(); } });
    const style = h("select", { "aria-label": "Shape of " + g.name, onchange: ev => { g.style = ev.target.value; redraw(); } },
      h("option", { value: "", selected: !g.style }, "Cards in a list"), h("option", { value: "row", selected: g.style === "row" }, "Cards in a row"));
    const cols = h("input", { class: "cols-in", type: "number", min: 1, max: 8, value: g.columns || "", placeholder: "cols", "aria-label": "Columns of " + g.name, onchange: ev => { g.columns = ev.target.value; redraw(); } });
    add(row, h("span", { class: "handle", title: "Drag to move", "aria-hidden": "true" }, "⠿"), iconEl(g.icon), h("span", { class: "name" }, g.name),
      g.automatic ? h("span", { class: "badge", title: "The lab fills this group by itself" }, "automatic") : null,
      h("button", { class: "small icon", "aria-label": "Move " + g.name + " up", disabled: gi === 0, onclick: () => move(-1) }, "↑"),
      h("button", { class: "small icon", "aria-label": "Move " + g.name + " down", disabled: gi === T[ti].groups.length - 1, onclick: () => move(1) }, "↓"),
      sel, icon, style, cols);
    return row;
  }
  function tabCol(t, ti) {
    const col = h("div", { class: "tabcol", ondragover: ev => ev.preventDefault(), ondrop: ev => { if (ev.target === col || !ev.target.closest(".grp")) { ev.preventDefault(); drop(ti, t.groups.length); } } });
    const mvT = d => { const j = ti + d; if (j < 0 || j >= T.length) return; [T[ti], T[j]] = [T[j], T[ti]]; redraw(); };
    add(col, h("header", {}, h("h3", {}, t.name),
      h("button", { class: "small icon", "aria-label": "Move the tab left", disabled: ti === 0, onclick: () => mvT(-1) }, "←"),
      h("button", { class: "small icon", "aria-label": "Move the tab right", disabled: ti === T.length - 1, onclick: () => mvT(1) }, "→"),
      h("button", { class: "small", onclick: async () => {
        const n = (await askText("Rename the tab", "New name for the tab “" + t.name + "”", t.name)) || "";
        if (!n || n === t.name) return;
        if (T.some(x => x.name === n)) return toast("There is already a tab with that name.", true);
        t.name = n; redraw();
      } }, "Rename")), t.groups.map((g, gi) => groupRow(g, ti, gi)),
    t.groups.length ? null : h("p", { class: "muted small" }, "Empty. A tab with no group is not kept."));
    return col;
  }
  const board = h("div", { class: "grid" }, T.map(tabCol));
  setTimeout(refreshBar, 0);
  return h("div", {},
    h("div", { class: "card" }, h("h2", {}, "Tabs and groups"),
      h("p", { class: "muted" }, "Each box is a tab of the dashboard. Drag a group (or use the arrows) to change the order, pick another tab to move it there, and choose how its cards are laid out. “Cards in a row” puts the cards side by side."),
      h("div", { class: "row", style: { marginBottom: "12px" } }, h("button", { onclick: async () => {
        const n = (await askText("Add a tab", "Name of the new tab", "")) || "";
        if (!n) return;
        if (T.some(x => x.name === n)) return toast("There is already a tab with that name.", true);
        T.push({ name: n, groups: [] }); redraw();
      } }, "+ Add a tab"), h("span", { class: "muted small" }, "Then move a group into it.")),
      board),
    bar);
}

// ---------------------------------------------------------------- Cards and links (one editor for both)
function groupNames(list, withNew) { return list.map(g => g.group); }
function viewCards() { return viewItems("cards"); }
function viewLinks() { return viewItems("links"); }

function viewItems(kind) {
  const isCards = kind === "cards";
  const groups = (isCards ? S.services.filter(g => !g.locked) : S.links);
  const locked = isCards ? S.services.filter(g => g.locked && !S.protected.includes(g.group)) : [];
  const path = isCards ? "/api/card" : "/api/link";
  const items = g => isCards ? g.cards : g.links;
  const tabsList = S.layout.tabs.map(t => t.name);
  const word = isCards ? "card" : "link";

  async function op(body, okMsg) { try { await api("POST", path, body); toast(okMsg); await afterChange(true); } catch (e) { fail(e); } }
  async function reorder(g, i, d) {
    const arr = items(g);
    const it = arr[i];
    const before = d < 0 ? arr[i - 1] : arr[i + 2];
    await op({ op: "move", group: g.group, name: it.name, to: g.group, before: before ? before.name : undefined }, "Order saved.");
  }
  async function remove(g, it) {
    if (!await confirmBox("Remove “" + it.name + "”?", "It disappears from the dashboard. Undo can bring it back.", "Remove it", true)) return;
    await op({ op: "remove", group: g.group, name: it.name }, "Removed.");
  }

  function editor(g, it) {
    const adding = !it;
    const v = it || { name: "", href: "", icon: "", description: "", abbr: "", siteMonitor: "" };
    const managed = isCards && it && it.managed;
    const name = h("input", { type: "text", value: v.name, maxlength: 60, "aria-label": "Name" });
    const href = h("input", { type: "url", value: v.href, placeholder: "https://…", disabled: managed, "aria-label": "Address" });
    const desc = h("input", { type: "text", value: v.description || "", maxlength: isCards ? 160 : 120, "aria-label": "Description" });
    const abbr = h("input", { type: "text", value: v.abbr || "", maxlength: 6, placeholder: "automatic", "aria-label": "Short label" });
    const dot = h("input", { type: "checkbox", id: "dot", checked: !!v.siteMonitor });
    const ic = iconField(v.icon, () => href.value);
    const names = groups.map(x => x.group);
    const gsel = h("select", { "aria-label": "Group" }, names.map(n => h("option", { value: n, selected: g && n === g.group }, n)), h("option", { value: "__new" }, "A new group…"));
    const gnew = h("input", { type: "text", placeholder: "Name of the new group", maxlength: 40, hidden: true, "aria-label": "New group name" });
    const tsel = h("select", { "aria-label": "Tab for the new group", hidden: true }, tabsList.map(n => h("option", { value: n, selected: n === (isCards ? "Home" : "Links") }, "On the tab: " + n)));
    gsel.addEventListener("change", () => { const nw = gsel.value === "__new"; gnew.hidden = !nw; tsel.hidden = !nw; if (nw) gnew.focus(); });
    if (!names.length) { gsel.value = "__new"; gnew.hidden = false; tsel.hidden = false; }
    const err = h("div", { class: "err", role: "alert", style: { color: "var(--bad)", minHeight: "20px" } });
    const d = h("dialog", {}, h("h2", {}, adding ? "Add a " + word : "Change “" + v.name + "”"),
      h("div", { class: "field" }, h("label", {}, "Name"), name),
      h("div", { class: "field" }, h("label", {}, "Web address"), href, managed ? h("div", { class: "hint" }, "The lab keeps this address right (the Tailscale name and ports), so it cannot be changed here.") : null),
      ic.el,
      h("div", { class: "field" }, h("label", {}, "Short text"), desc, h("div", { class: "hint" }, isCards ? "Shown under the name." : "Optional.")),
      isCards ? (managed ? null : h("div", { class: "field" }, h("label", { for: "dot", class: "row" }, dot, "Show a green/red dot to tell if it is up"))) : h("div", { class: "field" }, h("label", {}, "Short label"), abbr, h("div", { class: "hint" }, "Up to 6 letters, shown when there is no icon.")),
      h("div", { class: "field" }, h("label", {}, adding ? "Put it in" : "Group"), gsel, gnew, tsel),
      err,
      h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Cancel"), h("button", { class: "primary", onclick: async () => {
        err.textContent = "";
        const target = gsel.value === "__new" ? gnew.value.trim() : gsel.value;
        const body = { name: name.value.trim(), href: href.value.trim(), icon: ic.input.value.trim(), description: desc.value.trim(), dot: dot.checked, abbr: abbr.value.trim() };
        try {
          if (adding) { await api("POST", path, Object.assign(body, { op: "add", group: target, tab: tsel.value })); }
          else {
            await api("POST", path, Object.assign(body, { op: "edit", group: g.group, old: v.name }));
            if (target !== g.group) await api("POST", path, { op: "move", group: g.group, name: body.name, to: target, tab: tsel.value });
          }
          d.close(); toast(adding ? "Added." : "Saved."); await afterChange(true);
        } catch (e) { err.textContent = e.message; }
      } }, adding ? "Add" : "Save")));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    name.focus();
  }

  async function groupMenu(g) {
    const n = (await askText("Rename the group", "New name for the group “" + g.group + "”", g.group)) || "";
    if (!n || n === g.group) return;
    try {
      await api("POST", isCards ? "/api/group" : "/api/link", isCards ? { op: "rename", group: g.group, to: n } : { op: "group-rename", group: g.group, to: n });
      toast("Renamed."); await afterChange(true);
    } catch (e) { fail(e); }
  }
  async function groupRemove(g) {
    if (!await confirmBox("Remove the whole group “" + g.group + "”?", "This removes the group and its " + items(g).length + " " + word + (items(g).length === 1 ? "" : "s") + ". Undo can bring them back.", "Remove the group", true)) return;
    try {
      await api("POST", isCards ? "/api/group" : "/api/link", isCards ? { op: "remove", group: g.group } : { op: "group-remove", group: g.group });
      toast("Removed."); await afterChange(true);
    } catch (e) { fail(e); }
  }

  const cards = groups.map(g => h("div", { class: "card group-card" },
    h("header", {}, h("h2", {}, g.group), h("span", { class: "badge" }, items(g).length + (items(g).length === 1 ? " " + word : " " + word + "s")),
      h("button", { class: "small", onclick: () => groupMenu(g) }, "Rename"), h("button", { class: "small danger", onclick: () => groupRemove(g) }, "Remove group")),
    items(g).map((it, i) => h("div", { class: "item" }, iconEl(it.icon),
      h("div", { class: "txt" }, h("b", {}, it.name), h("span", {}, [it.description, it.href].filter(Boolean).join("  ·  ") || "No address")),
      isCards && it.managed ? h("span", { class: "badge", title: "Made by the lab; it keeps the address right" }, "lab card") : null,
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " up", disabled: i === 0, onclick: () => reorder(g, i, -1) }, "↑"),
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " down", disabled: i === items(g).length - 1, onclick: () => reorder(g, i, 1) }, "↓"),
      h("button", { class: "small", onclick: () => editor(g, it) }, "Change"),
      h("button", { class: "small danger", onclick: () => remove(g, it) }, "Remove"))),
    h("div", { style: { marginTop: "10px" } }, h("button", { class: "small", onclick: () => editor(g, null) }, "+ Add a " + word + " here"))));

  return h("div", {},
    h("div", { class: "card" }, h("h2", {}, isCards ? "Cards on the dashboard" : "Links (bookmarks)"),
      h("p", { class: "muted" }, isCards ? "The cards of Home. Add your own cards for any web page, change a name or text, put them in another order or group, or remove them."
        : "The bookmarks of the Links tab, in groups. Add your own sites with their icons."),
      h("button", { class: "primary", onclick: () => editor(groups[0] || null, null) }, "+ Add a " + word)),
    cards.length ? cards : h("p", { class: "muted" }, "There is nothing here yet."),
    locked.length ? h("details", { class: "card" }, h("summary", {}, "Kept up to date by the lab (" + locked.map(g => g.group).join(", ") + ")"),
      h("p", { class: "muted small" }, "These groups are filled in by the lab itself (numbers, calendar). You can move them to another tab on the Layout screen, but not change their cards.")) : null);
}

// ---------------------------------------------------------------- start
async function start() {
  let s;
  try { s = await api("GET", "/api/session"); } catch (e) { root.replaceChildren(h("p", { class: "loading" }, e.message)); return; }
  if (!s.loggedIn) return showLogin(s.passwordSet);
  try { S = await api("GET", "/api/state"); } catch (e) { return; }
  render();
}
start();
