"""The update-wiki skill carries Chris's rule for new people and places (2026-11-02)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "update-wiki" / "SKILL.md"


def test_new_people_and_places_get_the_dm_s_description_on_the_wiki():
    text = SKILL.read_text(encoding="utf-8")
    assert "New people and places carry their details here, not in the post" in text
    assert "`just wiki-plan <post> --session <session>`" in text
    assert "looks, clothes, voice, manner, the setting" in text


def test_the_details_are_retold_never_copied():
    text = SKILL.read_text(encoding="utf-8")
    assert "never copy the read-out" in text  # it is often the book's box text
    assert "never paste transcript lines into the site" in text
    assert "The book is good for spellings only" in text


def test_the_picture_prompt_uses_them_after_review():
    text = SKILL.read_text(encoding="utf-8")
    assert "reviewed against the posts and wiki before it goes to\n  Gemini" in text
    assert "picks the model from the picture's kind" in text


def test_agents_allows_transcript_descriptions_for_new_names():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "description from the session transcript" in text
