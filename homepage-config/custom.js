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
      if (cf.parentElement) { host = cf.parentElement.getBoundingClientRect(); sc = scroller(cf.parentElement); }
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
