"""Build the Curse of Strahd adventure log into public/.

Reads content/posts/*.md and content/wiki/*.md (YAML front matter + Markdown) and writes the home
page, one page per post at /posts/<slug>/, the wiki at /wiki/, a tags page at /tags/, a search page
at /search/ (with /search-index.json) and an Atom feed at /feed.xml.

    python build.py            # build
    python build.py --serve    # build, then serve public/ on http://localhost:8000
    BASE_PATH=/strahd-log/ python build.py   # links for a site under a sub-path (GitHub Pages)
"""

from __future__ import annotations

import argparse
import functools
import http.server
import hashlib
from html import escape
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

import article
import barovia_map
import poststyle
import sources as source_list
import share
import start
import suspect
import wiki
import wikistyle

ROOT = Path(__file__).resolve().parent
SITE_TITLE = "Curse of Strahd: The Owlbear Chronicles"
SITE_SUBTITLE = "An adventure log from the mists of Barovia"
# The publish workflow sets URL to the site's address.
DEFAULT_SITE_URL = "http://localhost:8000"
# Where the site lives under its host: "/" on owlbear.dicelore.quest and locally, "/strahd-log/" on
# GitHub Pages' default address.
DEFAULT_BASE_PATH = "/"
# GoatCounter site code for page-view counts (https://CODE.goatcounter.com). The publish workflow sets
# GOATCOUNTER, so local builds and previews never count visits.
COUNTER_CODE = re.compile(r"[a-z0-9-]+")
# Google Analytics 4 measurement id (Chris, 2026-11-04), beside GoatCounter. Like GOATCOUNTER it comes
# only from the publish workflow's GOOGLE_ANALYTICS, so local builds and previews never count.
GA_ID = re.compile(r"G-[A-Z0-9]+")


@dataclass
class Post:
    title: str
    date: datetime
    slug: str
    body_md: str
    tagline: str = ""
    tags: list[str] = field(default_factory=list)
    obsidian_portal_url: str = ""
    html: str = ""
    source: Path | None = None
    mentions: set[str] = field(default_factory=set)  # wiki slugs
    toc: list[dict] = field(default_factory=list)
    minutes: int = 1
    glance: list[str] = field(default_factory=list)
    teaser: str = ""
    cast: list = field(default_factory=list)
    characters_html: str = ""  # the cast as HTML, for link_wiki to find their pages
    listed: list[str] = field(default_factory=list)  # wiki slugs of the cast
    slides: list[str] = field(default_factory=list)  # static/slides/<file stem>/*.webp, in page order
    slides_pdf: str = ""
    decks: list = field(default_factory=list)  # article.Deck, the one above first, then any in subfolders
    show_cast: bool = True  # pills under the title (poststyle cast setting)
    slides_at: str = "above-story"  # where the slides go (poststyle slides setting)
    number: int = 0  # the session's number, oldest first; the map and wiki citations use it
    party: dict = field(default_factory=dict)  # data/party.yaml: died/revived/joined/returned/left -> [wiki pages]
    cast_names: list[str] = field(default_factory=list)  # front matter `cast:`: the player characters there
    # front matter `sources:`: what the post was written from, as hidden reference ids or public links
    # (sources.py). The site never shows them; dnd-scribe's private table says what each id is.
    sources: list[str] = field(default_factory=list)
    feature: str = ""  # front matter `feature:`: the feature picture's file name, when the story has several
    card_pic: str = ""  # images/cards/post-<slug>.webp: the feature picture, small, for the home page card

    @property
    def path(self) -> str:
        """Address relative to the site root; templates prefix it with the base path."""
        return f"posts/{self.slug}/"

    @property
    def slide_count(self) -> int:
        """Slides across every deck; list pages badge a session that has any."""
        return sum(len(deck.slides) for deck in self.decks)

    @property
    def life_badges(self) -> list[dict]:
        """List-page badges from data/party.yaml, in a fixed order: skull (died), revive (brought back),
        party (joined or came back) and leaves. Each is {kind, label, aria}."""
        badges = []
        for kind, keys in BADGE_KEYS:
            parts = [(key, self.party[key]) for key in keys if self.party.get(key)]
            if not parts:
                continue
            if kind in ("died", "revived"):
                label = and_list([first_name(p) for _, ps in parts for p in ps])
                aria = ", ".join(f"{and_list([first_name(p) for p in ps])} {PARTY_WORDS[key][0][len(ps) > 1]}"
                                 for key, ps in parts)
            else:
                label = aria = ", ".join(f"{and_list([first_name(p) for p in ps])} {PARTY_WORDS[key][0][len(ps) > 1]}"
                                         for key, ps in parts)
            badges.append({"kind": kind, "label": label, "aria": aria})
        return badges

    @property
    def life_lines(self) -> list[tuple]:
        """Lines under the character pills on the post: (badge kind, [wiki pages], what happened)."""
        return [(kind, self.party[key], PARTY_WORDS[key][1][len(self.party[key]) > 1])
                for kind, keys in BADGE_KEYS for key in keys if self.party.get(key)]


# Badge kinds and the data/party.yaml keys each one shows.
BADGE_KEYS = (("died", ("died",)), ("revived", ("revived",)), ("party", ("joined", "returned")), ("left", ("left",)))
# Per key: (badge words, post-page words), each as (one character, several).
PARTY_WORDS = {"died": (("died", "died"), ("died", "died")),
               "revived": (("was brought back", "were brought back"), ("was brought back", "were brought back")),
               "joined": (("joins", "join"), ("joins the party", "join the party")),
               "returned": (("returns", "return"), ("returns to the party", "return to the party")),
               "left": (("leaves", "leave"), ("leaves the party", "leave the party"))}


