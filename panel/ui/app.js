"use strict";
/* The control panel page. Plain JavaScript, no libraries. Everything that comes from the dashboard's files is put on the page as text (never as HTML). */

const framed = window.parent !== window;
let S = null;                 // what the server says (look, background, layout, cards, links)
let view = "look";
let lookW = null, bgW = null, layW = null;     // the changes in progress (not saved yet)
const root = document.getElementById("app");
const LOOKVIEWS = ["look", "colors"];                // these two screens work on the same look, so going from one to the other keeps the changes
const BLURS = ["none", "sm", "md", "lg", "xl", "2xl", "3xl"];
const ONLY = new URLSearchParams(location.search).get("only");       // "links": only the link editor, shown inside the Links tab of the dashboard
const VIEWS = ONLY === "links" ? [["links", "Links"]]
  : [["look", "Look"], ["colors", "Colors"], ["background", "Background"], ["layout", "Layout"], ["cards", "Cards"]];
if (ONLY === "links") view = "links";

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
  const fns = { look: viewLook, colors: viewColors, background: viewBackground, layout: viewLayout, cards: viewCards, links: viewLinks };
  if (ONLY === "links") { put(root, viewLinks()); applyAccent(); return; }
  footEl = h("div", { class: "savebar" });
  drawFoot(false, null, null);
  const auto = h("input", { type: "checkbox", checked: autoReload(), id: "auto", onchange: ev => { try { localStorage.setItem("hlp-auto", ev.target.checked ? "1" : "0"); } catch (e) { /* ignore */ } } });
  put(root,
    h("div", { class: "stickytop" },
      h("header", { class: "top" },
        h("div", { class: "grow" }, h("h1", {}, "Customize Your Dashboard"), h("div", { class: "sub" }, "Changes are saved to your dashboard files. Use Undo to reverse the most recent change."))),
      h("nav", { class: "tabs", role: "tablist" }, VIEWS.map(([id, label]) =>
        h("button", { role: "tab", "aria-selected": String(view === id), onclick: () => { if (view !== id) { if (!(LOOKVIEWS.includes(view) && LOOKVIEWS.includes(id))) discardPreview(); view = id; render(); window.scrollTo(0, 0); } } }, label)))),
    fns[view](),
    framed ? h("p", { class: "muted small" }, h("label", { for: "auto" }, auto, " Refresh the dashboard by itself after I change layout, cards or links")) : null,
    footEl);
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
function discardPreview() { send({ type: "clear" }); lookW = bgW = layW = null; clearDraft(); }

// the bar at the bottom of every screen: what is not saved yet, then Undo, Save and (in the dashboard's frame) Open in Tab, or Log Out
let footEl = null;
function drawFoot(dirty, onSave, onRevert, extra) {
  if (!footEl) return;
  put(footEl,
    h("div", { class: "state" + (dirty ? " dirty" : "") }, onSave ? (dirty ? "You have changes that are not saved yet." : "Everything shown is saved.") : ""),
    onRevert ? h("button", { disabled: !dirty, onclick: onRevert }, "Discard Changes") : null,
    extra || null,
    h("button", { disabled: !S.undo, onclick: doUndo, title: S.undo ? "Undo: " + S.undo : "Nothing to undo" }, "Undo"),
    h("button", { class: "primary", disabled: !onSave || !dirty, onclick: onSave || (() => {}) }, "Save"),
    framed ? h("a", { class: "btn", href: location.href, target: "_blank", rel: "noopener" }, "Open in New Tab") : null,
    h("button", { class: "ghost", onclick: async () => { try { await api("POST", "/api/logout", {}); } catch (e) { /* already out */ } S = null; showLogin(); } }, "Log Out"));
}
function saveBar(dirty, onSave, onRevert, saveLabel, extra) {      // (kept for the screens: they hand over what the bottom bar shows)
  drawFoot(dirty, onSave, onRevert, extra);
  return null;
}

// ---------------------------------------------------------------- Look and Colors (one look, two screens)
function rgb(hex) { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ""); const n = m ? parseInt(m[1], 16) : 0; return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
const PAINT_KEYS = ["paintAll", "paintStrength", "paintStyle", "cards", "links", "labels", "labelIcon", "names", "logo"];       // (what a built-in look leaves as it is)
let lookBarEl = null, pvTimer = null, pvSeq = 0;

