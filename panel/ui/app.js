"use strict";
/* The control panel page. Plain JavaScript, no libraries. Everything that comes from the dashboard's files is put on the page as text (never as HTML). */

const framed = window.parent !== window;
// Screen fit (the same as in the dashboard's custom.js): the panel in its own tab is shown at 90% on a 1080p screen and 110% on a 1440p screen. In the dashboard's frame the zoom is inherited.
(function () {
  if (framed) return;
  const BANDS = [[1850, 2000, 0.9], [2450, 2650, 1.1]], root = document.documentElement;
  let timer = 0;
  const fit = () => {
    const phys = Math.round(window.innerWidth * window.devicePixelRatio), band = BANDS.find(b => phys >= b[0] && phys <= b[1]), z = band ? band[2] : 1;
    if (z === 1) { root.style.removeProperty("zoom"); root.style.removeProperty("--vh"); return; }
    root.style.zoom = String(z);
    root.style.setProperty("--vh", (1 / z).toFixed(4) + "vh");
  };
  fit();
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(fit, 150); });
})();
let S = null;                 // what the server says (look, background, layout, cards, links)
let view = "look";
let lookW = null, bgW = null, layW = null;     // the changes in progress (not saved yet)
const root = document.getElementById("app");
const LOOKVIEWS = ["look"];                           // (the screens that work on the look and the background: the changes are kept while you are on them)
const BLURS = ["none", "sm", "md", "lg", "xl", "2xl", "3xl"];
const BLUR_NAMES = { none: "None", sm: "Small", md: "Medium", lg: "Large", xl: "Extra Large", "2xl": "Huge", "3xl": "Very Huge" };
const ONLY = new URLSearchParams(location.search).get("only");       // "links": only the link editor, shown inside the Links tab of the dashboard
const VIEWS = ONLY === "links" ? [["links", "Links"]]
  : [["look", "Look"], ["layout", "Layout"], ["cards", "Cards"], ["drives", "Drives"], ["updates", "Updates"]];
if (ONLY === "links") view = "links";

