"""Link previews: Open Graph and Twitter card tags, with a snippet and a 1200x630 picture per page."""
import html as htmllib
import re
from pathlib import Path

import pytest
from PIL import Image

import build
import share


def write_post(folder: Path, name: str, front: str, body: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


def meta(page_html: str) -> dict[str, str]:
    """{property or name: content} for every <meta> tag with content."""
    tags = {}
    for tag in re.findall(r"<meta\s[^>]*>", page_html):
        key = re.search(r'(?:property|name)="([^"]+)"', tag)
        value = re.search(r'content="([^"]*)"', tag)
        if key and value:
            tags[key.group(1)] = htmllib.unescape(value.group(1))
    return tags


def local(out: Path, url: str, site: str) -> Path:
    assert url.startswith(site + "/"), url
    return out / url[len(site) + 1:]


# --- snippets -------------------------------------------------------------------------------

def test_snippet_keeps_short_text_and_cuts_long_text_at_a_word():
    assert share.snippet("  A  short\nline. ") == "A short line."
    long = "word " * 80
    cut = share.snippet(long, limit=50)
    assert len(cut) <= 50 and cut.endswith("…") and not cut.endswith(" …")


def test_wiki_snippet_adds_the_first_prose_paragraph_without_citations_or_captions():
    html = ('<h2>Description</h2>\n<p><img alt="x" src="/images/x.jpg"></p>\n<p><em>AI-generated image. Not official art.</em></p>\n'
            '<p>Ismark\'s sister. Strahd has bitten her (<a href="/posts/a/">Barovia, Barovia</a>, '
            '<a href="/posts/b/">Leaving</a>). She is brave (<a href="/posts/c/">3</a>, 3 June 2025).</p>\n<p>Second paragraph.</p>')
    text = share.wiki_snippet("Ismark's adopted sister.", html)
    assert text.startswith("Ismark's adopted sister. Ismark's sister. Strahd has bitten her. She is brave.")
    assert "Barovia, Barovia" not in text and "AI-generated" not in text and "(" not in text
    assert share.wiki_snippet("", "<p>Only text.</p>") == "Only text."
    log = ('<h2>From the adventure log</h2>\n<p><em>Compiled from the session posts.</em></p>\n<ul>\n'
           '<li>Harvests wolfsbane to ease Dmitri\'s curse. (<a href="/posts/k/">Welcome to Krezk</a>)</li>\n'
           '<li>The Abbot wants her heart. (<a href="/posts/k/">Welcome to Krezk</a>)</li>\n</ul>')
    assert share.wiki_snippet("Dmitri's wife.", log) == (
        "Dmitri's wife. Harvests wolfsbane to ease Dmitri's curse. The Abbot wants her heart.")
    assert len(share.wiki_snippet("S.", "<p>" + "long words " * 60 + "</p>")) <= share.LIMIT


def test_post_snippet_tells_the_story_after_the_tagline():
    html = ("<ul><li><strong>Glance:</strong> a list</li></ul>\n<p>Note: Written from the session notes.</p>\n"
            "<p>- Liren: Dragonborn Barbarian - Gumbo: Half-orc Rogue</p>\n<p><em>AI-generated image.</em></p>\n"
            "<p>Strahd answered cryptically:</p>\n<blockquote><p>&ldquo;Perhaps.&rdquo;</p></blockquote>\n"
            "<p>We left.</p>")
    assert share.post_snippet("", html) == "Strahd answered cryptically: “Perhaps.” We left."
    assert share.post_snippet("Red Herring?", "<p>We rode out.</p>") == "Red Herring? We rode out."
    assert share.post_snippet("*Only welcome if you pay", "<p>We paid.</p>") == "Only welcome if you pay. We paid."
    assert share.post_snippet("Wolves love them", "") == "Wolves love them"
    old_style = ('<aside class="margin-note"><p>Written from the session notes.</p></aside>\n'
                 '<aside class="callout glance"><h2>At a Glance:</h2><ul><li>x</li></ul></aside>\n'
                 '<p><strong>Chronicle of the Larder</strong></p>\n'
                 '<p><strong>Chronicle</strong><br>\nShadows of the Larder: The Drowning Cells</p>\n'
                 '<p><strong>Characters:</strong><br>\n- Oogway<br>\n- Olfin<br>\n- Liren</p>\n'
                 '<p><strong>Summary:</strong><br>\nWe found a chest: - 20 bolts - a scroll</p>\n'
                 '<p class="ai-credit">AI-generated image.</p>\n'
                 '<p><strong>Healing Gumbo</strong><br>\nAfter the battle we checked one another over.</p>')
    assert share.post_snippet("", old_style) == "After the battle we checked one another over."


def test_long_snippets_end_at_a_sentence_when_one_ends_late_enough():
    text = share.snippet("A" * 150 + ". " + "word " * 40)
    assert text == "A" * 150 + "."
    short_first = share.snippet("Hi. " + "word " * 60)
    assert short_first.endswith("…") and len(short_first) > 100


def test_first_picture_prefers_a_local_file_then_an_outside_link(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (10, 10)).save(tmp_path / "images" / "here.jpg")
    md = ("![Gone](/images/gone.jpg)\n![Far](https://elsewhere.example/a.jpg)\n"
          "![Ireena with two swords](/images/here.jpg)\n")
    assert share.first_picture(md, tmp_path) == (tmp_path / "images" / "here.jpg", "Ireena with two swords")
    assert share.first_picture("![Victor](https://old.example/v.png)", tmp_path) == ("https://old.example/v.png", "Victor")
    assert share.first_picture("No pictures.", tmp_path) is None
    (tmp_path / "icon.svg").write_text("<svg/>", encoding="utf-8")
    assert share.first_picture("![Icon](/icon.svg)", tmp_path) is None  # no card can be made from it


def test_cards_are_made_once_and_reused_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(share, "CACHE", tmp_path / "cache")
    src = tmp_path / "pic.png"
    Image.new("RGB", (50, 50), "red").save(src)
    made = []
    real = share.make_card
    monkeypatch.setattr(share, "make_card", lambda s, d: (made.append(s), real(s, d)))
    first = share.card("x", src, tmp_path / "out1")
    second = share.card("x", src, tmp_path / "out2")
    assert first == second and len(made) == 1
    assert (tmp_path / "out1" / first).is_file() and (tmp_path / "out2" / second).is_file()


def test_file_names_are_not_alt_text():
    assert share.alt_text("IMG_1002.jpeg", "Session Zero") == "Session Zero"
    assert share.alt_text("", "Session Zero") == "Session Zero"
    assert share.alt_text("Ismark in a cloak", "Barovia") == "Ismark in a cloak"


# --- card pictures --------------------------------------------------------------------------

@pytest.mark.parametrize("size", [(400, 900), (1600, 500), (300, 300)])
def test_card_is_1200_by_630_and_shows_the_whole_picture(tmp_path, size):
    src = tmp_path / "pic.png"
    Image.new("RGB", size, (200, 30, 30)).save(src)
    dest = tmp_path / "out" / "card.jpg"
    share.make_card(src, dest)
    with Image.open(dest) as card:
        assert card.format == "JPEG" and card.size == (share.CARD_W, share.CARD_H)
        r, g, b = card.convert("RGB").getpixel((share.CARD_W // 2, share.CARD_H // 2))
        assert r > 180 and g < 60  # the picture itself, untouched, in the middle
        er, eg, eb = card.convert("RGB").getpixel((2, 2))
        assert er < r  # a darkened, blurred fill behind it, never stretched picture
    assert dest.stat().st_size < 400_000


def test_see_through_pictures_sit_on_the_site_background(tmp_path):
    src = tmp_path / "cutout.png"
    Image.new("RGBA", (300, 600), (255, 255, 255, 0)).save(src)
    share.make_card(src, tmp_path / "card.jpg")
    with Image.open(tmp_path / "card.jpg") as card:
        assert max(card.getpixel((share.CARD_W // 2, share.CARD_H // 2))) < 40  # dark, not white or grey


def test_card_name_changes_when_the_picture_changes(tmp_path):
    src = tmp_path / "pic.png"
    Image.new("RGB", (50, 50), "red").save(src)
    first = share.card_name("wiki-aera", src)
    Image.new("RGB", (50, 50), "blue").save(src)
    assert share.card_name("wiki-aera", src) != first and first.startswith("images/share/wiki-aera-")


# --- the built site -------------------------------------------------------------------------

SITE = "https://log.example"


@pytest.fixture
def site(tmp_path):
    posts = tmp_path / "content" / "posts"
    write_post(posts, "2024-01-09-first.md", "title: First Night\ndate: '2024-01-09T21:00:00-06:00'\nslug: first\n",
               "## Summary:\n\nWe walked into the mist, and the \"gates\" closed behind us.\n\n"
               "![Ireena with a sword in each hand](/images/ireena.jpg)\n")
    write_post(posts, "2024-02-13-second.md",
               "title: 'Second: Wolves'\ndate: '2024-02-13T21:00:00-06:00'\ntagline: Wolves love them\n",
               "Nothing drawn.\n")
    write_post(posts, "2024-03-01-old-art.md", "title: Old Art\ndate: '2024-03-01T21:00:00-06:00'\n",
               "We met Victor.\n\n![Portrait of Victor](https://old.example/Victor%20V.png)\n")
    wiki_dir = tmp_path / "content" / "wiki"
    wiki_dir.mkdir(parents=True)
    (wiki_dir / "ireena.md").write_text(
        "---\ntitle: Ireena\ntype: npc\nsummary: Ismark's adopted sister.\n---\n\n## Description\n\n"
        "![Ireena, red-haired](/images/ireena.jpg)\n\nShe found us ([First Night](/posts/first/)).\n", encoding="utf-8")
    (wiki_dir / "grom.md").write_text("---\ntitle: Grom\ntype: character\n---\n\nNo art yet.\n", encoding="utf-8")
    static = tmp_path / "static"
    (static / "images").mkdir(parents=True)
    Image.new("RGB", (600, 900), "red").save(static / "images" / "ireena.jpg")
    out = tmp_path / "public"
    build.build(posts, out, site_url=SITE, wiki_dir=wiki_dir, slides_static=static)
    return out


def test_post_shares_its_title_snippet_feature_picture_and_date(site):
    tags = meta((site / "posts" / "first" / "index.html").read_text(encoding="utf-8"))
    assert tags["og:title"] == tags["twitter:title"] == "First Night"
    assert tags["og:description"] == tags["twitter:description"] == tags["description"]
    assert tags["og:description"].startswith('We walked into the mist, and the “gates” closed')
    assert tags["og:type"] == "article" and tags["article:published_time"].startswith("2024-01-09")
    assert tags["og:url"] == f"{SITE}/posts/first/"
    assert tags["og:site_name"] == build.SITE_TITLE
    assert tags["twitter:card"] == "summary_large_image"
    assert tags["og:image"] == tags["twitter:image"] and "/images/share/post-first-" in tags["og:image"]
    assert tags["og:image:alt"] == tags["twitter:image:alt"] == "Ireena with a sword in each hand"
    assert (tags["og:image:width"], tags["og:image:height"]) == ("1200", "630")
    with Image.open(local(site, tags["og:image"], SITE)) as card:
        assert card.size == (1200, 630)
    page = (site / "posts" / "first" / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{SITE}/posts/first/">' in page


def test_post_tagline_is_its_snippet_and_a_post_without_a_picture_uses_the_site_card(site):
    tags = meta((site / "posts" / "second" / "index.html").read_text(encoding="utf-8"))
    assert tags["og:description"] == "Wolves love them. Nothing drawn."
    assert "/images/share/site-" in tags["og:image"] and tags["og:image:alt"] == share.DEFAULT_ALT
    assert local(site, tags["og:image"], SITE).is_file()


def test_wiki_page_shares_summary_paragraph_and_first_picture(site):
    tags = meta((site / "wiki" / "ireena" / "index.html").read_text(encoding="utf-8"))
    assert tags["og:title"] == "Ireena" and tags["og:type"] == "website"
    assert tags["og:description"] == "Ismark's adopted sister. She found us."
    assert "/images/share/wiki-ireena-" in tags["og:image"] and tags["og:image:alt"] == "Ireena, red-haired"
    assert local(site, tags["og:image"], SITE).is_file()
    grom = meta((site / "wiki" / "grom" / "index.html").read_text(encoding="utf-8"))
    assert grom["og:description"] == "No art yet." and "/images/share/site-" in grom["og:image"]


def test_post_whose_picture_lives_elsewhere_shares_that_address(site):
    tags = meta((site / "posts" / "old-art" / "index.html").read_text(encoding="utf-8"))
    assert tags["og:image"] == tags["twitter:image"] == "https://old.example/Victor%20V.png"
    assert tags["og:image:alt"] == "Portrait of Victor"
    assert "og:image:width" not in tags and "og:image:type" not in tags


@pytest.mark.parametrize("path, title", [("index.html", build.SITE_TITLE), ("wiki/index.html", "Wiki"),
                                         ("search/index.html", "Search")])
def test_list_pages_share_the_site_card(site, path, title):
    tags = meta((site / path).read_text(encoding="utf-8"))
    assert tags["og:title"].startswith(title) and tags["og:description"]
    assert "/images/share/site-" in tags["og:image"] and tags["twitter:card"] == "summary_large_image"
    assert tags["og:url"] == f"{SITE}/{path.removesuffix('index.html')}"


# --- the real blog ----------------------------------------------------------------------------

@pytest.fixture
def real_site(real_build):
    return real_build.out


def real_pages(out: Path) -> list[Path]:
    """Post and wiki pages, not the forwarding pages left at old addresses."""
    return sorted(p for p in [*(out / "posts").glob("*/index.html"), *(out / "wiki").glob("*/index.html")]
                  if 'http-equiv="refresh"' not in p.read_text(encoding="utf-8"))


def test_every_real_post_and_wiki_page_has_a_good_preview(real_site):
    problems = []
    for path in real_pages(real_site):
        name = path.parent.relative_to(real_site).as_posix()
        tags = meta(path.read_text(encoding="utf-8"))
        text = tags.get("og:description", "")
        if not 20 <= len(text) <= share.LIMIT:
            problems.append(f"{name}: snippet length {len(text)}: {text!r}")
        if re.search(r"[<>\[\]*]|\]\(|\(\s*\)|^- | - \w+:|^Note:|[:;,]$", text):
            problems.append(f"{name}: markup left in snippet: {text!r}")
        image = tags.get("og:image", "")
        if image.startswith("https://publish-01.obsidian.md/"):  # two 2024 posts show the old blog's art
            pass
        elif not image.startswith("https://owlbear.dicelore.quest/images/share/") or not local(
                real_site, image, "https://owlbear.dicelore.quest").is_file():
            problems.append(f"{name}: no card picture: {image}")
        if not tags.get("og:image:alt"):
            problems.append(f"{name}: picture has no alt text")
    assert not problems, problems


def test_every_real_post_shares_its_own_feature_picture(real_site):
    generic = [p.parent.name for p in real_pages(real_site) if p.parent.parent.name == "posts"
               if "/images/share/site-" in meta(p.read_text(encoding="utf-8"))["og:image"]]
    assert not generic, generic


def test_real_cards_stay_small(real_site):
    big = [p.name for p in (real_site / "images" / "share").glob("*.jpg") if p.stat().st_size > 400_000]
    assert not big, big
