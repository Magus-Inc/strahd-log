import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

import barovia_map
import build
import wiki


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def page(slug, title, aliases=(), kind="place"):
    return wiki.WikiPage(slug=slug, title=title, type=kind, aliases=list(aliases))


PAGES = [page("barovia", "Barovia", ["Village of Barovia"]), page("vallaki", "Vallaki", ["Vellaki"]),
         page("blue-water-inn", "Blue Water Inn"), page("krezk", "Krezk"), page("strahd", "Strahd", kind="npc")]
MAP = """places:
  barovia: {xy: [780, 450], label: Village of Barovia, names: [Village of Barovia]}
  vallaki: {xy: [400, 270]}
  krezk: {xy: [120, 232], anchor: end}
within:
  blue-water-inn: vallaki
"""


@pytest.fixture
def places(tmp_path):
    return barovia_map.load_places(write(tmp_path / "map.yaml", MAP), PAGES)


def test_base_map_is_deterministic_svg():
    svg = barovia_map.draw_base()
    assert svg == barovia_map.draw_base()
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 1000 750"
    assert "Lake Zarovich" in svg and "<script" not in svg


def test_load_places_labels_names_and_parents(places):
    by_slug, parent = places
    assert by_slug["barovia"].title == "Village of Barovia" and by_slug["barovia"].names == ["Village of Barovia"]
    assert by_slug["vallaki"].names == ["Vallaki", "Vellaki"]
    assert by_slug["krezk"].label_xy == (110.0, 236.0)
    assert parent["blue-water-inn"] == "vallaki" and "strahd" not in parent


def test_load_places_rejects_unknown_pages(tmp_path):
    with pytest.raises(ValueError, match="nowhere"):
        barovia_map.load_places(write(tmp_path / "m.yaml", "places:\n  nowhere: {xy: [1, 2]}\n"), PAGES)


def test_stops_follow_first_mention_and_map_rooms_to_places(places):
    by_slug, parent = places
    text = "We left Krezk, slept at the Blue Water Inn, then Vallaki again. Barovia is grim."
    # "Barovia" alone is the land, not the village, so it is not a stop.
    assert barovia_map.stops(text, by_slug, parent, PAGES) == ["krezk", "vallaki"]
    assert barovia_map.stops("Back to the Village of Barovia.", by_slug, parent, PAGES) == ["barovia"]


def test_visits_override_mentions_and_draw_strokes(tmp_path, places):
    by_slug, parent = places
    posts = []
    for stem, title, body in [("2024-01-01-a", "A", "Talk of Vallaki."), ("2024-01-08-b", "B", "Krezk!"),
                              ("2024-01-15-c", "C", "Nowhere much.")]:
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {title}\ndate: '{stem[:10]}'\n---\n\n{body}\n"))
        post.html = build.render_markdown(post.body_md)
        posts.append(post)
    visits = barovia_map.load_visits(write(tmp_path / "trail.yaml", "sessions:\n  2024-01-01-a: [barovia]\n  2024-01-15-c: [vallaki, krezk]\n"), by_slug)
    legs = barovia_map.trail(posts, by_slug, parent, PAGES, visits)
    # A talks about Vallaki but was in the village; B has no entry, so its mentions count.
    assert [(leg["post"].title, leg["stops"]) for leg in legs] == [("A", ["barovia"]), ("B", ["krezk"]), ("C", ["vallaki", "krezk"])]
    assert [len(leg["segments"]) for leg in legs] == [0, 1, 2]
    assert [leg["n"] for leg in legs] == [1, 2, 3]
    # Every hop follows the roads: each step of its path is a road (or track) edge.
    graph = barovia_map.road_graph()
    for leg in legs:
        for seg in leg["segments"]:
            assert seg["road"]
            assert all(b in graph[a] for a, b in zip(seg["points"], seg["points"][1:]))
    # Barovia to Krezk is a long way round by road, not a straight line.
    assert len(legs[1]["segments"][0]["points"]) > 10
    # Sessions ending at the same place get markers fanned around it, not on top of each other.
    assert legs[1]["marker"] != legs[2]["marker"]
    assert [p.title for p in by_slug["krezk"].sessions] == ["C", "B"]


def test_load_visits_rejects_unknown_places(tmp_path, places):
    with pytest.raises(ValueError, match="atlantis"):
        barovia_map.load_visits(write(tmp_path / "trail.yaml", "sessions:\n  x: [atlantis]\n"), places[0])