try { const v = sessionStorage.getItem("hlp-view"); if (v && VIEWS.some(x => x[0] === v)) view = v; } catch (e) { /* storage may be blocked */ }
if (ONLY !== "links" && ["updates", "drives"].includes(location.hash.slice(1))) view = location.hash.slice(1);       // the bell on the dashboard opens these screens

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
  if (!r.ok) { const err = new Error(js.error || ("Something went wrong (" + r.status + ").")); err.status = r.status; throw err; }
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
    clearDraft();
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
let iconLib = null;                 // the icon names (loaded once from the server, which keeps a copy for a month)
function loadIcons() {
  if (!iconLib) iconLib = api("GET", "/api/icons").catch(() => ({ apps: [], mdi: [] }));
  return iconLib;
}
const APP_ICON_URL = n => "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/" + n.slice(n.lastIndexOf(".") + 1) + "/" + n;
function pickIcon(current) {
  return new Promise(resolve => {
    let kind = "apps", lib = { apps: [], mdi: [] };
    const grid = h("div", { class: "picker" });
    const note = h("p", { class: "muted small" });
    const q = h("input", { type: "text", placeholder: "Search, for example: portainer, plex, music, server", "aria-label": "Search icons" });
    const tabs = h("div", { class: "chips", style: { margin: "10px 0" } });
    const MAX = 120;
    const choose = v => { d.close(); resolve(v); };
    const draw = () => {
      const t = q.value.trim().toLowerCase();
      const names = kind === "apps" ? (lib.apps.length ? lib.apps : []) : (lib.mdi.length ? lib.mdi : MDI);
      const hits = names.filter(n => !t || n.toLowerCase().includes(t));
      put(grid, hits.slice(0, MAX).map(n => kind === "apps"
        ? h("button", { title: n, onclick: () => choose(n) }, h("img", { src: APP_ICON_URL(n), alt: "", loading: "lazy" }), n.replace(/\.(svg|png)$/, ""))
        : h("button", { title: "mdi-" + n, onclick: () => choose("mdi-" + n) }, h("img", { src: iconInfo("mdi-" + n).url, class: "mdi", alt: "", loading: "lazy" }), n)));
      if (!hits.length) grid.append(h("p", { class: "muted" }, kind === "apps" && !lib.apps.length
        ? "The list of app icons could not be loaded (is the server online?). You can still type an icon name such as plex.svg in the icon box."
        : "Nothing matches that word. Try a shorter word."));
      put(note, hits.length > MAX ? "Showing the first " + MAX + " of " + hits.length + ". Type more letters to narrow it down." : hits.length + " icon" + (hits.length === 1 ? "" : "s"));
    };
    const drawTabs = () => put(tabs, [["apps", "Apps and Logos"], ["mdi", "Symbols"]].map(([id, text]) =>
      h("button", { class: "chip", "aria-pressed": String(kind === id), onclick: () => { kind = id; drawTabs(); draw(); } }, text)));
    q.addEventListener("input", draw);
    const d = h("dialog", { class: "wide" }, h("h2", {}, "Choose an Icon"), q, tabs, grid, note,
      h("p", { class: "muted small" }, "Apps and Logos has the icons of thousands of programs (Portainer, Plex, Nextcloud…). Symbols are plain pictures such as a house or a folder. You can also type a name in the icon box, or a web address of a picture."),
      h("div", { class: "actions" }, h("button", { onclick: () => { d.close(); resolve(current); } }, "Cancel")));
    d.addEventListener("close", () => { d.remove(); resolve(current); });
    document.body.append(d);
    drawTabs();
    put(grid, h("p", { class: "muted" }, "Loading the icon library…"));
    d.showModal();
    q.focus();
    loadIcons().then(l => { lib = l; if (!lib.apps.length && lib.mdi.length) kind = "mdi"; drawTabs(); draw(); });
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
    } }, "Use the Site's Icon") : null);
  const swatch = h("input", { type: "color", value: ((inp.value.match(/#[0-9a-fA-F]{6}$/) || ["#ffffff"])[0]), "aria-label": "Icon color", title: "Color of the icon" });
  const colorRow = h("div", { class: "row tight", style: { marginTop: "6px" } }, h("span", { class: "muted small" }, "Icon color"), swatch,
    h("button", { class: "small", type: "button", onclick: () => { inp.value = inp.value.replace(/-?#[0-9a-fA-F]{3,8}$/, ""); redraw(); } }, "No Color"),
    h("span", { class: "muted small" }, "(for the round icon library: names that start with mdi- or si-)"));
  swatch.addEventListener("input", () => {
    const base = inp.value.trim().replace(/-?#[0-9a-fA-F]{3,8}$/, "");
    if (!/^(mdi|si)-/.test(base)) { toast("Colors work with icons that start with mdi- or si-. Choose one of those first.", true); return; }
    inp.value = base + "-" + swatch.value;
    redraw();
  });
  return { input: inp, el: h("div", { class: "field" }, h("label", {}, "Icon"), row, colorRow, h("div", { class: "hint" }, "Optional. Leave it empty for no icon.")) };
}

// ---------------------------------------------------------------- the login
function showLogin(passwordSet = true, msg = "") {
  DR = DRhealth = DRcheck = null;          // (what was shown of the drives is not kept after a log out)
  const err = h("div", { class: "err", role: "alert" }, msg);
  const pw = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Password", placeholder: "Panel password" });
  const go = async () => {
    err.textContent = "";
    try { await api("POST", "/api/login", { password: pw.value }); await start(); }
    catch (e) { err.textContent = e.message; pw.select(); }
  };
  pw.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  put(root, h("div", { class: "login card" },
    h("h1", {}, "Customize Your Dashboard"),
    h("p", { class: "muted" }, "Type the control panel password. It is its own password (not the one for your other apps)."),
    passwordSet ? [pw, err, h("button", { class: "primary", onclick: go }, "Log In")] :
      h("p", {}, "No password is set yet. On the server, open a terminal and run: ", h("b", {}, "homelab panel password")),
    framed ? h("p", { class: "muted small" }, "If the login does not stay, your browser may block it inside the dashboard. ", h("a", { href: location.href, target: "_blank", rel: "noopener" }, "Open the panel in its own tab"), ".") : null));
  if (passwordSet) pw.focus();
}

// ---------------------------------------------------------------- the frame of the page
function render() {
  if (!S) return;
  try { sessionStorage.setItem("hlp-view", view); } catch (e) { /* storage may be blocked */ }
  const fns = { look: viewLook, layout: viewLayout, cards: viewCards, drives: viewDrives, updates: viewUpdates, links: viewLinks };
  if (ONLY === "links") { put(root, viewLinks()); applyAccent(); return; }
  footEl = h("div", { class: "hactions" });      // the buttons live in the top line, next to the title and the tabs
  drawFoot(false, null, null);
  const auto = h("input", { type: "checkbox", checked: autoReload(), id: "auto", onchange: ev => { try { localStorage.setItem("hlp-auto", ev.target.checked ? "1" : "0"); } catch (e) { /* ignore */ } } });
  put(root,
    h("div", { class: "stickytop" },
      h("header", { class: "top" },
        h("h1", {}, "Customize Your Dashboard"),
        h("nav", { class: "tabs", role: "tablist" }, VIEWS.map(([id, label]) =>
          h("button", { role: "tab", "aria-selected": String(view === id), onclick: () => { if (view !== id) { if (!(LOOKVIEWS.includes(view) && LOOKVIEWS.includes(id))) discardPreview(); view = id; render(); window.scrollTo(0, 0); } } }, label))),
        footEl)),
    fns[view](),
    framed ? h("p", { class: "muted small" }, h("label", { for: "auto" }, auto, " Refresh the dashboard by itself after I change layout, cards or links")) : null);
  applyAccent();
}
function colorParts(str) {      // "#0d1422", "#fff", "rgb(1, 2, 3)", "rgba(1, 2, 3, 0.4)" -> [r, g, b, a], or null
  str = String(str || "");
  let m = str.match(/#([0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3})\b/i);
  if (m) {
    let x = m[1];
    if (x.length === 3) x = x.split("").map(c => c + c).join("");
    return [parseInt(x.slice(0, 2), 16), parseInt(x.slice(2, 4), 16), parseInt(x.slice(4, 6), 16), x.length === 8 ? parseInt(x.slice(6, 8), 16) / 255 : 1];
  }
  m = str.match(/rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)/i);
  if (m) {
    let a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return [+m[1], +m[2], +m[3], isNaN(a) ? 1 : a];
  }
  return null;
}
function optionColors(ui) {      // a solid background for the options of a drop down (a theme's colours are often see-through) and a text colour that reads on it
  const base = colorParts(ui.bg) || colorParts("#0a0f19");
  let c = colorParts(ui.panel2) || colorParts(ui.panel) || colorParts(ui.field) || [23, 32, 51, 1];
  const a = Math.max(0, Math.min(1, c[3]));
  const mix = [0, 1, 2].map(i => Math.round(c[i] * a + base[i] * (1 - a)));
  const lum = (0.2126 * mix[0] + 0.7152 * mix[1] + 0.0722 * mix[2]) / 255;
  return { bg: "rgb(" + mix.join(", ") + ")", fg: lum > 0.55 ? "#101418" : "#f2f5fa", dark: lum <= 0.55 };
}
function allThemes() { return ((S.look && S.look.themes) || []).concat(S.mythemes || []); }      // the ready-made themes, then the ones you made
function applyAccent() {
  const v = lookW || S.look.values;
  const [r, g, b] = rgb(v.accent);
  const st = document.documentElement.style;
  st.setProperty("--accent", r + ", " + g + ", " + b);
  const t = allThemes().find(x => x.id === v.theme), ui = (t && t.ui) || {};      // the panel itself wears the theme too
  for (const [k, name] of [["bg", "--bg"], ["panel", "--panel"], ["panel2", "--panel2"], ["line", "--line"], ["field", "--field"], ["dialog", "--dialog"], ["blur", "--pblur"]]) {
    if (ui[k]) st.setProperty(name, ui[k]); else st.removeProperty(name);
  }
  const opt = optionColors(ui);      // the open list of a drop down is drawn by the browser: it gets solid colours that always read well, whatever the theme
  st.setProperty("--opt-bg", opt.bg); st.setProperty("--opt-fg", opt.fg);
  document.documentElement.classList.toggle("glassy", !!ui.blur);
  if (ui.rim) st.setProperty("--prim", rimShadow(ui.rim)); else st.removeProperty("--prim");
}
async function doUndo() {
  try { const r = await api("POST", "/api/undo", {}); send({ type: "clear" }); toast("Undone: " + r.undone); await afterChange(true); } catch (e) { fail(e); }
}
function discardPreview() { send({ type: "clear" }); lookW = bgW = layW = null; clearDraft(); }

// the buttons in the top line of every screen: what is not saved yet, then Discard, Undo, Save and (in the dashboard's frame) Open in Tab, or Log Out
let footEl = null, footSave = null;
// the Save button is kept (not made again) when the bar is drawn again: a hex code that is typed and then followed by a click on Save makes the field fire
// "change" while the mouse button is down, the bar is drawn again, and a button that is replaced at that moment never receives its click
function saveButton(off, fn) {
  if (!footSave) footSave = h("button", { class: "primary" }, "Save");
  footSave.disabled = off; footSave.onclick = fn;
  return footSave;
}
function drawFoot(dirty, onSave, onRevert, extra) {
  if (!footEl) return;
  put(footEl,
    onSave ? h("div", { class: "state" + (dirty ? " dirty" : ""), title: dirty ? "You have changes that are not saved yet." : "Everything shown is saved." }, dirty ? "Unsaved Changes" : "Saved") : null,
    onRevert ? h("button", { disabled: !dirty, onclick: onRevert }, "Discard Changes") : null,
    extra || null,
    view === "drives" ? null : h("button", { disabled: !S.undo, onclick: doUndo, title: S.undo ? "Undo: " + S.undo : "Nothing to undo" }, "Undo"),      // (the Drives screen changes no files of the dashboard: nothing to undo or save)
    view === "drives" ? null : saveButton(!onSave || !dirty, onSave || (() => {})),
    framed ? h("a", { class: "btn", href: location.href, target: "_blank", rel: "noopener" }, "Open in New Tab") : null,
    h("button", { class: "ghost", onclick: async () => { try { await api("POST", "/api/logout", {}); } catch (e) { /* already out */ } S = null; showLogin(); } }, "Log Out"));
}
function saveBar(dirty, onSave, onRevert, saveLabel, extra) {      // (kept for the screens: they hand over what the bottom bar shows)
  drawFoot(dirty, onSave, onRevert, extra);
  return null;
}


// ---------------------------------------------------------------- Drives (look at the drives, health and checks per drive; rename, sleep, wake, mount again;
// add a spare drive to a pool, move a drive between pools, take one out, erase a spare drive)
// The panel never touches a drive itself: the server asks the drives tool through a narrow sudo rule. The changes that erase or move things ask for
// typed confirmations here, and the drives tool asks for them again (it only goes on when it gets exactly the words), and refuses while a backup runs.
let DRapps = null;      // /api/drives/apps: which of Immich / Nextcloud cannot find their files, and whether a backup copy exists
let DR = null, DRerr = "", DRbusy = "", DRhealth = null, DRcheck = null, DRwait = "", DRjob = null, DRpoll = 0;
let drivesBox = null;
const ROLE_TEXT = { main: "Main", backup: "Backup", parity: "Parity", array: "Array", spare: "Spare", system: "System", "plain-data": "Plain Data" };
const STATE_TEXT = { connected: "Connected", "connected (used last)": "Connected", MISSING: "Missing", "NOT MOUNTED": "Not Mounted",
  "not connected to a pool": "Not in a Pool", "boot/system drive (never touched)": "Boot Drive" };      // (short words: they must fit in their column)
const STATE_HINT = { "connected (used last)": "A backup copy on the boot drive. It is only used when the other backup drives are full.", "boot/system drive (never touched)": "The boot drive. The panel never changes it." };
const JOB_TEXT = { add: "Adding the drive...", wipe: "Erasing the drive...", disconnect: "Taking the drive out of its pool...", move: "Moving the drive...", remount: "Fixing the drives. This can take a minute...", moveboot: "Moving the files from the boot drive to the drive. This can take a while...", appsfix: "Fixing Immich and Nextcloud. Copying files back from the backup can take a long time...",
  setup: "Building the new setup. This can take a few minutes...", bootadd: "Setting aside part of the boot drive...", rename: "Saving the name...", sleep: "Telling the drive to sleep...", wake: "Waking the drive up..." };
function humanBytes(n) {
  if (typeof n !== "number" || !(n >= 0)) return "-";
  const u = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }      // (as drives are sold: a 1 TB drive shows as 1 TB)
  return (n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)) + " " + u[i];
}
function stateText(t) { t = t || ""; return STATE_TEXT[t] || (t ? t[0].toUpperCase() + t.slice(1) : ""); }
function stateClass(t) { t = t || ""; return t.startsWith("connected") ? "ok" : (t.startsWith("MISSING") || t === "NOT MOUNTED") ? "bad" : ""; }
function usageBar(used, size) {
  if (typeof used !== "number" || typeof size !== "number" || !(size > 0)) return null;
  const pct = Math.max(0, Math.min(100, Math.round(used * 100 / size)));
  return h("div", { class: "usebar", role: "img", "aria-label": pct + " percent used" }, h("i", { style: { width: pct + "%" }, class: pct >= 95 ? "full" : pct >= 85 ? "high" : "" }));
}
function diskOf(dev) {      // /dev/sda1 -> sda, /dev/nvme0n1p2 -> nvme0n1, /dev/sdb -> sdb
  dev = (dev || "").replace(/^\/dev\//, "");
  return /^(nvme|mmcblk|loop)/.test(dev) ? dev.replace(/p\d+$/, "") : dev.replace(/\d+$/, "");
}
let DRretry = 0, DRhealthRetry = 0;
function loadDrives(tries) {
  if (DRjob && DRjob.running) return Promise.resolve();
  tries = tries || 0;
  clearTimeout(DRretry);
  DRwait = "Looking at the drives...";
  drawDrives();
  const gaveUp = e => { DRerr = e.message; DRwait = ""; drawDrives(); };
  const follow = () => api("GET", "/api/drives/job").then(j => { if (j.running) { DRbusy = j.action; DRjob = j; DRwait = ""; followJob(); drawDrives(); return true; } return false; }).catch(() => false);
  return api("GET", "/api/drives").then(d => {
    DR = d; DRerr = ""; DRwait = "";
    if (d.stale) {      // a change is running: the boxes show the drives as they were before it, and the progress is followed
      return follow().then(running => { if (!running && tries < 20) DRretry = setTimeout(() => { if (drivesBox && drivesBox.isConnected) loadDrives(tries + 1); }, 2500); drawDrives(); });
    }
    drawDrives(); if (!DRhealth) quietHealth(); rescanConfig(); quietApps();
  }).catch(e => {
    if (e.status !== 409) return gaveUp(e);
    // another drive command is running: when it is a change, follow its progress; else look again in a moment (nothing for the person to do)
    return api("GET", "/api/drives/job").then(j => {
      if (j.running) { DRbusy = j.action; DRjob = j; DRwait = ""; followJob(); drawDrives(); }
      else if (tries < 20) DRretry = setTimeout(() => { if (drivesBox && drivesBox.isConnected) loadDrives(tries + 1); }, 2500);
      else gaveUp(e);
    }).catch(() => gaveUp(e));
  });
}
function quietHealth(tries) {      // temperature, health, model and serial are read in the background; a sleeping drive is not woken up for it
  tries = tries || 0;
  clearTimeout(DRhealthRetry);
  api("GET", "/api/drives/health").then(r => { DRhealth = r; drawDrives(); }).catch(e => {
    if (e.status === 409 && tries < 20) { DRhealthRetry = setTimeout(() => { if (drivesBox && drivesBox.isConnected && !DRhealth) quietHealth(tries + 1); }, 3000); return; }
    DRhealth = { drives: [], ok: true }; drawDrives();
  });
}
function quietApps() {      // does Immich or Nextcloud miss its files? (looking only; nothing is shown when it cannot be told)
  api("GET", "/api/drives/apps").then(a => { DRapps = a; drawDrives(); }).catch(() => { DRapps = null; });
}
async function appsRestore() {
  const b = (DRapps || {}).backup || {};
  const ok = await confirmBox("Restore From the Backup?",
    "The files that are missing are copied back from the last backup" + (b.stamp ? " (" + b.stamp + ", result " + (b.result || "unknown") + ")" : "") + ". Files that are already there are never overwritten. Files that were added or changed after that backup are not in it and cannot come back. Immich and Nextcloud stay stopped while the files are copied, and start by themselves when it is done. Their accounts and settings are the same. This can take a long time.",
    "Restore From Backup");
  if (ok) startJob("appsfix", { mode: "restore", typed: ["RESTORE"] }, "The files are back and Immich and Nextcloud are running again.");
}
async function appsFresh() {
  const names = ((DRapps || {}).problems || []).map(a => a === "nextcloud" ? "Nextcloud" : a === "immich" ? "Immich" : a).join(" and ");
  const r = await driveDialog({
    title: "Start on Empty Folders",
    lead: [names + " will start on empty folders. Their accounts and settings stay the same, because those are saved on the boot drive."],
    questions: [],
    warn: () => "The photos and files that were on the missing drive will not show up. Immich keeps a list of photos it cannot open, and apps that sync with Nextcloud may remove their own copies of files the server no longer has. Do this only when the old files are really gone, or after you restored what you could.",
    typed: () => [{ word: "START" }],
    sure: () => "I understand that the old photos and files will not be shown.",
    ok: () => "Start on Empty Folders", danger: () => true });
  if (!r) return;
  startJob("appsfix", { mode: "fresh", typed: r.typed }, names + " started on empty folders.");
}
async function moveBootFiles() {      // the files saved on the boot drive while Main had no drive are copied to the Main pool and removed from the boot drive
  const ok = await confirmBox("Move the Files to the Drive?",
    "The files saved on the boot drive are copied to the Main pool and every file is checked. Only when all of them are on the pool are the old copies removed from the boot drive. A file that exists in both places with different content is never replaced, and its old copy stays on the boot drive. Your services stop for a moment while this runs.",
    "Move the Files");
  if (ok) startJob("moveboot", {}, "The files are on the Main pool now.");
}
function appsCard() {      // shown after Fix Drives, or whenever a drive was lost: the two apps are stopped on purpose
  const p = (DRapps && DRapps.problems) || [];
  if (!p.length) return null;
  const names = p.map(a => a === "nextcloud" ? "Nextcloud" : a === "immich" ? "Immich" : a).join(" and ");
  const bk = (DRapps.backup || {}).found;
  return h("div", { class: "card warncard", role: "alert" }, h("h2", {}, names + " Cannot Find Their Files"),
    h("p", {}, "Their files were on a drive that is not in the Main pool now, so " + (p.length > 1 ? "they refuse" : "it refuses") + " to start. That is on purpose: started on an empty folder, they would look as if everything was deleted. Their accounts and settings are not lost."),
    h("p", { class: "muted small" }, bk ? "A backup copy of your files was found. Restoring copies back only what is missing." : "No backup copy of your files was found. If the old drive still works, connect it again and press Fix Drives. Otherwise you can start on empty folders."),
    h("div", { class: "row" },
      bk ? h("button", { class: "primary small", disabled: !!DRbusy, onclick: appsRestore }, "Restore From Backup") : null,
      h("button", { class: "small", disabled: !!DRbusy, onclick: appsFresh }, "Start on Empty Folders")));
}
function drawDrives() {
  if (!(drivesBox && drivesBox.isConnected)) return;
  if (DRdrag) { DRdrawLater = true; return; }      // (not while a drive is being dragged: the tile under the mouse would vanish)
  put(drivesBox, drivesBody());
  drawBackups();      // (its buttons wait while a drive change runs)
  refreshCard();
}

// ---- a change that runs in the background (it can take hours when files are copied): the page follows its progress lines
function followJob() {
  clearTimeout(DRpoll);
  const tick = () => api("GET", "/api/drives/job").then(j => {
    DRjob = j;
    if (j.running) { drawDrives(); DRpoll = setTimeout(tick, 2000); return; }
    jobFinished(j);
  }).catch(() => { DRpoll = setTimeout(tick, 4000); });
  tick();
}
async function jobFinished(j) {
  const was = DRbusy, okText = DRokText, last = DRlast;
  DRbusy = "";
  DRjob = null;
  DRokText = "";
  DRlast = null;
  DRhealth = DRcheck = null;
  const busy = j.rc !== 0 && /Not a good moment/.test(j.message || "") && last && !(last.body.typed || []).includes("NOW");
  if (busy) {      // something is being written to a pool right now: say what, and let the person decide
    await loadDrives();
    const why = (j.message || "").replace(/^.*?Not a good moment: ?/, "").replace(/\. Nothing was changed.*$/, "").replace(/\.$/, "") || "something is being written to a pool";
    const go = await confirmBox("Not a Good Moment", why[0].toUpperCase() + why.slice(1) + ". Nothing was changed. Going ahead now stops the containers for a moment and can cut that short. Wait until it has finished, or go ahead anyway?", "Go Ahead Anyway", true);
    if (go) startJob(last.action, Object.assign({}, last.body, { typed: (last.body.typed || []).concat(["NOW"]) }), last.okText);
    return was;
  }
  if (j.rc !== 0 && j.rc !== 4) DRfail = { what: JOB_TEXT[j.action] ? JOB_TEXT[j.action].replace(/\.\.\..*$/, "") : "That change", message: j.message || "That did not work.", lines: (j.lines || []).filter(l => !/\(typed in the panel\)|^Type /.test(l)), time: new Date() };
  else DRfail = null;
  toast(j.rc === 0 ? (okText || "Done.") : (j.message || (j.rc === 4 ? "Stopped." : "That did not work.")), j.rc !== 0 && j.rc !== 4);      // (4: the person pressed Abort; the message says what was stopped and what was put back)
  await loadDrives();
  return was;
}
let DRokText = "";
let DRfail = null;      // the last change that did not work: it stays on the page until it is dismissed (a toast is gone in seconds)
async function startJob(action, body, okText) {
  if (DRbusy) return;
  DRbusy = action;
  DRfail = null;
  DRokText = okText || "";
  DRlast = { action, body, okText };
  const items = (body.ids || [body.id]).filter(Boolean).map(x => String(x).split(":")[0]);
  DRjob = { running: true, action, items, progress: {}, lines: [] };
  DRsel = new Set();
  drawDrives();
  try { await api("POST", "/api/drives/" + action, body); followJob(); } catch (e) { DRbusy = ""; DRjob = null; DRokText = ""; DRlast = null; fail(e); drawDrives(); }
}
async function driveDo(action, body, okReload) {      // the quick ones: rename, sleep, wake, mount again (the answer comes back in the same call)
  if (DRbusy) return;
  DRbusy = action;
  drawDrives();
  try {
    const r = await api("POST", "/api/drives/" + action, body);
    toast(r.message || "Done.");
  } catch (e) { fail(e); }
  DRbusy = "";
  await loadDrives();
}

// ---- a dialog with questions and typed confirmations
// cfg: { title, lead: [text], questions: [{ id, label, options: [{ value, label, hint }], value, show(state) }], note(state) -> text|null, warn(state) -> text|null,
//        refuse(state) -> text|null (nothing can be done: only a Close button), typed(state) -> [{ word, auto }] (the words the drives tool wants; nobody types them:
//        a risky one makes the "I understand" box show, which cfg.sure(state) words; an auto one does not), ok(state) -> button text, danger(state) -> bool }
function driveDialog(cfg) {
  return new Promise(resolve => {
    const state = {};
    (cfg.questions || []).forEach(q => { state[q.id] = q.value; });
    const dynamic = h("div", {});
    (cfg.fields || []).forEach(f => { state[f.id] = f.value; });
    const fieldBox = (cfg.fields || []).map(f => h("label", { class: "dfield" }, h("span", {}, h("b", {}, f.label), f.hint ? h("small", {}, f.hint) : null),
      h("input", { type: "number", min: f.min, max: f.max, step: 1, value: f.value, inputmode: "numeric", oninput: ev => { state[f.id] = ev.target.value; refresh(); } })));
    const okBtn = h("button", { class: "primary" }, "OK");
    let sure = false;      // the "I understand" box
    const finish = v => { if (!done) { done = true; resolve(v); } d.close(); };
    let done = false;
    const refresh = () => {
      const qs = (cfg.questions || []).filter(q => !q.show || q.show(state));
      const refuse = cfg.refuse ? cfg.refuse(state) : null;
      const typed = refuse ? [] : (cfg.typed ? cfg.typed(state) : []);
      const needSure = typed.some(t => !t.auto);      // (the drives tool still wants its exact words; the panel sends them, nobody has to type)
      const bad = refuse ? null : (cfg.invalid ? cfg.invalid(state) : null);
      const check = () => { const b = cfg.invalid && !refuse ? cfg.invalid(state) : null; okBtn.disabled = !!b || (!refuse && needSure && !sure); if (invalidBox) { invalidBox.textContent = b || ""; invalidBox.hidden = !b; } };
      const invalidBox = h("p", { class: "dwarn", role: "alert", hidden: !bad }, bad || "");
      put(dynamic, [
        qs.map(q => h("fieldset", { class: "dq" }, h("legend", {}, q.label),
          q.options.map(o => h("label", { class: "dopt" },
            h("input", Object.assign({ type: "radio", name: "dq-" + q.id, value: o.value, onchange: () => { state[q.id] = o.value; sure = false; refresh(); } }, state[q.id] === o.value ? { checked: true } : {})),
            h("span", {}, h("b", {}, o.label), o.hint ? h("small", {}, o.hint) : null))))),
        cfg.note && cfg.note(state) ? h("p", { class: "muted" }, cfg.note(state)) : null,
        cfg.fields && !refuse ? invalidBox : null,
        refuse ? h("p", { class: "dwarn", role: "alert" }, refuse) : (cfg.warn && cfg.warn(state) ? h("p", cfg.danger && cfg.danger(state) ? { class: "dwarn", role: "alert" } : { class: "dnote", role: "status" }, cfg.warn(state)) : null),
        needSure ? h("label", { class: "dopt sure" },
          h("input", { type: "checkbox", checked: sure, onchange: ev => { sure = ev.target.checked; check(); } }),
          h("span", {}, h("b", {}, cfg.sure ? cfg.sure(state) : "I understand this cannot be undone."))) : null]);
      okBtn.textContent = refuse ? "Close" : cfg.ok(state);
      okBtn.className = !refuse && cfg.danger && cfg.danger(state) ? "danger" : "primary";
      okBtn.onclick = () => refuse ? finish(null) : finish({ answers: Object.assign({}, state), typed: typed.map(t => t.word) });
      check();
    };
    const d = h("dialog", { class: "wide" }, h("h2", {}, cfg.title), (cfg.lead || []).map(t => h("p", {}, t)), fieldBox, dynamic,
      h("div", { class: "actions" }, h("button", { onclick: () => finish(null) }, "Cancel"), okBtn));
    d.addEventListener("close", () => { d.remove(); finish(null); });
    refresh();
    document.body.append(d);
    d.showModal();
  });
}
// ---- Configure Drives: scan the spare drives, recommend a setup, list the others from best to worst
let DRcfg = null;      // null = hidden, { loading } or { err } or the answer of /api/drives/setups
let DRskip = new Set();      // spare drives the person left out of Configure Drives (no setup uses them)
let DRcfgBusy = false;      // the list is being looked at again after a drive was left out or put back
const setupsUrl = () => "/api/drives/setups" + (DRskip.size ? "?skip=" + encodeURIComponent([...DRskip].join(",")) : "");
async function skipDrive(id, leave) {      // leave a spare drive out of the setups (or put it back): the setups are worked out again for the drives that are left
  if (leave) DRskip.add(id); else DRskip.delete(id);
  DRcfgBusy = true;
  drawDrives();
  await rescanConfig();
  DRcfgBusy = false;
  drawDrives();
}
async function openConfig() {
  if (DRcfg && !DRcfg.loading) { DRcfg = null; drawDrives(); return; }
  DRcfg = { loading: true };
  DRskip = new Set();
  drawDrives();
  try {
    DRcfg = await api("GET", setupsUrl());
    (DRcfg.options || []).forEach(o => { if (o.id === "pool" && o.fits) { o.can_build = true; o.why = ""; } });      // (a plain pool only adds drives to Main: it works with drives already in Main too)
  } catch (e) { DRcfg = { err: String((e && e.message) || e || "The drives could not be scanned.") }; }
  drawDrives();
}
async function rescanConfig() {      // the list in Configure Drives must match the drives as they are now (a change may have used or freed some)
  if (!DRcfg || DRcfg.loading || DRcfg.err) return;
  try {
    const c = await api("GET", setupsUrl());
    DRskip = new Set([...DRskip].filter(id => (c.spare || []).some(sp => sp.id === id)));      // (a drive that is gone from the list cannot be left out any more)
    (c.options || []).forEach(o => { if (o.id === "pool" && o.fits) { o.can_build = true; o.why = ""; } });
    if (DRcfg && !DRcfg.loading) { DRcfg = c; drawDrives(); }
  } catch (e) { /* the old list stays until the next refresh */ }
}
const protectText = o => o.tolerates > 0 ? (o.tolerates === 1 ? "1 drive can fail" : o.tolerates + " drives can fail") + (o.nightly ? " (copied every night)" : "") : "no protection";
const setupLine = o => o.title + (o.fits ? "  -  " + humanBytes(o.usable_bytes) + " usable, " + protectText(o) : "  -  needs " + o.min + " drives");
async function buildPlainPool(o) {      // a plain pool is just "add these drives to Main": the files on a drive can stay
  const c = DRcfg || { spare: [] };
  const drives = o.drives.map(id => c.spare.find(sp => sp.id === id)).filter(Boolean);
  const left = c.spare.filter(sp => !o.drives.includes(sp.id));
  const withFiles = drives.filter(sp => !sp.blank);
  const mode = (s, sp) => sp.blank ? "erase" : s["m-" + sp.id];
  const erasing = s => drives.filter(sp => mode(s, sp) === "erase");
  const running = poolOf("main").mounted;
  const r = await driveDialog({
    title: "Build: " + o.title,
    lead: [o.blurb, "Drives used (" + drives.length + " of " + c.spare.length + "): " + drives.map(sp => sp.name + " (" + humanBytes(sp.size_bytes) + ")").join(", "),
      withFiles.length ? "Drives that are already formatted can keep their files: the files then show up in the Main pool." : "These drives are empty. They are formatted for HomeLab.",
      left.length ? "Not used: " + left.map(sp => sp.name + " (" + humanBytes(sp.size_bytes) + ")").join(", ") + ". They stay as spare drives." : "Every spare drive is used."],
    questions: withFiles.map(sp => ({ id: "m-" + sp.id, label: sp.name + "  ·  " + sp.device + "  ·  already formatted", value: sp.keep_ok ? "keep" : "erase", options: sp.keep_ok ? [KEEP_OPT("Main"), ERASE_OPT] : [CANT_KEEP_OPT] })),
    warn: s => {
      const e = erasing(s).filter(sp => !sp.blank);
      if (e.length) return "Everything on " + e.map(sp => sp.device).join(", ") + " will be permanently deleted.";
      if (erasing(s).length) return "The empty drives are formatted for HomeLab. Nothing is lost. " + (withFiles.length ? "The files on the other drives stay as they are. " : "") + (running ? "The Main pool is running, so nothing stops." : "The containers that use the Main pool stop for a minute.");
      return "The files on the drives stay as they are. " + (running ? "The Main pool is running, so nothing stops." : "The containers that use the Main pool stop for a minute.");
    },
    typed: s => erasing(s).length ? erasing(s).map(sp => ({ word: sp.device })).concat([{ word: "ERASE" }]) : [],
    sure: () => "I understand that everything on the drives marked for erasing will be permanently deleted.",
    ok: s => erasing(s).some(sp => !sp.blank) ? "Erase Where Needed and Build" : erasing(s).length ? "Format and Build Pool" : "Build Pool", danger: s => erasing(s).some(sp => !sp.blank) });
  if (!r) return;
  const ids = drives.map(sp => sp.id + ":" + mode(r.answers, sp));
  const body = drives.length === 1 ? { ids: [drives[0].id], role: "main", mode: mode(r.answers, drives[0]), typed: r.typed } : { ids, role: "main", typed: r.typed };
  startJob("add", body, o.title + " is ready: " + nDrives(drives.length).toLowerCase() + " in the Main pool.");
}
async function buildSetup(o) {
  if (o.id === "pool") return buildPlainPool(o);
  const c = DRcfg || { spare: [] };
  const drives = o.drives.map(id => c.spare.find(sp => sp.id === id)).filter(Boolean);
  const left = c.spare.filter(sp => !o.drives.includes(sp.id));
  const withFiles = drives.filter(sp => !sp.blank);
  const par = o.id === "snapraid1" ? 1 : o.id === "snapraid2" ? 2 : 0;      // protection drives: they are erased, so a drive that keeps its files cannot be one
  const keepable = o.can_keep ? withFiles.filter(sp => sp.keep_ok) : [];
  const defKeep = new Set();
  if (o.id === "mirror") { const k = keepable.slice().sort((a, b) => b.size_bytes - a.size_bytes)[0]; if (k) defKeep.add(k.id); }      // (one drive can keep its files; the other holds the copy)
  else if (par) drives.slice().sort((a, b) => b.size_bytes - a.size_bytes).slice(par).forEach(sp => { if (keepable.includes(sp)) defKeep.add(sp.id); });
  const modeOf = (st, sp) => (keepable.includes(sp) ? st["m-" + sp.id] : "erase");
  const kept = st => drives.filter(sp => modeOf(st, sp) === "keep");
  const erased = st => drives.filter(sp => modeOf(st, sp) !== "keep");
  const withFilesErased = st => erased(st).filter(sp => !sp.blank);
  const r = await driveDialog({
    title: "Build: " + o.title,
    lead: [o.blurb, "Drives used (" + drives.length + " of " + c.spare.length + "): " + drives.map(sp => sp.name + " (" + humanBytes(sp.size_bytes) + ")").join(", "),
      (humanBytes(o.usable_bytes) === humanBytes(o.used_bytes) ? "You get all of the " + humanBytes(o.used_bytes) + " on these drives. " : "You get about " + humanBytes(o.usable_bytes) + " of the " + humanBytes(o.used_bytes) + " on these drives. ") + (o.tolerates > 0 ? cap(protectText(o)) + " without losing files." : "No drive may fail: one dead drive loses the files."),
      keepable.length ? (o.id === "mirror" ? "One drive can keep its files (it becomes the Main drive); the other drive holds the copy and is erased." : "Drives that hold files can keep them as data drives. The biggest drive" + (par > 1 ? "s" : "") + " that " + (par > 1 ? "are" : "is") + " not kept hold" + (par > 1 ? "" : "s") + " the protection data and " + (par > 1 ? "are" : "is") + " erased.") : null,
      o.migrate ? "Your Main pool has " + humanBytes(c.main_used_bytes || 0) + " of files and this setup holds " + humanBytes(o.usable_bytes) + ", so everything fits. The files are copied into the new setup first and checked; only then does it become your Main pool. The old Main drives are released afterwards: their files are not erased, and they show up as spare drives. " + serviceText(c.main_services) + " The copy can take hours for a lot of data. If you press Abort while it copies, the services start again and nothing changes." : null,
      left.length ? "Not used: " + left.map(sp => sp.name + " (" + humanBytes(sp.size_bytes) + ")").join(", ") + ". They stay as spare drives." : "Every spare drive is used."].filter(Boolean),
    questions: keepable.map(sp => ({ id: "m-" + sp.id, label: sp.name + "  ·  " + sp.device + "  ·  already formatted", value: defKeep.has(sp.id) ? "keep" : "erase", options: [KEEP_OPT("Main"), ERASE_OPT] })),
    invalid: st => o.id === "mirror" && kept(st).length > 1 ? "A mirror can keep the files of one drive only: the other drive becomes the copy." : par && drives.length - kept(st).length < par ? "SnapRAID needs " + par + " drive" + (par > 1 ? "s" : "") + " for the protection data, and " + (par > 1 ? "they are" : "it is") + " erased. Let at least " + par + " of the drives be erased." : null,
    refuse: () => o.can_build ? null : o.why,
    warn: st => (erased(st).length ? "Everything on " + erased(st).map(sp => sp.device).join(", ") + " will be permanently deleted" + (withFilesErased(st).length ? " (" + withFilesErased(st).map(sp => sp.name).join(", ") + " already hold files)" : "") + "." : "") + (kept(st).length ? " The files on " + kept(st).map(sp => sp.device).join(", ") + " stay as they are." : "") + (o.kind !== "pool" && o.id !== "mirror" && !/^snapraid/.test(o.id) ? " The new pool becomes your Main pool." : "") + (o.migrate ? " The files of your current Main pool are copied into it, and the old Main drives are released (nothing on them is erased)." : ""),
    typed: () => [{ word: o.id }, { word: "ERASE" }],
    sure: () => "I understand that everything on the drives marked for erasing will be permanently deleted.",
    ok: st => erased(st).length === drives.length ? "Erase and Build Setup" : "Build Setup", danger: () => true });
  if (!r) return;
  const ids = keepable.length ? o.drives.map(id => id + ":" + (modeOf(r.answers, drives.find(sp => sp.id === id) || {}) || "erase")) : o.drives;
  startJob("setup", { setup: o.id, ids, typed: r.typed }, o.title + " is ready.");
}
function cfgBox() {
  if (!DRcfg) return null;
  const off = !!DRbusy || !!DRwait;
  if (DRcfg.loading) return h("div", { class: "cfg", role: "status" }, h("p", { class: "muted" }, "Scanning the drives..."));
  if (DRcfg.err) return h("div", { class: "cfg", role: "alert" }, h("p", { class: "dwarn" }, DRcfg.err), h("button", { class: "small", onclick: () => { DRcfg = null; openConfig(); } }, "Try Again"));
  const c = DRcfg, rec = (c.options || []).find(o => o.id === c.recommended);
  const spare = c.spare || [], usable = spare.filter(sp => !sp.skipped);
  const sizes = usable.map(sp => humanBytes(sp.size_bytes)).join(", ");
  if (!spare.length) return h("div", { class: "cfg" }, h("p", { class: "muted" }, "No spare drives to build a setup on. Connect drives (or take them out of Main and Backup), then press Configure Drives again."));
  const pick = spare.length >= 2 ? h("fieldset", { class: "cfgpick", disabled: off || DRcfgBusy }, h("legend", {}, "Drives to Use"),
    spare.map(sp => h("label", {}, h("input", Object.assign({ type: "checkbox", onchange: ev => skipDrive(sp.id, !ev.target.checked) }, sp.skipped ? {} : { checked: true })),
      h("span", {}, sp.name + "  ·  " + sp.device + "  ·  " + humanBytes(sp.size_bytes)))),
    h("small", { class: "muted" }, "Take the tick off a drive to leave it out. It stays a spare drive and is not touched.")) : null;
  if (!rec) return h("div", { class: "cfg" }, pick, h("p", { class: "muted" }, usable.length ? "No setup can be built on the drives you chose." : "Every spare drive is left out. Tick at least one drive to see the setups."));
  const others = c.options.filter(o => o.id !== rec.id);
  return h("div", { class: "cfg" }, pick,
    h("p", { class: "muted small" }, "Scanned " + nDrives(spare.length).toLowerCase() + (spare.length === 1 ? " that is" : " that are") + " not in a pool" + (usable.length < spare.length ? " (using " + usable.length + ": " + sizes + ")" : ": " + sizes) + ". Setups are ranked by a balance of protection and usable space. Every setup erases the drives it uses, except a plain pool, a mirror and SnapRAID: they can keep the files that are on a drive. A RAID or ZFS setup can also be built while Main has drives: your files are copied into it first, and the old Main drives are released afterwards (their files are not erased)."),
    h("div", { class: "cfgrec" }, h("b", {}, "Recommended: " + rec.title), h("span", { class: "muted small" }, humanBytes(rec.usable_bytes) + " usable, " + protectText(rec) + ", uses " + nDrives(rec.drives.length).toLowerCase()),
      !rec.can_build ? h("span", { class: "dwarn small" }, rec.why) : null),
    h("div", { class: "row tight" },
      h("button", { class: "primary", disabled: off, onclick: () => buildSetup(rec) }, "Build Recommended Setup"),
      h("select", { class: "cfgsel", disabled: off, "aria-label": "Other setups, best to worst", onchange: ev => { const o = others.find(x => x.id === ev.target.value); ev.target.value = ""; if (o && o.fits) buildSetup(o); else if (o) toast(o.title + " needs " + o.min + " drives, and only " + usable.length + " can be used now.", true); } },
        h("option", { value: "" }, "Other setups, best to worst..."),
        others.map(o => h("option", Object.assign({ value: o.id }, o.fits ? {} : { disabled: true }), setupLine(o) + (o.fits && !o.can_build ? "  (not possible yet)" : ""))))));
}
const other = r => (r === "main" ? "backup" : "main");
const cap = t => t[0].toUpperCase() + t.slice(1);

async function renameDrive(a) {
  const name = await askText("Rename Drive", "New name for " + a.name + " (letters, numbers, spaces and . ( ) + , -)", a.custom ? a.name : "");
  if (name === null) return;
  if (!/^[A-Za-z0-9 .()+,-]{1,40}$/.test(name) || /^[ .-]|[ .-]$/.test(name)) { toast("A name may have up to 40 letters, numbers, spaces and these marks: . ( ) + , -  It cannot start or end with a space, a dot or a dash.", true); return; }
  driveDo("rename", { id: a.id, name }, true);
}
async function autoName(a) {
  if (await confirmBox("Use the Automatic Name?", "The drive will be called by its size, make and type again instead of \"" + a.name + "\".", "Use Automatic Name")) driveDo("rename", { id: a.id, name: "auto" }, true);
}
async function remountDrives() {
  const ok = await confirmBox("Fix Drives?",
    "Use this after a drive was unplugged, the power was cut or a drive was lost. The containers that use the pool stop, every drive and pool is mounted again from the saved setup, and the containers start again. Then it checks that Immich and Nextcloud can find their files. If they cannot, they stay stopped and you choose what to do next. It can take a minute, and nothing is erased or moved. If a backup or an upload is running right now, it is refused and nothing changes.",
    "Fix Drives");
  if (ok) driveDo("remount", {}, true);
}

const poolOf = role => ((DR && DR.status && DR.status.pools) || []).find(p => p.role === role) || {};
const devOf = t => "/dev/" + diskOf(t.d.device);
const nDrives = n => n === 0 ? "No Drives" : n + (n === 1 ? " Drive" : " Drives");
const KEEP_OPT = R => ({ value: "keep", label: "Keep the files", hint: "The drive is added as it is. Its files show up in the " + R + " pool." });
const ERASE_OPT = { value: "erase", label: "Erase the drive and format it", hint: "Everything on the drive is deleted. It is added as a new, empty drive." };
const CANT_KEEP_OPT = { value: "erase", label: "Erase the drive and format it", hint: "HomeLab can only use a drive as it is when it has one Linux (ext4) partition. This one is set up another way (for example Windows exFAT or NTFS, or several partitions), so its files cannot be kept. Everything on it is deleted and it is formatted for HomeLab." };

async function addDrives(tiles, role) {
  const R = cap(role), sps = tiles.map(t => t.sp), one = sps.length === 1;
  const modeOf = (s, sp) => one ? s.mode : s["m-" + sp.id];
  const erasing = s => sps.filter(sp => modeOf(s, sp) === "erase");
  const questions = one
    ? [{ id: "mode", label: sps[0].keep_ok ? "What should happen to the files on this drive?" : "This drive has to be erased first", value: sps[0].keep_ok ? "keep" : "erase", options: sps[0].keep_ok ? [KEEP_OPT(R), ERASE_OPT] : [CANT_KEEP_OPT] }]
    : sps.map(sp => ({ id: "m-" + sp.id, label: sp.name + "  ·  " + sp.device, value: sp.keep_ok ? "keep" : "erase", options: sp.keep_ok ? [KEEP_OPT(R), ERASE_OPT] : [CANT_KEEP_OPT] }));
  const running = poolOf(role).mounted;
  const r = await driveDialog({
    title: one ? "Add Drive to " + R + " Pool" : "Add " + sps.length + " Drives to " + R + " Pool",
    lead: sps.map(sp => sp.name + "  ·  " + sp.device + "  ·  " + humanBytes(sp.size_bytes)),
    questions,
    warn: s => {
      const e = erasing(s);
      if (e.length) return "Everything on " + e.map(sp => sp.device).join(", ") + " will be permanently deleted.";
      return "The files on the drive" + (one ? "" : "s") + " stay as they are and appear in the " + R + " pool. " + (running ? "The pool is running, so nothing stops." : "The containers that use it stop for a minute.");
    },
    typed: s => { const e = erasing(s); return e.length ? e.map(sp => ({ word: sp.device })).concat([{ word: "ERASE" }]) : []; },
    sure: () => "I understand that everything on " + (one ? "this drive" : "the erased drives") + " will be permanently deleted.",
    ok: s => erasing(s).length ? "Erase and Add " + (one ? "Drive" : "Drives") : "Add " + (one ? "Drive" : "Drives"), danger: s => erasing(s).length > 0 });
  if (!r) return;
  const body = one ? { ids: [sps[0].id], role, mode: r.answers.mode, typed: r.typed }
    : { ids: sps.map(sp => sp.id + ":" + r.answers["m-" + sp.id]), role, typed: r.typed };
  startJob("add", body, one ? sps[0].name + " was added to the " + R + " pool." : nDrives(sps.length) + " were added to the " + R + " pool.");
}
async function eraseSpare(sp) {
  const dev = sp.device;
  const r = await driveDialog({
    title: "Erase Spare Drive",
    lead: [sp.name + "  ·  " + dev + "  ·  " + humanBytes(sp.size_bytes), "Only a spare drive can be erased here. A drive in a pool and the boot drive never can."],
    questions: [{ id: "mode", label: "What should the drive be afterwards?", value: "format", options: [
      { value: "format", label: "A new, empty drive (formatted)", hint: "Ready to be added to a pool." },
      { value: "empty", label: "Empty, without a file system", hint: "It must be formatted before it can be used." }] }],
    warn: () => "Everything on " + dev + " will be permanently deleted.",
    typed: () => [{ word: dev }, { word: "ERASE" }],
    sure: () => "I understand that everything on this drive will be permanently deleted.",
    ok: () => "Erase Drive", danger: () => true });
  if (r) startJob("wipe", { id: sp.id, mode: r.answers.mode, typed: r.typed }, sp.name + " was erased" + (r.answers.mode === "format" ? " and formatted." : "."));
}
const DRAIN_SPARE = 2147483648;      // the drives tool keeps this much free on a drive it copies to
async function bootAdd(role) {      // part of the boot drive becomes a drive of this pool
  const bl = bootLimits(), R = cap(role);
  if (!bl) { toast("The boot drive cannot lend any space right now.", true); return; }
  if (bootIn(role)) { toast("The " + R + " pool already has a Boot Drive Space. Take it out first to make a different size.", true); return; }
  const free = (DR.status || {}).boot_free_bytes;
  const r = await driveDialog({
    title: "Use Part of the Boot Drive for the " + R + " Pool",
    lead: ["The boot drive also holds the system and your apps. Free now: " + humanBytes(free) + ". It always keeps " + humanBytes(typeof free === "number" ? free - bl.max_bytes : 0) + " or more free for the system.",
      "The space is taken from the boot drive right away and stays reserved, even while the space is empty. The space is the last place the " + role + " pool uses: it gets files only when the other " + role + " drives are full."],
    fields: [{ id: "size", label: "Size in " + bl.unit, value: Math.max(bl.lo, Math.min(bl.hi, 100)), min: bl.lo, max: bl.hi, hint: "From " + bl.lo + " to " + bl.hi + " " + bl.unit }],
    questions: [],
    invalid: st => { const n = Number(st.size); return !Number.isInteger(n) || n < bl.lo || n > bl.hi ? "Choose a whole number from " + bl.lo + " to " + bl.hi + " " + bl.unit + "." : null; },
    warn: () => "If the boot drive fails, you lose everything in this space together with the system." + (role === "backup" ? " A backup on the boot drive helps if a Main drive dies, but not if the boot drive dies: the backup goes with it." : ""),
    typed: () => [{ word: "CONTINUE" }],
    sure: () => "I understand that this part of the boot drive is used for storage and goes with it if it fails.",
    ok: () => "Add to " + R + " Pool", danger: () => false });
  if (r) startJob("bootadd", { role, units: Number(r.answers.size), typed: r.typed }, "The Boot Drive Space was added to the " + R + " pool.");
}
function poolFacts(tiles) {      // what is left in the pool when these drives go, and whether the files that are on the leaving drives fit on the ones that stay
  const rens = tiles.map(t => t.ren), total = rens[0].others + 1, remaining = total - rens.length, role = rens[0].role;
  const copyable = rens.some(a => a.has_data) && remaining > 0;
  const leaving = new Set(tiles.map(t => t.id));
  const stay = tilesNow().filter(t => (t.kind === "pool" || t.kind === "boot") && t.d.role === role && t.ren && t.ren.connected && !leaving.has(t.id));
  const free = stay.reduce((n, t) => n + (t.d.free_bytes || 0), 0), maxFree = stay.reduce((n, t) => Math.max(n, t.d.free_bytes || 0), 0);
  const need = rens.reduce((n, a) => n + (a.used_bytes || 0), 0), maxNeed = rens.reduce((n, a) => Math.max(n, a.used_bytes || 0), 0);
  const noRoom = copyable && (need + DRAIN_SPARE > free || maxNeed + DRAIN_SPARE > maxFree);
  const roomText = "There is not enough free room on the " + role + " drives that stay (" + humanBytes(need) + " to copy, " + humanBytes(free) + " free, and " + humanBytes(DRAIN_SPARE) + " is kept free). A drive whose files do not fit is not taken out. Pick fewer drives, or choose not to copy.";
  return { remaining, only: remaining <= 0, copyable, noRoom, roomText };
}
function friendlyService(n) { const w = String(n).split(/[_-]/)[0] || String(n); return w.charAt(0).toUpperCase() + w.slice(1); }
function serviceText(list) {      // the containers that use the Main pool, in plain words (immich_server and immich_redis both count as Immich)
  const names = [...new Set((list || []).map(friendlyService))];
  if (!names.length) return "No services use the Main pool right now.";
  return "These services use the Main pool and are stopped while the files are copied, then started again: " + names.join(", ") + ". Until the copy is done, they cannot reach your files.";
}
function emptyDriveText(t) { return t.ren.used_bytes > 0 ? "  ·  no files on it (the " + humanBytes(t.ren.used_bytes) + " used is the drive's own format)" : "  ·  holds no files"; }
async function takeOutDrives(tiles) {
  const f = poolFacts(tiles), role = tiles[0].ren.role, R = cap(role), one = tiles.length === 1;
  const names = tiles.map(t => t.d.name).join(", ");
  const held = tiles.reduce((n, t) => n + (t.ren.used_bytes || 0), 0);
  const bootData = tiles.some(t => t.kind === "boot" && t.ren.has_data);      // a Boot Drive Space is deleted when it leaves, so its files must be copied first
  const r = await driveDialog({
    title: one ? "Take Drive Out of the " + R + " Pool" : "Take " + tiles.length + " Drives Out of the " + R + " Pool",
    lead: [one ? tiles[0].d.name + (tiles[0].ren.has_data ? "  ·  holds " + humanBytes(held) : emptyDriveText(tiles[0])) : names],
    questions: f.copyable && !bootData ? [{ id: "copy", label: (one ? "Its files are" : "Their files are") + " in the " + role + " pool. What should happen to them?", value: "yes", options: [
      { value: "yes", label: "Copy them to another " + role + " drive first (recommended)", hint: "Every file is copied and checked before the drive is taken out. Nothing is lost." },
      { value: "no", label: "Do not copy them", hint: "The files stay on the drive only. They disappear from the " + role + " pool." }] }] : [],
    note: () => bootData && !f.only ? "The files in the Boot Drive Space are copied to the other " + role + " drives first. Taking it out gives its space back to the boot drive, which deletes it." : null,
    warn: s => bootData && f.only ? "There is no other " + role + " drive to copy the files of the Boot Drive Space to, and taking it out deletes it. Every file in it is permanently lost. If you want to keep them, add another " + role + " drive first (or cancel)." : f.only ? "No " + role + " drive stays, so nothing can be copied: the files stay on the " + (one ? "drive" : "drives") + " only (nothing is deleted). " + (role === "main" ? "The Main pool will be empty, and the services that use it (like Immich, Nextcloud and FileBrowser) will keep running and save their files on the boot drive until you add a Main drive again." : "Backups stop until another backup drive is added.") : f.copyable && s.copy === "no" ? "Without copying, the files on " + (one ? "this drive" : "these drives") + " will not show in the " + role + " pool any more. They stay on the drive." : f.noRoom && s.copy === "yes" ? f.roomText : "The drive" + (one ? " is" : "s are") + " taken out of the " + role + " pool. The data on the drive is not touched. The containers that use the pool stop for a minute.",
    typed: s => bootData && f.only ? [{ word: "ERASE" }, { word: "REMOVE" }] : f.only ? [{ word: "REMOVE" }] : f.copyable && s.copy === "no" ? [{ word: "CONTINUE" }] : [],
    sure: () => bootData && f.only ? "I understand that the files in the Boot Drive Space will be permanently deleted." : f.only ? (role === "main" ? "I understand that the Main pool will be empty and the services that use it stay stopped until a Main drive is added." : "I understand that backups stop until another backup drive is added.") : "I understand that the files on " + (one ? "this drive" : "these drives") + " will no longer show in the " + role + " pool.",
    ok: () => one ? "Take Drive Out" : "Take Drives Out", danger: s => f.only || (f.copyable && s.copy === "no") });
  if (r) startJob("disconnect", { ids: tiles.map(t => t.ren.id), copy: bootData ? "yes" : (r.answers.copy || "no"), typed: r.typed }, one ? tiles[0].d.name + " was taken out of the " + R + " Pool." : nDrives(tiles.length) + " were taken out of the " + R + " Pool.");
}
async function moveDrives(tiles) {
  const f = poolFacts(tiles), role = tiles[0].ren.role, to = other(role), T = cap(to), R = cap(role), one = tiles.length === 1;
  const keepQ = (id, label, t) => ({ id, label, value: "keep", options: t.kind === "boot" ? [
    { value: "keep", label: "Keep the files in the space", hint: "The space moves as it is, so its files show up in the " + T + " pool." },
    { value: "erase", label: "Start with a new, empty space", hint: "The files in the space are deleted. A new, empty space of the same size joins the " + T + " pool." }] : [
    { value: "keep", label: "Keep the files on the drive", hint: "The drive is added to the " + T + " pool as it is, so its files show up in the " + T + " pool." },
    { value: "erase", label: "Erase the drive and format it", hint: "Everything on the drive is deleted. It joins the " + T + " pool as a new, empty drive." }] });
  const clash = tiles.some(t => t.kind === "boot") && bootIn(to);
  const questions = (one ? [keepQ("keep", "What should happen to the files on this drive?", tiles[0])] : tiles.map(t => keepQ("k-" + t.ren.id, t.d.name, t)))
    .concat([{ id: "copy", label: (one ? "Copy its files" : "Copy their files") + " to the other " + role + " drives first?", value: "yes", show: () => f.copyable, options: [
      { value: "yes", label: "Yes, copy them first (recommended)", hint: "Every file is copied and checked, so the " + role + " pool keeps them." },
      { value: "no", label: "No, do not copy them", hint: "The " + role + " pool loses the files of " + (one ? "this drive" : "these drives") + "." }] }]);
  const keepOf = (s, t) => one ? s.keep : s["k-" + t.ren.id];
  const erasing = s => tiles.filter(t => keepOf(s, t) === "erase");
  const r = await driveDialog({
    title: one ? "Move Drive to the " + T + " Pool" : "Move " + tiles.length + " Drives to the " + T + " Pool",
    lead: [one ? tiles[0].d.name + " moves from the " + R + " pool to the " + T + " pool." + (tiles[0].ren.has_data ? "  It holds " + humanBytes(tiles[0].ren.used_bytes) + "." : tiles[0].ren.used_bytes > 0 ? "  It has no files on it (the " + humanBytes(tiles[0].ren.used_bytes) + " used is the drive's own format)." : "  It holds no files.")
      : tiles.map(t => t.d.name).join(", ") + " move from the " + R + " pool to the " + T + " pool."],
    questions,
    refuse: () => clash ? "The " + T + " pool already has a Boot Drive Space. A pool can have only one." : f.only && role === "main" ? (one ? "This is the only Main drive. Moving it would take away the pool your services use. Add another Main drive first." : "These are all the Main drives. Moving them would take away the pool your services use. Leave at least one Main drive.") : null,
    warn: s => {
      const noCopy = f.copyable && s.copy === "no", e = erasing(s);
      const devs = x => x.map(t => t.kind === "boot" ? "the Boot Drive Space" : devOf(t)).join(", ");
      if (e.length && noCopy) return "The files on " + (one ? "this drive" : "the erased drives") + " will be permanently lost: " + (one ? "the drive is" : "they are") + " erased and the files are not copied anywhere.";
      if (e.length) return "Everything on " + devs(e) + " will be permanently deleted" + (f.copyable ? ", after its files are copied to the other " + role + " drives." : ".");
      if (f.only) return "No " + role + " drive stays, so nothing can be copied: the files stay on the " + (one ? "drive" : "drives") + " and show in the " + T + " pool. The " + R + " pool is empty until another drive is added.";
      if (f.noRoom && s.copy === "yes") return f.roomText;
      if (noCopy) return "The files go with the drive" + (one ? "" : "s") + " to the " + T + " pool. The " + R + " pool loses them.";
      return "The files stay on the drive" + (one ? "" : "s") + " and also show up in the " + T + " pool, while the " + R + " pool keeps its own copy. The two pools then hold some of the same files." + (f.only ? " This is the only Backup drive: backups stop until another backup drive is added." : "");
    },
    typed: s => {
      const t = [];
      erasing(s).forEach(x => { if (x.kind !== "boot") t.push({ word: devOf(x) }); });
      if (erasing(s).length) t.push({ word: "ERASE" });
      if (erasing(s).length < tiles.length) t.push({ word: "KEEP", auto: true });      // (keeping the files is not risky: no box to tick)
      if (f.copyable && s.copy === "no") t.push({ word: "CONTINUE" });
      if (f.only) t.push({ word: "REMOVE" });
      return t;
    },
    sure: s => {
      const noCopy = f.copyable && s.copy === "no";
      if (erasing(s).length) return noCopy ? "I understand that everything on the erased drives will be permanently deleted and its files are not copied anywhere." : "I understand that everything on " + (one ? "this drive" : "the erased drives") + " will be permanently deleted.";
      return noCopy ? "I understand that the " + role + " pool will lose the files of " + (one ? "this drive" : "these drives") + "." : "I understand that backups stop until another backup drive is added.";
    },
    ok: s => erasing(s).length ? (one ? "Erase and Move Drive" : "Erase and Move Drives") : (one ? "Move Drive" : "Move Drives"), danger: s => erasing(s).length > 0 || (f.copyable && s.copy === "no") });
  if (!r) return;
  const copy = f.copyable ? r.answers.copy : "no";
  const body = one ? { ids: [tiles[0].ren.id], keep: r.answers.keep, copy, typed: r.typed }
    : { ids: tiles.map(t => t.ren.id + ":" + r.answers["k-" + t.ren.id]), copy, typed: r.typed };
  startJob("move", body, one ? tiles[0].d.name + " was moved to the " + T + " Pool." : nDrives(tiles.length) + " were moved to the " + T + " Pool.");
}

// ---- health and quick check, inside a drop down under each connected drive
function powerFor(drive, power) {         // the spinning drive a row belongs to (a pool drive is a partition such as sdb1; a spare drive is sdb)
  const dev = (drive.device || "").replace(/^\/dev\//, "");
  return (power || []).find(p => dev.startsWith(p.id) && /^p?\d*$/.test(dev.slice(p.id.length))) || null;
}
function rowFor(d, rows) {      // the health / check row of this drive: same name and disk, else same disk
  rows = rows || [];
  const disk = diskOf(d.device);
  return rows.find(r => r.name === d.name && diskOf(r.device) === disk) || rows.find(r => disk && diskOf(r.device) === disk) || rows.find(r => r.name === d.name) || null;
}
function runLook(kind) {
  return async () => {
    DRwait = kind === "health" ? "Reading the health of the drives..." : "Checking the drives...";
    drawDrives();
    try { const r = await api("GET", "/api/drives/" + kind); if (kind === "health") DRhealth = r; else DRcheck = r; } catch (e) { fail(e); }
    DRwait = "";
    drawDrives();
  };
}
function healthBlock(d) {
  const r = rowFor(d, DRhealth && DRhealth.drives);
  if (!DRhealth) return null;
  if (!r) return h("p", { class: "muted small" }, "Health: this drive did not report anything (a Boot Drive Space has no health of its own).");
  const bits = [typeof r.temperature_c === "number" ? r.temperature_c + " °C" : "", typeof r.power_on_hours === "number" ? r.power_on_hours.toLocaleString() + " hours on" : "",
    typeof r.reallocated_sectors === "number" ? r.reallocated_sectors + " moved sectors" : "", typeof r.pending_sectors === "number" ? r.pending_sectors + " waiting sectors" : ""].filter(Boolean);
  const bad = r.health === "FAILED" || r.pending_sectors > 0;
  return h("div", { class: "result" },
    h("div", { class: "row tight" }, h("b", {}, "Health"), h("span", { class: "pill " + (r.health === "PASSED" ? "ok" : bad ? "bad" : "dim") }, r.health === "PASSED" ? "Passed" : r.health === "FAILED" ? "Failing" : r.health === "asleep" ? "Asleep" : r.health === "unsupported" ? "Not Reported" : stateText(r.health))),
    bits.length ? h("p", { class: "muted small" }, bits.join("  ·  ")) : null,
    r.note ? h("p", { class: bad ? "badtext" : "muted small" }, cap(r.note)) : null,
    bad ? h("p", { class: "badtext" }, "Copy its files to another drive soon.") : null);
}
function checkBlock(d, spare) {
  const r = rowFor(d, DRcheck && DRcheck.drives);
  if (!DRcheck) return null;
  if (!r) return h("p", { class: "muted small" }, spare ? "Quick Check: nothing to check yet. It looks at the drives in the Main and Backup pools, and this drive is not in a pool. Add it to a pool and check again." : "Quick Check: this drive has no result.");
  return h("div", { class: "result" },
    h("div", { class: "row tight" }, h("b", {}, "Quick Check"), h("span", { class: "pill " + (r.result === "ok" ? "ok" : r.result === "warn" ? "warn" : "bad") }, r.result === "ok" ? "OK" : r.result === "warn" ? "Warning" : "Problem")),
    (r.findings || []).length ? r.findings.map(f => h("p", { class: f.level === "problem" ? "badtext" : "muted small" }, cap(f.text))) : h("p", { class: "muted small" }, "The file system is clean, no errors are recorded and the drive reports no problem."));
}
// ---- the Drives screen: a box with the drives that are not in a pool, and a box for each pool. A drive is a tile: drag it into a pool (or press it for its details and buttons).
function hddIcon() {
  const ns = "http://www.w3.org/2000/svg";
  const mk = (tag, at) => { const e = document.createElementNS(ns, tag); for (const k in at) e.setAttribute(k, at[k]); return e; };
  const svg = mk("svg", { viewBox: "0 0 64 48", width: 64, height: 48, class: "hdd", "aria-hidden": "true" });
  svg.append(mk("rect", { x: 3, y: 4, width: 58, height: 40, rx: 7, class: "hdd-body" }), mk("circle", { cx: 26, cy: 24, r: 12, class: "hdd-disc" }), mk("circle", { cx: 26, cy: 24, r: 3.5, class: "hdd-hub" }),
    mk("path", { d: "M26 24 L45 11", class: "hdd-arm" }), mk("circle", { cx: 54, cy: 37, r: 2.2, class: "hdd-led" }));
  return svg;
}
function ring(used, size) {
  const pct = typeof used === "number" && typeof size === "number" && size > 0 ? Math.max(0, Math.min(100, Math.round(used * 100 / size))) : null;
  const R = 26, C = 2 * Math.PI * R, ns = "http://www.w3.org/2000/svg";
  const mk = (tag, at) => { const e = document.createElementNS(ns, tag); for (const k in at) e.setAttribute(k, at[k]); return e; };
  const svg = mk("svg", { viewBox: "0 0 64 64", width: 56, height: 56, class: "ring" + (pct !== null && pct >= 95 ? " full" : pct !== null && pct >= 85 ? " high" : ""), role: "img", "aria-label": pct === null ? "Usage not known" : pct + " percent used" });
  svg.append(mk("circle", { cx: 32, cy: 32, r: R, class: "ring-bg" }));
  if (pct !== null) svg.append(mk("circle", { cx: 32, cy: 32, r: R, class: "ring-fg", "stroke-dasharray": (C * pct / 100).toFixed(1) + " " + C.toFixed(1), transform: "rotate(-90 32 32)" }));
  const t = mk("text", { x: 32, y: 36, "text-anchor": "middle", class: "ring-t" });
  t.textContent = pct === null ? "-" : pct + "%";
  svg.append(t);
  return svg;
}
function tempCell(r, pw) {
  if (!DRhealth) return h("span", { class: "muted" }, "...");
  if (pw && pw.state === "asleep") return h("span", { class: "muted", title: "The drive is asleep, so its temperature is not read." }, "Asleep");
  if (!r || typeof r.temperature_c !== "number") return h("span", { class: "muted", title: r && r.health === "unsupported" ? "This drive does not report a temperature." : null }, "-");
  return h("span", { class: r.temperature_c >= 60 ? "badtext" : r.temperature_c >= 50 ? "warntext" : "" }, r.temperature_c + " °C");
}
function healthCell(r) {
  if (!DRhealth) return h("span", { class: "muted" }, "...");
  if (!r) return h("span", { class: "muted", title: "This drive did not report anything." }, "-");
  const bad = r.health === "FAILED" || r.pending_sectors > 0;
  return h("span", { class: "pill " + (r.health === "PASSED" && !bad ? "ok" : bad ? "bad" : "dim"), title: r.health === "unsupported" ? (cap(r.note) || "This drive does not report its health.") : null },
    bad && r.health !== "FAILED" ? "Warning" : r.health === "PASSED" ? "Passed" : r.health === "FAILED" ? "Failing" : r.health === "asleep" ? "Asleep" : r.health === "unsupported" ? "Not Reported" : stateText(r.health));
}

let DRsel = new Set(), DRselMode = false, DRdrag = null, DRdrawLater = false, DRcard = null, DRlast = null;
function tilesNow() {      // every drive as one tile: where it is, and what can be done with it
  if (!DR) return [];
  const st = DR.status || {}, act = DR.actions || {};
  const lend = bootTile();
  const list = (st.drives || []).filter(d => !(lend.length && /^boot\/system drive/.test(d.state || ""))).map(d0 => {      // (the system drive's own tile would be a second "boot drive" next to the Boot Drive tile)
    const ren = (act.rename || []).find(a => d0.mount && d0.mount.split("/").pop() === a.id) || null;
    const d = ren && ren.boot_section ? Object.assign({}, d0, { name: d0.name.replace(/ boot drive section$/i, " Boot Drive Space") }) : d0;
    const sp = ren ? null : (act.spare || []).find(a => diskOf(d.device) === a.id) || null;
    const kind = ren ? (ren.boot_section ? "boot" : "pool") : sp ? "spare" : "other";
    const group = kind === "spare" ? "spare" : (kind === "pool" || kind === "boot") && ren.connected ? ren.role : "";      // "" = it cannot be dragged
    return { d, ren, sp, kind, group, id: ren ? ren.id : sp ? sp.id : (d.device && d.device !== "-" ? d.device : d.name) };
  });
  const arr = arrayTile(st, list);
  return list.concat(arr ? [arr] : [], lend);
}
const isMember = t => t.kind === "other" && t.d.role === "array";      // a drive of a RAID or ZFS setup: it is shown inside the setup's tile, not on its own
function arrayTile(st, list) {      // a RAID or ZFS setup is one tile inside Main, with its drives behind it
  if (!st.array) return null;
  const p = (st.pools || []).find(x => x.role === "main") || {}, members = list.filter(isMember);
  const ok = /^(online|clean|active|optimal)/i.test(st.array.health || "");
  return { d: { name: st.array.title, device: "-", role: "main", state: ok ? "connected" : (st.array.health || "unknown"), size_bytes: p.size_bytes, used_bytes: p.used_bytes, free_bytes: p.free_bytes, mount: p.path },
    ren: null, sp: null, kind: "array", group: "", id: "ARRAY", members, array: st.array };
}
function bootLimits() {      // what the boot drive can lend now (in the unit the drives tool uses: GB, or MB in its test mode)
  const bl = ((DR && DR.status) || {}).boot_limits;
  if (!bl || bl.small || typeof bl.max_bytes !== "number" || bl.max_bytes < bl.min_bytes || (bl.main && bl.backup)) return null;
  return Object.assign({ lo: Math.ceil(bl.min_bytes / bl.unit_bytes), hi: Math.floor(bl.max_bytes / bl.unit_bytes) }, bl);
}
const bootIn = role => ((DR && DR.actions && DR.actions.rename) || []).some(a => a.boot_section && a.role === role);
function bootTile() {      // the part of the boot drive that can be lent to a pool: a tile of its own in the Drives box
  const bl = bootLimits();
  if (!bl || bl.hi < bl.lo) return [];
  return [{ d: { name: "Boot Drive", device: "-", role: "bootfree", state: "connected", size_bytes: bl.max_bytes, used_bytes: null, free_bytes: null, mount: "" }, ren: null, sp: null, kind: "bootfree", group: "bootfree", id: "BOOTFREE" }];
}
const tileById = id => tilesNow().find(t => t.id === id) || null;
function selTiles() { return tilesNow().filter(t => DRsel.has(t.id)); }
function toggleSel(t) {
  if (!t.group || DRbusy || t.kind === "bootfree") return;
  if (DRsel.has(t.id)) DRsel.delete(t.id);
  else {
    const have = selTiles()[0];
    if (have && have.group !== t.group) { toast("Pick drives from one place: the Drives box, or one pool.", true); return; }
    DRsel.add(t.id);
  }
  drawDrives();
}
function dotBad(t) { return stateClass(t.d.state) === "bad"; }
function tile(t) {
  const d = t.d, pw = powerFor(d, (DR.actions || {}).power), hr = rowFor(d, DRhealth && DRhealth.drives);
  const bad = hr && (hr.health === "FAILED" || hr.pending_sectors > 0);
  const prog = DRjob && DRjob.running && (DRjob.items || []).includes(t.id) ? ((DRjob.progress || {})[t.id] || { pct: 0, text: "Waiting" }) : null;
  const dim = DRbusy && !prog;
  const sel = DRsel.has(t.id);
  const used = t.kind === "array" ? (typeof d.used_bytes === "number" ? humanBytes(d.used_bytes) + " of " + humanBytes(d.size_bytes) + " used  ·  " : "") + nDrives(t.members.length).toLowerCase() : t.kind === "bootfree" ? "up to " + humanBytes(d.size_bytes) + " to lend" : typeof d.used_bytes === "number" ? humanBytes(d.used_bytes) + " of " + humanBytes(d.size_bytes) + " used" : typeof d.size_bytes === "number" ? humanBytes(d.size_bytes) + " drive" : "";
  const draggable = !!t.group && !DRbusy;
  const el = h("div", {
    class: "tile" + (sel ? " sel" : "") + (t.group ? "" : " locked") + (dim ? " dim" : "") + (prog ? " working" : "") + (pw && pw.state === "asleep" ? " asleep" : ""),
    role: "button", tabindex: 0, draggable: draggable ? "true" : "false", "data-id": t.id, "data-group": t.group,
    "aria-label": d.name + ", " + stateText(d.state) + (used ? ", " + used : "") + (sel ? ", selected" : ""),
    title: d.name + (d.device && d.device !== "-" ? "  ·  " + d.device : ""),
    onclick: ev => { if (ev.ctrlKey || ev.metaKey || ev.shiftKey || DRselMode) { ev.preventDefault(); toggleSel(t); } else openCard(t.id); },
    onkeydown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); if (ev.ctrlKey || ev.metaKey || ev.shiftKey || DRselMode) toggleSel(t); else openCard(t.id); } },
    ondragstart: ev => dragStart(ev, t),
    ondragend: dragEnd },
    h("div", { class: "tname" }, d.name),
    h("div", { class: "ticon" }, hddIcon(),
      h("span", { class: "dot " + (dotBad(t) ? "bad" : "ok"), title: dotBad(t) ? stateText(d.state) : "Connected", role: "img", "aria-label": dotBad(t) ? stateText(d.state) : "Connected" }),
      bad ? h("span", { class: "warnmark", title: "The drive reports a problem. Press it for the health." }, "!") : null,
      (t.kind === "other" || (t.kind === "boot" && !t.group)) ? h("span", { class: "lock", title: t.kind === "boot" ? "This Boot Drive Space is not connected." : "This drive is managed outside the pools.", "aria-hidden": "true" }, "🔒") : null),
    prog ? h("div", { class: "tprog", role: "progressbar", "aria-valuenow": prog.pct, "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": d.name + ": " + prog.text },
        h("div", { class: "bar" }, h("i", { style: { width: Math.max(4, prog.pct) + "%" } })), h("small", {}, prog.text + (/%$/.test(prog.text) ? "" : "  " + prog.pct + "%")))
      : [usageBar(d.used_bytes, d.size_bytes) || h("div", { class: "usebar ghost" }), h("div", { class: "tused" }, used || "Size unknown")]);
  return el;
}
function dragStart(ev, t) {
  if (DRbusy || !t.group) { ev.preventDefault(); return; }
  const sel = selTiles(), ids = DRsel.has(t.id) ? sel.map(x => x.id) : [t.id];
  if (DRsel.has(t.id) && sel.some(x => x.group !== t.group)) { ev.preventDefault(); toast("Pick drives from one place: the Drives box, or one pool.", true); return; }
  DRdrag = { ids, group: t.group };
  try { ev.dataTransfer.setData("text/plain", ids.join(",")); ev.dataTransfer.effectAllowed = "move"; } catch (e) { /* ignore */ }
  if (drivesBox) drivesBox.dataset.drag = t.group;
  document.querySelectorAll(".tile").forEach(x => { if (ids.includes(x.dataset.id)) x.classList.add("dragging"); });
}
function dragEnd() {
  DRdrag = null;
  if (drivesBox) delete drivesBox.dataset.drag;
  document.querySelectorAll(".dzone.over").forEach(z => z.classList.remove("over"));
  document.querySelectorAll(".tile.dragging").forEach(z => z.classList.remove("dragging"));
  if (DRdrawLater) { DRdrawLater = false; drawDrives(); }
}
function zone(kind, accepts, kids, extra) {      // a box that takes dropped drives: kind is "drives", "main" or "backup"
  const ok = () => DRdrag && accepts.includes(DRdrag.group) && !(DRdrag.group === kind);
  return h("div", Object.assign({
    class: "dzone zone-" + kind, "data-zone": kind, "data-accepts": accepts.join(" "),
    ondragover: ev => { if (ok()) { ev.preventDefault(); ev.currentTarget.classList.add("over"); } },
    ondragleave: ev => { if (!ev.currentTarget.contains(ev.relatedTarget)) ev.currentTarget.classList.remove("over"); },
    ondrop: ev => { ev.preventDefault(); ev.currentTarget.classList.remove("over"); dropOn(kind); } }, extra || {}), kids);
}
function dropOn(kind) {
  const drag = DRdrag;
  dragEnd();
  if (!drag || DRbusy) return;
  const tiles = drag.ids.map(tileById).filter(Boolean);
  if (!tiles.length) return;
  if (drag.group === "bootfree" && (kind === "main" || kind === "backup")) bootAdd(kind);
  else if (drag.group === "spare" && (kind === "main" || kind === "backup")) addDrives(tiles, kind);
  else if ((drag.group === "main" || drag.group === "backup") && kind === other(drag.group)) moveDrives(tiles);
  else if ((drag.group === "main" || drag.group === "backup") && kind === "drives") takeOutDrives(tiles);
}
function selBar() {
  const sel = selTiles();
  if (!sel.length) return null;
  const g = sel[0].group, n = sel.length;
  const go = f => () => f(selTiles());      // (the drives stay picked when the question is cancelled; starting the change puts them back)
  return h("div", { class: "selbar", role: "region", "aria-label": "Selected drives" },
    h("b", {}, nDrives(n) + " selected"),
    g === "spare" ? [h("button", { class: "small", disabled: !!DRbusy, onclick: go(t => addDrives(t, "main")) }, "Add to Main"), h("button", { class: "small", disabled: !!DRbusy, onclick: go(t => addDrives(t, "backup")) }, "Add to Backup")] :
      [h("button", { class: "small", disabled: !!DRbusy, onclick: go(t => moveDrives(t)) }, "Move to " + cap(other(g))), h("button", { class: "small danger", disabled: !!DRbusy, onclick: go(t => takeOutDrives(t)) }, "Take Out")],
    h("button", { class: "small", onclick: () => { DRsel = new Set(); drawDrives(); } }, "Clear"));
}
function poolBox(p, tiles) {
  const T = (ROLE_TEXT[p.role] || p.role) + " Pool";
  return zone(p.role, ["spare", other(p.role)].concat(bootIn(p.role) ? [] : ["bootfree"]), [
    h("div", { class: "ph" },
      h("div", { class: "pt" }, h("h2", {}, T), h("span", { class: "sub" }, p.path + (p.mounted ? "  ·  " + (p.filesystem || "") : ""))),
      p.mounted ? [ring(p.used_bytes, p.size_bytes), h("div", { class: "pu" }, h("b", {}, humanBytes(p.used_bytes) + " used"), h("span", { class: "sub" }, humanBytes(p.free_bytes) + " free of " + humanBytes(p.size_bytes)))] : h("div", { class: "pu" }, h("span", { class: "sub" }, "Not mounted")),
      h("span", { class: "pill " + (p.mounted ? "ok" : "bad") }, p.mounted ? "Online" : "Offline")),
    h("div", { class: "tiles" }, tiles.length ? tiles.map(tile) : h("p", { class: "dropnote" }, "Drag a drive here to add it to the " + (ROLE_TEXT[p.role] || p.role) + " pool."))], { class: "dzone card pool zone-" + p.role });
}
// ---- the card that opens when a drive is pressed: its facts, and everything that can be done with it
function cardStat(label, ...kids) { return h("div", { class: "st" }, h("small", {}, label), h("div", {}, kids)); }
function bootCardBody(t) {
  const bl = bootLimits(), dis = !!DRbusy || !!DRwait, go = f => () => { closeCard(); f(); };
  const btn = (role, label) => h("button", { class: "small", disabled: dis || bootIn(role), title: bootIn(role) ? "The " + cap(role) + " pool already has a Boot Drive Space" : "", onclick: go(() => bootAdd(role)) }, label);
  return [
    h("p", { class: "muted" }, "The drive the system runs from. Part of its free space can be used as a drive of Main or Backup (a Boot Drive Space)."),
    h("div", { class: "stats" },
      cardStat("Free Space", typeof ((DR.status || {}).boot_free_bytes) === "number" ? humanBytes(DR.status.boot_free_bytes) : "-"),
      cardStat("Can Lend", bl ? bl.lo + " to " + bl.hi + " " + bl.unit : "-"),
      cardStat("Always Kept Free", bl ? humanBytes(bl.max_bytes > 0 ? DR.status.boot_free_bytes - bl.max_bytes : 0) : "-")),
    h("div", { class: "row tight cardactions" }, btn("main", "Add to Main"), btn("backup", "Add to Backup")),
    h("p", { class: "muted small" }, "You can also drag this tile into Main or Backup. A Boot Drive Space is the last place its pool uses, and it can be moved to the other pool or taken out again whenever you like.")];
}
function arrayCardBody(t) {
  const d = t.d, a = t.array || {};
  return [
    h("p", { class: "muted" }, "A RAID or ZFS setup: its drives work together as one pool, so the drives cannot be moved or erased one by one here."),
    h("div", { class: "stats" },
      cardStat("Health", h("span", { class: "pill " + (t.d.state === "connected" ? "ok" : "bad") }, cap(String(a.health || "unknown").toLowerCase()))),
      cardStat("Size", typeof d.size_bytes === "number" ? humanBytes(d.size_bytes) : "-"),
      cardStat("Used", typeof d.used_bytes === "number" ? humanBytes(d.used_bytes) + " (" + humanBytes(d.free_bytes) + " free)" : "-"),
      cardStat("Pool", "Main Pool")),
    typeof d.used_bytes === "number" ? usageBar(d.used_bytes, d.size_bytes) : null,
    h("div", { class: "stats" }, t.members.map(m => cardStat(m.d.name, humanBytes(m.d.size_bytes), h("span", { class: "devpath" }, m.d.device || "")))),
    h("p", { class: "muted small" }, "To take this setup apart, run \"sudo drives release\" on the server. It asks you to confirm, because it erases the drives of the setup.")];
}
function cardBody(t) {
  if (t.kind === "array") return arrayCardBody(t);
  if (t.kind === "bootfree") return bootCardBody(t);
  const d = t.d, act = DR.actions || {}, pw = powerFor(d, act.power), hr = rowFor(d, DRhealth && DRhealth.drives);
  const dis = !!DRbusy, ren = t.ren, sp = t.sp, wait = !!DRwait;
  const dev = devOf(t);
  const ident = hr ? [hr.model, hr.serial ? "Serial " + hr.serial : "", hr.filesystem ? hr.filesystem + (hr.label ? ' "' + hr.label + '"' : "") : ""].filter(Boolean).join("  ·  ") : "";
  const used = typeof d.used_bytes === "number" ? d : hr && typeof hr.used_bytes === "number" ? { used_bytes: hr.used_bytes, free_bytes: hr.free_bytes, size_bytes: d.size_bytes } : null;      // (a drive in no pool: its space is read from the drive itself)
  const poolName = t.kind === "spare" ? "Not in a pool" : t.kind === "other" ? "Outside the pools" : cap(ren.role) + " Pool";
  const go = f => () => { closeCard(); f(); };
  const btn = (label, f, opt) => h("button", { class: (opt && opt.danger ? "danger " : "") + "small", disabled: dis || wait || (opt && opt.off), onclick: f }, label);
  const connected = (d.state || "").startsWith("connected") || t.kind === "spare";
  const actions = [
    ren && btn("Rename", go(() => renameDrive(ren))),
    ren && ren.custom && btn("Automatic Name", go(() => autoName(ren))),
    pw && pw.state !== "asleep" && btn("Put to Sleep", go(() => driveDo("sleep", { id: pw.id }))),
    pw && pw.state === "asleep" && btn("Wake Up", go(() => driveDo("wake", { id: pw.id }))),
    (t.kind === "pool" || t.kind === "boot") && ren.connected && btn("Move to " + cap(other(ren.role)), go(() => moveDrives([t]))),
    (t.kind === "pool" || t.kind === "boot") && ren.connected && btn("Take Out", go(() => takeOutDrives([t])), { danger: true }),
    sp && btn("Add to Main", go(() => addDrives([t], "main"))),
    sp && btn("Add to Backup", go(() => addDrives([t], "backup"))),
    sp && btn("Erase", go(() => eraseSpare(sp)), { danger: true })].filter(Boolean);
  return [
    h("p", { class: "muted" }, [d.device && d.device !== "-" ? d.device : "", ident].filter(Boolean).join("  ·  ")),
    h("div", { class: "stats" },
      cardStat("Status", h("span", { class: "pill " + stateClass(d.state), title: STATE_HINT[d.state] || null }, stateText(d.state))),
      cardStat("Power", pw ? h("span", { class: "pill " + (pw.state === "asleep" ? "dim" : "") }, pw.state === "asleep" ? "Asleep" : pw.state === "awake" ? "Awake" : "Unknown")
        : hr && hr.removable ? h("span", { class: "pill", title: "A USB stick or memory card has no motor, so it never sleeps." }, "Always On") : h("span", { class: "muted" }, "-")),
      cardStat("Temp", tempCell(hr, pw)),
      cardStat("Health", healthCell(hr)),
      cardStat("Hours On", hr && typeof hr.power_on_hours === "number" ? hr.power_on_hours.toLocaleString() : h("span", { class: "muted" }, DRhealth ? "-" : "...")),
      cardStat("Size", typeof d.size_bytes === "number" ? humanBytes(d.size_bytes) : "-"),
      cardStat("Used", used ? humanBytes(used.used_bytes) + " (" + humanBytes(used.free_bytes) + " free)" : t.kind === "spare" && !DRhealth ? "..." : "-"),
      cardStat("Pool", poolName)),
    used ? usageBar(used.used_bytes, used.size_bytes || (used.used_bytes + used.free_bytes)) : null,
    connected ? h("div", { class: "row tight" },
      btn(DRhealth ? "Check Health Again" : "Check Health", runLook("health")),
      btn(DRcheck ? "Run Quick Check Again" : "Run Quick Check", runLook("check"))) : h("p", { class: "muted small" }, "This drive is not connected. Connect it and press Fix Drives."),
    wait ? h("p", { class: "muted small", role: "status" }, DRwait) : null,
    healthBlock(d), checkBlock(d, !!sp),
    actions.length ? h("div", { class: "row tight cardactions" }, actions) : null,
    h("p", { class: "muted small" }, "Health reads what the drive says about itself (SMART); a sleeping drive is not woken up. The quick check looks for file system errors and changes nothing." + (dev !== "/dev/" ? "" : ""))];
}
function openCard(id) {
  closeCard();
  const t = tileById(id);
  if (!t) return;
  const body = h("div", {});
  const d = h("dialog", { class: "wide dcard" }, h("h2", {}, t.d.name), body, h("div", { class: "actions" }, h("button", { class: "primary", onclick: () => closeCard() }, "Close")));
  d.addEventListener("close", () => { d.remove(); if (DRcard && DRcard.dlg === d) DRcard = null; });
  DRcard = { id, dlg: d, body, title: d.querySelector("h2") };
  document.body.append(d);
  refreshCard();
  d.showModal();
}
function refreshCard() {
  if (!DRcard) return;
  const t = tileById(DRcard.id);
  if (!t) { closeCard(); return; }
  DRcard.title.textContent = t.d.name;
  put(DRcard.body, cardBody(t));
}
function closeCard() { if (DRcard) { const d = DRcard.dlg; DRcard = null; try { d.close(); } catch (e) { /* closed */ } d.remove(); } }
async function abortJob() {      // the Abort button of a running add, move or take out
  const act = DRbusy;
  if (!/^(add|disconnect|move|setup|appsfix)$/.test(act) || (DRjob && DRjob.stopping)) return;
  if (act === "appsfix") {      // Cancel of the copy from the backup: what was copied is removed again
    if (!await confirmBox("Cancel the Copy?", "The copy stops right away and the files that were already copied from the backup are removed again, so the Main pool has none of this restore's data. Files that were in Main before are not touched. Immich and Nextcloud stay stopped, and you can start the restore again later.", "Cancel the Copy", true)) return;
    try { const r = await api("POST", "/api/drives/abort", {}); if (DRjob) DRjob.stopping = true; toast(r.message || "Stopping."); } catch (e) { fail(e); }
    drawDrives();
    return;
  }
  const text = act === "add"
    ? "Drives that are not added yet are not added. A drive that is already added stays added. A drive that is being erased finishes that step first."
    : act === "setup"
    ? "The copy stops right away. Your Main pool stays exactly as it is, with all of its files. The new setup is taken apart again and its drives are left empty."
    : "A drive that is still copying stops right away and stays where it is, with its files. A drive that is already done is put back into the pool it came from. A drive that is being erased finishes that step first. Files that were already copied to other drives stay there as extra copies.";
  if (!await confirmBox("Abort This Change?", text, "Abort", true)) return;
  try {
    const r = await api("POST", "/api/drives/abort", {});
    if (DRjob) DRjob.stopping = true;
    toast(r.message || "Stopping.");
  } catch (e) { fail(e); }
  drawDrives();
}
let DRlogOpen = false;      // the "Show the steps" box stays open while the page draws itself again (it redraws every two seconds during a change)
function stepsBox(lines) {
  const pre = h("pre", { class: "joblog" }, lines.join("\n"));
  const box = h("details", { class: "joblogbox", open: DRlogOpen }, h("summary", {}, "Show the steps"), pre);
  box.addEventListener("toggle", () => { DRlogOpen = box.open; });
  const keep = DRlogOpen && drivesBox && drivesBox.querySelector("details.joblogbox pre.joblog");      // (also keep the place the person scrolled to, unless it was at the end)
  if (keep) { const atEnd = keep.scrollTop + keep.clientHeight >= keep.scrollHeight - 4; setTimeout(() => { pre.scrollTop = atEnd ? pre.scrollHeight : keep.scrollTop; }, 0); }
  return box;
}
function drivesParts() {
  const out = [];
  if (DRwait || DRbusy) {
    const lines = DRjob && DRjob.lines ? DRjob.lines.filter(l => !/\(typed in the panel\)|^Type /.test(l)).slice(-60) : [];
    const copying = !!DRjob && Object.values(DRjob.progress || {}).some(p => /^Copying files/.test(p.text || ""));      // (a new setup can be stopped only while the files are copied: before that it is erasing, after that it is checking and switching over)
    const stopping = !!(DRjob && DRjob.stopping), canStop = !!DRbusy && (/^(add|disconnect|move)$/.test(DRbusy) || ((DRbusy === "setup" || DRbusy === "appsfix") && copying));
    const rp = (DRbusy === "appsfix" || DRbusy === "moveboot") && DRjob && DRjob.progress ? DRjob.progress[DRbusy] : null;      // the bar of the copy from the backup: "5.00 GB / 11.00 GB"
    out.push(h("div", { class: "card working", role: "status" }, DRbusy ? (stopping ? "Stopping at the next safe moment..." : (JOB_TEXT[DRbusy] || "Working...")) : DRwait,
      canStop ? h("div", { class: "row tight" }, h("button", { class: "danger small", disabled: stopping, onclick: abortJob, title: "Stops what is not finished yet, and puts the drives that are done back" }, stopping ? "Stopping..." : (DRbusy === "appsfix" ? "Cancel" : "Abort")),
        stopping ? h("span", { class: "muted small" }, DRbusy === "appsfix" ? "The copy has been told to stop. The files copied so far are being removed again. This can take a minute or two." : DRbusy === "setup" ? "The copy has been told to stop. The drives still have to finish writing what they already received, and then the new setup is taken apart and the services start again. This can take a few minutes (longer the more was already copied). Your Main pool is not touched." : "A copy stops at once; a step that has started finishes first. Drives that are already done are put back. This can take a few minutes.") : null) : null,
      rp ? h("div", { class: "tprog big", role: "progressbar", "aria-valuenow": rp.pct, "aria-valuemin": 0, "aria-valuemax": 100, "aria-label": rp.text },
        h("div", { class: "bar" }, h("i", { style: { width: Math.max(2, rp.pct) + "%" } })), h("small", {}, rp.text + "  (" + rp.pct + "%)")) : null,
      DRbusy === "appsfix" && !stopping ? h("p", { class: "muted small" }, copying ? "Cancel stops the copy and removes the files copied so far, so Main has none of this restore's data. You can leave this page: the work goes on." : "You can leave this page: the work goes on. The Cancel button shows up while the files are being copied.") : null,
      DRbusy && /^(add|wipe|disconnect|move)$/.test(DRbusy) ? h("p", { class: "muted small" }, "Please keep this page open or come back later. Copying files can take a long time. You can leave the page: the work goes on.") : null,
      DRbusy === "setup" && !stopping ? h("p", { class: "muted small" }, copying ? "You can stop while the files are copied: your Main pool then stays as it is. You can leave this page: the work goes on." : "A new setup can be stopped only while its files are copied (the Abort button shows up then). You can leave this page: the work goes on.") : null,
      lines.length ? stepsBox(lines) : null));
  }
  if (DRfail && !DRbusy) out.push(h("div", { class: "card failcard", role: "alert" }, h("h2", {}, "What Happened"),
    h("p", {}, h("b", {}, DRfail.what + " did not work. "), DRfail.message),
    h("p", { class: "muted small" }, "Nothing else was changed unless the message above says so. " + DRfail.time.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })),
    DRfail.lines.length ? stepsBox(DRfail.lines) : null,
    h("div", { class: "row tight" }, h("button", { class: "small", onclick: () => { DRfail = null; drawDrives(); } }, "Dismiss"))));
  if (DRerr) out.push(h("div", { class: "card", role: "alert" }, h("h2", {}, "The Drives Could Not Be Read"), h("p", { class: "muted" }, DRerr), h("button", { onclick: loadDrives }, "Try Again")));
  if (!DR) return out;
  const st = DR.status || {}, drives = st.drives || [];
  const off = !!DRbusy || !!DRwait;
  const tiles = tilesNow();
  out.push(h("div", { class: "dbar" },
    h("div", { class: "info" },
      st.last_backup ? h("span", {}, "Last backup: " + st.last_backup) : null,
      typeof st.boot_free_bytes === "number" ? h("span", {}, "Free space on the boot drive: " + humanBytes(st.boot_free_bytes)) : null),
    h("button", { class: "small" + (DRselMode ? " on" : ""), "aria-pressed": DRselMode ? "true" : "false", disabled: !!DRbusy, onclick: () => { DRselMode = !DRselMode; if (!DRselMode) DRsel = new Set(); drawDrives(); }, title: "Press drives to pick several, then use the buttons that show up" }, DRselMode ? "Done Selecting" : "Select"),
    h("button", { class: "small", disabled: off, onclick: () => { DRhealth = null; loadDrives(); } }, "Refresh"),
    h("button", { class: "small", disabled: !!DRbusy, onclick: remountDrives, title: "Mounts every drive and pool again from the saved setup and checks that Immich and Nextcloud find their files (after an unplug, a power cut or a lost drive)" }, "Fix Drives")));
  if ((st.main_empty || st.main_on_boot) && !DRbusy) {      // no drive in Main, or its drive is missing: the services keep running on the boot drive
    out.push(h("div", { class: "card warncard", role: "alert" }, h("h2", {}, st.main_on_boot ? "A Main Drive Is Missing" : "Main Has No Drive"),
      h("p", {}, st.main_on_boot
        ? "The Main drive was not found, so your services (Immich and Nextcloud, for example) are running from the boot drive for now. Files on the missing drive are not visible until it is back."
        : "Nothing is connected to the Main pool, so your services (Immich and Nextcloud, for example) are using the boot drive as their storage."),
      h("p", { class: "muted small" }, st.main_on_boot
        ? "Plug the drive in and press Fix Drives. Files saved on the boot drive meanwhile can then be copied onto the drive."
        : "To use a drive instead, drag it into Main, or press Configure Drives and build a setup. Files already saved on the boot drive are copied to the drive first.")));
  }
  if (st.boot_files_waiting && !DRbusy) {      // files saved on the boot drive lie hidden under the mounted Main pool
    out.push(h("div", { class: "card warncard", role: "status" }, h("h2", {}, "Files Are Waiting On The Boot Drive"),
      h("p", {}, "Some files were saved on the boot drive while Main had no drive. They are hidden while the Main pool is mounted."),
      h("p", { class: "muted small" }, "This copies them onto the Main pool, checks every file, and only then removes the old copies from the boot drive. Photos, videos and documents are not involved: only the small files that kept your services running. Your services stop for a moment and start again."),
      h("div", { class: "row tight" }, h("button", { class: "primary", onclick: moveBootFiles }, "Move the Files to the Drive"))));
  }
  const ac = appsCard();
  if (ac && !DRbusy) out.push(ac);
  out.push(selBar());
  const inPool = t => t.kind === "pool" || t.kind === "boot" || t.kind === "array" || (t.kind === "other" && (t.d.role === "main" || t.d.role === "backup"));
  const top = tiles.filter(t => !inPool(t) && !isMember(t));
  out.push(zone("drives", ["main", "backup"], [
    h("div", { class: "ph" }, h("div", { class: "pt" }, h("h2", {}, "Drives"), h("span", { class: "sub" }, "Connected but not in a pool. Drag a drive into Main or Backup, or select it for its details and buttons (a phone uses the buttons). Hold Ctrl or Shift while you select, or use Select, to pick several.")),
      h("span", { class: "pill dim" }, nDrives(top.filter(t => t.kind !== "bootfree").length)),
      h("button", { class: "small" + (DRcfg ? " on" : ""), "aria-expanded": DRcfg ? "true" : "false", disabled: off, onclick: openConfig, title: "Scans the spare drives and suggests the best setup for them (ZFS, RAID, SnapRAID, a pool)" }, "Configure Drives")),
    cfgBox(),
    h("div", { class: "tiles" }, top.length ? top.map(tile) : h("p", { class: "dropnote" }, "No spare drives. Connect a drive and press Refresh. Drag a drive from a pool here to take it out."))], { class: "dzone card pool zone-drives" }));
  out.push(h("div", { class: "pools" }, (st.pools || []).map(p => poolBox(p, tiles.filter(t => inPool(t) && t.d.role === p.role)))));
  if (!drives.length && !(st.pools || []).length) out.push(h("p", { class: "muted" }, "No drives were found."));
  if ((DR.actions || {}).can_sleep === false) out.push(h("p", { class: "muted small" }, "Sleep and wake need the tool hdparm, which is not installed on this machine."));
  return out;
}
function drivesBody() { return [drivesParts(), upBox, bkBox]; }
function viewDrives() {
  drivesBox = h("div", {});
  put(drivesBox, drivesBody());
  loadUploads();
  loadBackups();
  api("GET", "/api/backup/job").then(j => { if (j.running) { BKjob = j; BKwas = j.action; drawBackups(); followBackup(); } }).catch(() => { /* no backup tool: the section says so */ });
  api("GET", "/api/drives/job").then(j => {      // a change may still be running (the page was reloaded meanwhile)
    if (j.running) {      // (the drive boxes are asked for too: during a change the server answers with the last good look, marked stale, so the boxes stay on the page)
      DRbusy = j.action; DRjob = j; followJob(); drawDrives();
      api("GET", "/api/drives").then(d => { if (!DR) { DR = d; drawDrives(); } }).catch(() => { /* the progress card is still there */ });
    } else loadDrives();
  }).catch(() => loadDrives());
  return drivesBox;
}

// ---------------------------------------------------------------- Updates (what the bell on the dashboard points to)
// Container updates go through homelab-update (a quick database dump first, then one stack at a time), system updates through apt, and a restart through systemd.
// The panel runs them in the background and shows the lines they print; the page keeps following them when it is reloaded.
let UPD = null, UPDerr = "", UPDtimer = 0, UPDjob = null, UPDwas = "";
const updBox = h("div", { class: "upd" });
const UPD_WORKING = { check: "Looking for new versions...", containers: "Updating the containers...", system: "Updating the system...", restart: "Restarting the machine..." };

function updAgo(then, now) {
  if (!then) return "never";
  const m = Math.max(0, Math.round((now - then) / 60));
  return m < 2 ? "just now" : m < 120 ? m + " minutes ago" : m < 2880 ? Math.round(m / 60) + " hours ago" : Math.round(m / 1440) + " days ago";
}
async function loadUpdates(fresh) {
  try { UPD = await api("GET", "/api/updates" + (fresh === true ? "?fresh=1" : "")); UPDerr = ""; if (UPD.job && UPD.job.running) { UPDjob = UPD.job; UPDwas = UPD.job.action; followUpdates(); } } catch (e) { UPD = null; UPDerr = e.message; }
  drawUpdates();
}
function followUpdates() {
  clearTimeout(UPDtimer);
  const tick = async () => {
    if (!updBox.isConnected) return;
    let j;
    try { j = await api("GET", "/api/updates/job"); } catch (e) { UPDtimer = setTimeout(tick, 3000); return; }      // (a restart: the panel is away for a minute)
    if (j.running) { UPDjob = j; drawUpdates(); UPDtimer = setTimeout(tick, 1500); return; }
    UPDjob = null;
    const said = UPDwas;
    UPDwas = "";
    await loadUpdates();
    if (said) toast(j.message || "Done.", !!j.rc);
  };
  tick();
}
async function updStart(what, extra) {
  if (UPDjob && UPDjob.running) return;
  try {
    await api("POST", "/api/updates/start", Object.assign({ what }, extra || {}));
    UPDjob = { running: true, action: what, lines: [], pct: null, stage: "" };
    UPDwas = what;
    drawUpdates();
    followUpdates();
  } catch (e) { fail(e); }
}
async function updRestart() {
  if (!(await confirmBox("Restart the machine?", "Every service stops for a minute or two and starts again by itself. Do not do this while a backup or an upload is running.", "Restart Now", true))) return;
  updStart("restart", { confirm: true });
}
function updRow(title, sub, pill, buttons, prog) {
  return h("div", { class: "bkt" }, h("div", { class: "ph" }, h("div", { class: "pt" }, h("h3", {}, title), h("span", { class: "sub" }, sub)), pill, buttons), prog || null);
}
// the bar of a running update: the server counts what the tools print (images, services, packages) and sends a percent and a few words;
// without a percent (a check, a restart) the bar pulses
function updBar(job) {
  const pct = typeof job.pct === "number" ? Math.max(2, Math.min(100, job.pct)) : null;
  const words = job.stage || UPD_WORKING[job.action] || "Working...";
  return h("div", { class: "bkprog updprog" },
    h("div", { class: "bar" + (pct === null ? " wait" : ""), role: "progressbar", "aria-label": words, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": pct === null ? null : String(pct) },
      h("i", { style: { width: (pct === null ? 100 : pct) + "%" } })),
    h("span", { class: "muted small" }, words + (pct === null ? "" : "  (" + pct + "%)")));
}
function drawUpdates() {
  const busy = !!(UPDjob && UPDjob.running);
  const body = [h("div", { class: "ph" },
    h("div", { class: "pt" }, h("h2", {}, "Updates"), h("span", { class: "sub" }, "What is waiting to be updated. The bell on the dashboard shows the same things.")),
    h("button", { class: "small", disabled: busy, onclick: () => loadUpdates(true) }, "Refresh"))];
  if (UPDerr) body.push(h("p", { class: "badtext", role: "alert" }, UPDerr), h("button", { class: "small", onclick: loadUpdates }, "Try Again"));
  else if (!UPD) body.push(h("p", { class: "muted" }, "Looking at the updates..."));
  else {
    const n = UPD.containers.length;
    const names = UPD.containers.map(c => c.name).join(", ");
    body.push(h("div", { class: "bkl" },
      updRow("Containers", n ? n + " waiting: " + names + ". A quick database dump is made first, then each service is updated one after the other." : "Everything is up to date. Last looked " + updAgo(UPD.checked, UPD.now) + ".",
        h("span", { class: "pill " + (n ? "warn" : "ok") }, n ? n + " waiting" : "Up to date"),
        h("div", { class: "pills" }, h("button", { class: "small", disabled: busy, onclick: () => updStart("check") }, "Check Now"),
          h("button", { class: "small primary", disabled: busy || !n, onclick: () => updStart("containers") }, "Update Containers")),
        busy && (UPDjob.action === "containers" || UPDjob.action === "check") ? updBar(UPDjob) : null),
      updRow("System", UPD.system === null ? "Not checked yet. Press Update System to look and install." : UPD.system ? UPD.system + " package" + (UPD.system === 1 ? "" : "s") + " waiting (Ubuntu or Mint). Installing can take several minutes." : "Everything that can be installed is installed." + (UPD.kept_back ? " " + UPD.kept_back + " more " + (UPD.kept_back === 1 ? "package is" : "packages are") + " held back by Ubuntu: " + (UPD.kept_back === 1 ? "it needs" : "they need") + " other changes first, or " + (UPD.kept_back === 1 ? "is" : "are") + " being rolled out slowly. " + (UPD.kept_back === 1 ? "It installs" : "They install") + " by itself later. To see the list: apt list --upgradable" : ""),
        h("span", { class: "pill " + (UPD.system ? "warn" : UPD.system === null ? "dim" : "ok") }, UPD.system === null ? "Unknown" : UPD.system ? UPD.system + " waiting" : "Up to date"),
        h("div", { class: "pills" }, h("button", { class: "small primary", disabled: busy || UPD.system === 0, onclick: () => updStart("system") }, "Update System")),
        busy && UPDjob.action === "system" ? updBar(UPDjob) : null),
      updRow("Restart", UPD.restart ? "A system update asked for a restart. Do it when nothing important is running." : "No restart is needed.",
        h("span", { class: "pill " + (UPD.restart ? "warn" : "ok") }, UPD.restart ? "Needed" : "Not needed"),
        h("div", { class: "pills" }, h("button", { class: "small" + (UPD.restart ? " primary" : ""), disabled: busy, onclick: updRestart }, "Restart Machine")),
        busy && UPDjob.action === "restart" ? updBar(UPDjob) : null)));
  }
  if (UPDjob && UPDjob.running) {
    if (!UPD || UPDerr) body.push(updBar(UPDjob));
    body.push(h("p", { class: "muted" }, "Keep this page open if you can. It also keeps going if you leave."),
      h("pre", { class: "updlog", "aria-live": "polite" }, (UPDjob.lines || []).join("\n")));
  }
  put(updBox, h("div", { class: "card" }, body));
}
function viewUpdates() {
  drawUpdates();
  loadUpdates();
  return updBox;
}

// ---------------------------------------------------------------- Upload (above Backups on the Drives tab)
// Photos and videos go to Immich (with an API key pasted once), songs go into the music folder Navidrome plays from. Files are sent one at a time,
// each as the raw body of a request, so a video of several GB is fine. The queue lives here, so it keeps going while another tab of the panel is open.
let UP = null, UPerr = "";
const UPq = { photo: [], song: [] }, UPrun = { photo: false, song: false };
const upBox = h("div", { class: "up" });
const UP_NAMES = { photo: "Photos and Videos", song: "Songs" };
const upBusy = () => UPrun.photo || UPrun.song;
window.addEventListener("beforeunload", e => { if (upBusy()) { e.preventDefault(); e.returnValue = ""; } });

async function loadUploads() {
  try { UP = await api("GET", "/api/upload"); UPerr = ""; } catch (e) { UP = null; UPerr = e.message; }
  drawUploads();
}
const upExt = n => (n.includes(".") ? n.split(".").pop().toLowerCase() : "");
function upAdd(kind, files) {
  const ok = new Set(kind === "photo" ? UP.photo_ext : UP.song_ext), max = UP.limits[kind];
  for (const f of files) {
    const it = { file: f, state: "wait", pct: 0, msg: "" };
    if (!ok.has(upExt(f.name))) { it.state = "fail"; it.msg = upExt(f.name) ? "Not accepted here (." + upExt(f.name) + ")" : "No ending like .mp3 or .jpg"; }
    else if (f.size === 0) { it.state = "fail"; it.msg = "The file is empty"; }
    else if (f.size > max) { it.state = "fail"; it.msg = "Too big (the most is " + humanBytes(max) + ")"; }
    UPq[kind].push(it);
  }
  drawUploads();
  upPump(kind);
}
function upSendOne(kind, it) {
  return new Promise(resolve => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/upload/" + kind + "?name=" + encodeURIComponent(it.file.name) + (kind === "photo" ? "&mtime=" + (it.file.lastModified || Date.now()) : ""));
    x.setRequestHeader("X-Panel", "1");
    it.xhr = x;
    x.upload.onprogress = e => {
      if (!e.lengthComputable) return;
      it.pct = Math.round(e.loaded * 100 / e.total);
      if (it.barEl) it.barEl.style.width = it.pct + "%";
      if (it.pctEl) put(it.pctEl, it.pct + "%");
    };
    x.onload = () => {
      let js = {};
      try { js = JSON.parse(x.responseText); } catch (e) { /* not JSON */ }
      if (x.status === 401) { S = null; showLogin(); it.state = "fail"; it.msg = "Please log in again"; }
      else if (x.status >= 200 && x.status < 300) { it.state = kind === "photo" && js.status === "duplicate" ? "dup" : "done"; it.msg = js.saved && js.saved !== it.file.name ? "Saved as " + js.saved : ""; it.pct = 100; }
      else { it.state = "fail"; it.msg = js.error || ("Something went wrong (" + x.status + ")"); if (x.status === 409 && kind === "photo") loadUploads(); }
      resolve();
    };
    x.onerror = () => { it.state = "fail"; it.msg = "The connection was lost"; resolve(); };
    x.onabort = () => { it.state = "fail"; it.msg = "Stopped"; resolve(); };
    x.send(it.file);
  });
}
async function upPump(kind) {
  if (UPrun[kind]) return;
  UPrun[kind] = true;
  let sent = 0, bad = 0;
  try {
    for (;;) {
      const it = UPq[kind].find(x => x.state === "wait");
      if (!it) break;
      it.state = "send";
      drawUploads();
      await upSendOne(kind, it);
      delete it.xhr;
      if (it.state === "fail") bad++; else sent++;
      drawUploads();
    }
  } finally { UPrun[kind] = false; drawUploads(); }
  if (sent || bad) toast((UP_NAMES[kind]) + ": " + sent + " sent" + (bad ? ", " + bad + " failed (see the list)" : "") + ".", !!bad && !sent);
}
function upStop(kind) {
  for (const it of UPq[kind]) { if (it.state === "wait") { it.state = "fail"; it.msg = "Stopped"; } else if (it.xhr) it.xhr.abort(); }
  drawUploads();
}
function upClear(kind) { UPq[kind] = UPq[kind].filter(x => x.state === "wait" || x.state === "send"); drawUploads(); }

function upList(kind) {
  const q = UPq[kind];
  if (!q.length) return null;
  const done = q.filter(x => x.state === "done" || x.state === "dup").length, bad = q.filter(x => x.state === "fail").length, running = UPrun[kind];
  const sumEl = h("span", {}, done + " of " + q.length + " done" + (bad ? ", " + bad + " failed" : ""));
  return h("div", { class: "uplist" },
    h("div", { class: "row tight" }, sumEl, h("span", { class: "grow" }),
      running ? h("button", { class: "small danger", onclick: () => upStop(kind) }, "Stop") : h("button", { class: "small", onclick: () => upClear(kind) }, "Clear the List")),
    h("div", { class: "upitems" }, q.map(it => {
      it.barEl = null; it.pctEl = null;
      const label = { wait: "Waiting", send: "Sending", done: "Sent", dup: "Already in Immich", fail: it.msg }[it.state];
      it.pctEl = it.state === "send" ? h("span", { class: "muted small" }, it.pct + "%") : null;
      it.barEl = it.state === "send" ? h("i", { style: { width: it.pct + "%" } }) : null;
      return h("div", { class: "upit " + it.state },
        h("span", { class: "n" }, it.file.name),
        h("span", { class: "s" + (it.state === "fail" ? " badtext" : " muted") }, it.state === "send" ? it.pctEl : label + (it.state !== "fail" && it.msg ? " (" + it.msg + ")" : "")),
        it.state === "send" ? h("div", { class: "bar" }, it.barEl) : null);
    })));
}
function upZone(kind, accept, title, hint) {
  const input = h("input", { type: "file", multiple: true, accept, hidden: true, "aria-label": title, onchange: e => { const fs = [...e.target.files]; e.target.value = ""; if (fs.length) upAdd(kind, fs); } });
  const zone = h("div", { class: "upzone", role: "button", tabindex: "0", onclick: () => input.click(),
    onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } },
    ondragover: e => { e.preventDefault(); zone.classList.add("over"); }, ondragleave: () => zone.classList.remove("over"),
    ondrop: e => { e.preventDefault(); zone.classList.remove("over"); const fs = [...(e.dataTransfer ? e.dataTransfer.files : [])]; if (fs.length) upAdd(kind, fs); } },
  h("b", {}, title), h("span", { class: "muted small" }, hint), input);
  return zone;
}
function upPhotoBox() {
  const im = UP.immich;
  const key = h("input", { type: "password", autocomplete: "new-password", maxlength: 200, "aria-label": "Immich API key", placeholder: "Paste the Immich API key" });
  const msg = h("p", { class: "badtext small", role: "alert" });
  const save = async () => {
    put(msg, "");
    try { const r = await api("POST", "/api/upload/immich-key", { key: key.value }); toast(r.message); await loadUploads(); } catch (e) { put(msg, e.message); }
  };
  const link = "https://" + location.hostname + ":1002/user-settings?isOpen=api-keys";
  return h("div", { class: "upbox" },
    h("div", { class: "ph" }, h("div", { class: "pt" }, h("h3", {}, "Photos and Videos"), h("span", { class: "sub" }, "Go to Immich")),
      h("span", { class: "pill " + (!im.up ? "bad" : im.configured ? "ok" : "warn") }, !im.up ? "Immich is not answering" : im.configured ? "Ready" : "Needs a key")),
    im.configured ? upZone("photo", "image/*,video/*,.heic,.heif,.dng,.arw,.cr2,.cr3,.nef,.orf,.raf,.rw2,.mkv,.mts,.m2ts", "Drop photos and videos here, or press to choose",
      "Any size. Sent one at a time. Photos Immich already has are skipped.") :
      h("div", { class: "upkey" },
        h("p", { class: "small" }, "Immich needs a key before the panel may add photos for you. In Immich open Account Settings, API Keys, make a new key (allow uploading) and paste it here once. It is kept in a private file on the server and never shown again."),
        h("p", { class: "small" }, h("a", { href: link, target: "_blank", rel: "noopener" }, "Open Immich's API Keys page")),
        h("div", { class: "row tight" }, key, h("button", { class: "small primary", onclick: save }, "Save the Key")), msg),
    upList("photo"),
    im.configured ? h("button", { class: "small link", onclick: async () => { if (await confirmBox("Forget the Immich key?", "The panel stops uploading to Immich until you paste a key again. The key itself stays in Immich.", "Forget It", true)) { try { await api("POST", "/api/upload/immich-key", { key: "" }); await loadUploads(); } catch (e) { fail(e); } } } }, "Forget the Immich key") : null);
}
function upSongBox() {
  const m = UP.music, usable = m.exists && m.writable;
  return h("div", { class: "upbox" },
    h("div", { class: "ph" }, h("div", { class: "pt" }, h("h3", {}, "Songs"), h("span", { class: "sub" }, "Saved in " + m.dir + " (Navidrome plays them, Downtify saves there too)")),
      h("span", { class: "pill " + (usable ? "ok" : "bad") }, usable ? "Ready" : m.exists ? "Cannot write there" : "Folder not found")),
    usable ? upZone("song", "audio/*,.flac,.m4a,.opus,.ogg,.wma,.alac,.aiff,.ape,.wv", "Drop songs here, or press to choose",
      "Saved as they are. A song with the same name is never replaced. Navidrome adds new songs at its next scan (within the hour).") :
      h("p", { class: "warntext small" }, m.exists ? "The panel is not allowed to write in that folder." : "That folder is not there. Is the music drive connected?"),
    !usable && m.exists ? h("p", { class: "muted small" }, "To allow it, run this once on the server (it only adds this user to that folder; nothing else changes):") : null,
    !usable && m.exists ? h("code", { class: "upcmd" }, "sudo setfacl -m u:" + (m.user || "USER") + ":rwx " + upQuote(m.dir)) : null,
    typeof m.free === "number" ? h("span", { class: "muted small" }, humanBytes(m.free) + " free there") : null,
    upList("song"));
}
function upQuote(t) { return /^[A-Za-z0-9_\/.@%+=:,-]+$/.test(t) ? t : "'" + t.replace(/'/g, "'\\''") + "'"; }

function drawUploads() {
  const body = [h("div", { class: "ph" }, h("div", { class: "pt" }, h("h2", {}, "Upload"), h("span", { class: "sub" }, "Send photos and videos to Immich, and songs to your music folder, from this device. Keep this page open while files are being sent.")),
    h("button", { class: "small", disabled: upBusy(), onclick: loadUploads }, "Refresh"))];
  if (UPerr) body.push(h("p", { class: "badtext", role: "alert" }, UPerr), h("button", { class: "small", onclick: loadUploads }, "Try Again"));
  else if (!UP) body.push(h("p", { class: "muted" }, "Looking at Immich and the music folder..."));
  else body.push(h("div", { class: "upgrid" }, upPhotoBox(), upSongBox()));
  put(upBox, h("div", { class: "card" }, body));
}

// ---------------------------------------------------------------- Backups (the last section of the Drives tab)
// Tasks that copy a folder to a drive, another computer or the cloud on a schedule, with versions to go back to. The panel only asks the backup tool
// (/api/backup/...) and shows what it says; a run, a preview and a restore go on in the background and the page follows them.
let BK = null, BKerr = "", BKjob = null, BKtimer = 0, BKwas = "";
const bkBox = h("div", { class: "bk" });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const BK_KIND = { local: "Drive", ssh: "Another computer", cloud: "Cloud" };
const BK_WORKING = { run: "Backing up...", dry: "Checking what would be copied...", restore: "Restoring..." };
const KEEP_LABELS = [["hourly", "Hourly"], ["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["yearly", "Yearly"]];

function bkWhen(s) {      // "2026-03-14 02:00" -> "Mar 14, 02:00"
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)$/.exec(s || "");
  return m ? MONTHS[+m[2] - 1] + " " + (+m[3]) + ", " + m[4] : (s || "");
}
function bkDestText(d) {
  if (d.type === "ssh") return d.host + ":" + d.path;
  if (d.type === "cloud") return d.remote + ":" + (d.path || "");
  return d.path;
}
function bkKeepText(t) {
  if (t.dest.type === "cloud" || t.kind === "nightly") return "Files you delete or replace are kept for " + (t.keep.days || 30) + " days";
  const parts = KEEP_LABELS.filter(([k]) => t.keep[k] > 0).map(([k, l]) => t.keep[k] + " " + l.toLowerCase());
  return parts.length ? parts.join(", ") + " (newest version of each)" : "";
}
async function loadBackups() {
  try { BK = await api("GET", "/api/backup"); BKerr = ""; } catch (e) { BK = null; BKerr = e.message; }
  drawBackups();
}
function followBackup() {
  clearTimeout(BKtimer);
  const tick = async () => {
    if (!bkBox.isConnected) return;      // (the person left the Drives tab; viewDrives looks again when they come back)
    let j;
    try { j = await api("GET", "/api/backup/job"); } catch (e) { BKtimer = setTimeout(tick, 3000); return; }
    if (j.running) { BKjob = j; drawBackups(); BKtimer = setTimeout(tick, 1500); return; }
    BKjob = null;
    const said = BKwas;
    BKwas = "";
    await loadBackups();
    if (said || j.rc) toast(j.message || "Done.", !!j.rc);
  };
  tick();
}
async function bkStart(action, body) {
  if ((BKjob && BKjob.running) || DRbusy) return;
  try {
    await api("POST", "/api/backup/" + action, body);
    BKjob = { running: true, action, task: body.id, lines: [], pct: null };
    BKwas = action;
    drawBackups();
    followBackup();
  } catch (e) { fail(e); }
}
function bkBusy() { return !!(BKjob && BKjob.running) || !!(BK && BK.running) || !!DRbusy; }

function bkStatus(t) {
  const mine = BKjob && BKjob.running && BKjob.task === t.id;
  if (mine) return h("span", { class: "pill warn" }, BK_WORKING[BKjob.action] || "Working...");
  if (t.running) return h("span", { class: "pill warn" }, "Running now");
  if (!t.enabled) return h("span", { class: "pill dim" }, "Off");
  if (!t.last) return h("span", { class: "pill dim" }, "Never run");
  return t.last.result === "OK" ? h("span", { class: "pill ok" }, "Last run OK, " + bkWhen(t.last.when)) : h("span", { class: "pill bad" }, "Last run failed, " + bkWhen(t.last.when));
}
function bkTask(t) {
  const mine = BKjob && BKjob.running && BKjob.task === t.id ? BKjob : null;
  const off = bkBusy();
  const nightly = t.kind === "nightly";
  const last = t.last;
  const rows = [
    h("div", { class: "bkline" }, h("span", { class: "k" }, "From"), h("span", { class: "v" }, t.source)),
    h("div", { class: "bkline" }, h("span", { class: "k" }, "To"), h("span", { class: "v" }, bkDestText(t.dest))),
    h("div", { class: "bkline" }, h("span", { class: "k" }, "When"), h("span", { class: "v" }, t.schedule_text + (t.enabled && t.next_run ? ". Next: " + bkWhen(t.next_run) : ""))),
    bkKeepText(t) ? h("div", { class: "bkline" }, h("span", { class: "k" }, "Keeps"), h("span", { class: "v" }, bkKeepText(t))) : null,
    last && typeof last.size_bytes === "number" ? h("div", { class: "bkline" }, h("span", { class: "k" }, "Space used"), h("span", { class: "v" }, humanBytes(last.size_bytes) + " in all versions together")) : null,
    last && last.message ? h("div", { class: "bkline" }, h("span", { class: "k" }, "Last run"), h("span", { class: "v " + (last.result === "OK" ? "" : "badtext") }, last.message)) : null];
  const prog = mine ? h("div", { class: "bkprog" },
    h("div", { class: "bar" + (typeof mine.pct === "number" ? "" : " wait") }, h("i", { style: { width: (typeof mine.pct === "number" ? mine.pct : 100) + "%" } })),
    h("span", { class: "muted small" }, (mine.lines || []).slice(-1)[0] || BK_WORKING[mine.action])) : null;
  return h("div", { class: "bkt" + (t.enabled ? "" : " isoff") },
    h("div", { class: "ph" },
      h("div", { class: "pt" }, h("h3", {}, t.name), h("span", { class: "sub" }, nightly ? "The nightly backup of your files" : BK_KIND[t.dest.type])),
      bkStatus(t)),
    h("div", { class: "bklines" }, rows),
    prog,
    h("div", { class: "row tight" },
      h("button", { class: "small primary", disabled: off, onclick: () => bkStart("run", { id: t.id }) }, "Run Now"),
      nightly ? null : h("button", { class: "small", disabled: off, onclick: () => bkStart("dry", { id: t.id }), title: "Shows how much would be copied. Nothing is changed" }, "Preview"),
      h("button", { class: "small", disabled: off, onclick: () => bkRestore(t) }, "Restore"),
      t.dest.type === "local" ? h("button", { class: "small", onclick: () => bkDownload(t), title: "Download files or folders of this backup to this device (for when you have no other way to get your files)" }, "Download") : null,
      h("button", { class: "small", onclick: () => bkEdit(t) }, "Edit"),
      h("button", { class: "small", onclick: () => bkToggle(t) }, t.enabled ? "Turn Off" : "Turn On"),
      nightly ? null : h("button", { class: "small danger", disabled: off, onclick: () => bkDelete(t) }, "Delete")));
}
function drawBackups() {
  const off = bkBusy();
  const body = [h("div", { class: "ph" },
    h("div", { class: "pt" }, h("h2", {}, "Backups"), h("span", { class: "sub" }, "Copy a folder to a drive, another computer or the cloud on a schedule. Every run keeps a version you can go back to.")),
    h("button", { class: "small", onclick: loadBackups }, "Refresh"),
    h("button", { class: "small primary", disabled: !BK || off, onclick: () => bkEdit(null) }, "New Backup Task"))];
  if (BKerr) body.push(h("p", { class: "badtext", role: "alert" }, BKerr), h("button", { class: "small", onclick: loadBackups }, "Try Again"));
  else if (!BK) body.push(h("p", { class: "muted" }, "Looking at the backups..."));
  else body.push(h("div", { class: "bkl" }, BK.tasks.map(bkTask)));
  put(bkBox, h("div", { class: "card" }, body));
}
async function bkToggle(t) {
  try { await api("POST", "/api/backup/toggle", { id: t.id, enabled: !t.enabled }); await loadBackups(); } catch (e) { fail(e); }
}
function bkDelete(t) {
  const d = h("dialog", {}, h("h2", {}, "Delete " + t.name + "?"),
    h("p", {}, "The task stops running. You can keep the copies it already made (they stay where they are, and you can delete them yourself), or erase them now."),
    h("p", { class: "muted small" }, "Your original files are never touched."),
    h("div", { class: "actions" },
      h("button", { onclick: () => d.close() }, "Cancel"),
      h("button", { onclick: () => go("keep") }, "Delete Task, Keep Copies"),
      h("button", { class: "danger", onclick: () => go("erase") }, "Delete Task and Erase Copies")));
  const go = async data => {
    d.close();
    try { await api("POST", "/api/backup/delete", { id: t.id, data }); toast("The task was deleted."); await loadBackups(); } catch (e) { fail(e); }
  };
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
}

// ---- the setup dialog (new task or edit)
function bkNew() {
  return { name: "", enabled: true, kind: "versions", source: "", exclude: [], dest: { type: "local", path: "" }, schedule: { kind: "daily", time: "02:00" }, keep: { hourly: 0, daily: 7, weekly: 4, monthly: 6, yearly: 1 } };
}
function bkField(label, input, hint) { return h("div", { class: "field" }, h("label", {}, label), input, hint ? h("span", { class: "hint" }, hint) : null); }
function bkNum(f, k, label) {
  return h("div", { class: "field bknum" }, h("label", {}, label), h("input", { type: "number", min: 0, max: 90, value: f.keep[k] || 0, "aria-label": label + " versions to keep", oninput: e => { f.keep[k] = Math.max(0, parseInt(e.target.value, 10) || 0); } }));
}
function bkEdit(t) {
  const f = t ? clone(t) : bkNew();
  const nightly = f.kind === "nightly";
  const err = h("p", { class: "badtext", role: "alert" });
  const where = h("div", {});
  const when = h("div", {});
  const keep = h("div", {});
  let keyInfo = null;
  const setErr = m => { put(err, m || ""); };
  const drawWhere = () => {
    const d = f.dest;
    const pick = BK.drives.length ? h("div", { class: "field" }, h("select", { "aria-label": "Choose a connected drive", onchange: e => { if (e.target.value) { d.path = e.target.value.replace(/\/$/, "") + "/backups"; drawWhere(); } } },
      h("option", { value: "" }, "Pick a connected drive to fill in the folder..."),
      BK.drives.map(x => h("option", { value: x.path }, x.path + "  (" + humanBytes(x.free) + " free of " + humanBytes(x.size) + ")")))) : null;
    const types = h("select", { "aria-label": "Where the copies go", onchange: e => {
      const ty = e.target.value;
      f.dest = ty === "local" ? { type: "local", path: "" } : ty === "ssh" ? { type: "ssh", host: "", path: "" } : { type: "cloud", remote: (BK.cloud.remotes || [])[0] || "", path: "homelab-backups" };
      f.keep = ty === "cloud" ? { days: 30 } : { hourly: 0, daily: 7, weekly: 4, monthly: 6, yearly: 1 };
      drawWhere(); drawKeep();
    } }, Object.entries(BK_KIND).map(([k, v]) => h("option", { value: k, selected: d.type === k }, k === "local" ? "A drive connected to this machine" : k === "ssh" ? "Another computer (over Tailscale or the network)" : "The cloud (Google Drive, Backblaze, ...)")));
    const kids = [bkField("Where should the copies go?", types)];
    if (d.type === "local") {
      kids.push(pick, bkField("Folder for the copies", h("input", { type: "text", value: d.path, placeholder: "/mnt/backup/homelab-backups", maxlength: 300, oninput: e => { d.path = e.target.value.trim(); } }),
        "Each task makes its own folder inside it, with one dated folder per version. The folder must be on a connected drive."));
    } else if (d.type === "ssh") {
      kids.push(bkField("The other computer", h("input", { type: "text", value: d.host, placeholder: "user@computer.your-tailnet.ts.net", maxlength: 300, oninput: e => { d.host = e.target.value.trim(); } }), "The account to log in with. Add :2222 at the end for another port."),
        bkField("Folder on that computer", h("input", { type: "text", value: d.path, placeholder: "/home/user/homelab-backups", maxlength: 300, oninput: e => { d.path = e.target.value.trim(); } })),
        h("div", { class: "row tight" },
          h("button", { class: "small", onclick: showKey }, "Show the Key"),
          h("button", { class: "small", onclick: testSsh }, "Test the Connection")),
        keyInfo || (BK.ssh.key ? null : h("p", { class: "muted small" }, "First press Show the Key, add it on the other computer, then test the connection.")),
        h("p", { class: "muted small" }, "The other computer needs rsync installed and must accept this machine's key."));
    } else {
      const remotes = BK.cloud.remotes || [];
      if (!BK.cloud.installed) kids.push(h("p", { class: "warntext" }, "The tool for the cloud (rclone) is not installed on this machine. Install it first: sudo apt install rclone"));
      kids.push(remotes.length ? bkField("Cloud account", h("select", { "aria-label": "Cloud account", onchange: e => { d.remote = e.target.value; } }, remotes.map(r => h("option", { value: r, selected: d.remote === r }, r)))) :
        h("p", { class: "muted" }, "No cloud account is set up yet. Add a Backblaze B2 or S3 account below, or set up Google Drive, OneDrive, Dropbox and others once in the Terminal card with: sudo rclone config (it asks you to log in through your browser). Then press Refresh."),
        bkField("Folder in the cloud", h("input", { type: "text", value: d.path, maxlength: 200, oninput: e => { d.path = e.target.value.trim().replace(/^\/+/, ""); } })),
        cloudAdd(),
        h("p", { class: "muted small" }, "The cloud keeps the latest copy plus the older versions of files that changed or were deleted, for the number of days you choose. It does not keep a full copy for every run."));
    }
    put(where, kids);
  };
  const cloudAdd = () => {
    const v = { type: "b2", name: "", key_id: "", key: "", endpoint: "" };
    const note = h("p", { class: "muted small" });
    return h("details", { class: "bkmore" }, h("summary", {}, "Add a Backblaze B2 or S3 account"),
      bkField("Kind", h("select", { "aria-label": "Kind of account", onchange: e => { v.type = e.target.value; } }, h("option", { value: "b2" }, "Backblaze B2"), h("option", { value: "s3" }, "S3 (Amazon or compatible)"))),
      bkField("Name for this account", h("input", { type: "text", maxlength: 32, placeholder: "b2", oninput: e => { v.name = e.target.value.trim(); } })),
      bkField("Key ID", h("input", { type: "text", autocomplete: "off", maxlength: 200, oninput: e => { v.key_id = e.target.value.trim(); } })),
      bkField("Application Key", h("input", { type: "password", autocomplete: "new-password", maxlength: 200, oninput: e => { v.key = e.target.value.trim(); } }), "It is saved in a file only the administrator of this machine can read."),
      bkField("Address of the service (S3 only, optional)", h("input", { type: "text", maxlength: 200, placeholder: "https://s3.example.com", oninput: e => { v.endpoint = e.target.value.trim(); } })),
      note,
      h("button", { class: "small", onclick: async () => {
        try {
          await api("POST", "/api/backup/cloud-add", v);
          await loadBackups();
          f.dest.remote = v.name;
          drawWhere();
        } catch (e) { put(note, e.message); note.className = "badtext small"; }
      } }, "Add the Account"));
  };
  const showKey = async () => {
    try {
      const r = await api("POST", "/api/backup/sshkey", {});
      const line = r.key;
      const box = h("textarea", { readonly: true, rows: 3, "aria-label": "The public key", onfocus: e => e.target.select() }, line);
      keyInfo = h("div", { class: "bkkey" }, h("p", { class: "small" }, "Add this line to the file ~/.ssh/authorized_keys of the account you log in with on the other computer:"), box,
        h("button", { class: "small", onclick: async () => { try { await navigator.clipboard.writeText(line); toast("Copied."); } catch (e) { box.focus(); box.select(); } } }, "Copy"));
      drawWhere();
    } catch (e) { setErr(e.message); }
  };
  const testSsh = async () => {
    setErr("");
    try { const r = await api("POST", "/api/backup/sshtest", { host: f.dest.host }); toast("It works: " + r.message); } catch (e) { setErr(e.message); }
  };
  const drawWhen = () => {
    const s = f.schedule;
    const kind = h("select", { "aria-label": "How often", onchange: e => {
      const k = e.target.value;
      f.schedule = k === "hourly" ? { kind: k, minute: 0 } : k === "weekly" ? { kind: k, dow: 6, time: s.time || "02:00" } : k === "monthly" ? { kind: k, dom: 1, time: s.time || "02:00" } : k === "days" ? { kind: k, every: 3, time: s.time || "02:00" } : { kind: k, time: s.time || "02:00" };
      drawWhen();
    } }, [["hourly", "Every hour"], ["daily", "Every day"], ["days", "Every few days"], ["weekly", "Every week"], ["monthly", "Every month"]].map(([k, l]) => h("option", { value: k, selected: s.kind === k }, l)));
    const kids = [kind];
    if (s.kind === "days") kids.push(h("label", { class: "inl" }, "every ", h("input", { type: "number", min: 2, max: 30, value: s.every || 3, "aria-label": "Number of days between backups",
      oninput: e => { s.every = Math.max(2, Math.min(30, parseInt(e.target.value, 10) || 3)); delete s.from; } }), " days"));      // (a new number counts from the day it is saved)
    if (s.kind === "weekly") kids.push(h("select", { "aria-label": "Day of the week", onchange: e => { s.dow = +e.target.value; } }, WEEKDAYS.map((n, i) => h("option", { value: i, selected: s.dow === i }, n))));
    if (s.kind === "monthly") kids.push(h("select", { "aria-label": "Day of the month", onchange: e => { s.dom = +e.target.value; } }, Array.from({ length: 28 }, (_, i) => h("option", { value: i + 1, selected: s.dom === i + 1 }, "Day " + (i + 1)))));
    if (s.kind === "hourly") kids.push(h("label", { class: "inl" }, "at minute ", h("input", { type: "number", min: 0, max: 59, value: s.minute || 0, "aria-label": "Minute of the hour", oninput: e => { s.minute = Math.max(0, Math.min(59, parseInt(e.target.value, 10) || 0)); } })));
    else kids.push(h("label", { class: "inl" }, "at ", h("input", { type: "time", value: s.time || "02:00", "aria-label": "Time of day", oninput: e => { s.time = e.target.value || "02:00"; } })));
    put(when, h("div", { class: "field" }, h("label", {}, "When should it run?"), h("div", { class: "row tight" }, kids)));
  };
  const drawKeep = () => {
    if (f.dest.type === "cloud") {
      put(keep, bkField("How long to keep older versions of changed files", h("input", { type: "number", min: 1, max: 3650, value: (f.keep.days || 30), "aria-label": "Days", oninput: e => { f.keep = { days: Math.max(1, parseInt(e.target.value, 10) || 30) }; } }), "In days. The latest copy always stays."));
      return;
    }
    put(keep, h("div", { class: "field" }, h("label", {}, "Versions to keep"), h("div", { class: "row tight bkkeep" }, KEEP_LABELS.map(([k, l]) => bkNum(f, k, l))),
      h("span", { class: "hint" }, "For example Daily 7 keeps the newest version of each of the last 7 days. Older versions are removed automatically. Versions share the files that did not change, so they take little extra space.")));
  };
  const form = [h("h2", {}, t ? "Edit " + t.name : "New Backup Task"),
    bkField("Name", h("input", { type: "text", value: f.name, maxlength: 40, placeholder: "My documents", oninput: e => { f.name = e.target.value; } }))];
  if (nightly) {
    form.push(h("p", { class: "muted" }, "This is the nightly backup of " + f.source + " to " + f.dest.path + ". You can rename it, turn it off, change when it runs and how long it keeps files you delete or replace."), when,
      bkField("Keep files that are deleted or replaced for how many days?",
        h("input", { type: "number", min: 1, max: 3650, value: (f.keep && f.keep.days) || 30, "aria-label": "Days to keep deleted or replaced files", oninput: e => { f.keep = { days: Math.max(1, Math.min(3650, parseInt(e.target.value, 10) || 30)) }; } }),
        "The default is 30 days. When a file is deleted or changed, the older copy stays in the backup for this long, and is then removed to free space. A longer time needs more room on the backup drive."));
  } else {
    form.push(bkField("Folder to back up", h("input", { type: "text", value: f.source, placeholder: "/mnt/storage/photos", maxlength: 300, list: "bk-src", oninput: e => { f.source = e.target.value.trim(); } }), "The full path of the folder on this machine."),
      h("datalist", { id: "bk-src" }, BK.drives.map(x => h("option", { value: x.path }))),
      where, when, keep,
      h("details", { class: "bkmore" }, h("summary", {}, "Skip some files (optional)"),
        h("div", { class: "field" }, h("textarea", { rows: 3, "aria-label": "Files and folders to skip, one per line", placeholder: "*.tmp\ncache/", value: (f.exclude || []).join("\n"), oninput: e => { f.exclude = e.target.value.split("\n").map(x => x.trim()).filter(Boolean); } }),
          h("span", { class: "hint" }, "One pattern per line, like *.tmp or cache/. Skipped files are not copied."))));
  }
  const d = h("dialog", { class: "wide dcard bkdlg" }, form, err,
    h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Cancel"),
      h("button", { class: "primary", onclick: async () => {
        setErr("");
        const out = { id: f.id, name: f.name, enabled: f.enabled, schedule: f.schedule };
        if (!nightly) Object.assign(out, { source: f.source, exclude: f.exclude, dest: f.dest, keep: f.keep });
        else out.keep = { days: (f.keep && f.keep.days) || 30 };
        if (!t) delete out.id;
        try { await api("POST", "/api/backup/save", out); d.close(); toast("Saved."); await loadBackups(); } catch (e) { setErr(e.message); }
      } }, "Save")));
  if (!nightly) { drawWhere(); drawKeep(); }
  drawWhen();
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
}

// ---- the download dialog: look inside a backup and save a file, or a folder as a .zip, to this device (for when there is no other way to get the files)
async function bkDownload(t) {
  let versions;
  try { versions = (await api("GET", "/api/backup/versions?id=" + encodeURIComponent(t.id))).versions; } catch (e) { fail(e); return; }
  if (!versions.length) { toast("There is nothing to download yet. Run the backup first.", true); return; }
  let ver = versions[0], path = [];
  const list = h("div", { class: "bklist" });
  const crumbs = h("div", { class: "bkcrumbs" });
  const note = h("p", { class: "muted small" });
  const err = h("p", { class: "badtext", role: "alert" });
  const rel = () => path.join("/") || ".";
  const go = async p => {
    path = p;
    put(err, "");
    let entries = [];
    try { entries = (await api("GET", "/api/backup/browse?id=" + encodeURIComponent(t.id) + "&v=" + encodeURIComponent(ver.name) + "&rel=" + encodeURIComponent(rel()))).entries; } catch (e) { put(err, e.message); }
    put(crumbs, h("button", { class: "small link", onclick: () => go([]) }, "Top"), path.map((n, i) => [" / ", h("button", { class: "small link", onclick: () => go(path.slice(0, i + 1)) }, n)]));
    put(note, ver.kind === "changes" ? "This version holds only the files that were replaced or deleted at that time." : "");
    put(list, entries.length ? entries.map(e => h("div", { class: "item" },
      h("div", { class: "txt" }, e.type === "dir" ? h("button", { class: "small link", onclick: () => go(path.concat(e.name)) }, "\uD83D\uDCC1 " + e.name) : h("b", {}, e.name), e.type === "file" ? h("span", {}, humanBytes(e.size)) : null),
      h("button", { class: "small", onclick: () => fetchOut(path.concat(e.name).join("/"), e.type === "dir" ? "zip" : "file") }, e.type === "dir" ? "Download .zip" : "Download"))) : h("p", { class: "muted" }, "Nothing in this folder."));
  };
  const fetchOut = async (r, mode) => {
    put(err, "");
    try {
      const j = await api("POST", "/api/backup/dltoken", { id: t.id, v: ver.name, rel: r, mode });
      const a = h("a", { href: j.url, target: "_blank", rel: "noopener" });      // (a link opens it: the browser saves the stream as it arrives, nothing is held in memory)
      document.body.append(a); a.click(); a.remove();
      toast(mode === "zip" ? "The .zip is on its way. A big folder takes a while: the download starts at once and runs until it is done." : "The download has started.");
    } catch (e) { put(err, e.message); }
  };
  const d = h("dialog", { class: "wide dcard bkdlg" }, h("h2", {}, "Download from " + t.name),
    h("p", { class: "muted small" }, "Saves a file, or a whole folder as one .zip, to this device. Use it when you have no other way to get your files back. The zip of a big folder has no size shown while it downloads. Keep this page open until the browser says it is done."),
    h("div", { class: "field" }, h("label", {}, "Which version?"),
      h("select", { "aria-label": "Version", onchange: e => { ver = versions.find(v => v.name === e.target.value); go([]); } }, versions.map(v => h("option", { value: v.name }, v.label)))),
    note, crumbs, list, err,
    h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Close"), h("button", { class: "primary", onclick: () => fetchOut(rel(), "zip") }, "Download This Folder as .zip")));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  go([]);
}

// ---- the restore dialog: pick a version, look inside, bring back a file or a folder
async function bkRestore(t) {
  let versions;
  try { versions = (await api("GET", "/api/backup/versions?id=" + encodeURIComponent(t.id))).versions; } catch (e) { fail(e); return; }
  if (!versions.length) { toast("There is nothing to restore yet. Run the backup first.", true); return; }
  let ver = versions[0], path = [], target = "folder";
  const list = h("div", { class: "bklist" });
  const crumbs = h("div", { class: "bkcrumbs" });
  const note = h("p", { class: "muted small" });
  const err = h("p", { class: "badtext", role: "alert" });
  const rel = () => path.join("/") || ".";
  const go = async p => {
    path = p;
    put(err, "");
    let entries = [];
    try { entries = (await api("GET", "/api/backup/browse?id=" + encodeURIComponent(t.id) + "&v=" + encodeURIComponent(ver.name) + "&rel=" + encodeURIComponent(rel()))).entries; } catch (e) { put(err, e.message); }
    put(crumbs, h("button", { class: "small link", onclick: () => go([]) }, "Top"), path.map((n, i) => [" / ", h("button", { class: "small link", onclick: () => go(path.slice(0, i + 1)) }, n)]));
    put(note, ver.kind === "changes" ? "This version holds only the files that were replaced or deleted at that time." : "");
    put(list, entries.length ? entries.map(e => h("div", { class: "item" },
      h("div", { class: "txt" }, e.type === "dir" ? h("button", { class: "small link", onclick: () => go(path.concat(e.name)) }, "\uD83D\uDCC1 " + e.name) : h("b", {}, e.name), e.type === "file" ? h("span", {}, humanBytes(e.size)) : null),
      h("button", { class: "small", onclick: () => doRestore(path.concat(e.name).join("/")) }, "Restore"))) : h("p", { class: "muted" }, "Nothing in this folder."));
  };
  const doRestore = async r => {
    if (target === "original" && !(await confirmBox("Put the files back over the originals?", "Files with the same name in " + t.source + " will be replaced by the ones from this version. What they replace is kept in the _restored folder next to them.", "Replace the Files", true))) return;
    d.close();
    bkStart("restore", { id: t.id, version: ver.name, rel: r, target });
  };
  const d = h("dialog", { class: "wide dcard bkdlg" }, h("h2", {}, "Restore from " + t.name),
    h("div", { class: "field" }, h("label", {}, "Which version?"),
      h("select", { "aria-label": "Version", onchange: e => { ver = versions.find(v => v.name === e.target.value); go([]); } }, versions.map(v => h("option", { value: v.name }, v.label)))),
    note, crumbs, list,
    h("div", { class: "field" }, h("label", {}, "Where should the files go?"),
      h("label", { class: "inl" }, h("input", { type: "radio", name: "bk-target", checked: true, onchange: () => { target = "folder"; } }), " Into a new folder next to the originals (safe, nothing is replaced)"),
      h("label", { class: "inl" }, h("input", { type: "radio", name: "bk-target", onchange: () => { target = "original"; } }), " Over the original files (they are replaced; the old ones are kept)")),
    err,
    h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Close"), h("button", { class: "primary", onclick: () => doRestore(rel()) }, "Restore Everything Shown Here")));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  go([]);
}

// ---------------------------------------------------------------- Look and Colors (one look, two screens)
function rgb(hex) { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ""); const n = m ? parseInt(m[1], 16) : 0; return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
let lookBarEl = null, pvTimer = null, pvSeq = 0;

function lookOut() {                       // what is sent to the server: the look, with only the tab colors that differ from the shipped ones
  const out = clone(lookW);
  out.tabs = {};
  for (const [n, c] of Object.entries(lookW.tabs)) if (c !== S.look.defaults.tabs[n]) out.tabs[n] = c;
  return out;
}
function rimShadow(level) {                // the same shine as the server writes (--lk-rim)
  const r = Math.max(0, Math.min(100, Number(level) || 0)) / 100;
  if (r <= 0) return "0 0 0 0 transparent";
  const n = x => String(Math.round(x * 1000) / 1000);
  return "inset 1px 1px 0 rgba(255,255,255," + n(0.7 * r) + "), inset -1px -1px 0 rgba(255,255,255," + n(0.32 * r) + "), inset 0 0 " + Math.round(10 + 14 * r) + "px rgba(255,255,255," + n(0.12 * r) + "), inset 0 12px 18px -14px rgba(255,255,255," + n(0.3 * r) + ")";
}
function glassAlpha(v) { if (v.glassTint === false) return 0; return v.glassClear ? 0.4 * (1 - v.glassLevel / 100) : v.glassOpacity / 100; }
function lookPreview(quiet) {
  const p = document.getElementById("mock");
  if (p) {
    p.style.setProperty("--pc", rgb(lookW.accent).join(", "));
    p.style.setProperty("--pg", rgb(lookW.glass).join(", "));
    p.style.setProperty("--pa", glassAlpha(lookW));
    p.style.setProperty("--pr", Math.min(lookW.radius, 30) + "px");
    p.style.setProperty("--pe", lookW.edge / 100);
    p.style.setProperty("--pbl", Math.round(lookW.glassBlur * 0.6) + "px");
    p.style.setProperty("--prm", rimShadow(lookW.glassRim));
  }
  applyAccent();
  if (quiet) return;
  send({ type: "names", names: lookW.names || {}, logo: (lookW.logo && !lookW.logo.off) ? lookW.logo : {} });       // the names and the logo do not go through the CSS of the preview
  clearTimeout(pvTimer);                    // the server writes the rules, so the preview is exactly what Save keeps
  pvTimer = setTimeout(async () => {
    const n = ++pvSeq;
    try { const r = await api("POST", "/api/look/css", { look: lookOut() }); if (n === pvSeq) send({ type: "css", css: r.css }); } catch (e) { /* the next change tries again */ }
  }, 120);
}
function lookDirty() { return !same(lookNorm(lookW), lookNorm(S.look.values)); }
function lookNorm(v) { const o = clone(v); o.tabs = o.tabs || {}; o.names = o.names || {}; o.logo = o.logo || {}; return o; }
function bgDirty() {
  const b = S.background, B = bgW;
  return !!B && (B.url !== "" || B.blur !== (b.blur || "none") || B.saturate !== b.saturate || B.brightness !== b.brightness || B.opacity !== b.opacity);
}
function refreshLookBar() {
  if (!lookBarEl) return;
  put(lookBarEl, saveBar(lookDirty() || bgDirty(), saveLook, () => { discardPreview(); render(); }, "Save",
    h("button", { onclick: resetLook }, "Reset All Settings")));
}
function lookChanged() { lookPreview(); refreshLookBar(); try { sessionStorage.setItem("hlp-draft", JSON.stringify(lookW)); } catch (e) { /* storage may be blocked */ } }
function clearDraft() { try { sessionStorage.removeItem("hlp-draft"); } catch (e) { /* ignore */ } }
// Cards of the other tabs are only on the page while their tab is open, so you look at them on their own tab and come back: the unsaved work is kept for that
function startLook() {
  try {
    const d = JSON.parse(sessionStorage.getItem("hlp-draft") || "null");
    if (d && typeof d === "object") { const l = Object.assign(clone(S.look.values), d); if (!same(lookNorm(l), lookNorm(S.look.values))) return l; }
  } catch (e) { /* no draft */ }
  return clone(S.look.values);
}
async function saveLook() {                // saves what was changed on the Look screen: the look and the background together
  try {
    const both = lookDirty() && bgDirty();
    let restarting = false;
    const bgSaved = bgDirty();
    if (bgSaved) {
      const B = bgW;
      const nums = { blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity };
      if (B.theme && B.url) { toast("Getting the picture of the theme…"); const r = await api("POST", "/api/background/theme", Object.assign({ theme: B.theme }, nums)); restarting = !!r.restarting; }
      else await api("POST", "/api/background", Object.assign({ url: B.url || undefined }, nums));
    }
    if (lookDirty()) {
      clearTimeout(pvTimer); pvSeq++;
      await api("POST", "/api/look", { look: lookOut() });
      clearTimeout(pvTimer); pvSeq++; send({ type: "saved", bg: !!bgSaved });
    }
    const what = both ? "Look and background saved." : (bgDirty() ? "Background saved." : "Look saved.");
    toast(restarting ? what + " The dashboard restarts for about 10 seconds…" : what);
    await afterChange(false);
    if (restarting) setTimeout(() => send({ type: "reload", wait: true }), 4000);      // (the dashboard waits until Homepage answers again, then reloads)
  } catch (e) { fail(e); }
}
async function resetLook() {
  if (!await confirmBox("Reset All Settings?", "The colors, glass, shapes, names, logo and the colors of cards and labels go back to how the dashboard came. Your picture, cards and layout stay as they are. Undo can bring this change back.", "Reset All Settings")) return;
  try { await api("POST", "/api/look/reset", {}); send({ type: "saved" }); toast("All settings are back to the defaults."); await afterChange(false); } catch (e) { fail(e); }
}
function lookSlider(label, key, lo, hi, step, unit, hint) {
  const L = lookW;
  const val = h("span", { class: "val" }, L[key] + unit);
  const inp = h("input", { type: "range", min: lo, max: hi, step, value: L[key], "aria-label": label, oninput: ev => { L[key] = Number(ev.target.value); val.textContent = L[key] + unit; lookChanged(); } });
  return h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, label), val, inp), hint ? h("div", { class: "hint" }, hint) : null);
}
function colorField(label, key, hint, swatches) {
  const L = lookW;
  const hex = h("input", { type: "text", value: L[key], maxlength: 7, "aria-label": label + " (hex code)", style: { maxWidth: "120px" } });
  const pick = h("input", { type: "color", value: L[key], "aria-label": label });
  const set = v => { L[key] = v; hex.value = v; pick.value = v; lookChanged(); };
  pick.addEventListener("input", () => set(pick.value));
  hex.addEventListener("input", () => { const v = hex.value.trim().toLowerCase(); if (/^#[0-9a-f]{6}$/.test(v) && v !== L[key]) { L[key] = v; pick.value = v; lookChanged(); } });      // (a complete code counts at once: Save is ready before the field is left)
  hex.addEventListener("change", () => { const v = hex.value.trim().toLowerCase(); if (/^#[0-9a-f]{6}$/.test(v)) { if (v !== L[key]) set(v); hex.value = v; } else hex.value = L[key]; });      // (nothing is drawn again when the code was already taken: the bar under the mouse keeps its Save button)
  return h("div", { class: "field" }, h("div", { class: "lab" }, label),
    h("div", { class: "row" }, pick, hex, h("div", { class: "swatches" }, (swatches || []).map(c => h("button", { class: "swatch", style: { background: c }, title: c, "aria-label": "Use " + c, onclick: () => set(c) })))),
    hint ? h("div", { class: "hint" }, hint) : null);
}

// ---- Names and Logo (the top card of the Look screen)
const SHIPPED_NAMES = [["homelab", "HomeLab", "Server Name", "The name under the big tile at the top left (and anywhere else it is shown)."],
  ["main", "Main Pool", "Main Pool Name", "The first drive: on its tile at the top and in the Stats tab."],
  ["backup", "Backup Pool", "Backup Pool Name", "The second drive. When it is not plugged in, its tile says “Connect” and then this name, then “Drive”."]];
function shrinkLogo(file) {                  // the picture is made small (256 px) in the browser, so the dashboard loads it fast
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onerror = () => reject(new Error("That file could not be read."));
    fr.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("That file could not be read as a picture. Choose a PNG, JPG, WebP, GIF or SVG file."));
      img.onload = () => {
        const w = img.naturalWidth || 256, ht = img.naturalHeight || 256, big = Math.max(w, ht);
        let scale = file.type === "image/svg+xml" ? 256 / big : Math.min(1, 256 / big);
        for (let i = 0; i < 8; i++) {
          const c = document.createElement("canvas");
          c.width = Math.max(1, Math.round(w * scale)); c.height = Math.max(1, Math.round(ht * scale));
          c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
          const out = c.toDataURL("image/png");
          if (out.length <= 140000) return resolve(out);
          scale *= 0.7;
        }
        reject(new Error("That picture is too detailed to use as a logo. Try a simpler or smaller one."));
      };
      img.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}
// ready-made logos: simple line drawings that are painted in the color you choose and made into a picture (like an uploaded one) when you pick one
const LOGO_ART = [
  ["Server", '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M12 6.5h5M12 17.5h5"/><circle cx="7" cy="6.5" r="1" fill="#C"/><circle cx="7" cy="17.5" r="1" fill="#C"/>'],
  ["House", '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-5.5h4V20"/>'],
  ["Cloud", '<path d="M7 18.5h10.5a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.4 9.1 4.7 4.7 0 0 0 7 18.5z"/>'],
  ["Shield", '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.8 7.5 9 4.3-1.2 7.5-4.5 7.5-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>'],
  ["Bolt", '<path d="M13 2.5 5 13.5h6l-1 8 8-11h-6z"/>'],
  ["Database", '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13"/><path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8"/>'],
  ["Cube", '<path d="M12 2.8 20 7.4v9.2l-8 4.6-8-4.6V7.4z"/><path d="M4 7.4l8 4.6 8-4.6M12 12v9.2"/>'],
  ["Music", '<path d="M9 18V5.5l11-2V16"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>'],
  ["Movie", '<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="m10 9 5 3-5 3z"/>'],
  ["Terminal", '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3M12.5 15H17"/>'],
];
function logoArt(i, color, px) {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="' + px + '" height="' + px + '" fill="none" stroke="' + color + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + LOGO_ART[i][1].replace(/#C/g, color) + "</svg>";
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}
function logoPicture(i, color) {            // the drawing as a PNG (256 px), the same kind of picture as an uploaded one
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onerror = () => reject(new Error("The logo could not be drawn."));
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = c.height = 256;
      c.getContext("2d").drawImage(img, 0, 0, 256, 256);
      resolve(c.toDataURL("image/png"));
    };
    img.src = logoArt(i, color, 256);
  });
}
let logoPick = { i: -1, color: "", src: "" };
function namesCard() {
  const L = lookW;
  L.names = L.names || {}; L.logo = L.logo || {};
  const inputs = SHIPPED_NAMES.map(([key, shipped, label, hint]) => {
    const inp = h("input", { type: "text", maxlength: 24, value: L.names[key] || "", placeholder: shipped, "aria-label": label,
      oninput: ev => { const v = ev.target.value.replace(/\s+/g, " ").trim(); if (v && v !== shipped) L.names[key] = v; else delete L.names[key]; lookChanged(); } });
    return [key, inp, h("div", { class: "field" }, h("div", { class: "lab" }, label), inp, h("div", { class: "hint" }, hint))];
  });
  const now = h("span", { class: "logo-now" }), nowName = h("span", { class: "small muted" });
  const status = h("div", {});                                  // the logo in use, the On/Off button, the link and the size
  const tiles = [];                                             // the ready-made drawings (made once, so an open color picker stays open)
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif,image/svg+xml", hidden: true, onchange: async () => {
    const f = file.files[0]; file.value = "";
    if (!f) return;
    if (f.size > 15 * 1024 * 1024) return toast("That picture is bigger than 15 MB. Choose a smaller one.", true);
    try { L.logo.src = await shrinkLogo(f); delete L.logo.off; logoPick.i = -1; lookChanged(); refresh(); toast("The logo is ready. Press Save to keep it."); } catch (e) { fail(e); }
  } });
  const color = logoPick.color || L.accent;
  LOGO_ART.forEach(([name], i) => tiles.push(h("button", { class: "logo-tile", title: name, "aria-label": "Use the " + name + " logo",
    onclick: async () => {
      try {
        L.logo.src = await logoPicture(i, logoPick.color || L.accent); delete L.logo.off;
        logoPick = { i, color: logoPick.color, src: L.logo.src };
        lookChanged(); refresh(); toast("The logo is ready. Press Save to keep it.");
      } catch (e) { fail(e); }
    } }, h("img", { src: logoArt(i, color, 40), alt: "", width: 40, height: 40 }))));
  const pick = h("input", { type: "color", value: color, "aria-label": "Color of the built-in logos" });
  pick.addEventListener("input", async () => {
    logoPick.color = pick.value;
    tiles.forEach((t, i) => { t.firstChild.src = logoArt(i, pick.value, 40); });
    if (logoPick.i >= 0 && logoPick.src === L.logo.src) {
      try { L.logo.src = await logoPicture(logoPick.i, pick.value); logoPick.src = L.logo.src; lookChanged(); refresh(); } catch (e) { /* the next change tries again */ }
    }
  });
  const url = h("input", { type: "url", placeholder: "https://…", "aria-label": "Address of a logo picture on the web" });
  const menu = h("details", { class: "logo-menu" },
    h("summary", {}, now, h("b", {}, "Choose a Logo"), nowName),
    h("div", { class: "field" }, h("div", { class: "lab" }, "Built-In Logos"),
      h("div", { class: "logo-tiles" }, tiles),
      h("div", { class: "row", style: { marginTop: "8px", alignItems: "center" } }, pick, h("span", { class: "small muted" }, "Color of the built-in logos"))),
    h("div", { class: "field" }, h("div", { class: "lab" }, "Your Own Picture"),
      h("div", { class: "row" }, h("button", { class: "primary", onclick: () => file.click() }, "Choose a Picture from This Computer…"), file),
      h("div", { class: "row", style: { marginTop: "8px" } }, h("div", { class: "grow" }, url), h("button", { onclick: () => {
        const v = url.value.trim();
        if (!/^https?:\/\/\S+$/.test(v)) return toast("Type a web address that starts with http:// or https:// first.", true);
        L.logo.src = v; delete L.logo.off; logoPick.i = -1; lookChanged(); refresh(); toast("Press Save to keep it.");
      } }, "Use This Address")),
      h("div", { class: "hint" }, "A picture from the web needs an address that starts with http:// or https://.")));
  function refresh() {
    const has = !!L.logo.src, on = has && !L.logo.off;
    const shown = has && logoPick.i >= 0 && logoPick.src === L.logo.src;
    put(now, has ? h("img", { src: L.logo.src, alt: "", style: { opacity: on ? 1 : 0.4 } }) : h("span", { class: "small muted" }, "None"));
    nowName.textContent = !has ? "No logo chosen" : (shown ? LOGO_ART[logoPick.i][0] + (on ? "" : " (off)") : (on ? "Your picture" : "Your picture (off)"));
    tiles.forEach((t, i) => t.setAttribute("aria-pressed", String(on && logoPick.i === i && logoPick.src === L.logo.src)));
    const link = h("input", { type: "url", placeholder: "https://… (optional)", value: L.logo.link || "", "aria-label": "Web address the logo opens",
      oninput: ev => { const v = ev.target.value.trim(); if (v) L.logo.link = v; else delete L.logo.link; lookChanged(); } });
    const val = h("span", { class: "val" }, (L.logo.size || 48) + " px");
    put(status,
      h("div", { class: "lab" }, "Logo"),
      has ? [
        h("div", { class: "row logo-state" },
          h("button", { class: "chip logo-switch", "aria-pressed": String(on), onclick: () => { if (L.logo.off) delete L.logo.off; else L.logo.off = true; lookChanged(); refresh(); } }, on ? "Logo: On" : "Logo: Off"),
          h("span", { class: "small muted" }, on ? "Shown at the top left of the dashboard." : "Hidden. It is kept, so you can turn it back on.")),
        h("div", { class: "field" }, h("div", { class: "lab" }, "Web Address the Logo Opens"), link,
          h("div", { class: "hint" }, "Optional. Leave it empty for a logo that only shows.")),
        h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, "Logo Size"), val,
          h("input", { type: "range", min: 24, max: 96, step: 2, value: L.logo.size || 48, "aria-label": "Logo size",
            oninput: ev => { const n = Number(ev.target.value); if (n === 48) delete L.logo.size; else L.logo.size = n; val.textContent = n + " px"; lookChanged(); } })))
      ] : h("p", { class: "muted small" }, "There is no logo yet. Open “Choose a Logo” below to pick one."));
  }
  refresh();
  return h("details", { class: "card" }, h("summary", {}, h("b", {}, "Names and Logo"), h("span", { class: "muted small" }, "Name the server and drives, add a logo")),
    h("p", { class: "muted" }, "Give the server and the two drives your own names, and show your own logo at the top left of the dashboard. Nothing is saved until you press “Save”."),
    h("div", { class: "grid cols2" },
      h("div", {}, inputs.map(x => x[2]),
        h("div", { class: "row" }, h("button", { class: "small", onclick: () => { L.names = {}; inputs.forEach(x => { x[1].value = ""; }); lookChanged(); } }, "Restore Original Names"))),
      status),
    menu);
}

