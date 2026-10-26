import article
import build
import wiki

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
