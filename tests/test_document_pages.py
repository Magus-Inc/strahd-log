"""Pages for the texts the party read or heard (Chris, 2026-11-03, picked "all 12").

Like Fortune Reading, each page holds the text word for word, says where we came by it, and links
the session. Texts quoted in a post must match the post; texts from Ryan's Discord posts keep their
words and name their hidden discord- source.
"""
import re
from pathlib import Path

import pytest

import build
import wiki

ROOT = Path(__file__).resolve().parent.parent
WIKI, POSTS = ROOT / "content" / "wiki", ROOT / "content" / "posts"

# page -> (post it comes from, first words of the text, last words of the text)
FROM_POSTS = {
    "durst-manor-rhyme": ("2023-11-28-entering-durst-manor", "Beneath this dwelling", "servants of his brood."),
    "elisabeths-letter-to-drasha": ("2023-12-12-deeper-into-the-manor", "Drasha,", "Elisabeth"),
    "strahds-letter-to-elisabeth": ("2024-01-09-finishing-the-manor", "My most pathetic servant", "Strahd von Zarovich"),
    "guide-to-killing-vampires": ("2024-02-13-barovia-barovia", "In some shadowed corners", "while the vampire allows."),
    "arabelles-prophecy": ("2024-10-29-finding-arabelle", "In darkest night", "torment black."),
    "wachter-family-history": ("2024-12-17-delivery-for-lady-fiona", "The wedding of Prince Sergei", "of his return."),
    "the-gargoyle-s-riddle": ("2025-07-29-the-oath-the-spy-and-the-silver-moon", "When the dragon dreams", "this land of gloom."),
}
# page -> (session post slug, words that must stay, hidden source ids)
FROM_RYAN = {
    "fall-of-the-dusk-elves": ("a-doll-for-arabelle", ["Even now, nearly five centuries past", "And so here we have remained ever since."],
                               ["discord-ktsn7s", "discord-e7o9ho"]),
    "van-richtens-story": ("finding-arabelle", ["Until recently, he had been laying low", "weeping bitter tears for the sons and daughters of Barovia."],
                           ["discord-vmm5cm", "discord-gayizv", "discord-bs524v", "discord-ca1rve"]),
    "vow-of-the-silver-dragon": ("echoes-of-the-silver-dragon", ["I solemnly vow to uphold the virtues", "from this to the end of days."], ["discord-zhfe39"]),
    "argynvosts-journal": ("echoes-of-the-silver-dragon", ["My knights have fallen, and this land is lost.", "Now, to battle!"], ["discord-phtkme"]),
    "the-younger-of-the-twin-dragons": ("blood-and-oaths-under-moonligh", ["Seek out the younger of the twin dragons above.", "fill it once more."], ["discord-k74vij"]),
}


def words(text: str) -> str:
    """Quote text with Markdown marks, spacer dashes and line breaks taken out."""
    text = re.sub(r"(?m)^>\s?-?\s*$", "", text)
    text = re.sub(r"(?m)^>\s?", "", text).replace("*", "").replace("\\", "")
    return " ".join(text.split())


def quoted(text: str) -> str:
    return words("\n".join(line for line in text.splitlines() if line.startswith(">")))


def page_text(slug: str) -> str:
    return (WIKI / f"{slug}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", sorted(FROM_POSTS))
def test_a_text_from_a_post_is_on_its_page_word_for_word(slug):
    stem, first, last = FROM_POSTS[slug]
    post = quoted((POSTS / f"{stem}.md").read_text(encoding="utf-8"))
    ours = quoted(page_text(slug))
    assert ours.lstrip("“").startswith(first) and ours.rstrip("”").endswith(last)
    assert ours in post, f"{slug}: the page's text is not the post's, word for word"


@pytest.mark.parametrize("slug", sorted(FROM_RYAN))
def test_a_text_from_ryan_keeps_its_words_and_its_hidden_source(slug):
    post, kept, ids = FROM_RYAN[slug]
    text = page_text(slug)
    assert all(w in quoted(text) for w in kept)
    assert wiki.parse_wiki_page(WIKI / f"{slug}.md", build.split_front_matter).sources == ids


@pytest.mark.parametrize("slug", sorted({**FROM_POSTS, **FROM_RYAN}))
def test_every_document_page_says_where_we_came_by_it(slug):
    text = page_text(slug)
    post = FROM_POSTS[slug][0].split("-", 3)[3] if slug in FROM_POSTS else FROM_RYAN[slug][0]
    assert "## Description" in text and f"(/posts/{post}/)" in text.split("\n## ", 2)[1]
    assert "<!-- from-the-log -->" not in text or text.index("> ") < text.index("<!-- from-the-log -->")


def test_the_twin_dragons_page_does_not_say_who_spoke():
    # Chris, 2026-11-03: "hedge and say the party ran into that quote without specifying how or where"
    story = page_text("the-younger-of-the-twin-dragons").split("## The words")[0]
    assert "we came upon these words" in story and "Argynvostholt" not in story
    assert not re.search(r"\b(said|spoke|told|ghost|voice|wrote|carved|inscribed)\b", story.split("## Description")[1])


def test_pages_a_recap_names_in_passing_are_linked_by_hand():
    # The Finding Arabelle! recap names "Arabelle's prophecy" and "Van Richten's story", which its story never does.
    for slug in ["arabelles-prophecy", "van-richtens-story"]:
        assert wiki.parse_wiki_page(WIKI / f"{slug}.md", build.split_front_matter).link_by_hand
