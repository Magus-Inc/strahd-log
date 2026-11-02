"""The early posts (Session Zero, Nov 2023, through Finding Arabelle, Oct 2024) were story only.
Chris (2026-11-02) asked for the same recap lists as later posts, drawn only from each post's own story."""
import re
from pathlib import Path

import pytest

import build
import wiki

ROOT = Path(build.__file__).parent
POSTS = sorted((ROOT / "content" / "posts").glob("*.md"))
EARLY = [p for p in POSTS if p.name < "2024-11-01"]
RECAP = ["Key Locations", "Encounters", "Loot", "Notable NPCs", "Plot Points", "Session Highlights"]


@pytest.fixture(scope="module")
def linker():
    return wiki.Linker(wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter))


def sections(path: Path) -> tuple[str, dict[str, str]]:
    """The story (everything above the first recap heading) and each recap section's Markdown."""
    body = build.parse_post(path).body_md
    parts = re.split(r"^## (" + "|".join(RECAP) + r"):?[ \t]*$", body, flags=re.M)
    return parts[0], dict(zip(parts[1::2], parts[2::2]))


def in_story(story: str, linker) -> set[str]:
    """Wiki pages the story mentions: linked, or named in any case ("the skeletal rider")."""
    _, slugs = linker.link(build.render_markdown(story))
    text = wiki.fold(story).lower()
    return slugs | {page.slug for name, page in linker.by_name.items()
                    if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", text)}


# People the story describes but never names, so there is no wiki page to link.
UNNAMED = {"A boy and a girl"}


def entries(text: str) -> list[str]:
    """The bold name at the start of each bullet."""
    return re.findall(r"^\* \*\*(.+?)\*\*", text, flags=re.M)


def test_eighteen_early_posts():
    assert len(EARLY) == 18
    assert EARLY[0].name.startswith("2023-11-07-session-zero") and EARLY[-1].name.startswith("2024-10-29-finding-arabelle")


@pytest.mark.parametrize("path", EARLY, ids=lambda p: p.stem)
def test_early_post_has_every_recap_list_in_order(path):
    story, recap = sections(path)
    assert list(recap) == RECAP, f"{path.name}: needs ## {', ## '.join(RECAP)} after the story"
    assert len(story.split()) > 100
    for name, text in recap.items():
        bullets = [ln for ln in text.splitlines() if ln.startswith("* ")]
        assert bullets, f"{path.name}: {name} is empty"
        assert all(ln.strip() == "" or ln.startswith(("* ", "    * ")) for ln in text.splitlines()), \
            f"{path.name}: every line of {name} is a bullet"
        if name != "Session Highlights":
            assert len(entries(text)) == len(bullets), f"{path.name}: every {name} bullet starts with a bold name"


@pytest.mark.parametrize("path", EARLY, ids=lambda p: p.stem)
def test_notable_npcs_are_linked_and_from_the_story(path, linker):
    """Notable NPCs entries always link to the wiki, and the lists add no new people: everyone named
    there is in the post's own story."""
    story, recap = sections(path)
    mentioned = in_story(story, linker)
    for name in entries(recap["Notable NPCs"]):
        if name in UNNAMED:
            continue
        m = linker.pattern.search(name)
        assert m, f"{path.name}: Notable NPC {name!r} has no wiki page to link to"
        slug = linker.by_name[wiki.fold(m.group(1))].slug
        assert slug in mentioned, f"{path.name}: {name!r} is not in this post's story"


@pytest.mark.parametrize("path", EARLY, ids=lambda p: p.stem)
def test_recap_names_only_wiki_pages_from_the_story(path, linker):
    """Every wiki name the lists mention is a page the story already mentions (no new events)."""
    story, recap = sections(path)
    mentioned = in_story(story, linker)
    _, in_recap = linker.link(build.render_markdown("\n".join(recap.values())))
    extra = in_recap - mentioned
    assert not extra, f"{path.name}: the lists name {sorted(extra)}, which the story never mentions"


@pytest.mark.parametrize("path", EARLY, ids=lambda p: p.stem)
def test_recap_has_no_player_names_or_dice(path):
    _, recap = sections(path)
    text = "\n".join(recap.values())
    assert not re.search(r"\b\d+d\d+\b|\bDC \d+|\broll(ed|s)?\b|\bthe DM\b", text), f"{path.name}: no dice talk"
