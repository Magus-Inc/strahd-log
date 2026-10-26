"""Import Obsidian Portal character and wiki pages into content/wiki/, and point posts at them.

The input is a JSON export made in a signed-in browser (Obsidian Portal puts a bot check in front
of scripted requests): {"/characters/<slug>" or "/wikis/<slug>": {"title", "final", "md"}}, where
"md" is the page's main content already converted to Markdown and "final" is the address the
page redirected to. Each page becomes content/wiki/<slug>.md, written as the author wrote it,
without Obsidian Portal's footer. Links between pages, and the Obsidian Portal links in posts,
are rewritten to the local wiki. Re-running gives the same files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://curseofstrahdowlbear.obsidianportal.com"

# Obsidian Portal pages that are not wiki content: the editor's template, and index pages the
# site's own wiki index replaces. Raw session notes ("/wikis/notes-...") are not published either;
# links to any skipped page become plain text.
SKIP = {"/characters/minofaustus-s-character", "/wikis/main-page", "/wikis/raw-notes"}


def skipped(path: str) -> bool:
    return path in SKIP or path.startswith("/wikis/notes-")
# Pages folded into another page: "Manor" was the party's name for Durst Manor before they knew.
MERGE = {"/wikis/manor": "/wikis/durst-manor"}
# Wiki page type by Obsidian Portal address; characters are always "character".
TYPES = {
    "barovia": "place", "daggerford": "place", "durst-manor": "place",
    "fortune-reading": "other",
}
# Images that already live in static/images/.
LOCAL_IMAGES = {
    "durst_floor1__Small_.jpg": "/images/entering-durst-manor-1.jpg",
    "durst_floor2__Small_.jpg": "/images/entering-durst-manor-2.jpg",
}


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def clean_markdown(md: str, title: str) -> tuple[str, str]:
    """Strip Obsidian Portal's chrome; return (summary from the italic subtitle, body)."""
    md = md.replace("\r\n", "\n")
    # Footer: "# <title>", campaign name, author names and timestamps.
    md = re.split(rf"\n# {re.escape(title)}\n\nCurse of Strahd - owlbear\n", md)[0]
    md = re.sub(rf"^## {re.escape(title)}(\n+|$)", "", md.strip())
    summary = ""
    m = re.match(r"^\*([^*\n]+)\*(\n+|$)", md)
    if m:
        summary, md = m.group(1).strip(), md[m.end():]
    md = re.sub(r"^\* \[notes\]\(/search\)\n*", "", md, flags=re.M)
    md = re.sub(r"^#{1,6} (Description|Bio):[ \t]*$", r"## \1", md, flags=re.M)
    for name, local in LOCAL_IMAGES.items():
        md = re.sub(rf"\]\(https://[^)]*/{re.escape(name)}\)", f"]({local})", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    # A body that only repeats the title says nothing.
    if md.strip() == title:
        md = ""
    return summary, md


def import_pages(export: dict, wiki_dir: Path, posts_dir: Path) -> dict[str, str]:
    """Write wiki pages; return {Obsidian Portal path: local wiki address}."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    pages, addresses, unlinked = {}, {}, set()
    for path, page in export.items():
        if skipped(path):
            unlinked.add(path)
            continue
        if page["final"].startswith("/adventure-log/"):
            addresses[path] = f"/posts/{page['final'].rsplit('/', 1)[1]}/"
            continue
        pages[path] = page
    for path, page in pages.items():
        target = MERGE.get(path, path)
        addresses[path] = f"/wiki/{slugify(pages[target]['title'])}/"

    def relink(md: str) -> str:
        # A line that is only a pointer to a skipped page ("Raw Notes: [Notes - ...](...)") goes.
        def drop(m: re.Match) -> str:
            href = m.group(1).split("#")[0].rstrip("/").removeprefix(SITE)
            return "" if href in unlinked or skipped(href) else m.group(0)
        md = re.sub(r"^(?:[\w ]+:\s*)?\[[^\]]*\]\(([^)\s]+)\)[ \t]*\n?", drop, md, flags=re.M)

        def swap(m: re.Match) -> str:
            href = m.group(2).split("#")[0].rstrip("/")
            href = href.removeprefix(SITE)
            if href in unlinked or skipped(href):
                return m.group(1)
            return f"[{m.group(1)}]({addresses[href]})" if href in addresses else m.group(0)
        return re.sub(r"\[([^\]]*)\]\(((?:" + re.escape(SITE) + r")?/(?:wikis|characters)/[^)\s]+)\)", swap, md)

    merged: dict[str, dict] = {}
    for path, page in pages.items():
        summary, body = clean_markdown(page["md"], page["title"])
        target = MERGE.get(path, path)
        entry = merged.setdefault(target, {"title": pages[target]["title"], "summary": "", "parts": [],
                                           "path": target, "aliases": []})
        if target != path:
            entry["aliases"].append(page["title"])
            if body:
                entry["parts"].append(f"## As “{page['title']}”\n\n{body}")
        else:
            entry["summary"] = summary
            if body:
                entry["parts"].insert(0, body)

    written = []
    for path, entry in merged.items():
        kind = "character" if path.startswith("/characters/") else TYPES.get(path.rsplit("/", 1)[1], "npc")
        meta = {"title": entry["title"], "type": kind}
        if entry["aliases"]:
            meta["aliases"] = entry["aliases"]
        if entry["summary"]:
            meta["summary"] = entry["summary"]
        meta["source"] = "Written on Obsidian Portal"
        meta["obsidian_portal_url"] = SITE + path
        body = relink("\n\n".join(entry["parts"]))
        slug = addresses[path].strip("/").rsplit("/", 1)[1]
        text = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n" + body + "\n"
        target = wiki_dir / f"{slug}.md"
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        # Keep anything the log-extraction step added below the imported text.
        marker = "<!-- from-the-log -->"
        if marker in existing:
            text = text.rstrip("\n") + "\n\n" + existing[existing.index(marker):]
        if existing != text:
            target.write_text(text, encoding="utf-8", newline="\n")
        written.append(target)

    for post in sorted(posts_dir.glob("*.md")):
        text = post.read_text(encoding="utf-8")
        new = relink(text)
        if new != text:
            post.write_text(new, encoding="utf-8", newline="\n")
    return addresses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Obsidian Portal wiki and character pages")
    parser.add_argument("export", type=Path, help="JSON export of the pages (see module docstring)")
    parser.add_argument("--wiki", type=Path, default=ROOT / "content" / "wiki")
    parser.add_argument("--posts", type=Path, default=ROOT / "content" / "posts")
    args = parser.parse_args(argv)
    export = json.loads(args.export.read_text(encoding="utf-8"))
    addresses = import_pages(export, args.wiki, args.posts)
    print(f"Imported {sum(1 for a in addresses.values() if a.startswith('/wiki/'))} pages into {args.wiki}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
