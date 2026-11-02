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
    assert swapped["titles"] == ["Strahd von Zarovich"]
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
def real_index(tmp_path_factory) -> list[dict]:
    out = tmp_path_factory.mktemp("site")
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    page = (out / "search" / "index.html").read_text(encoding="utf-8")
    assert "function search(" in page, "the built search page carries the matcher"
    return json.loads((out / "search-index.json").read_text(encoding="utf-8"))


@needs_node
def test_ilia_finds_ilya_on_the_real_site(real_index):
    [result] = run_search(real_index, "Ilia")
    assert result["close"] == {"ilia": ["ilya"]}
    assert result["titles"][0] == "Ilya"
