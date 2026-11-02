"""Spell names the way the Curse of Strahd book does, in the posts, wiki pages and log extracts.

The list is data/spellings.yaml: {fix: {wrong spelling: right spelling}}. Word's transcripts and our
own notes spell names by ear ("Davien", "Kaven", "Emil Terescu"); the book fixes the spelling only.
What happened at the table still comes from the posts, and names Ryan made up stay as he said them.

    python tools/fix_spellings.py            # fix every file in place
    python tools/fix_spellings.py --check    # list misspellings, exit 1 if there are any

Matching is whole words and case-sensitive, longest name first. Link targets and URLs are left
alone (slugs change through data/redirects.yaml, not here). On a wiki page, aliases that the fix
made the same as the title or as another alias are dropped.
"""

from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPELLINGS = ROOT / "data" / "spellings.yaml"
DEFAULT_PATHS = [ROOT / "content" / "posts", ROOT / "content" / "wiki", ROOT / "data" / "log-extract"]
SUFFIXES = {".md", ".json", ".yaml"}
# Spans never touched: markdown link targets, bare URLs, and a post's slug and old-site address.
PROTECTED = re.compile(r"\]\([^)]*\)|https?://\S+|^(?:slug|obsidian_portal_url):.*$", re.M)


def load_keep(path: Path = SPELLINGS) -> set[str]:
    """Near-spellings the table means (a pun, an in-story rename): never reported by near_misses."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k) for k in (data.get("keep") or {})}


def _words(name: str) -> list[str]:
    name = name.replace("\u2019", "'").casefold()
    name = re.sub(r"'s\b", "", name)
    return re.findall(r"[^\W_]+", name)


def _same_name(a: str, b: str) -> bool:
    """One is a shorter or longer form of the other, or they differ only in spacing, hyphens,
    quotes, a possessive or a plural."""
    wa, wb = _words(a), _words(b)
    if set(wa) <= set(wb) or set(wb) <= set(wa):
        return True
    ja, jb = "".join(wa), "".join(wb)
    return ja.rstrip("s") == jb.rstrip("s")


def near_misses(pages: dict[str, list[str]], keep=frozenset(), cutoff: float = 0.7) -> list[tuple[str, str, str]]:
    """(page, alias, name) for each alias spelled almost, but not quite, like another name of the
    same page: "Sarepool crossroads" for "Tser Pool Crossroads", "Velaki" for "Vallaki". Only the
    words the two names don't share are compared, so "St." for "Saint" or "Count Strahd" for
    "Lord" pass. pages maps a page to its names, title first."""
    found = []
    for page, names in pages.items():
        for alias in names[1:]:
            if alias in keep:
                continue
            close = []
            for name in names:
                if name == alias or _same_name(alias, name):
                    continue
                wa, wn = _words(alias), _words(name)
                ours = "".join(w for w in wa if w not in wn)
                theirs = "".join(w for w in wn if w not in wa)
                ratio = SequenceMatcher(None, ours, theirs).ratio()
                if ratio >= cutoff:
                    close.append((ratio, name))
            if close:
                found.append((page, alias, max(close)[1]))
    return sorted(found)


def load_spellings(path: Path = SPELLINGS) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get("fix") or {}).items()}


def _pattern(spellings: dict[str, str]) -> re.Pattern:
    names = sorted(spellings, key=len, reverse=True)
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w])")


def fix_text(text: str, spellings: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Return the text with every wrong spelling replaced, and how often each was found."""
    if not spellings:
        return text, {}
    pattern, counts, out, pos = _pattern(spellings), {}, [], 0

    def fix(chunk: str) -> str:
        def one(m: re.Match) -> str:
            counts[m.group(0)] = counts.get(m.group(0), 0) + 1
            return spellings[m.group(0)]
        return pattern.sub(one, chunk)

    for m in PROTECTED.finditer(text):
        out += [fix(text[pos:m.start()]), m.group(0)]
        pos = m.end()
    out.append(fix(text[pos:]))
    return "".join(out), counts


def tidy_aliases(text: str) -> str:
    """In a page's front matter, drop alias lines that repeat the title or an earlier alias."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    lines = m.group(1).split("\n")
    title = next((ln[len("title:"):].strip().strip("'\"") for ln in lines if ln.startswith("title:")), "")
    seen, kept, in_aliases = {title.casefold()}, [], False
    for ln in lines:
        if re.match(r"^\w[\w-]*:", ln):
            in_aliases = ln.startswith("aliases:")
        elif in_aliases and ln.startswith("- "):
            name = ln[2:].strip().strip("'\"").casefold()
            if name in seen:
                continue
            seen.add(name)
        kept.append(ln)
    front = "\n".join(kept)
    front = re.sub(r"^aliases:\n(?=\w|\Z)", "", front + "\n", flags=re.M).rstrip("\n")
    return f"---\n{front}\n---\n" + text[m.end():]


def files(paths) -> list[Path]:
    out = []
    for p in map(Path, paths):
        out += sorted(f for f in p.rglob("*") if f.suffix in SUFFIXES) if p.is_dir() else [p]
    return out


def check(paths, spellings: dict[str, str]) -> list[tuple[str, str, str]]:
    """(file name, wrong spelling, right spelling) for each misspelling still in the files."""
    found = []
    for f in files(paths):
        if f.name == "corrections.yaml":
            continue  # its "same" groups list the old spellings on purpose
        _, counts = fix_text(f.read_text(encoding="utf-8"), spellings)
        found += [(f.name, wrong, spellings[wrong]) for wrong in sorted(counts)]
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", type=Path, default=DEFAULT_PATHS)
    ap.add_argument("--spellings", type=Path, default=SPELLINGS)
    ap.add_argument("--check", action="store_true", help="only list misspellings")
    args = ap.parse_args(argv)
    spellings = load_spellings(args.spellings)
    if args.check:
        found = check(args.paths, spellings)
        for name, wrong, right in found:
            print(f"{name}: {wrong} -> {right}")
        return 1 if found else 0
    total = 0
    for f in files(args.paths):
        if f.name == "corrections.yaml":
            continue
        old = f.read_text(encoding="utf-8")
        new, counts = fix_text(old, spellings)
        if "wiki" in f.parts and f.suffix == ".md":
            new = tidy_aliases(new)
        if new != old:
            f.write_text(new, encoding="utf-8", newline="\n")
            total += sum(counts.values())
            print(f"{f.name}: " + ", ".join(f"{w} -> {spellings[w]} x{n}" for w, n in sorted(counts.items())))
    print(f"{total} names fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
