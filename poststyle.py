"""One look for every session post, whatever era it was written in.

The posts were written over three years in five styles: story only, place headings, bold first lines
as headings, the recap template (Characters, Summary, Key Locations...), and the template with an
"At a Glance" box. Each difference is a setting in data/post-style.yaml, and the build applies the
settings to the rendered HTML, so the Markdown the players wrote is never reworded. The settings and
their values are the template options Tablebard can offer other campaigns later.

apply() runs on a post's freshly rendered Markdown, before wiki links are added, so a heading made
from a bold line carries no link and the first mention in the story gets it instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

import wiki

# Setting -> allowed values; the first value of each is "as written", which changes nothing.
OPTIONS = {
    "cast": ["pills+list", "pills", "list"],         # PCs present: pills under the title, a Characters list, or both
    "headings": ["as-written", "real"],              # bold first lines become headings; no "Summary:" colons
    "entries": ["as-written", "bullets"],            # recap entries: one bullet each, name in bold
    "links": ["as-written", "gold"],                 # hand-made wiki links look like the automatic ones
    "bold": ["as-written", "plain"],                 # no bold names mid-sentence in the story
    "glance": ["new-posts", "every-post", "none"],   # the "At a Glance" box (every-post is writing, not build)
    "tagline": ["keep", "every-post", "none"],       # the line under the title (every-post is writing)
    "picture": ["scene", "top"],                     # the feature picture beside its scene, or first
}
AS_WRITTEN = {name: values[0] for name, values in OPTIONS.items()}

# The recap template's sections. Their headings are h2; any other heading in a post is a place or a
# scene inside the story, and is h3.
SECTIONS = ("at a glance", "characters", "summary", "key locations", "encounters", "loot", "notable npcs",
            "plot points", "session highlights", "what we learned", "the reading")
# Sections that hold reference entries rather than story.
RECAP = SECTIONS[3:]


def load_style(path: Path) -> dict:
    """The blog's settings; a missing file means every post as written."""
    style = dict(AS_WRITTEN)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, value in data.items():
            if name not in OPTIONS:
                raise ValueError(f"{path.name}: unknown setting {name!r}; known: {', '.join(OPTIONS)}")
            if value not in OPTIONS[name]:
                raise ValueError(f"{path.name}: {name} must be one of {', '.join(OPTIONS[name])}, not {value!r}")
            style[name] = value
    return style


@dataclass
class Styled:
    html: str
    characters: str = ""  # the post's Characters section as HTML, whether or not it is still shown


def apply(html: str, style: dict) -> Styled:
    if style["headings"] == "real":
        html = outside_quotes(html, real_headings)
    characters = characters_section(html)
    if style["cast"] == "pills":
        html = drop_characters(html)
    if style["glance"] == "none":
        html = drop_glance(html)
    if style["entries"] == "bullets":
        html = on_sections(html, RECAP, bullet_entries)
    if style["bold"] == "plain":
        html = outside_quotes(html, lambda h: on_sections(h, RECAP, plain_story, inside=False))
    if style["links"] == "gold":
        html = gold_links(html)
    if style["picture"] == "top":
        html = picture_first(html)
    return Styled(html, characters)


def outside_quotes(html: str, change) -> str:
    """Run change() on everything but blockquotes: letters, notes and riddles the party found are
    quoted as written, bold lines and all."""
    parts = re.split(r"(<blockquote>.*?</blockquote>)", html, flags=re.S)
    return "".join(p if p.startswith("<blockquote>") else change(p) for p in parts)


def heading_text(inner: str) -> str:
    return wiki.plain_text(inner).rstrip(":").strip()


def is_section(text: str, names=SECTIONS) -> bool:
    return text.lower().startswith(names)


# A paragraph whose first line is all bold and ends in a line break: the 2024-2025 way of writing a heading.
# A bold line alone in its paragraph is a heading too when it ends in a colon ("**What we learned:**").
BOLD_LINE = re.compile(r"<p><strong>(?P<bold>[^<]{1,80})</strong>(?:\s*<br\s*/?>\s*(?P<rest>.*?))?</p>", re.S)


