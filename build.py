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

import wiki

ROOT = Path(__file__).resolve().parent
SITE_TITLE = "Curse of Strahd: The Owlbear Chronicles"
SITE_SUBTITLE = "An adventure log from the mists of Barovia"
# Netlify sets URL to the site's main address during builds.
DEFAULT_SITE_URL = "http://localhost:8000"
# Where the site lives under its host: "/" on Netlify and locally, "/strahd-log/" on GitHub Pages.
DEFAULT_BASE_PATH = "/"


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

    @property
    def path(self) -> str:
        """Address relative to the site root; templates prefix it with the base path."""
        return f"posts/{self.slug}/"


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
    )


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=["extra", "sane_lists", "smarty"], output_format="html")


def rebase(html: str, prefix: str) -> str:
    """Point root-relative links in rendered Markdown ("/images/x.png") at prefix ("/strahd-log/" or
    an absolute site address), so post bodies can use /images/... whatever the base path."""
    return re.sub(r'((?:src|href)=")/(?!/)', lambda m: m.group(1) + prefix, html)


def link_wiki(posts: list[Post], pages: list[wiki.WikiPage]) -> None:
    """Link wiki names in posts and wiki pages, and record which posts mention each page."""
    linker = wiki.Linker(pages)
    by_slug = {w.slug: w for w in pages}
    for post in posts:  # newest first, so mentioned_in comes out newest first too
        post.html, post.mentions = linker.link(post.html)
        for slug in sorted(post.mentions):
            by_slug[slug].mentioned_in.append(post)
    for page in pages:
        page.html, _ = linker.link(render_markdown(page.body_md), self_slug=page.slug)


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
    entries = [{"t": p.title, "u": p.path, "l": nice_date(p.date), "x": wiki.plain_text(p.html)}
               for p in posts]
    entries += [{"t": w.title, "u": w.path, "l": wiki.LABELS[w.type],
                 "x": " ".join([*w.aliases, w.summary, wiki.plain_text(w.html).replace(wiki.LOG_NOTE, "")])}
                for w in pages]
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def build(content_dir: Path = ROOT / "content" / "posts", out_dir: Path = ROOT / "public",
          site_url: str | None = None, base_path: str | None = None,
          wiki_dir: Path | None = None) -> list[Post]:
    site_url = (site_url or os.environ.get("URL") or DEFAULT_SITE_URL).rstrip("/")
    base = normalize_base_path(base_path or os.environ.get("BASE_PATH") or DEFAULT_BASE_PATH)
    posts = load_posts(content_dir)
    pages = wiki.load_wiki(wiki_dir or content_dir.parent / "wiki", split_front_matter)
    link_wiki(posts, pages)
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["tag_slug"] = tag_slug
    env.filters["nice_date"] = nice_date
    env.globals.update(site_title=SITE_TITLE, site_subtitle=SITE_SUBTITLE, site_url=site_url, base=base,
                       types=wiki.TYPES)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(ROOT / "static", out_dir)

    write(out_dir / "index.html", env.get_template("index.html").render(posts=posts))
    for i, post in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        write(out_dir / "posts" / post.slug / "index.html",
              env.get_template("post.html").render(post=post, body=rebase(post.html, base),
                                                   newer=newer, older=older))

    tags: dict[str, list[Post]] = {}
    for post in posts:
        for tag in post.tags:
            tags.setdefault(tag, []).append(post)
    write(out_dir / "tags" / "index.html",
          env.get_template("tags.html").render(tags=sorted(tags.items(), key=lambda kv: kv[0].lower())))
    groups = [(label, [w for w in pages if w.type == kind]) for kind, label in wiki.TYPES.items()]
    write(out_dir / "wiki" / "index.html",
          env.get_template("wiki_index.html").render(groups=[g for g in groups if g[1]], count=len(pages)))
    for page in pages:
        write(out_dir / "wiki" / page.slug / "index.html",
              env.get_template("wiki_page.html").render(page=page, body=rebase(page.html, base)))
    write(out_dir / "search" / "index.html", env.get_template("search.html").render())
    write(out_dir / "search-index.json", build_search_index(posts, pages))
    write(out_dir / "404.html", env.get_template("404.html").render())
    write(out_dir / "feed.xml", build_feed(posts, site_url + base))
    return posts


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