// ---- Themes (the first card of the Look screen)
function themeColors(t) {            // the colors a theme gives to the cards, tiles and bookmarks: one color for each group, round and round
  const P = S.paint, out = { cards: {}, links: {}, paintAll: t.paintAll || "" };
  if (t.paintLinks) for (const it of P.links) out.links[it.name] = t.paintLinks;       // (a theme with one color for the cards and tiles may give the bookmarks a second one that goes with it)
  if (!t.palette || !t.palette.length) return out;
  const groups = [];
  const pick = g => { let i = groups.indexOf(g); if (i < 0) { groups.push(g); i = groups.length - 1; } return t.palette[i % t.palette.length]; };
  for (const list of [P.cards, P.stats, P.calendar]) for (const it of list) out.cards[it.id] = pick(it.group);
  for (const it of P.links) out.links[it.name] = pick(it.group);
  return out;
}
let themePic = true;                         // "Also change the background picture" in the Themes card
function themeBg(t) {                       // the background of a theme as a draft: its picture and its four sliders (the picture is copied to the dashboard on Save)
  const g = t && t.background;
  if (!g || !themePic) return null;
  return { url: g.url, blur: g.blur, saturate: g.saturate, brightness: g.brightness, opacity: g.opacity, theme: t.id };
}
function savedBg() { const b = S.background; return { url: "", blur: b.blur || "none", saturate: b.saturate, brightness: b.brightness, opacity: b.opacity }; }
function previewBg() { const B = bgW || savedBg(), b = S.background; send({ type: "bg", image: B.url || b.image, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); }
function chooseTheme(t) {            // like every change here it is only a draft until Save; the names, the logo and the label colors you made stay
  const def = S.look.defaults;
  const base = clone(def); base.tabs = Object.assign({}, def.tabs);
  for (const k of ["labels", "labelIcon", "names", "logo"]) base[k] = clone(lookW[k]);
  const pl = clone(t.look); const tabs = Object.assign({}, base.tabs, pl.tabs || {}); delete pl.tabs;
  const col = themeColors(t);
  lookW = Object.assign(base, pl, { tabs, theme: t.id, cards: col.cards, links: col.links, paintAll: col.paintAll });
  bgW = (t.id !== S.look.values.theme && themeBg(t)) || null;       // (the theme that is saved already keeps the picture it has)
  render(); lookChanged(); previewBg();
  toast(t.name + " is a draft. Press Save to keep it, or Discard Changes to go back.");
}
async function chooseMyTheme(t) {          // a theme you made: its look and picture are a draft (Save keeps them); its layout and cards, if it has them, are put back at once (Undo takes that back)
  const server = t.parts.filter(p => p === "layout" || p === "cards");
  if (server.length) {
    const what = server.map(p => p === "layout" ? "layout (tabs and groups)" : "cards (their names, icons, groups and order)").join(" and ");
    const draft = t.parts.includes("look") || t.parts.includes("background");
    if (!await confirmBox("Use “" + t.name + "”?", "This theme also puts back its " + what + ". That happens right now, and the Undo button at the top takes it back. " +
      (draft ? "The colors and the picture are a draft until you press Save." : ""), "Use This Theme")) return;
    try { await api("POST", "/api/mytheme", { op: "apply", id: t.id }); await afterChange(true); } catch (e) { return fail(e); }
    if (framed && autoReload()) await new Promise(r => setTimeout(r, 1400));      // (the dashboard reloads itself first, then the draft is shown on it)
  }
  const def = S.look.defaults;
  if (t.parts.includes("look")) {
    const base = clone(def); base.tabs = Object.assign({}, def.tabs);
    const pl = clone(t.look || {}); const tabs = Object.assign({}, base.tabs, pl.tabs || {}); delete pl.tabs;
    lookW = Object.assign(base, pl, { tabs, theme: t.id });
  } else if (!lookW) lookW = startLook();
  if (t.parts.includes("background") && t.background) {
    const g = t.background;
    bgW = { url: g.image || "", blur: g.blur || "none", saturate: g.saturate, brightness: g.brightness, opacity: g.opacity };
  }
  render(); lookChanged(); previewBg();
  toast(t.name + (t.parts.includes("look") || t.parts.includes("background") ? " is a draft. Press Save to keep it, or Discard Changes to go back." : " is in place."));
}
async function refreshMyThemes() { const s = await api("GET", "/api/state"); S.mythemes = s.mythemes; S.undo = s.undo; render(); }
function createThemeDialog() {          // takes the settings on the Look screen (what you see now, also what is not saved yet) and, if you tick them, the picture, the layout and the cards
  const name = h("input", { type: "text", maxlength: 30, placeholder: "For example: Movie Night", "aria-label": "Theme name" });
  const blurb = h("input", { type: "text", maxlength: 90, placeholder: "Optional: a few words about it", "aria-label": "Theme description" });
  const err = h("div", { class: "err", role: "alert", style: { color: "var(--bad)", minHeight: "20px" } });
  const parts = [
    ["look", "Look", "Colors, glass, shapes, the colors of tabs and cards, names and logo, as they are on this screen now (also what is not saved yet).", true],
    ["background", "Background Picture", "The picture and its sliders (blur, brightness and so on).", true],
    ["layout", "Layout", "The tabs, which groups are on each tab, their order, icons and columns (the Layout screen).", false],
    ["cards", "Cards", "The list of cards with their names, icons, texts, groups and order (the Cards screen). Picking the theme later puts them back; Undo can bring your old ones back.", false]];
  const boxes = parts.map(([id, label, hint, on]) => ({ id, box: h("input", { type: "checkbox", checked: on, "aria-label": label }), label, hint }));
  const d = h("dialog", {}, h("h2", {}, "Make a Theme"),
    h("p", { class: "muted" }, "Your settings on the Look screen are the start. Tick what else the theme should hold, so picking it later changes those too."),
    h("div", { class: "field" }, h("label", {}, "Name"), name), h("div", { class: "field" }, h("label", {}, "Description"), blurb),
    boxes.map(b => h("label", { class: "partrow" }, b.box, h("span", {}, h("b", {}, b.label), h("span", { class: "muted small" }, b.hint)))),
    err,
    h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Cancel"), h("button", { class: "primary", onclick: async () => {
      err.textContent = "";
      const chosen = boxes.filter(b => b.box.checked).map(b => b.id);
      if (!name.value.trim()) { err.textContent = "Give the theme a name."; name.focus(); return; }
      if (!chosen.length) { err.textContent = "Tick at least one thing for the theme to hold."; return; }
      const cur = allThemes().find(x => x.id === lookW.theme);
      const B = bgW || savedBg(), sb = S.background;
      const body = { op: "create", name: name.value.trim(), blurb: blurb.value.trim(), parts: chosen, look: lookOut(), ui: cur && cur.ui,
        background: { image: B.url || sb.image || "", blur: B.blur || "none", saturate: B.saturate, brightness: B.brightness, opacity: B.opacity } };
      try {
        const r = await api("POST", "/api/mytheme", body);
        d.close(); await refreshMyThemes();
        if (chosen.includes("look")) { lookW.theme = r.id; lookChanged(); render(); }
        toast("The theme “" + body.name + "” is saved. It is in the list under Your Themes.");
      } catch (e) { err.textContent = e.message; }
    } }, "Save the Theme")));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  name.focus();
}
function myThemeTile(t) {
  const partName = { look: "Look", background: "Picture", layout: "Layout", cards: "Cards" };
  const tile = themeTile(t, lookW.theme, () => chooseMyTheme(t));
  const chips = h("div", { class: "chips2" }, t.parts.map(p => h("span", { class: "badge" }, partName[p])));
  return h("div", { class: "mytheme" }, tile, chips,
    h("div", { class: "row tight" },
      h("button", { class: "small", onclick: async () => {
        const n = await askText("Rename the Theme", "New name for “" + t.name + "”", t.name);
        if (!n || n === t.name) return;
        try { await api("POST", "/api/mytheme", { op: "rename", id: t.id, name: n, blurb: t.blurb }); await refreshMyThemes(); } catch (e) { fail(e); }
      } }, "Rename"),
      h("button", { class: "small danger", onclick: async () => {
        if (!await confirmBox("Delete “" + t.name + "”?", "The theme is deleted from the list. What is on your dashboard now stays as it is.", "Delete the Theme", true)) return;
        try { await api("POST", "/api/mytheme", { op: "delete", id: t.id }); await refreshMyThemes(); toast("Deleted."); } catch (e) { fail(e); }
      } }, "Delete")));
}
function themeTile(t, now, onpick) {
  const lk = Object.assign({}, S.look.defaults, t.look);
  const alpha = glassAlpha(lk);
  const cols = (t.palette && t.palette.length) ? t.palette : t.paintAll ? [t.paintAll].concat(t.paintLinks ? [t.paintLinks] : []) : S.paint.cards.slice(0, 3).map(c => c.color);
  const shot = h("div", { class: "shot" },
    h("div", { class: "tabs" }, h("span", { class: "on" }), h("span", {}), h("span", {})),
    h("div", { class: "cards" }, [0, 1, 2].map(i => { const c = h("i", {}); c.style.setProperty("--c", rgb(cols[i % cols.length] || lk.accent).join(", ")); return c; })));
  shot.style.setProperty("--pc", rgb(lk.accent).join(", "));
  shot.style.setProperty("--pg", rgb(lk.glass).join(", "));
  shot.style.setProperty("--pa", alpha);
  shot.style.setProperty("--pr", Math.round(Math.min(lk.radius, 30) * 0.5) + "px");
  shot.style.setProperty("--pe", lk.edge / 100);
  shot.style.setProperty("--bl", Math.round(lk.glassBlur * 0.5) + "px");
  shot.style.setProperty("--prm", rimShadow(lk.glassRim));
  return h("button", { class: "theme", "aria-pressed": String(now === t.id), onclick: onpick || (() => chooseTheme(t)) }, shot, h("b", {}, t.name), h("span", { class: "small muted" }, t.blurb));
}
function themesCard() {
  return h("div", { class: "card" }, h("h2", {}, "Themes"),
    h("p", { class: "muted" }, "A theme changes the colors, glass and shapes of the dashboard and of this panel together, and gives every card, tile and bookmark a matching color. Pick one to try it. Nothing is saved until you press “Save”."),
    h("div", { class: "themes" }, S.look.themes.map(t => themeTile(t, lookW.theme))),
    (S.mythemes || []).length ? [h("h3", {}, "Your Themes"), h("div", { class: "themes" }, S.mythemes.map(myThemeTile))] : null,
    h("div", { class: "row", style: { marginBottom: "10px" } }, h("button", { onclick: createThemeDialog }, "+ Make a Theme from These Settings…")),
    h("label", { class: "row check" }, h("input", { type: "checkbox", checked: themePic, "aria-label": "Also change the background picture", onchange: ev => {
      themePic = ev.target.checked;
      const t = S.look.themes.find(x => x.id === lookW.theme);
      bgW = (themePic && t) ? themeBg(t) : null;       // (off: the picture you have stays)
      render(); previewBg(); refreshLookBar();
    } }), h("span", {}, "Also Change the Background Picture")),
    h("p", { class: "muted small" }, "Each theme has a background picture that goes with it. With the box ticked, the picture and its sliders change when you pick a theme. Untick it to keep your own picture. Your names and logo always stay as they are. Colors you gave single cards are replaced by the theme’s colors. You can still change anything below after picking a theme."));
}

