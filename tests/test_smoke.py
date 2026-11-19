"""端到端冒烟测试：加载 spec → 渲染 → 质量门。"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from pptforge.engine.renderer import Renderer
from pptforge.gates.checks import _contrast_ratio, run_gates
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


def test_contrast_ratio_standard() -> None:
    assert round(_contrast_ratio("000000", "FFFFFF"), 2) == 21.0


def test_gates_catch_bounds_and_contrast() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor.from_string("FFFFFF")
    bg.line.fill.background()

    # 越界矩形
    bad = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(12), Inches(6), Inches(3), Inches(3)
    )
    bad.fill.solid()
    bad.fill.fore_color.rgb = RGBColor.from_string("1F6FEB")
    bad.line.fill.background()

    # 低对比度文字
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "低对比度文字"
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor.from_string("DDDDDD")
    run.font.name = "Microsoft YaHei"

    report = run_gates(prs)
    assert not report.ok
    assert any("越界" in i for i in report.issues)
    assert any("对比度" in i for i in report.issues)
