"""The map page's controls live inside the map's frame, and every map can go full screen."""
import re

import pytest

import build

CSS = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
ZOOM_JS = (build.ROOT / "templates" / "_map_zoom.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return out


def figure_of(html: str) -> str:
    return re.search(r'<figure class="map-figure".*?</figure>', html, re.S).group(0)


def test_map_page_controls_sit_inside_the_map_frame(site):
    html = (site / "map" / "index.html").read_text(encoding="utf-8")
    fig = figure_of(html)
    for control in ('id="show-trail"', 'id="faint-markers"', 'id="trail-upto"', 'id="trail-now"'):
        assert control in fig, control
        assert html.count(control) == 1, control  # not also left above the map
    # Nothing between the page heading and the map any more.
    between = html.split("</header>", 1)[1].split('<figure class="map-figure"', 1)[0]
    assert "<input" not in between


def test_post_maps_have_no_trail_controls(site):
    html = (site / "posts" / "skeletal-rider" / "index.html").read_text(encoding="utf-8")
    fig = figure_of(html)
    assert 'id="show-trail"' not in fig and 'id="trail-upto"' not in fig


@pytest.mark.parametrize("page", ["map/index.html", "posts/skeletal-rider/index.html"])
def test_every_map_has_a_full_screen_button(site, page):
    fig = figure_of((site / page).read_text(encoding="utf-8"))
    button = re.search(r'<button[^>]*data-zoom="full"[^>]*>', fig)
    assert button and 'aria-label="Full screen"' in button.group(0) and 'aria-pressed="false"' in button.group(0)


def test_full_screen_fills_the_window_and_stops_page_scroll():
    rule = re.search(r"\n\.map-figure\.map-full \{([^}]*)\}", CSS).group(1)
    assert "position: fixed" in rule and "inset: 0" in rule
    assert re.search(r"html\.map-full-open[^{]*\{[^}]*overflow: hidden", CSS)
    # Above the site header, below the place card so a place still opens in full screen.
    z_full = int(re.search(r"z-index: (\d+)", rule).group(1))
    z_card = int(re.search(r"\n\.place-panel \{[^}]*z-index: (\d+)", CSS).group(1))
    assert z_full < z_card


def test_full_screen_script_fits_the_screen_and_exits_cleanly():
    # The whole map fits a screen of any shape; the browser's own full screen is used when it has one
    # (not on iPhone), and leaving it (Esc) leaves our full-screen mode too.
    assert "map-full" in ZOOM_JS and "map-full-open" in ZOOM_JS
    assert "requestFullscreen" in ZOOM_JS and "fullscreenchange" in ZOOM_JS
    assert '"Escape"' in ZOOM_JS
    assert "aria-pressed" in ZOOM_JS
    # Escape closes an open place card first; only the next Escape leaves full screen.
    assert ".place-panel:not([hidden])" in ZOOM_JS


def test_controls_hidden_when_printing():
    printing = CSS.split("@media print", 1)[1]
    hidden = re.search(r"\n  ([^{}]*)\{ display: none !important; \}", printing).group(1)
    assert ".map-controls" in hidden