def first_name(page) -> str:
    return page.title.split()[0]


def and_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def apply_party_entry(post: "Post", entry: dict, pages: dict) -> None:
    """One post's entry in data/party.yaml: who died, who was brought back (the same session or a later
    one), who joined, came back or left. Names are wiki slugs of player characters."""
    party = {}
    for key, names in entry.items():
        if key not in PARTY_WORDS:
            raise ValueError(f"data/party.yaml: {post.slug}: unknown key {key} (use {', '.join(PARTY_WORDS)})")
        for name in names or []:
            page = pages.get(name)
            if page is None:
                raise ValueError(f"data/party.yaml: {post.slug}: no wiki page {name}")
            if page.type != "character" or page.dm:
                raise ValueError(f"data/party.yaml: {post.slug}: {name} is not a player character")
            party.setdefault(key, []).append(page)
    post.party = party


def apply_party(posts: list["Post"], pages: list, path: Path) -> None:
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_slug = {p.slug: p for p in posts}
    by_page = {p.slug: p for p in pages}
    for slug, entry in data.items():
        if slug not in by_slug:
            raise ValueError(f"data/party.yaml: unknown post {slug}")
        apply_party_entry(by_slug[slug], entry or {}, by_page)


def split_front_matter(text: str) -> tuple[dict, str]:
    """'---\\n<yaml>\\n---\\n<body>' -> (dict, body). Text without front matter has empty meta."""
    text = text.replace("\r\n", "\n").lstrip("﻿")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("front matter is not a mapping")
    return meta, m.group(2)


def to_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value).strip())


def slug_from_filename(path: Path) -> str:
    return re.sub(r"^\d{4}-\d\d-\d\d-", "", path.stem)


def parse_post(path: Path) -> Post:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    for key in ("title", "date"):
        if key not in meta:
            raise ValueError(f"{path.name}: front matter has no {key}")
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return Post(
        title=str(meta["title"]),
        date=to_datetime(meta["date"]),
        slug=str(meta.get("slug") or slug_from_filename(path)),
        body_md=body,
        tagline=str(meta.get("tagline") or ""),
        tags=[str(t) for t in tags],
        obsidian_portal_url=str(meta.get("obsidian_portal_url") or ""),
        source=path,
        cast_names=[str(n) for n in meta.get("cast") or []],
        sources=source_list.parse_sources(meta.get("sources"), path.name),
        feature=str(meta.get("feature") or ""),
    )


def render_markdown(text: str) -> str:
    return markdown.markdown(suspect.to_html(text), extensions=["extra", "sane_lists", "smarty"], output_format="html")


def rebase(html: str, prefix: str) -> str:
    """Point root-relative links in rendered Markdown ("/images/x.png") at prefix ("/strahd-log/" or
    an absolute site address), so post bodies can use /images/... whatever the base path."""
    return re.sub(r'((?:src|href|data-full)=")/(?!/)', lambda m: m.group(1) + prefix, html)


# Where a section starts for relink: every heading in the On this page box, or only the big ones.
SECTION_START = {"each-heading": r"<h[23][ >]", "each-section": r"<h2[ >]"}


def link_wiki(posts: list[Post], pages: list[wiki.WikiPage], relink: str = "once",
              phrases: dict[str, list[str]] | None = None, exact: set[str] | frozenset = frozenset()) -> None:
    """Link wiki names (and the phrases in data/described-places.yaml) in posts and wiki pages, and record
    which posts mention each page."""
    linker = wiki.Linker(pages, phrases, exact)
    by_slug = {w.slug: w for w in pages}
    # The narrator writes every session and the DM runs every one, so both are at each (Chris, 2026-11-03).
    narrators = {w.slug for w in pages if w.narrator or w.dm}
    for post in posts:  # newest first, so mentioned_in comes out newest first too
        post.html, post.mentions = linker.link(post.html, each_section=SECTION_START.get(relink))
        post.html = wiki.link_npc_names(post.html, linker)
        if post.characters_html:  # who the cast names, even when the style shows no pills
            _, named = linker.link(post.characters_html)
            post.listed = sorted(s for s in named if by_slug[s].type == "character" and not by_slug[s].dm)
        post.mentions |= narrators | set(post.listed)
        for slug in sorted(post.mentions):
            by_slug[slug].mentioned_in.append(post)
    for page in pages:
        page.html, _ = linker.link(article.name_ai_subjects(article.ai_credits(article.add_image_votes(
            article.hover_titles(article.full_size(render_markdown(page.body_md), ROOT / "static")))), page.title), self_slug=page.slug)


def apply_style(posts: list[Post], style: dict) -> None:
    """The look settings (data/post-style.yaml, poststyle.py) on every post in the one post format."""
    for post in posts:
        post.html = poststyle.apply(post.html, style, post.cast_names, post.feature)
        # Who the front matter's `cast:` names; link_wiki finds their pages, shown or not.
        post.characters_html = f"<p>{', '.join(post.cast_names)}</p>" if post.cast_names else ""
        if style["tagline"] == "none":
            post.tagline = ""
        post.show_cast = style["cast"] != "list"
        post.slides_at = style["slides"]


