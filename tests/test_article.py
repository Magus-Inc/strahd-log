import re
from pathlib import Path

import article
import build
import wiki

ROOT = Path(__file__).resolve().parent.parent

POST = build.render_markdown("""## At a Glance:

* **Reunion:** Liren and Gumbo rise from the abbey well, after months away from the party and only hours for them.
* **The red door:** A hall of lost things.

## Characters:

* **Shabasta**: a bard

## Summary:

The party sleeps in the abbey. """ + "word " * 600 + """

### Key Locations:

> "Even the dead return for an encore."
""")


def test_reading_minutes():
    assert article.reading_minutes(POST) == 3
    assert article.reading_minutes("<p>short</p>") == 1


def test_heading_ids_and_toc_are_unique_and_ordered():
    html, toc = article.add_heading_ids(POST + "<h2>Summary:</h2>")
    assert [(h["level"], h["id"], h["text"]) for h in toc] == [
        (2, "at-a-glance", "At a Glance"), (2, "characters", "Characters"), (2, "summary", "Summary"),
        (3, "key-locations", "Key Locations"), (2, "summary-2", "Summary")]
    assert '<h2 id="summary-2">Summary:</h2>' in html


def test_glance_items_and_callout():
    items = article.glance_items(POST)
    assert len(items) == 2 and items[0].startswith("<strong>Reunion:</strong>")
    wrapped = article.wrap_glance(POST)
    assert wrapped.startswith('<aside class="callout glance"><h2>At a Glance:</h2>') and wrapped.count("<aside") == 1
    assert article.glance_items("<p>no glance</p>") == []


def test_teaser_uses_first_glance_bullet_without_its_label_and_trims():
    t = article.teaser(POST, limit=60)
    assert t.startswith("Liren and Gumbo rise") and t.endswith("…") and len(t) <= 61
    assert article.teaser("<p>Just a paragraph.</p>") == "Just a paragraph."


def test_cast_lists_mentioned_player_characters():
    pages = [wiki.WikiPage("liren", "Liren", type="character"), wiki.WikiPage("ireena", "Ireena", type="npc"),
             wiki.WikiPage("aera", "Aera", type="character")]
    assert [p.title for p in article.cast({"liren", "ireena", "aera"}, pages)] == ["Aera", "Liren"]


def test_deck_goes_after_the_glance_callout():
    html = article.add_deck(article.wrap_glance(POST), ["slides/x/01.webp", "slides/x/02.webp"])
    assert html.index('class="callout glance"') < html.index('class="deck"') < html.index("<h2>Characters")
    assert 'src="/slides/x/02.webp" alt="Slide 2 of 2"' in html
    assert "Download PDF" not in html


def test_deck_without_glance_goes_before_first_section_and_links_pdf():
    plain = build.render_markdown("# Title\n\nIntro.\n\n## Characters:\n\n* Shabasta\n")
    html = article.add_deck(plain, ["slides/x/01.webp"], "slides/x/deck.pdf")
    assert html.index("Intro.") < html.index('class="deck"') < html.index("<h2>Characters")
    assert '<a href="/slides/x/deck.pdf" download>Download PDF</a>' in html
    assert article.add_deck(plain, []) == plain


def test_two_decks_sit_one_after_the_other_with_a_vote_each():
    decks = [article.Deck("NotebookLM", "notebooklm", ["slides/x/01.webp", "slides/x/02.webp"]),
             article.Deck("Gemini", "gemini", ["slides/x/gemini/01.webp"], "slides/x/gemini/deck.pdf")]
    html = article.add_decks(article.wrap_glance(POST), decks)
    assert html.count("<h2>The Slides</h2>") == 1
    assert html.count('class="deck"') == 2
    label = '<p class="deck-label">{}</p>'
    assert html.index(label.format("NotebookLM")) < html.index(label.format("Gemini")) < html.index("<h2>Characters")
    assert html.index('data-vote="notebooklm"') < html.index('data-vote="gemini"')
    assert 'src="/slides/x/gemini/01.webp" alt="Gemini slide 1 of 1"' in html
    assert '<a href="/slides/x/gemini/deck.pdf" download>Download PDF</a>' in html
    assert "vote for your favorite" in html.lower()
    assert 'class="decks vote-group"' in html


