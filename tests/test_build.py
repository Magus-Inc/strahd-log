import json
import re
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import build

ATOM = "{http://www.w3.org/2005/Atom}"


def write_post(folder: Path, name: str, front: str, body: str = "Body.\n") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


@pytest.fixture
def content(tmp_path):
    folder = tmp_path / "content"
    write_post(folder, "2024-01-09-first.md",
               "title: First Night\ndate: '2024-01-09T21:00:00-06:00'\nslug: first\ntags: [Barovia]\n",
               "## Arrival\n\n* **Mist:** thick\n\n> A quote\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
               "![Icon](/favicon.svg)\n")
    write_post(folder, "2024-02-13-second.md",
               "title: 'Second: Wolves'\ndate: '2024-02-13T21:00:00-06:00'\ntagline: Wolves love them\n"
               "tags: [Barovia, Wolves]\n")
    write_post(folder, "2026-09-01-third.md", "title: Third & Last\ndate: '2026-09-01T17:00:00-05:00'\n")
    return folder


def test_split_front_matter():
    meta, body = build.split_front_matter("---\ntitle: 'A: B'\ntags: [x]\n---\n\nHello\n")
    assert meta == {"title": "A: B", "tags": ["x"]}
    assert body.strip() == "Hello"
    assert build.split_front_matter("No front matter") == ({}, "No front matter")


def test_parse_post_reads_fields_and_defaults_slug(content):
    post = build.parse_post(content / "2026-09-01-third.md")
    assert post.slug == "third"  # from the file name
    assert post.date == datetime.fromisoformat("2026-09-01T17:00:00-05:00")
    assert post.tags == [] and post.tagline == ""


def test_parse_post_requires_title(tmp_path):
    write_post(tmp_path, "2024-01-01-x.md", "date: '2024-01-01'\n")
    with pytest.raises(ValueError, match="title"):
        build.parse_post(tmp_path / "2024-01-01-x.md")


def test_build_writes_pages_feed_and_links(content, tmp_path):
    out = tmp_path / "public"
    posts = build.build(content, out, site_url="https://log.example")
    assert [p.slug for p in posts] == ["third", "second", "first"]

    for slug in ("first", "second", "third"):
        assert (out / "posts" / slug / "index.html").is_file()
    assert (out / "style.css").is_file()

    home = (out / "index.html").read_text(encoding="utf-8")
    assert home.index("Third &amp; Last") < home.index("Second: Wolves") < home.index("First Night")
    assert "Latest session" in home and "September 1, 2026" in home
    assert 'id="y2024"' in home  # older sessions grouped by year
    assert "Wolves love them" in (out / "posts" / "second" / "index.html").read_text(encoding="utf-8")

    middle = (out / "posts" / "second" / "index.html").read_text(encoding="utf-8")
    assert 'href="/posts/first/"' in middle and 'href="/posts/third/"' in middle
    newest = (out / "posts" / "third" / "index.html").read_text(encoding="utf-8")
    assert 'href="/posts/second/"' in newest and "Next &rarr;" not in newest

    first = (out / "posts" / "first" / "index.html").read_text(encoding="utf-8")
    assert '<h2 id="arrival">Arrival</h2>' in first and "<blockquote>" in first and "<table>" in first

    tags = (out / "tags" / "index.html").read_text(encoding="utf-8")
    assert 'id="barovia"' in tags and 'id="wolves"' in tags

    feed = ET.parse(out / "feed.xml").getroot()
    assert feed.tag == f"{ATOM}feed"
    entries = feed.findall(f"{ATOM}entry")
    assert [e.find(f"{ATOM}title").text for e in entries] == ["Third & Last", "Second: Wolves", "First Night"]
    assert entries[0].find(f"{ATOM}link").get("href") == "https://log.example/posts/third/"
    assert feed.find(f"{ATOM}updated").text == "2026-09-01T17:00:00-05:00"


@pytest.fixture(scope="module")
def real_site(tmp_path_factory):
    """The whole blog, built from the repo's own posts, wiki and map."""
    out = tmp_path_factory.mktemp("site") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return out


def test_every_link_and_image_on_the_real_site_resolves(real_site):
    missing = set()
    for page in real_site.rglob("*.html"):
        html = re.sub(r"<script.*?</script>", "", page.read_text(encoding="utf-8"), flags=re.S)
        for url in re.findall(r'\b(?:href|src)="(/[^"#?]*)', html):
            target = real_site / url.lstrip("/")
            if url.endswith("/") or target.is_dir():
                target = target / "index.html"
            if not target.exists():
                missing.add(f"{page.relative_to(real_site).as_posix()} -> {url}")
    assert not missing, sorted(missing)[:20]


