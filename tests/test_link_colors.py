"""Links in lists read as links (Chris, 2026-11-03): plain white names in the wiki facts box, the
"Appears in" lists and the map's session lists looked like ordinary words. They are gold, like the
wiki names in posts; the red session number discs beside them stay red."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "static" / "style.css").read_text(encoding="utf-8"), flags=re.S)


def _declarations(selector: str) -> str:
    """Every declaration from the rules whose selector list names `selector` exactly, in order."""
    found = []
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        names = [s.strip() for s in selectors.split(",")]
        if selector in names:
            found.append(body)
    assert found, f"style.css needs a rule for {selector}"
    return ";".join(found)


def _last(prop: str, decls: str) -> str:
    values = re.findall(rf"(?:^|[;\s]){prop}:\s*([^;]+)", decls)
    assert values, f"no {prop} set"
    return values[-1].strip()


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_facts_box_links_are_gold():
    assert _last("color", _declarations(".infobox dd a")) == "var(--gold)"


def test_session_list_titles_are_gold():
    # The wiki "Appears in" list, the map's "The road so far" and the map place card all use .session-list.
    assert _last("color", _declarations(".session-list a:not(.num):not(.place-num)")) == "var(--gold)"


def test_session_number_discs_stay_red():
    # The gold must not reach the discs: map place cards draw theirs as a.place-num inside a
    # .session-list (templates/map.html), so a bare `.session-list a` rule would beat `.place-num`.
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        for sel in (s.strip() for s in selectors.split(",")):
            if sel.startswith(".session-list a") and ("--gold" in body or "#f0d48e" in body):
                assert ":not(.num)" in sel and ":not(.place-num)" in sel, sel
    assert _last("color", _declarations(".place-num")) == "#f2c6ce"
    # `.session-list a` outranks `.place-num`, so it must leave the colour to the title and disc rules.
    assert not re.search(r"(?:^|[;\s])color:", _declarations(".session-list a"))
    assert _last("color", _declarations(".session-list a.num")) == "#f2c6ce"
    assert _last("color", _declarations(".infobox .num")) == "#f2c6ce"


def test_list_links_hover_like_wiki_names():
    wiki_hover = _declarations(".prose a.wiki-link:hover")
    for sel in (".infobox dd a:hover", ".session-list a:not(.num):not(.place-num):hover"):
        hover = _declarations(sel)
        assert _last("color", hover) == _last("color", wiki_hover)
        assert "underline" in _last("text-decoration", hover)


def test_gold_is_readable_on_page_and_cards():
    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", CSS))
    for ground in ("--bg", "--surface", "--surface-2"):
        assert _contrast(tokens["--gold"], tokens[ground]) >= 4.5, ground
