"""Item rules Ryan posted on Discord are on the item's wiki page (Chris, 2026-11-04).

Ryan posts an item's rules on Discord the night it turns up; the session post's Loot list often keeps
only its name. Each item below had a Discord post with its rules (dated to the session it came up in)
and a wiki page without them.
"""
from pathlib import Path

import yaml

WIKI = Path(__file__).resolve().parent.parent / "content" / "wiki"

# page: words its rules section must keep
RYAN_ITEMS = {
    "locket-of-the-last-laugh": ("attunement", "60 feet", "DC 15 Wisdom", "natural 1"),
    "twilight-crest": ("3 charges", "aid", "spirit guardians", "enervation", "three dawns"),
    "shades-ring": ("attunement", "invisibility", "Stealth"),
    "charm-of-mass-heroism": ("potion of heroism", "30 feet", "vanishes"),
    "winter-wolf-teeth": ("DC 12 Dexterity", "4d8", "immunity to cold"),
}


def _parts(slug: str) -> tuple[dict, str]:
    text = (WIKI / f"{slug}.md").read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front) or {}, body


def test_ryan_items_have_his_rules():
    for slug, words in RYAN_ITEMS.items():
        _, body = _parts(slug)
        assert "## What it does" in body, slug
        rules = body.split("## What it does", 1)[1].split("<!-- from-the-log -->", 1)[0]
        for word in words:
            assert word.lower() in rules.lower(), f"{slug}: {word!r}"


def test_ryan_items_cite_his_post():
    for slug in RYAN_ITEMS:
        meta, _ = _parts(slug)
        assert any(s.startswith("discord-") for s in meta.get("sources") or []), slug


def test_khazans_ring_is_the_signet_ring():
    # Ryan's art for "Khazan's Ring" (8/13/2024) is the sigil ring Kasimir held that night
    meta, _ = _parts("signet-ring")
    assert "Khazan's Ring" in (meta.get("aliases") or [])
