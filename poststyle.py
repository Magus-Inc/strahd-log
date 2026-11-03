"""The look of a session post: how a post in the one post format becomes a page.

Every post file is written one way (AGENTS.md, "One post format"; tests/test_post_format.py checks
it): who was there in the front matter (`cast:`), the story under "## Story" with its "###" scene
headings, then the recap lists. The settings in data/post-style.yaml are only look choices on top of
that (pills or a list, the story's heading, scene headings shown or not, the feature picture...).
They are the template options Tablebard can offer other groups. A post that drifts from the format
is fixed in its file, never with a rule here.

apply() runs on a post's freshly rendered Markdown, before wiki links are added.
"""

from __future__ import annotations

import html as htmllib
import re
from pathlib import Path

import yaml

import wiki

# Setting -> allowed values; the first value of each is the plainest.
OPTIONS = {
    "cast": ["pills+list", "pills", "list"],         # PCs present: pills under the title, a list, or both
    "glance": ["new-posts", "every-post", "none"],   # the "At a Glance" box (every-post is writing, not build)
    "tagline": ["keep", "every-post", "none"],       # the line under the title (every-post is writing)
    "tagline-look": ["plain", "subtitle", "quote", "hand"],  # how the tagline looks under the title
    "card-tagline": ["hide", "above-teaser", "instead"],  # the tagline on chronicle cards
    "picture": ["scene", "top"],                     # the feature picture beside its scene, or first
    "story": ["as-written", "no-heading", "titled"], # "Story" as written, no heading, or one named by story-title
    "scenes": ["as-written", "written"],             # show the "###" scene headings in the story (written) or not
    "slides": ["above-story", "after-story", "end"],  # the slides: above the story, after it, or last
    "relink": ["once", "each-section", "each-heading"],  # link a name's first mention in the post, each h2, or each heading
}
# Settings that take any text rather than one of a list.
TEXT = {"story-title": "Malron’s Account"}  # the parent heading over the story when story is titled
AS_WRITTEN = {**{name: values[0] for name, values in OPTIONS.items()}, **TEXT}

# The recap sections that follow the story; their entries are reference, not story.
RECAP = ("key locations", "encounters", "loot", "notable npcs", "plot points", "session highlights",
         "what we learned", "the reading")

STORY = "<!--story-->"  # where the story starts; the slides go here
STORY_END = "<!--story-end-->"  # where the story stops and the recap lists start
STORY_HEADING = re.compile(r"<h2>Story</h2>\s*")


def load_style(path: Path) -> dict:
    """The blog's settings; a missing file means the plainest look."""
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


def apply(html: str, style: dict) -> str:
    """A post's rendered Markdown, with the look settings applied."""
    style = {**AS_WRITTEN, **style}
    heading = {"titled": style["story-title"], "as-written": "Story"}.get(style["story"])
    m = STORY_HEADING.search(html)
    if m:
        html = html[:m.start()] + STORY + "\n" + html[m.end():]
    else:  # a bare story (a test's tiny post): it starts after any At a Glance box
        glance = re.match(r"\s*<h2>At a Glance</h2>\s*<ul>.*?</ul>\s*", html, re.S)
        at = glance.end() if glance else 0
        html = html[:at] + STORY + "\n" + html[at:]
    if style["glance"] == "none":
        html = drop_glance(html)
    if style["scenes"] != "written":
        start, end = story_span(html)
        html = html[:start] + re.sub(r"<h3[^>]*>.*?</h3>\s*", "", html[start:end], flags=re.S) + html[end:]
    if heading:
        html = html.replace(STORY + "\n", f"{STORY}\n<h2>{htmllib.escape(heading, quote=False)}</h2>\n", 1)
    html = mark_story_end(html)
    html = gold_links(html)
    if style["picture"] == "top":
        html = picture_first(html)
    return html


def story_span(html: str) -> tuple[int, int]:
    """Where the story runs: from its marker to the first recap section."""
    start = html.index(STORY)
    end = len(html)
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", html[start:], re.S):
        if wiki.plain_text(m.group(1)).strip().lower().startswith(RECAP):
            end = start + m.start()
            break
    return start, end


def mark_story_end(html: str) -> str:
    _, end = story_span(html)
    return html[:end] + STORY_END + "\n" + html[end:]


def drop_glance(html: str) -> str:
    return re.sub(r"<h2>At a Glance</h2>\s*<ul>.*?</ul>\s*", "", html, count=1, flags=re.S)


def gold_links(html: str) -> str:
    """A hand-made wiki link looks like the automatic ones."""
    return re.sub(r'<a href="(/wiki/[^"]*)"', r'<a class="wiki-link" href="\1"', html)


AI_PICTURE = re.compile(r'<p><img [^>]*src="[^"]*-ai(?:-\d+)?\.(?:jpe?g|png|webp)"[^>]*></p>\s*'
                        r'(?:<p><em>AI-generated.*?</em></p>\s*)?', re.S)


def picture_first(html: str) -> str:
    m = AI_PICTURE.search(html)
    if not m:
        return html
    return m.group(0).rstrip() + "\n" + html[:m.start()] + html[m.end():]