def test_build_writes_map_page_and_post_maps(tmp_path):
    root = tmp_path
    write(root / "content" / "posts" / "2024-01-09-first.md", "---\ntitle: First\ndate: '2024-01-09'\n---\n\nIn the Village of Barovia.\n")
    write(root / "content" / "posts" / "2024-01-16-second.md", "---\ntitle: Second\ndate: '2024-01-16'\n---\n\nOn to Vallaki.\n")
    write(root / "content" / "wiki" / "barovia.md", "---\ntitle: Barovia\ntype: place\naliases: [Village of Barovia]\n---\n")
    write(root / "content" / "wiki" / "vallaki.md", "---\ntitle: Vallaki\ntype: place\n---\n")
    write(root / "content" / "wiki" / "blue-water-inn.md", "---\ntitle: Blue Water Inn\ntype: place\n---\n")
    write(root / "data" / "map.yaml", "places:\n  barovia: {xy: [780, 450], names: [Village of Barovia]}\n  vallaki: {xy: [400, 270]}\n"
                                      "within:\n  blue-water-inn: vallaki\n"
                                      "sprites:\n  vallaki: {image: vallaki, xy: [400, 260], width: 60}\n")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")

    assert (out / "map" / "barovia.svg").is_file()
    page_html = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert 'href="/strahd-log/map/barovia.svg"' in page_html and 'class="crumb' in page_html
    # The parchment lies under the drawing, and the sprites over it, under the trail and the pins.
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert page_html.index("images/map/parchment.jpg") < page_html.index("map/barovia.svg") \
        < page_html.index('href="/strahd-log/images/map/sprites/vallaki.webp" x="370.0"') < page_html.index('class="trail"')
    assert (out / "images" / "map" / "sprites" / "vallaki.webp").is_file()
    # A place's picture is its link: it opens the place like its pin, and glows red on hover.
    assert re.search(r'<a class="sprite js-pin" href="/strahd-log/wiki/vallaki/" data-place="vallaki">\s*<title>Vallaki</title>\s*'
                     r'<image href="/strahd-log/images/map/sprites/vallaki.webp"', page_html)
    assert re.search(r"\.map \.sprite:hover image[^{]*\{[^}]*filter: url\(#place-glow\)", css)
    assert 'data-zoom="in"' in page_html and 'href="/strahd-log/posts/second/"' in page_html
    assert 'href="/strahd-log/wiki/vallaki/"' in page_html and 'id="show-trail"' in page_html
    assert 'id="faint-markers"' in page_html and "See-through numbers" in page_html  # the see-through toggle
    # Zoom: buttons, and our own pinch / wheel / double-tap handling (no library); the wheel zooms
    # without Ctrl, so there is no hint to show.
    assert all(f'data-zoom="{z}"' in page_html for z in ("in", "out", "reset"))
    assert 'id="map-hint"' not in page_html and "Ctrl + scroll" not in page_html
    assert '"wheel"' in page_html and "zoomAt" in page_html and '"dblclick"' in page_html
    assert "<script src=" not in page_html
    # Session markers are drawn last, over the place names, so a label never hides a number.
    assert page_html.index('class="pins"') < page_html.index('class="labels"') < page_html.index('class="markers"')
    # Names, pins and markers shrink about their own point in map units; fill-box put names in the
    # wrong place on iPhone Safari when zoomed.
    assert 'class="pin-dot" style="transform-origin: ' in page_html and '" style="transform-origin: ' in page_html
    assert "transform-box: fill-box;" not in (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    # Place names link to their wiki pages (every place on the map has one).
    # On the map page a name opens the same place card as its picture and pin (Chris: one predictable
    # action); on a post's small map it links straight to the wiki page.
    assert 'wiki/vallaki/" class="js-pin" data-place="vallaki" tabindex="-1"><text' in page_html
    second = (out / "posts" / "second" / "index.html").read_text(encoding="utf-8")
    # A session's map stops at that session: no crumbs from later sessions.
    first = (out / "posts" / "first" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert 'data-i="1"' in first and 'data-i="2"' not in first and 'current" data-i="2"' in second
    # No black dots: the sprites show where places are. Each pin stays as an invisible, bigger tap
    # target with no ring.
    assert re.search(r"\.map \.pin-dot \{[^}]*fill: transparent", css) and 'r="11" class="pin-dot"' in page_html
    # The place card floats over the map (a bottom sheet on phones), so it is seen without scrolling.
    assert re.search(r"\.place-panel \{[^}]*position: fixed[^}]*bottom: 0", css) and "scrollIntoView" not in page_html
    assert '"Escape"' in page_html
    # The card stands out from the page: a light red edge and a red glow.
    assert re.search(r"\.place-panel \{[^}]*border: 1\.5px solid rgba\(224, 74, 99[^}]*box-shadow:[^;]*0 0 22px rgba\(224, 74, 99", css)
    # Chris: no red ring when a place is clicked, and a red glow (gold was lost on the parchment) strong enough to see: a solid red
    # edge (zero-blur shadows) plus a wide halo, also kept on the place whose card is open.
    assert ".pin:focus .pin-dot" not in css and "stroke: var(--accent)" not in css.split(".map .pin-dot")[1].split("/* Crumb")[0]
    # The glow is an SVG filter in the map itself: iPhone Safari ignores CSS drop-shadow() on SVG
    # pictures, so Chris saw no glow there (2026-11-02). A solid edge (dilate) plus a blurred halo.
    assert re.search(r"\.map \.sprite\.chosen image[^{]*\{[^}]*filter: url\(#place-glow\)", css) and "drop-shadow(" not in css.split("/* Map:")[1].split("/* Crumb")[0]
    glow = re.search(r'<filter id="place-glow".*?</filter>', page_html, re.S).group(0)
    assert 'operator="dilate"' in glow and "feGaussianBlur" in glow and 'flood-color="#c8213f"' in glow
    assert re.search(r"\.map \.pin\.under-sprite \{ pointer-events: none", css)
    assert "classList.add(\"chosen\")" in page_html and "--glow: #c8213f" in css
    # Dragging the map never selects (highlights) place names.
    assert re.search(r"\.map \{[^}]*user-select: none", css) and re.search(r"\.map \{[^}]*-webkit-user-select: none", css)
    assert 'wiki/vallaki/" tabindex="-1"><text' in second and 'class="sprite js-pin"' not in second
    assert "Where we were" in second and 'class="crumb current"' in second and 'class="marker current"' in second
    inn = (out / "wiki" / "blue-water-inn" / "index.html").read_text(encoding="utf-8")
    assert "On the map" in inn and 'data-place="vallaki"' in inn
    assert 'href="/strahd-log/map/"' in (out / "index.html").read_text(encoding="utf-8")

    # Chris: pinch-zoom didn't work on a post's map on his phone (the map blocks the browser's own
    # pinch so it can pan the page). Every map, not only the map page, zooms and pans with our own
    # code: buttons, two-finger pinch, one-finger drag once zoomed in, double-tap.
    for html in (page_html, second, inn):
        assert html.count('class="map-zoom"') == 1 and all(f'data-zoom="{z}"' in html for z in ("in", "out", "reset"))
        assert html.count("function zoomAt(") == 1 and '"pointerdown"' in html and '"dblclick"' in html
        assert "<script src=" not in html
    # Small maps sit in the middle of a post, so a plain scroll wheel keeps scrolling the page there;
    # only a trackpad pinch (a wheel with Ctrl) zooms them. The map page zooms with the plain wheel.
    assert 'data-wheel="zoom"' in page_html and 'data-wheel="zoom"' not in second + inn


def test_wiki_page_map_opens_on_its_place_and_marks_it(tmp_path):
    """Chris 2026-11-02: on Berez and Durst Manor's wiki pages you couldn't tell where on the map the
    place was. A wiki page's map opens zoomed in on its place, its picture glows red and its name is
    red; a place with no picture gets a red dot. A room's page (the Blue Water Inn) marks its town."""
    root = tmp_path
    write(root / "content" / "posts" / "2024-01-09-first.md", "---\ntitle: First\ndate: '2024-01-09'\n---\n\nIn the Village of Barovia, then Vallaki.\n")
    write(root / "content" / "wiki" / "barovia.md", "---\ntitle: Barovia\ntype: place\naliases: [Village of Barovia]\n---\n")
    write(root / "content" / "wiki" / "vallaki.md", "---\ntitle: Vallaki\ntype: place\n---\n")
    write(root / "content" / "wiki" / "blue-water-inn.md", "---\ntitle: Blue Water Inn\ntype: place\n---\n")
    write(root / "data" / "map.yaml", "places:\n  barovia: {xy: [780, 450], names: [Village of Barovia]}\n  vallaki: {xy: [400, 270]}\n"
                                      "within:\n  blue-water-inn: vallaki\n"
                                      "sprites:\n  vallaki: {image: vallaki, xy: [400, 260], width: 60}\n")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    vallaki = (out / "wiki" / "vallaki" / "index.html").read_text(encoding="utf-8")
    inn = (out / "wiki" / "blue-water-inn" / "index.html").read_text(encoding="utf-8")
    barovia = (out / "wiki" / "barovia" / "index.html").read_text(encoding="utf-8")
    for html in (vallaki, inn):
        assert 'data-focus="400.0 270.0"' in html
        assert re.search(r'<a class="sprite here" href="/strahd-log/wiki/vallaki/" data-place="vallaki">', html)
        assert re.search(r'<a class="here" href="/strahd-log/wiki/vallaki/" tabindex="-1"><text', html)
        assert 'class="here-dot"' not in html  # the glowing picture marks it
    assert 'data-focus="780.0 450.0"' in barovia and 'class="here-dot"' in barovia
    # The glow is the map page's chosen-place glow; names and dots are the same red.
    assert re.search(r"\.map \.sprite\.here image[^{]*\{[^}]*filter: url\(#place-glow\)", css)
    # The wiki page's own place carries the filter in its markup too, so it glows even without the CSS.
    for html in (vallaki, inn):
        assert '<filter id="place-glow"' in html and re.search(r'class="sprite here"[^>]*>\s*<title>[^<]*</title>\s*<image filter="url\(#place-glow\)"', html)
    assert re.search(r"\.map \.labels \.here text \{[^}]*fill: #b3122e", css)
    assert re.search(r"\.map \.here-dot \{[^}]*fill: #b3122e", css)
    # The zoom script starts from the focus, and the whole-map button still shows the whole map.
    assert 'getAttribute("data-focus")' in vallaki
    # A place on the east edge (Durst Manor) isn't left under the zoom buttons: zoomed in, the view may
    # run a little past that edge.
    assert "EAST_SPARE = 0.14" in vallaki and "clampAxis(view.x, view.w, MAP.w, EAST_SPARE)" in vallaki
    # Other maps don't focus: the map page and the posts open on the whole map.
    assert "data-focus=" not in (out / "map" / "index.html").read_text(encoding="utf-8")
    assert "data-focus=" not in (out / "posts" / "first" / "index.html").read_text(encoding="utf-8")


def test_landmarks_mark_a_wiki_page_on_its_map_only(tmp_path):
    """A landmark (a river, a wood, a lone tree) has a wiki page but no pin, label or card on the map
    page; its wiki page's map opens on it with a red dot and its name (Chris, 2026-11-02)."""
    pages = PAGES + [page("luna-river", "Luna River")]
    path = write(tmp_path / "map.yaml", MAP + "landmarks:\n  luna-river: {xy: [366, 350], anchor: start}\n")
    places, _ = barovia_map.load_places(path, pages)
    marks = barovia_map.load_landmarks(path, pages, places)
    assert "luna-river" not in places and marks["luna-river"].title == "Luna River"
    assert (marks["luna-river"].x, marks["luna-river"].y) == (366.0, 350.0) and marks["luna-river"].anchor == "start"
    with pytest.raises(ValueError, match="no wiki page"):
        barovia_map.load_landmarks(write(tmp_path / "bad.yaml", MAP + "landmarks:\n  nowhere: {xy: [1, 2]}\n"), pages, places)
    with pytest.raises(ValueError, match="already a place"):
        barovia_map.load_landmarks(write(tmp_path / "dup.yaml", MAP + "landmarks:\n  vallaki: {xy: [1, 2]}\n"), pages, places)

    root = tmp_path / "site"
    write(root / "content" / "posts" / "2024-01-09-first.md", "---\ntitle: First\ndate: '2024-01-09'\n---\n\nTo Vallaki by the Luna River.\n")
    write(root / "content" / "wiki" / "vallaki.md", "---\ntitle: Vallaki\ntype: place\n---\n")
    write(root / "content" / "wiki" / "luna-river.md", "---\ntitle: Luna River\ntype: place\n---\n")
    write(root / "data" / "map.yaml", "places:\n  vallaki: {xy: [400, 270]}\nlandmarks:\n  luna-river: {xy: [366, 350], anchor: start}\n")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")
    river = (out / "wiki" / "luna-river" / "index.html").read_text(encoding="utf-8")
    assert "On the map" in river and 'data-focus="366.0 350.0"' in river and 'class="here-dot"' in river
    assert re.search(r'<a class="here" href="/strahd-log/wiki/luna-river/" tabindex="-1"><text[^>]*>Luna River</text>', river)
    whole = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert "wiki/luna-river/" not in whole  # no pin, name or card on the map page


def test_every_barovian_place_page_has_a_map():
    """Every place page set in Barovia shows where it is (Chris, 2026-11-02). Places the party has only
    heard of stay off until they go there; places outside Barovia never get one."""
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    mapped = set(data["places"]) | set(data["within"]) | set(data.get("landmarks") or {})
    not_yet = {"forest-fane", "kavan-s-cairn", "zoldoph"}            # only talked about so far
    elsewhere = {"daggerford", "ethereal-plane", "the-void", "othrondil"}  # not in Barovia
    for f in sorted((ROOT / "content" / "wiki").glob("*.md")):
        if "\ntype: place\n" in f.read_text(encoding="utf-8").replace("\r\n", "\n"):
            assert f.stem in mapped | not_yet | elsewhere, f"{f.stem} has no place on the map"
    assert not mapped & (not_yet | elsewhere)
    # Where the posts put them: gates of Vallaki, the shrine in the werewolf den, Sarepool is the Tser
    # Pool crossroads (Chris), the ancient oak is the old oak by the Ivlis.
    within = data["within"]
    assert within["eastern-gate"] == within["zarovich-gate"] == "vallaki"
    assert within["shrine-of-mother-night"] == "lake-baratok-cave" and within["sarepool"] == "tser-crossroads"
    # The Blood on the Vine is the tavern in the Village of Barovia where the party met Ismark (Barovia,
    # Barovia); it was wrongly in Vallaki (Chris, 2026-11-02).
    assert within["blood-on-the-vine-tavern"] == "barovia"
    # The Ancient Oak page is the "K & V" tree on the Old Windmill Road east of Vallaki (The Oath, the Spy
    # and the Silver Moon), not the oak by the Ivlis (independent review, 2026-11-02).
    assert data["landmarks"]["ancient-oak"]["xy"] == data["spots"]["bonegrinder-road"]["xy"]
    # The Balinoks: the sun sank behind them seen from Vallaki, so the western peaks (Unwelcome Guests).
    assert data["landmarks"]["balinoks"]["xy"][0] < data["places"]["vallaki"]["xy"][0]
    assert {"luna-river", "svalich-woods", "balinoks"} <= set(data["landmarks"])


def test_no_map_file_means_no_map(tmp_path):
    write(tmp_path / "content" / "posts" / "2024-01-09-a.md", "---\ntitle: A\ndate: '2024-01-09'\n---\n\nHi.\n")
    out = tmp_path / "public"
    build.build(tmp_path / "content" / "posts", out, site_url="https://x.example")
    assert not (out / "map").exists() and "/map/" not in (out / "index.html").read_text(encoding="utf-8")


def test_route_follows_roads_between_junctions():
    graph = barovia_map.road_graph()
    vallaki, castle = (400, 250), (720, 398)
    path = barovia_map.route(graph, vallaki, castle)
    assert path[0] == vallaki and path[-1] == castle
    assert (490, 305) in path and (610, 360) in path  # round the hairpin by Old Bonegrinder, then the switchbacks
    assert all(b in graph[a] for a, b in zip(path, path[1:]))
    assert barovia_map.route(graph, vallaki, vallaki) == [vallaki]


def test_every_mapped_place_sits_on_a_road():
    import yaml
    spec = yaml.safe_load(Path("data/map.yaml").read_text(encoding="utf-8"))
    graph = barovia_map.road_graph()
    for slug, place in spec["places"].items():
        if place.get("offroad"):
            assert barovia_map.nearest_vertex(graph, *place["xy"]) is None, slug  # really off the roads
        else:
            assert tuple(place["xy"]) in graph, slug


def test_trail_passes_the_east_gate_only_once():
    # The party came through the east gate of Barovia once, from Durst Manor into the village.
    import yaml
    sessions = yaml.safe_load(Path("data/trail.yaml").read_text(encoding="utf-8"))["sessions"]
    stops = {stem: (e["stops"] if isinstance(e, dict) else e or []) for stem, e in sessions.items()}
    assert [stem for stem, s in stops.items() if "gates-of-barovia" in s] == ["2024-02-13-barovia-barovia"]
    # The black carriage waited at the west gates, on the way to the castle.
    assert "west-gates-of-barovia" in stops["2025-07-29-the-oath-the-spy-and-the-silver-moon"]


def test_answered_sessions_use_the_new_places():
    import yaml
    sessions = yaml.safe_load(Path("data/trail.yaml").read_text(encoding="utf-8"))["sessions"]
    # Chris (2026-11-01): Dream Pies met Morgantha's cart at the turnoff to Old Bonegrinder and never
    # went down to the windmill; its number sits at Tser Falls bridge, where Sir Godfrey stood.
    assert sessions["2024-07-16-dream-pies"] == {
        "stops": ["tser-pool-road", "tser-falls-bridge", "tser-crossroads", "bonegrinder-fork", "lake-road"],
        "marker": "tser-falls-bridge"}
    # Heart Stone: planning in Vallaki, then the road toward the windmill heist (not the Tser Pool crossroads).
    assert sessions["2025-01-14-the-hunt-for-the-heart-stone"] == {"stops": ["vallaki", "bonegrinder-road"], "marker": "vallaki"}
    assert sessions["2025-04-15-the-whispering-wall"] == ["yester-hill", "whispering-wall"]
    assert sessions["2026-02-10-unwelcome-guests"] == ["vallaki", "tser-crossroads", "castle-ravenloft"]
    assert "2026-02-03-notebook" not in sessions  # merged into welcome-back-to-vellanki


def test_offroad_place_is_reached_by_a_dotted_leg(tmp_path):
    pages = [page("yester-hill", "Yester Hill"), page("whispering-wall", "Whispering Wall"),
             page("wizard-of-wines", "Wizard of Wines")]
    places, parent = barovia_map.load_places(write(tmp_path / "map.yaml",
        "places:\n  wizard-of-wines: {xy: [110, 360]}\n  yester-hill: {xy: [70, 488]}\n"
        "  whispering-wall: {xy: [40, 520], offroad: true}\n"), pages)
    posts = []
    for stem in ("2025-04-01-a", "2025-04-15-b", "2025-04-29-c"):
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {stem}\ndate: '{stem[:10]}'\n---\n\nx\n"))
        post.html = "<p>x</p>"
        posts.append(post)
    visits = {"2025-04-01-a": ["wizard-of-wines", "yester-hill"], "2025-04-15-b": ["yester-hill", "whispering-wall"]}
    post = posts.pop()
    legs = barovia_map.trail(posts, places, parent, pages, visits)
    assert [s["road"] for s in legs[0]["segments"]] == [True]
    assert [s["road"] for s in legs[1]["segments"]] == [False]
    # Leaving an off-road place, the party walks back to the nearest road first, then follows it.
    legs = barovia_map.trail(posts + [post], places, parent, pages, {**visits, post.source.stem: ["wizard-of-wines"]})
    assert [s["road"] for s in legs[2]["segments"]] == [False, True]


ROOT = Path(__file__).resolve().parent.parent


def real_travel():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    return barovia_map.load_travel(ROOT / "data" / "travel-times.yaml", places)


def test_travel_legs_match_the_table_and_the_map_prints_no_hours():
    import yaml
    table = {(leg["from"], leg["to"]): float(leg["hours"])
             for leg in yaml.safe_load((ROOT / "data" / "travel-times.yaml").read_text(encoding="utf-8"))["legs"]}
    travel = real_travel()
    assert {(leg["from"], leg["to"]): leg["hours"] for leg in travel} == table
    root = ET.fromstring(barovia_map.draw_base())
    assert not [t for t in root.iter() if t.get("class") == "hours"]  # Chris: no hour markers on the trails
    assert any("hours on foot" in "".join(t.itertext()) for t in root.iter())  # the scale bar stays


def test_travel_legs_need_known_ends_on_the_roads(tmp_path, places):
    by_slug, _ = places
    with pytest.raises(ValueError, match="unknown"):
        barovia_map.load_travel(write(tmp_path / "t.yaml", "legs:\n  - {from: vallaki, to: atlantis, hours: 1}\n"), by_slug)
    with pytest.raises(ValueError, match="road vertex"):
        barovia_map.load_travel(write(tmp_path / "t.yaml", "junctions:\n  nowhere: [500, 700]\n"
                                      "legs:\n  - {from: vallaki, to: nowhere, hours: 1}\n"), by_slug)
    assert barovia_map.load_travel(tmp_path / "missing.yaml", by_slug) == []


def test_places_keep_their_places_on_the_official_layout():
    # Where things sit relative to each other, as on the official map (y grows southward).
    import yaml
    xy = {slug: spec["xy"] for slug, spec in
          yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["places"].items()}
    x = {slug: v[0] for slug, v in xy.items()}
    y = {slug: v[1] for slug, v in xy.items()}
    assert x["durst-manor"] > x["gates-of-barovia"] > x["barovia"] > x["castle-ravenloft"]   # east to west
    assert x["vallaki"] < x["the-windmill"] < x["tser-crossroads"] < x["castle-ravenloft"]
    assert x["krezk"] < x["raven-river-crossroads"] < x["tower-of-khazan"] < x["luna-river-crossroads"] < x["vallaki"]
    assert y["luna-river-crossroads"] < y["argynvostholt"] < y["berez"]                     # south of the crossroads
    assert x["wizard-of-wines"] < x["argynvostholt"] and y["krezk"] < y["wizard-of-wines"] < y["yester-hill"]
    assert y["tser-crossroads"] < y["tser-pool"] and y["castle-ravenloft"] < y["barovia"]
    assert y["amber-temple"] > y["tsolenka-pass"] > y["yester-hill"] > y["krezk"]


def test_the_two_crossroads_are_joined_only_by_the_bend_past_the_argynvostholt_fork():
    graph = barovia_map.road_graph()
    luna, raven, fork = (350, 278), (220, 262), (263, 307)
    assert raven not in graph[luna]
    path = barovia_map.route(graph, luna, raven)
    assert fork in path or (242, 225) in path  # by the Old Svalich Road, or the trail by Lake Baratok


def test_the_trail_past_tser_pool_is_drawn_but_never_walked():
    graph = barovia_map.road_graph()
    for line in barovia_map.UNUSED_TRACKS.values():
        inner = line[1:-1]
        assert inner and not any(p in graph for p in inner)
    assert "stroke-dasharray" in barovia_map.draw_base()
    # From the Tser Pool camp to the fork below the falls, the party goes back round by the road.
    path = barovia_map.route(graph, (690, 530), (600, 405))
    assert (680, 555) in path


def test_scale_bar_reads_in_hours_that_fit_the_roads():
    import statistics
    per_hour = [barovia_map.path_length(leg["points"]) / leg["hours"] for leg in real_travel()]
    assert abs(statistics.median(per_hour) - barovia_map.HOUR) <= 4
    svg = barovia_map.draw_base()
    assert "About 5 hours on foot" in svg and "Miles" not in svg


# --- the hand-drawn look: one water network, roads that only cross it, sprites -------------------

def touches(point, line, within=3.0):
    return barovia_map.near_line(point, line, within)


def test_water_is_one_network_like_the_official_and_old_maps():
    lakes, rivers = barovia_map.LAKES, barovia_map.RIVERS

    def ends_somewhere(name, end):
        x, y = end
        return (x <= 2 or x >= barovia_map.W - 2 or y <= 14
                or any(touches(end, shore + shore[:1], 14) or barovia_map.inside(end, shore) for shore in lakes.values())
                or any(touches(end, line) for other, line in rivers.items() if other != name))

    for name, line in rivers.items():
        assert ends_somewhere(name, line[0]) and ends_somewhere(name, line[-1]), name

    # Both sources: Tser Falls is fed by a branch of the Luna River, not a spring, and Tser Pool
    # drains east as the River Ivlis.
    branch = rivers["Tser Falls"]
    assert touches(branch[0], rivers["Luna River"])
    assert touches(branch[-1], rivers["Below the falls"]) or branch[-1] == rivers["Below the falls"][0]
    assert barovia_map.inside(rivers["Below the falls"][-1], lakes["Tser Pool"]) or \
        touches(rivers["Below the falls"][-1], lakes["Tser Pool"] + lakes["Tser Pool"][:1], 14)
    assert touches(rivers["Ivlis River"][0], lakes["Tser Pool"] + lakes["Tser Pool"][:1], 14)
    # Two ponds sit in the hills along the branch, as on both maps.
    assert len([n for n in lakes if n.startswith("Hill pond")]) == 2


def test_roads_and_trails_only_cross_water_never_run_along_it():
    roads = {**barovia_map.ROADS, **barovia_map.TRACKS, **barovia_map.UNUSED_TRACKS}
    for road, line in roads.items():
        for river, water in barovia_map.RIVERS.items():
            close = 0.0
            for a, b in zip(line, line[1:]):
                steps = max(int(math.dist(a, b)), 1)
                for k in range(steps):
                    p = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
                    close += barovia_map.near_line(p, water, 7)
            assert close < 16, f"{road} runs along {river} for about {close:.0f} units"
        for lake, shore in barovia_map.LAKES.items():
            assert not any(barovia_map.inside(p, shore) for p in line), f"{road} goes into {lake or 'a pond'}"


def test_tser_pool_camp_sits_south_of_the_pool_on_dry_land():
    import yaml
    xy = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["places"]["tser-pool"]["xy"]
    pool = barovia_map.LAKES["Tser Pool"]
    assert not barovia_map.inside(tuple(xy), pool)
    assert xy[1] > max(y for _, y in pool)


def test_amber_temple_trail_climbs_into_the_mountains_for_about_an_hour_and_a_half():
    line = barovia_map.TRACKS["Amber Temple trail"]
    hours = barovia_map.path_length(line) / barovia_map.HOUR
    assert 1.2 <= hours <= 2.0
    top = line[-1]
    assert any(math.dist(top, centre) <= radius for centre, radius, _, _ in barovia_map.MOUNTAINS)


def test_sprites_load_with_their_sizes_and_clear_the_woods(tmp_path):
    from PIL import Image
    sprite_dir = tmp_path / "sprites"
    sprite_dir.mkdir()
    Image.new("RGBA", (200, 100)).save(sprite_dir / "keep.webp")
    path = write(tmp_path / "map.yaml", "sprites:\n  # the castle\n  castle: {image: keep, xy: [720, 400], width: 80}\n")
    sprites = barovia_map.load_sprites(path, sprite_dir)
    assert [(s.name, s.image, s.x, s.y, s.width, s.height, s.place) for s in sprites] == [("castle", "keep", 720, 400, 80, 40, "castle")]
    tower = barovia_map.load_sprites(write(tmp_path / "t.yaml", "sprites:\n  w: {image: keep, xy: [1, 2], width: 9, place: tower}\n"
                                           "  b: {image: keep, xy: [1, 2], width: 9, place: null}\n"), sprite_dir)
    assert [s.place for s in tower] == ["tower", None]
    with pytest.raises(ValueError, match="no sprite image"):
        barovia_map.load_sprites(write(tmp_path / "bad.yaml", "sprites:\n  x: {image: nope, xy: [1, 2], width: 9}\n"),
                                 sprite_dir)
    svg = barovia_map.draw_base(sprites)
    assert svg == barovia_map.draw_base(sprites)
    trees = [tuple(map(float, m)) for m in re.findall(r'class="tree" data-xy="([\d.]+),([\d.]+)"', svg)]
    assert trees and not any(math.dist(t, (720, 400)) < 30 for t in trees)


def test_every_real_sprite_has_its_image():
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    names = {s.name for s in sprites}
    assert {"castle-ravenloft", "vallaki", "gates-west", "gates-east", "tser-pool", "amber-temple"} <= names


def test_sprite_editor_rewrites_one_line_and_keeps_comments():
    import map_editor
    text = ("places:\n  vallaki: {xy: [400, 250]}\n\nsprites:\n  # Vallaki, walls and all\n"
            "  vallaki: {image: vallaki, xy: [400, 240], width: 60}\n  castle: {image: c, xy: [1, 2], width: 9}\n")
    out = map_editor.move_sprite(text, "vallaki", (412.46, 236.2), 72.04)
    assert out == text.replace("xy: [400, 240], width: 60", "xy: [412.5, 236.2], width: 72")
    with pytest.raises(KeyError):
        map_editor.move_sprite(text, "nowhere", (1, 2), 3)


def crossings(line, water):
    found = []
    for p1, p2 in zip(line, line[1:]):
        for p3, p4 in zip(water, water[1:]):
            d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
            if not d:
                continue
            t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
            u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
            if 0 <= t <= 1 and 0 <= u <= 1:
                found.append((p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])))
    return found


