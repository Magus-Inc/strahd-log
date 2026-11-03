"""Shared fixtures. The real blog takes about 5 seconds to build, so it is built once per test run
and every test file that checks the real site reads the same copy. Tests must not change it."""
from dataclasses import dataclass
from pathlib import Path

import pytest

import build

SITE_URL = "https://owlbear.dicelore.quest"


@dataclass(frozen=True)
class RealBuild:
    out: Path
    posts: tuple  # build.Post, newest first
    site_url: str = SITE_URL
    base_path: str = "/"


@pytest.fixture(scope="session")
def real_build(tmp_path_factory) -> RealBuild:
    """The whole blog, built from the repo's own posts, wiki and map."""
    out = tmp_path_factory.mktemp("real-site") / "public"
    posts = build.build(out_dir=out, site_url=SITE_URL, base_path="/")
    return RealBuild(out, tuple(posts))