def test_no_images_on_links_that_expire(real_site):
    # Discord attachment links carry an expiry (ex=...) and stop working, so their images go in static/.
    expiring = {page.relative_to(real_site).as_posix()
                for page in real_site.rglob("*.html")
                if re.search(r'src="https://cdn\.discordapp\.com/attachments/[^"]*\bex=', page.read_text(encoding="utf-8"))}
    assert not expiring, sorted(expiring)


def test_every_image_in_posts_and_wiki_has_alt_text(real_site):
    bare = set()
    for page in [*real_site.glob("posts/*/index.html"), *real_site.glob("wiki/*/index.html")]:
        for img in re.findall(r"<img\b[^>]*>", page.read_text(encoding="utf-8")):
            if not re.search(r'\balt="[^"]', img) and "aria-hidden" not in img and "deck" not in img:
                bare.add(f"{page.relative_to(real_site).as_posix()}: {img[:120]}")
    assert not bare, sorted(bare)


def test_duplicate_slugs_fail(tmp_path):
    write_post(tmp_path, "2024-01-01-a.md", "title: A\ndate: '2024-01-01'\nslug: same\n")
    write_post(tmp_path, "2024-01-02-b.md", "title: B\ndate: '2024-01-02'\nslug: same\n")
    with pytest.raises(ValueError, match="duplicate"):
        build.load_posts(tmp_path)


def test_normalize_base_path():
    assert build.normalize_base_path("") == "/"
    assert build.normalize_base_path("/") == "/"
    assert build.normalize_base_path("strahd-log") == "/strahd-log/"
    assert build.normalize_base_path("/strahd-log") == "/strahd-log/"


def site_links(out: Path) -> list[str]:
    links = []
    for page in out.rglob("*.html"):
        text = re.sub(r"<script>.*?</script>", "", page.read_text(encoding="utf-8"), flags=re.S)
        links += re.findall(r'(?:href|src)="([^"]*)"', text)
    return links


@pytest.mark.parametrize("base", ["/", "/strahd-log/"])
def test_every_internal_link_respects_base_path(content, tmp_path, base):
    out = tmp_path / "public"
    build.build(content, out, site_url="https://example.github.io", base_path=base)
    internal = [l for l in site_links(out) if not l.startswith(("http://", "https://", "#", "mailto:"))]
    assert internal, "expected some internal links"
    for link in internal:
        assert link.startswith(base), link
        target = out / link[len(base):].split("#")[0]
        assert target.exists() or (target / "index.html").exists(), link

    feed = ET.parse(out / "feed.xml").getroot()
    root = "https://example.github.io" + base
    assert feed.find(f"{ATOM}id").text == root
    assert feed.find(f"{ATOM}entry").find(f"{ATOM}link").get("href") == root + "posts/third/"


