/* >>> homelab groups >>> */
(function () {
  var queued = false;
  function slug(t) { return String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }
  function label() {
    queued = false;
    var groups = document.querySelectorAll(".bookmark-group, .services-group");
    for (var i = 0; i < groups.length; i++) {
      var h = groups[i].querySelector(".bookmark-group-name, .service-group-name");
      var s = h ? slug(h.textContent.replace(/\s*\u00b7\s*\d+$/, "")) : "";
      if (s && groups[i].getAttribute("data-group") !== s) groups[i].setAttribute("data-group", s);
    }
    var marks = document.querySelectorAll(".bookmark > a");
    for (var j = 0; j < marks.length; j++) {
      var n = marks[j].querySelector(".bookmark-name");
      var t = n ? slug(n.textContent) : "";
      if (t && marks[j].getAttribute("data-bm") !== t) marks[j].setAttribute("data-bm", t);
    }
  }
  function soon() { if (!queued) { queued = true; window.requestAnimationFrame(label); } }
  soon();
  new MutationObserver(soon).observe(document.documentElement, { childList: true, subtree: true });
})();
/* <<< homelab groups <<< */

/* >>> homelab player >>> */
(function () {
  var box = null, frame = null, src = "", queued = false;
  var style = document.createElement("style");
  style.textContent = "#hl-player-box{position:absolute;z-index:5;overflow:hidden;border-radius:10px;}" +
    "#hl-player-box.hl-away{left:-10000px !important;pointer-events:none;}" +
    "#hl-player{display:block;width:calc(100% + 32px);height:100%;border:0;}";
  document.head.appendChild(style);

  function cardFrame() { return document.querySelector("#navidrome-card iframe"); }
  function real(u) { return !!u && u.indexOf("about:") !== 0; }

  function address(cf) {
    var u = cf.getAttribute("src") || "";
    if (!real(u)) return src;
    if (location.protocol === "https:" && u.indexOf("http:") === 0) {
      var a = document.querySelector('#navidrome-card a[href^="https:"]');
      if (a) { try { return new URL(a.href).origin; } catch (e) {  } }
    }
    return u;
  }

  function make(u) {
    box = document.createElement("div");
    box.id = "hl-player-box";
    box.className = "hl-away";
    frame = document.createElement("iframe");
    frame.id = "hl-player";
    frame.setAttribute("allow", "autoplay; fullscreen");
    frame.src = u;
    box.appendChild(frame);
    document.body.appendChild(box);
  }

  function scroller(el) {
    for (var e = el; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      var o = window.getComputedStyle(e).overflowY;
      if (o === "auto" || o === "scroll" || e.hasAttribute("data-hl-locked")) return e;
    }
    return null;
  }

  function place() {
    queued = false;
    var cf = cardFrame(), host = null, sc = null;
    if (cf) {
      var u = address(cf);
      if (u) {
        if (!box) make(u); else if (u !== src) frame.src = u;
        src = u;
      }
      if (real(cf.getAttribute("src"))) cf.setAttribute("src", "about:blank");
      if (cf.parentElement && !cf.closest(".hl-folded") && !document.documentElement.classList.contains("hl-sliding")) { host = cf.parentElement.getBoundingClientRect(); sc = scroller(cf.parentElement); }
    }
    if (!box) return;
    if (host && host.width > 0 && host.height > 0) {
      var home = sc || document.body;
      if (box.parentNode !== home) {
        if (sc && window.getComputedStyle(sc).position === "static") sc.style.position = "relative";
        home.appendChild(box);
      }
      box.className = "";
      box.style.left = "0px";
      box.style.top = "0px";
      var o = box.getBoundingClientRect();
      var z = parseFloat(window.getComputedStyle(document.documentElement).zoom) || 1;
      box.style.cssText = "left:" + ((host.left - o.left) / z) + "px;top:" + ((host.top - o.top) / z) + "px;width:" + (host.width / z) + "px;height:" + (host.height / z) + "px;";
    } else if (box.className !== "hl-away") {
      box.className = "hl-away";
    }
  }

  function soon() { if (!queued) { queued = true; window.requestAnimationFrame(place); } }
  soon();
  new MutationObserver(soon).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", soon);
  window.setInterval(soon, 500);
})();
/* <<< homelab player <<< */

