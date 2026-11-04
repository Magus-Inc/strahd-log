"""Picture weight on pages full of pictures (Chris, 2026-11-04).

Start here once loaded about 1.5 MB of full-size portraits and chapter pictures. Pages that show a grid
of pictures (the home page, the wiki index, Start here) load small copies the build makes:
images/cards/ (home cards), images/thumbs/ (wiki list cards, faces) and images/small/ (Start here).
Wiki articles and session logs keep the full-size pictures. A new page with a grid of pictures must be
added to GRID_PAGES, and its pictures must come from small copies.
"""
import re

import pytest

GRID_PAGES = ("index.html", "wiki/index.html", "start/index.html")
MAX_PICTURE = 100_000  # bytes; a small copy is 5-80 KB, a full-size picture 100-250 KB
# Pictures on a grid page allowed to be bigger, with why.
BIG_OK = {
    "images/map-teaser.jpg": "the map's fine lines and labels blur when shrunk; it loads only when "
                             "the reader scrolls to the bottom",
}
SMALL_FOLDERS = ("images/cards/", "images/thumbs/", "images/small/")


def pictures_on(html: str) -> set[str]:
    found = re.findall(r'<img[^>]*\ssrc="/([^"]+)"', html) + re.findall(r"url\('/([^']+)'\)", html)
    found += [part.split()[0].lstrip("/") for srcset in re.findall(r'srcset="([^"]+)"', html)
              for part in srcset.split(",")]
    return {p.split("?")[0] for p in found}


def is_article(rel: str) -> bool:
    """A session log or one wiki article: these keep full-size pictures."""
    return bool(re.fullmatch(r"(posts|wiki)/[^/]+/index\.html", rel))


@pytest.mark.parametrize("page", GRID_PAGES)
def test_grid_pages_load_only_small_copies(real_build, page):
    html = (real_build.out / page).read_text(encoding="utf-8")
    for rel in pictures_on(html):
        path = real_build.out / rel
        if rel in BIG_OK or not path.is_file() or rel.endswith(".svg"):
            continue
        assert rel.startswith(SMALL_FOLDERS), f"{page}: {rel} is a full-size picture; use a small copy"
        assert path.stat().st_size <= MAX_PICTURE, (page, rel, path.stat().st_size)


def test_every_page_with_a_grid_of_pictures_is_checked(real_build):
    for path in real_build.out.rglob("index.html"):
        rel = path.relative_to(real_build.out).as_posix()
        if is_article(rel) or rel in GRID_PAGES:
            continue
        pictures = pictures_on(path.read_text(encoding="utf-8"))
        assert len(pictures) <= 6, f"{rel} shows {len(pictures)} pictures: add it to GRID_PAGES and use small copies"


def test_every_big_picture_allowed_says_why():
    assert all(len(why) > 20 for why in BIG_OK.values())
