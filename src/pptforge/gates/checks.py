"""质量门：对生成的 PPTX 做静态硬检查。

覆盖：
- 字体名与投影级字号；
- 元素几何越界（形状不得超出画布）；
- 文字与页面背景的 WCAG 对比度（AA）。
视觉留白/精确文本溢出由渲染回看与后续门补充。
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.oxml.ns import qn
from pptx.presentation import Presentation
from pptx.util import Inches

from pptforge.theme import FONT_FAMILY

# 投影级最小字号（pt），脚注为全稿下限
MIN_RUN_SIZE = 13

# WCAG AA 对比度阈值
CONTRAST_BODY = 4.5
CONTRAST_LARGE = 3.0
LARGE_TEXT_PT = 18
BOLD_LARGE_TEXT_PT = 14

# 几何容差：允许贴边，不允许实质越界
_TOL_EMU = Inches(0.02)


@dataclass
class GateReport:
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


def _run_font_names(run) -> set[str]:
    names = set()
    if run.font.name:
        names.add(run.font.name)
    rPr = run._r.find(qn("a:rPr"))
    if rPr is not None:
        for tag in ("a:ea", "a:cs"):
            el = rPr.find(qn(tag))
            if el is not None and el.get("typeface"):
                names.add(el.get("typeface"))
    return names


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    lum_a = _relative_luminance(hex_a)
    lum_b = _relative_luminance(hex_b)
    hi, lo = max(lum_a, lum_b), min(lum_a, lum_b)
    return (hi + 0.05) / (lo + 0.05)


def _slide_background_hex(slide, width: int, height: int) -> str | None:
    """提取铺满画布的背景矩形填充色；找不到返回 None。"""
    for shape in slide.shapes:
        if shape.left is None or shape.width is None:
            continue
        if (
            abs(shape.left) <= _TOL_EMU
            and abs(shape.top) <= _TOL_EMU
            and abs(shape.width - width) <= _TOL_EMU
            and abs(shape.height - height) <= _TOL_EMU
        ):
            try:
                return str(shape.fill.fore_color.rgb)
            except Exception:
                continue
    return None


def _check_fonts(slide_idx: int, slide, issues: list[str]) -> None:
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                names = _run_font_names(run)
                if names and FONT_FAMILY not in names:
                    issues.append(
                        f"P{slide_idx} 字体非{FONT_FAMILY}：{run.text[:20]!r} -> {names}"
                    )
                if run.font.size is not None:
                    size_pt = run.font.size.pt
                    if size_pt < MIN_RUN_SIZE:
                        issues.append(
                            f"P{slide_idx} 字号 {size_pt}pt 低于下限"
                            f" {MIN_RUN_SIZE}：{run.text[:20]!r}"
                        )


def _check_bounds(
    slide_idx: int, slide, width: int, height: int, issues: list[str]
) -> None:
    for shape in slide.shapes:
        if shape.left is None or shape.top is None:
            continue
        right = shape.left + shape.width
        bottom = shape.top + shape.height
        if (
            shape.left < -_TOL_EMU
            or shape.top < -_TOL_EMU
            or right > width + _TOL_EMU
            or bottom > height + _TOL_EMU
        ):
            issues.append(
                f"P{slide_idx} 元素越界：{shape.shape_type} "
                f"({shape.left},{shape.top},{shape.width},{shape.height}) 超出画布"
            )


def _check_contrast(
    slide_idx: int, slide, bg_hex: str | None, issues: list[str]
) -> None:
    if bg_hex is None:
        return
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                try:
                    fg_hex = str(run.font.color.rgb)
                except Exception:
                    continue
                ratio = _contrast_ratio(fg_hex, bg_hex)
                size_pt = run.font.size.pt if run.font.size is not None else 0
                is_bold = bool(run.font.bold)
                is_large = size_pt >= LARGE_TEXT_PT or (
                    is_bold and size_pt >= BOLD_LARGE_TEXT_PT
                )
                threshold = CONTRAST_LARGE if is_large else CONTRAST_BODY
                if ratio < threshold:
                    issues.append(
                        f"P{slide_idx} 对比度 {ratio:.2f} 低于 {threshold}："
                        f"{run.text[:20]!r}（{fg_hex} 对 {bg_hex}）"
                    )


def run_gates(prs: Presentation) -> GateReport:
    issues: list[str] = []
    width, height = prs.slide_width, prs.slide_height
    assert width is not None and height is not None
    for slide_idx, slide in enumerate(prs.slides, start=1):
        _check_fonts(slide_idx, slide, issues)
        _check_bounds(slide_idx, slide, width, height, issues)
        bg_hex = _slide_background_hex(slide, width, height)
        _check_contrast(slide_idx, slide, bg_hex, issues)
    return GateReport(issues)
