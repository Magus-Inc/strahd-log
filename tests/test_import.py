from pathlib import Path

import import_op
from build import split_front_matter

SITE = import_op.SITE


def make_export(root: Path, slug: str, textile_text: str, html: str | None = None, manifest: str | None = None) -> Path:
    (root / "posts").mkdir(parents=True, exist_ok=True)
    (root / "posts" / f"{slug}.textile").write_text(textile_text, encoding="utf-8")
    if html is not None:
        (root / "posts" / f"{slug}.html").write_text(html, encoding="utf-8")
    if manifest is not None:
        (root / "manifest.csv").write_text(manifest, encoding="utf-8")
    return root


def test_parse_header_splits_meta_and_body():
    meta, body = import_op.parse_header(
        "title: A Night: In Barovia\ndate: 2024-02-13 9:00 PM\ntagline: Wolves love them\n\nh2. Hello\n"
    )
    assert meta == {"title": "A Night: In Barovia", "date": "2024-02-13 9:00 PM", "tagline": "Wolves love them"}
    assert body.startswith("h2. Hello")


def test_parse_date_is_chicago_time_with_dst():
    assert import_op.parse_date("2026-09-01 5:00 PM").isoformat() == "2026-09-01T17:00:00-05:00"
    assert import_op.parse_date("2024-01-09 9:00 PM").isoformat() == "2024-01-09T21:00:00-06:00"


def test_split_wiki_and_fallback_urls():
    assert import_op.split_wiki("Ireena Kolyana | Ireena ") == ("Ireena Kolyana", "Ireena")
    assert import_op.split_wiki("Doru") == ("Doru", "Doru")
    assert import_op.split_wiki(":mal") == (":mal", "mal")
    assert import_op.fallback_href("Notes - October 22nd, 2024") == f"{SITE}/wikis/notes-october-22nd-2024"
    assert import_op.fallback_href("Finishing the Manor?") == f"{SITE}/wikis/finishing-the-manor"
    assert import_op.fallback_href(":mal") == f"{SITE}/characters/mal"


def test_wiki_links_use_rendered_hrefs(tmp_path):
    html = (
        '<html><body><a href="/characters/new">Character</a><div class="post">'
        '<a href="/characters/schlopkht" class="wiki-content-link">Schloptk</a>'
        '<a href="/wikis/the-manor-house" class="wiki-page-link"> four story manor</a>'
        "</div></body></html>"
    )
    export = make_export(
        tmp_path / "export", "wiki",
        "title: Wiki\ndate: 2024-02-13 9:00 PM\n\n"
        "p. [[:schlopkht | Schloptk]] went into the [[Manor | four story manor]] and met [[Doru]].\n",
        html,
    )
    post = import_op.load_post(export / "posts" / "wiki.textile")
    _, text = import_op.render_post(post)
    # Counts differ (3 links, 2 anchors), so links are matched by URL and Doru falls back.
    assert f"[Schloptk]({SITE}/characters/schlopkht)" in text
    assert f"[four story manor]({SITE}/wikis/manor)" in text
    assert f"[Doru]({SITE}/wikis/doru)" in text
    assert "[[" not in text and "]]" not in text


def test_wiki_links_pair_in_order_when_counts_match(tmp_path):
    html = '<a href="/wikis/the-manor-house" class="wiki-page-link">Manor</a>'
    export = make_export(tmp_path / "e", "pair", "title: P\ndate: 2024-02-13 9:00 PM\n\nSee [[Manor]].\n", html)
    _, text = import_op.render_post(import_op.load_post(export / "posts" / "pair.textile"))
    assert f"[Manor]({SITE}/wikis/the-manor-house)" in text


def test_textile_blocks_become_markdown(tmp_path):
    body = (
        "h2. **At a Glance:**\n\n"
        "* **One:** first\n* Two\n\n"
        "# numbered\n# again\n\n"
        "bq. A quote from the mists.\n\n"
        '"Barovia":https://example.com/barovia and !https://example.com/map.png!\n\n'
        "|_. Name |_. Role |\n| Ismark | Burgomaster's son |\n\n"
        "[[File:1370972  | class=media-item-align-none | durst_floor2__Small_.jpg]]\n\n"
        "<div class='oembed external-link'><a href='https://cdn.example.com/Ismark.png?ex=1&amp;b=2'></a></div>\n"
    )
    html = ('<img src="https://cdn.example.com/assets/1370972/durst_floor2__Small_.jpg?1" '
            'data-asset-id="1370972" alt="durst_floor2__Small_.jpg">')
    export = make_export(tmp_path / "e", "blocks", "title: Blocks\ndate: 2024-02-13 9:00 PM\n\n" + body, html)
    _, text = import_op.render_post(import_op.load_post(export / "posts" / "blocks.textile"))
    md = split_front_matter(text)[1]
    assert "## At a Glance:" in md
    assert "* **One:** first" in md
    assert "1. numbered" in md
    assert "> A quote from the mists." in md
    assert "[Barovia](https://example.com/barovia)" in md
    assert "![](https://example.com/map.png)" in md
    assert "| Name | Role |" in md and "| Ismark |" in md
    assert "![durst_floor2__Small_.jpg](https://cdn.example.com/assets/1370972/durst_floor2__Small_.jpg?1)" in md
    assert "![](https://cdn.example.com/Ismark.png?ex=1&b=2)" in md
    for leftover in ("h2.", "bq.", '":http', "!https", "oembed", "<div"):
        assert leftover not in md


def test_import_writes_front_matter_and_is_idempotent(tmp_path):
    export = make_export(
        tmp_path / "export", "the-red-door",
        "title: The Red Door: A Reunion\ndate: 2026-09-01 5:00 PM\ntagline: Old friends\ntags: abbey, reunion\n\n"
        "Body text.\n",
        manifest="slug,url,title\nthe-red-door,https://op.example/adventure-log/the-red-door,The Red Door\n",
    )
    out = tmp_path / "content"
    (written,) = import_op.import_export(export, out)
    assert written.name == "2026-09-01-the-red-door.md"
    meta, body = split_front_matter(written.read_text(encoding="utf-8"))
    assert meta == {
        "title": "The Red Door: A Reunion",
        "date": "2026-09-01T17:00:00-05:00",
        "tagline": "Old friends",
        "tags": ["abbey", "reunion"],
        "slug": "the-red-door",
        "obsidian_portal_url": "https://op.example/adventure-log/the-red-door",
    }
    assert body.strip() == "Body text."

    first = written.read_bytes()
    import_op.import_export(export, out)
    assert written.read_bytes() == first
    assert [p.name for p in out.iterdir()] == ["2026-09-01-the-red-door.md"]

    # A changed date replaces the old file rather than leaving a duplicate.
    src = export / "posts" / "the-red-door.textile"
    src.write_text(src.read_text(encoding="utf-8").replace("2026-09-01", "2026-09-02"), encoding="utf-8")
    import_op.import_export(export, out)
    assert [p.name for p in out.iterdir()] == ["2026-09-02-the-red-door.md"]


def test_import_drops_a_heading_that_repeats_the_title(tmp_path):
    # The adventure-log prompt starts the body with "h1. <title>"; the page already shows the title.
    export = make_export(
        tmp_path / "export", "the-red-door",
        "title: The Red Door\ndate: 2026-09-01 5:00 PM\n\nh1. The Red Door\n\nh2. Summary:\n\nBody text.\n",
    )
    (written,) = import_op.import_export(export, tmp_path / "content")
    _, body = split_front_matter(written.read_text(encoding="utf-8"))
    assert body.strip() == "## Summary:\n\nBody text."
