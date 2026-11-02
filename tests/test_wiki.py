import re
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
    assert '<a class="wiki-link" href="/wiki/strahd/" title="Strahd">Strahd</a> again' in html
    assert html.count('href="/wiki/strahd/"') == 1
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


# --- regressions from the review of PR #1 --------------------------------------------------------

def test_linker_matches_names_with_apostrophes_and_ampersands():
    linker = wiki.Linker([page("mansion", "Baron's Mansion"), page("tower", "Kazan’s Tower"),
                          page("inn", "Blood & Vine")])
    html = build.render_markdown("We hid in the Baron's Mansion, then Kazan's Tower, then the Blood & Vine.")
    linked, mentioned = linker.link(html)
    assert mentioned == {"mansion", "tower", "inn"}
    assert linked.count('class="wiki-link"') == 3


def test_linker_leaves_quoted_attributes_alone():
    linker = wiki.Linker([page("strahd", "Strahd")])
    html, _ = linker.link('<span title="a > Strahd">hi</span> Strahd')
    assert html == '<span title="a > Strahd">hi</span> <a class="wiki-link" href="/wiki/strahd/" title="Strahd">Strahd</a>'


def test_load_wiki_rejects_duplicate_slugs(tmp_path):
    write(tmp_path / "a.md", "---\ntitle: A\nslug: same\n---\n")
    write(tmp_path / "b.md", "---\ntitle: B\nslug: same\n---\n")
    with pytest.raises(ValueError, match="duplicate wiki slugs"):
        wiki.load_wiki(tmp_path, build.split_front_matter)


def test_wiki_from_extract_adds_up_groups_that_land_on_one_page(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First\n---\n")
    wiki_dir = tmp_path / "wiki"
    page_file = write(wiki_dir / "ismark.md", "---\ntitle: Ismark Kolyanovich\naliases: [Ismark, Ismark the Lesser]\n---\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Ismark", "type": "npc", "facts": [{"text": "Fought wolves", "post": "2024-01-09-first"},
                                                     {"text": "Buried his father", "post": "2024-01-09-first"}]},
        {"name": "Ismark the Lesser", "type": "npc", "facts": [{"text": "Mocked by villagers", "post": "2024-01-09-first"}]},
    ]))
    assert wiki_from_extract.apply([extract], wiki_dir, posts) == (1, 0)
    assert page_file.read_text(encoding="utf-8").count("\n* ") == 3


def test_wiki_from_extract_leaves_hand_written_front_matter_alone(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First\n---\n")
    front = "---\n# my note\ntitle: Doru\ntype: npc\nsummary: Son of the priest\n---\n"
    page_file = write(tmp_path / "wiki" / "doru.md", front + "\nMine.\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Doru", "type": "npc", "summary": "Other", "facts": [{"text": "A vampire", "post": "2024-01-09-first"}]}]))
    wiki_from_extract.apply([extract], tmp_path / "wiki", posts)
    text = page_file.read_text(encoding="utf-8")
    assert text.startswith(front + "\nMine.\n") and "Compiled from the adventure log" not in text.split("<!--")[0]


