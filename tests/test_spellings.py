"""Names are spelled as the Curse of Strahd book spells them (data/spellings.yaml)."""
import json
import re
from pathlib import Path

import pytest
import yaml

import build
import fix_spellings
import wiki

ROOT = Path(build.__file__).parent
SPELLINGS = fix_spellings.load_spellings(ROOT / "data" / "spellings.yaml")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- the tool ------------------------------------------------------------------------------------

def test_fix_text_replaces_whole_words_longest_first():
    spellings = {"Davien": "Davian", "Davien Warningkoff": "Davian Martikov", "Kaven": "Kavan"}
    text, counts = fix_spellings.fix_text("Davien Warningkoff and Davien met Kaven's kin, not Kavenly.", spellings)
    assert text == "Davian Martikov and Davian met Kavan's kin, not Kavenly."
    assert counts == {"Davien Warningkoff": 1, "Davien": 1, "Kaven": 1}



def test_player_characters_are_spelled_like_their_wiki_pages():
    """Chris, 2026-11-02: the 13 Aug 2024 post called Shabasta "Shivasta", and Crusty was "Krusty"."""
    spellings = SPELLINGS
    for wrong, right in (("Shivasta", "Shabasta"), ("Krusty", "Crusty"), ("Marlon", "Malron"), ("Schloptk", "Schlopkht")):
        assert spellings[wrong] == right
    doll = (ROOT / "content" / "posts" / "2024-08-13-a-doll-for-arabelle.md").read_text(encoding="utf-8")
    assert "Shabasta the Great" in doll and "Shivasta" not in doll

def test_fix_text_leaves_links_and_urls_alone():
    spellings = {"Kaven": "Kavan"}
    text, _ = fix_spellings.fix_text(
        "[Kaven](/wiki/Kaven-x/) at https://example.com/Kaven and Kaven.\n", spellings)
    assert text == "[Kavan](/wiki/Kaven-x/) at https://example.com/Kaven and Kavan.\n"


def test_fix_text_is_case_sensitive():
    # "cloven hooves" is a word; "Cloven" is Clovin Belview misheard.
    text, _ = fix_spellings.fix_text("Cloven has cloven hooves.", {"Cloven": "Clovin"})
    assert text == "Clovin has cloven hooves."


def test_fixing_a_wiki_page_drops_aliases_that_now_repeat():
    page = ("---\ntitle: Emil Toranescu\ntype: npc\naliases:\n- Emil Tornescu\n- Emil Terescu\n- Emil\n"
            "summary: Werewolf.\n---\n\nEmil Terescu waits.\n")
    text, _ = fix_spellings.fix_text(page, {"Tornescu": "Toranescu", "Terescu": "Toranescu"})
    text = fix_spellings.tidy_aliases(text)
    meta = yaml.safe_load(text.split("---")[1])
    assert meta["aliases"] == ["Emil"]
    assert text.endswith("Emil Toranescu waits.\n")


def test_check_lists_each_misspelling_with_its_file(tmp_path):
    write(tmp_path / "posts" / "a.md", "---\ntitle: A\n---\n\nWe met Davien.\n")
    write(tmp_path / "posts" / "b.md", "---\ntitle: B\n---\n\nWe met Davian.\n")
    found = fix_spellings.check([tmp_path / "posts"], {"Davien": "Davian"})
    assert found == [("a.md", "Davien", "Davian")]


def test_main_fixes_files_in_place(tmp_path):
    post = write(tmp_path / "posts" / "a.md", "---\ntitle: A\n---\n\nWe met Davien.\n")
    extract = write(tmp_path / "x.json", json.dumps([{"name": "Davien", "facts": []}]))
    spellings = write(tmp_path / "s.yaml", "fix:\n  Davien: Davian\n")
    assert fix_spellings.main(["--spellings", str(spellings), str(tmp_path / "posts"), str(extract)]) == 0
    assert "We met Davian." in post.read_text(encoding="utf-8")
    assert json.loads(extract.read_text(encoding="utf-8"))[0]["name"] == "Davian"
    assert fix_spellings.main(["--check", "--spellings", str(spellings), str(tmp_path / "posts")]) == 0


# --- the spelling list --------------------------------------------------------------------------

def test_spellings_have_no_chains():
    """A right spelling is never itself listed as wrong, so one pass fixes everything."""
    assert not {right for right in SPELLINGS.values()} & set(SPELLINGS)


