"""No module room codes in Malron's words (Chris, 2026-11-03).

On the Dragon Skull post Chris wrote: "Malron account wouldn't use the room codes like k-20, or
k-62 as that's above the table talk, he could describe the room or call it something instead. If
we want to keep those clues for readers they go in the blue handwriting text to the side." Room
keys from the Curse of Strahd book (K20, K-62, room S15...) are table talk: the story and the recap
lists name or describe the room, and a code a reader may want goes in a `Note:` margin paragraph.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "content" / "posts"
WIKI = ROOT / "content" / "wiki"
CORRECTIONS = ROOT / "data" / "log-extract" / "corrections.yaml"
ROOM_CODE = re.compile(r"\b(?:[Rr]ooms? )?[A-Z]-?\d{1,3}[a-z]?\b")


def malrons_words(text: str) -> str:
    """A post's body without front matter or margin notes."""
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    return "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("Note:"))


def room_codes(text: str) -> list[str]:
    return ROOM_CODE.findall(malrons_words(text))


def test_the_check_catches_the_codes_chris_quoted():
    post = ("---\ntitle: T\n---\n\n## Story\n\nThe ladder brought us to K-20, a landing.\n\n"
            "On the larder level, room K-62, we met Cyrus.\n\n"
            "In the courtyard, room S12, we met Clovin.\n\n## Key Locations\n\n"
            "* **The Asylum**: Room S15, a lightless corridor.\n* **Front Courtyard**: K1.\n")
    assert room_codes(post) == ["K-20", "room K-62", "room S12", "Room S15", "K1"]


def test_margin_notes_may_keep_the_codes():
    post = ("---\ntitle: K1\n---\n\n## Story\n\nWe climbed to a landing above the Heart of Sorrow.\n\n"
            "Note: That landing is K20 in the book; the larder is K62.\n\nCR 14 talk and a d20 roll.\n")
    assert room_codes(post) == []


@pytest.mark.parametrize("post", sorted(POSTS.glob("*.md")), ids=lambda p: p.stem)
def test_posts_keep_room_codes_to_the_margin(post):
    assert room_codes(post.read_text(encoding="utf-8")) == []


# The wiki (Chris, 2026-11-03): the same in Malron's Account and the adventure-log lines under it.
# A page that is a room in the book keeps its code in `book_room:`, shown in the facts box.

def wiki_page(path: Path) -> tuple[dict, str]:
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)), m.group(2)


@pytest.mark.parametrize("page", sorted(WIKI.glob("*.md")), ids=lambda p: p.stem)
def test_wiki_pages_keep_room_codes_to_the_facts_box(page):
    meta, body = wiki_page(page)
    assert ROOM_CODE.findall(body) == []
    assert [a for a in meta.get("aliases") or [] if ROOM_CODE.fullmatch(str(a))] == []


def test_book_rooms_are_in_the_facts_box():
    rooms = {p.stem: wiki_page(p)[0].get("book_room") for p in WIKI.glob("*.md")}
    assert rooms["hall-of-bones"] == "K67" and rooms["strahds-tomb"] == "K86"


def test_log_corrections_do_not_put_codes_back():
    """tools/wiki_from_extract.py rebuilds the log lines from the extracts and these corrections."""
    fixes = yaml.safe_load(CORRECTIONS.read_text(encoding="utf-8"))
    assert [v for v in (fixes.get("facts") or {}).values() if v and ROOM_CODE.search(v)] == []
    extracts = "".join(p.read_text(encoding="utf-8") for p in CORRECTIONS.parent.glob("posts-part*.json"))
    codes = {c.strip('"') for c in re.findall(r'"[A-Z]-?\d{1,3}"', extracts)}
    assert codes <= set(fixes.get("not_alias") or [])
