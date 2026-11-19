"""质量门：对生成的 PPTX 做静态硬检查。

覆盖：
- 字体名与投影级字号；
- 元素几何越界（形状不得超出画布）；
- 文字与页面背景的 WCAG 对比度（AA）；
- 文本容量溢出（估算行数×行高是否超出文本框，抓"字压字"）；
- 文本框区域重叠。
视觉留白与精确文本度量仍由逐页渲染回看补充。
"""

from __future__ import annotations

import math
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

# 文本溢出容差（英寸）：中文宽度估算存在误差，留出余量避免误报
OVERFLOW_TOL_IN = 0.10

# 文本框重叠判定：相交面积阈值（平方英寸）
OVERLAP_MIN_AREA = 0.15

_EMU_PER_INCH = 914400


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


def _solid_rects(slide) -> list[tuple[float, float, float, float, str]]:
    """收集非文本实心形状的矩形与填充色，按绘制顺序（先画的在下）。"""
    rects: list[tuple[float, float, float, float, str]] = []
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip():
            continue
        if None in (shape.left, shape.top, shape.width, shape.height):
            continue
        try:
            color = str(shape.fill.fore_color.rgb)
        except Exception:
            continue
        rects.append(
            (
                shape.left / _EMU_PER_INCH,
                shape.top / _EMU_PER_INCH,
                (shape.left + shape.width) / _EMU_PER_INCH,
                (shape.top + shape.height) / _EMU_PER_INCH,
                color,
            )
        )
    return rects


def _effective_bg(
    rects: list[tuple[float, float, float, float, str]], cx: float, cy: float
) -> str | None:
    """取覆盖该点的最上层实心形状颜色；这正是文字实际压住的背景。"""
    for x0, y0, x1, y1, color in reversed(rects):
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return color
    return None


def _check_contrast(
    slide_idx: int,
    slide,
    bg_hex: str | None,
    issues: list[str],
    rects: list[tuple[float, float, float, float, str]],
) -> None:
    for shape in slide.shapes:
        if not shape.has_text_frame or not shape.text_frame.text.strip():
            continue
        # 以文字框中心点落在的色块为准；没有色块则回退页面背景
        shape_bg = bg_hex
        if None not in (shape.left, shape.top, shape.width, shape.height):
            # 注意：中心 = left + width/2，不是 (left+width)/2
            cx = (shape.left + shape.width / 2) / _EMU_PER_INCH
            cy = (shape.top + shape.height / 2) / _EMU_PER_INCH
            shape_bg = _effective_bg(rects, cx, cy) or bg_hex
        if shape_bg is None:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                try:
                    fg_hex = str(run.font.color.rgb)
                except Exception:
                    continue
                ratio = _contrast_ratio(fg_hex, shape_bg)
                size_pt = run.font.size.pt if run.font.size is not None else 0
                is_bold = bool(run.font.bold)
                is_large = size_pt >= LARGE_TEXT_PT or (
                    is_bold and size_pt >= BOLD_LARGE_TEXT_PT
                )
                threshold = CONTRAST_LARGE if is_large else CONTRAST_BODY
                if ratio < threshold:
                    issues.append(
                        f"P{slide_idx} 对比度 {ratio:.2f} 低于 {threshold}："
                        f"{run.text[:20]!r}（{fg_hex} 对 {shape_bg}）"
                    )


def _char_em(ch: str) -> float:
    """单字符宽度（以 em 计）：全角按 1.0，半角按 0.55 估算。"""
    return 0.55 if ord(ch) < 128 else 1.0


def _estimate_text_height(shape) -> tuple[float, float] | None:
    """估算文本所需高度与框高（英寸）；无法估算（无字号）返回 None。"""
    if not shape.has_text_frame:
        return None
    if shape.width is None or shape.height is None:
        return None
    # 减去左右内边距，得到可用文本宽度
    box_w = shape.width / _EMU_PER_INCH - 0.10
    box_h = shape.height / _EMU_PER_INCH
    if box_w <= 0.2:
        return None
    need = 0.0
    measured = False
    for para in shape.text_frame.paragraphs:
        runs = [r for r in para.runs if r.font.size is not None]
        if not runs:
            continue
        measured = True
        size = max(r.font.size.pt for r in runs if r.font.size is not None)
        em_width = sum(_char_em(ch) * size / 72 for r in runs for ch in r.text)
        lines = max(1, math.ceil(em_width / box_w))
        need += lines * size * 1.28 / 72
    if not measured:
        return None
    return need, box_h


def _check_text_overflow(slide_idx: int, slide, issues: list[str]) -> None:
    """文本超出文本框容量会压到相邻元素，渲染图上表现为字叠字。"""
    for shape in slide.shapes:
        estimate = _estimate_text_height(shape)
        if estimate is None:
            continue
        need, box_h = estimate
        if need > box_h + OVERFLOW_TOL_IN:
            text = shape.text_frame.text.strip().replace("\n", " ")[:24]
            issues.append(
                f"P{slide_idx} 文本溢出：{text!r} 约需 {need:.2f}in 超出框高 {box_h:.2f}in"
            )


def _check_text_overlap(slide_idx: int, slide, issues: list[str]) -> None:
    """两个含文字的文本框区域相交，说明版面排挤，须重排。"""
    boxes: list[tuple[str, float, float, float, float]] = []
    for shape in slide.shapes:
        if not shape.has_text_frame or not shape.text_frame.text.strip():
            continue
        if None in (shape.left, shape.top, shape.width, shape.height):
            continue
        boxes.append(
            (
                shape.text_frame.text.strip().replace("\n", " ")[:16],
                shape.left / _EMU_PER_INCH,
                shape.top / _EMU_PER_INCH,
                (shape.left + shape.width) / _EMU_PER_INCH,
                (shape.top + shape.height) / _EMU_PER_INCH,
            )
        )
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            dx = min(a[3], b[3]) - max(a[1], b[1])
            dy = min(a[4], b[4]) - max(a[2], b[2])
            if dx > 0 and dy > 0 and dx * dy > OVERLAP_MIN_AREA:
                issues.append(
                    f"P{slide_idx} 文本框重叠：{a[0]!r} 与 {b[0]!r} 相交 {dx * dy:.2f}in²"
                )


def run_gates(prs: Presentation) -> GateReport:
    issues: list[str] = []
    width, height = prs.slide_width, prs.slide_height
    assert width is not None and height is not None
    for slide_idx, slide in enumerate(prs.slides, start=1):
        _check_fonts(slide_idx, slide, issues)
        _check_bounds(slide_idx, slide, width, height, issues)
        _check_text_overflow(slide_idx, slide, issues)
        _check_text_overlap(slide_idx, slide, issues)
        bg_hex = _slide_background_hex(slide, width, height)
        rects = _solid_rects(slide)
        _check_contrast(slide_idx, slide, bg_hex, issues, rects)
    return GateReport(issues)
