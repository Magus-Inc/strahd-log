// How a search result looks, shared by the search page (templates/search.html) and the search panel
// in every page's header (templates/_search_panel.html). Tested by tests/test_search.py under Node.
var SearchResults = (function () {
  var LIMIT = 50;
  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; });
  }
  function snippet(text, folded, term) {
    var at = folded.indexOf(term);
    if (at < 0) return esc(text.slice(0, 160)) + (text.length > 160 ? "…" : "");
    var start = Math.max(0, at - 70), end = Math.min(text.length, at + term.length + 90);
    return (start ? "…" : "") + esc(text.slice(start, at)) + "<mark>" + esc(text.slice(at, at + term.length)) +
      "</mark>" + esc(text.slice(at + term.length, end)) + (end < text.length ? "…" : "");
  }
  // Same icons as templates/_badges.html.
  var SLIDES_ICON = '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/></svg>';
  var PICTURE_ICON = '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/></svg>';
  var LIFE_ICONS = {died: '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12 3a8 8 0 0 0-8 8c0 2.6 1.2 4.4 3 5.5V20h10v-3.5c1.8-1.1 3-2.9 3-5.5a8 8 0 0 0-8-8z"/><circle cx="9" cy="11.5" r="1.6"/><circle cx="15" cy="11.5" r="1.6"/><path d="M10.5 20v-2.5M13.5 20v-2.5"/></svg>', revived: '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 18h18"/><path d="M7 18a5 5 0 0 1 10 0"/><path d="M12 6v3M5.6 9.6l2 2M18.4 9.6l-2 2"/></svg>', party: '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="9" r="2.5"/><path d="M16.5 14.6c2.6.2 4.5 2.1 4.5 5.4"/></svg>', left: '<svg class="badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5 1.6 0 3 .5 4.1 1.4"/><path d="M15 17h6M18 14l3 3-3 3"/></svg>'};
  // Skull (died), sunrise (brought back), party (joined or came back) and leaves badges: e.b.
  function lifeTags(e) {
    return (e.b || []).map(function (b) {
      var named = b.kind === "died" || b.kind === "revived";
      return ' <span class="life-tag ' + b.kind + '-tag"' + (named ? ' role="img" aria-label="' + esc(b.aria) + '" title="' + esc(b.aria) + '"' : "") + ">" +
        LIFE_ICONS[b.kind] + (named ? '<span aria-hidden="true">' + esc(b.label) + "</span>" : esc(b.label)) + "</span>";
    }).join("");
  }
  // The line over the results: how many, and which words were widened to close spellings
  // ("Ilia" also finds Ilya).
  function summary(found) {
    var hits = found.hits;
    var guessed = Object.keys(found.close).map(function (w) { return "“" + w + "” → " + found.close[w].join(", "); });
    return (hits.length ? hits.length + (hits.length === 1 ? " match" : " matches") : "No matches") +
      (guessed.length ? ", with close spellings: " + guessed.join("; ") + "." : hits.length ? "" : ".");
  }
  // One result card's class and inner HTML. `base` is the site's base path ("/" or "/pr-preview/pr-7/").
  function card(h, base) {
    var text = '<span class="chip">' + esc(h.e.l) + '</span><h2><a class="stretched" href="' + base + h.e.u + '">' + esc(h.e.t) +
      '</a></h2><p class="teaser">' + snippet(h.e.x, h.e.f, h.mark) + "</p>" +
      (h.e.s || h.e.b ? '<p class="meta">' + (h.e.s ? '<span class="slides-tag">' + SLIDES_ICON + h.e.s + (h.e.s === 1 ? " slide" : " slides") + "</span>" : "") +
        lifeTags(h.e) + "</p>" : "");
    return {
      className: "card result" + (h.e.p ? " has-pic" : ""),
      html: h.e.p ? '<div class="wiki-card-text">' + text + '</div><span class="pic-badge"><span class="pic-thumb"><img src="' + base + h.e.p +
        '" alt="" loading="lazy" decoding="async"></span>' +
        (h.e.n > 1 ? '<span class="pic-count" role="img" aria-label="' + h.e.n + ' pictures">' + PICTURE_ICON + h.e.n + "</span>" : "") + "</span>" : text
    };
  }
  // Fill a list with the best LIMIT cards for found (SearchMatch.search's answer) and the status line.
  function show(found, list, status, base) {
    list.innerHTML = "";
    status.textContent = summary(found);
    found.hits.slice(0, LIMIT).forEach(function (h) {
      var li = list.ownerDocument.createElement("li"), c = card(h, base);
      li.className = c.className;
      li.innerHTML = c.html;
      list.appendChild(li);
    });
  }
  return {LIMIT: LIMIT, esc: esc, summary: summary, card: card, show: show};
})();
if (typeof module !== "undefined") module.exports = SearchResults;