def test_roads_cross_water_only_where_the_official_map_does():
    # Read off the official map and the old Obsidian Portal map (both agree): the Old Svalich Road
    # bridges the Luna at the Luna River crossroads and the Raven River between the Raven River
    # crossroads and Krezk; the loop road crosses the Tser Falls water at the falls; the road from the
    # village to the River Ivlis crossroads bridges the Ivlis; the road past Tsolenka Pass crosses the
    # Luna where it runs into Luna Lake. The trail past Tser Pool meets the road on the falls bridge.
    rivers = {name: ("Tser Falls" if name == "Below the falls" else name) for name in barovia_map.RIVERS}
    roads = {**barovia_map.ROADS, **barovia_map.TRACKS, **barovia_map.UNUSED_TRACKS}
    found = {}
    for road, line in roads.items():
        for river, water in barovia_map.RIVERS.items():
            for point in crossings(line, water):
                found.setdefault((road, rivers[river]), []).append(point)
    assert set(found) == {
        ("Old Svalich Road (the lake shore)", "Luna River"),
        ("Old Svalich Road (west)", "Raven River"),
        ("The loop past Tser Falls", "Tser Falls"),
        ("Village to the Ivlis crossroads", "Ivlis River"),
        ("Amber Temple road", "Luna River"),
        ("Tser Pool trail (past the pool)", "Tser Falls"),
    }
    # The Luna crossing is at the Luna River crossroads, and every crossing has its bridge.
    luna = found[("Old Svalich Road (the lake shore)", "Luna River")][0]
    assert math.dist(luna, (350, 278)) < 10
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    bridges = [(s.x, s.y) for s in sprites if s.image == "bridge"]
    for (road, river), points in found.items():
        for point in points:
            assert any(math.dist(point, b) < 10 for b in bridges), f"no bridge where {road} crosses {river}"


