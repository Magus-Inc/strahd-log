"""Hidden source lists on wiki pages (Chris, 2026-11-03): ids only, never shown on the site."""
from pathlib import Path

import pytest

import build
import sources
import wiki

WIKI = Path(__file__).resolve().parent.parent / "content" / "wiki"


@pytest.mark.parametrize("entry", ["discord-w4k9rt", "notes-7k2m9q", "transcript-p4x8tw", "recording-000aaa",
                                   "https://curseofstrahdowlbear.obsidianportal.com/adventure-log/tser-pool"])
def test_ids_and_public_links_are_sources(entry):
    assert sources.is_valid_source(entry)


@pytest.mark.parametrize("entry", [
    "C:\\Users\\someone\\Documents\\notes.docx",  # a private path
    "/home/someone/texts/discord.md",
    "https://1drv.ms/w/s!AbCdEf", "https://onedrive.live.com/redir?resid=1",  # private shares
    "https://docs.google.com/document/d/abc", "https://drive.google.com/file/d/abc",
    "https://discord.com/channels/1/2/3", "https://cdn.discordapp.com/attachments/1/2/x.png",
    "Ryan's Discord post, 6/3/2025",  # words about the source are not an id
    "discord-W4K9RT", "discord-w4k9r", "discord-w4k9rtx", "letter-w4k9rt",  # wrong shape or kind
    "http://example.com/page",  # not https
    "file:///C:/notes.md", 7, None])
def test_anything_else_is_refused(entry):
    assert not sources.is_valid_source(entry)


def test_a_wiki_page_with_a_bad_source_does_not_build(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("---\ntitle: X\nsources:\n- D:\\somewhere\\ryan.txt\n---\nText\n", encoding="utf-8")
    with pytest.raises(ValueError, match="x.md: sources:"):
        wiki.parse_wiki_page(path, build.split_front_matter)


def test_a_wiki_page_keeps_its_sources(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("---\ntitle: X\nsources:\n- discord-w4k9rt\n---\nText\n", encoding="utf-8")
    assert wiki.parse_wiki_page(path, build.split_front_matter).sources == ["discord-w4k9rt"]


def test_every_real_wiki_page_has_valid_sources():
    for path in sorted(WIKI.glob("*.md")):
        wiki.parse_wiki_page(path, build.split_front_matter)  # raises on a bad entry


def test_sources_never_show_on_the_site(real_build):
    out = real_build.out
    ids = {s for p in WIKI.glob("*.md") for s in wiki.parse_wiki_page(p, build.split_front_matter).sources}
    assert ids, "the wiki pages from Ryan's texts carry ids"
    texts = [f for f in out.rglob("*") if f.suffix in {".html", ".json", ".xml", ".txt"}]
    leaks = [(f.relative_to(out), i) for f in texts for i in ids if i in f.read_text(encoding="utf-8")]
    assert not leaks, f"source ids shown on the site: {leaks[:5]}"


def test_every_post_has_valid_sources():
    # build.py reads posts' sources once the post format lands; until then this keeps them honest.
    for path in sorted((WIKI.parent / "posts").glob("*.md")):
        meta, _ = build.split_front_matter(path.read_text(encoding="utf-8"))
        sources.parse_sources(meta.get("sources"), path.name)
