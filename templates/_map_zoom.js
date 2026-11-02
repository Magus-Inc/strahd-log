// Zooming and panning one map, all with our own few lines (no library). Included inline after
// each map's <figure> by templates/_map.html, and run on that figure:
//  - buttons: + / - / back to the whole map;
//  - phone: pinch with two fingers, drag with one once zoomed in (one finger scrolls the page
//    while the whole map shows), double-tap to zoom in. The map's touch-action stops the browser's
//    own pinch over the map, so without this code a pinch on the map does nothing at all;
//  - desktop: a trackpad pinch (a wheel with Ctrl) zooms around the pointer, drag to pan once zoomed
//    in, double-click to zoom in. When the figure has data-wheel set to zoom (the map page), the plain scroll wheel zooms
//    too, wheel up in and down out; a wheel that can't zoom any further (down with the whole map
//    showing, up at 6x) scrolls the page as usual, so the map never traps the page. Small maps in
//    posts leave the plain wheel to scroll the page.
// A wiki page's map opens at 2.5x on its place.
// Zoom runs from the whole map to 6x and the view never leaves the map (but for a strip past its east edge). A drag is not a click,
// so taps on markers and places still open them.
//  - full screen: the corner button fills the window with the map (and the screen too, with the
//    browser's own full screen where it has one; iPhone doesn't, so there it fills the window). The
//    map's frame takes the screen's shape, so the whole map fits with a margin on the long side.
//    Esc or the button again leaves it; an open place card closes first.
(function (figure) {
  var svg = figure.querySelector(".map");
  var wheelZooms = figure.getAttribute("data-wheel") === "zoom";
  var MAP = {w: 1000, h: 750}, MIN_W = MAP.w / 6, FOCUS_ZOOM = 2.5;
  // Height over width of what shows: the map's own 3:4, or in full screen the screen's shape.
  function aspect() {
    if (!figure.classList.contains("map-full")) return 0.75;
    return (svg.clientHeight / svg.clientWidth) || 0.75;
  }
  // The whole map, with a margin on the long side when the frame is a different shape.
  function fit() {
    var a = aspect();
    return a >= 0.75 ? {x: 0, y: (MAP.h - MAP.w * a) / 2, w: MAP.w, h: MAP.w * a}
                     : {x: (MAP.w - MAP.h / a) / 2, y: 0, w: MAP.h / a, h: MAP.h};
  }
  var full = fit(), view = Object.assign({}, full);
  // Zoomed in, the view may run a little past the map's east edge, so a place there (Durst Manor) can
  // come out from under the zoom buttons in the top-right corner.
  var EAST_SPARE = 0.14;
  function clampAxis(at, span, size, spare) { return span >= size ? (size - span) / 2 : Math.min(size - span + span * (spare || 0), Math.max(0, at)); }
  function apply() {
    full = fit();
    view.w = Math.min(full.w, Math.max(MIN_W, view.w)); view.h = view.w * aspect();
    view.x = clampAxis(view.x, view.w, MAP.w, EAST_SPARE); view.y = clampAxis(view.y, view.h, MAP.h);
    svg.setAttribute("viewBox", [view.x, view.y, view.w, view.h].join(" "));
    svg.classList.toggle("zoomed", view.w < full.w - 0.5);
    // Markers, pins and names grow more slowly than the map, so they don't get huge.
    svg.style.setProperty("--mark", Math.min(1, Math.pow(view.w / MAP.w, 0.45)).toFixed(3));
  }
  function toMap(cx, cy) {
    var r = svg.getBoundingClientRect();
    return {x: view.x + (cx - r.left) / r.width * view.w, y: view.y + (cy - r.top) / r.height * view.h};
  }
  function zoomAt(f, p) {  // f < 1 zooms in; the map point p stays where it is on screen
    var w = Math.min(full.w, Math.max(MIN_W, view.w * f)), k = w / view.w;
    view.x = p.x - (p.x - view.x) * k; view.y = p.y - (p.y - view.y) * k; view.w = w; apply();
  }
  function zoom(f) { zoomAt(f, {x: view.x + view.w / 2, y: view.y + view.h / 2}); }
  figure.querySelectorAll("[data-zoom]").forEach(function (b) {
    b.addEventListener("click", function () {
      var z = b.getAttribute("data-zoom");
      if (z === "in") zoom(0.66); else if (z === "out") zoom(1.5);
      else if (z === "full") setFull(!figure.classList.contains("map-full"));
      else { view = fit(); apply(); }
    });
  });

  var fullButton = figure.querySelector('[data-zoom="full"]'), root = document.documentElement;
  function setFull(on) {
    if (on === figure.classList.contains("map-full")) return;
    figure.classList.toggle("map-full", on);
    root.classList.toggle("map-full-open", on);
    if (fullButton) {
      fullButton.setAttribute("aria-pressed", on ? "true" : "false");
      fullButton.setAttribute("aria-label", on ? "Leave full screen" : "Full screen");
    }
    try {
      if (on && root.requestFullscreen && !document.fullscreenElement) root.requestFullscreen().catch(function () {});
      if (!on && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function () {});
    } catch (err) {}
    view = fit(); apply();
  }
  // The browser's own full screen ended (its Esc, or a swipe): leave ours too.
  document.addEventListener("fullscreenchange", function () { if (!document.fullscreenElement) setFull(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !figure.classList.contains("map-full")) return;
    if (document.querySelector(".place-panel:not([hidden])")) return;  // the card closes first
    setFull(false);
  });
  window.addEventListener("resize", function () { if (figure.classList.contains("map-full")) apply(); });

  svg.addEventListener("wheel", function (e) {
    var dy = e.deltaY * (e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? 600 : 1);  // lines or pages to pixels
    if (!dy) return;
    var pinch = e.ctrlKey || e.metaKey;  // a trackpad pinch arrives as a wheel with Ctrl held
    if (!pinch && (!(wheelZooms || figure.classList.contains("map-full")) || (dy > 0 ? view.w >= full.w - 0.5 : view.w <= MIN_W + 0.5))) return;  // let the page scroll
    e.preventDefault();
    zoomAt(Math.exp(Math.max(-120, Math.min(120, dy)) * (pinch ? 0.01 : 0.0025)), toMap(e.clientX, e.clientY));
  }, {passive: false});

  var pointers = {}, gesture = null, moved = false, lastTap = null;
  function count() { return Object.keys(pointers).length; }
  function begin() {  // (re)start a drag or pinch from the pointers down now
    var ids = Object.keys(pointers);
    if (ids.length >= 2) {
      var a = pointers[ids[0]], b = pointers[ids[1]];
      gesture = {pinch: true, d: Math.hypot(a.x - b.x, a.y - b.y) || 1, view: Object.assign({}, view),
                 at: toMap((a.x + b.x) / 2, (a.y + b.y) / 2)};
    } else if (ids.length === 1 && view.w < full.w - 0.5) {
      var p = pointers[ids[0]];
      gesture = {pinch: false, x: p.x, y: p.y, vx: view.x, vy: view.y};
    } else {
      gesture = null;
    }
  }
  svg.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
    if (count() === 1) moved = false;
    begin();
  });
  window.addEventListener("pointermove", function (e) {
    if (!(e.pointerId in pointers)) return;
    if (!gesture) return;
    pointers[e.pointerId] = {x: e.clientX, y: e.clientY};
    var r = svg.getBoundingClientRect();
    if (gesture.pinch) {
      var ids = Object.keys(pointers), a = pointers[ids[0]], b = pointers[ids[1]];
      var w = Math.min(full.w, Math.max(MIN_W, gesture.view.w * gesture.d / (Math.hypot(a.x - b.x, a.y - b.y) || 1)));
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      view.w = w; view.h = w * aspect();
      view.x = gesture.at.x - (mx - r.left) / r.width * w; view.y = gesture.at.y - (my - r.top) / r.height * view.h;
      moved = true; apply();
    } else {
      var dx = e.clientX - gesture.x, dy = e.clientY - gesture.y;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
      if (!moved) { moved = true; try { svg.setPointerCapture(e.pointerId); } catch (err) {} }
      view.x = gesture.vx - dx * view.w / r.width; view.y = gesture.vy - dy * view.h / r.height; apply();
    }
    if (moved) e.preventDefault();
  });
  function end(e) {
    if (!(e.pointerId in pointers)) return;
    delete pointers[e.pointerId];
    begin();
    // Double-tap on a touch screen zooms in where you tapped.
    if (e.type === "pointerup" && e.pointerType !== "mouse" && !moved && count() === 0) {
      var now = Date.now();
      if (lastTap && now - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
        zoomAt(0.5, toMap(e.clientX, e.clientY)); lastTap = null;
      } else {
        lastTap = {t: now, x: e.clientX, y: e.clientY};
      }
    }
  }
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
  svg.addEventListener("click", function (e) {
    if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; }
  }, true);
  // Links in the map would otherwise start the browser's own drag-and-drop instead of a pan.
  svg.addEventListener("dragstart", function (e) { e.preventDefault(); });
  svg.addEventListener("dblclick", function (e) {
    if (e.target.closest && e.target.closest("a")) return;
    e.preventDefault();
    zoomAt(0.5, toMap(e.clientX, e.clientY));
  });
  // A wiki page's map opens zoomed in on its place (data-focus "x y"); the whole-map button shows it all.
  var focus = (figure.getAttribute("data-focus") || "").split(" ").map(Number);
  if (focus.length === 2 && !isNaN(focus[0]) && !isNaN(focus[1])) {
    view.w = MAP.w / FOCUS_ZOOM; view.h = view.w * aspect();
    view.x = focus[0] - view.w / 2; view.y = focus[1] - view.h / 2;
  }
  apply();
})(document.currentScript.previousElementSibling);