def test_sprite_cutting_keeps_the_drawing_solid_and_fades_the_edge():
    from PIL import Image, ImageDraw
    import make_sprites
    cell = Image.new("RGB", (120, 120), "white")
    ImageDraw.Draw(cell).rectangle((30, 30, 90, 90), fill=(90, 70, 50))
    sprite = make_sprites.cut(cell)
    alpha = sprite.getchannel("A")
    w, h = sprite.size
    assert alpha.getpixel((0, 0)) == 0 and alpha.getpixel((w // 2, h // 2)) == 255
    edge = [alpha.getpixel((x, h // 2)) for x in range(w // 2)]
    assert any(0 < a < 255 for a in edge) or edge.count(0) > 1   # a dithered edge, not a hard cut
    assert set(make_sprites.SHEETS) == {p.name for p in (ROOT / "tools" / "sprite_sheets").iterdir()}


def test_werewolf_den_sits_west_of_lake_baratok_and_the_lake_is_named_on_the_water():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, parent = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    den, lake = places["lake-baratok-cave"], barovia_map.LAKES["Lake Baratok"]
    assert den.title == "Werewolf Den" and den.x < min(x for x, _ in lake) and parent["lake-baratok-cave"] == "lake-baratok-cave"
    assert barovia_map.inside(places["lake-baratok"].label_xy, lake)
    # The den's sessions stop at the den, not at the lake.
    visits = barovia_map.load_visits(ROOT / "data" / "trail.yaml", places,
                                     barovia_map.load_spots(ROOT / "data" / "map.yaml", places))
    assert visits["2025-05-06-echoes-of-the-black-terro"] == ["lake-baratok-cave"]


def test_a_place_can_put_its_label_at_a_given_spot(tmp_path):
    path = write(tmp_path / "map.yaml", "places:\n  vallaki: {xy: [400, 270], label_at: [410, 240]}\n")
    places, _ = barovia_map.load_places(path, PAGES)
    assert places["vallaki"].label_xy == (410, 240) and places["vallaki"].text_anchor == "middle"


def test_every_real_sprite_links_to_a_real_place_or_none():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    assert all(s.place in places for s in sprites if s.place)
    assert {s.name for s in sprites if s.place is None} == {s.name for s in sprites if s.image == "bridge"}


def test_every_crossroads_with_a_wiki_page_has_a_signpost():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    crossroads = {slug for slug in places if "crossroads" in slug}
    assert crossroads == {s.place for s in sprites if s.image == "signpost"}
    for s in sprites:
        if s.image == "signpost":
            assert math.dist((s.x, s.y), (places[s.place].x, places[s.place].y)) < 25


def test_west_and_east_gates_are_separate_places():
    # Chris: the gates near Castle Ravenloft and the gates the party walked through after Durst Manor
    # are different places, each with its own wiki page, pin and picture.
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    sprites = {s.name: s for s in barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")}
    assert sprites["gates-east"].place == "gates-of-barovia" and sprites["gates-west"].place == "west-gates-of-barovia"
    assert places["west-gates-of-barovia"].x < places["castle-ravenloft"].x < places["gates-of-barovia"].x
    east = (ROOT / "content" / "wiki" / "gates-of-barovia.md").read_text(encoding="utf-8")
    west = (ROOT / "content" / "wiki" / "west-gates-of-barovia.md").read_text(encoding="utf-8")
    assert "black carriage" in west and "black carriage" not in east
    assert "barovia-barovia" in east
    # The map no longer paints a bare "Gates of Barovia" name by the west gates; the pin's label names them.
    assert "Gates of Barovia" not in [name for name, *_ in barovia_map.LABELS]


def test_session_numbers_count_every_session_even_off_the_map(tmp_path, places):
    by_slug, parent = places
    posts = []
    for stem, title in [("2024-01-01-a", "A"), ("2024-01-08-b", "B"), ("2024-01-15-c", "C")]:
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {title}\ndate: '{stem[:10]}'\n---\n\nKrezk.\n"))
        post.html = build.render_markdown(post.body_md)
        posts.append(post)
    visits = barovia_map.load_visits(write(tmp_path / "trail.yaml", "sessions:\n  2024-01-08-b: []\n"), by_slug)
    legs = barovia_map.trail(posts, by_slug, parent, PAGES, visits)
    # B is nowhere on the map, but keeps its number so the map and the wiki citations agree.
    assert [(leg["post"].title, leg["n"]) for leg in legs] == [("A", 1), ("C", 3)]
    build.number_sessions(posts)
    assert [p.number for p in posts] == [1, 2, 3]


SPOT_MAP = MAP + """spots:
  tser-falls-bridge: {xy: [600, 405], label: Tser Falls bridge}
  the-oak: {xy: [745, 520], label: the old oak, offroad: true}
"""


def spot_posts(tmp_path, stems):
    posts = []
    for stem in stems:
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {stem}\ndate: '{stem[:10]}'\n---\n\nx\n"))
        post.html = "<p>x</p>"
        posts.append(post)
    return posts


def test_a_session_marker_can_sit_where_the_main_action_was(tmp_path):
    # Chris: the number goes where the session's main action happened, so the trail of numbers
    # shows the journey instead of always the start or end. A spot is a point on the roads (or off
    # them) with no wiki page: it routes the trail and can carry the marker, but gets no pin or card.
    path = write(tmp_path / "map.yaml", SPOT_MAP)
    places, parent = barovia_map.load_places(path, PAGES)
    spots = barovia_map.load_spots(path, places)
    assert set(spots) == {"tser-falls-bridge", "the-oak"} and spots["the-oak"].offroad
    visits = barovia_map.load_visits(write(tmp_path / "trail.yaml", """sessions:
  2024-01-01-a: [barovia]
  2024-01-08-b: {stops: [barovia, tser-falls-bridge, vallaki], marker: tser-falls-bridge}
  2024-01-15-c: {stops: [vallaki, krezk], marker: vallaki}
  2024-01-22-d: [krezk, the-oak]
"""), places, spots)
    assert visits["2024-01-01-a"] == ["barovia"] and visits["2024-01-01-a"].marker is None
    legs = barovia_map.trail(spot_posts(tmp_path, ["2024-01-01-a", "2024-01-08-b", "2024-01-15-c", "2024-01-22-d"]),
                             places, parent, PAGES, visits, spots)
    a, b, c, d = legs
    # Listed stops (post pages, the map's session list, place cards) are real places only.
    assert b["stops"] == ["barovia", "vallaki"] and d["stops"] == ["krezk"]
    assert [p.title for p in places["vallaki"].sessions] == ["2024-01-15-c", "2024-01-08-b"]
    # The trail runs through the spot: the bridge is on B's road path.
    assert any((600, 405) in seg["points"] for seg in b["segments"])
    # B's number sits by the bridge, C's by Vallaki where it started, D's at the oak, off the road.
    assert math.dist(b["marker"], (600, 405)) < 20
    assert math.dist(c["marker"], (400, 270)) < 20
    assert math.dist(d["marker"], (745, 520)) < 20 and d["segments"][-1]["road"] is False
    # A has no marker key, so it keeps the default: where the session ended.
    assert math.dist(a["marker"], (780, 450)) < 20


def test_trail_entries_are_checked(tmp_path):
    path = write(tmp_path / "map.yaml", SPOT_MAP)
    places, _ = barovia_map.load_places(path, PAGES)
    spots = barovia_map.load_spots(path, places)
    with pytest.raises(ValueError, match="marker"):
        barovia_map.load_visits(write(tmp_path / "t1.yaml", "sessions:\n  x: {stops: [barovia], marker: vallaki}\n"), places, spots)
    with pytest.raises(ValueError, match="atlantis"):
        barovia_map.load_visits(write(tmp_path / "t2.yaml", "sessions:\n  x: {stops: [barovia, atlantis]}\n"), places, spots)
    with pytest.raises(ValueError, match="vallaki"):
        barovia_map.load_spots(write(tmp_path / "m2.yaml", MAP + "spots:\n  vallaki: {xy: [1, 1]}\n"), places)


def test_every_real_spot_sits_on_a_road_unless_offroad():
    import yaml
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    graph = barovia_map.road_graph()
    for slug, spot in (data.get("spots") or {}).items():
        assert spot.get("label"), slug
        if spot.get("offroad"):
            assert barovia_map.nearest_vertex(graph, *spot["xy"]) is None, slug
        else:
            assert tuple(spot["xy"]) in graph, slug


def real_legs():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, parent = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    spots = barovia_map.load_spots(ROOT / "data" / "map.yaml", places)
    visits = barovia_map.load_visits(ROOT / "data" / "trail.yaml", places, spots)
    posts = [build.parse_post(f) for f in sorted((ROOT / "content" / "posts").glob("*.md"))]
    for post in posts:
        post.html = ""
    legs = barovia_map.trail(posts, places, parent, pages, visits, spots)
    return {leg["post"].slug: leg for leg in legs}, places, spots


def test_dream_pies_number_sits_at_tser_falls_bridge_and_skips_the_windmill():
    legs, places, spots = real_legs()
    leg = legs["dream-pies"]
    bridge = spots["tser-falls-bridge"]
    assert math.dist(leg["marker"], (bridge.x, bridge.y)) < 20
    assert "the-windmill" not in leg["stops"]
    assert "dream-pies" not in [p.slug for p in places["the-windmill"].sessions]
    # The trail passes the turnoff but never walks the lane down to the windmill.
    windmill = (places["the-windmill"].x, places["the-windmill"].y)
    assert all(windmill not in seg["points"] for seg in leg["segments"])


def test_heart_stone_number_sits_in_vallaki():
    legs, places, _ = real_legs()
    leg = legs["the-hunt-for-the-heart-stone"]
    assert math.dist(leg["marker"], (places["vallaki"].x, places["vallaki"].y)) < 35
    assert leg["stops"] == ["vallaki"]


@pytest.mark.parametrize("slug, at", [
    # Chris's picks (2026-11-01): each number sits where the session's main action happened.
    ("leaving-village-barovia", "the-old-oak"),          # the fight at the ancient oak
    ("skeletal-rider", "tser-pool-road"),                # the toll-men by the road
    ("looking-for-zoldars-tower", "luna-river-crossroads"),  # scarecrows and twig blights
    ("finishing-up-at-the-vineyard", "yester-hill-trail"),   # Kavan, and Strahd rides up
    ("blood-and-oaths-under-moonligh", "lake-baratok-cave"), # the shrine and the oath
    ("the-oath-the-spy-and-the-silver-moon", "west-gates-of-barovia"),  # the black carriage
    ("the-shard-s-warning-and-the-abbot-s-madness", "vallaki-east-road"),  # the roadside ambush
])
def test_picked_numbers_sit_at_the_main_action(slug, at):
    legs, places, spots = real_legs()
    spot = places.get(at) or spots[at]
    assert math.dist(legs[slug]["marker"], (spot.x, spot.y)) < 25


def test_the_oath_session_stops_at_the_west_gates_and_the_carriage_brings_the_next_one_in():
    legs, _, _ = real_legs()
    assert legs["the-oath-the-spy-and-the-silver-moon"]["stops"][-1] == "west-gates-of-barovia"
    assert legs["velvet-vintages-and-veiled-intentions"]["segments"]  # the carriage ride to the castle


def test_every_spot_is_used_by_some_session():
    import yaml
    spots = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["spots"]
    sessions = yaml.safe_load((ROOT / "data" / "trail.yaml").read_text(encoding="utf-8"))["sessions"]
    used = {s for e in sessions.values() for s in (e["stops"] if isinstance(e, dict) else e or [])}
    assert set(spots) <= used


WAYS = {"three": 3, "four": 4, "five": 5, "six": 6}


def test_a_crossroads_page_names_as_many_ways_as_the_map_draws():
    # Chris, 2026-11-01: the Luna River crossroads page said "five-way" but the map drew four
    # roads. The party's own log calls it "a four-way crossroads" (Act 3: The Broken Land).
    pages = {p.slug: p for p in wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)}
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", list(pages.values()))
    graph = barovia_map.road_graph()
    checked = 0
    for slug, place in places.items():
        text = (ROOT / "content" / "wiki" / f"{slug}.md").read_text(encoding="utf-8").lower()
        for word in re.findall(r"\b(three|four|five|six)-way\b", text):
            assert len(graph[(place.x, place.y)]) == WAYS[word], (slug, word)
            checked += 1
    assert checked


def test_vallaki_vistani_camp_sits_south_of_vallaki_toward_the_luna():
    # "A doll for Arabelle": Alexi begs for help finding Arabelle at the Vistani encampment, and
    # Yann's head lay "toward the Luna River". Chris remembers the camp south of Vallaki.
    import yaml
    places = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["places"]
    camp, vallaki = places["vallaki-vistani-camp"]["xy"], places["vallaki"]["xy"]
    assert camp[1] > vallaki[1] + 20 and abs(camp[0] - vallaki[0]) < 40
    luna = barovia_map.RIVERS["Luna River"]
    near = min(math.dist(camp, (a[0] + (b[0] - a[0]) * t / 20, a[1] + (b[1] - a[1]) * t / 20))
               for a, b in zip(luna, luna[1:]) for t in range(21))
    assert near < 30
    path = barovia_map.route(barovia_map.road_graph(), tuple(vallaki), tuple(camp))
    assert path and len(path) < 6   # a short walk from town


def test_the_lost_girl_session_visits_the_vallaki_vistani_camp():
    import yaml
    trail = yaml.safe_load((ROOT / "data" / "trail.yaml").read_text(encoding="utf-8"))["sessions"]
    entry = trail["2024-08-13-a-doll-for-arabelle"]
    assert "vallaki-vistani-camp" in entry["stops"]
    assert entry["marker"] == "vallaki-vistani-camp"


def test_the_road_to_old_bonegrinder_winds_like_the_official_map():
    # Chris, 2026-11-02: on the official map the Old Svalich Road zig-zags down switchbacks from the
    # Tser Pool crossroads to the Old Bonegrinder turnoff, then swings in a wide loop north-east
    # to a hairpin before it runs back west along the lake to Vallaki. Ours was nearly straight.
    graph = barovia_map.road_graph()
    crossroads, fork, east_of_vallaki = (610, 360), (487, 319), (442, 259)

    def length(path):
        return sum(math.dist(a, b) for a, b in zip(path, path[1:]))

    down = barovia_map.route(graph, crossroads, fork)
    assert length(down) > 1.4 * math.dist(crossroads, fork)
    # the switchbacks: the road turns back on itself (heads east again) at least twice going down
    turns = sum(1 for a, b, c in zip(down, down[1:], down[2:]) if (b[0] - a[0]) * (c[0] - b[0]) < 0)
    assert turns >= 2

    loop = barovia_map.route(graph, fork, east_of_vallaki)
    assert length(loop) > 2.5 * math.dist(fork, east_of_vallaki)
    assert max(x for x, _ in loop) > fork[0] + 60     # the hairpin is well east of the turnoff
    assert min(y for _, y in loop) < east_of_vallaki[1] - 15   # and north, toward the lake


def test_the_bonegrinder_turnoff_is_at_the_foot_of_the_switchbacks():
    # Chris, 2026-11-02: the turnoff was too far north. On the official map the lane to Old
    # Bonegrinder leaves the road at the bottom of the last bend, and the windmill sits west of it.
    import yaml
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    fork, mill = data["spots"]["bonegrinder-fork"]["xy"], data["places"]["the-windmill"]["xy"]
    graph = barovia_map.road_graph()
    assert tuple(fork) in graph[tuple(mill)]
    lowest_bend = max(y for x, y in barovia_map.ROADS["Old Svalich Road (the switchbacks)"] if x < 520)
    assert fork[1] > 315 and lowest_bend - fork[1] < 25
    assert mill[0] < fork[0] - 10 and abs(mill[1] - fork[1]) < 10


def test_east_roads_bend_like_the_official_map():
    # Chris, 2026-11-02: retrace the roads from the official map, region by region; the east first.
    graph = barovia_map.road_graph()
    gates, village, ivlis, falls, tser, castle = (930, 398), (780, 450), (680, 555), (600, 405), (610, 360), (720, 398)
    # From the gates the road drops south, then runs straight west into the village.
    down = barovia_map.route(graph, gates, village)
    assert any(x > 860 and y >= 448 for x, y in down)
    # From the village it heads south past the Ivlis before it turns west to the crossroads.
    south = barovia_map.route(graph, village, ivlis)
    assert any(x > 755 and y > 520 for x, y in south)
    # The road past Tser Falls swings south of the crossroads and loops far west before the falls.
    loop = barovia_map.route(graph, ivlis, falls)
    assert max(y for _, y in loop) > ivlis[1] + 8 and min(x for x, _ in loop) < 540
    # The castle road climbs north over a rise before it comes down to the castle gate.
    up = barovia_map.route(graph, tser, castle)
    assert min(y for _, y in up) < 350


def test_roads_west_of_vallaki_bend_like_the_official_map():
    # Region 2 of the retrace (Chris, 2026-11-02): around the Luna River crossroads.
    graph = barovia_map.road_graph()
    luna, fork, raven, argyn, baratok = (350, 278), (263, 307), (220, 262), (316, 384), (242, 225)
    # From the Luna crossroads the Old Svalich Road sags south through the woods to the fork.
    sag = barovia_map.route(graph, luna, fork)
    assert max(y for _, y in sag) > 315
    # The Argynvostholt road drops south, runs east along the valley, then turns down to the gate.
    valley = barovia_map.route(graph, fork, argyn)
    assert any(x > 300 and y < 345 for x, y in valley)
    # The Lake Baratok trail heads north from the crossroads, then arcs west along the lake.
    arc = barovia_map.route(graph, luna, baratok)
    assert min(y for _, y in arc) < 223 and any(x > 335 and y < 255 for x, y in arc)


def test_south_roads_bend_like_the_official_map():
    # Region 4 of the retrace (Chris, 2026-11-02): the long road south to Tsolenka Pass and on.
    graph = barovia_map.road_graph()
    raven, tsolenka, amber_fork = (220, 262), (240, 578), (352, 672)
    south = barovia_map.route(graph, raven, tsolenka)
    # it swings well west into the hills, doubles back on a hairpin, and winds down to the pass
    assert min(x for x, _ in south) < 140
    turns = sum(1 for a, b, c in zip(south, south[1:], south[2:]) if (b[0] - a[0]) * (c[0] - b[0]) < 0)
    assert turns >= 3
    # past the pass it climbs east, then down a long bend to the fork below the Amber Temple
    on = barovia_map.route(graph, tsolenka, amber_fork)
    assert sum(math.dist(a, b) for a, b in zip(on, on[1:])) > 1.05 * math.dist(tsolenka, amber_fork)


def test_argynvostholt_stands_clear_of_the_berez_trail():
    # Chris, 2026-11-02: Argynvostholt sat too close to the trail down to Berez. On the official map
    # the trail runs well east of the mansion, between it and the Luna.
    import yaml
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    mansion = data["places"]["argynvostholt"]["xy"]
    sprite = data["sprites"]["argynvostholt"]
    trail = barovia_map.TRACKS["Berez trail"]
    gap = min(_seg_distance(mansion, a, b) for a, b in zip(trail, trail[1:]))
    assert gap >= 28
    edge = sprite["xy"][0] + sprite["width"] / 2
    assert min(x for x, y in trail if abs(y - sprite["xy"][1]) < 30) - edge >= 8


def _seg_distance(p, a, b):
    ax, ay = a
    bx, by = b
    t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
    return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


def test_leaving_barovia_follows_the_ivlis_north_bank_to_the_old_oak():
    # Session 8: "leave the path and enter the woods to follow the river towards the pool". Chris:
    # "we hit the river from Barovia before the bridge, not after." So the trail leaves the road
    # just north of the Ivlis bridge and keeps to the north bank; it never crosses the river.
    import yaml
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    places = {**data["places"], **data["spots"]}
    oak, village = tuple(places["the-old-oak"]["xy"]), tuple(places["barovia"]["xy"])
    assert not places["the-old-oak"].get("offroad")
    path = barovia_map.route(barovia_map.road_graph(), village, oak)
    assert path and path[-1] == oak
    river = barovia_map.RIVERS["Ivlis River"]

    def river_y(x):
        for (ax, ay), (bx, by) in zip(river, river[1:]):
            if ax <= x <= bx:
                return ay + (by - ay) * (x - ax) / (bx - ax)
        return math.inf

    assert all(y < river_y(x) for x, y in path), "the walk to the oak crosses the Ivlis"
    assert barovia_map.path_length(path) / barovia_map.HOUR < 3   # no detour round by the bridge


def test_vallaki_vistani_camp_has_a_picture_and_its_label_beside_it():
    # Chris: "Vistani camp has no sprite and the label is very far south." The camp reuses the
    # wagon-ring drawing from the Tser Pool camp, and its label sits right next to the picture.
    import yaml
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    camp_sprite = [s for s in sprites if s.place == "vallaki-vistani-camp"]
    assert len(camp_sprite) == 1 and camp_sprite[0].image == "tser-pool"
    camp = data["places"]["vallaki-vistani-camp"]
    sprite = camp_sprite[0]
    assert math.dist((sprite.x, sprite.y), camp["xy"]) < 8
    place = barovia_map.Place("vallaki-vistani-camp", "Vistani Camp", *camp["xy"], [],
                              camp.get("anchor", "middle"),
                              label_at=tuple(camp["label_at"]) if camp.get("label_at") else None)
    lx, ly = place.label_xy
    # beside the picture: just past its edge, not a long way south of it
    assert abs(ly - sprite.y) <= sprite.height / 2 + 12
    assert abs(lx - sprite.x) <= sprite.width / 2 + 45   # the label is centred, about 70 wide
