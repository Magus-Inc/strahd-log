"""Rules the DM read out at the table belong on the wiki, not only in a session post (Chris, 2026-11-04).

Chris was unsure what the Reliquary of Two Flames does: the rules were in the 9/1/2026 transcript and the
post's Loot list, but the wiki page only hinted at them. A Discord search or a reader looking an item up
lands on the wiki page, so an item whose Loot entry states its rules (charges, actions, once a day) gets
a rules section on its page.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "content" / "wiki"
POSTS = ROOT / "content" / "posts"
RULES_SECTIONS = ("## What it does", "## Stats", "## What the beacon does")
# Words in a Loot entry that mean it states how the item works, not just what it is.
STATES_RULES = re.compile(r"\b(charges?|reaction|bonus action|as an action|long rest|short rest|attunement|"
                          r"once per|per day|once a day|next dawn)\b", re.IGNORECASE)


def _front(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def _items() -> dict[str, tuple[Path, list[str]]]:
    out = {}
    for page in sorted(WIKI.glob("*.md")):
        meta = _front(page.read_text(encoding="utf-8"))
        if meta.get("type") == "item":
            out[meta["title"]] = (page, [meta["title"], *(meta.get("aliases") or [])])
    return out


def _loot_lines() -> list[tuple[str, str]]:
    lines = []
    for post in sorted(POSTS.glob("*.md")):
        m = re.search(r"^## Loot\n(.*?)(?=^## |\Z)", post.read_text(encoding="utf-8"), re.S | re.M)
        if m:
            lines += [(post.stem, line) for line in m.group(1).splitlines() if line.startswith("*")]
    return lines


def _name(line: str) -> str:
    m = re.match(r"\*\s+\*\*(.+?)\*\*", line)
    return m.group(1).casefold() if m else ""


def test_items_whose_rules_were_stated_have_a_rules_section():
    loot = _loot_lines()
    missing = []
    for title, (page, names) in _items().items():
        text = page.read_text(encoding="utf-8")
        if any(s in text for s in RULES_SECTIONS):
            continue
        folded = {n.casefold() for n in names}
        stated = [stem for stem, line in loot if _name(line) in folded and STATES_RULES.search(line)]
        if stated:
            missing.append(f"{title} (rules in {stated[0]})")
    assert not missing, "item pages missing a '## What it does' section: " + ", ".join(missing)


def test_reliquary_says_what_it_does():
    text = (WIKI / "reliquary-of-two-flames.md").read_text(encoding="utf-8")
    rules = text.split("## What it does", 1)[1].split("<!-- from-the-log -->", 1)[0]
    for words in ("2 charges", "long rest", "30 feet", "reaction", "Once ever", "back to life"):
        assert words in rules
    # the table's Pokémon joke is not a rule: the flames are never summoned to fight
    assert "summon" not in rules.lower()


def test_beacon_effect_is_on_argynvostholt():
    text = (WIKI / "argynvostholt.md").read_text(encoding="utf-8")
    assert "## What the beacon does" in text and "+1 to AC" in text and "+1 to saving throws" in text
