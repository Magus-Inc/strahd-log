"""Pictures read big and open full size (Chris, 2026-11-02: "why are all the images so small now on
desktop ... there is no way to click on an image to see it in more detail")."""
import re
from pathlib import Path

import pytest

import build

ROOT = Path(build.__file__).parent
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("zoom-site") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return out


def read(site, path):
    return (site / path / "index.html").read_text(encoding="utf-8")


def test_every_post_and_wiki_page_has_the_picture_viewer(site):
    for path in ("wiki/zorya", "wiki/rahadin", "posts/a-doll-for-arabelle"):
        html = read(site, path)
        assert '<dialog class="zoom"' in html, path
        assert 'data-zoom' in html, path  # the script that opens pictures in it


def test_the_viewer_covers_story_infobox_and_vote_pictures_but_not_slides_or_maps():
    script = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    m = re.search(r'ZOOMABLE = "([^"]+)"', script)
    assert m, "base.html names the pictures the viewer opens"
    selector = m.group(1)
    for part in (".prose img", ".infobox img", ".wiki-hero img"):
        assert part in selector
    assert "deck" not in selector and "map" not in selector


def test_a_post_picture_still_leads_to_its_wiki_page_from_the_viewer():
    script = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "a.ai-picture" in script and "in the wiki" in script


def test_zoomable_pictures_show_a_zoom_cursor_and_the_viewer_fills_the_screen():
    assert "cursor: zoom-in" in CSS
    assert re.search(r"dialog\.zoom img \{[^}]*max-height: 9\dvh", CSS)
    assert re.search(r"dialog\.zoom img \{[^}]*max-width: 9\dvw", CSS)


def test_infobox_picture_is_full_width_on_desktop_with_the_facts_below():
    """The facts no longer sit beside the picture and squeeze it to 17rem."""
    assert "grid-template-columns: 17rem 1fr" not in CSS
    assert re.search(r"\.infobox-picture img \{[^}]*max-height: 80vh", CSS)
    assert re.search(r"\.infobox dl \{[^}]*repeat\(auto-fit", CSS)
