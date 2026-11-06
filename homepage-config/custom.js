/* >>> homelab groups >>> managed by the installer: an upgrade replaces everything between this line and the closing marker,
   so put your own script above it. It gives every bookmark group a name tag (data-group) so that custom.css can colour each group. */
(function () {
  var queued = false;
  function slug(t) { return String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }
  function label() {
    queued = false;
    var groups = document.querySelectorAll(".bookmark-group");
    for (var i = 0; i < groups.length; i++) {
      var h = groups[i].querySelector(".bookmark-group-name");
      var s = h ? slug(h.textContent) : "";
      if (s && groups[i].getAttribute("data-group") !== s) groups[i].setAttribute("data-group", s);
    }
  }
  function soon() { if (!queued) { queued = true; window.requestAnimationFrame(label); } }
  soon();
  new MutationObserver(soon).observe(document.documentElement, { childList: true, subtree: true });
})();
/* <<< homelab groups <<< */

/* >>> homelab player >>> managed by the installer: an upgrade replaces everything between this line and the closing marker.
   Keeps the Navidrome music playing when you change tabs. Homepage removes the cards of a tab you leave, and the player inside the
   Navidrome card would go with them. So the real player is a frame on the page itself: it is laid over the card while the card is
   shown and moved out of sight while it is not. The frame Homepage puts in the card is emptied, so there is only one player. */