function viewLook() {
  if (!lookW) lookW = startLook();
  const L = lookW;
  lookBarEl = h("div", {});
  const glass = h("div", {});
  function drawGlass() {
    const chip = (on, text, set) => h("button", { class: "chip", "aria-pressed": String(on), onclick: () => { set(); lookChanged(); drawGlass(); } }, text);
    const tint = L.glassTint !== false;
    put(glass,
      h("div", { class: "field" }, h("div", { class: "lab" }, "Card Tint"),
        h("div", { class: "chips" }, chip(tint, "Tint On", () => { L.glassTint = true; }), chip(!tint, "No Tint", () => { L.glassTint = false; })),
        h("div", { class: "hint" }, "No Tint takes the colored glass layer off the cards, so only the blur is left. The colors you gave your cards stay (see Color Strength below). The text gets a thin shadow so it stays sharp over a bright picture.")),
      tint ? [h("div", { class: "field" }, h("div", { class: "lab" }, "Glass Style"),
        h("div", { class: "chips" }, chip(!L.glassClear, "Tinted", () => { L.glassClear = false; }), chip(L.glassClear, "Transparent", () => { L.glassClear = true; })),
        h("div", { class: "hint" }, "Transparent glass lets the picture and the colors of your cards show through, so they look more vibrant.")),
      L.glassClear
        ? [lookSlider("How Transparent", "glassLevel", 0, 100, 1, "%", "Higher is clearer. 100% is plain frosted glass with no tint."),
           h("div", { class: "chips", style: { marginBottom: "12px" } }, [["A Little", 30], ["Medium", 55], ["Very", 80], ["Clear", 100]].map(([t, n]) =>
             h("button", { class: "chip", onclick: () => { L.glassLevel = n; lookChanged(); render(); } }, t)))]
        : lookSlider("How Solid the Glass Is", "glassOpacity", 0, 100, 1, "%", "Low shows the picture through the cards. High makes them solid.")] : null,
      lookSlider("Shine on the Glass Edge", "glassRim", 0, 100, 1, "%", "A bright thin line around the glass and a soft glow just inside it, like the glass on Apple devices. 0% turns it off."));
  }
  drawGlass();
  const tabRows = S.look.tabNames.map(name => {
    const cur = () => L.tabs[name] || L.accent;
    const pick = h("input", { type: "color", value: cur(), "aria-label": "Color of the tab " + name });
    pick.addEventListener("input", () => { L.tabs[name] = pick.value; lookChanged(); });
    return h("div", { class: "row", style: { marginBottom: "6px" } }, pick, h("span", { class: "grow" }, name),
      h("button", { class: "small", onclick: () => { L.tabs[name] = L.accent; pick.value = L.accent; lookChanged(); } }, "Use Main Color"));
  });
  const mock = h("div", { class: "preview", id: "mock" },
    h("div", { class: "mini-tabs" }, h("span", { class: "on" }, "Home"), h("span", {}, "Stats"), h("span", {}, "Links")),
    h("div", { class: "mini-cards" }, ["Navidrome", "Immich", "Beszel"].map(n => h("div", { class: "mini-card" }, h("b", {}, n), h("span", { class: "small muted" }, "Sample Card"), h("i", {})))));
  setTimeout(() => { lookPreview(!lookDirty()); refreshLookBar(); }, 0);       // nothing is sent to the dashboard until something is changed
  const previewCard =
h("div", { class: "card" }, h("h2", {}, "Preview and Shape"),
  h("div", { class: "grid cols2" },
        h("div", {}, h("p", { class: "muted" }, framed ? "The dashboard around this panel changes while you move the sliders, so you can see the real result." : "A small sample of how cards and tabs look."), mock),
        h("div", {},
          lookSlider("How Round the Corners Are", "radius", 0, 40, 1, " px"),
          lookSlider("Brightness of the Card Edge", "edge", 0, 40, 0.5, "%"),
          lookSlider("Space at the Left and Right", "side", 0, 120, 2, " px"),
          h("p", { class: "muted small" }, "The height of the music player is changed on the dashboard itself, with the small arrows button next to the shrink button on the player."))));
  const colorsCard =
h("div", { class: "card" }, h("h2", {}, "Colors and Glass"),
      h("div", { class: "grid cols2" },
        h("div", {},
          colorField("Main Color", "accent", "The color of the active tab, bars, icons and the edge of a card you point at.", ["#8ab4ff", "#5ec8ff", "#7ee0a0", "#ffa66b", "#ff8fb5", "#c9a0ff", "#ffd36b", "#c3cad6"]),
          colorField("Glass Color", "glass", "The tint of every card and tile (only when Card Tint is on).", ["#0d121e", "#06141f", "#07150d", "#1c0f12", "#1a0c16", "#111214"]),
          colorField("Text Color", "text", "The names and numbers on cards, tiles and bookmarks. Choose a light color on a dark picture and a dark color on a bright one.", ["#eef2f9", "#ffffff", "#fff6ee", "#f2fcff", "#fff2f7", "#1a2233"]),
          colorField("Smaller Text Color", "muted", "The descriptions and labels under the names.", ["#a9b4c7", "#dde8f8", "#ecd0bf", "#bcdbe8", "#efcadb", "#4a5568"])),
        glass),
      h("div", { class: "field" }, h("div", { class: "lab" }, "Color of Each Tab"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "Each tab can have its own accent color."),
        h("div", { class: "grid cols2 tabcolors" }, tabRows)),
      h("p", { class: "muted small" }, "Further down you can give single cards, tiles, bookmarks and labels their own colors."));
  const strengthCard =
h("div", { class: "card" }, h("h2", {}, "Color Strength"),
  lookSlider("How Strong the Colors Are", "paintStrength", 0, 100, 1, "%", "How strong the colors of your cards, tiles and bookmarks are. Higher makes the color, the edge and the glow stronger, so the color is not washed out."),
  lookSlider("Card Depth", "cardDepth", 0, 100, 1, "%", "A deep, rich shade of each card's own color under the bright color. Higher makes the words stand out more and the colors look fuller, not washed out. 0% turns it off."));
  return h("div", {},
    themesCard(),
    previewCard,
    colorsCard,
    strengthCard,
    backgroundCards(),
    namesCard(),
    colorOptions(),
    lookBarEl);
}

