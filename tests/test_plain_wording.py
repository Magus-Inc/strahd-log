"""Plain wording in the text we write (Chris, 2026-11-03).

Chris found "Before the heist we counted it a shard of the Ladies Three's power, lying in the
castle's south crypts" hard to follow. Malron's words on the wiki stay first person and in-world,
but plain: data/plain-wording.yaml lists the archaic words and stiff turns of phrase to avoid.
Lines that start with ">" and anything in quotation marks are other people's words, kept word for word.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "content" / "wiki"
AVOID = yaml.safe_load((ROOT / "data" / "plain-wording.yaml").read_text(encoding="utf-8"))["avoid"]
QUOTE = re.compile(r"“[^”\n]*”|‘[^’\n]*’|\"[^\"\n]*\"")


def ours(text: str) -> str:
    """The Malron's-words description of a wiki page, without quotes or word-for-word texts."""
    if "Malron's words" not in text and "Malron’s words" not in text:
        return ""
    text = text.split("<!-- from-the-log -->")[0]
    lines = [l for l in text.splitlines() if not l.lstrip().startswith((">", "*As ", "![", "*AI-generated"))]
    return QUOTE.sub("", "\n".join(lines))


def stiff(text: str) -> list[str]:
    found = []
    for entry in AVOID:
        for m in re.finditer(entry["pattern"], text, re.IGNORECASE):
            found.append(f"{m.group(0)!r} -> {entry['instead']}")
    return found


def test_the_list_catches_the_line_chris_quoted():
    line = ("Before the heist we counted it a shard of the Ladies Three's power, "
            "lying in the [castle](/wiki/castle-ravenloft/)'s south crypts")
    assert any("counted it a" in hit for hit in stiff(line))


def test_quotes_and_kept_texts_are_left_alone():
    page = ("*Written from the session logs, in Malron's words.*\n\n"
            "It said “Ere the dawn, betwixt the hills.”\n\n> Silent, with naught but stars to guide.\n")
    assert stiff(ours(page)) == []


@pytest.mark.parametrize("page", sorted(WIKI.glob("*.md")), ids=lambda p: p.stem)
def test_wiki_descriptions_use_plain_words(page):
    assert stiff(ours(page.read_text(encoding="utf-8"))) == []
