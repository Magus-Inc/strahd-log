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


def test_izeks_battleaxe_went_to_liren():
    # Ryan's 12/10/2024 post: Izek carried a silvered +2 battleaxe; Chris: Liren took it
    meta, body = _parts("silvered-battleaxe")
    assert meta.get("type") == "item" and any(s.startswith("discord-") for s in meta.get("sources") or [])
    assert "Liren" in body and "+2" in body
    post = (WIKI.parent / "posts" / "2024-12-10-the-fall-of-izek.md").read_text(encoding="utf-8")
    loot = post.split("## Loot", 1)[1].split("\n## ", 1)[0]
    assert "Silvered Battleaxe" in loot and "Liren" in loot


def test_hell_hound_whisperer_is_the_amber_shard():
    # Ryan: "an amber shard of Seriach, the Hell Hound Whisperer" is one item, not two
    assert not (WIKI / "hell-hound-whisperer.md").exists()
    meta, body = _parts("amber-shard-of-seriach")
    assert "Hell Hound Whisperer" in (meta.get("aliases") or [])
    redirects = yaml.safe_load((WIKI.parent.parent / "data" / "redirects.yaml").read_text(encoding="utf-8"))
    assert redirects["wiki"]["hell-hound-whisperer"] == "amber-shard-of-seriach"


def test_twilight_crest_spell_is_enervation():
    for path in (WIKI.parent / "posts").glob("*.md"):
        assert "Innervation" not in path.read_text(encoding="utf-8"), path.name


def test_glamour_weave_pelt_has_the_book_rules_marked_standard():
    _, body = _parts("glamour-weave-pelt")
    rules = body.split("## What it does", 1)[1].split("<!-- from-the-log -->", 1)[0]
    assert "Standard rules from the book" in rules and "bonus action" in rules and "d4" in rules


def test_ryans_march_18_loot_is_in_the_march_11_post():
    # Ryan's #loot post of 3/18/2025 has no session post of its own; Chris: put it in the 3/11 post
    post = (WIKI.parent / "posts" / "2025-03-11-wizard-of-wines-vineyard.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(post.split("---", 2)[1])
    assert any(s.startswith("discord-") for s in meta["sources"])
    loot = post.split("## Loot", 1)[1].split("\n## ", 1)[0]
    for words in ("greater healing", "dust of disappearance", "75 gold"):
        assert words in loot.lower()