function labelIconSample(style) {
  return h("span", { class: "lis lis-" + style }, h("img", { src: iconInfo("mdi-movie-open").url, class: "mdi", alt: "" }));
}

function colorOptions() {                    // the colors of single cards, tiles, bookmarks and labels (the last part of the Look screen)
  const L = lookW, P = S.paint;

  function colorInput(value, label, onset) {
    const inp = h("input", { type: "color", value: value || "#8ab4ff", "aria-label": label });
    inp.addEventListener("input", () => onset(inp.value));
    return inp;
  }
  // everything that shows "Default" or "All Color" and has to follow a change of the one color for everything
  const followers = [];
  // one row per card, tile or bookmark: the color, and a button to go back to the default. A change is made in place (a new picker would close the open one).
  function itemRow(map, key, name, sub, def) {
    const badge = h("span", { class: "badge" }), reset = h("button", { class: "small" }, "Reset");
    const base = () => L.paintAll || def || "#8ab4ff";
    const inp = colorInput(map[key] || base(), "Color of " + name, v => { map[key] = v; lookChanged(); refresh(); });
    function refresh() {
      const set = !!map[key];
      badge.textContent = set ? "Custom" : (L.paintAll ? "All Color" : "Default");
      badge.className = "badge" + (set ? "" : " dim");
      reset.disabled = !set;
      if (!set && inp.value !== base()) inp.value = base();
    }
    reset.addEventListener("click", () => { delete map[key]; lookChanged(); refresh(); });
    refresh();
    return h("div", { class: "prow" }, h("div", { class: "txt" }, h("b", {}, name), sub ? h("span", {}, sub) : null), badge, inp, reset);
  }
  // a list of items with "one color for all of these"
  function section(title, hint, items, map, keyOf, subOf, open) {
    if (!items.length) return null;
    let bulk = "#8ab4ff";
    const rows = h("div", {});
    const draw = () => put(rows, items.map(it => itemRow(map, keyOf(it), it.name, subOf(it), it.color)));
    draw();
    const bulkInp = colorInput(bulk, "One color for all in " + title, v => { bulk = v; });
    followers.push(draw, () => { if (L.paintAll) { bulk = L.paintAll; bulkInp.value = bulk; } });      // (the box for "all below" follows the one color for everything)
    return h("details", { class: "card", open: open }, h("summary", {}, h("b", {}, title), h("span", { class: "badge" }, String(items.length))),
      h("p", { class: "muted small" }, hint),
      h("div", { class: "row bulk" }, h("span", { class: "lab" }, "One Color for All Below:"), bulkInp,
        h("button", { class: "small", onclick: () => { for (const it of items) map[keyOf(it)] = bulk; lookChanged(); draw(); } }, "Apply"),
        h("button", { class: "small", onclick: () => { for (const it of items) delete map[keyOf(it)]; lookChanged(); draw(); } }, "Set All to Default")),
      rows);
  }

  // labels: the text and the icon of a group name
  const labelRows = h("div", {});
  function drawLabels() {
    put(labelRows, P.labels.map(name => {
      const part = (key, text, def) => {
        const reset = h("button", { class: "small", "aria-label": "Reset " + text.toLowerCase() + " of " + name }, "Reset");
        const inp = colorInput((L.labels[name] || {})[key] || def, text + " of " + name, v => { (L.labels[name] = L.labels[name] || {})[key] = v; lookChanged(); refresh(); });
        const refresh = () => { reset.disabled = !(L.labels[name] || {})[key]; };
        reset.addEventListener("click", () => {
          if (L.labels[name]) { delete L.labels[name][key]; if (!Object.keys(L.labels[name]).length) delete L.labels[name]; }
          inp.value = def; lookChanged(); refresh();
        });
        refresh();
        return h("span", { class: "lpart" }, h("span", { class: "small muted" }, text), inp, reset);
      };
      return h("div", { class: "prow" }, h("div", { class: "txt" }, h("b", {}, name)), part("text", "Text", "#eef2f9"), part("icon", "Icon", "#c9d6f2"));
    }));
  }
  drawLabels();
  let bulkText = "#eef2f9", bulkIcon = "#c9d6f2";
  const styles = h("div", { class: "chips" });
  function drawStyles() {
    put(styles, [["plain", "Plain Icon"], ["circle", "Circle Badge"], ["square", "Rounded Square Badge"], ["ring", "Glowing Ring"]].map(([id, text]) =>
      h("button", { class: "chip styl", "aria-pressed": String(L.labelIcon === id), onclick: () => { L.labelIcon = id; lookChanged(); drawStyles(); } }, labelIconSample(id), text)));
  }
  drawStyles();

  // one color for everything: changed in place too, and the rows below follow it
  const allBadge = h("span", { class: "badge" }), allOff = h("button", { class: "small" }, "Turn Off");
  const allInp = colorInput(L.paintAll || "#8ab4ff", "One color for everything", v => { L.paintAll = v; lookChanged(); refreshAll(); });
  function refreshAll() {
    allBadge.textContent = L.paintAll ? "On" : "Off";
    allBadge.className = "badge" + (L.paintAll ? "" : " dim");
    allOff.disabled = !L.paintAll;
    for (const f of followers) f();
  }
  allOff.addEventListener("click", () => { L.paintAll = ""; lookChanged(); refreshAll(); });
  refreshAll();
  const paintAll = h("div", {},
    h("div", { class: "row" }, allInp, allBadge, allOff),
    h("div", { class: "hint" }, "Pick a color to give every card, tile and bookmark the same color. A color you pick for a single one below still wins."));

  const styleChips = h("div", { class: "chips" });
  function drawPaintStyle() {
    put(styleChips, [["gradient", "Gradient"], ["solid", "Solid"]].map(([id, text]) =>
      h("button", { class: "chip", "aria-pressed": String(L.paintStyle === id), onclick: () => { L.paintStyle = id; lookChanged(); drawPaintStyle(); } }, text)));
  }
  drawPaintStyle();

  return h("div", {},
    h("details", { class: "card" }, h("summary", {}, h("b", {}, "Colors of Cards, Tiles and Bookmarks"), h("span", { class: "muted small" }, "Advanced: a theme already sets these")),
      h("p", { class: "muted" }, "Give single service cards, the calendar, the tiles of the Stats tab and the bookmarks of the Links tab their own color: a tint, a colored edge and a soft glow. It looks best with Transparent glass (set under Colors and Glass)."),
      h("p", { class: "muted small" }, "To see a color on the dashboard, open the tab that has it (Home, Stats or Links). The preview stays there. Come back here to keep it with Save."),
      h("div", { class: "field" }, h("div", { class: "lab" }, "Color Style"), styleChips,
        h("div", { class: "hint" }, "Gradient: the color is strong on one side and fades out across the card. Solid: the same color across the whole card.")),
      h("div", { class: "field" }, h("div", { class: "lab" }, "One Color for Everything"), paintAll)),
    section("Service Cards", "The cards of the Home tab, such as Portainer or Downtify.", P.cards, L.cards, it => it.id, it => it.group, false),
    section("Stats Tiles", "The tiles of the Stats tab.", P.stats, L.cards, it => it.id, it => it.group, false),
    section("Calendar", "The calendar and the list of coming events.", P.calendar, L.cards, it => it.id, it => it.group, false),
    section("Bookmarks", "The bookmarks of the Links tab.", P.links, L.links, it => it.name, it => it.group, false),
    h("details", { class: "card" }, h("summary", {}, h("b", {}, "Labels"), h("span", { class: "badge" }, String(P.labels.length))),
      h("p", { class: "muted small" }, "The names above each row of cards, such as Media & Entertainment. Choose a color for the text and for the small icon next to it."),
      h("div", { class: "row bulk" }, h("span", { class: "lab" }, "One Color for All Labels:"),
        h("span", { class: "lpart" }, h("span", { class: "small muted" }, "Text"), colorInput(bulkText, "Text color for all labels", v => { bulkText = v; })),
        h("span", { class: "lpart" }, h("span", { class: "small muted" }, "Icon"), colorInput(bulkIcon, "Icon color for all labels", v => { bulkIcon = v; })),
        h("button", { class: "small", onclick: () => { for (const n of P.labels) L.labels[n] = { text: bulkText, icon: bulkIcon }; lookChanged(); drawLabels(); } }, "Apply"),
        h("button", { class: "small", onclick: () => { L.labels = {}; lookChanged(); drawLabels(); } }, "Set All to Default")),
      labelRows,
      h("div", { class: "field", style: { marginTop: "14px" } }, h("div", { class: "lab" }, "Icon Style"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "How the small icon next to every label looks."), styles)));
}

