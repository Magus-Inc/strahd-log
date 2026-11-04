"""Player names and source lines a reader can see (Chris, 2026-11-04).

Chris, on Aera's page: "From Chris's character notes and the session logs. That's on Aera's page. I
don't like that. We mostly keep sources private and I don't like seeing my name too often. Mainly
expecting it on Malron page and some slides." From the review page he then picked:

- A player's real name shows only in a player character's Player box ("Played by" line too), on the
  Dungeon Master page, and in an art credit ("drawn by Grant Haseloff"). Story text says "his player".
- No line says where a page came from: no "session logs", notes, recordings, "Ryan shared", "shared
  at the table", no gray source line under a wiki page, and picture credits name only the model and
  the date. Where a page came from stays in its hidden `sources:` ids.
- The table-talk margin notes ("the DM", "Shabasta's player") and the Start page stay as they are.
"""
import html
import re
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "content" / "wiki"
DM_PAGE = "wiki/dungeon-master/index.html"

SOURCE_WORDS = ("session logs", "session log,", "session notes", "character notes", "the recording",
                "no recording", "Ryan shared", "Ryan's", "Ryan’s", "shared at the table",
                "notes from the table", "Discord post", "combined with the session",
                "Compiled from the adventure log,", "Written on Obsidian Portal")


def _players() -> set[str]:
    """Every real name in a wiki page's `player:` or `people:`, with its first name."""
    names = set()
    for p in WIKI.glob("*.md"):
        meta, _ = build.split_front_matter(p.read_text(encoding="utf-8"))
        found = [meta.get("player")] + [x.get("name") for x in meta.get("people") or [] if isinstance(x, dict)]
        for name in filter(None, found):
            name = str(name)
            names.add(name)
            names.add(name.split()[0])
    return names


def _visible(page: str) -> str:
    """The words a reader sees, less the places a real name belongs (the Player box, art credits)."""
    page = page.split("<body", 1)[-1]
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r"<dt>(?:Player|Played by|Run by)</dt>\s*<dd>.*?</dd>", " ", page, flags=re.S)
    page = re.sub(r'<p class="muted">(Played|Run) by .*?</p>', " ", page, flags=re.S)
    page = re.sub(r'alt="([^"]*)"', r" \1 ", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return re.sub(r"drawn by [A-Z][\w’']+(?: [A-Z][\w’']+)*", " ", text)


def _pages(real_build):
    for p in sorted(real_build.out.rglob("*.html")):
        rel = p.relative_to(real_build.out).as_posix()
        if rel != DM_PAGE:
            yield rel, _visible(p.read_text(encoding="utf-8"))


def test_the_name_list_is_the_real_one():
    names = _players()
    assert {"Christopher O’Toole", "Ryan Mathews", "Grant", "Cole"} <= names


def test_no_real_name_outside_the_player_box(real_build):
    words = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(_players(), key=len, reverse=True)) + r")\b")
    found = [f"{rel}: {m.group(0)} in “…{text[max(0, m.start() - 50):m.end() + 50].strip()}…”"
             for rel, text in _pages(real_build) for m in words.finditer(text)]
    assert not found, "\n".join(found)


def test_no_line_says_where_a_page_came_from(real_build):
    found = [f"{rel}: “{w}”" for rel, text in _pages(real_build) for w in SOURCE_WORDS if w in text]
    assert not found, "\n".join(found)


def test_wiki_pages_show_no_gray_source_line(real_build):
    shown = [p.parent.name for p in (real_build.out / "wiki").glob("*/index.html")
             if 'class="source' in p.read_text(encoding="utf-8")]
    assert not shown, shown


def test_picture_credits_name_only_the_model():
    """No month or year either (Chris, 2026-11-04): "AI-generated image (Google Gemini). Not official art."."""
    credit = re.compile(r"AI-generated (?:image|images|portrait) \(([^)]*)\)")
    dated = [f"{p.relative_to(ROOT).as_posix()}: {m.group(0)}"
             for folder in ("posts", "wiki") for p in sorted((ROOT / "content" / folder).glob("*.md"))
             for m in credit.finditer(p.read_text(encoding="utf-8")) if m.group(1) != "Google Gemini"]
    assert not dated, "\n".join(dated)


def test_picture_credits_say_nothing_about_where_the_picture_came_from():
    """At most one short sentence after the credit that helps read the picture, never "drawn from"."""
    drawn = [p.relative_to(ROOT).as_posix()
             for folder in ("posts", "wiki") for p in sorted((ROOT / "content" / folder).glob("*.md"))
             if re.search(r"\*AI-generated[^*]*drawn from", p.read_text(encoding="utf-8"))]
    assert not drawn, drawn
