"""Links say where they go (Chris, 2026-11-03): plain white names in the wiki facts box, the
"Appears in" lists, the map's session lists and the card titles looked like ordinary words. A link
to a wiki page (a noun: a person, place or thing) is gold, like the wiki names in posts; a link to a
session post is red. The red session number discs keep their own look, and the footer stays as it is."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "static" / "style.css").read_text(encoding="utf-8"), flags=re.S)

WIKI = '[href*="/wiki/"]'
POST = '[href*="/posts/"]'
TITLE = ":not(.num):not(.place-num)"


def _declarations(selector: str) -> str:
    """Every declaration from the rules whose selector list names `selector` exactly, in order."""
    found = []
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        if selector in [s.strip() for s in selectors.split(",")]:
            found.append(body)
    assert found, f"style.css needs a rule for {selector}"
    return ";".join(found)


def _last(prop: str, decls: str) -> str:
    values = re.findall(rf"(?:^|[;\s]){prop}:\s*([^;]+)", decls)
    assert values, f"no {prop} set"
    return values[-1].strip()


def _tokens() -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", CSS))


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_facts_box_wiki_links_gold_session_links_red():
    assert _last("color", _declarations(f".infobox dd a{WIKI}")) == "var(--gold)"
    assert _last("color", _declarations(f".infobox dd a{POST}")) == "var(--link-red)"


def test_session_list_titles_are_red():
    # The wiki "Appears in" list, the map's "The road so far" and the map place card all use .session-list.
    assert _last("color", _declarations(f".session-list a{TITLE}")) == "var(--link-red)"


def test_card_titles_follow_their_destination():
    # Chronicle and search cards for sessions, wiki index and search cards for wiki pages, Previous/Next.
    assert _last("color", _declarations(f".card a.stretched{WIKI}")) == "var(--gold)"
    assert _last("color", _declarations(f".card a.stretched{POST}")) == "var(--link-red)"
    assert _last("color", _declarations(".pager-card strong")) == "var(--link-red)"


def test_hover_matches_the_rest_of_the_site():
    gold_hover = _last("color", _declarations(".prose a.wiki-link:hover"))
    red_hover = _last("color", _declarations("a:hover"))
    assert _last("color", _declarations(f".infobox dd a{WIKI}:hover")) == gold_hover
    assert _last("color", _declarations(f".infobox dd a{POST}:hover")) == red_hover
    assert _last("color", _declarations(f".session-list a{TITLE}:hover")) == red_hover
    for sel in (".infobox dd a:hover", f".session-list a{TITLE}:hover"):
        assert "underline" in _last("text-decoration", _declarations(sel))


def test_session_number_discs_keep_their_colour():
    # Map place cards draw their discs as a.place-num inside a .session-list (templates/map.html), and
    # `.session-list a` outranks `.place-num`: title colours must skip the discs.
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS):
        for sel in (s.strip() for s in selectors.split(",")):
            if sel.startswith(".session-list a") and re.search(r"(?:^|[;\s])color:", body) and ".num" not in sel and ".place-num" not in sel:
                assert TITLE in sel, sel
    assert _last("color", _declarations(".session-list a.num")) == "#f2c6ce"
    assert _last("color", _declarations(".infobox .num")) == "#f2c6ce"
    assert _last("color", _declarations(".place-num")) == "#f2c6ce"


def test_footer_links_unchanged():
    assert _last("color", _declarations(".site-footer a")) == "#d9cfc6"


def test_gold_and_red_are_readable_on_page_and_cards():
    tokens = _tokens()
    for ground in ("--bg", "--surface", "--surface-2"):
        assert _contrast(tokens["--gold"], tokens[ground]) >= 4.5, ground
        assert _contrast(tokens["--link-red"], tokens[ground]) >= 4.5, ground