def test_wiki_from_extract_skips_generic_titles(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First\n---\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Abbot", "type": "npc", "facts": [{"text": "Builds things", "post": "2024-01-09-first"}]}]))
    assert wiki_from_extract.apply([extract], tmp_path / "wiki", posts) == (0, 0)


def test_import_keeps_aliases_added_later_and_post_text_near_skipped_links(tmp_path):
    site = import_op_wiki.SITE
    export = {"/wikis/doru": {"title": "Doru", "final": "/wikis/doru", "md": "## Doru\n\nA vampire." + FOOTER.format(t="Doru")},
              "/wikis/notes-july-9": {"title": "Notes", "final": "/wikis/notes-july-9", "md": "x"}}
    wiki_dir = tmp_path / "wiki"
    write(wiki_dir / "doru.md", "---\ntitle: Doru\ntype: npc\naliases: [Dorru]\nsummary: Son of the priest\n"
                                "player: Grant\nformer: true\n---\n\nold\n")
    post = write(tmp_path / "posts" / "2024-01-01-a.md",
                 f"---\ntitle: A\n---\n\nThe party agreed on this:\n\n[Notes]({site}/wikis/notes-july-9) are where Crusty kept the map.\n")
    import_op_wiki.import_pages(export, wiki_dir, tmp_path / "posts")
    meta = build.split_front_matter((wiki_dir / "doru.md").read_text(encoding="utf-8"))[0]
    assert meta["aliases"] == ["Dorru"] and meta["summary"] == "Son of the priest"
    assert meta["player"] == "Grant" and meta["former"] is True
    assert "The party agreed on this:\n\nNotes are where Crusty kept the map." in post.read_text(encoding="utf-8")


def test_notable_npcs_that_lacked_pages_now_have_them():
    """Chris wants every name in a post's Notable NPCs to lead to a wiki page."""
    pages = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
    linker = wiki.Linker(pages)
    for name, slug in [("Pidlwick", "pidlwick"), ("Masked Servant", "masked-servant"), ("Druids", "forest-folk"),
                       ("Vallakovich", "baron-of-vallaki")]:
        assert linker.by_name[wiki.fold(name)].slug == slug


def test_corrections_merge_fix_move_and_retype(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First\n---\n")
    wiki_dir = tmp_path / "wiki"
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Blinsky", "type": "npc", "aliases": ["Toy Shop"], "summary": "A toymaker.",
         "facts": [{"text": "Sells toys", "post": "2024-01-09-first"}]},
        {"name": "Blinksy", "type": "npc", "facts": [{"text": "Store burned", "post": "2024-01-09-first"}]},
        {"name": "Bianca", "type": "npc", "facts": [{"text": "Franz's sister", "post": "2024-01-09-first"},
                                                    {"text": "A werewolf named Bianca", "post": "2024-01-09-first"}]},
        {"name": "Zollst", "type": "creature", "facts": [{"text": "Wrong fact", "post": "2024-01-09-first"},
                                                         {"text": "A trapper", "post": "2024-01-09-first"}]},
    ]))
    fixes = {"same": [["Blinsky", "Blinksy"]], "not_alias": ["Toy Shop"],
             "facts": {"Wrong fact": None, "Sells toys": "Makes and sells toys"},
             "move_facts": {"A werewolf named Bianca": "Bianca (werewolf)"},
             "types": {"Zollst": "npc"}, "summaries": {"Bianca (werewolf)": "A werewolf."}}
    # A stale compiled page from an earlier run is removed; a hand-written one is kept.
    write(wiki_dir / "blinksy.md", "---\ntitle: Blinksy\nsource: Compiled from the adventure log\n---\n")
    write(wiki_dir / "mine.md", "---\ntitle: Mine\n---\n")
    wiki_from_extract.apply([extract], wiki_dir, posts, fixes)

    assert sorted(p.name for p in wiki_dir.iterdir()) == ["bianca-werewolf.md", "bianca.md", "blinsky.md", "mine.md", "zollst.md"]
    blinsky_meta, blinsky = build.split_front_matter((wiki_dir / "blinsky.md").read_text(encoding="utf-8"))
    assert blinsky_meta["aliases"] == ["Blinksy"]
    assert "Makes and sells toys." in blinsky and "Store burned." in blinsky
    assert "werewolf" not in (wiki_dir / "bianca.md").read_text(encoding="utf-8")
    werewolf = build.split_front_matter((wiki_dir / "bianca-werewolf.md").read_text(encoding="utf-8"))[0]
    assert werewolf["summary"] == "A werewolf." and werewolf["title"] == "Bianca (werewolf)"
    zollst_meta, zollst = build.split_front_matter((wiki_dir / "zollst.md").read_text(encoding="utf-8"))
    assert zollst_meta["type"] == "npc" and "Wrong fact" not in zollst