// ---------------------------------------------------------------- Background (cards of the Look screen)
function bgUrl(img) { return !img ? "" : (img.startsWith("/") && S.background.homepageUrl ? S.background.homepageUrl + img : (img.startsWith("/") ? "" : img)); }
function backgroundCards() {
  const b = S.background;
  if (!bgW) bgW = savedBg();
  const B = bgW;
  const pic = h("div", { class: "pic" });
  const drawPic = () => { const u = B.url || bgUrl(b.image); pic.style.backgroundImage = u ? 'url("' + u.replace(/"/g, "%22") + '")' : "none"; };
  drawPic();
  const preview = () => { send({ type: "bg", image: B.url || b.image, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); refreshLookBar(); };
  function reset() {      // like every other change on this screen: it is only a draft until Save
    const d = b.defaults || { blur: "md", saturate: 60, brightness: 42, opacity: 80 };
    B.blur = d.blur; B.saturate = d.saturate; B.brightness = d.brightness; B.opacity = d.opacity;
    preview();
    render();
    toast("The sliders are back to their default values. Press Save to keep it.");
  }
  function slider(label, key, hint) {
    const val = h("span", { class: "val" }, B[key] + "%");
    return h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, label), val,
      h("input", { type: "range", min: 0, max: 100, step: 1, value: B[key], "aria-label": label, oninput: ev => { B[key] = Number(ev.target.value); val.textContent = B[key] + "%"; preview(); } })),
      h("div", { class: "hint" }, hint));
  }
  const blurVal = h("span", { class: "val" }, BLUR_NAMES[B.blur] || B.blur);
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
  return h("div", { class: "grid cols2" },
    h("div", { class: "card" }, h("h2", {}, "Background Picture"), pic,
      h("div", { class: "row", style: { marginTop: "12px" } }, file, h("button", { class: "primary", onclick: () => file.click() }, "Upload a Picture…")),
      h("p", { class: "hint muted small" }, "JPG, PNG, WebP, GIF or AVIF, up to 14 MB. After a new picture the dashboard restarts for about 10 seconds."),
      b.mounted === false ? h("p", { class: "small", style: { color: "var(--bad)" } }, "The dashboard cannot see its pictures folder yet, so an uploaded picture will not show. Run: sudo homelab-setup upgrade") : null,
      h("div", { class: "field", style: { marginTop: "12px" } }, h("label", {}, "Or Use a Picture from the Web"), h("div", { class: "row" }, h("div", { class: "grow" }, url),
        h("button", { onclick: () => { const v = url.value.trim(); if (!/^https?:\/\/\S+$/.test(v)) return toast("Type a web address that starts with http:// or https:// first.", true); B.url = v; B.theme = ""; drawPic(); preview(); toast("Press Save to keep it."); } }, "Use This Address")))),
    h("div", { class: "card" }, h("h2", {}, "How the Background Looks Behind the Cards"),
      h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, "Picture Blur"), blurVal,
        h("input", { type: "range", min: 0, max: 6, step: 1, value: BLURS.indexOf(B.blur) < 0 ? 2 : BLURS.indexOf(B.blur), "aria-label": "Picture Blur",
          oninput: ev => { B.blur = BLURS[Number(ev.target.value)]; blurVal.textContent = BLUR_NAMES[B.blur] || B.blur; preview(); } })), h("div", { class: "hint" }, "None keeps the picture sharp. Very Huge makes it very soft.")),
      slider("Picture Brightness", "brightness", "Low makes the picture darker, so the text is easy to read."),
      slider("Picture Color", "saturate", "Low turns the picture toward gray."),
      slider("How Much Picture Shows", "opacity", "Higher shows more of the picture. Lower covers it with the dark layer."),
      h("div", { class: "row" }, h("button", { class: "small", onclick: reset }, "Restore Default Sliders"))));
}