def number_sessions(posts: list[Post]) -> None:
    """Number every session oldest first, the same order the map numbers its markers in."""
    for number, post in enumerate(sorted(posts, key=lambda p: (p.date, p.slug)), 1):
        post.number = number


def cite_sessions(posts: list[Post], pages: list[wiki.WikiPage]) -> None:
    """On wiki pages, turn "(Session Title)" links into small session numbers that open the post, and
    count a cited session as one the page appears in, unless the page lists it under heard_of_in
    (we were only told of the place or thing there). page.html keeps the titles for search."""
    by_slug = {p.slug: p for p in posts}

    def marker(slug: str, title: str) -> str:
        post = by_slug.get(slug)
        if post is None:  # not a session we know: leave the link as it was written
            return f' (<a href="/posts/{slug}/">{escape(title)}</a>)'
        label = escape(f"Session {post.number}: {post.title}", quote=True)
        # A word joiner keeps the number on the line of the word it follows.
        return f'&#8288;<a class="cite" href="/posts/{slug}/" title="{label}" aria-label="{label}">{post.number}</a>'

    for page in pages:
        page.cited_html, cited = wiki.cite_sessions(page.html, marker)
        stray = [s for s in page.heard_of_in if s not in cited]
        if stray:
            raise ValueError(f"wiki/{page.slug}: heard_of_in names {', '.join(stray)}, which the page never cites")
        heard = set(page.heard_of_in)
        known = {p.slug for p in page.mentioned_in}
        extra = [by_slug[s] for s in cited if s in by_slug and s not in known]
        if extra:
            page.mentioned_in = sorted([*page.mentioned_in, *extra], key=lambda p: (p.date, p.slug), reverse=True)
        if heard:
            page.mentioned_in = [p for p in page.mentioned_in if p.slug not in heard]


def apply_wiki_style(pages: list[wiki.WikiPage], style: dict) -> None:
    """One layout for every wiki page (see wikistyle.py and data/wiki-style.yaml)."""
    for page in pages:
        styled = wikistyle.apply(page.cited_html, style, page.type)
        page.cited_html, page.top_picture = styled.html, styled.picture
        page.facts = wikistyle.facts(page) if style["top"] == "infobox" and (
            style["kinds"] == "all" or page.type in wikistyle.PEOPLE) else []


def add_place_facts(pages: list[wiki.WikiPage], parent: dict[str, str], nearby_file: Path) -> None:
    """Place pages' facts boxes link the places around them (Chris, 2026-11-02): "Part of" and "Places
    inside" from data/map.yaml's within list, and "Nearby" from data/nearby.yaml."""
    by_slug = {p.slug: p for p in pages}
    nearby = (yaml.safe_load(nearby_file.read_text(encoding="utf-8")) or {}).get("nearby", {}) \
        if nearby_file.exists() else {}
    inside: dict[str, list[str]] = {}
    for child, home in parent.items():
        if child != home and child in by_slug:
            inside.setdefault(home, []).append(child)

    def links(slugs) -> dict:
        return {"links": [(by_slug[s].title, by_slug[s].path) for s in slugs if s in by_slug]}

    for page in pages:
        if page.type != "place":
            continue
        rows = []
        if parent.get(page.slug, page.slug) != page.slug:
            rows.append(("Part of", links([parent[page.slug]])))
        if inside.get(page.slug):
            rows.append(("Places inside", links(sorted(inside[page.slug], key=lambda s: by_slug[s].title))))
        if nearby.get(page.slug):
            rows.append(("Nearby", links(nearby[page.slug])))
        at = 1 if page.facts and page.facts[0][0] == "Also known as" else 0
        page.facts[at:at] = rows


def find_slides(posts: list[Post], static_dir: Path) -> None:
    """A post's slide deck is static/slides/<post file name>/ (e.g. 2026-09-29-the-beacon-of-argynvostholt/):
    one image per slide (01.webp, 02.webp, ...) and, optionally, the deck as a PDF. Another deck for the
    same session goes in a subfolder (e.g. gemini/) laid out the same way; readers vote between them.
    A label.txt in a deck's folder names it (e.g. "NotebookLM"); an optional second line is a short
    subheading on the deck's style, shown under the name."""
    for post in posts:
        name = post.source.stem if post.source else post.slug
        folder = static_dir / "slides" / name
        if not folder.is_dir():
            continue
        post.decks = [deck for deck in (read_deck(d, static_dir) for d in [folder, *sorted(folder.iterdir())]
                                        if d.is_dir()) if deck.slides]
        if post.decks:
            post.slides, post.slides_pdf = post.decks[0].slides, post.decks[0].pdf


def read_deck(folder: Path, static_dir: Path) -> article.Deck:
    rel = folder.relative_to(static_dir).as_posix()
    label_file = folder / "label.txt"
    lines = [ln.strip() for ln in label_file.read_text(encoding="utf-8").splitlines()] if label_file.exists() else []
    label, note = (lines + ["", ""])[:2]
    pdfs = sorted(folder.glob("*.pdf"))
    return article.Deck(label, tag_slug(label) or folder.name, [f"{rel}/{f.name}" for f in sorted(folder.glob("*.webp"))],
                        f"{rel}/{pdfs[0].name}" if pdfs else "", note)


THUMB_SIZE = 200  # px, the long side; cards show it at about 76 CSS px, so this stays sharp on phones


