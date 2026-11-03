"""Eliza at the Tser Pool camp and Elizabella in Stanimir's caravan are one Vistani woman
(Chris, 2026-11-03). One name, Elizabella (his notes from 2/10/2026), one page that cites both
sessions and keeps Malron's unease about her."""
import re
from pathlib import Path

import build
import fix_spellings
import wiki

ROOT = Path(__file__).resolve().parent.parent


def _page(slug):
    pages = {p.slug: p for p in wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)}
    return pages.get(slug)


def test_one_page_named_elizabella():
    page = _page("elizabella")
    assert page is not None and page.title == "Elizabella"
    assert _page("eliza") is None


def test_old_eliza_address_forwards():
    redirects = build.load_redirects(ROOT / "data" / "redirects.yaml", "wiki")
    assert redirects["eliza"] == "elizabella"


def test_page_cites_both_sessions_and_malrons_unease():
    text = (ROOT / "content" / "wiki" / "elizabella.md").read_text(encoding="utf-8")
    story = text.split("<!-- from-the-log -->")[0]
    assert "## Description" in story
    assert "(/posts/tser-pool/)" in story and "(/posts/unwelcome-guests/)" in story
    assert "shadow" in story


def test_misheard_forms_are_fixed():
    spellings = fix_spellings.load_spellings(ROOT / "data" / "spellings.yaml")
    assert spellings["Eliza"] == "Elizabella"
    assert spellings["Elisabetta"] == "Elizabella"


def test_no_eliza_left():
    left = [f.relative_to(ROOT).as_posix()
            for d in ("content", "data") for f in (ROOT / d).rglob("*")
            if f.suffix in {".md", ".yaml", ".json"} and f.name != "spellings.yaml"
            and re.search(r"\bEliza\b", f.read_text(encoding="utf-8"))]
    assert left == []