function lookOut() {                       // what is sent to the server: the look, with only the tab colors that differ from the shipped ones
  const out = clone(lookW);
  out.tabs = {};
  for (const [n, c] of Object.entries(lookW.tabs)) if (c !== S.look.defaults.tabs[n]) out.tabs[n] = c;
  return out;
}
function glassAlpha(v) { return v.glassClear ? 0.4 * (1 - v.glassLevel / 100) : v.glassOpacity / 100; }
function lookPreview(quiet) {
  const p = document.getElementById("mock");
  if (p) {
    p.style.setProperty("--pc", rgb(lookW.accent).join(", "));
    p.style.setProperty("--pg", rgb(lookW.glass).join(", "));
    p.style.setProperty("--pa", glassAlpha(lookW));
    p.style.setProperty("--pr", Math.min(lookW.radius, 30) + "px");
    p.style.setProperty("--pe", lookW.edge / 100);
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
function refreshLookBar() {
  if (!lookBarEl) return;
  put(lookBarEl, saveBar(lookDirty(), saveLook, () => { discardPreview(); render(); }, "Save",
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
async function saveLook() {
  try { clearTimeout(pvTimer); pvSeq++; await api("POST", "/api/look", { look: lookOut() }); clearTimeout(pvTimer); pvSeq++; send({ type: "saved" }); toast("Look saved."); await afterChange(false); } catch (e) { fail(e); }
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
  hex.addEventListener("change", () => { if (/^#[0-9a-f]{6}$/i.test(hex.value.trim())) set(hex.value.trim().toLowerCase()); else hex.value = L[key]; });
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
    if (f.size > 15 * 1024 * 1024) return toast("That picture is larger than 15 MB. Choose a smaller one.", true);
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
        if (!/^https?:\/\/\S+$/.test(v)) return toast("Type a web address that starts with https:// first.", true);
        L.logo.src = v; delete L.logo.off; logoPick.i = -1; lookChanged(); refresh(); toast("Press Save to keep it.");
      } }, "Use This Address")),
      h("div", { class: "hint" }, "A picture from the web needs an address that starts with https://.")));
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
  return h("div", { class: "card" }, h("h2", {}, "Names and Logo"),
    h("p", { class: "muted" }, "Give the server and the two drives your own names, and show your own logo at the top left of the dashboard. Nothing is saved until you press “Save”."),
    h("div", { class: "grid cols2" },
      h("div", {}, inputs.map(x => x[2]),
        h("div", { class: "row" }, h("button", { class: "small", onclick: () => { L.names = {}; inputs.forEach(x => { x[1].value = ""; }); lookChanged(); } }, "Restore Original Names"))),
      status),
    menu);
}

function viewLook() {
  const sv = S.look.values, def = S.look.defaults;
  if (!lookW) lookW = startLook();
  const L = lookW;
  lookBarEl = h("div", {});
  const glass = h("div", {});
  function drawGlass() {
    const chip = (on, text, set) => h("button", { class: "chip", "aria-pressed": String(on), onclick: () => { set(); lookChanged(); drawGlass(); } }, text);
    put(glass,
      h("div", { class: "field" }, h("div", { class: "lab" }, "Glass Style"),
        h("div", { class: "chips" }, chip(!L.glassClear, "Tinted", () => { L.glassClear = false; }), chip(L.glassClear, "Transparent", () => { L.glassClear = true; })),
        h("div", { class: "hint" }, "Transparent glass lets the picture and the colors of your cards show through, so they look more vibrant.")),
      L.glassClear
        ? [lookSlider("How Transparent", "glassLevel", 0, 100, 1, "%", "Higher is clearer. 100% is plain frosted glass with no tint."),
           h("div", { class: "chips", style: { marginBottom: "12px" } }, [["A Little", 30], ["Medium", 55], ["Very", 80], ["Clear", 100]].map(([t, n]) =>
             h("button", { class: "chip", onclick: () => { L.glassLevel = n; lookChanged(); render(); } }, t)))]
        : lookSlider("How Solid the Glass Is", "glassOpacity", 0, 100, 1, "%", "Low shows the picture through the cards. High makes them solid."));
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
  return h("div", {},
    namesCard(),
    h("div", { class: "card" }, h("h2", {}, "Colors and Built-In Looks"),
      h("div", { class: "field" }, h("div", { class: "lab" }, "Built-In Looks"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "Pick one to try it. Nothing is saved until you press “Save”."),
        h("div", { class: "chips" }, S.look.presets.map(p => h("button", { class: "chip", onclick: () => {
          const base = clone(def); base.tabs = Object.assign({}, def.tabs);
          for (const k of PAINT_KEYS) base[k] = clone(lookW[k]);              // the colors you gave single cards and labels stay
          const pl = clone(p.look); const tabs = Object.assign({}, base.tabs, pl.tabs || {}); delete pl.tabs;
          lookW = Object.assign(base, pl, { tabs });
          render(); lookChanged();
        } }, h("span", { class: "dot", style: { background: p.look.accent || def.accent } }), p.name)))),
      h("div", { class: "grid cols2" },
        h("div", {},
          colorField("Main Color", "accent", "The color of the active tab, bars, icons and the edge of a card you point at.", ["#8ab4ff", "#5ec8ff", "#7ee0a0", "#ffa66b", "#ff8fb5", "#c9a0ff", "#ffd36b", "#c3cad6"]),
          colorField("Glass Color", "glass", "The tint of every card and tile.", ["#0d121e", "#06141f", "#07150d", "#1c0f12", "#1a0c16", "#111214"])),
        glass),
      h("div", { class: "field" }, h("div", { class: "lab" }, "Color of Each Tab"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "Each tab can have its own accent color."),
        h("div", { class: "grid cols2 tabcolors" }, tabRows)),
      h("p", { class: "muted small" }, "To give single cards, tiles, bookmarks or labels their own colors, open the Colors screen.")),
    h("div", { class: "card" }, h("h2", {}, "Preview, Shapes and Space"),
      h("div", { class: "grid cols2" },
        h("div", {}, h("p", { class: "muted" }, framed ? "The dashboard around this panel changes while you move the sliders, so you can see the real result." : "A small sample of how cards and tabs look."), mock),
        h("div", {},
          lookSlider("How Round the Corners Are", "radius", 0, 40, 1, " px"),
          lookSlider("Brightness of the Card Edge", "edge", 0, 40, 0.5, "%"),
          lookSlider("Space at the Left and Right", "side", 0, 120, 2, " px"),
          h("p", { class: "muted small" }, "The height of the music player is changed on the dashboard itself, with the small arrows button next to the shrink button on the player.")))),
    lookBarEl);
}

function labelIconSample(style) {
  return h("span", { class: "lis lis-" + style }, h("img", { src: iconInfo("mdi-movie-open").url, class: "mdi", alt: "" }));
}

function viewColors() {
  if (!lookW) lookW = startLook();
  const L = lookW, P = S.paint;
  lookBarEl = h("div", {});
  setTimeout(() => { lookPreview(!lookDirty()); refreshLookBar(); }, 0);

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
    followers.push(draw);
    return h("details", { class: "card", open: open }, h("summary", {}, h("b", {}, title), h("span", { class: "badge" }, String(items.length))),
      h("p", { class: "muted small" }, hint),
      h("div", { class: "row bulk" }, h("span", { class: "lab" }, "One Color for All Below:"), colorInput(bulk, "One color for all in " + title, v => { bulk = v; }),
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
    h("div", { class: "card" }, h("h2", {}, "Colors of Cards, Tiles and Bookmarks"),
      h("p", { class: "muted" }, "Give single service cards, the calendar, the tiles of the Stats tab and the bookmarks of the Links tab their own color: a tint, a colored edge and a soft glow. It looks best with Transparent Glass on the Look screen."),
      h("p", { class: "muted small" }, "To see a color on the dashboard, open the tab that has it (Home, Stats or Links). The preview stays there. Come back here to keep it with Save."),
      h("div", { class: "field" }, h("div", { class: "lab" }, "Color Style"), styleChips,
        h("div", { class: "hint" }, "Gradient: the color is strong on one side and fades out across the card. Solid: the same color across the whole card.")),
      lookSlider("How Strong the Colors Are", "paintStrength", 0, 100, 1, "%", "Higher makes the color, the edge and the glow stronger, so the color is not washed out."),
      h("div", { class: "field" }, h("div", { class: "lab" }, "One Color for Everything"), paintAll)),
    section("Service Cards", "The cards of the Home tab, such as Portainer or Downtify.", P.cards, L.cards, it => it.id, it => it.group, true),
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
      h("div", { class: "field", style: { marginTop: "14px" } }, h("div", { class: "lab" }, "Icon Style"), h("div", { class: "hint", style: { marginBottom: "8px" } }, "How the small icon next to every label looks."), styles)),
    lookBarEl);
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
  const refreshBar = () => put(bar, saveBar(dirty(), save, () => { discardPreview(); render(); }, "Save", h("button", { onclick: reset }, "Restore Default Sliders")));
  const preview = () => { send({ type: "bg", image: B.url || b.image, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); refreshBar(); };
  async function save() {
    try { await api("POST", "/api/background", { url: B.url || undefined, blur: B.blur, saturate: B.saturate, brightness: B.brightness, opacity: B.opacity }); toast("Background saved."); await afterChange(false); }
    catch (e) { fail(e); }
  }
  async function reset() {
    try { await api("POST", "/api/background/reset", {}); send({ type: "clear" }); toast("The sliders are back to their default values."); await afterChange(true); } catch (e) { fail(e); }
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
      h("div", { class: "card" }, h("h2", {}, "The Picture"), pic,
        h("div", { class: "row", style: { marginTop: "12px" } }, file, h("button", { class: "primary", onclick: () => file.click() }, "Upload a Picture…")),
        h("p", { class: "hint muted small" }, "JPG, PNG, WebP, GIF or AVIF, up to 14 MB. After a new picture the dashboard restarts for about 10 seconds."),
        b.mounted === false ? h("p", { class: "small", style: { color: "var(--bad)" } }, "The dashboard cannot see its pictures folder yet, so an uploaded picture will not show. Run: sudo homelab-setup upgrade") : null,
        h("div", { class: "field", style: { marginTop: "12px" } }, h("label", {}, "Or Use a Picture from the Web"), h("div", { class: "row" }, h("div", { class: "grow" }, url),
          h("button", { onclick: () => { B.url = url.value.trim(); if (!B.url) return toast("Type a web address first.", true); preview(); toast("Press Save to keep it."); } }, "Use This Address")))),
      h("div", { class: "card" }, h("h2", {}, "How It Looks Behind the Cards"),
        h("div", { class: "field" }, h("div", { class: "slider" }, h("span", { class: "lab" }, "Blur"), blurVal,
          h("input", { type: "range", min: 0, max: 6, step: 1, value: BLURS.indexOf(B.blur) < 0 ? 2 : BLURS.indexOf(B.blur), "aria-label": "Blur",
            oninput: ev => { B.blur = BLURS[Number(ev.target.value)]; blurVal.textContent = B.blur; preview(); } })), h("div", { class: "hint" }, "none is sharp. 3xl is very soft.")),
        slider("Brightness", "brightness", "Low makes the picture darker, so the text is easy to read."),
        slider("Color", "saturate", "Low turns the picture toward gray."),
        slider("Strength", "opacity", "How much of the picture shows through the dark cover."))),
    bar);
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
  async function quickIcon(g, it) {                       // change only the icon of a card
    const pick = await pickIcon(it.icon);
    if (pick === it.icon) return;
    await op({ op: "edit", group: g.group, old: it.name, name: it.name, href: it.href, icon: pick, description: it.description, dot: !!it.siteMonitor }, "Icon saved.");
  }
  async function remove(g, it) {
    if (!await confirmBox("Remove “" + it.name + "”?", "It disappears from the dashboard. Undo can bring it back.", "Remove It", true)) return;
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
      h("button", { class: "small", onclick: () => groupMenu(g) }, "Rename"), h("button", { class: "small danger", onclick: () => groupRemove(g) }, "Remove Group")),
    items(g).map((it, i) => h("div", { class: "item" }, iconEl(it.icon),
      h("div", { class: "txt" }, h("b", {}, it.name), h("span", {}, [it.description, it.href].filter(Boolean).join("  ·  ") || "No address")),
      isCards && it.managed ? h("span", { class: "badge", title: "Made by the lab; it keeps the address right" }, "lab card") : null,
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " up", disabled: i === 0, onclick: () => reorder(g, i, -1) }, "↑"),
      h("button", { class: "small icon", "aria-label": "Move " + it.name + " down", disabled: i === items(g).length - 1, onclick: () => reorder(g, i, 1) }, "↓"),
      isCards && !it.locked ? h("button", { class: "small", onclick: () => quickIcon(g, it) }, "Icon…") : null,
      h("button", { class: "small", onclick: () => editor(g, it) }, "Change"),
      h("button", { class: "small danger", onclick: () => remove(g, it) }, "Remove"))),
    h("div", { style: { marginTop: "10px" } }, h("button", { class: "small", onclick: () => editor(g, null) }, "+ Add a " + (word === "card" ? "Card" : "Link") + " here"))));

  return h("div", {},
    h("div", { class: "card" }, h("h2", {}, isCards ? "Cards on the Dashboard" : "Links (Bookmarks)"),
      h("p", { class: "muted" }, isCards ? "The cards of Home. Add your own cards for any web page, change a name or text, put them in another order or group, or remove them."
        : "The bookmarks of the Links tab, in groups. Add your own sites with their icons."),
      h("button", { class: "primary", onclick: () => editor(groups[0] || null, null) }, "+ Add a " + (word === "card" ? "Card" : "Link"))),
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