def test_corrections_set_player_and_former_pc(tmp_path):
    posts = tmp_path / "posts"
    write(posts / "2024-01-09-first.md", "---\ntitle: First\n---\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Zorpheus", "type": "character", "facts": [{"text": "A fate bard", "post": "2024-01-09-first"}]}]))
    wiki_from_extract.apply([extract], tmp_path / "wiki", posts,
                            {"players": {"Zorpheus": "Grant Haseloff"}, "former": ["Zorpheus"]})
    meta = build.split_front_matter((tmp_path / "wiki" / "zorpheus.md").read_text(encoding="utf-8"))[0]
    assert meta["player"] == "Grant Haseloff" and meta["former"] is True
    page = wiki.parse_wiki_page(tmp_path / "wiki" / "zorpheus.md", build.split_front_matter)
    assert page.former and page.player == "Grant Haseloff"


def test_facts_citing_a_folded_post_cite_the_merged_one(tmp_path):
    posts = tmp_path / "content" / "posts"
    write(posts / "2026-02-03-welcome.md", "---\ntitle: Welcome Back\n---\n")
    write(tmp_path / "data" / "redirects.yaml", "posts:\n  2026-02-03-notebook: 2026-02-03-welcome\n")
    extract = write(tmp_path / "x.json", json.dumps([
        {"name": "Doru", "type": "npc", "facts": [{"text": "His intelligence maps the castle", "post": "2026-02-03-notebook"}]}]))
    wiki_from_extract.apply([extract], tmp_path / "wiki", posts)
    assert "([Welcome Back](/posts/welcome/))" in (tmp_path / "wiki" / "doru.md").read_text(encoding="utf-8")


def test_players_real_names_stay_on_their_pc_pages():
    # Chris: real player names appear only on the PC wiki pages, never in a session post.
    root = Path(__file__).resolve().parent.parent
    pages = wiki.load_wiki(root / "content" / "wiki", build.split_front_matter)
    names = {part for p in pages if p.player for part in [p.player, *p.player.split()] if len(part) > 3}
    for post in (root / "content" / "posts").glob("*.md"):
        text = post.read_text(encoding="utf-8")
        found = sorted(n for n in names if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text))
        assert not found, f"{post.name} names players: {found}"


def test_narrator_appears_in_every_session():
    """Malron writes the journal, so he was at every session even when a post never names him."""
    posts = build.load_posts(build.ROOT / "content" / "posts")
    pages = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
    build.link_wiki(posts, pages)
    malron = next(p for p in pages if p.slug == "malron-lichtstrahl")
    assert malron.narrator
    assert len(malron.mentioned_in) == len(posts)
    assert all("malron-lichtstrahl" in p.mentions for p in posts)


def test_notable_npcs_link_every_name_even_after_an_earlier_mention():
    linker = wiki.Linker([page("kasimir", "Kasimir Velikov", ["Kasimir"]), page("argynvost", "Argynvost"),
                          page("sasha", "Sasha Ivliskova", ["Sasha"]), page("fiona", "Lady Fiona Wachter")])
    html = build.render_markdown(
        "## Summary:\n\nArgynvost rises. Kasimir is named.\n\n### Notable NPCs:\n\n"
        "**Argynvost**: The silver dragon. He blesses a sword.\n\n"
        "**Sir Godfried**: He tells us of Kasimir.\n\n"
        "**Kasimir Velikov** (mentioned): A dusk elf.\n\n"
        "**Sasha, Kavan and Lady Fiona Wachter** (glimpsed): Touched by the light.\n\n"
        "### Plot Points:\n\nArgynvost again.\n")
    html, mentioned = linker.link(html)
    html = wiki.link_npc_names(html, linker)
    section = html[html.index("Notable NPCs"):html.index("Plot Points")]
    # Each bold name in the section links to its page, though the summary linked it first.
    assert '<strong><a class="wiki-link" href="/wiki/argynvost/"' in section
    assert '<a class="wiki-link" href="/wiki/kasimir/" title="Kasimir Velikov">Kasimir Velikov</a>' in section
    assert 'href="/wiki/sasha/"' in section and 'href="/wiki/fiona/"' in section
    # Names without a page stay plain, and descriptions are not linked a second time.
    assert "<strong>Sir Godfried</strong>" in section and "of Kasimir." in section
    # Other sections keep first-mention-only linking.
    assert html.count('href="/wiki/argynvost/"') == 2
    assert {"kasimir", "argynvost", "sasha", "fiona"} <= mentioned