def make_thumbnails(pages: list[wiki.WikiPage], static_dir: Path, out_dir: Path) -> None:
    """Give each wiki page with a picture a small thumbnail of its first one that exists, for list cards.
    Pictures must live under the site (/images/...); missing files and outside links get no thumbnail."""
    from PIL import Image  # only the build needs it, not the importer tools
    for page in pages:
        for src in page.pictures:
            rel = src.split("?")[0].lstrip("/")
            source = static_dir / rel
            if src.startswith(("http:", "https:", "//")) or not source.is_file():
                continue
            thumb = f"images/thumbs/{Path(rel).stem}.webp"
            (out_dir / thumb).parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((THUMB_SIZE, THUMB_SIZE))
                image.save(out_dir / thumb, "WEBP", quality=80)
            page.thumb = thumb
            break


CARD_PIC_WIDTH = 640  # px; home cards are about 17-20rem wide, so this stays sharp on phones


def flat_rgb(image, width: int, height: int):
    """A picture ready to save small: turned the right way up, see-through parts laid on the site's dark
    background, and shrunk to fit width x height (never made bigger)."""
    from PIL import Image, ImageOps  # only the build needs it
    image.draft("RGB", (width, height))
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, share.BACKGROUND)
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    image = image.convert("RGB")
    image.thumbnail((width, height))
    return image


def make_card_pictures(posts: list[Post], static_dir: Path, out_dir: Path) -> None:
    """Give each post a small copy of its feature picture (the `feature:` one, else the first) for its
    home page card (blog review idea 1, Chris 2026-11-04). Only pictures on the site get one."""
    from PIL import Image  # only the build needs it
    for post in posts:
        picture = share.first_picture(post.body_md, static_dir, prefer=post.feature)
        if picture is None or isinstance(picture[0], str):
            continue
        rel = f"images/cards/post-{post.slug}.webp"
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        with Image.open(picture[0]) as image:
            flat_rgb(image, CARD_PIC_WIDTH, CARD_PIC_WIDTH * 2).save(out_dir / rel, "WEBP", quality=78)
        post.card_pic = rel


def small_copy(source: Path, out_dir: Path, width: int, name: str = "") -> str:
    """A small WebP copy of a site picture, at most width pixels wide, for pages full of pictures
    (Chris, 2026-11-04: Start here loaded 1.5 MB of full-size pictures). Wiki articles and session
    logs keep the full-size picture. Returns its path under the site (images/small/<name>-<width>.webp);
    name defaults to the file's stem, and two pictures need different names."""
    from PIL import Image  # only the build needs it
    rel = f"images/small/{name or source.stem}-{width}.webp"
    (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        flat_rgb(image, width, width * 4).save(out_dir / rel, "WEBP", quality=78)
    return rel


PORTRAIT_WIDTH = 400  # px; a party cell is up to about 180 CSS px wide, so this stays sharp on phones
CHAPTER_WIDTHS = (800, 1100)  # px; a chapter picture is 22rem beside its text, or the page's width
HERO_WIDTH = 1100  # px; the castle at the top of Start here, as wide as its original


def make_start_pictures(page: start.StartPage | None, static_dir: Path, out_dir: Path) -> None:
    """Small copies of the Start here pictures: party portraits, chapter pictures and the castle.
    page.small maps each picture (images/...) to its copies, smallest first. A copy's name keeps the
    picture's folder and type (images/full/a.png -> full-a-png), so two pictures never share one."""
    if page is None:
        return
    def copies(rel: str, widths) -> None:
        source = static_dir / rel
        if rel not in page.small and source.is_file():
            name = rel.removeprefix("images/").replace("/", "-").replace(".", "-")
            page.small[rel] = [(small_copy(source, out_dir, w, name), w) for w in widths]
    for member in page.party:
        if member.pictures:
            copies(member.pictures[0].lstrip("/"), (PORTRAIT_WIDTH,))
    for chapter in page.chapters:
        copies(chapter.picture, CHAPTER_WIDTHS)
    if page.hero:
        copies(page.hero, (HERO_WIDTH,))


def picture_card(stem: str, picture, title: str, out_dir: Path) -> dict:
    """The card for a page's picture: made on the site from a local file, or the outside address as is.
    A page with no picture of its own shares as text only (Chris, 2026-11-05), not the site's castle card."""
    if picture is None:
        return {"no_picture": True}
    source, alt = picture
    if isinstance(source, str):
        return {"image_url": source, "alt": share.alt_text(alt, title)}
    return {"image": share.card(stem, source, out_dir), "alt": share.alt_text(alt, title)}


def share_cards(posts: list[Post], pages: list[wiki.WikiPage], static_dir: Path, out_dir: Path) -> dict:
    """Link-preview details for each post and wiki page, by path: title, snippet, card picture (made
    from the page's first picture; none when it has no picture) and its alt text. Key None is the site's
    card, which list pages such as the home page share."""
    default = next(p for p in (static_dir / share.DEFAULT_PICTURE, ROOT / "static" / share.DEFAULT_PICTURE)
                   if p.is_file())
    site = {"image": share.card("site", default, out_dir), "alt": share.DEFAULT_ALT}
    cards: dict = {None: site}
    for post in posts:
        picture = share.first_picture(post.body_md, static_dir, prefer=post.feature)
        cards[post.path] = {
            "path": post.path, "title": post.title, "type": "article", "published": post.date.isoformat(),
            "description": share.post_snippet(post.tagline, post.html) or post.title,
            **picture_card(f"post-{post.slug}", picture, post.title, out_dir)}
    for page in pages:
        picture = share.first_picture(page.body_md, static_dir)
        cards[page.path] = {
            "path": page.path, "title": page.title,
            "description": share.wiki_snippet(page.summary, page.html) or page.title,
            **picture_card(f"wiki-{page.slug}", picture, page.title, out_dir)}
    return cards


def add_reading_aids(posts: list[Post], pages: list[wiki.WikiPage]) -> None:
    """Reading time, table of contents, glance callout, slides, card teaser and cast for every post."""
    owners = article.ai_picture_owners(pages)
    for post in posts:
        post.minutes = article.reading_minutes(post.html)
        post.glance = article.glance_items(post.html)
        post.teaser = article.teaser(post.html)
        post.cast = article.cast(set(post.listed) or post.mentions, pages) if post.show_cast else []
        post.html, post.toc = article.add_heading_ids(article.margin_notes(
            article.add_decks(article.wrap_glance(article.link_ai_pictures(article.ai_credits(article.hover_titles(article.full_size(post.html, ROOT / "static"))), owners)), post.decks, post.slides_at)))


def load_posts(content_dir: Path) -> list[Post]:
    posts = [parse_post(p) for p in sorted(content_dir.glob("*.md"))]
    slugs = [p.slug for p in posts]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ValueError(f"duplicate slugs: {', '.join(sorted(dupes))}")
    for post in posts:
        post.html = render_markdown(post.body_md)
    # Newest first; slug breaks ties so the order never depends on the file system.
    return sorted(posts, key=lambda p: (sort_key(p.date), p.slug), reverse=True)


def sort_key(when: datetime) -> float:
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).timestamp()


