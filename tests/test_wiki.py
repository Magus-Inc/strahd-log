import json
from pathlib import Path

import pytest

import build
import import_op_wiki
import wiki
import wiki_from_extract


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def page(slug: str, title: str, aliases=(), kind="npc", summary="") -> wiki.WikiPage:
    return wiki.WikiPage(slug=slug, title=title, type=kind, aliases=list(aliases), summary=summary)


# --- linking -----------------------------------------------------------------------------------

def test_linker_links_first_mention_only_and_records_all():
    linker = wiki.Linker([page("ireena", "Ireena Kolyana", ["Ireena"]), page("strahd", "Strahd")])
    html, mentioned = linker.link("<p>Ireena Kolyana fears Strahd.</p><p>Ireena runs. Strahd laughs.</p>")
    assert html.count('href="/wiki/ireena/"') == 1 and html.count('href="/wiki/strahd/"') == 1
    assert html.startswith('<p><a class="wiki-link" href="/wiki/ireena/"')
    assert mentioned == {"ireena", "strahd"}


def test_linker_prefers_longest_name_and_whole_words():
    linker = wiki.Linker([page("rose", "Rose"), page("rose-durst", "Rose Durst")])
    html, mentioned = linker.link("<p>Rose Durst and Roses and Rosemary.</p>")
    assert '<a class="wiki-link" href="/wiki/rose-durst/"' in html and "/wiki/rose/" not in html
    assert mentioned == {"rose-durst"}


def test_linker_skips_links_headings_and_self():
    linker = wiki.Linker([page("strahd", "Strahd"), page("ireena", "Ireena")])
    html, mentioned = linker.link(
        '<h2>Strahd</h2><p><a href="/wiki/ireena/">Ireena</a> and <a href="https://x">Strahd</a></p>'
        "<p>Ireena again, Strahd again.</p>", self_slug=None)
    # The heading and the external link are left alone; the first plain mention of Strahd is linked.
    assert "<h2>Strahd</h2>" in html
    assert html.count('href="/wiki/strahd/"') == 1 and "Strahd again" not in html.split("/wiki/strahd/")[0][-40:]
    # Ireena was already linked by hand, so it is not linked a second time.
    assert html.count('href="/wiki/ireena/"') == 1
    assert mentioned == {"strahd", "ireena"}
    own, mentioned = linker.link("<p>Strahd watches.</p>", self_slug="strahd")
    assert own == "<p>Strahd watches.</p>" and mentioned == set()


def test_load_wiki_rejects_shared_names(tmp_path):
    write(tmp_path / "a.md", "---\ntitle: A\naliases: [Same]\n---\n")
    write(tmp_path / "b.md", "---\ntitle: Same\n---\n")
    with pytest.raises(ValueError, match="Same"):
        wiki.load_wiki(tmp_path, build.split_front_matter)


def test_load_wiki_rejects_unknown_type(tmp_path):
    write(tmp_path / "a.md", "---\ntitle: A\ntype: spaceship\n---\n")
    with pytest.raises(ValueError, match="spaceship"):
        wiki.load_wiki(tmp_path, build.split_front_matter)


# --- build -------------------------------------------------------------------------------------

@pytest.fixture
def site(tmp_path):
    posts = tmp_path / "content" / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First Night\ndate: '2024-01-09T21:00:00-06:00'\n---\n\n"
                                         "We met Ireena Kolyana in Barovia.\n")
    write(posts / "2024-02-13-second.md", "---\ntitle: Second\ndate: '2024-02-13T21:00:00-06:00'\n---\n\n"
                                          "Ireena wept. Strahd watched.\n")
    wiki_dir = tmp_path / "content" / "wiki"
    write(wiki_dir / "ireena-kolyana.md", "---\ntitle: Ireena Kolyana\ntype: npc\naliases: [Ireena]\n"
                                          "summary: Adopted sister of Ismark\n---\n\nShe fears Strahd.\n")
    write(wiki_dir / "strahd.md", "---\ntitle: Strahd\ntype: npc\n---\n\nThe vampire.\n")
    write(wiki_dir / "barovia.md", "---\ntitle: Barovia\ntype: place\n---\n")
    return tmp_path


def test_build_writes_wiki_pages_backlinks_and_search(site):
    out = site / "public"
    build.build(site / "content" / "posts", out, site_url="https://log.example", base_path="/strahd-log/")
    first = (out / "posts" / "first" / "index.html").read_text(encoding="utf-8")
    assert '<a class="wiki-link" href="/strahd-log/wiki/ireena-kolyana/"' in first
    assert 'href="/strahd-log/wiki/barovia/"' in first

    ireena = (out / "wiki" / "ireena-kolyana" / "index.html").read_text(encoding="utf-8")
    assert "Appears in" in ireena
    assert ireena.index("posts/second/") < ireena.index("posts/first/")  # newest first
    assert 'href="/strahd-log/wiki/strahd/"' in ireena  # wiki pages link each other too

    index = (out / "wiki" / "index.html").read_text(encoding="utf-8")
    assert "People" in index and "Places" in index and "3 pages" in index

    entries = json.loads((out / "search-index.json").read_text(encoding="utf-8"))
    by_title = {e["t"]: e for e in entries}
    assert by_title["First Night"]["u"] == "posts/first/"
    assert by_title["Ireena Kolyana"]["l"] == "Person" and "Ireena" in by_title["Ireena Kolyana"]["x"]
    search = (out / "search" / "index.html").read_text(encoding="utf-8")
    assert 'var base = "/strahd-log/";' in search


# --- Obsidian Portal wiki import ---------------------------------------------------------------