def test_notable_npcs_written_as_a_bold_line_link_too():
    # Five older posts start the section with a bold "Notable NPCs:" line instead of a heading.
    linker = wiki.Linker([page("urwin", "Urwin"), page("lucien", "Father Lucien")])
    html = build.render_markdown(
        "Urwin pours. Father Lucien prays.\n\n**Notable NPCs:**  \n- **Father Lucien:** Preparing the blessing.  \n"
        "- **Urwin:** Innkeeper.\n\n**Plot Points:**  \n- **Urwin:** Pours again.\n")
    html, _ = linker.link(html)
    html = wiki.link_npc_names(html, linker)
    section = html[html.index("Notable NPCs"):html.index("Plot Points")]
    assert 'href="/wiki/lucien/"' in section and 'href="/wiki/urwin/"' in section
    # The section ends at the next bold "Something:" line.
    assert "<strong>Urwin:</strong> Pours again." in html


def test_entry_names_in_every_reference_list_link():
    """Chris (2026-11-02): one linking rule. The first mention in the story links, and so does the bold
    name of every entry in Key Locations, Encounters, Loot and Notable NPCs, where readers look things up."""
    linker = wiki.Linker([page("fiona", "Lady Fiona Wachter", ["Lady Fiona"]), page("estate", "Wachter Estate"),
                          page("mirror", "Mirror of Victor")])
    html = build.render_markdown(
        "## Summary:\n\nLady Fiona helps at the Wachter Estate with the Mirror of Victor.\n\n"
        "## Key Locations:\n\n* **Wachter Estate**: A manor.\n\n## Encounters:\n\n* **Lady Fiona**: We talked.\n\n"
        "## Loot:\n\n* **Mirror of Victor**: A mirror.\n\n## Plot Points:\n\n* **Lady Fiona** is kind.\n")
    html, _ = linker.link(html)
    html = wiki.link_npc_names(html, linker)
    for section, slug in (("Key Locations", "estate"), ("Encounters", "fiona"), ("Loot", "mirror")):
        part = html[html.index(section):]
        assert f'<strong><a class="wiki-link" href="/wiki/{slug}/"' in part.split("<h2")[0], section
    assert "<strong>Lady Fiona</strong> is kind." in html  # Plot Points are sentences, not entries


def test_pages_in_five_or_more_sessions_have_a_picture():
    """Chris (2026-10-31): anyone or anything in 5+ sessions gets a picture on its wiki page."""
    posts = build.load_posts(build.ROOT / "content" / "posts")
    pages = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
    build.link_wiki(posts, pages)
    missing = sorted(p.slug for p in pages if len(p.mentioned_in) >= 5 and not p.pictures and not p.narrator)
    assert not missing, f"add a picture to: {missing}"


def test_every_player_character_has_a_picture():
    """Chris (2026-11-01): every PC, current or former, has a picture on its wiki page."""
    pages = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
    missing = sorted(p.slug for p in pages if p.type == "character" and not p.pictures)
    assert not missing, f"add a picture to: {missing}"


# --- session citations -------------------------------------------------------------------------

def mark(slug, title):
    return f"[{slug}]"


def test_session_citations_become_markers_that_hug_the_word():
    html = '<p>We met him (<a href="/posts/a/">Night A</a>). Then left.</p>'
    out, cited = wiki.cite_sessions(html, mark)
    assert out == "<p>We met him[a]. Then left.</p>"
    assert cited == ["a"]


def test_several_sessions_in_one_bracket_each_get_a_marker():
    html = ('<li>Fought. (<a href="/posts/a/">A</a>, <a href="/posts/b/">The B, part 2</a>; '
            '<a href="/posts/a/">A</a>)</li>')
    out, cited = wiki.cite_sessions(html, lambda s, t: f"<{s}>", sep="|")
    assert out == "<li>Fought.<a>|<b>|<a></li>"
    assert cited == ["a", "b"]


