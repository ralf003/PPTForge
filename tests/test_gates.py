"""质量门回归测试：既验证正例通过，也验证反例被抓。"""

from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.util import Inches

from pptforge.engine.renderer import Renderer
from pptforge.gates.checks import run_gates


def _slide(renderer: Renderer, bg: str = "F4F6FA"):
    return renderer._add_slide(bg)


def test_clean_page_passes() -> None:
    r = Renderer()
    s = _slide(r)
    r._add_text(s, 1.0, 0.6, 11.0, 0.9, [("正常标题", 32, "0B1F3A", True)])
    r._add_text(s, 1.0, 2.0, 11.0, 0.6, [("正常正文一行", 18, "4B5563", False)])
    assert run_gates(r.prs).ok


def test_text_overflow_detected() -> None:
    """框太矮装不下长标题，会压到相邻元素。"""
    r = Renderer()
    s = _slide(r)
    long_title = "规模化的瓶颈是长程轨迹与治理，不是模型能力这句话很长很长"
    r._add_text(s, 1.0, 0.5, 11.4, 0.55, [(long_title, 32, "0B1F3A", True)])
    issues = run_gates(r.prs).issues
    assert any("文本溢出" in i for i in issues)


def test_text_overlap_detected() -> None:
    r = Renderer()
    s = _slide(r)
    r._add_text(s, 1.0, 2.0, 5.0, 1.0, [("上块", 22, "0B1F3A", True)])
    r._add_text(s, 1.5, 2.2, 5.0, 1.0, [("下块", 22, "0B1F3A", True)])
    issues = run_gates(r.prs).issues
    assert any("文本框重叠" in i for i in issues)


def test_low_contrast_on_light_bg_detected() -> None:
    """浅底上的青色小字对比度不足，必须报。"""
    r = Renderer()
    s = _slide(r)
    r._add_text(s, 1.0, 5.0, 6.0, 0.4, [("浅底看不清", 14, "22D3EE", False)])
    issues = run_gates(r.prs).issues
    assert any("对比度" in i for i in issues)


def test_white_text_on_dark_block_not_flagged() -> None:
    """深色色块上的白字不应误报：背景按文字实际压住的色块取。"""
    r = Renderer()
    s = _slide(r)
    block = s.shapes.add_shape(1, Inches(0), Inches(5.9), Inches(13.333), Inches(1.6))
    block.fill.solid()
    block.fill.fore_color.rgb = RGBColor.from_string("0B1F3A")
    block.line.fill.background()
    block.shadow.inherit = False
    r._add_text(s, 0.95, 6.05, 11.6, 0.6, [("深色条上的白字", 26, "FFFFFF", True)])
    assert run_gates(r.prs).ok