@pytest.mark.parametrize("wrong,right", [
    ("Emil Terescu", "Emil Toranescu"), ("Emil Tornescu", "Emil Toranescu"), ("Anastrasia", "Anastrasya"),
    ("Ludmila", "Ludmilla"), ("Baba Lasaga", "Baba Lysaga"), ("Kiril Vonstrranovich", "Kiril Stoyanovich"),
    ("Davien Martikov", "Davian Martikov"), ("Father Lucien", "Father Lucian"), ("Hornguard", "Horngaard"),
    ("Sir Godfried William", "Sir Godfrey Gwilym"), ("Kazan", "Khazan"), ("Mordakainen", "Mordenkainen"),
    # Places too, at Chris's word (2026-10-31).
    ("Welcome to Vellaki", "Welcome to Vallaki"), ("Wachter Haus", "Wachterhaus"), ("St. Markova Abbey", "St. Markovia Abbey"),
    # Misheard names whose wiki link was right but whose words were not (Chris, 2026-11-02).
    ("Near the Sarepool crossroads", "Near the Tser Pool crossroads"), ("Test Pool", "Tser Pool"),
    ("Velaki", "Vallaki"), ("Forest Fand", "Forest Fane"), ("the Bluewater Inn", "the Blue Water Inn"),
    ("St. Andrals Church", "St. Andral's Church"), ("Ric Tavio", "Rictavio"),
    ("Holy Symbol of Raven Kind", "Holy Symbol of Ravenkind"), ("Anna Krezkov", "Anna Krezkova"),
    ("a Vistano", "a Vistana"), ("a priest of Latander", "a priest of Lathander"),
])
def test_book_spellings(wrong, right):
    assert fix_spellings.fix_text(wrong, SPELLINGS)[0] == right


def test_near_misses_finds_an_alias_spelled_almost_like_its_page():
    """Chris, 2026-11-02: "Sarepool crossroads" linked to the Tser Pool Crossroads page, so the link
    was right and the words were wrong. An alias a letter or two off its page's name is a misspelling."""
    pages = {
        "tser-crossroads": ["Tser Pool Crossroads", "Sarepool crossroads"],
        "vallaki": ["Vallaki", "Velaki"],
        "anna-krezkova": ["Anna Krezkova", "Anna", "Anna Krezkov"],
        "chest-of-holding": ["Chest of Holding", "Chest of Holden"],
        "sarepool": ["Tser Pool Crossroads", "Sarepool"],
        "lady-fiona-wachter": ["Lady Fiona Wachter", "Fiona Watcher"],
        "blue-water-inn": ["Blue Water Inn", "Bluewater Inn"],
        "van-richten": ["Van Richten", "Rictavio", "Ric Tavio"],
    }
    found = fix_spellings.near_misses(pages, keep={"Chest of Holden"})
    assert found == [("anna-krezkova", "Anna Krezkov", "Anna Krezkova"),
                     ("blue-water-inn", "Bluewater Inn", "Blue Water Inn"),
                     ("lady-fiona-wachter", "Fiona Watcher", "Lady Fiona Wachter"),
                     ("sarepool", "Sarepool", "Tser Pool Crossroads"),
                     ("tser-crossroads", "Sarepool crossroads", "Tser Pool Crossroads"),
                     ("vallaki", "Velaki", "Vallaki"),
                     ("van-richten", "Ric Tavio", "Rictavio"), ("van-richten", "Rictavio", "Ric Tavio")]


@pytest.mark.parametrize("names", [
    ["Lady Fiona Wachter", "Fiona Wachter", "Lady Fiona"],      # shorter forms of the name
    ["Emil", "Emil Toranescu"],                                  # a longer form
    ["Silver-thorn Collars", "Silver Thorn Collar"],            # hyphen, plural
    ["Belview Family", "Belviews"], ["Blinsky's Toy Store", "Blinsky toys"],
    ["Argynvost’s Skull", "Argynvost Skull"],                   # possessive
    ["Ezmerelda d'Avenir", "Ezmerelda d’Avenir"],               # curly quote
    ["Strahd von Zarovich", "Count Strahd von Zarovich", "Vlahd"],  # a different word is not a slip
])
def test_near_misses_leaves_other_forms_of_a_name_alone(names):
    assert fix_spellings.near_misses({"page": names}) == []