def real_headings(html: str) -> str:
    """Bold first lines become headings and headings lose their colons. Template sections are h2 and
    anything else h3, except a bold name inside a recap section, which is an entry (bullet_entries)."""
    recap = False

    def one(m: re.Match) -> str:
        nonlocal recap
        if m.group("bold") is not None:
            text = heading_text(m.group("bold"))
            if is_section(text):
                level = 2
            elif m.group("rest") is None and not m.group("bold").rstrip().endswith(":"):
                return m.group(0)  # a bold quote on its own, not a heading
            elif recap and m.group("rest") is not None:
                return m.group(0)
            else:
                level = 3
            rest = (m.group("rest") or "").strip()
            out = f"<h{level}>{text}</h{level}>" + (f"\n<p>{rest}</p>" if rest else "")
        else:
            inner = re.sub(r":\s*((?:</strong>)?)\s*$", r"\1", m.group("inner").strip())
            text = heading_text(inner)
            level = 2 if is_section(text) else 3
            out = f"<h{level}>{inner}</h{level}>"
        if level == 2:
            recap = is_section(text, RECAP)
        return out

    return re.sub(rf"{BOLD_LINE.pattern}|<h(?P<lv>[2-4])>(?P<inner>.*?)</h(?P=lv)>", one, html, flags=re.S)


# The Characters section: a heading (or bold line) and the list or paragraph after it.
CHARACTERS = re.compile(r"(?:<h[23]>Characters:?</h[23]>\s*(?:<ul>.*?</ul>|<p>.*?</p>)"
                        r"|<p><strong>Characters:?</strong>\s*<br\s*/?>.*?</p>)\s*", re.S)


def characters_section(html: str) -> str:
    """The Characters section; the build finds who it names with the wiki linker, since older posts
    name the characters without links ("Liren: Dragonborn Barbarian")."""
    m = CHARACTERS.search(html)
    return m.group(0) if m else ""


def drop_characters(html: str) -> str:
    return CHARACTERS.sub("", html, count=1)


def drop_glance(html: str) -> str:
    return re.sub(r"<h[23]>At a Glance:?</h[23]>\s*<ul>.*?</ul>\s*", "", html, count=1, flags=re.S | re.I)


def on_sections(html: str, names, change, inside: bool = True) -> str:
    """Run change() on each stretch of HTML under an h2 whose name is (inside=True) or is not
    (inside=False) one of names; text before the first h2 counts as story."""
    parts = re.split(r"(<h2[^>]*>.*?</h2>)", html, flags=re.S)
    out, current = [], None
    for part in parts:
        if re.match(r"<h2[^>]*>", part):
            current = heading_text(re.sub(r"<h2[^>]*>|</h2>", "", part))
            out.append(part)
            continue
        hit = current is not None and is_section(current, tuple(names))
        out.append(change(part) if hit == inside else part)
    return "".join(out)


def bullet_entries(html: str) -> str:
    """Paragraphs of "**Name**: text" lines become list items; neighbouring lists merge into one."""
    def para(m: re.Match) -> str:
        raw = [ln.strip() for ln in re.split(r"<br\s*/?>", m.group(1))]
        lines = [re.sub(r"^-\s+", "", ln) for ln in raw]
        if all(ln.startswith("- ") for ln in raw):  # a list typed with dashes but no blank line before it
            return "<ul>\n" + "".join(f"<li>{ln}</li>\n" for ln in lines) + "</ul>"
        name = re.fullmatch(r"<strong>([^<]*?):?</strong>", lines[0])
        if name and len(lines) == 2 and not lines[1].startswith("<strong>"):  # name on its own line
            lines = [f"<strong>{name.group(1)}</strong>: {lines[1]}"]
        if not all(ln.startswith("<strong>") for ln in lines):
            return m.group(0)
        return "<ul>\n" + "".join(f"<li>{ln}</li>\n" for ln in lines) + "</ul>"

    html = re.sub(r"<p>(.*?)</p>", para, html, flags=re.S)
    return re.sub(r"</ul>\s*<ul>\n", "", html)


def plain_story(html: str) -> str:
    """Unbold names mid-sentence in story paragraphs; a bold label that starts a paragraph stays."""
    def para(m: re.Match) -> str:
        body = m.group(1)
        lead = re.match(r"\s*<strong>.*?</strong>", body, re.S)
        start = lead.end() if lead else 0
        return "<p>" + body[:start] + re.sub(r"</?strong>", "", body[start:]) + "</p>"

    return re.sub(r"<p>(.*?)</p>", para, html, flags=re.S)


def gold_links(html: str) -> str:
    return re.sub(r'<a href="(/wiki/[^"]*)"', r'<a class="wiki-link" href="\1"', html)


AI_PICTURE = re.compile(r'<p><img [^>]*src="[^"]*-ai(?:-\d+)?\.(?:jpe?g|png|webp)"[^>]*></p>\s*'
                        r'(?:<p><em>AI-generated.*?</em></p>\s*)?', re.S)


def picture_first(html: str) -> str:
    m = AI_PICTURE.search(html)
    if not m:
        return html
    return m.group(0).rstrip() + "\n" + html[:m.start()] + html[m.end():]