// ---------------------------------------------------------------- Layout
function viewLayout() {
  if (!layW) layW = clone(S.layout.tabs);
  const T = layW;
  const dirty = () => !same(T, S.layout.tabs);
  const bar = h("div", {});
  const refreshBar = () => put(bar, saveBar(dirty(), save, () => { layW = null; render(); }, "Save"));
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
    const icon = h("button", { class: "small", "aria-label": "Choose the icon of " + g.name, onclick: async () => { const pick = await pickIcon(g.icon || ""); if (typeof pick === "string" && pick !== (g.icon || "")) { g.icon = pick; redraw(); } } }, "Icon…");
    const style = h("select", { "aria-label": "Shape of " + g.name, onchange: ev => { g.style = ev.target.value; redraw(); } },
      h("option", { value: "", selected: !g.style }, "Cards in a list"), h("option", { value: "row", selected: g.style === "row" }, "Cards in a row"));
    const cols = h("input", { class: "cols-in", type: "number", min: 1, max: 8, value: g.columns || "", placeholder: "Columns", title: "How many columns (empty = automatic)", "aria-label": "Columns of " + g.name, onchange: ev => { g.columns = ev.target.value; redraw(); } });
    add(row, h("span", { class: "handle", title: "Drag to move", "aria-hidden": "true" }, "⠿"), iconEl(g.icon), h("span", { class: "name" }, g.name),
      g.automatic ? h("span", { class: "badge", title: "HomeLab fills this group by itself" }, "automatic") : null,
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
    h("div", { class: "card" }, h("h2", {}, "Tabs and Groups"),
      h("p", { class: "muted" }, "Each box is a tab of the dashboard. Drag a group (or use the arrows) to change the order, pick another tab to move it there, and choose how its cards are laid out. “Cards in a row” puts the cards side by side."),
      h("div", { class: "row", style: { marginBottom: "12px" } }, h("button", { onclick: async () => {
        const n = (await askText("Add a tab", "Name of the new tab", "")) || "";
        if (!n) return;
        if (T.some(x => x.name === n)) return toast("There is already a tab with that name.", true);
        T.push({ name: n, groups: [] }); redraw();
      } }, "+ Add a Tab"), h("span", { class: "muted small" }, "Then move a group into it.")),
      board),
    bar);
}

