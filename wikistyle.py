"""One layout for every wiki page (Chris, 2026-11-02, looking at the Zorya page).

Wiki pages grew in layers: the summary under the title, sometimes an opening line or a stat block,
the "Description" in Malron's words with the picture in it, then "From the adventure log", one bullet
per session that retells the same story. Each difference is a setting in data/wiki-style.yaml, and
the build applies the settings to the rendered HTML, so the Markdown is never reworded and
tools/wiki_from_extract.py and the update-wiki skill keep writing pages the same way. The settings
are the wiki template options Tablebard can offer other campaigns later.
"""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Setting -> allowed values; the first value of each is "as written", which changes nothing.
OPTIONS = {
    "top": ["as-written", "picture", "infobox"],      # the first picture under the title, or in a facts box
    "story-heading": ["as-written", "account", "none"],  # "Description" is called Malron's Account, or has no heading
    "extras": ["as-written", "after-story"],          # sections above the story (a stat block) go after it
    "log": ["open", "folded", "hidden"],              # "From the adventure log" under a story: open, folded, gone
    "kinds": ["all", "people"],                        # which pages get the layout
}
TEXT = {"story-title": "Malron’s Account"}
AS_WRITTEN = {**{name: values[0] for name, values in OPTIONS.items()}, **TEXT}
PEOPLE = {"character", "npc", "creature", "deity"}

LOG_MARK = "<!-- from-the-log -->"
STORY_H2 = re.compile(r"<h2[^>]*>\s*Description\s*</h2>\n?")
WRITTEN_FROM = re.compile(r"<p><em>Written from the session logs\b.*?</em></p>\n?", re.S)
# A picture on its own line (maybe wrapped in a link), or a reader vote between pictures.
PICTURE = re.compile(r'<p>(?:<a [^>]*>)?<img [^>]*>(?:</a>)?</p>\n?|<div class="vote-group[^"]*">.*?</div>\n?', re.S)
# The line under a picture: a gray AI credit, or an italic caption such as "Crusty, drawn by Grant".
CAPTION = re.compile(r'\s*(<p class="ai-credit">.*?</p>|<p><em>(?!Written from)(?:(?!</p>).)*</em></p>)\n?', re.S)


def load_style(path: Path) -> dict:
    """The wiki's settings; a missing file means every page as written."""
    style = dict(AS_WRITTEN)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, value in data.items():
            if name in TEXT:
                style[name] = str(value)
                continue
            if name not in OPTIONS:
                raise ValueError(f"{path.name}: unknown setting {name!r}; known: {', '.join([*OPTIONS, *TEXT])}")
            if value not in OPTIONS[name]:
                raise ValueError(f"{path.name}: {name} must be one of {', '.join(OPTIONS[name])}, not {value!r}")
            style[name] = value
    return style


@dataclass
class Styled:
    html: str
    picture: str = ""  # the first picture and its caption, when the layout puts it at the top


def apply(html: str, style: dict, kind: str) -> Styled:
    style = {**AS_WRITTEN, **style}
    if style["kinds"] == "people" and kind not in PEOPLE:
        return Styled(html)
    body, mark, notes = html.partition(LOG_MARK)
    story = STORY_H2.search(body)
    picture = ""
    if style["top"] != "as-written":
        body, picture = take_picture(body)
    if style["extras"] == "after-story" and story:
        body = story_first(body)
    if style["story-heading"] == "account":
        body = STORY_H2.sub(f"<h2>{htmllib.escape(style['story-title'], quote=False)}</h2>\n", body, count=1)
        body = WRITTEN_FROM.sub("", body, count=1)
    elif style["story-heading"] == "none":
        body = STORY_H2.sub("", body, count=1)
    if story and mark and style["log"] == "hidden":
        return Styled(body.rstrip() + "\n", picture)
    if story and mark and style["log"] == "folded":
        notes = fold_notes(notes)
    return Styled(body + mark + notes, picture)


def take_picture(body: str) -> tuple[str, str]:
    m = PICTURE.search(body)
    if not m:
        return body, ""
    end, picture = m.end(), m.group(0)
    caption = CAPTION.match(body, end)
    if caption:
        picture, end = picture + caption.group(1) + "\n", caption.end()
    return body[:m.start()] + body[end:], picture


def story_first(body: str) -> str:
    """Whole sections between the opening lines and the story move to just after the story."""
    first_h2 = body.find("<h2")
    story = STORY_H2.search(body)
    if first_h2 < 0 or story.start() == first_h2:
        return body
    nxt = re.compile(r"<h2[ >]").search(body, story.end())
    story_end = nxt.start() if nxt else len(body)
    head, extras, story_part, rest = body[:first_h2], body[first_h2:story.start()], body[story.start():story_end], body[story_end:]
    return head + story_part.rstrip() + "\n" + extras + rest


def fold_notes(notes: str) -> str:
    count = len(re.findall(r"<li[ >]", notes))
    inner = re.sub(r"\s*<h2[^>]*>\s*From the adventure log\s*</h2>\n?", "\n", notes, count=1)
    word = "note" if count == 1 else "notes"
    return (f'\n<details class="log-notes">\n<summary>From the adventure log: {count} {word}, session by session</summary>'
            f"{inner.rstrip()}\n</details>\n")


def facts(page) -> list[tuple[str, object]]:
    """The facts box: other names, who plays a PC (or runs the game, for the DM), when we first and last saw them, how often."""
    out: list[tuple[str, object]] = []
    if page.aliases:
        out.append(("Also known as", ", ".join(page.aliases)))
    if getattr(page, "player", ""):
        out.append(("Run by" if getattr(page, "dm", False) else "Played by", page.player))
    seen = list(page.mentioned_in)
    if seen:
        first, last = seen[-1], seen[0]
        out.append(("First seen", (first.number, first.title, first.path)))
        if len(seen) > 1:
            out.append(("Last seen", (last.number, last.title, last.path)))
            out.append(("Sessions", len(seen)))
    return out
