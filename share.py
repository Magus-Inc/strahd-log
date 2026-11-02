"""Link previews for Discord, iMessage, Facebook, X and the rest: a short snippet and a 1200x630 card
picture for every page, read by the Open Graph and Twitter card tags in templates/base.html."""

from __future__ import annotations

import hashlib
import html as htmllib
import re
import shutil
from pathlib import Path

import wiki

CARD_W, CARD_H = 1200, 630  # the 1.91:1 size Facebook, Discord, iMessage and X all show uncropped
LIMIT = 200  # characters; longer snippets get cut off mid-sentence by most apps
MIN_READ = 120  # a snippet shorter than this takes the next paragraph too
# The card for pages without a picture of their own (home, lists, wiki pages not yet drawn).
DEFAULT_PICTURE = "images/castle-ravenloft-ai.jpg"
DEFAULT_ALT = "Castle Ravenloft on its cliff above the village of Barovia"
BACKGROUND = (18, 16, 20)  # the site's page colour, #121014
RASTER = (".jpg", ".jpeg", ".png", ".webp", ".gif")  # what Pillow can turn into a card
# Cards already made, by name (which carries the picture's hash), so rebuilds and tests skip the work.
CACHE = Path(__file__).resolve().parent / ".cache" / "share"
PICTURE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)")
# "(<a href="/posts/x/">Title</a>, <a ...>, 3 June 2025)": the session citations after a wiki sentence.
CITATION = re.compile(r"\s*\(\s*<a\s[^>]*href=\"[^\"]*/posts/[^\"]*\"[^>]*>[^()]*\)", re.S)
PARAGRAPH = re.compile(r"<p>(.*?)</p>", re.S)
ASIDE = re.compile(r"<aside\b.*?</aside>", re.S)
SUBHEAD = re.compile(r"^<strong>(?:(?!</strong>).)*</strong>\s*<br\s*/?>\s*", re.S)
ITEM = re.compile(r"<(?:p|li)>(.*?)</(?:p|li)>", re.S)  # wiki facts from the log are list items


def snippet(text: str, limit: int = LIMIT) -> str:
    """Plain text on one line. Past limit characters it ends at the last full sentence, if that keeps
    most of the room, else at a word with "…"."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    sentences = [m.end() for m in re.finditer(r"[.!?][”’\"]?(?=\s)", text[:limit + 1])]
    if sentences and sentences[-1] >= limit * 0.6:
        return text[:sentences[-1]]
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:.—–-") + "…"


def sentence(text: str) -> str:
    """text ending in punctuation, so another sentence can follow it."""
    text = text.strip()
    return text if not text or text.endswith((".", "!", "?", "…", ":", "”", '"')) else text + "."


def paragraphs(html: str, pattern: re.Pattern = PARAGRAPH) -> list[str]:
    """Plain text of the prose paragraphs (quotes included), skipping pictures, captions in italics,
    margin notes, bold sub-headings and lists typed as one paragraph ("- Liren: Barbarian - ...")."""
    found = []
    html = ASIDE.sub("", html)  # margin notes and the glance callout
    for para in pattern.findall(html):
        body = SUBHEAD.sub("", para.strip())  # "<strong>Healing Gumbo</strong><br>" opens some old posts
        if (not body or body.startswith("<img") or re.fullmatch(r"<em>.*</em>", body, re.S)
                or re.fullmatch(r"<strong>.*</strong>", body, re.S)):  # a heading typed in bold
            continue
        text = wiki.plain_text(CITATION.sub("", body))
        if (not text or text.startswith(("Note:", "- ")) or text.count(" - ") >= 2 or re.search(r" - [\w’' ]+:", text)
                or (len(text) < 80 and not re.search(r"[.!?:…”\"]$", text))):  # a subtitle, not a sentence
            continue
        found.append(text)
    return found


def fill(parts: list[str], more: list[str], limit: int) -> str:
    """parts, then paragraphs from more until the snippet has enough to read (or ends on a colon,
    which leads into the next paragraph), cut to limit."""
    parts = [p for p in parts if p]
    for text in more:
        if parts and len(" ".join(parts)) >= MIN_READ and not parts[-1].endswith(":"):
            break
        if text not in parts:
            parts.append(text)
    return snippet(" ".join(sentence(p) if i < len(parts) - 1 else p for i, p in enumerate(parts)), limit)


def post_snippet(tagline: str, html: str, limit: int = LIMIT) -> str:
    """The post's tagline (its hook), then the story's opening lines."""
    return fill([tagline.strip().strip("*_").strip()], paragraphs(html), limit)


def wiki_snippet(summary: str, html: str, limit: int = LIMIT) -> str:
    """The page's summary, then its first prose paragraphs or facts from the log, without session
    citations or picture captions."""
    return fill([summary.strip()], paragraphs(html, ITEM), limit)


def alt_text(alt: str, title: str) -> str:
    """The picture's alt text, or the page title when it has none or only a file name ("IMG_1002.jpeg")."""
    alt = htmllib.unescape(alt).strip()
    return title if not alt or re.fullmatch(r"[\w .-]+\.(?:jpe?g|png|webp|gif)", alt, re.I) else alt


