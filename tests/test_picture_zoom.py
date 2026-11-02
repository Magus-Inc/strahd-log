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


def test_the_viewer_zooms_in_with_scroll_pinch_and_tap_and_pans_by_dragging():
    """Chris, 2026-11-02: "clicking barely makes them bigger and scrolling once clicked won't zoom
    in further". The picture opens as big as the screen allows, then zooms further."""
    script = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    zoom = script[script.index("<script data-zoom>"):]
    zoom = zoom[:zoom.index("</script>")]
    assert '"wheel"' in zoom and "passive: false" in zoom      # scroll zooms instead of scrolling
    assert '"pointerdown"' in zoom and '"pointermove"' in zoom  # drag to pan, two fingers to pinch
    assert "MAX_ZOOM" in zoom and "TAP_ZOOM" in zoom            # a tap zooms in, a second tap back out
    assert "naturalWidth" in zoom  # opens fitted to the screen, even past the file's own size
    assert re.search(r"dialog\.zoom img \{[^}]*touch-action: none", CSS)  # the page doesn't pinch instead
    assert "Scroll or pinch to zoom" in script


# --- the full-size files the viewer loads (Chris, 2026-11-02: "I have the bigger res pictures") --

FULL = ROOT / "static" / "images" / "full"


def test_a_picture_with_a_full_size_file_says_so_and_others_do_not(tmp_path):
    (tmp_path / "images" / "full").mkdir(parents=True)
    (tmp_path / "images" / "full" / "big-ai.jpg").write_bytes(b"x")
    html = '<p><img alt="A" src="/images/big-ai.jpg"></p><p><img alt="B" src="/images/small-ai.jpg"></p>'
    out = build.article.full_size(html, tmp_path)
    assert '<img alt="A" src="/images/big-ai.jpg" data-full="/images/full/big-ai.jpg">' in out
    assert '<img alt="B" src="/images/small-ai.jpg">' in out


def test_full_size_addresses_follow_the_base_path():
    assert build.rebase('<img src="/images/a.jpg" data-full="/images/full/a.jpg">', "/strahd-log/") == \
        '<img src="/strahd-log/images/a.jpg" data-full="/strahd-log/images/full/a.jpg">'


def test_every_full_size_file_is_a_bigger_copy_of_a_published_picture():
    from PIL import Image
    files = sorted(FULL.glob("*"))
    assert len(files) >= 100
    for f in files:
        small = ROOT / "static" / "images" / f.name
        assert small.is_file(), f.name
        with Image.open(f) as big, Image.open(small) as pic:
            assert big.width > pic.width, f.name
            assert abs(big.width / big.height - pic.width / pic.height) < 0.02, f.name


def test_pages_point_the_viewer_at_the_full_size_file_and_ship_it(site):
    assert 'data-full="/images/full/zorya-ai.jpg"' in read(site, "wiki/zorya")
    assert 'data-full="/images/full/kasimir-ai.jpg"' in read(site, "posts/a-doll-for-arabelle")
    assert (site / "images" / "full" / "zorya-ai.jpg").is_file()


def test_the_viewer_swaps_in_the_full_size_file_only_when_opened():
    script = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    zoom = script[script.index("<script data-zoom>"):]
    assert "dataset.full" in zoom[:zoom.index("</script>")]
