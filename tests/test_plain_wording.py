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


POSTS = ROOT / "content" / "posts"
# A name with a fact in brackets after it, such as "**Khazan (Deceased)**", "**Ezmerelda** (mentioned)"
# or a room key like "the courtyard (S12)" (Chris, 2026-11-03: never on the site; say it in a sentence).
NAME_FACT = re.compile(r"\*\*[^*\n]*\([A-Za-z][^)\n]*\)[^*\n]*\*\*|\*\*:? \([A-Za-z][^)\n]*\)|\((?:S|K-?)\d+[^)\n]*\)")


def story(text: str) -> str:
    """A post's story, without quotes, margin notes, pictures or texts kept word for word."""
    m = re.search(r"^## Story\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    lines = [l for l in (m.group(1) if m else "").splitlines()
             if not l.lstrip().startswith((">", "![", "*", "Note:"))]
    return QUOTE.sub("", "\n".join(lines))


def test_the_post_story_check_skips_quotes_and_kept_texts():
    post = ("## Story\n\n### A Scene\n\nIt said “Ere the dawn.”\n\n*Naught but stars, as Kasimir told it.*\n\n"
            "Note: the DM bade us roll.\n\n## Key Locations\n\n* **Bade Hall**: Not the story.\n")
    assert stiff(story(post)) == []


@pytest.mark.parametrize("post", sorted(POSTS.glob("*.md")), ids=lambda p: p.stem)
def test_post_stories_use_plain_words(post):
    assert stiff(story(post.read_text(encoding="utf-8"))) == []


def test_the_name_fact_check_catches_brackets_after_names():
    for line in ["* **Khazan (Deceased)**: An archmage.", "* **Ezmerelda** (mentioned): She told us.",
                 "* **Rahadin**: (Mentioned) Strahd's chamberlain.", "In the courtyard (S12) we met Clovin."]:
        assert NAME_FACT.search(line), line
    assert not NAME_FACT.search("*AI-generated image (Google Gemini, November 2026).*")
    assert not NAME_FACT.search("We consulted the map Ismark gave us (I’ve made a crude copy).")


@pytest.mark.parametrize("post", sorted(POSTS.glob("*.md")), ids=lambda p: p.stem)
def test_posts_put_no_fact_in_brackets_after_a_name(post):
    lines = [l for l in post.read_text(encoding="utf-8").splitlines() if not l.startswith("Note:")]
    assert [l for l in lines if NAME_FACT.search(l)] == []
