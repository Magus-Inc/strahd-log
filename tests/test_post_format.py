"""The one post format (Chris picked it 2026-11-03, the "Blog post format (option C)" doc).

Every post file is written one way, so the build turns it into the page without clean-up rules:
who was there in the front matter (`cast:`), the story under "## Story" with its scene headings
("###"), then the recap lists in a fixed order, one bullet per entry. A post that drifts from the
format fails here and is fixed in the file once; the style engine does not grow a rule for it.
"""
import re
from pathlib import Path

import pytest
import yaml

import build
import poststyle
import wiki

ROOT = Path(build.__file__).parent
POSTS = sorted((ROOT / "content" / "posts").glob("*.md"))
md = build.render_markdown

# The recap sections, in the order they come after the story.
RECAP = ["Key Locations", "Encounters", "Loot", "Notable NPCs", "Plot Points", "Session Highlights"]
# Sections only one session has, kept as the players wrote them: Madam Eva's card reading, and what
# we learned of the castle "not from Doru" (Chris's notes, 2/3/2026).
EXTRA = {"The Reading", "What We Learned (Not from Doru)"}
# Places and people are named entries; encounters and loot may also be plain sentences ("None this time.").
NAMED_ENTRIES = {"Key Locations", "Notable NPCs"}

STYLE = {**poststyle.AS_WRITTEN, "story": "titled", "scenes": "written", "glance": "none", "links": "gold"}
POST = ("## At a Glance\n\n* **Run**: we ran.\n\n## Story\n\n### Into the Fog\n\nWe ran.\n\n"
        "### Out Again\n\nWe hid with [Ireena](/wiki/ireena/).\n\n## Key Locations\n\n* **Fog**: thick.\n")


# --- the look settings on a post in the format -------------------------------------------------

def test_story_heading_becomes_the_story_title_with_its_scenes():
    html = poststyle.apply_format(md(POST), STYLE).html
    assert "<h2>Story</h2>" not in html
    assert f"{poststyle.STORY}\n<h2>Malron’s Account</h2>\n<h3>Into the Fog</h3>" in html
    assert html.index("<h3>Out Again</h3>") < html.index(poststyle.STORY_END) < html.index("<h2>Key Locations</h2>")


def test_scene_headings_can_be_hidden():
    html = poststyle.apply_format(md(POST), {**STYLE, "scenes": "as-written", "story": "titled"}).html
    assert "<h3>" not in html and "We hid" in html


def test_glance_none_hides_the_box_and_gold_links_apply():
    html = poststyle.apply_format(md(POST), STYLE).html
    assert "At a Glance" not in html
    assert '<a class="wiki-link" href="/wiki/ireena/">' in html
    shown = poststyle.apply_format(md(POST), {**STYLE, "glance": "new-posts"}).html
    assert "<h2>At a Glance</h2>" in shown


def test_a_post_without_a_story_heading_is_refused():
    with pytest.raises(ValueError, match="Story"):
        poststyle.apply_format(md("We ran.\n"), STYLE)


# --- the build reads the format ----------------------------------------------------------------

def test_cast_in_the_front_matter_gives_the_pills(tmp_path):
    posts = tmp_path / "content" / "posts"
    posts.mkdir(parents=True)
    (posts / "2024-01-09-first.md").write_text(
        "---\ntitle: First\ndate: '2024-01-09'\ncast: [Crusty]\n---\n\n## Story\n\nWe met Ireena.\n",
        encoding="utf-8")
    wiki_dir = tmp_path / "content" / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "crusty.md").write_text("---\ntitle: Crusty\ntype: character\n---\n", encoding="utf-8")
    (wiki_dir / "ireena.md").write_text("---\ntitle: Ireena\ntype: npc\n---\n", encoding="utf-8")
    site = build.prepare(posts)
    post = site.posts[0]
    assert post.cast_names == ["Crusty"]
    assert [c.slug for c in post.cast] == ["crusty"]  # the pills: the cast, not everyone mentioned
    assert "Story" not in post.html and "We met" in post.html


# --- every post follows the format -------------------------------------------------------------

def parts(path: Path) -> tuple[dict, str]:
    return build.split_front_matter(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", POSTS, ids=lambda p: p.stem)
def test_post_follows_the_format(path):
    meta, body = parts(path)
    problems = []
    for key in ("title", "date", "slug", "cast"):
        if key not in meta:
            problems.append(f"front matter has no {key}")
    if not isinstance(meta.get("cast"), list):
        problems.append("cast is a list of the player characters there")
    heads = re.findall(r"^(#{1,6}) (.*)$", body, re.M)
    names = [text for hashes, text in heads if len(hashes) == 2]
    if any(len(h) not in (2, 3) for h, _ in heads):
        problems.append("only ## sections and ### scene headings")
    if names.count("Story") != 1:
        problems.append('one "## Story" heading')
    else:
        before = names[:names.index("Story")]
        after = names[names.index("Story") + 1:]
        if before not in ([], ["At a Glance"]):
            problems.append(f"before the story only At a Glance, not {before}")
        recap = [n for n in after if n not in EXTRA]
        if recap != [n for n in RECAP if n in recap] or any(n not in RECAP for n in recap):
            problems.append(f"recap sections in the order {RECAP}, not {after}")
    if any(text.endswith(":") for _, text in heads):
        problems.append("no colon after a heading")
    if re.search(r"^\*\*[^*\n]+:\*\*\s*$", body, re.M):  # a bold quote on its own line is fine
        problems.append("a bold line on its own is a heading: write it as ## or ###")
    problems += [f"in {name}: {problem}" for name, problem in section_problems(body)]
    assert problems == []


def sections(body: str) -> dict[str, str]:
    chunks = re.split(r"^## (.*)$", body, flags=re.M)
    return {chunks[i]: chunks[i + 1] for i in range(1, len(chunks), 2)}


def section_problems(body: str):
    for name, text in sections(body).items():
        if name not in RECAP and name not in EXTRA:
            continue
        if "![" in text:
            yield name, "pictures belong in the story"
        for line in text.strip().splitlines():
            if not line.strip() or line.startswith((" ", "\t", "Note: ")):  # sub-lists, margin notes
                continue
            if not line.startswith("* "):
                yield name, f"one bullet per entry: {line[:50]!r}"
            elif name in NAMED_ENTRIES and not line.startswith("* **"):
                yield name, f"an entry starts with its name in bold: {line[:50]!r}"
            elif re.match(r"\* \*\*[^*]+:\*\*", line):
                yield name, f'the colon goes after the bold name ("**Name**: text"): {line[:50]!r}'


def test_cast_names_are_player_character_pages():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    characters = {p.title for p in pages if p.type == "character" and not p.dm}
    unknown = sorted({(p.stem, name) for p in POSTS for name in parts(p)[0].get("cast") or []
                      if name not in characters})
    assert unknown == []


def test_scene_headings_are_short():
    long = [(p.stem, text) for p in POSTS for text in re.findall(r"^### (.*)$", parts(p)[1], re.M)
            if len(text.split()) > 6]
    assert long == []


def test_no_scene_heading_list_outside_the_posts():
    # Scene headings live in the posts now; the old list matched paragraphs by their first words.
    assert not (ROOT / "data" / "scene-headings.yaml").exists()
    assert yaml.safe_load((ROOT / "data" / "post-style.yaml").read_text(encoding="utf-8"))["scenes"] == "written"