FOOTER = "\n\n# {t}\n\nCurse of Strahd - owlbear\n\nMinofaustus\n\notoolec\n\n2023-11-18T14:20:08-06:00"


def test_clean_markdown_strips_portal_chrome():
    md = "## Crusty\n\n*High Elf Sage Wizard*\n\n###### Description:\n\nA scholar." + FOOTER.format(t="Crusty")
    assert import_op_wiki.clean_markdown(md, "Crusty") == ("High Elf Sage Wizard", "## Description\n\nA scholar.")
    assert import_op_wiki.clean_markdown("## Klara" + FOOTER.format(t="Klara"), "Klara") == ("", "")


def test_import_pages_relinks_wiki_and_posts(tmp_path):
    site = import_op_wiki.SITE
    export = {
        "/wikis/barovia": {"title": "Barovia", "final": "/wikis/barovia",
                           "md": "## Barovia\n\nSee [Doru](/wikis/doru) and [the log](/wikis/tser-pool)."
                                 + FOOTER.format(t="Barovia")},
        "/wikis/doru": {"title": "Doru", "final": "/wikis/doru", "md": "## Doru\n\nA vampire." + FOOTER.format(t="Doru")},
        "/wikis/tser-pool": {"title": "Tser Pool", "final": "/adventure-log/tser-pool", "md": "a post"},
        "/wikis/notes-july-9-2024": {"title": "Notes - July 9, 2024", "final": "/wikis/notes-july-9-2024",
                                     "md": "raw notes"},
        "/characters/aera": {"title": "Aera shan Ravanór", "final": "/characters/aera",
                             "md": "## Aera shan Ravanór\n\n*Wood-elf Rogue*" + FOOTER.format(t="Aera shan Ravanór")},
    }
    posts = tmp_path / "posts"
    post = write(posts / "2024-01-01-a.md", f"---\ntitle: A\n---\n\n[Aera]({site}/characters/aera) met [Doru]({site}/wikis/doru)."
                                             f" See [my notes]({site}/wikis/notes-july-9-2024).\n\n"
                                             f"Raw Notes: [Notes - July 9, 2024]({site}/wikis/notes-july-9-2024)\n")
    import_op_wiki.import_pages(export, tmp_path / "wiki", posts)

    barovia = (tmp_path / "wiki" / "barovia.md").read_text(encoding="utf-8")
    assert "[Doru](/wiki/doru/)" in barovia and "[the log](/posts/tser-pool/)" in barovia
    aera = build.split_front_matter((tmp_path / "wiki" / "aera-shan-ravanor.md").read_text(encoding="utf-8"))[0]
    assert aera["type"] == "character" and aera["summary"] == "Wood-elf Rogue"
    assert not (tmp_path / "wiki" / "tser-pool.md").exists()
    text = post.read_text(encoding="utf-8")
    assert "[Aera](/wiki/aera-shan-ravanor/) met [Doru](/wiki/doru/). See my notes." in text
    assert "Notes - July 9" not in text  # a line that only pointed at the notes is dropped
    # Raw session notes are not published, and links to them become plain text.
    assert not list((tmp_path / "wiki").glob("notes-*"))


# --- merging extracted entities ----------------------------------------------------------------

def test_wiki_from_extract_keeps_author_text_and_adds_facts(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First Night\n---\n")
    write(posts / "2024-02-13-second.md", "---\ntitle: Second\nslug: second-night\n---\n")
    wiki_dir = tmp_path / "wiki"
    doru = write(wiki_dir / "doru.md", "---\ntitle: Doru\ntype: npc\nsource: Written on Obsidian Portal\n---\n\n"
                                       "My own words about Doru.\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Doru", "type": "npc", "aliases": ["Dorru"], "summary": "Son of the priest.",
         "facts": [{"text": "Locked in the cellar", "post": "2024-02-13-second"}]},
        {"name": "Dorru", "type": "npc", "aliases": [], "summary": "",
         "facts": [{"text": "Turned into a vampire", "post": "2024-01-09-first"}]},
        {"name": "Tser Pool", "type": "place", "aliases": ["the pool", "Abbey"], "summary": "A lake.",
         "facts": [{"text": "Vistani camp here", "post": "2024-01-09-first"}]},
        {"name": "No Facts", "type": "npc", "aliases": [], "summary": "", "facts": []},
    ]))
    assert wiki_from_extract.apply([extract], wiki_dir, posts) == (1, 1)

    meta, body = build.split_front_matter(doru.read_text(encoding="utf-8"))
    assert body.lstrip().startswith("My own words about Doru.")
    assert meta["aliases"] == ["Dorru"] and meta["summary"] == "Son of the priest."
    assert meta["source"] == "Written on Obsidian Portal"
    lines = [l for l in body.splitlines() if l.startswith("* ")]
    assert lines == ["* Turned into a vampire. ([First Night](/posts/first/))",
                     "* Locked in the cellar. ([Second](/posts/second-night/))"]

    pool = build.split_front_matter((wiki_dir / "tser-pool.md").read_text(encoding="utf-8"))[0]
    assert pool["type"] == "place" and pool["source"] == "Compiled from the adventure log"
    assert "aliases" not in pool  # "the pool" is lower case and "Abbey" is too generic
    assert not (wiki_dir / "no-facts.md").exists()

    before = {p.name: p.read_text(encoding="utf-8") for p in wiki_dir.iterdir()}
    wiki_from_extract.apply([extract], wiki_dir, posts)
    assert {p.name: p.read_text(encoding="utf-8") for p in wiki_dir.iterdir()} == before
