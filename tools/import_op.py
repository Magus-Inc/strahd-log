"""Import an Obsidian Portal adventure-log export into content/posts/ as Markdown.

The export folder holds posts/<slug>.textile (title:/date:/tagline:/tags: header lines, a blank
line, then the Textile body), posts/<slug>.html (the page as Obsidian Portal rendered it) and
manifest.csv. Each post becomes content/posts/YYYY-MM-DD-<slug>.md with YAML front matter.

Wiki links ([[Page]], [[Page | Text]], [[:character | Text]]) become ordinary Markdown links to the
real Obsidian Portal URL, taken from the matching rendered <a> in the post's HTML when there is
one. [[File:<id> | ... | name]] becomes an image from the rendered <img>. Re-running rewrites the
same files with the same bytes.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import markdownify
import textile
import yaml
from bs4 import BeautifulSoup

SITE = "https://curseofstrahdowlbear.obsidianportal.com"
TZ = ZoneInfo("America/Chicago")
HEADER_KEYS = ("title", "date", "tagline", "tags")
WIKI_RE = re.compile(r"\[\[(.+?)\]\]", re.S)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Post:
    slug: str
    meta: dict
    body: str  # Textile
    links: list[tuple[str, str]] = field(default_factory=list)  # rendered (text, href)
    images: dict[str, tuple[str, str]] = field(default_factory=dict)  # asset id -> (src, alt)


def parse_header(text: str) -> tuple[dict, str]:
    """Split the export's header lines (key: value) from the Textile body."""
    meta: dict = {}
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^(\w+):\s?(.*)$", lines[i])
        if not m or m.group(1) not in HEADER_KEYS:
            break
        meta[m.group(1)] = m.group(2).strip()
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return meta, "\n".join(lines[i:])


def parse_date(value: str) -> datetime:
    """'2026-09-01 5:00 PM' (Obsidian Portal's edit form) -> aware datetime in America/Chicago."""
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")


