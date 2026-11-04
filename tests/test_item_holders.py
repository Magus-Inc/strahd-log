"""Who holds an item, or that it was used up, is on its wiki page (Chris, 2026-11-04).

Chris settled these before asking the table, after the posts and transcripts were searched for them.
"""
from pathlib import Path

WIKI = Path(__file__).resolve().parent.parent / "content" / "wiki"

# page: words its page must say
SETTLED = {
    "moontouched-rapier": ("Aera took it",),
    "spear-of-the-huntress": ("Shabasta", "2d6 temporary hit points", "{?"),
    "tome-of-strahd": ("I carry it",),
    "amber-shard-of-seriach": ("Aera",),
    "amber-shard-of-durst-manor": ("Aera",),
    "candle-of-long-resting": ("used up", "The Echoing Choirs of Ravenloft"),
    "heart-stone": ("used up",),
    "potion-of-fire-breath": ("used up",),
    "twilight-crest": ("threw it to Shabasta", "enervation"),
    "clairvoyance-stone": ("Aera carries it",),
    # A player character who leaves the party keeps what they won, ready if they come back (Chris)
    "telescope": ("Last seen with Grom",),
    "silvered-battleaxe": ("Last seen with Liren",),
    "locket-of-the-last-laugh": ("Last seen with Liren",),
    "cloak-of-elvenkind": ("Last seen with Gumbo",),
    "charm-of-mass-heroism": ("Last seen with Gumbo",),
}


def test_settled_holders_are_on_the_pages():
    for slug, words in SETTLED.items():
        text = (WIKI / f"{slug}.md").read_text(encoding="utf-8")
        for word in words:
            assert word in text, f"{slug}: {word!r}"


def test_spear_rules_are_in_a_rules_section():
    text = (WIKI / "spear-of-the-huntress.md").read_text(encoding="utf-8")
    rules = text.split("## What it does", 1)[1].split("<!-- from-the-log -->", 1)[0]
    assert "2d6 temporary hit points" in rules
    # Grant read the disadvantage out at the table (9/1/2026), but the book's blood spear doesn't have it
    assert "{?" in rules and "disadvantage" in rules
