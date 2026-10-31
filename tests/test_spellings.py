"""Names are spelled as the Curse of Strahd book spells them (data/spellings.yaml)."""
import json
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
])
def test_book_spellings(wrong, right):
    assert fix_spellings.fix_text(wrong, SPELLINGS)[0] == right


# --- the site -----------------------------------------------------------------------------------

def test_posts_wiki_and_log_extracts_use_book_spellings():
    """Every name in the posts, wiki pages and log extracts is spelled the book's way. To fix new
    text, run `just spellings`; to add a name, add it to data/spellings.yaml."""
    found = fix_spellings.check(fix_spellings.DEFAULT_PATHS, SPELLINGS)
    assert not found, "Misspelled names (file, wrong, right): " + repr(found[:20])


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
    slugs = {p.stem for p in (ROOT / "content" / "wiki").glob("*.md")}
    for old, new in redirects.items():
        assert old not in slugs and new in slugs, (old, new)
