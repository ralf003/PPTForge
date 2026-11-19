"""端到端冒烟测试：加载 spec → 渲染 → 质量门。"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from pptforge.engine.renderer import Renderer
from pptforge.gates.checks import run_gates
from pptforge.models import Deck

EXAMPLE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "sample_spec.yaml"


def test_load_and_validate() -> None:
    deck = Deck.load(EXAMPLE_SPEC)
    assert deck.validate() == []
    assert len(deck.pages) == 6


def test_render_end_to_end(tmp_path: Path) -> None:
    deck = Deck.load(EXAMPLE_SPEC)
    out = Renderer().save(deck, tmp_path / "deck.pptx")
    assert out.exists() and out.stat().st_size > 0

    prs = Presentation(out)
    assert len(prs.slides) == 6

    report = run_gates(prs)
    assert report.ok, report.issues


def test_invalid_deck_rejected() -> None:
    deck = Deck(title="", pages=[])
    assert deck.validate()
