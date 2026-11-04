"""Aera's werewolf curse (Chris, 2026-11-04: "I thought we undid that with a spell"). Chris's notes
for 5/13/2025 say Oogway cast Remove Curse on her before she drank the blood in Strahd's hourglass
game, and the blood turned her fully into a werewolf anyway. Nothing later records a cure, so her
page tells the spell and the change in that order, each citing the session."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POST = "(/posts/blood-and-oaths-under-moonligh/)"


def _parts(slug):
    text = (ROOT / "content" / "wiki" / f"{slug}.md").read_text(encoding="utf-8")
    story, _, log = text.partition("<!-- from-the-log -->")
    return story, log


def test_aera_story_tells_the_spell_before_the_change():
    story, _ = _parts("aera-shan-ravanor")
    assert "Oogway" in story and "Remove Curse" in story
    assert story.index("Remove Curse") < story.index("fully into a werewolf")
    assert POST in story


def test_aera_log_line_keeps_the_spell():
    _, log = _parts("aera-shan-ravanor")
    line = next(l for l in log.splitlines() if "Strahd's game" in l and "werewolf" in l)
    assert "Remove Curse" in line and POST in line


def test_oogway_log_has_the_spell():
    _, log = _parts("oogway")
    assert any("Remove Curse" in l and "Aera" in l and POST in l for l in log.splitlines())
