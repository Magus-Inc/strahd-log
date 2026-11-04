"""Magic items from the session posts' Loot lists have wiki pages (Chris, 2026-11-04).

The unclaimed-loot list for the table found three with no page: a reader of the post had nowhere to look
them up, and nobody could be asked "who has it?" with a link.
"""
import re
from pathlib import Path

import build
import wiki

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "content" / "wiki"
POSTS = ROOT / "content" / "posts"

# page slug: (post it turned up in, words its page must say)
ITEMS = {
    "silvered-1-shortsword": ("2024-08-20-whispers-in-the-barons-mansion", ("+1", "Ireena")),
    "telescope": ("2024-04-16-tser-pool", ("around corners", "Grom")),
    "potion-of-fire-breath": ("2025-09-16-varushkas-key", ("Varushka", "Olfin")),
}


def _linker():
    pages = [wiki.parse_wiki_page(p, build.split_front_matter) for p in sorted(WIKI.glob("*.md"))]
    return wiki.Linker(pages)


def test_each_item_has_a_page_that_says_where_it_came_from():
    for slug, (post, words) in ITEMS.items():
        text = (WIKI / f"{slug}.md").read_text(encoding="utf-8")
        assert "type: item" in text, slug
        assert f"/posts/{post[11:]}/" in text or post[11:] in text, slug
        for word in words:
            assert word in text, f"{slug}: {word!r}"


def test_the_posts_link_to_the_new_pages():
    linker = _linker()
    for slug, (post, _) in ITEMS.items():
        body = (POSTS / f"{post}.md").read_text(encoding="utf-8").split("---", 2)[2]
        _, mentioned = linker.link(body)
        assert slug in mentioned, f"{post} never names {slug}"
