"""Wiki gaps filled from the texts Ryan shared at the table (Chris, 2026-11-02).

Chris pasted Ryan's Discord read-alouds (4/16/2024, 8/13/2024, 10/29/2024, 1/14/2025, 6/3/2025) "to fill in
any wiki gaps". These checks keep those facts on the pages: a page whose `source:` is exactly
"Compiled from the adventure log" is rebuilt by `just wiki-from-log`, which would wipe them.
"""
from pathlib import Path

import pytest

WIKI = Path(__file__).resolve().parent.parent / "content" / "wiki"
REBUILT = "source: Compiled from the adventure log\n"

# page -> words its Malron's Account must keep, each from one of Ryan's texts
FACTS = {
    "erevan-lowenhart": ["council of princes", "style of the lion", "royal line"],
    "othrondil": ["Forest of Twilight", "council of princes"],
    "king-barov": ["old Zarovia", "iron fist"],
    "dusk-elves": ["fewer than a hundred", "naming it Barovia"],
    "kasimir": ["barely a century old"],
    "escher": ["a bard from Barovia"],
    "arabelle": ["Talisman of Echoes"],
    "van-richten": ["undead dire wolf", "light lingers in the valley"],
    "madam-eva": ["while light lingered in the valley"],
    "drusilla": ["Lake Baratok"],
    "rictavio-s-carnival-of-wonders": ["three pots of paint"],
    "hat-of-disguise": ["Vistani camp by Vallaki"],
    "amulet-of-proof-against-detection-and-location": ["Ezmerelda", "first places he looked"],
    "lake-baratok": ["blocks all magic"],
    "forest-folk": ["loose society of hermits", "land and the weather"],
    "mother-night": ["darkness, trickery and the occult"],
    "lady-fiona-wachter": ["banished from Berez", "Lady Lovina Wachter", "Ezra"],
    "baba-lysaga": ["her students as her children"],
    "leo-dilisnya": ["Lady Lovina Wachter", "hunted Leo down"],
    "tsolenka-pass": ["curtain of green flame"],
    "amulet-of-knights-passage": ["white stone", "only that it is a key"],
    "bracelet-of-warding": ["3 charges", "regains 1 charge each dawn"],
    "andral": ["Markovia's counsel", "songs of prayer"],
    "andrals-scroll": ["Faithfully yours, Andral"],
    "argynvost": ["Protector of the Balinok Mountains", "true dragon form"],
    "order-of-the-silver-dragon": ["honor as a shield and truth as a guide"],
    "silver-tablet-and-banner": ["hidden stone shelf"],
    "moontouched-rapier": ["hole in the mortar"],
    # Chris 2026-11-02: the party heard this at a Vistani campfire and takes it as true
    "ireena-kolyana": ["went fishing", "Kolyan Indirovich", "set us wondering"],
    "izek-strazni": ["fishing trip", "doll of her"],
}


def _ours(stem: str) -> str:
    text = (WIKI / f"{stem}.md").read_text(encoding="utf-8")
    return text.split("<!-- from-the-log -->")[0]


@pytest.mark.parametrize("stem", sorted(FACTS))
def test_table_text_facts_stay_on_the_page(stem):
    ours = _ours(stem)
    assert REBUILT not in ours, f"{stem}: `just wiki-from-log` would delete its description"
    missing = [w for w in FACTS[stem] if w not in ours]
    assert not missing, f"{stem} lost {missing}"


@pytest.mark.parametrize("stem", sorted(FACTS))
def test_story_cites_a_post(stem):
    ours = _ours(stem)
    assert "## Description" in ours or "## What it does" in ours
    assert "(/posts/" in ours, f"{stem}: every story links the session it comes from"


@pytest.mark.parametrize("stem", ["bracelet-of-warding", "amulet-of-knights-passage"])
def test_rules_from_the_item_card_keep_their_source_hidden(stem):
    # Chris, 2026-11-04: no visible "From the item card shared at the table" line; the card is a
    # hidden discord- id in the page's sources (tests/test_player_mentions.py).
    assert "## What it does" in _ours(stem) and "shared at the table" not in _ours(stem)
    assert any(s.startswith("discord-") for s in _page(WIKI / f"{stem}.md").sources)


def test_heart_stone_post_has_ryans_second_paragraph():
    # Chris 2026-11-02 picked "add it to the post": the 1/14/2025 post had only the first half
    post = WIKI.parent / "posts" / "2025-01-14-the-hunt-for-the-heart-stone.md"
    text = post.read_text(encoding="utf-8")
    for words in ["banished from Berez", "Lady Lovina Wachter", "House Wachter has been loyal"]:
        assert words in text


# --- Ryan's Discord texts as hidden sources (Chris, 2026-11-03: "copied from discord as a data source
# and tagged as such in the meta-data", "hidden metadata") -------------------------------------------

import build  # noqa: E402
import wiki  # noqa: E402

FROM_RYAN = ("shared at the table", "Ryan shared", "Ryan's Discord post", "notes from the table")


def _page(path):
    return wiki.parse_wiki_page(path, build.split_front_matter)


def test_every_page_written_from_ryans_texts_names_a_discord_source():
    untagged = [p.stem for p in sorted(WIKI.glob("*.md"))
                if any(w in _ours(p.stem) for w in FROM_RYAN)
                and not any(s.startswith("discord-") for s in _page(p).sources)]
    assert not untagged, f"pages written from Ryan's texts with no discord- id in sources: {untagged}"


def test_discord_sources_sit_on_pages_the_log_tool_keeps():
    tagged = [p for p in WIKI.glob("*.md") if any(s.startswith("discord-") for s in _page(p).sources)]
    assert len(tagged) >= 40
    rebuilt = [p.stem for p in tagged if REBUILT in p.read_text(encoding="utf-8")]
    assert not rebuilt, f"`just wiki-from-log` would drop their sources: {rebuilt}"


def _quote(text: str) -> str:
    return " ".join(line[2:].strip() for line in text.splitlines() if line.startswith("> "))


def test_werewolf_manuscript_is_on_its_page_word_for_word():
    # Ryan's 4/16/2024 text; the Tser Pool post quotes it in full, and the wiki page now does too.
    post = (WIKI.parent / "posts" / "2024-04-16-tser-pool.md").read_text(encoding="utf-8")
    page = _ours("a-study-of-the-werewolf-s-curse")
    assert _quote(post) and _quote(page) == _quote(post)
    assert "van Richten" in page and "Arturi" not in page


def test_van_richten_wrote_the_werewolf_manuscript():
    # The Dungeon Master page once called it "Arturi's manuscript".
    dm = (WIKI / "dungeon-master.md").read_text(encoding="utf-8")
    assert "Van Richten's manuscript, *A Study of the Werewolf's Curse*" in dm and "Arturi's manuscript" not in dm