(function () {
  var box = null, frame = null, src = "", queued = false;
  var style = document.createElement("style");
  style.textContent = "#hl-player-box{position:absolute;z-index:5;overflow:hidden;border-radius:10px;}" +
    "#hl-player-box.hl-away{left:-10000px !important;pointer-events:none;}" +
    "#hl-player{display:block;width:calc(100% + 32px);height:100%;border:0;}";
  document.head.appendChild(style);

  function cardFrame() { return document.querySelector("#navidrome-card iframe"); }
  function real(u) { return !!u && u.indexOf("about:") !== 0; }                 // an address (not the empty page the card's frame is set to)

  function address(cf) {
    var u = cf.getAttribute("src") || "";
    if (!real(u)) return src;                                    // already emptied: the address we know stays
    if (location.protocol === "https:" && u.indexOf("http:") === 0) {      // an https page cannot show an http frame: use the card's https link
      var a = document.querySelector('#navidrome-card a[href^="https:"]');
      if (a) { try { return new URL(a.href).origin; } catch (e) { /* keep u */ } }
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

  // The box goes INTO the box that scrolls (Homepage scrolls inside its own page box, not the window), so the browser scrolls the player together with
  // the cards, with no delay. Without such a box (or in an old page) it stays on the body and is moved by the timers below.
  function scroller(el) {
    for (var e = el; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      var o = window.getComputedStyle(e).overflowY;
      if ((o === "auto" || o === "scroll")) return e;
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
      if (cf.parentElement && !cf.closest(".hl-folded") && !document.documentElement.classList.contains("hl-sliding")) { host = cf.parentElement.getBoundingClientRect(); sc = scroller(cf.parentElement); }      // (a folded group hides its cards)
    }
    if (!box) return;
    if (host && host.width > 0 && host.height > 0) {
      var home = sc || document.body;
      if (box.parentNode !== home) {
        if (sc && window.getComputedStyle(sc).position === "static") sc.style.position = "relative";
        home.appendChild(box);                                   // (moving a frame reloads it, so this happens only when the scrolling box itself changes)
      }
      box.className = "";
      box.style.left = "0px";                                    // measure from the corner, so the move is right whatever the page's own offsets are
      box.style.top = "0px";
      var o = box.getBoundingClientRect();
      box.style.cssText = "left:" + (host.left - o.left) + "px;top:" + (host.top - o.top) + "px;width:" + host.width + "px;height:" + host.height + "px;";
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

/* >>> homelab extras >>> managed by the installer: an upgrade replaces everything between this line and the closing marker.
   Small helpers for the look of the dashboard: the red edge of a card whose service does not answer, the shrink button of the music player, the fold button and the
   count of every group, the search button on a phone, the colour of the tab you are on, bars for the percentages of the Stats tab, and a slightly
   darker background late at night. Nothing here changes what Homepage does; without it the page still works, it just looks plainer. */
(function () {
  var root = document.documentElement, queued = false;
  function store(key, value) { try { if (value === undefined) return window.localStorage.getItem(key); window.localStorage.setItem(key, value); } catch (e) { /* no storage: fine */ } return null; }
  function all(sel, from) { return Array.prototype.slice.call((from || document).querySelectorAll(sel)); }

  // ---- a card whose service does not answer gets a red edge (the dot Homepage shows on the card already says it; this makes it easy to see)
  function health() {
    all(".service.hl-down").forEach(function (li) { li.classList.remove("hl-down"); });
    all(".service .site-monitor-status > div").forEach(function (d) {
      var li = d.closest(".service");
      if (li && /rose|red/.test(d.className)) li.classList.add("hl-down");
    });
  }

  // While a card or a group slides, the player block is told to look again on every frame; the music frame itself stays out of sight until it stops.
  function moving() {
    var until = Date.now() + 450;
    root.classList.add("hl-sliding");
    (function follow() {
      window.dispatchEvent(new Event("resize"));
      if (Date.now() < until) window.requestAnimationFrame(follow);
      else { root.classList.remove("hl-sliding"); window.dispatchEvent(new Event("resize")); }
    })();
  }

  // ---- the shrink button on the Navidrome card: the card folds to its title bar, the music keeps playing
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
      moving();                                                        // the player frame waits (out of sight) while the card slides
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

  // ---- every group: a count behind its name and a button that folds it (the choice is remembered by name)
  function folded() { try { return JSON.parse(store("hl-folded") || "[]"); } catch (e) { return []; } }
  // The group slides shut or open (the height is animated from the real height to 0 and back). While it moves, the player block is told to
  // look again on every frame, so the music frame follows the card.
  function slide(g, fold) {
    var panel = g.querySelector(":scope > div"), still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!panel || still) { g.classList.toggle("hl-folded", fold); window.dispatchEvent(new Event("resize")); return; }
    if (g.querySelector("#navidrome-card")) moving();                // the player frame waits (out of sight) until the card has stopped moving
    else { var until = Date.now() + 450; (function follow() { window.dispatchEvent(new Event("resize")); if (Date.now() < until) window.requestAnimationFrame(follow); })(); }
    function done() { panel.style.maxHeight = ""; panel.removeEventListener("transitionend", ended); }
    function ended(ev) { if (ev.target === panel && ev.propertyName === "max-height") done(); }
    panel.addEventListener("transitionend", ended);
    window.setTimeout(done, 600);
    if (fold) {
      panel.style.maxHeight = panel.scrollHeight + "px";               // start from the real height ...
      void panel.offsetHeight;
      g.classList.add("hl-folded");                                  // ... and the folded rule takes it to 0
    } else {
      panel.style.maxHeight = "0px";
      g.classList.remove("hl-folded");
      void panel.offsetHeight;
      panel.style.maxHeight = panel.scrollHeight + "px";             // grow to the real height, then the limit is taken off again
    }
  }
  function groups() {
    var list = folded();
    all(".services-group, .bookmark-group").forEach(function (g) {
      var h = g.querySelector(".service-group-name, .bookmark-group-name");
      if (!h) return;
      var name = h.textContent.replace(/\s*·\s*\d+$/, "").trim(), n = g.querySelectorAll("li.service, li.bookmark").length;
      if (n && h.getAttribute("data-count") !== String(n)) h.setAttribute("data-count", String(n));
      g.classList.toggle("hl-folded", list.indexOf(name) >= 0);
      if (g.querySelector(":scope > .hl-gfold")) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "hl-gfold";
      b.setAttribute("aria-label", "Fold or open " + name);
      b.addEventListener("click", function () {
        var cur = folded(), i = cur.indexOf(name);
        if (i >= 0) cur.splice(i, 1); else cur.push(name);
        store("hl-folded", JSON.stringify(cur));
        b.setAttribute("aria-expanded", i >= 0 ? "true" : "false");
        slide(g, i < 0);
      });
      b.setAttribute("aria-expanded", list.indexOf(name) >= 0 ? "false" : "true");
      g.appendChild(b);
    });
  }

  // ---- phone: a search button next to the weather opens the search bar
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

  // ---- the tab you are on gives the page its accent colour
  function tabName() {
    var t = document.querySelector('#myTab button[aria-selected="true"]');
    var name = t ? t.textContent.trim() : "";
    if (name && root.getAttribute("data-tab") !== name) root.setAttribute("data-tab", name);
  }

  // ---- Stats: a value that is a percentage gets a bar under it (amber from 85, red from 95)
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

  // ---- late at night the background is a little darker (0 by day, up to 1 at night)
  function night() {
    var d = new Date(), h = d.getHours() + d.getMinutes() / 60;
    var n = Math.max(0, Math.min(1, (Math.abs(h - 13) - 5) / 6));
    root.style.setProperty("--hl-night", n.toFixed(2));
  }

  function run() {
    queued = false;
    health(); shrinkButton(); groups(); searchButton(); tabName(); bars();
  }
  function soon() { if (!queued) { queued = true; window.requestAnimationFrame(run); } }
  night(); soon();
  new MutationObserver(soon).observe(document.documentElement, { childList: true, subtree: true });
  window.setInterval(soon, 3000);
  window.setInterval(night, 600000);
})();
/* <<< homelab extras <<< */
