"""Words that were hard to hear are kept and marked, not left out (Chris, 2026-11-04).

"We can tag numbers that were hard to hear as suspect and to be verified (provenance)." A post or wiki
page writes them as {?a d2?}. The site shows them with a dotted underline, a small "?" and a tooltip that
says they're unconfirmed (screen readers hear it too), and the Discord bot's corpus spells it out so its
answers can say so.
"""
import json
from pathlib import Path

import build
import suspect

ROOT = Path(__file__).resolve().parent.parent


def test_a_mark_renders_as_a_flagged_span():
    html = build.render_markdown("Spend a charge to let it roll {?a d2?} on that roll.")
    assert '<span class="suspect" tabindex="0" title="' + suspect.NOTE + '">a d2' in html
    assert '<span class="suspect-note"> (' + suspect.NOTE.lower() in html  # read out, hidden on screen
    assert "{?" not in html and "?}" not in html


def test_two_marks_on_a_line_stay_separate():
    html = build.render_markdown("{?3?} charges and {?1d4?} cold")
    assert html.count('class="suspect"') == 2 and "charges and" in html


def test_plain_text_spells_the_mark_out_for_the_bot():
    assert suspect.plain("roll {?a d2?} on it") == "roll a d2 (" + suspect.NOTE.lower() + ") on it"


def test_ordinary_braces_and_question_marks_are_left_alone():
    assert suspect.to_html("Who? {x} and ?} {? alone") == "Who? {x} and ?} {? alone"


def test_the_style_sheet_styles_the_mark():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".suspect" in css and ".suspect-note" in css


def test_the_reliquary_keeps_its_hard_to_hear_die_marked():
    page = (ROOT / "content" / "wiki" / "reliquary-of-two-flames.md").read_text(encoding="utf-8")
    assert "{?a d2?}" in page


def test_no_raw_mark_reaches_the_built_site(real_build):
    for html in sorted(real_build.out.glob("**/*.html")):
        text = html.read_text(encoding="utf-8")
        assert "{?" not in text, html


def test_the_bot_corpus_spells_marks_out(real_build):
    corpus = json.loads((real_build.out / "bot" / "corpus.json").read_text(encoding="utf-8"))
    texts = [p["text"] for p in corpus["posts"]] + [w["text"] for w in corpus["wiki"]]
    assert not any("{?" in t for t in texts)
    assert any(suspect.NOTE.lower() in t for t in texts)
