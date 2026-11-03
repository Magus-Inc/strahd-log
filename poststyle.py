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


def apply(html: str, style: dict, cast: list[str] | None = None, feature: str = "") -> str:
    """A post's rendered Markdown, with the look settings applied; cast is its `cast:` names."""
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
    if style["cast"] != "pills" and cast:  # a Characters list above the story (link_wiki links the names)
        items = "".join(f"<li>{htmllib.escape(name, quote=False)}</li>\n" for name in cast)
        html = html.replace(STORY, f"<h2>Characters</h2>\n<ul>\n{items}</ul>\n{STORY}", 1)
    html = mark_story_end(html)
    html = gold_links(html)
    if style["picture"] == "top":
        html = picture_first(html, feature)
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


def picture_first(html: str, feature: str = "") -> str:
    """Move the feature picture and its credit to the top: the one `feature` names, else the first."""
    found = list(AI_PICTURE.finditer(html))
    m = next((x for x in found if feature and f'/{feature}"' in x.group(0)), found[0] if found else None)
    if not m:
        return html
    return m.group(0).rstrip() + "\n" + html[:m.start()] + html[m.end():]


# --- pictures in the story (a format rule, not a look setting) --------------------------------

MAX_PICTURES = 3  # Chris (2026-11-03): "a cap of 3 images per article", the feature picture included
MOST_PICTURES = 4  # a post Chris names may say `picture-cap: 4` in its front matter ("show a fourth image")
PICTURE_LINE = re.compile(r"^!\[[^\]]*\]\(([^)\s]+)[^)]*\)\s*$")
CREDIT_LINE = re.compile(r"^\*AI-generated .*\*\s*$")
AI_NAME = re.compile(r"-ai(?:-[a-z0-9]+)?\.(?:jpe?g|png|webp)$", re.I)
ANY_PICTURE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def picture_cap(meta: dict) -> int:
    """How many pictures a post may hold: MAX_PICTURES unless its front matter raises it (at most 4)."""
    cap = int(meta.get("picture-cap", MAX_PICTURES))
    if not MAX_PICTURES <= cap <= MOST_PICTURES:
        raise ValueError(f"picture-cap must be {MAX_PICTURES} to {MOST_PICTURES}, not {cap}")
    return cap


def picture_problems(body: str, cap: int = MAX_PICTURES) -> list[str]:
    """What breaks the picture rules in a post's Markdown body: at most `cap` pictures, each on a
    line of its own inside "## Story" with words between it and the next (two in a row read as a
    gallery and break the scene), none twice, and an AI picture over its "AI-generated ..." credit line."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    problems = []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    seen: set[str] = set()
    words_since_picture = True
    section = None
    for i, block in enumerate(blocks):
        if block.startswith("## "):
            section = block[3:].strip()
        m = PICTURE_LINE.match(block)
        if not m:
            if "![" in block:
                problems.append("a picture shares its paragraph with other text: give it a line of its own")
            elif not CREDIT_LINE.match(block) and not block.startswith("#"):
                words_since_picture = True
            continue
        name = m.group(1).rsplit("/", 1)[-1]
        if section != "Story":
            problems.append(f"{name} is outside the story")
        if name in seen:
            problems.append(f"{name} is shown twice")
        elif not words_since_picture:
            problems.append(f"{name} comes right after another picture: put a paragraph between them")
        seen.add(name)
        words_since_picture = False
        if AI_NAME.search(name) and not (i + 1 < len(blocks) and CREDIT_LINE.match(blocks[i + 1])):
            problems.append(f"{name} has no AI-generated credit line under it")
    count = len(ANY_PICTURE.findall(body))  # a picture inside a paragraph counts too
    if count > cap:
        problems.append(f"{count} pictures: a post holds at most {cap}")
    return problems


def feature_problems(meta: dict, body: str) -> list[str]:
    """A post with more than one picture names its feature picture (`feature: name.jpg`), which gives
    its link preview and goes first under `picture: top`; it must be one of the post's pictures."""
    names = [src.rsplit("/", 1)[-1] for src in ANY_PICTURE.findall(re.sub(r"<!--.*?-->", "", body, flags=re.S))]
    feature = meta.get("feature")
    if feature:
        return [] if feature in names else [f"feature {feature} is not a picture in the post"]
    return ["more than one picture: name the feature picture (feature: name.jpg)"] if len(names) > 1 else []