/* >>> homelab extras >>> */
(function () {
  var root = document.documentElement, queued = false;
  function store(key, value) { try { if (value === undefined) return window.localStorage.getItem(key); window.localStorage.setItem(key, value); } catch (e) {  } return null; }
  function all(sel, from) { return Array.prototype.slice.call((from || document).querySelectorAll(sel)); }

  function health() {
    all(".service.hl-down").forEach(function (li) { li.classList.remove("hl-down"); });
    all(".service .site-monitor-status > div").forEach(function (d) {
      var li = d.closest(".service");
      if (li && /rose|red/.test(d.className)) li.classList.add("hl-down");
    });
  }

  function moving() {
    var until = Date.now() + 450;
    root.classList.add("hl-sliding");
    (function follow() {
      window.dispatchEvent(new Event("resize"));
      if (Date.now() < until) window.requestAnimationFrame(follow);
      else { root.classList.remove("hl-sliding"); window.dispatchEvent(new Event("resize")); }
    })();
  }

  function shrinkButton() {
    root.classList.toggle("hl-player-min", store("hl-player-shrunk") === "1");
    var title = document.querySelector("#navidrome-card .service-title");
    if (!title || title.querySelector(".hl-shrink")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "hl-shrink";
    b.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var on = !root.classList.contains("hl-player-min");
      store("hl-player-shrunk", on ? "1" : "0");
      moving();
      root.classList.toggle("hl-player-min", on);
      label(b);
    });
    label(b);
    title.appendChild(b);
  }
  function label(b) {
    var min = root.classList.contains("hl-player-min");
    b.setAttribute("aria-label", min ? "Show the player" : "Shrink the player");
    b.setAttribute("title", min ? "Show the player" : "Shrink the player");
    b.setAttribute("aria-expanded", min ? "false" : "true");
  }

  function folded() { try { return JSON.parse(store("hl-folded") || "[]"); } catch (e) { return []; } }
  function opened() { try { return JSON.parse(store("hl-opened") || "[]"); } catch (e) { return []; } }
  var PANEL_GROUPS = ["Customize", "Edit Links", "Terminal"];
  var FOLDED_AT_FIRST = ["Edit Links", "Terminal"];
  function isFolded(name) { return folded().indexOf(name) >= 0 || (FOLDED_AT_FIRST.indexOf(name) >= 0 && opened().indexOf(name) < 0); }
  function slide(g, fold) {
    var panel = g.querySelector(":scope > div"), still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!panel || still) { g.classList.toggle("hl-folded", fold); window.dispatchEvent(new Event("resize")); return; }
    if (g.querySelector("#navidrome-card")) moving();
    else { var until = Date.now() + 450; (function follow() { window.dispatchEvent(new Event("resize")); if (Date.now() < until) window.requestAnimationFrame(follow); })(); }
    function done() { panel.style.maxHeight = ""; panel.removeEventListener("transitionend", ended); }
    function ended(ev) { if (ev.target === panel && ev.propertyName === "max-height") done(); }
    panel.addEventListener("transitionend", ended);
    window.setTimeout(done, 600);
    if (fold) {
      panel.style.maxHeight = panel.scrollHeight + "px";
      void panel.offsetHeight;
      g.classList.add("hl-folded");
    } else {
      panel.style.maxHeight = "0px";
      g.classList.remove("hl-folded");
      void panel.offsetHeight;
      panel.style.maxHeight = panel.scrollHeight + "px";
    }
  }
  var FRAMES = {
    "Customize": { key: "hl-h-customize", css: "--hl-h-customize", min: 400, max: 1600, vh: 0.88, top: 1200, label: "Customize Height", sel: "#customize-card iframe" },
    "Terminal": { key: "hl-h-terminal", css: "--hl-h-terminal", min: 240, max: 1400, vh: 0.7, top: 720, label: "Terminal Height", sel: "#terminal-card iframe" }
  };
  function frameHeights() {
    var w = document.getElementById("inner_wrapper");
    if (!w) return;
    Object.keys(FRAMES).forEach(function (n) {
      var f = FRAMES[n], v = parseInt(store(f.key) || "", 10);
      if (v >= f.min && v <= f.max) { if (w.style.getPropertyValue(f.css) !== v + "px") w.style.setProperty(f.css, v + "px"); }
      else if (w.style.getPropertyValue(f.css)) w.style.removeProperty(f.css);
    });
  }
  function groupHeight(g, name) {
    var f = FRAMES[name];
    if (!f || g.querySelector(":scope > .hl-gheight")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "hl-height hl-gheight";
    b.setAttribute("aria-label", "Change the height of " + name);
    b.setAttribute("title", "Change the height");
    b.setAttribute("aria-expanded", "false");
    var pop = document.createElement("aside");
    pop.className = "hl-height-pop";
    pop.hidden = true;
    var lab = document.createElement("label");
    lab.textContent = f.label;
    var val = document.createElement("span");
    var rng = document.createElement("input");
    rng.type = "range"; rng.min = String(f.min); rng.max = String(f.max); rng.step = "20";
    rng.setAttribute("aria-label", f.label);
    var back = document.createElement("button");
    back.type = "button";
    back.textContent = "Default";
    function current() {
      var v = parseInt(store(f.key) || "", 10);
      if (v >= f.min && v <= f.max) return v;
      var fr = document.querySelector(f.sel);
      if (fr && fr.offsetHeight > 100) return Math.min(f.max, Math.max(f.min, Math.round(fr.offsetHeight)));
      return Math.min(f.max, Math.max(f.min, Math.round(Math.min(window.innerHeight / (parseFloat(getComputedStyle(document.documentElement).zoom) || 1) * f.vh, f.top))));
    }
    function show() { var v = current(); rng.value = String(v); val.textContent = v + " px"; }
    function changed() { frameHeights(); show(); window.dispatchEvent(new Event("resize")); }
    rng.addEventListener("input", function () { store(f.key, rng.value); changed(); });
    back.addEventListener("click", function () { store(f.key, ""); changed(); });
    ["click", "mousedown", "pointerdown", "touchstart"].forEach(function (t) { pop.addEventListener(t, function (ev) { ev.stopPropagation(); }); });
    function close() { pop.hidden = true; b.setAttribute("aria-expanded", "false"); }
    b.addEventListener("click", function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      pop.hidden = !pop.hidden;
      b.setAttribute("aria-expanded", pop.hidden ? "false" : "true");
      if (!pop.hidden) show();
    });
    document.addEventListener("click", function (ev) { if (!pop.hidden && !pop.contains(ev.target) && ev.target !== b) close(); });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !pop.hidden) { close(); b.focus(); } });
    pop.appendChild(lab); pop.appendChild(rng); pop.appendChild(val); pop.appendChild(back);
    g.appendChild(b);
    g.appendChild(pop);
  }

  var LOCKED = "#hl-player-box, #customize-card iframe, #linkedit-card iframe, #terminal-card iframe", held = null;
  function scrolling(el) {
    for (var e = el; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      if (e.hasAttribute("data-hl-locked")) return e;
      var o = window.getComputedStyle(e).overflowY;
      if (o === "auto" || o === "scroll") return e;
    }
    return null;
  }
  function lock(el) {
    if (held) return;
    var box = scrolling(el), t = box || root;
    var bar = box ? box.offsetWidth - box.clientWidth - (parseFloat(window.getComputedStyle(box).borderLeftWidth) || 0) - (parseFloat(window.getComputedStyle(box).borderRightWidth) || 0)
                  : window.innerWidth - root.clientWidth;
    held = { el: t, overflow: t.style.overflowY, gutter: t.style.scrollbarGutter };
    t.setAttribute("data-hl-locked", "");
    if (bar > 0) t.style.scrollbarGutter = "stable";
    t.style.overflowY = "hidden";
    root.classList.add("hl-lock");
  }
  function unlock() {
    if (!held) return;
    held.el.style.overflowY = held.overflow;
    held.el.style.scrollbarGutter = held.gutter;
    held.el.removeAttribute("data-hl-locked");
    held = null;
    root.classList.remove("hl-lock");
  }
  var hovered = null;
  function sync() {
    if (hovered && document.activeElement === hovered) lock(hovered); else unlock();
  }
  if (window.matchMedia && window.matchMedia("(hover: hover)").matches) {
    function leave(was) {
      if (was && document.activeElement === was) { try { was.blur(); } catch (e) {  } }
    }
    document.addEventListener("mouseover", function (ev) {
      var over = ev.target && ev.target.closest ? ev.target.closest(LOCKED) : null, now = over ? (over.tagName === "IFRAME" ? over : over.querySelector("iframe")) : null, was = hovered;
      hovered = now;
      if (was && was !== now) leave(was);
      sync();
    });
    root.addEventListener("mouseleave", function () { var was = hovered; hovered = null; leave(was); sync(); });
    window.addEventListener("blur", function () { window.setTimeout(sync, 0); });
    window.addEventListener("focus", function () { window.setTimeout(sync, 0); });
    document.addEventListener("mousedown", function () { window.setTimeout(sync, 0); }, true);
  }

  function groups() {
    all(".services-group, .bookmark-group").forEach(function (g) {
      var h = g.querySelector(".service-group-name, .bookmark-group-name");
      if (!h) return;
      var name = h.textContent.replace(/\s*·\s*\d+$/, "").trim(), n = g.querySelectorAll("li.service, li.bookmark").length;
      if (PANEL_GROUPS.indexOf(name) >= 0) h.removeAttribute("data-count");
      else if (n && h.getAttribute("data-count") !== String(n)) h.setAttribute("data-count", String(n));
      g.classList.toggle("hl-folded", isFolded(name));
      groupHeight(g, name);
      if (g.querySelector(":scope > .hl-gfold")) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "hl-gfold";
      b.setAttribute("aria-label", "Fold or open " + name);
      b.addEventListener("click", function () {
        var fold = !isFolded(name), cur = folded().filter(function (x) { return x !== name; }), op = opened().filter(function (x) { return x !== name; });
        if (fold) { if (FOLDED_AT_FIRST.indexOf(name) < 0) cur.push(name); } else if (FOLDED_AT_FIRST.indexOf(name) >= 0) op.push(name);
        store("hl-folded", JSON.stringify(cur));
        store("hl-opened", JSON.stringify(op));
        b.setAttribute("aria-expanded", fold ? "false" : "true");
        slide(g, fold);
      });
      b.setAttribute("aria-expanded", isFolded(name) ? "false" : "true");
      g.appendChild(b);
    });
  }

  function sharp() {
    var w = document.getElementById("inner_wrapper");
    if (!w) return;
    var f = window.getComputedStyle(w).getPropertyValue("backdrop-filter") || "";
    var m = /blur\(\s*([0-9.]+)/.exec(f);
    root.classList.toggle("hl-sharp", !m || parseFloat(m[1]) === 0);
  }
  window.addEventListener("hl-look-changed", sharp);

  function playerHeight() {
    var w = document.getElementById("inner_wrapper"), v = parseInt(store("hl-player-h") || "", 10);
    if (!w) return;
    if (v >= 240 && v <= 1000) { if (w.style.getPropertyValue("--lk-player-h") !== v + "px") w.style.setProperty("--lk-player-h", v + "px"); }
    else if (w.style.getPropertyValue("--lk-player-h")) w.style.removeProperty("--lk-player-h");
  }
  function heightButton() {
    var title = document.querySelector("#navidrome-card .service-title");
    if (!title || title.querySelector(".hl-height")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "hl-height";
    b.setAttribute("aria-label", "Change the height of the player");
    b.setAttribute("title", "Change the height of the player");
    b.setAttribute("aria-expanded", "false");
    var pop = document.createElement("div");
    pop.className = "hl-height-pop";
    pop.hidden = true;
    var lab = document.createElement("label");
    lab.textContent = "Player Height";
    var val = document.createElement("span");
    var rng = document.createElement("input");
    rng.type = "range"; rng.min = "240"; rng.max = "1000"; rng.step = "10";
    rng.setAttribute("aria-label", "Player height");
    var back = document.createElement("button");
    back.type = "button";
    back.textContent = "Default";
    function current() { var v = parseInt(store("hl-player-h") || "", 10); if (v >= 240 && v <= 1000) return v; var w = document.getElementById("inner_wrapper"); return Math.round(parseFloat(window.getComputedStyle(w).getPropertyValue("--lk-player-h")) || 600); }
    function show() { var v = current(); rng.value = String(v); val.textContent = v + " px"; }
    rng.addEventListener("input", function () { store("hl-player-h", rng.value); playerHeight(); show(); window.dispatchEvent(new Event("resize")); });
    back.addEventListener("click", function () { store("hl-player-h", ""); playerHeight(); show(); window.dispatchEvent(new Event("resize")); });
    ["click", "mousedown", "pointerdown", "touchstart"].forEach(function (t) { pop.addEventListener(t, function (ev) { ev.stopPropagation(); }); });
    b.addEventListener("click", function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      pop.hidden = !pop.hidden;
      b.setAttribute("aria-expanded", pop.hidden ? "false" : "true");
      if (!pop.hidden) show();
    });
    document.addEventListener("click", function (ev) { if (!pop.hidden && !pop.contains(ev.target) && ev.target !== b) { pop.hidden = true; b.setAttribute("aria-expanded", "false"); } });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !pop.hidden) { pop.hidden = true; b.setAttribute("aria-expanded", "false"); b.focus(); } });
    pop.appendChild(lab); pop.appendChild(rng); pop.appendChild(val); pop.appendChild(back);
    title.appendChild(b);
    title.appendChild(pop);
  }

  var namesPreview = null, textWas = new WeakMap(), textSet = new WeakMap(), renamed = false;
  function cssText(name) {
    var w = document.getElementById("inner_wrapper");
    var v = w ? (window.getComputedStyle(w).getPropertyValue(name) || "").trim() : "";
    return v.length >= 2 && v.charAt(0) === '"' && v.charAt(v.length - 1) === '"' ? v.slice(1, -1) : "";
  }
  function theNames() {
    if (namesPreview) return namesPreview;
    var w = document.getElementById("inner_wrapper");
    return { homelab: cssText("--hl-name-homelab"), main: cssText("--hl-name-main"), backup: cssText("--hl-name-backup"), src: cssText("--hl-logo-src"), link: cssText("--hl-logo-link"),
             size: w ? parseFloat(window.getComputedStyle(w).getPropertyValue("--hl-logo-size")) || 48 : 48 };
  }
  function nameOf(text, N) {
    var t = text;
    t = t.replace(/^(\s*)connect (main|backup) drive(\s*)$/i, function (all, a, k, z) { var n = N[k.toLowerCase()]; return n ? a + "Connect " + n + " Drive" + z : all; });
    t = t.replace(/^(\s*)homelab(\s*)$/i, function (all, a, z) { return N.homelab ? a + N.homelab + z : all; });
    t = t.replace(/\bmain pool\b/gi, function (all) { return N.main || all; });
    t = t.replace(/\bbackup pool\b/gi, function (all) { return N.backup || all; });
    return t;
  }
  var NAMED = /homelab|main pool|backup pool|connect (main|backup) drive/i;
  function rename() {
    var N = theNames(), w = document.getElementById("inner_wrapper");
    if (!w || !(N.homelab || N.main || N.backup || renamed)) return;
    var walk = document.createTreeWalker(w, NodeFilter.SHOW_TEXT, null), n;
    while ((n = walk.nextNode())) {
      var cur = n.nodeValue, mine = textWas.has(n);
      if (!mine && !NAMED.test(cur)) continue;
      var orig = mine && textSet.get(n) === cur ? textWas.get(n) : cur;
      var next = nameOf(orig, N);
      if (next !== orig) {
        textWas.set(n, orig); textSet.set(n, next); renamed = true;
        if (cur !== next) n.nodeValue = next;
      } else if (mine) {
        if (cur !== orig && textSet.get(n) === cur) n.nodeValue = orig;
        textWas.delete(n); textSet.delete(n);
      }
    }
  }
  var logoShown = "";
  function logo() {
    var N = theNames(), wrap = document.getElementById("widgets-wrap"), el = document.getElementById("hl-logo");
    var tile = wrap ? wrap.querySelector(":scope > .widget-container:has(.information-widget-resource)") || wrap.querySelector(":scope > .widget-container") : null;
    var ok = N.src && /^(https?:\/\/[^\s"'()\\<>]+|data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+\/]+={0,2})$/.test(N.src);
    var link = N.link && /^https?:\/\/[^\s"'()\\<>]+$/.test(N.link) ? N.link : "";
    if (!tile || !ok) {
      if (el) el.remove();
      logoShown = "";
      all(".hl-has-logo").forEach(function (t) { t.classList.remove("hl-has-logo"); });
      return;
    }
    var key = N.src + "|" + link;
    if (el && (el.tagName === "A") !== !!link) { el.remove(); el = null; }
    if (!el) {
      el = document.createElement(link ? "a" : "span");
      el.id = "hl-logo";
      var img = document.createElement("img");
      img.alt = "";
      img.setAttribute("decoding", "async");
      el.appendChild(img);
      logoShown = "";
    }
    if (link) { el.setAttribute("href", link); el.setAttribute("target", "_blank"); el.setAttribute("rel", "noopener noreferrer"); el.setAttribute("aria-label", "Logo (opens a link)"); }
    if (logoShown !== key) { el.firstChild.src = N.src; logoShown = key; }
    var h = Math.max(24, Math.min(96, N.size || 48)) + "px";
    if (el.firstChild.style.height !== h) el.firstChild.style.height = h;
    if (tile.firstElementChild !== el) tile.insertBefore(el, tile.firstChild);
    if (!tile.classList.contains("hl-has-logo")) tile.classList.add("hl-has-logo");
  }
  window.addEventListener("hl-names", function (e) { namesPreview = e.detail || null; rename(); logo(); });

  function searchButton() {
    var host = document.getElementById("information-widgets-right");
    if (!host || document.getElementById("hl-search-btn")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.id = "hl-search-btn";
    b.setAttribute("aria-label", "Search");
    b.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><span>Search</span>';
    b.addEventListener("click", function () {
      var open = root.classList.toggle("hl-search-open");
      var input = document.querySelector("#information-widgets .information-widget-search input");
      if (open && input) input.focus();
    });
    host.appendChild(b);
  }

  function tabName() {
    var t = document.querySelector('#myTab button[aria-selected="true"]');
    var name = t ? t.textContent.trim() : "";
    if (name && root.getAttribute("data-tab") !== name) root.setAttribute("data-tab", name);
  }

  function bars() {
    all('li[id^="stat-"] .service-block').forEach(function (blk) {
      var v = blk.querySelector(".service-block-value, .font-thin");
      var m = v && /^\s*(\d+(?:\.\d+)?)\s*%\s*$/.exec(v.textContent);
      if (!m) { if (blk.classList.contains("hl-bar")) blk.classList.remove("hl-bar", "hl-amber", "hl-red"); return; }
      var pct = Math.max(0, Math.min(100, parseFloat(m[1])));
      blk.classList.add("hl-bar");
      blk.classList.toggle("hl-amber", pct >= 85 && pct < 95);
      blk.classList.toggle("hl-red", pct >= 95);
      if (blk.style.getPropertyValue("--hl-pct") !== pct + "%") blk.style.setProperty("--hl-pct", pct + "%");
    });
  }

  function night() {
    var d = new Date(), h = d.getHours() + d.getMinutes() / 60;
    var n = Math.max(0, Math.min(1, (Math.abs(h - 13) - 5) / 6));
    root.style.setProperty("--hl-night", n.toFixed(2));
  }

  var calWatch = null, calChrome = 70;
  function calendar() {
    var lg = document.getElementById("layout-groups");
    if (!lg) return;
    var cal = lg.querySelector(":scope > .services-group:has(li[id^='cal-'])"), media = lg.querySelector(":scope > .services-group:has(#navidrome-card)");
    var off = !cal || !media || !window.matchMedia("(min-width: 1500px)").matches;
    if (off) {
      if (lg.classList.contains("hl-cal-a") || lg.classList.contains("hl-cal-b")) { lg.classList.remove("hl-cal-a", "hl-cal-b"); lg.style.removeProperty("--hl-cal-h"); lg.style.removeProperty("--hl-cal-cell"); }
      return;
    }
    var others = Array.prototype.filter.call(lg.children, function (g) { return g !== cal && g !== media && g.classList.contains("services-group") && g.offsetHeight > 0; });
    if (calWatch !== lg && window.ResizeObserver) {
      if (calWatch && calWatch.ro) calWatch.ro.disconnect();
      var ro = new ResizeObserver(function () { soon(); });
      ro.observe(media); others.forEach(function (g) { ro.observe(g); });
      lg.ro = ro; calWatch = lg;
    }
    var cols = Math.max(1, getComputedStyle(lg).gridTemplateColumns.split(" ").length - 1), gap = parseFloat(getComputedStyle(lg).rowGap) || 8;
    var rows = [];
    others.forEach(function (g, i) { var r = Math.floor(i / cols); rows[r] = Math.max(rows[r] || 0, g.offsetHeight); });
    var right = rows.reduce(function (a, b) { return a + b; }, 0) + gap * Math.max(0, rows.length - 1);
    var avail = right - media.offsetHeight - gap;
    var state = lg.classList.contains("hl-cal-a") ? "a" : lg.classList.contains("hl-cal-b") ? "b" : "c";
    var toA = state === "a" ? 380 : 392, toB = state === "c" ? 282 : 270;
    var next = avail >= toA ? "a" : avail >= toB ? "b" : "c";
    var ul = cal.querySelector(".services-list"), month = document.getElementById("cal-month");
    if (state !== "b" && ul && cal.offsetHeight > 0) calChrome = cal.offsetHeight - ul.offsetHeight;
    lg.classList.toggle("hl-cal-a", next === "a"); lg.classList.toggle("hl-cal-b", next === "b");
    if (next === "c" || !month) { lg.style.removeProperty("--hl-cal-h"); lg.style.removeProperty("--hl-cal-cell"); return; }
    var h = Math.floor(next === "a" ? avail - calChrome : avail);
    lg.style.setProperty("--hl-cal-h", h + "px");
    var days = month.querySelectorAll("button[style*='14%']"), box = month.querySelector(".service-container");
    if (days.length >= 28 && box) {
      var rowsN = Math.round(days.length / 7), cell = days[0].offsetHeight, title = month.querySelector(".service-title");
      var fixed = (title ? title.offsetHeight : 0) + box.offsetHeight + 8 - rowsN * cell;
      lg.style.setProperty("--hl-cal-cell", Math.max(18, Math.min(44, Math.floor((h - fixed) / rowsN))) + "px");
    }
  }

  function linkRows() {
    var lg = document.getElementById("layout-groups");
    if (!lg) return;
    var items = Array.prototype.filter.call(lg.children, function (g) { return g.classList.contains("bookmark-group"); });
    var on = items.length > 0 && window.matchMedia("(min-width: 1500px)").matches && !lg.querySelector("#navidrome-card, #customize-card, li[id^='stat-']");
    var half = Math.ceil(items.length / 2);
    items.forEach(function (g, k) {
      var want = on ? String(k < half ? 2 * k : 2 * (k - half) + 1) : "";
      if (g.style.order !== want) g.style.order = want;
    });
  }

  function wording() {
    all("#information-widgets .pr-1").forEach(function (e) { if (e.children.length === 0 && e.textContent === "UP") e.textContent = "Uptime"; });
    all("li.service details > summary div").forEach(function (e) {
      var said = e.textContent.replace(/\s+/g, " ").trim();
      if (said !== "API Error Information" && said !== "API Error") return;
      var kids = Array.prototype.slice.call(e.childNodes).filter(function (n) { return n.nodeType === 3; });
      kids.forEach(function (n, i) { n.nodeValue = i === 0 ? "Service Unavailable" : ""; });
    });
    all("#information-widgets span.primary-text").forEach(function (e) {
      if (e.childNodes.length !== 1 || e.firstChild.nodeType !== 3 || e.firstChild.nodeValue.trim() !== "API Error") return;
      var up = e.parentElement, hops = 0;
      while (up && hops < 5 && !/connect .+ drive/i.test(up.textContent)) { up = up.parentElement; hops++; }
      if (up && hops < 5 && /connect .+ drive/i.test(up.textContent) && up.querySelectorAll("span.primary-text").length === 1) e.firstChild.nodeValue = "No Drive";
    });
  }

  var BELL = { data: null, at: 0, busy: false, failed: false };
  var BELL_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>';
  function panelUrl(hash) { return "https://" + window.location.hostname + ":1100/" + (hash ? "#" + hash : ""); }
  function ago(sec) {
    var m = Math.max(0, Math.round(sec / 60));
    return m < 2 ? "just now" : m < 120 ? m + " minutes ago" : Math.round(m / 60) + " hours ago";
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function bellLoad() {
    BELL.busy = true;
    fetch("/images/alerts.json?t=" + Date.now(), { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("no file"); return r.json(); })
      .then(function (j) { BELL.data = j && Array.isArray(j.items) ? j : null; BELL.failed = !BELL.data; })
      .catch(function () { BELL.failed = true; })
      .then(function () { BELL.busy = false; BELL.at = Date.now(); bellDraw(); });
  }
  function bellDraw() {
    var box = document.getElementById("hl-bell");
    if (!box) return;
    var d = BELL.data, items = d ? d.items : [], worst = items.length ? items[0].level : "";
    var badge = box.querySelector(".hl-bell-n"), btn = box.querySelector("button");
    badge.textContent = items.length > 9 ? "9+" : String(items.length);
    badge.hidden = !items.length;
    badge.className = "hl-bell-n hl-lv-" + (worst || "info");
    btn.setAttribute("aria-label", items.length ? "Notifications: " + items.length + " need attention" : "Notifications: nothing needs attention");
    var pop = box.querySelector(".hl-bellpop");
    while (pop.firstChild) pop.removeChild(pop.firstChild);
    var head = el("div", "hl-bellhead");
    head.appendChild(el("strong", "", "Notifications"));
    var stale = d && d.updated && (Date.now() / 1000 - d.updated) > 1200;
    head.appendChild(el("span", "hl-bellsub", !d ? "" : (stale ? "Not updated for a while" : "Checked " + ago(Date.now() / 1000 - (d.updated || 0)))));
    pop.appendChild(head);
    if (!d) pop.appendChild(el("p", "hl-bellempty", BELL.failed ? "The list is not there yet. It is generated every 5 minutes (run sudo homelab-alerts to generate it now)." : "Looking..."));
    else if (!items.length) pop.appendChild(el("p", "hl-bellempty hl-allgood", "All good. Nothing needs attention."));
    items.forEach(function (it) {
      var row = el("div", "hl-bellrow");
      row.appendChild(el("span", "hl-dot hl-lv-" + (it.level === "bad" || it.level === "warn" ? it.level : "info")));
      var txt = el("div", "hl-belltxt");
      txt.appendChild(el("div", "hl-belltitle", String(it.title || "")));
      if (it.detail) txt.appendChild(el("div", "hl-belldetail", String(it.detail)));
      row.appendChild(txt);
      if (it.action === "update" || it.action === "drives") {
        var a = el("a", "hl-bellbtn", it.action === "update" ? "Update" : "Open Drives");
        a.href = panelUrl(it.action === "update" ? "updates" : "drives");
        a.target = "_blank";
        a.rel = "noopener";
        row.appendChild(a);
      }
      pop.appendChild(row);
    });
  }
  function bell() {
    var tabs = document.getElementById("tabs"), ul = document.getElementById("myTab");
    if (!tabs || !ul) return;
    var box = document.getElementById("hl-bell");
    if (!box) {
      box = el("div", "hl-bellwrap");
      box.id = "hl-bell";
      var btn = el("button", "hl-bellbtn-main");
      btn.type = "button";
      btn.setAttribute("aria-haspopup", "true");
      btn.setAttribute("aria-expanded", "false");
      btn.innerHTML = BELL_ICON;
      btn.appendChild(el("span", "hl-bell-n hl-lv-info", "0"));
      btn.onclick = function () {
        var open = !box.classList.contains("hl-open");
        box.classList.toggle("hl-open", open);
        btn.setAttribute("aria-expanded", String(open));
        if (open && !BELL.busy) bellLoad();
      };
      box.appendChild(btn);
      var pop = el("div", "hl-bellpop");
      pop.setAttribute("role", "region");
      pop.setAttribute("aria-label", "Notifications");
      box.appendChild(pop);
      document.addEventListener("click", function (e) { var b = document.getElementById("hl-bell"); if (b && !b.contains(e.target)) { b.classList.remove("hl-open"); b.querySelector("button").setAttribute("aria-expanded", "false"); } });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") { var b = document.getElementById("hl-bell"); if (b) b.classList.remove("hl-open"); } });
      bellDraw();
    }
    if (box.parentNode !== tabs || ul.nextSibling !== box) tabs.insertBefore(box, ul.nextSibling);
    if (!BELL.busy && Date.now() - BELL.at > 60000) bellLoad();
  }

  function run() {
    queued = false;
    wording(); health(); shrinkButton(); heightButton(); playerHeight(); frameHeights(); rename(); logo(); groups(); calendar(); linkRows(); searchButton(); tabName(); bars(); sharp(); bell();
  }
  function soon() { if (!queued) { queued = true; window.requestAnimationFrame(run); } }
  night(); soon();
  new MutationObserver(soon).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", soon);
  window.setInterval(soon, 3000);
  window.setInterval(night, 600000);
})();
(function () {
  if (window.parent !== window) return;
  var BANDS = [[1850, 2000, "1080", 0.9], [2450, 2650, "1440", 1.1]];
  var root = document.documentElement, timer = 0;
  function fit() {
    var phys = Math.round(window.innerWidth * window.devicePixelRatio), z = 1, name = "";
    for (var i = 0; i < BANDS.length; i++) if (phys >= BANDS[i][0] && phys <= BANDS[i][1]) { name = BANDS[i][2]; z = BANDS[i][3]; }
    if (z === 1) { root.style.removeProperty("zoom"); root.style.removeProperty("--hl-vh"); root.removeAttribute("data-hl-fit"); return; }
    root.style.zoom = String(z);
    root.style.setProperty("--hl-vh", (1 / z).toFixed(4) + "vh");
    root.setAttribute("data-hl-fit", name);
  }
  fit();
  window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(fit, 150); });
})();
/* <<< homelab extras <<< */

/* >>> homelab panel >>> */
(function () {
  var STYLE_ID = "hl-live-look";
  var BLUR_PX = { none: 0, sm: 4, md: 12, lg: 16, xl: 24, "2xl": 40, "3xl": 64 };

  function fromPanel(e) {
    var frames = document.querySelectorAll("iframe");
    for (var i = 0; i < frames.length; i++) {
      if (frames[i].contentWindow === e.source) return !!frames[i].closest("#customize-card, #linkedit-card");
    }
    return false;
  }
  function inRange(n) { return typeof n === "number" && n >= 0 && n <= 100; }

  var kept = null;
  function keep() {
    if (kept) return;
    var w = document.getElementById("inner_wrapper"), b = document.getElementById("background");
    kept = {
      filter: w ? w.style.getPropertyValue("backdrop-filter") : "",
      webkit: w ? w.style.getPropertyValue("-webkit-backdrop-filter") : "",
      image: b ? b.style.getPropertyValue("background-image") : ""
    };
  }
  function put(el, prop, val) { if (!el) return; if (val) el.style.setProperty(prop, val); else el.style.removeProperty(prop); }
  var SAVED_ID = "hl-saved-sheet", headWatch = null;
  function placePreview(s) {
    var sv = document.getElementById(SAVED_ID);
    if (sv && sv.parentNode && (s.parentNode !== sv.parentNode || !(sv.compareDocumentPosition(s) & 4))) sv.parentNode.appendChild(s);
    else if (!s.parentNode) document.head.appendChild(s);
    return s;
  }
  var pendingCss = null, savedSeq = 0;
  function clearAll() {
    var s = document.getElementById(STYLE_ID);
    if (pendingCss !== null) {
      if (!s) { s = document.createElement("style"); s.id = STYLE_ID; }
      s.textContent = pendingCss;
      placePreview(s);
    } else if (s) s.remove();
    if (kept) {
      var w = document.getElementById("inner_wrapper"), b = document.getElementById("background");
      put(w, "backdrop-filter", kept.filter);
      put(w, "-webkit-backdrop-filter", kept.webkit);
      put(b, "background-image", kept.image);
      kept = null;
    }
    window.dispatchEvent(new CustomEvent("hl-names", { detail: null }));
    window.dispatchEvent(new Event("hl-look-changed"));
  }
  function look(css) {
    if (typeof css !== "string" || css.length > 60000 || /[<\\]|url\s*\(|@import|expression|javascript:/i.test(css) || !/^[A-Za-z0-9 \n#,.:;(){}\[\]="%@&_>*~+!-]*$/.test(css)) return;
    var s = document.getElementById(STYLE_ID);
    if (!s) { s = document.createElement("style"); s.id = STYLE_ID; }
    s.textContent = css;
    placePreview(s);
  }
  function background(d) {
    if (!inRange(d.saturate) || !inRange(d.brightness) || !inRange(d.opacity) || !Object.prototype.hasOwnProperty.call(BLUR_PX, d.blur)) return;
    keep();
    var w = document.getElementById("inner_wrapper");
    if (w) {
      var f = "blur(" + BLUR_PX[d.blur] + "px) saturate(" + d.saturate / 100 + ") brightness(" + d.brightness / 100 + ")";
      w.style.setProperty("backdrop-filter", f);
      w.style.setProperty("-webkit-backdrop-filter", f);
    }
    var b = document.getElementById("background");
    if (b && typeof d.image === "string" && /^(https?:\/\/|\/)[^'"()\\\s]+$/.test(d.image)) {
      var o = 1 - d.opacity / 100;
      b.style.setProperty("background-image", "linear-gradient(rgb(var(--bg-color) / " + o + "), rgb(var(--bg-color) / " + o + ")), url('" + d.image + "')");
    }
    window.dispatchEvent(new Event("hl-look-changed"));
  }
  function names(d) {
    function t(v, n) { return typeof v === "string" && v.length <= n && !/[\u0000-\u001f"\\<>{}`]/.test(v) ? v : ""; }
    var n = d.names || {}, lg = d.logo || {}, size = typeof lg.size === "number" && lg.size >= 24 && lg.size <= 96 ? lg.size : 48;
    window.dispatchEvent(new CustomEvent("hl-names", { detail: { homelab: t(n.homelab, 24), main: t(n.main, 24), backup: t(n.backup, 24), src: t(lg.src, 150000), link: t(lg.link, 600), size: size } }));
  }
  function saved(d) {
    if (d && d.bg === true && kept) {
      var w0 = document.getElementById("inner_wrapper"), b0 = document.getElementById("background");
      kept.image = b0 ? b0.style.getPropertyValue("background-image") : kept.image;
      kept.filter = w0 ? w0.style.getPropertyValue("backdrop-filter") : kept.filter;
      kept.webkit = w0 ? w0.style.getPropertyValue("-webkit-backdrop-filter") : kept.webkit;
    }
    try {
      fetch("/api/hash", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) { if (j && j.hash) window.localStorage.setItem("hash", j.hash); }).catch(function () {  });
    } catch (e) {  }
    var prevSheet = document.querySelector('link[rel="stylesheet"][href*="custom.css"]');
    if (!prevSheet) { clearAll(); return; }
    var cur = document.getElementById(STYLE_ID);
    if (cur) pendingCss = cur.textContent;
    var base = prevSheet.getAttribute("href").replace(/[?&]hl=\d+/, "");
    var tries = 0, mine = ++savedSeq;
    (function load() {
      if (mine !== savedSeq) return;
      var fresh = prevSheet.cloneNode();
      fresh.setAttribute("href", base + (base.indexOf("?") < 0 ? "?" : "&") + "hl=" + Date.now());
      fresh.onload = function () {
        if (mine !== savedSeq) { fresh.remove(); return; }
        var all = document.querySelectorAll('link[rel="stylesheet"][href*="custom.css"]');
        for (var i = 0; i < all.length; i++) if (all[i] !== fresh) all[i].remove();
        pendingCss = null; clearAll();
        keepSaved(fresh.getAttribute("href"));
      };
      fresh.onerror = function () {
        fresh.remove();
        if (++tries < 40) setTimeout(load, 1500);
      };
      (prevSheet.parentNode || document.head).insertBefore(fresh, prevSheet.nextSibling);
    })();
  }
  function keepSaved(href) {
    try {
      fetch(href, { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("no"); return r.text(); }).then(function (txt) {
        if (!txt || txt.length > 400000) return;
        var s = document.getElementById(SAVED_ID);
        if (!s) { s = document.createElement("style"); s.id = SAVED_ID; (document.body || document.head).appendChild(s); }
        s.textContent = txt;
        var pv = document.getElementById(STYLE_ID); if (pv) placePreview(pv);
        if (!headWatch && window.MutationObserver) {
          headWatch = new MutationObserver(function (list) {
            for (var i = 0; i < list.length; i++) for (var j = 0; j < list[i].addedNodes.length; j++) {
              var n = list[i].addedNodes[j];
              if (n.nodeType === 1 && n.tagName === "LINK" && /custom\.css/.test(n.getAttribute("href") || "") && !/[?&]hl=\d+/.test(n.getAttribute("href"))) n.setAttribute("media", "not all");
            }
          });
          headWatch.observe(document.head, { childList: true });
        }
        var all = document.querySelectorAll('link[rel="stylesheet"][href*="custom.css"]');
        for (var k = 0; k < all.length; k++) if (!/[?&]hl=\d+/.test(all[k].getAttribute("href"))) all[k].setAttribute("media", "not all");
      }).catch(function () {  });
    } catch (e) {  }
  }
  var waiting = false;
  function reloadWhenUp() {
    if (waiting) return;
    waiting = true;
    var t0 = Date.now(), sawDown = false;
    (function poll() {
      fetch("/api/hash", { cache: "no-store" }).then(function (r) {
        if (!r.ok) throw new Error("not yet");
        if (sawDown || Date.now() - t0 >= 10000) window.location.reload(); else setTimeout(poll, 1500);
      }).catch(function () {
        sawDown = true;
        if (Date.now() - t0 > 90000) window.location.reload(); else setTimeout(poll, 1500);
      });
    })();
  }
  window.addEventListener("message", function (e) {
    var d = e.data;
    if (!d || d.hlp !== 1 || typeof d.type !== "string" || !fromPanel(e)) return;
    if (d.type === "css") look(d.css);
    else if (d.type === "bg") background(d);
    else if (d.type === "names") names(d);
    else if (d.type === "saved") saved(d);
    else if (d.type === "clear") clearAll();
    else if (d.type === "reload") { if (d.wait === true) reloadWhenUp(); else window.location.reload(); }
  });
})();
/* <<< homelab panel <<< */
