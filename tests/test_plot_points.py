"""Every Plot Points entry is told in Malron's Account (Chris, 2026-11-03: "Feels odd if they list
something that wasn't already mentioned above").

data/plot-points.yaml lists, for every post, each plot point (its opening words) and `told:`, one or
more phrases copied from that post's account that tell it. The account is the story as the reader
sees it, between "Malron's Account" and the recap lists, without margin notes (table talk). A new
post fails here until each of its plot points has an entry, and a phrase that later leaves the
story fails too. When a plot point is missing from the story, add it to the story from the
transcript, Chris's notes or Ryan's texts; never invent it."""
import html
import re
from pathlib import Path

import pytest
import yaml

import build

ROOT = Path(build.__file__).parent
DATA = ROOT / "data" / "plot-points.yaml"


def plain(text: str) -> str:
    """Text to compare: no tags, straight quotes, one space, any case."""
    text = re.sub(r"</?(?:a|strong|em|b|i|span)\b[^>]*>", "", text)  # inline: links, bold
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = text.translate(str.maketrans("‘’“”–—", "''\"\"--"))
    return re.sub(r"\s+", " ", text).strip().casefold()


def account(page: str) -> str:
    start = page.index('<h2 id="malron-s-account">')
    story = page[start:page.index("<!--story-end-->", start)]
    return plain(re.sub(r'<aside class="margin-note">.*?</aside>', " ", story, flags=re.S))


def plot_points(page: str) -> list[str]:
    m = re.search(r'<h2 id="plot-points">.*?</h2>(.*?)(?=<h2|<!--|</div>|$)', page, re.S)
    if not m:
        return []
    return [plain(li) for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S)]


def told(entry) -> list[str]:
    phrases = entry["told"]
    return [phrases] if isinstance(phrases, str) else list(phrases)


@pytest.fixture(scope="module")
def pages(real_build) -> dict[str, str]:
    """slug -> built page, for every post with a Plot Points list."""
    out = {}
    for post in real_build.posts:
        page = (real_build.out / "posts" / post.slug / "index.html").read_text(encoding="utf-8")
        if plot_points(page):
            out[post.slug] = page
    return out


@pytest.fixture(scope="module")
def data() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def test_every_post_with_plot_points_is_listed(pages, data):
    missing = sorted(set(pages) - set(data))
    assert not missing, f"add these posts to {DATA.name}: {missing}"
    extra = sorted(set(data) - set(pages))
    assert not extra, f"{DATA.name} lists posts with no Plot Points: {extra}"


def test_every_plot_point_is_told_in_the_account(pages, data):
    problems = []
    for slug, page in sorted(pages.items()):
        points = plot_points(page)
        entries = data.get(slug) or []
        story = account(page)
        for i, point in enumerate(points):
            if i >= len(entries):
                problems.append(f"{slug}: no entry for plot point {point[:70]!r}")
                continue
            entry = entries[i]
            if not point.startswith(plain(entry["point"])):
                problems.append(f"{slug}: entry {i + 1} is {entry['point']!r}, but plot point {i + 1} is {point[:70]!r}")
            for phrase in told(entry):
                if plain(phrase) not in story:
                    problems.append(f"{slug}: {entry['point']!r} says it is told as {phrase!r}, "
                                    "which is not in Malron's Account")
        if len(entries) > len(points):
            problems.append(f"{slug}: {len(entries) - len(points)} entries more than plot points")
    assert not problems, "\n".join(problems)


def test_no_post_with_plot_points_is_skipped(real_build, pages):
    """A Plot Points heading whose entries did not come out as a list would drop the post from the
    check silently; every post that has the heading in its Markdown must yield entries."""
    for post in real_build.posts:
        source = (ROOT / "content" / "posts").glob(f"*-{post.slug}.md")
        text = "".join(path.read_text(encoding="utf-8") for path in source)
        if re.search(r"^(?:## |\*\*)Plot Points", text, re.M):
            assert post.slug in pages, f"{post.slug}: its Plot Points did not render as a list"


def test_every_entry_names_a_phrase(data):
    empty = [f"{slug}: {e.get('point')!r}" for slug, entries in data.items() for e in entries
             if not e.get("told") or not told(e)]
    assert not empty, "\n".join(empty)


def test_phrases_are_long_enough_to_mean_something(data):
    """A word or two would match by chance; a phrase should carry the fact."""
    short = [f"{slug}: {phrase!r}" for slug, entries in data.items() for e in entries
             for phrase in told(e) if len(plain(phrase).split()) < 3]
    assert not short, "\n".join(short)


def test_account_skips_margin_notes():
    page = ('<h2 id="malron-s-account">Malron’s Account</h2><p>We ran.</p>'
            '<aside class="margin-note"><p>The DM rolled.</p></aside><!--story-end-->'
            '<h2 id="plot-points">Plot Points</h2><ul><li><strong>Run</strong>: We “ran”.</li></ul>')
    assert account(page).endswith("we ran.")
    assert "dm rolled" not in account(page)
    assert plot_points(page) == ['run: we "ran".']
