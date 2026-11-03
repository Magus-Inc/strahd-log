"""The search page's matching (templates/_search_match.js), run under Node.

The search page has no external JavaScript, so the fuzzy matching is our own script. These tests
load the same file the page inlines and call it the way the page does.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import build

MATCH_JS = build.ROOT / "templates" / "_search_match.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node is needed to run the search page's script")

RUNNER = """
const m = require(process.argv[1]);
let input = "";
process.stdin.on("data", d => input += d);
process.stdin.on("end", () => {
  const {entries, queries} = JSON.parse(input);
  const out = queries.map(q => {
    const r = m.search(entries, q);
    return {titles: r.hits.map(h => h.e.t), marks: r.hits.map(h => h.mark), close: r.close};
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def run_search(entries: list[dict], *queries: str) -> list[dict]:
    done = subprocess.run([NODE, "-e", RUNNER, str(MATCH_JS)], input=json.dumps({"entries": entries, "queries": queries}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(done.stdout)


def entry(title: str, text: str) -> dict:
    return {"t": title, "u": title.lower().replace(" ", "-") + "/", "l": "NPC", "x": text}


ENTRIES = [
    entry("Ilya Krezkov", "The runaway son of the burgomaster of Krezk."),
    entry("Strahd von Zarovich", "The lord of Barovia watches from Castle Ravenloft."),
    entry("Blue Water Inn", "A rose garden grows behind the inn."),
    entry("Nose of the Hag", "A crooked nose on a cliff."),
    entry("Ireena Kolyana", "The burgomaster's adopted daughter."),
    entry("Wizard of Wines", "A familiar raven circles the vineyard."),
    entry("Beucephalus", "The nightmare in Strahd's stable, its hooves wreathed in flame."),
    entry("Belview", "A quiet hamlet by the river."),
    entry("Madam Eva", "Their thief went over there with the other seer."),
]


@needs_node
def test_a_near_miss_spelling_finds_the_name():
    # "ilia" sits inside "familiar", but no word starts with it, so close spellings join in and rank first.
    [result] = run_search(ENTRIES, "Ilia")
    assert result["titles"] == ["Ilya Krezkov", "Wizard of Wines"]
    assert result["close"] == {"ilia": ["ilya"]}
    assert result["marks"] == ["ilya", "ilia"]


@needs_node
def test_swapped_letters_and_accents_still_match():
    swapped, accented = run_search(ENTRIES, "Starhd", "Ilía")
    assert swapped["titles"][0] == "Strahd von Zarovich"
    assert accented["titles"][0] == "Ilya Krezkov"


@needs_node
def test_each_word_of_the_query_is_matched_on_its_own():
    [result] = run_search(ENTRIES, "ilia krezk")
    assert result["titles"] == ["Ilya Krezkov"]
    assert result["close"] == {"ilia": ["ilya"]}


@needs_node
def test_a_word_that_is_found_exactly_is_not_widened():
    [result] = run_search(ENTRIES, "rose")
    assert result["titles"] == ["Blue Water Inn"]
    assert result["close"] == {}


@needs_node
def test_the_start_of_a_word_counts_as_found_while_typing():
    [result] = run_search(ENTRIES, "krez")
    assert result["titles"] == ["Ilya Krezkov"]
    assert result["close"] == {}


@needs_node
def test_short_words_need_an_exact_match():
    # Three letters is too short to guess at: "inx" is one letter from "inn" but finds nothing.
    [result] = run_search(ENTRIES, "inx")
    assert result["titles"] == []
    assert result["close"] == {}


@needs_node
def test_long_words_allow_two_slips():
    [result] = run_search(ENTRIES, "burgomastr")
    assert result["close"] == {"burgomastr": ["burgomaster"]}
    assert result["titles"] == ["Ilya Krezkov", "Ireena Kolyana"]


@pytest.mark.parametrize("typed", ["belsepharus", "balzepharus", "bucephalus", "beusephalis", "bewcefalus"])
@needs_node
def test_names_spelled_the_way_they_sound_find_the_page(typed):
    # Chris heard the nightmare's name at the table and spelled it by ear (2026-11-02). Letters
    # that sound alike (c/s/z, l/r, ph/f, any two vowels) count as half a slip.
    [result] = run_search(ENTRIES, typed)
    assert result["titles"][0] == "Beucephalus"
    assert result["close"] == {typed: ["beucephalus"]}


@needs_node
def test_sound_alike_matching_does_not_reach_unrelated_words():
    # Few slips allowed for short words, so a short misspelling still finds only its own word.
    rows = run_search(ENTRIES, "nightmear", "stabel", "belveiw", "zxcvbnm")
    assert [r["close"] for r in rows] == [{"nightmear": ["nightmare"]}, {"stabel": ["stable"]},
                                          {"belveiw": ["belview"]}, {}]


@needs_node
def test_only_the_closest_spellings_are_used():
    # "thier" is half a slip from "their" (swapped letters) and further from there/thief/other.
    thier, evva = run_search(ENTRIES, "thier", "evva")
    assert thier["close"] == {"thier": ["their"]}
    assert evva["close"] == {"evva": ["eva"]}


@needs_node
def test_a_swap_after_a_change_is_still_counted():
    # Cheap neighbour swaps reach back two rows, so the early stop must not give up a row too soon.
    done = subprocess.run([NODE, "-e", "const m = require(process.argv[1]); console.log(m.distance('pzr', 'trz', 1.5))",
                           str(MATCH_JS)], capture_output=True, text=True, check=True)
    assert float(done.stdout) == 1.5


@needs_node
def test_exact_matching_is_unchanged():
    [result] = run_search(ENTRIES, "castle raven")
    assert result["titles"] == ["Strahd von Zarovich"]
    assert result["close"] == {}


def test_the_search_page_inlines_the_matcher_and_says_when_it_guessed():
    page = (build.ROOT / "templates" / "search.html").read_text(encoding="utf-8")
    assert '{% include "_search_match.js" %}' in page
    assert "SearchMatch.search(" in page
    assert "close spelling" in page


@pytest.fixture(scope="module")
def real_index(real_build) -> list[dict]:
    out = real_build.out  # built once per run (conftest.py)
    page = (out / "search" / "index.html").read_text(encoding="utf-8")
    assert "function search(" in page, "the built search page carries the matcher"
    return json.loads((out / "search-index.json").read_text(encoding="utf-8"))


@needs_node
def test_ilia_finds_ilya_on_the_real_site(real_index):
    [result] = run_search(real_index, "Ilia")
    assert result["close"] == {"ilia": ["ilya"]}
    assert result["titles"][0] == "Ilya"


@needs_node
def test_common_typos_stay_narrow_on_the_real_site(real_index):
    rows = run_search(real_index, "wierd", "thier", "stradh", "dragn", "abot")
    assert [r["close"] for r in rows] == [{"wierd": ["wield"]}, {"thier": ["their"]}, {"stradh": ["strahd"]},
                                          {"dragn": ["dragon"]}, {"abot": ["abbot"]}]


@pytest.mark.parametrize("typed", ["belsepharus", "balzepharus"])
@needs_node
def test_sound_alike_spellings_find_beucephalus_on_the_real_site(real_index, typed):
    [result] = run_search(real_index, typed)
    assert result["close"][typed][0] == "beucephalus"
    assert result["titles"][0] == "Beucephalus"