// ---------------------------------------------------------------- Cards and links (one editor for both)
function viewCards() { return viewItems("cards"); }
function viewLinks() { return viewItems("links"); }

function viewItems(kind) {
  const isCards = kind === "cards";
  const groups = (isCards ? S.services.filter(g => !g.locked) : S.links);
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
  async function quickIcon(g, it) {                       // change only the icon of a card
    const pick = await pickIcon(it.icon);
    if (pick === it.icon) return;
    await op({ op: "edit", group: g.group, old: it.name, name: it.name, href: it.href, icon: pick, description: it.description, dot: !!it.siteMonitor }, "Icon saved.");
  }
  async function remove(g, it) {
    if (it.hl) {
      if (!await confirmBox("Hide “" + it.name + "”?", "It disappears from the dashboard. Bring it back any time with Add From HomeLab's List (or with Undo).", "Hide It", true)) return;
      return op({ op: "remove", group: g.group, name: it.name }, "Hidden.");
    }
    if (!await confirmBox("Remove “" + it.name + "”?", "It disappears from the dashboard. Undo can bring it back.", "Remove It", true)) return;
    await op({ op: "remove", group: g.group, name: it.name }, "Removed.");
  }
  function hlList() {                                      // the cards HomeLab fills in, to pick from (shown ones are ticked and cannot be added twice)
    const list = S.hlcards || [];
    if (!list.length) { toast("The list of HomeLab's cards is not on this machine yet. On the server run: sudo homelab-setup upgrade", true); return; }
    const picks = new Set();
    const err = h("div", { class: "err", role: "alert", style: { color: "var(--bad)", minHeight: "20px" } });
    const gsel = h("select", { "aria-label": "Put them in" }, h("option", { value: "" }, "Each in its usual group"), groups.map(x => h("option", { value: x.group }, x.group)));
    const names = [...new Set(list.map(c => c.group))];
    const rows = names.map(n => h("div", { class: "card", style: { margin: "8px 0" } }, h("h3", {}, n),
      list.filter(c => c.group === n).map(c => {
        const on = !!c.in;
        const box = h("input", { type: "checkbox", disabled: on, "aria-label": c.name + (on ? " (already on the dashboard)" : ""), onchange: ev => { ev.target.checked ? picks.add(c.id) : picks.delete(c.id); } });
        return h("label", { class: "item", style: { cursor: on ? "default" : "pointer" } }, box, iconEl(c.icon),
          h("div", { class: "txt" }, h("b", {}, c.name), h("span", {}, c.description || "")),
          on ? h("span", { class: "badge" }, "On the dashboard" + (c.in !== n ? " (in " + c.in + ")" : "")) : (c.extra ? h("span", { class: "badge" }, "Extra") : null));
      })));
    const d = h("dialog", {}, h("h2", {}, "Add From HomeLab's List"),
      h("p", { class: "muted" }, "Cards HomeLab fills in with numbers. Tick the ones you want. The ones already on the dashboard are greyed out. “Extra” cards show a single number."),
      h("div", { style: { maxHeight: "50vh", overflow: "auto" } }, rows),
      h("div", { class: "field" }, h("label", {}, "Put them in"), gsel), err,
      h("div", { class: "actions" }, h("button", { onclick: () => d.close() }, "Cancel"), h("button", { class: "primary", onclick: async () => {
        err.textContent = "";
        if (!picks.size) { err.textContent = "Tick at least one card."; return; }
        try {
          await api("POST", "/api/card", { op: "add-list", ids: [...picks], group: gsel.value || undefined });
          d.close(); toast("Added."); await afterChange(true);
        } catch (e) { err.textContent = e.message; }
      } }, "Add the Ticked Cards")));
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
  }
  async function hlRestore() {
    if (!await confirmBox("Put HomeLab's Cards Back?", "Every card HomeLab fills in goes back to its own name, icon and group, and the ones you hid come back. Cards you added yourself stay. Undo can take this back.", "Put Them Back", true)) return;
    try { await api("POST", "/api/hlcards/restore", {}); toast("Put back."); await afterChange(true); } catch (e) { fail(e); }
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
    const ic = iconField(v.icon, v.hl ? null : () => href.value);
    const names = groups.map(x => x.group);
    const gsel = h("select", { "aria-label": "Group" }, names.map(n => h("option", { value: n, selected: g && n === g.group }, n)), h("option", { value: "__new" }, "A new group…"));
    const gnew = h("input", { type: "text", placeholder: "Name of the new group", maxlength: 40, hidden: true, "aria-label": "New group name" });
    const tsel = h("select", { "aria-label": "Tab for the new group", hidden: true }, tabsList.map(n => h("option", { value: n, selected: n === (isCards ? "Home" : "Links") }, "On the tab: " + n)));
    gsel.addEventListener("change", () => { const nw = gsel.value === "__new"; gnew.hidden = !nw; tsel.hidden = !nw; if (nw) gnew.focus(); });
    if (!names.length) { gsel.value = "__new"; gnew.hidden = false; tsel.hidden = false; }
    const err = h("div", { class: "err", role: "alert", style: { color: "var(--bad)", minHeight: "20px" } });
    const d = h("dialog", {}, h("h2", {}, adding ? "Add a " + word : "Change “" + v.name + "”"),
      h("div", { class: "field" }, h("label", {}, "Name"), name),
      v.hl ? h("p", { class: "muted small" }, "HomeLab fills in the numbers of this card by itself, so only its name, icon, color, text and group change here.") :
        h("div", { class: "field" }, h("label", {}, "Web address"), href, managed ? h("div", { class: "hint" }, "HomeLab keeps this address right (the Tailscale name and ports), so it cannot be changed here.") : null),
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
    const n = (await askText("Rename the Group", "New name for the group “" + g.group + "”", g.group)) || "";
    if (!n || n === g.group) return;
    try {
      await api("POST", isCards ? "/api/group" : "/api/link", isCards ? { op: "rename", group: g.group, to: n } : { op: "group-rename", group: g.group, to: n });
      toast("Renamed."); await afterChange(true);
    } catch (e) { fail(e); }
  }
  async function groupRemove(g) {
    if (!await confirmBox("Remove the Whole Group “" + g.group + "”?", "This removes the group and its " + items(g).length + " " + word + (items(g).length === 1 ? "" : "s") + ". Undo can bring them back.", "Remove the Group", true)) return;
    try {
      await api("POST", isCards ? "/api/group" : "/api/link", isCards ? { op: "remove", group: g.group } : { op: "group-remove", group: g.group });
      toast("Removed."); await afterChange(true);
    } catch (e) { fail(e); }
  }

  const cards = groups.map(g => h("div", { class: "card group-card" },
    h("header", {}, h("h2", {}, g.group), h("span", { class: "badge" }, items(g).length + (items(g).length === 1 ? " " + word : " " + word + "s")),
      isCards && g.automatic ? h("span", { class: "badge", title: "HomeLab fills in the numbers of these cards" }, "Filled in by HomeLab") : null,
      isCards && g.automatic ? null : [h("button", { class: "small", onclick: () => groupMenu(g) }, "Rename"), h("button", { class: "small danger", onclick: () => groupRemove(g) }, "Remove Group")]),
    items(g).map((it, i) => h("div", { class: "item" }, iconEl(it.icon),
      h("div", { class: "txt" }, h("b", {}, it.name), h("span", {}, [it.description, it.href].filter(Boolean).join("  ·  ") || "No address")),
      isCards && it.managed ? h("span", { class: "badge", title: "Made by HomeLab; it keeps the address right" }, "Built-In") : null,
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " up", disabled: i === 0, onclick: () => reorder(g, i, -1) }, "↑"),
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " down", disabled: i === items(g).length - 1, onclick: () => reorder(g, i, 1) }, "↓"),
      isCards && !it.locked ? h("button", { class: "small", onclick: () => quickIcon(g, it) }, "Icon…") : null,
      h("button", { class: "small", onclick: () => editor(g, it) }, "Change"),
      h("button", { class: "small danger", onclick: () => remove(g, it) }, it.hl ? "Hide" : "Remove"))),
    h("div", { style: { marginTop: "10px" } }, h("button", { class: "small", onclick: () => editor(g, null) }, "+ Add a " + (word === "card" ? "Card" : "Link") + " here"))));

  return h("div", {},
    h("div", { class: "card" }, h("h2", {}, isCards ? "Cards on the Dashboard" : "Links (Bookmarks)"),
      h("p", { class: "muted" }, isCards ? "The cards of Home. Add your own cards for any web page, change a name or text, put them in another order or group, or remove them."
        : "The bookmarks of the Links tab, in groups. Add your own sites with their icons."),
      h("div", { class: "row" }, h("button", { class: "primary", onclick: () => editor(groups[0] || null, null) }, "+ Add a " + (word === "card" ? "Card" : "Link")),
        isCards ? [h("button", { onclick: hlList }, "Add From HomeLab's List…"), h("button", { onclick: hlRestore, title: "Bring back the cards HomeLab fills in, as they came" }, "Put HomeLab's Cards Back…")] : null),
      isCards ? h("p", { class: "muted small" }, "The groups marked “Filled in by HomeLab” hold the numbers and the calendar. Their cards can be renamed, given another icon or color, moved, put in another order, hidden and brought back like any other card.") : null),
    cards.length ? cards : h("p", { class: "muted" }, "There is nothing here yet."));
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