def test_each_deck_can_carry_a_short_subheading_on_its_style():
    decks = [article.Deck("The Larders of Ill Omen", "larders", ["slides/x/01.webp"], note="The quick recap"),
             article.Deck("Drowning Shadows", "drowning", ["slides/x/b/01.webp"])]
    html = article.add_decks(article.wrap_glance(POST), decks)
    assert html.index('<p class="deck-label">The Larders of Ill Omen</p>') \
        < html.index('<p class="deck-note">The quick recap</p>') < html.index('data-vote="larders"')
    assert html.count('class="deck-note"') == 1


def test_one_deck_has_no_vote():
    html = article.add_decks(article.wrap_glance(POST), [article.Deck("", "main", ["slides/x/01.webp"])])
    assert html == article.add_deck(article.wrap_glance(POST), ["slides/x/01.webp"])
    assert "data-vote" not in html and "deck-label" not in html


def test_two_ai_pictures_in_a_row_each_get_a_vote():
    html = build.render_markdown("Intro.\n\n![Ismark in a tavern](/images/ismark-ai.jpg)\n\n"
                                 "![Ismark in a tavern](/images/ismark-ai-2.jpg)\n\n*AI-generated images.*\n")
    voted = article.add_image_votes(html)
    assert voted.count('class="vote-group image-vote"') == 1
    assert voted.index('src="/images/ismark-ai.jpg"') < voted.index('data-vote="image-1"') \
        < voted.index('src="/images/ismark-ai-2.jpg"') < voted.index('data-vote="image-2"')
    assert "vote for your favorite" in voted.lower()


def test_three_or_more_ai_pictures_vote_in_a_grid_that_opens_each_full_size():
    md = "".join(f"![Schlopkht take {i}](/images/schlopkht-ai{'' if i == 1 else f'-{i}'}.jpg)\n\n" for i in range(1, 7))
    voted = article.add_image_votes(build.render_markdown(md))
    assert voted.count('class="vote-group image-vote image-grid"') == 1
    assert [f"image-{i}" for i in range(1, 7)] == re.findall(r'data-vote="(image-\d+)"', voted)
    assert '<a href="/images/schlopkht-ai-4.jpg"' in voted  # tap a small picture to see it large
    pair = article.add_image_votes(build.render_markdown(
        "![Ismark](/images/ismark-ai.jpg)\n\n![Ismark](/images/ismark-ai-2.jpg)\n"))
    assert "image-grid" not in pair and "<a href" not in pair  # a pair stays full width, as before


def test_vote_grid_is_two_across_on_a_phone_and_three_on_a_wide_screen():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.image-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,", css)
    assert re.search(r"@media \(min-width: \d+px\)\s*\{[^@]*\.image-grid\s*\{[^}]*repeat\(3,", css)


def test_a_lone_or_non_ai_picture_gets_no_vote():
    lone = build.render_markdown("![Izek](/images/izek-ai.jpg)\n\nText.\n\n![Map](/images/map.jpg)\n")
    art = build.render_markdown("![Ireena](/images/ireena-by-ryan.webp)\n\n![Ireena](/images/ireena-2.webp)\n")
    assert article.add_image_votes(lone) == lone
    assert article.add_image_votes(art) == art


def test_deck_has_no_count_or_hint_text():
    html = article.add_deck(article.wrap_glance(POST), ["slides/x/01.webp", "slides/x/02.webp"])
    assert "deck-count" not in html and "deck-hint" not in html and "1 / 2" not in html
    assert "deck-meta" not in html  # no PDF, so nothing under the strip at all
