"""GitHub Pages is the only host (Chris, 2026-11-02): no Netlify settings or mentions are left."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", ".venv", "public", ".cache", ".previews", "content", "__pycache__", "node_modules"}


def repo_text_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP for part in path.relative_to(ROOT).parts) or not path.is_file():
            continue
        if path.suffix in {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".html", ".js", ".css"} \
                or path.name in {"justfile"}:
            yield path


def test_no_netlify_settings_file():
    assert not (ROOT / "netlify.toml").exists()


def test_nothing_mentions_netlify():
    me = Path(__file__).resolve()
    mentions = sorted(p.relative_to(ROOT).as_posix() for p in repo_text_files()
                      if p.resolve() != me and "netlify" in p.read_text(encoding="utf-8", errors="ignore").lower())
    assert mentions == []
