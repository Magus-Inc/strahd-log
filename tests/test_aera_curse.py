"""Aera's werewolf curse (Chris, 2026-11-04: "I thought we undid that with a spell"). Chris's notes
for 5/13/2025 say Oogway cast Remove Curse on her before she drank the blood in Strahd's hourglass
game, and the blood turned her fully into a werewolf anyway. Nothing later records a cure or a
change, and Chris is not sure (2026-11-04: "leave it open"), so her page tells the spell and the
change in that order, each citing the session, and says nobody knows whether the curse still holds."""
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


def test_aera_story_leaves_the_curse_open():
    story, _ = _parts("aera-shan-ravanor")
    assert "whether the curse still holds" in story


def test_malron_remembers_that_night_as_a_blur():
    """Chris, 2026-11-04: play the gap off as Malron's hazy, shaken memory of Strahd's game."""
    story, _ = _parts("aera-shan-ravanor")
    assert "blur" in story and "bad dream" in story


def test_malron_tells_his_price_and_lathanders_help():
    """Chris, 2026-11-04: Malron was told he would lose his spells for three days, and he believes
    Lathander heard his silent prayers and meditation, lifted the curse and rewarded his faith."""
    story, log = _parts("malron-lichtstrahl")
    assert "three days" in story and "Lathander" in story and POST in story
    line = next(l for l in log.splitlines() if "Strahd's game" in l)
    assert "three days" in line and "Lathander" in line


def test_post_matches_and_tells_malrons_anguish():
    """Chris, 2026-11-04: the session post matches the wiki and holds the most of Malron's inner
    thoughts, which explain why the rest of that night's record is hazy."""
    text = (ROOT / "content" / "posts" / "2025-05-13-blood-and-oaths-under-moonligh.md").read_text(encoding="utf-8")
    story = text.split("## Key Locations")[0]
    assert "a day of silence" not in story
    assert "three days" in story and "Lathander" in story
    assert "blur" in story and "bad dream" in story
    assert "whether her curse still holds" in story
