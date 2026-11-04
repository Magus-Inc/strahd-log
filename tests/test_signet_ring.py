"""The signet ring's wiki picture shows the sigil that opened Khazan's tower (Chris, 2026-11-04)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "content" / "wiki" / "signet-ring.md"
IMAGES = ROOT / "static" / "images"


def test_signet_ring_has_its_picture():
    body = PAGE.read_text(encoding="utf-8")
    assert "/images/signet-ring-ai.jpg" in body
    assert (IMAGES / "signet-ring-ai.jpg").exists() and (IMAGES / "full" / "signet-ring-ai.jpg").exists()


def test_signet_ring_picture_has_the_ai_credit_and_names_the_seal():
    body = PAGE.read_text(encoding="utf-8")
    picture = body.index("/images/signet-ring-ai.jpg")
    assert "*AI-generated image (Google Gemini).*" in body[picture:picture + 200]
    alt = body[body.rindex("![", 0, picture):picture]
    assert "seal" in alt.lower() or "sigil" in alt.lower()
