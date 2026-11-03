// Search matching for templates/search.html, inlined there and tested by tests/test_search.py.
// Every query word must appear in a page. A word that starts no word on the site (a near miss
// like "Ilia" for "Ilya", or a name spelled by ear like "balzepharus" for "Beucephalus") also
// matches the site's closest spellings of it, where sound-alike letters count as half a slip.
var SearchMatch = (function () {
  function fold(s) {
    return s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  // How many slips a word may have: none under 4 letters, where a guess is mostly noise, one up
  // to 7 letters, then half a slip for every 2 letters (8-9: 2, 10-11: 2.5, as in "balzepharus").
  function slips(word) {
    return word.length < 4 ? 0 : word.length < 8 ? 1 : Math.floor(word.length / 2) / 2;
  }

  // Spell a word closer to how it sounds: "ph" is "f", "ck" is "k", doubled letters count once.
  function sounds(w) {
    return w.replace(/ph/g, "f").replace(/ck/g, "k").replace(/(.)\1+/g, "$1");
  }

  // Letters easily heard or written for each other: swapping within a group is half a slip.
  // GROUP[char code] is a bit per group the letter belongs to, so the check is one AND.
  var ALIKE = ["aeiouy", "uw", "csz", "ckq", "lr", "fv", "mn", "dt", "bp", "gj"];
  var GROUP = new Array(128).fill(0);
  ALIKE.forEach(function (g, bit) { for (var k = 0; k < g.length; k++) GROUP[g.charCodeAt(k)] |= 1 << bit; });
  // Adding or dropping a vowel or a silent-ish "h" is half a slip; any other letter is a whole one.
  var SOFT = new Array(128).fill(false);
  "aeiouyh".split("").forEach(function (c) { SOFT[c.charCodeAt(0)] = true; });

  function swapCost(x, y) {
    return x === y ? 0 : x < 128 && y < 128 && (GROUP[x] & GROUP[y]) ? 0.5 : 1;
  }
  function dropCost(x) {
    return x < 128 && SOFT[x] ? 0.5 : 1;
  }

  // Letter codes of a word (or the codes themselves, worked out once per site word).
  function codes(w) {
    if (typeof w !== "string") return w;
    var out = [];
    for (var k = 0; k < w.length; k++) out.push(w.charCodeAt(k));
    return out;
  }

  // Slips from a to b (add, drop or change a letter, priced as above; swapping two neighbours,
  // a typing slip, is half), or max + 1 if more than max. Call it with sounds() spellings.
  function distance(a, b, max) {
    if (Math.abs(a.length - b.length) / 2 > max) return max + 1;
    var A = codes(a), B = codes(b), i, j;
    var before = null, prev = [0], row, prevBest = 0;
    for (j = 1; j <= B.length; j++) prev.push(prev[j - 1] + dropCost(B[j - 1]));
    for (i = 1; i <= A.length; i++) {
      row = [prev[0] + dropCost(A[i - 1])];
      var best = row[0];
      for (j = 1; j <= B.length; j++) {
        var d = Math.min(prev[j] + dropCost(A[i - 1]), row[j - 1] + dropCost(B[j - 1]), prev[j - 1] + swapCost(A[i - 1], B[j - 1]));
        if (before && j > 1 && A[i - 1] === B[j - 2] && A[i - 2] === B[j - 1]) d = Math.min(d, before[j - 2] + 0.5);
        row.push(d);
        if (d < best) best = d;
      }
      // Later rows build on this row, or on the previous one through a half-slip swap.
      if (best > max && prevBest + 0.5 > max) return max + 1;
      prevBest = best;
      before = prev;
      prev = row;
    }
    return prev[B.length];
  }

  function prepare(entries) {
    var vocab = Object.create(null);
    entries.forEach(function (e) {
      if (!e.f) e.f = fold(e.x);
      if (!e.ft) e.ft = fold(e.t);
      (e.ft + " " + e.f).split(/[^\p{L}\p{N}]+/u).forEach(function (w) { if (w) vocab[w] = true; });
    });
    return Object.keys(vocab).map(function (w) { return {w: w, s: codes(sounds(w))}; });
  }

  // The site's words of 3+ letters within a few slips of term, the closest ones only (at most five).
  function closeWords(term, vocab) {
    var max = slips(term);
    if (!max) return [];
    var near = [], said = codes(sounds(term));
    vocab.forEach(function (v) {
      if (v.w.length < 3) return;  // too short to be what someone meant to type
      var d = distance(said, v.s, max);
      if (d <= max) near.push({w: v.w, d: d});
    });
    near.sort(function (a, b) { return a.d - b.d || (a.w < b.w ? -1 : 1); });
    // Only the closest spellings: "thier" is "their", not also "there", "thief" and "other".
    return near.filter(function (n) { return n.d === near[0].d; }).slice(0, 5).map(function (n) { return n.w; });
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
      if (vocab.some(function (v) { return v.w.lastIndexOf(t, 0) === 0; })) return [t];
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

  return {fold: fold, sounds: sounds, distance: distance, search: search};
})();
if (typeof module !== "undefined") module.exports = SearchMatch;