def test_base_path_from_environment(content, tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", "strahd-log")
    out = tmp_path / "public"
    build.build(content, out, site_url="https://example.github.io")
    assert 'href="/strahd-log/style.css"' in (out / "index.html").read_text(encoding="utf-8")


def test_post_images_follow_base_path_and_are_absolute_in_feed(content, tmp_path):
    out = tmp_path / "public"
    build.build(content, out, site_url="https://example.github.io", base_path="/strahd-log/")
    page = (out / "posts" / "first" / "index.html").read_text(encoding="utf-8")
    assert '<img alt="Icon" src="/strahd-log/favicon.svg"' in page
    feed = (out / "feed.xml").read_text(encoding="utf-8")
    assert "https://example.github.io/strahd-log/favicon.svg" in feed


def test_tags_page_and_menu_link_only_when_posts_have_tags(tmp_path):
    write_post(tmp_path / "content", "2024-01-09-a.md", "title: A\ndate: '2024-01-09'\n")
    out = tmp_path / "public"
    build.build(tmp_path / "content", out, site_url="https://log.example")
    home = (out / "index.html").read_text(encoding="utf-8")
    assert not (out / "tags").exists() and 'href="/tags/"' not in home
    # The feed is still built, and linked from the footer rather than the menu.
    assert (out / "feed.xml").is_file()
    nav = home[home.index('<nav class="site-nav"'):home.index("</nav>")]
    assert "feed.xml" not in nav and "Tags" not in nav
    assert 'href="/feed.xml">Follow new sessions' in home[home.index("site-footer"):]


def test_tags_page_and_menu_link_appear_with_tags(content, tmp_path):
    out = tmp_path / "public"
    build.build(content, out, site_url="https://log.example")
    assert (out / "tags" / "index.html").is_file() and 'href="/tags/"' in (out / "index.html").read_text(encoding="utf-8")


def test_folded_post_keeps_its_old_address(tmp_path):
    root = tmp_path
    write_post(root / "content" / "posts", "2026-02-03-welcome.md", "title: Welcome Back\ndate: '2026-02-03'\n")
    (root / "data").mkdir()
    (root / "data" / "redirects.yaml").write_text("posts:\n  2026-02-03-notebook: 2026-02-03-welcome\n", encoding="utf-8")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")
    stub = (out / "posts" / "notebook" / "index.html").read_text(encoding="utf-8")
    assert "url=/strahd-log/posts/welcome/" in stub and "Welcome Back" in stub
    assert (out / "_redirects").read_text(encoding="utf-8").splitlines()[0] == "/posts/notebook/ /posts/welcome/ 301"


def test_folded_wiki_page_keeps_its_old_address(tmp_path):
    root = tmp_path
    write_post(root / "content" / "posts", "2026-02-03-welcome.md", "title: Welcome Back\ndate: '2026-02-03'\n")
    (root / "content" / "wiki").mkdir(parents=True)
    (root / "content" / "wiki" / "zorya.md").write_text("---\ntitle: Zorya\ntype: creature\n---\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "redirects.yaml").write_text("wiki:\n  zora: zorya\n", encoding="utf-8")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")
    stub = (out / "wiki" / "zora" / "index.html").read_text(encoding="utf-8")
    assert "url=/strahd-log/wiki/zorya/" in stub and "Zorya" in stub
    assert "/wiki/zora/ /wiki/zorya/ 301" in (out / "_redirects").read_text(encoding="utf-8").splitlines()


def test_redirect_to_an_unknown_post_fails(tmp_path):
    write_post(tmp_path / "content" / "posts", "2026-02-03-a.md", "title: A\ndate: '2026-02-03'\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "redirects.yaml").write_text("posts:\n  old: 2026-02-03-missing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown post"):
        build.build(tmp_path / "content" / "posts", tmp_path / "public", site_url="https://x.example")


def test_custom_domain_lands_in_the_output(content, tmp_path):
    out = tmp_path / "public"
    build.build(content, out, site_url="https://owlbear.dicelore.quest")
    assert (out / "CNAME").read_text(encoding="utf-8").strip() == "owlbear.dicelore.quest"


def test_page_view_counter_only_when_configured(content, tmp_path, monkeypatch):
    monkeypatch.delenv("GOATCOUNTER", raising=False)
    build.build(content, tmp_path / "plain", site_url="https://log.example")
    assert "goatcounter" not in (tmp_path / "plain" / "index.html").read_text(encoding="utf-8")

    monkeypatch.setenv("GOATCOUNTER", "owlbear")
    build.build(content, tmp_path / "counted", site_url="https://log.example", base_path="/strahd-log/")
    for page in ("index.html", "posts/first/index.html", "404.html"):
        html = (tmp_path / "counted" / page).read_text(encoding="utf-8")
        assert "https://owlbear.goatcounter.com/count?p=" in html
        assert 'base = "/strahd-log/"' in html
        assert "gc.zgo.at" not in html  # the counter script is ours, not GoatCounter's


def test_page_view_counter_rejects_a_bad_code(content, tmp_path, monkeypatch):
    monkeypatch.setenv("GOATCOUNTER", "owlbear.goatcounter.com/x")
    with pytest.raises(ValueError, match="GOATCOUNTER"):
        build.build(content, tmp_path / "public")


def test_note_paragraphs_become_table_notes_in_the_margin():
    import article
    html = article.margin_notes("<p>We ran.</p><p>Note: [Meta details] The table laughed.</p><p>Not a Note: here</p>")
    assert html == ('<p>We ran.</p><aside class="margin-note" aria-label="From the table"><p>The table laughed.</p></aside>'
                    "<p>Not a Note: here</p>")


def test_find_slides_matches_the_post_file_name(content, tmp_path):
    posts = build.load_posts(content)
    folder = tmp_path / "static" / "slides" / "2026-09-01-third"
    folder.mkdir(parents=True)
    for name in ("02.webp", "01.webp", "deck.pdf", "notes.txt"):
        (folder / name).write_bytes(b"")
    build.find_slides(posts, tmp_path / "static")
    third = next(p for p in posts if p.slug == "third")
    assert third.slides == ["slides/2026-09-01-third/01.webp", "slides/2026-09-01-third/02.webp"]
    assert third.slides_pdf == "slides/2026-09-01-third/deck.pdf"
    assert all(not p.slides for p in posts if p is not third)


def test_a_second_deck_lives_in_a_subfolder_with_its_own_label(content, tmp_path):
    posts = build.load_posts(content)
    folder = tmp_path / "static" / "slides" / "2026-09-01-third"
    (folder / "gemini").mkdir(parents=True)
    for name in ("01.webp", "02.webp", "gemini/01.webp", "gemini/deck.pdf"):
        (folder / name).write_bytes(b"")
    (folder / "label.txt").write_text("NotebookLM\n", encoding="utf-8")
    (folder / "gemini" / "label.txt").write_text("Gemini\n", encoding="utf-8")
    build.find_slides(posts, tmp_path / "static")
    third = next(p for p in posts if p.slug == "third")
    assert [(d.label, d.key) for d in third.decks] == [("NotebookLM", "notebooklm"), ("Gemini", "gemini")]
    assert third.decks[1].slides == ["slides/2026-09-01-third/gemini/01.webp"]
    assert third.decks[1].pdf == "slides/2026-09-01-third/gemini/deck.pdf"


def test_vote_buttons_count_through_goatcounter_without_cookies(content, tmp_path, monkeypatch):
    monkeypatch.setenv("GOATCOUNTER", "owlbear")
    static = tmp_path / "static"
    folder = static / "slides" / "2026-09-01-third"
    (folder / "gemini").mkdir(parents=True)
    for name in ("01.webp", "gemini/01.webp"):
        (folder / name).write_bytes(b"")
    (folder / "gemini" / "label.txt").write_text("Gemini", encoding="utf-8")
    out = tmp_path / "public"
    build.build(content, out, site_url="https://log.example", slides_static=static)
    html = (out / "posts" / "third" / "index.html").read_text(encoding="utf-8")
    assert html.count('data-vote="') == 2
    assert "goatcounter.com/count" in html and "e=true" in html and '"/vote/third/"' in html
    assert "document.cookie" not in html
    single = (out / "posts" / "second" / "index.html").read_text(encoding="utf-8")
    assert "data-vote" not in single


def test_bot_corpus_lists_posts_oldest_first_without_player_names(content, tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "malron.md").write_text("---\ntitle: Malron\ntype: character\nplayer: Chris\n"
                                         "summary: A cleric.\n---\n\nPriest of Lathander.\n", encoding="utf-8")
    write_post(content, "2026-09-08-fourth.md", "title: Fourth\ndate: '2026-09-08T17:00:00-05:00'\n",
               "## At a Glance:\n\n* **Wolves:** Malron *wins*.\n\nWe met wolves.\n")
    out = tmp_path / "public"
    build.build(content, out, site_url="https://example.org", wiki_dir=wiki_dir)
    corpus = json.loads((out / "bot" / "corpus.json").read_text(encoding="utf-8"))
    assert [p["date"] for p in corpus["posts"]] == ["2024-01-09", "2024-02-13", "2026-09-01", "2026-09-08"]
    last = corpus["posts"][-1]
    assert last["url"] == "https://example.org/posts/fourth/"
    assert last["glance"] == ["Wolves: Malron wins."]
    assert last["wiki"] == ["malron"]
    assert "We met wolves." in last["text"]
    assert corpus["wiki"][0]["summary"] == "A cleric."
    assert "Chris" not in json.dumps(corpus)


def test_footer_license_line_is_clean_and_names_no_one(content, tmp_path):
    out = tmp_path / "public"
    build.build(content, out, site_url="https://log.example")
    page = (out / "index.html").read_text(encoding="utf-8")
    legal = re.findall(r'<p class="legal">(.*?)</p>', page, re.S)[-1]
    assert legal.endswith("The site&rsquo;s code is all rights reserved.")
    # Every entity is whole ("&rsquo;", never a stray "rsquo;"), and real names stay off the site's pages.
    assert not re.search(r"(?<!&)\b(?:rsquo|copy|amp);", page)
    assert "O&rsquo;Toole" not in page and "Christopher" not in page


def test_full_screen_slides_use_the_whole_screen_and_fade_their_controls():
    css = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    script = (build.ROOT / "templates" / "post.html").read_text(encoding="utf-8")
    # The slide may fill the screen: dots sit over its bottom edge instead of below it.
    assert "max-height: 100dvh" in css
    assert re.search(r"\.deck\.open \.deck-dots \{[^}]*position: absolute", css)
    # Dots, close button and arrows fade out once quiet, and come back on each slide change.
    assert re.search(r"\.deck\.open\.quiet \.deck-dots,[^{]*\.deck\.open\.quiet \.deck-close[^{]*\{[^}]*opacity: 0", css)
    assert "QUIET_AFTER = 2000" in script and "wake()" in script
    # Where the browser allows it, its own bars are hidden too, and leaving that closes the view.
    assert "requestFullscreen" in script and "fullscreenchange" in script
    # A rotation re-fits the open slide.
    assert 'addEventListener("resize"' in script


def test_closing_full_screen_slides_returns_to_the_strip():
    # Chris: after leaving a full-screen slide he was often further down the page.
    template = (build.ROOT / "templates" / "post.html").read_text(encoding="utf-8")
    assert 'frame.scrollIntoView({block: "center"})' in template and "returnUntil" in template
