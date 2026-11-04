  // Reading: did anyone read this post? GoatCounter events at /read/<page>/started (30 seconds with the
  // tab in front), /halfway (all of Malron's Account has been on screen, down to the bottom of its last
  // paragraph or margin note) and /finished (reached the map, "Where we were", after at least half the
  // "min read" time). A post without a map finishes at the end of its text. Each is sent at most once
  // per visit; nothing is stored in the browser. Wiki pages send none. With Google Analytics on, each
  // is also a GA4 event: read_started, read_halfway, read_finished.
  (function () {
    var prose = document.querySelector(".prose[data-read-minutes]");
    if (!prose) return;
    var path = location.pathname, base = "{{ base }}";
    if (path.indexOf(base) === 0) path = "/" + path.slice(base.length);
    if (path.slice(-1) !== "/") path += "/";
    var needed = Math.max(30, Number(prose.dataset.readMinutes) * 30), seconds = 0, sent = {}, timer;
    // The story runs from the <!--story--> mark to <!--story-end--> (poststyle.STORY, STORY_END);
    // the recap lists follow it. Its blocks are the account; margin notes float beside them.
    var walk = document.createTreeWalker(prose, NodeFilter.SHOW_COMMENT), start, end, node, story = [];
    while ((node = walk.nextNode())) {
      if (node.data === "story" && !start) start = node;
      else if (node.data === "story-end" && !end) end = node;
    }
    if (start && end && start.parentNode === prose && end.parentNode === prose) {
      for (node = start.nextSibling; node && node !== end; node = node.nextSibling) {
        if (node.nodeType === 1) story.push(node);
      }
    }
    var map = document.querySelector(".where-we-were .map-figure");
    function send(step) {
      if (sent[step]) return;
      sent[step] = true;
{% if counter %}
      new Image().src = "https://{{ counter }}.goatcounter.com/count?e=true&p=" +
        encodeURIComponent("/read" + path + step) + "&t=" + encodeURIComponent("Read " + step + ": " + document.title) +
        "&rnd=" + Math.random().toString(36).slice(2);
{% endif %}
{% if ga %}
      gtag("event", "read_" + step);
{% endif %}
    }
    function inView(bottom) { return window.innerHeight >= bottom; }
    function storyBottom() {
      if (!story.length) return prose.getBoundingClientRect().bottom;
      return Math.max.apply(null, story.map(function (el) { return el.getBoundingClientRect().bottom; }));
    }
    function check() {
      if (inView(storyBottom())) send("halfway");
      if (seconds >= 30) send("started");
      if (inView(map ? map.getBoundingClientRect().top : prose.getBoundingClientRect().bottom)) sent.end = true;
      if (sent.end && seconds >= needed) { send("finished"); clearInterval(timer); }
    }
    timer = setInterval(function () {
      if (document.visibilityState === "visible") seconds += 1;
      check();
    }, 1000);
    window.addEventListener("scroll", check, {passive: true});
    document.addEventListener("visibilitychange", check);
  })();
