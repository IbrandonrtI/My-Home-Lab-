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