def test_brackets_with_other_words_or_wiki_links_are_left_alone():
    html = ('<p>Old (see <a href="/posts/a/">A</a>) and (<a href="/wiki/x/">X</a>) '
            'and <a href="/posts/b/">B</a> in running text.</p>')
    out, cited = wiki.cite_sessions(html, mark)
    assert out == html and cited == []


def test_citation_titles_with_markup_entities_still_match():
    html = '<p>It spoke (<a href="/posts/s/">The Shard&rsquo;s Warning &amp; Madness</a>).</p>'
    out, cited = wiki.cite_sessions(html, lambda s, t: f"[{t}]")
    assert out == "<p>It spoke[The Shard’s Warning & Madness].</p>"


def test_wiki_pages_cite_sessions_by_number_and_number_the_appears_in_list(site):
    write(site / "content" / "posts" / "2024-03-05-third.md",
          "---\ntitle: The Third Night\ndate: '2024-03-05T21:00:00-06:00'\n---\n\nNothing named here.\n")
    write(site / "content" / "wiki" / "strahd.md",
          "---\ntitle: Strahd\ntype: npc\n---\n\nThe vampire watched us ([Second](/posts/second/)) and spoke "
          "([First Night](/posts/first/), [The Third Night](/posts/third/)).\n\n"
          "* Seen at the gates. ([Second](/posts/second/))\n")
    out = site / "public"
    build.build(site / "content" / "posts", out, site_url="https://log.example", base_path="/strahd-log/")
    strahd = (out / "wiki" / "strahd" / "index.html").read_text(encoding="utf-8")
    prose = strahd.split('<div class="prose">', 1)[1].split("</div>", 1)[0]
    # Sessions are numbered in date order: First 1, Second 2, Third 3. The number opens the post.
    assert ('watched us&#8288;<a class="cite" href="/strahd-log/posts/second/" title="Session 2: Second" '
            'aria-label="Session 2: Second">2</a> and') in prose
    assert 'spoke&#8288;<a class="cite" href="/strahd-log/posts/first/"' in prose and ">1</a>&#8288;<a class=\"cite\"" in prose
    assert "Seen at the gates.&#8288;<a class=\"cite\"" in prose
    assert "(" not in prose and "The Third Night" not in prose.replace('title="Session 3: The Third Night"', "").replace(
        'aria-label="Session 3: The Third Night"', "")
    # The Appears-in list carries the same numbers, and takes in a session cited but never named.
    appears = strahd.split('class="appears-in"', 1)[1]
    assert "Appears in 3 sessions" in appears
    assert '<span class="num">3</span><a href="/strahd-log/posts/third/">' in appears
    assert '<span class="num">1</span><a href="/strahd-log/posts/first/">' in appears
    # The search index keeps the readable titles, not bare numbers.
    entries = {e["t"]: e for e in json.loads((out / "search-index.json").read_text(encoding="utf-8"))}
    assert "watched us (Second)" in entries["Strahd"]["x"]


def test_wiki_links_are_gold_and_citations_are_red_dots():
    css = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    link = re.search(r"\.prose a\.wiki-link \{([^}]*)\}", css).group(1)
    assert "var(--gold)" in link and "dotted" not in link
    cite = re.search(r"\.prose a\.cite \{([^}]*)\}", css)
    assert cite and "border-radius" in cite.group(1)


def test_a_date_after_the_session_link_stays_in_brackets():
    html = '<p>She died at the gallows (<a href="/posts/a/">A</a>, February 2025). Later.</p>'
    out, cited = wiki.cite_sessions(html, mark)
    assert out == "<p>She died at the gallows[a] (February 2025). Later.</p>" and cited == ["a"]


def test_hall_of_bones_picture_shows_the_skull_doors_and_bone_table():
    # Chris, 2026-11-02: the picture needs Argynvost's skull over the steel-banded double doors in
    # the side wall and the long bone table with its bone chairs (Ryan read both out on 17 Feb 2026).
    text = (build.ROOT / "content" / "wiki" / "hall-of-bones.md").read_text(encoding="utf-8")
    alt = re.search(r"!\[([^\]]*)\]\(/images/hall-of-bones-ai\.jpg\)", text).group(1).lower()
    for words in ("skull", "double doors", "table", "chairs"):
        assert words in alt, words
