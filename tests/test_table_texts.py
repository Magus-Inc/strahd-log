"""Wiki gaps filled from the texts Ryan shared at the table (Chris, 2026-11-02).

Chris pasted Ryan's Discord read-alouds (8/13/2024, 10/29/2024, 1/14/2025, 6/3/2025) "to fill in
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
    "ireena-kolyana": ["went fishing", "Kolyan Indirovich"],
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
def test_rules_from_the_item_card_are_dated(stem):
    assert "*From the item card shared at the table (3 June 2025). In short:*" in _ours(stem)


def test_heart_stone_post_has_ryans_second_paragraph():
    # Chris 2026-11-02 picked "add it to the post": the 1/14/2025 post had only the first half
    post = WIKI.parent / "posts" / "2025-01-14-the-hunt-for-the-heart-stone.md"
    text = post.read_text(encoding="utf-8")
    for words in ["banished from Berez", "Lady Lovina Wachter", "House Wachter has been loyal"]:
        assert words in text
