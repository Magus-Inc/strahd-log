"""Add what the adventure logs say about each character, place and thing to content/wiki/.

Input: one or more JSON files of entities extracted from the posts (by a person or a model), each
a list of {"name", "type", "aliases", "summary", "player"?, "facts": [{"text", "post"}]} where
"post" is a post's file name without ".md". Entities that share a name or alias are merged.

For a page that already exists, the facts go in a "From the adventure log" section after the
author's own text, and new aliases are added; nothing the author wrote is changed. Entities with
no page get a new draft page marked as compiled from the log. Re-running replaces only the
compiled parts, so it is safe to run again after the extraction is redone.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MARKER = "<!-- from-the-log -->"
TYPES = {"character", "npc", "creature", "place", "item", "faction", "deity", "other"}
# Words that are names in one sentence and ordinary words in the next; never used as aliases.
GENERIC = {
    "abbot", "baron", "baroness", "bishop", "brother", "captain", "count", "devil", "father",
    "god", "guard", "king", "lady", "lord", "master", "mayor", "mother", "priest", "queen",
    "sister", "the", "village", "castle", "church", "tower", "town", "abbey", "temple",
    "ethereal",
}


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def split_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text.replace("\r\n", "\n"), re.S)
    return (yaml.safe_load(m.group(1)) or {}, m.group(2)) if m else ({}, text)


def merge_entities(entities: list[dict]) -> list[list[dict]]:
    """Group entities that share any name or alias (case-insensitive)."""
    parent = list(range(len(entities)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[str, int] = {}
    for i, e in enumerate(entities):
        for name in [e["name"], *e.get("aliases", [])]:
            key = name.strip().lower()
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    groups: dict[int, list[dict]] = defaultdict(list)
    for i, e in enumerate(entities):
        groups[find(i)].append(e)
    return list(groups.values())


def usable_alias(name: str) -> bool:
    return len(name) >= 3 and name[0].isupper() and name.lower() not in GENERIC


def load_posts(posts_dir: Path) -> dict[str, tuple[str, str]]:
    """{file stem: (slug, title)}"""
    posts = {}
    for path in posts_dir.glob("*.md"):
        meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
        slug = meta.get("slug") or re.sub(r"^\d{4}-\d\d-\d\d-", "", path.stem)
        posts[path.stem] = (slug, str(meta.get("title", slug)))
    return posts


def fact_lines(group: list[dict], posts: dict[str, tuple[str, str]]) -> list[str]:
    facts, seen = [], set()
    for e in group:
        for f in e.get("facts", []):
            stem = f.get("post", "")
            if stem not in posts or f["text"] in seen:
                continue
            seen.add(f["text"])
            facts.append((stem, f["text"].strip().rstrip(".") + "."))
    facts.sort(key=lambda sf: sf[0])  # file names start with the date
    return [f"* {text} ([{posts[stem][1]}](/posts/{posts[stem][0]}/))" for stem, text in facts]


def log_section(lines: list[str]) -> str:
    return (f"{MARKER}\n## From the adventure log\n\n"
            "*Compiled from the session posts. Each line links to the session it comes from.*\n\n"
            + "\n".join(lines) + "\n")


def apply(extract_files: list[Path], wiki_dir: Path, posts_dir: Path) -> tuple[int, int]:
    """Return (pages updated, pages created)."""
    entities = [e for f in extract_files for e in json.loads(f.read_text(encoding="utf-8"))]
    posts = load_posts(posts_dir)
    wiki_dir.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Path] = {}  # lower-case name -> page file
    for path in sorted(wiki_dir.glob("*.md")):
        meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
        for name in [meta.get("title", ""), *(meta.get("aliases") or [])]:
            existing.setdefault(str(name).lower(), path)
    taken = set(existing)  # names already claimed, so no two pages share an alias

    updated = created = 0
    groups = merge_entities(entities)
    # Bigger groups first, so the best-attested entity keeps a contested alias.
    groups.sort(key=lambda g: -sum(len(e.get("facts", [])) for e in g))
    for group in groups:
        names = Counter(n for e in group for n in [e["name"], *e.get("aliases", [])])
        page = next((existing[n.lower()] for n in names if n.lower() in existing), None)
        lines = fact_lines(group, posts)
        if page is None:
            title = max((e["name"] for e in group), key=lambda n: (names[n], len(n.split()), len(n)))
            if title.lower() in taken or not lines:
                continue
            kinds = Counter(e.get("type", "other") for e in group)
            kind = kinds.most_common(1)[0][0]
            meta = {"title": title, "type": kind if kind in TYPES else "other"}
            body_prefix = ""
            page = wiki_dir / f"{slugify(title)}.md"
            if page.exists():
                continue
            created += 1
        else:
            meta, body = split_front_matter(page.read_text(encoding="utf-8"))
            body_prefix = body.split(MARKER)[0].strip("\n")
            updated += 1
        aliases = list(meta.get("aliases") or [])
        for name, _count in names.most_common():
            if name != meta["title"] and name not in aliases and usable_alias(name) and name.lower() not in taken:
                aliases.append(name)
        for name in [meta["title"], *aliases]:
            taken.add(name.lower())
        if aliases:
            meta["aliases"] = aliases
        if not meta.get("summary"):
            summary = next((e["summary"] for e in group if e.get("summary")), "")
            if summary:
                meta["summary"] = summary
        player = next((e["player"] for e in group if e.get("player")), "")
        if player and not meta.get("player"):
            meta["player"] = player
        meta.setdefault("source", "Compiled from the adventure log")
        order = ["title", "type", "aliases", "summary", "player", "source", "obsidian_portal_url"]
        meta = {k: meta[k] for k in order if k in meta} | {k: v for k, v in meta.items() if k not in order}
        body = (body_prefix + "\n\n" if body_prefix.strip() else "") + log_section(lines)
        text = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n" + body
        page.write_text(text, encoding="utf-8", newline="\n")
    return updated, created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge entities extracted from the posts into the wiki")
    parser.add_argument("extract", type=Path, nargs="*",
                        help="JSON entity files (default: data/log-extract/*.json)")
    parser.add_argument("--wiki", type=Path, default=ROOT / "content" / "wiki")
    parser.add_argument("--posts", type=Path, default=ROOT / "content" / "posts")
    args = parser.parse_args(argv)
    files = args.extract or sorted((ROOT / "data" / "log-extract").glob("*.json"))
    updated, created = apply(files, args.wiki, args.posts)
    print(f"Updated {updated} wiki pages and created {created} from the adventure log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