def test_kept_variants_are_explained_and_used():
    """The deliberate near-spellings (a pun, an in-story rename...) are listed in spellings.yaml
    under keep, and each is still an alias somewhere, so the list doesn't go stale."""
    keep = fix_spellings.load_keep(ROOT / "data" / "spellings.yaml")
    assert "Chest of Holden" in keep and "Blood of the Vine Tavern" in keep
    aliases = {a for p in wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter) for a in p.aliases}
    assert keep <= aliases, keep - aliases
    assert not keep & set(SPELLINGS)


# --- the site -----------------------------------------------------------------------------------

def test_posts_wiki_and_log_extracts_use_book_spellings():
    """Every name in the posts, wiki pages and log extracts is spelled the book's way. To fix new
    text, run `just spellings`; to add a name, add it to data/spellings.yaml."""
    found = fix_spellings.check(fix_spellings.DEFAULT_PATHS, SPELLINGS)
    assert not found, "Misspelled names (file, wrong, right): " + repr(found[:20])


def test_wiki_aliases_are_not_misspellings_of_their_page():
    """Aliases link the name wherever it appears, so a misspelled alias hides a misspelling behind a
    right link. Fix it in data/spellings.yaml, or list it under keep if the table means it."""
    keep = fix_spellings.load_keep(ROOT / "data" / "spellings.yaml")
    pages = {p.slug: [p.title, *p.aliases]
             for p in wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)}
    assert fix_spellings.near_misses(pages, keep) == []


def test_fixed_names_still_link_to_the_right_page():
    """The fix must keep the link right: the crossroads, not the lake."""
    linker = wiki.Linker(wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter))
    html, slugs = linker.link("<p>Near the Tser Pool Crossroads we met a Vistani caravan.</p>")
    assert slugs == {"tser-crossroads", "vistani"}, html
    post = (ROOT / "content" / "posts" / "2026-02-10-unwelcome-guests.md").read_text(encoding="utf-8")
    assert "Near the Tser Pool Crossroads we met" in post


def _posts():
    out = {}
    for f in sorted((ROOT / "content" / "posts").glob("*.md")):
        meta, body = build.split_front_matter(f.read_text(encoding="utf-8"))
        out[meta.get("slug", f.stem)] = (meta["title"], body)
    return out


def test_post_titles_cut_off_by_obsidian_portal_read_in_full():
    """Obsidian Portal cut two titles mid-word; their addresses stay as they were."""
    posts = _posts()
    assert posts["echoes-of-the-black-terro"][0] == "Echoes of the Black Terror"
    assert posts["blood-and-oaths-under-moonligh"][0] == "Blood and Oaths Under Moonlight"


def test_links_to_posts_do_not_cut_a_word():
    """A wiki line citing a post uses its title; a stale copy of a cut-off title shows up here."""
    titles = {slug: title for slug, (title, _) in _posts().items()}
    cut = []
    for f in (ROOT / "content").rglob("*.md"):
        for text, slug in re.findall(r"\[([^\]]+)\]\(/posts/([^/)#]+)/?\)", f.read_text(encoding="utf-8")):
            title = titles.get(slug, "")
            if title.startswith(text) and len(title) > len(text) and title[len(text)].isalnum():
                cut.append((f.name, text, title))
    assert not cut, cut[:10]


def test_npc_pages_named_from_the_book():
    pages = {p.slug: p for p in wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)}
    assert pages["kiril-stoyanovich"].title == "Kiril Stoyanovich"
    assert pages["baba-lysaga"].title == "Baba Lysaga"
    assert "Emil Toranescu" in pages["emil"].aliases
    assert pages["volenta"].aliases[0] == "Volenta Popofsky"


def test_renamed_wiki_pages_keep_their_old_address():
    redirects = build.load_redirects(ROOT / "data" / "redirects.yaml", "wiki")
    assert redirects["kiril-vonstrranovich"] == "kiril-stoyanovich"
    assert redirects["baba-lasaga"] == "baba-lysaga"
    assert redirects["wachter-haus"] == "wachterhaus"
    assert redirects["sarepool"] == "tser-crossroads"  # "Sarepool" was Tser Pool misheard
    slugs = {p.stem for p in (ROOT / "content" / "wiki").glob("*.md")}
    for old, new in redirects.items():
        assert old not in slugs and new in slugs, (old, new)