def wiki_slug(page: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", page.lower()).strip("-")


def split_wiki(inner: str) -> tuple[str, str]:
    """[[Page | Text]] -> (Page, Text); [[Page]] -> (Page, Page)."""
    parts = [p.strip() for p in inner.split("|")]
    page = parts[0]
    text = parts[-1] if len(parts) > 1 and parts[-1] else page.lstrip(":")
    return page, text


def fallback_href(page: str) -> str:
    if page.startswith(":"):
        return f"{SITE}/characters/{wiki_slug(page[1:])}"
    return f"{SITE}/wikis/{wiki_slug(page)}"


def absolute(href: str) -> str:
    return SITE + href if href.startswith("/") else href


def rendered_refs(html: str) -> tuple[list[tuple[str, str]], dict[str, tuple[str, str]]]:
    """Wiki anchors (in page order) and asset images from an Obsidian Portal post page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        classes = a.get("class") or []
        if any(c in ("wiki-content-link", "wiki-page-link") for c in classes):
            links.append((a.get_text().strip(), absolute(a["href"])))
    images = {}
    for img in soup.find_all("img", attrs={"data-asset-id": True}):
        images[img["data-asset-id"]] = (img["src"], img.get("alt", ""))
    return links, images


def resolve_links(post: Post) -> list[tuple[str, str, str]]:
    """Return (kind, text, url) for each [[...]] in the body, in order.

    When the post has as many rendered wiki anchors as Textile wiki links, they pair up in order.
    Otherwise each link looks for a rendered anchor with the expected URL, then falls back to it.
    """
    found = [m.group(1) for m in WIKI_RE.finditer(post.body)]
    wiki = [f for f in found if not f.strip().startswith("File:")]
    paired = iter(post.links) if len(wiki) == len(post.links) else None
    by_url = {href.rstrip("/").lower(): href for _, href in post.links}
    out = []
    for inner in found:
        if inner.strip().startswith("File:"):
            parts = [p.strip() for p in inner.strip()[5:].split("|")]
            asset, alt = parts[0], parts[-1]
            src, rendered_alt = post.images.get(
                asset, (f"https://db4sgowjqfwig.cloudfront.net/campaigns/319855/assets/{asset}/{alt}", alt)
            )
            out.append(("image", rendered_alt or alt, src))
            continue
        page, text = split_wiki(inner)
        want = fallback_href(page)
        if paired is not None:
            _, href = next(paired)
        else:
            href = by_url.get(want.lower(), want)
        out.append(("link", text, href))
    return out


def md_escape(text: str) -> str:
    return re.sub(r"([\[\]\\])", r"\\\1", text)


def fix_embeds(html: str) -> str:
    """Obsidian Portal oembed blocks (<div class=oembed><a href=img></a></div>) -> <img>/<a>."""
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.find_all("div", class_="oembed"):
        a = div.find("a", href=True)
        if a is None:
            div.unwrap()
            continue
        href = a["href"]
        new = soup.new_tag("p")
        if href.split("?")[0].lower().endswith(IMAGE_EXTS):
            new.append(soup.new_tag("img", src=href, alt=""))
        else:
            link = soup.new_tag("a", href=href)
            link.string = href
            new.append(link)
        div.replace_with(new)
    return str(soup)


def textile_to_markdown(body: str, refs: list[tuple[str, str, str]]) -> str:
    """Convert a Textile body to Markdown, swapping each [[...]] for its resolved link or image."""
    tokens = {}

    def stash(match: re.Match) -> str:
        token = f"zzwikiref{len(tokens):04d}zz"
        kind, text, url = refs[len(tokens)]
        tokens[token] = f"![{md_escape(text)}]({url})" if kind == "image" else f"[{md_escape(text)}]({url})"
        return token

    body = WIKI_RE.sub(stash, body)
    html = fix_embeds(textile.textile(body))
    md = markdownify.markdownify(html, heading_style="ATX", bullets="*", escape_misc=False)
    for token, link in tokens.items():
        md = md.replace(token, link)
    return tidy(md)


def tidy(md: str) -> str:
    lines = []
    for line in md.replace("\r\n", "\n").split("\n"):
        line = line.rstrip() if not line.endswith("  ") else line.rstrip() + "  "
        # "## **At a Glance:**" -> "## At a Glance:"
        m = re.match(r"^(#{1,6}) \*\*(.+)\*\*$", line)
        if m and "**" not in m.group(2):
            line = f"{m.group(1)} {m.group(2)}"
        lines.append(line)
    md = "\n".join(lines).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", md) + "\n"


def front_matter(meta: dict) -> str:
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n"


def read_manifest(export: Path) -> dict[str, dict]:
    path = export / "manifest.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row["slug"]: row for row in csv.DictReader(f)}


def load_post(textile_path: Path) -> Post:
    meta, body = parse_header(textile_path.read_text(encoding="utf-8"))
    post = Post(slug=textile_path.stem, meta=meta, body=body)
    html_path = textile_path.with_suffix(".html")
    if html_path.exists():
        post.links, post.images = rendered_refs(html_path.read_text(encoding="utf-8"))
    return post


def render_post(post: Post, manifest_row: dict | None = None) -> tuple[str, str]:
    """Return (file name, Markdown file text) for one post."""
    when = parse_date(post.meta["date"])
    meta = {"title": post.meta.get("title") or (manifest_row or {}).get("title") or post.slug}
    meta["date"] = when.isoformat()
    if post.meta.get("tagline"):
        meta["tagline"] = post.meta["tagline"]
    if post.meta.get("tags"):
        meta["tags"] = [t.strip() for t in re.split(r"[,;]", post.meta["tags"]) if t.strip()]
    meta["slug"] = post.slug
    meta["obsidian_portal_url"] = (manifest_row or {}).get("url") or f"{SITE}/adventure-log/{post.slug}"
    md = textile_to_markdown(post.body, resolve_links(post))
    return f"{when:%Y-%m-%d}-{post.slug}.md", front_matter(meta) + md


def import_export(export: Path, out_dir: Path) -> list[Path]:
    manifest = read_manifest(export)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for src in sorted((export / "posts").glob("*.textile")):
        post = load_post(src)
        name, text = render_post(post, manifest.get(post.slug))
        target = out_dir / name
        for stale in out_dir.glob(f"*-{post.slug}.md"):
            if stale != target and re.fullmatch(rf"\d{{4}}-\d\d-\d\d-{re.escape(post.slug)}\.md", stale.name):
                stale.unlink()
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8", newline="\n")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path, help="export folder with posts/ and manifest.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "content" / "posts")
    args = parser.parse_args(argv)
    if not (args.export / "posts").is_dir():
        parser.error(f"{args.export} has no posts/ folder")
    written = import_export(args.export, args.out)
    print(f"Imported {len(written)} posts into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
