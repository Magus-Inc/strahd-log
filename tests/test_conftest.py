"""The real blog is built once per test run (tests/conftest.py), not once per test file."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_only_conftest_builds_the_real_site():
    # build.build(out_dir=...) with no content folder builds the repo's own posts: about 5 s each.
    # Allowed: the repeatability check (a second build on purpose) and the PR preview test (another
    # base path).
    real = re.compile(r"build\.build\(\s*out_dir=")
    allowed = ("conftest.py", "test_conftest.py", "test_site_diff.py", "test_pr_previews.py")
    builders = sorted(p.name for p in (ROOT / "tests").glob("*.py")
                      if p.name not in allowed
                      and real.search(p.read_text(encoding="utf-8")))
    assert builders == []


def test_real_build_is_shared(real_build):
    assert (real_build.out / "index.html").exists()
    assert real_build.posts, "the fixture keeps the built posts for tests that read them"
