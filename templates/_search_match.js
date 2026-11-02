// Search matching for templates/search.html, inlined there and tested by tests/test_search.py.
// Every query word must appear in a page. A word that starts no word on the site (a near miss
// like "Ilia" for "Ilya") also matches the site's closest spellings of it.
var SearchMatch = (function () {
  function fold(s) {
    return s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  // How many slips a word may have: none for short words, where a guess is mostly noise.
  function slips(word) {
    return word.length < 4 ? 0 : word.length < 8 ? 1 : 2;
  }

  // Edits (insert, delete, change, swap two neighbours) from a to b, or max + 1 if more than max.
  function distance(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var before = null, prev = [], row, i, j;
    for (j = 0; j <= b.length; j++) prev.push(j);
    for (i = 1; i <= a.length; i++) {
      row = [i];
      var best = i;
      for (j = 1; j <= b.length; j++) {
        var cost = a[i - 1] === b[j - 1] ? 0 : 1;
        var d = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost);
        if (before && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d = Math.min(d, before[j - 2] + 1);
        row.push(d);
        if (d < best) best = d;
      }
      if (best > max) return max + 1;
      before = prev;
      prev = row;
    }
    return prev[b.length];
  }

  function prepare(entries) {
    var vocab = Object.create(null);
    entries.forEach(function (e) {
      if (!e.f) e.f = fold(e.x);
      if (!e.ft) e.ft = fold(e.t);
      (e.ft + " " + e.f).split(/[^\p{L}\p{N}]+/u).forEach(function (w) { if (w) vocab[w] = true; });
    });
    return Object.keys(vocab);
  }

  // The site's words within a few slips of term, closest first (at most five).
  function closeWords(term, vocab) {
    var max = slips(term);
    if (!max) return [];
    var near = [];
    vocab.forEach(function (w) {
      var d = distance(term, w, max);
      if (d <= max) near.push({w: w, d: d});
    });
    near.sort(function (a, b) { return a.d - b.d || (a.w < b.w ? -1 : 1); });
    return near.slice(0, 5).map(function (n) { return n.w; });
  }

  function count(text, word) {
    return text.split(word).length - 1;
  }

  // Returns {hits: [{e, score, mark}] best first, close: {query word: [spellings used instead]}}.
  function search(entries, query) {
    var vocab = entries.vocab || (entries.vocab = prepare(entries));
    var terms = fold(query.trim()).split(/\s+/).filter(Boolean);
    var close = {};
    var options = terms.map(function (t) {
      // Found if some word on the site starts with it ("krez" while typing Krezk). Otherwise
      // ("ilia", only inside "familiar") close spellings join the search too.
      if (vocab.some(function (w) { return w.lastIndexOf(t, 0) === 0; })) return [t];
      var near = closeWords(t, vocab);
      if (near.length) close[t] = near;
      return near.concat([t]);
    });
    var hits = [];
    if (!terms.length) return {hits: hits, close: close};
    entries.forEach(function (e) {
      var score = 0, mark = null;
      for (var i = 0; i < options.length; i++) {
        var best = -1, bestWord = null;
        options[i].forEach(function (w) {
          var inTitle = e.ft.indexOf(w) >= 0, inBody = e.f.indexOf(w) >= 0;
          if (!inTitle && !inBody) return;
          var s = (inTitle ? 10 : 0) + (inBody ? 1 + Math.min(count(e.f, w), 9) : 0);
          if (s > best) { best = s; bestWord = w; }
        });
        if (best < 0) return;
        score += best;
        if (mark === null) mark = bestWord;
      }
      hits.push({e: e, score: score, mark: mark});
    });
    hits.sort(function (a, b) { return b.score - a.score; });
    return {hits: hits, close: close};
  }

  return {fold: fold, distance: distance, search: search};
})();
if (typeof module !== "undefined") module.exports = SearchMatch;