def first_picture(markdown: str, static_dir: Path) -> tuple[Path | str, str] | None:
    """(file, alt text) of the first picture in the text that lives on the site and exists, else
    (address, alt text) of the first one hosted elsewhere (a few old posts show the old blog's art)."""
    remote = None
    for alt, src in PICTURE.findall(markdown):
        if src.startswith(("http:", "https:")):
            if src.split("?")[0].lower().endswith(RASTER):
                remote = remote or (src, alt.strip())
            continue
        path = static_dir / src.split("?")[0].lstrip("/")
        if path.suffix.lower() in RASTER and path.is_file():
            return path, htmllib.unescape(alt).strip()
    return remote


def card_name(stem: str, source: Path) -> str:
    """images/share/<stem>-<hash>.jpg: the name changes with the picture, so apps that cache a link's
    preview by picture address pick up a new one."""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
    return f"images/share/{stem}-{digest}.jpg"


def make_card(source: Path, dest: Path) -> None:
    """A 1200x630 JPEG: the whole picture, centred, over a dark blurred copy of itself, so portraits
    and wide pictures alike show uncropped."""
    from PIL import Image, ImageEnhance, ImageFilter  # only the build needs Pillow
    with Image.open(source) as image:
        image.draft("RGB", (CARD_W, CARD_H))
        if image.mode in ("RGBA", "LA", "P"):  # see-through parts go on the site's dark background
            image = image.convert("RGBA")
            flat = Image.new("RGB", image.size, BACKGROUND)
            flat.paste(image, mask=image.getchannel("A"))
            image = flat
        image = image.convert("RGB")
    # Background: cover the card, blurred at low resolution (fast), then darkened.
    scale = max(CARD_W / image.width, CARD_H / image.height)
    small = image.resize((max(1, round(image.width * scale / 8)), max(1, round(image.height * scale / 8))))
    left, top = (small.width - CARD_W // 8) // 2, (small.height - CARD_H // 8) // 2
    back = small.crop((left, top, left + CARD_W // 8, top + CARD_H // 8)).filter(ImageFilter.GaussianBlur(3))
    card = ImageEnhance.Brightness(back.resize((CARD_W, CARD_H), Image.BILINEAR)).enhance(0.45)
    # Foreground: the whole picture, as large as fits.
    fit = min(CARD_W / image.width, CARD_H / image.height)
    front = image.resize((round(image.width * fit), round(image.height * fit)), Image.LANCZOS)
    card.paste(front, ((CARD_W - front.width) // 2, (CARD_H - front.height) // 2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest, "JPEG", quality=82, optimize=True, progressive=True)


def card(stem: str, source: Path, out_dir: Path) -> str:
    """Put the card for source in out_dir (made once, then copied from the cache) and return its
    address relative to the site root."""
    name = card_name(stem, source)
    cached = CACHE / Path(name).name
    if not cached.exists():
        make_card(source, cached)
    (out_dir / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, out_dir / name)
    return name