def tag_slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def nice_date(when: datetime) -> str:
    """September 1, 2026 (strftime's %-d is not portable to Windows)."""
    return f"{when:%B} {when.day}, {when:%Y}"


def atom_time(when: datetime) -> str:
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).isoformat()


def normalize_base_path(base: str) -> str:
    """'strahd-log' or '/strahd-log' -> '/strahd-log/'; '' -> '/'."""
    base = base.strip().strip("/")
    return f"/{base}/" if base else "/"


def build_feed(posts: list[Post], root: str, limit: int = 20) -> str:
    """Atom feed; root is the site's absolute address ending in '/'."""
    ns = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", ns)
    feed = ET.Element(f"{{{ns}}}feed")

    def sub(parent, tag, text=None, **attrs):
        el = ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)
        if text is not None:
            el.text = text
        return el

    sub(feed, "title", SITE_TITLE)
    sub(feed, "subtitle", SITE_SUBTITLE)
    sub(feed, "id", root)
    sub(feed, "link", href=root + "feed.xml", rel="self")
    sub(feed, "link", href=root)
    sub(feed, "updated", atom_time(posts[0].date) if posts else "1970-01-01T00:00:00+00:00")
    author = sub(feed, "author")
    sub(author, "name", "The Owlbear Party")
    for post in posts[:limit]:
        entry = sub(feed, "entry")
        sub(entry, "title", post.title)
        sub(entry, "link", href=root + post.path)
        sub(entry, "id", root + post.path)
        sub(entry, "published", atom_time(post.date))
        sub(entry, "updated", atom_time(post.date))
        if post.tagline:
            sub(entry, "summary", post.tagline)
        for tag in post.tags:
            sub(entry, "category", term=tag)
        sub(entry, "content", rebase(post.html, root), type="html")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(feed, encoding="unicode") + "\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_search_index(posts: list[Post], pages: list[wiki.WikiPage]) -> str:
    """JSON the search page loads: title, address (relative to the base path), label, plain text."""
    # Text is NFC-normalised so the search page's accent folding keeps character positions.
    # Optional badges: "s" slide count and "b" skull/revive/party/leaves badges for a session, "p" thumbnail and "n" picture count for a wiki page.
    entries = [{"t": p.title, "u": p.path, "l": nice_date(p.date), "x": wiki.plain_text(p.html),
                **({"s": p.slide_count} if p.slide_count else {}),
                **({"b": p.life_badges} if p.party else {})}
               for p in posts]
    entries += [{"t": w.title, "u": w.path, "l": wiki.label(w),
                 "x": " ".join([*w.aliases, w.summary, wiki.plain_text(w.html).replace(wiki.LOG_NOTE, "")]),
                 **({"p": w.thumb, "n": len(w.pictures)} if w.thumb else {})}
                for w in pages]
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def build_bot_corpus(posts: list[Post], pages: list[wiki.WikiPage], root: str) -> str:
    """JSON the Discord bot answers from: every post (oldest first) and wiki page, as written.

    Oldest first, so posts read in story order and a new post only adds to the end.
    Leaves out the `player` field. A PC's own wiki page can still name its player in the text, as
    it does on the public site.
    """
    return json.dumps({
        "site": root,
        "posts": [{"title": p.title, "date": p.date.date().isoformat(), "url": root + p.path,
                   "glance": [wiki.plain_text(g) for g in p.glance], "wiki": sorted(p.mentions),
                   "cast": sorted(p.listed),
                   "text": suspect.plain(p.body_md).strip()} for p in reversed(posts)],
        "wiki": [{"slug": w.slug, "title": w.title, "type": "dm" if w.dm else w.type, "aliases": w.aliases, "summary": w.summary,
                  "url": root + w.path, "text": suspect.plain(w.body_md).strip()} for w in pages],
    }, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Site:
    """Everything the stages read and fill in, in the order build() runs them (see STAGES)."""
    posts: list[Post]
    pages: list[wiki.WikiPage]
    data_dir: Path
    map_file: Path
    static_dir: Path
    party_file: Path
    style: dict
    wiki_style: dict
    places: dict = field(default_factory=dict)
    parent: dict = field(default_factory=dict)
    spots: dict = field(default_factory=dict)
    landmarks: dict = field(default_factory=dict)
    legs: list = field(default_factory=list)
    sprites: list = field(default_factory=list)
    start: start.StartPage | None = None  # the Start here page, from data/start-here.yaml


# --- the stages: each takes the Site and changes it in place ------------------------------------

def style_posts(site: Site) -> None:
    """One look for every post. Runs first: wiki linking reads the restyled headings and sections."""
    apply_style(site.posts, site.style)


def number_posts(site: Site) -> None:
    number_sessions(site.posts)


def link_names(site: Site) -> None:
    link_wiki(site.posts, site.pages, site.style["relink"],
              wiki.load_phrases(site.data_dir / "described-places.yaml", site.pages),
              wiki.load_exact_names(site.data_dir / "name-case.yaml"))


def cite_wiki(site: Site) -> None:
    """Session numbers on wiki pages; needs the numbers and the links."""
    cite_sessions(site.posts, site.pages)


def style_wiki(site: Site) -> None:
    apply_wiki_style(site.pages, site.wiki_style)


def attach_slides(site: Site) -> None:
    find_slides(site.posts, site.static_dir)


def attach_party(site: Site) -> None:
    apply_party(site.posts, site.pages, site.party_file)


def reading_aids(site: Site) -> None:
    """Reading time, contents, decks, cast; needs links, slides and party."""
    add_reading_aids(site.posts, site.pages)


def lay_out_map(site: Site) -> None:
    """Places, the trail and the sprites; the trail needs every post numbered and its party."""
    site.places, site.parent = barovia_map.load_places(site.map_file, site.pages)
    if site.wiki_style["top"] == "infobox" and site.wiki_style["kinds"] == "all":
        add_place_facts(site.pages, site.parent, site.data_dir / "nearby.yaml")
    if not site.places:
        return
    site.spots = barovia_map.load_spots(site.map_file, site.places)
    site.landmarks = barovia_map.load_landmarks(site.map_file, site.pages, site.places)
    visits = barovia_map.load_visits(site.map_file.parent / "trail.yaml", site.places, site.spots)
    site.legs = barovia_map.trail(site.posts, site.places, site.parent, site.pages, visits, site.spots)
    site.sprites = barovia_map.load_sprites(site.map_file, ROOT / "static" / "images" / "map" / "sprites")


def plan_start(site: Site) -> None:
    """The Start here page: chapters, party and fortune; needs the party data and the cast."""
    path = site.data_dir / "start-here.yaml"
    if not path.exists():
        return
    linker = wiki.Linker(site.pages, wiki.load_phrases(site.data_dir / "described-places.yaml", site.pages),
                         wiki.load_exact_names(site.data_dir / "name-case.yaml"))
    site.start = start.plan(start.load(path), site.posts, site.pages, site.static_dir,
                            lambda md: linker.link(render_markdown(md))[0] if md else "")


# The only place the order lives (tests/test_stages.py).
STAGES = (style_posts, number_posts, link_names, cite_wiki, style_wiki, attach_slides, attach_party,
          reading_aids, lay_out_map, plan_start)


def prepare(content_dir: Path = ROOT / "content" / "posts", wiki_dir: Path | None = None,
            map_file: Path | None = None, slides_static: Path | None = None, style_file: Path | None = None,
            party_file: Path | None = None, wiki_style_file: Path | None = None) -> Site:
    """Load the posts and wiki and run every stage, without writing anything."""
    data_dir = content_dir.parent.parent / "data"
    pages = wiki.load_wiki(wiki_dir or content_dir.parent / "wiki", split_front_matter)
    site = Site(posts=load_posts(content_dir), pages=pages, data_dir=data_dir,
                map_file=map_file or data_dir / "map.yaml", static_dir=slides_static or ROOT / "static",
                party_file=party_file or data_dir / "party.yaml",
                style=poststyle.load_style(style_file or data_dir / "post-style.yaml"),
                wiki_style=wikistyle.load_style(wiki_style_file or data_dir / "wiki-style.yaml"))
    for stage in STAGES:
        stage(site)
    return site


# --- writing the site -----------------------------------------------------------------------------

def make_env(site: Site, site_url: str, base: str) -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["tag_slug"] = tag_slug
    env.filters["nice_date"] = nice_date
    env.filters["rebase"] = lambda html: rebase(html, base)
    counter = os.environ.get("GOATCOUNTER", "").strip().lower()
    if counter and not COUNTER_CODE.fullmatch(counter):
        raise ValueError(f"GOATCOUNTER must be a GoatCounter site code like 'owlbear', not {counter!r}")
    ga = os.environ.get("GOOGLE_ANALYTICS", "").strip()
    if ga and not GA_ID.fullmatch(ga):
        raise ValueError(f"GOOGLE_ANALYTICS must be a GA4 measurement id like 'G-AB12CD34EF', not {ga!r}")
    env.globals.update(site_title=SITE_TITLE, site_subtitle=SITE_SUBTITLE, site_url=site_url, base=base,
                       types=wiki.TYPES, counter=counter, ga=ga,
                       css_version=hashlib.sha256((ROOT / "static" / "style.css").read_bytes()).hexdigest()[:10])
    env.globals["has_tags"] = bool(tag_index(site.posts))
    env.globals["post_style"] = site.style
    env.globals["wiki_style"] = site.wiki_style
    env.globals["map_sprites"] = site.sprites
    env.globals["all_places"] = site.places
    env.globals["has_start"] = site.start is not None
    env.globals["start_party"] = site.start.party if site.start else []
    env.globals["start_fortune"] = bool(site.start and site.start.fortune)
    env.globals["start_first"] = site.posts[-1] if site.posts else None  # the first session, for the banner
    return env


def tag_index(posts: list[Post]) -> dict[str, list[Post]]:
    tags: dict[str, list[Post]] = {}
    for post in posts:
        for tag in post.tags:
            tags.setdefault(tag, []).append(post)
    return tags


def write_posts(site: Site, env: Environment, out_dir: Path, shares: dict, base: str) -> None:
    posts, places = site.posts, site.places
    leg_by_post = {leg["post"].slug: leg for leg in site.legs}
    years: dict[int, list[Post]] = {}
    for post in posts:  # the newest leads the list, marked Latest (no separate box; Chris, 2026-11-02)
        years.setdefault(post.date.year, []).append(post)
    write(out_dir / "index.html",
          env.get_template("index.html").render(share_page={"path": ""}, latest=posts[0] if posts else None, years=list(years.items()),
                                                first_with_pic=next((p for p in posts if p.card_pic), None),
                                                count=len(posts)))
    for i, post in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        write(out_dir / "posts" / post.slug / "index.html",
              env.get_template("post.html").render(
                  post=post, share_page=shares[post.path], body=rebase(post.html, base), newer=newer, older=older, legs=site.legs,
                  leg=leg_by_post.get(post.slug),
                  stops=[places[s] for s in leg_by_post[post.slug]["stops"]] if post.slug in leg_by_post else []))
    # The tags page and its menu link only exist once some post has tags.
    tags = tag_index(posts)
    if tags:
        write(out_dir / "tags" / "index.html",
              env.get_template("tags.html").render(share_page={"path": "tags/"}, tags=sorted(tags.items(), key=lambda kv: kv[0].lower())))


def write_wiki(site: Site, env: Environment, out_dir: Path, shares: dict, base: str) -> None:
    pages, places = site.pages, site.places
    groups = [(label, [w for w in pages if w.type == kind]) for kind, label in wiki.TYPES.items()]
    write(out_dir / "wiki" / "index.html",
          env.get_template("wiki_index.html").render(share_page={"path": "wiki/"}, groups=[g for g in groups if g[1]], count=len(pages)))
    for page in pages:
        write(out_dir / "wiki" / page.slug / "index.html",
              env.get_template("wiki_page.html").render(
                  page=page, share_page=shares[page.path], body=rebase(page.cited_html, base),
                  place=(places.get(site.parent.get(page.slug, "")) or site.landmarks.get(page.slug)) if places else None))


def map_data(site: Site) -> dict:
    """What the map page's script reads: every session by number, and each place's sessions."""
    related = barovia_map.place_sessions(site.legs, site.places, site.spots)
    summaries = {w.slug: w.summary for w in site.pages}
    return {
        # Every session by number (the slider's "Session N" line), including any off the map.
        "legs": [{"t": p.title, "u": p.path} for p in sorted(site.posts, key=lambda p: p.number)],
        "places": {p.slug: {"t": p.title, "u": p.path, "s": summaries.get(p.slug, ""),
                            # Every session tied to the place, oldest first, with its map number (i) and how
                            # it relates (k: here, ended, stop, near, from, past; w: the spot, for near), plus the
                            # skull, revive, party and leaves badges (b).
                            "sessions": [{"t": leg["post"].title, "u": leg["post"].path, "d": nice_date(leg["post"].date),
                                          "n": leg["post"].slide_count, "i": leg["n"], "k": kind,
                                          **({"b": leg["post"].life_badges} if leg["post"].party else {}),
                                          **({"w": where} if where else {})}
                                         for leg, kind, where in related.get(p.slug, [])]}
                   for p in site.places.values()},
    }


def write_map(site: Site, env: Environment, out_dir: Path) -> None:
    if not site.places:
        return
    write(out_dir / "map" / "barovia.svg", barovia_map.draw_base(site.sprites))
    write(out_dir / "map" / "index.html",
          env.get_template("map.html").render(share_page={"path": "map/"}, places=list(site.places.values()), legs=site.legs,
                                              map_data=map_data(site)))


def sitemap_paths(site: Site) -> list[str]:
    """Every page worth finding in a search engine, relative to the site root: the home page, posts
    (newest first), the wiki and its pages, the map and tags pages. Not search, 404 or forwarding pages."""
    paths = [""] + [p.path for p in site.posts] + ["wiki/"] + [w.path for w in site.pages]
    if site.places:
        paths.append("map/")
    if tag_index(site.posts):
        paths.append("tags/")
    return list(dict.fromkeys(paths))


def build_sitemap(paths: list[str], root: str) -> str:
    """sitemap.xml (sitemaps.org); root is the site's absolute address ending in '/'."""
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", ns)
    urlset = ET.Element(f"{{{ns}}}urlset")
    for path in paths:
        ET.SubElement(ET.SubElement(urlset, f"{{{ns}}}url"), f"{{{ns}}}loc").text = root + path
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(urlset, encoding="unicode") + "\n"


def robots_txt(root: str) -> str:
    """Crawl everything; the sitemap lists the pages. The publish workflow adds the PR-preview block."""
    return f"User-agent: *\nAllow: /\nSitemap: {root}sitemap.xml\n"


def write_extras(site: Site, env: Environment, out_dir: Path, site_url: str, base: str) -> None:
    """Search, the bot corpus, the 404 page, the feed, the sitemap, robots.txt and the forwarding pages."""
    write(out_dir / "search" / "index.html", env.get_template("search.html").render(share_page={"path": "search/"}))
    write(out_dir / "search-index.json", build_search_index(site.posts, site.pages))
    write(out_dir / "bot" / "corpus.json", build_bot_corpus(site.posts, site.pages, site_url + base))
    write(out_dir / "404.html", env.get_template("404.html").render())
    if site.start:
        write(out_dir / "start" / "index.html",
              env.get_template("start.html").render(share_page={"path": "start/"}, start=site.start))
    write(out_dir / "feed.xml", build_feed(site.posts, site_url + base))
    write(out_dir / "sitemap.xml", build_sitemap(sitemap_paths(site), site_url + base))
    write(out_dir / "robots.txt", robots_txt(site_url + base))
    redirects = site.map_file.parent / "redirects.yaml"
    write_redirects(out_dir, load_redirects(redirects), site.posts, base, load_redirects(redirects, "wiki"), site.pages)


def build(content_dir: Path = ROOT / "content" / "posts", out_dir: Path = ROOT / "public",
          site_url: str | None = None, base_path: str | None = None,
          wiki_dir: Path | None = None, map_file: Path | None = None,
          slides_static: Path | None = None, style_file: Path | None = None,
          party_file: Path | None = None, wiki_style_file: Path | None = None) -> list[Post]:
    site_url = (site_url or os.environ.get("URL") or DEFAULT_SITE_URL).rstrip("/")
    base = normalize_base_path(base_path or os.environ.get("BASE_PATH") or DEFAULT_BASE_PATH)
    site = prepare(content_dir, wiki_dir, map_file, slides_static, style_file, party_file, wiki_style_file)
    env = make_env(site, site_url, base)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(ROOT / "static", out_dir)
    make_thumbnails(site.pages, site.static_dir, out_dir)
    make_card_pictures(site.posts, site.static_dir, out_dir)
    make_start_pictures(site.start, site.static_dir, out_dir)
    shares = share_cards(site.posts, site.pages, site.static_dir, out_dir)
    env.globals.update(site_card=shares.pop(None), card_size=(share.CARD_W, share.CARD_H))
    write_posts(site, env, out_dir, shares, base)
    write_wiki(site, env, out_dir, shares, base)
    write_map(site, env, out_dir)
    write_extras(site, env, out_dir, site_url, base)
    return site.posts


def load_redirects(path: Path, section: str = "posts") -> dict[str, str]:
    """From data/redirects.yaml: {old post file stem: post file stem it was folded into}, or with
    section="wiki", {old wiki slug: wiki slug it was folded into}."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get(section) or {}).items()}


def forwarding_page(title: str, target: str, what: str) -> str:
    title = article.escape(title)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<title>{title}</title><link rel="canonical" href="{target}">'
            f'<meta http-equiv="refresh" content="0; url={target}"></head>'
            f'<body><p>This {what} moved to <a href="{target}">{title}</a>.</p></body></html>\n')


def write_redirects(out_dir: Path, redirects: dict[str, str], posts: list[Post], base: str,
                    wiki_redirects: dict[str, str] | None = None, pages: list[wiki.WikiPage] = ()) -> None:
    """Keep old post and wiki addresses working: a forwarding page at each old address."""
    by_stem = {p.source.stem: p for p in posts if p.source}
    by_slug = {w.slug: w for w in pages}
    for old, new in sorted((wiki_redirects or {}).items()):
        if new not in by_slug:
            raise ValueError(f"data/redirects.yaml: wiki {old} points at unknown wiki page {new}")
        if old in by_slug:
            raise ValueError(f"data/redirects.yaml: wiki {old} is still a page; remove it or the redirect")
        page = by_slug[new]
        write(out_dir / "wiki" / old / "index.html", forwarding_page(page.title, base + page.path, "page"))
    for old_stem, new_stem in sorted(redirects.items()):
        if new_stem not in by_stem:
            raise ValueError(f"data/redirects.yaml: {old_stem} points at unknown post {new_stem}")
        old, new = slug_from_filename(Path(old_stem)), by_stem[new_stem]
        write(out_dir / "posts" / old / "index.html", forwarding_page(new.title, base + new.path, "session"))


def serve(out_dir: Path, port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {out_dir} at http://localhost:{port}/ (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the adventure log into public/")
    parser.add_argument("--serve", action="store_true", help="serve public/ after building")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--base-path", help='path the site lives under, e.g. "/strahd-log/" '
                        '(default: $BASE_PATH or "/")')
    args = parser.parse_args(argv)
    site_url = f"http://localhost:{args.port}" if args.serve else None
    posts = build(site_url=site_url, base_path=args.base_path)
    print(f"Built {len(posts)} posts into {ROOT / 'public'}")
    if args.serve:
        serve(ROOT / "public", args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
