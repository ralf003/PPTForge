"""骨架库：可复用的确定性版式。

Designer 只选骨架并填语义（名称/描述/量化），坐标全部由本模块计算。
骨架不接收任何坐标参数，页面上所有位置由内容量与设计系统推导，
这样"agent 不写坐标"才是真的。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

from pptforge.models import Page
from pptforge.theme import Theme

if TYPE_CHECKING:  # 仅类型引用，避免循环导入
    from pptforge.engine.renderer import Renderer

CENTER = PP_ALIGN.CENTER
LEFT = PP_ALIGN.LEFT
MIDDLE = MSO_ANCHOR.MIDDLE

# 内容区边界（英寸）：标题区之下到页脚之上
CONTENT_TOP = 1.75
CONTENT_BOTTOM = 7.10
# 有结论带时，内容区需为其让出空间
CLAIM_BAND_TOP = 5.95
CLAIM_BAND_H = 1.55


def _no_shadow(shape) -> None:
    """彻底去效果：add_shape 会带 <p:style> 引用主题 effectRef，只清 spPr 无效。"""
    from pptx.oxml.ns import qn

    sp = shape._element
    for el in sp.findall(qn("p:style")):
        sp.remove(el)
    shape.shadow.inherit = False


def _rect(slide, x: float, y: float, w: float, h: float, color: str, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(color)
    s.line.fill.background()
    if len(s.adjustments):
        s.adjustments[0] = 0.06  # 小圆角，避免胶囊化
    _no_shadow(s)
    return s


def _rgb(hex_color: str):
    from pptforge.engine.renderer import _rgb as _r

    return _r(hex_color)


def _circle(slide, cx: float, cy: float, d: float, color: str):
    s = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d)
    )
    s.fill.solid()
    s.fill.fore_color.rgb = _rgb(color)
    s.line.fill.background()
    _no_shadow(s)
    return s


def _header(r: Renderer, slide, page: Page, theme: Theme) -> float:
    """统一标题区：强调竖条 + 单行标题 + 可选口径句，返回内容起始 y。"""
    p, s = theme.palette, theme.scale
    _rect(slide, 0.75, 0.55, 0.12, 0.72, p.blue)
    r._add_text(slide, 1.0, 0.45, 11.4, 0.95, [(page.title, s.page_title - 2, p.dark, True)])
    y = 1.50
    if page.subtitle:
        r._add_text(
            slide, 1.0, y, 11.4, 0.45,
            [(page.subtitle, s.section_label + 2, p.mute, False)],
        )
        y += 0.55
    return max(CONTENT_TOP, y + 0.10)


def _claim_band(r: Renderer, slide, page: Page, theme: Theme) -> None:
    """整幅深色结论带：把"往哪走"落在页脚；claim 含换行时第二行小字作支撑。"""
    p, s = theme.palette, theme.scale
    _rect(slide, 0, CLAIM_BAND_TOP, theme.slide_width_in, CLAIM_BAND_H, p.dark)
    lines = (page.claim or "").split("\n")
    main = lines[0].strip()
    sub = lines[1].strip() if len(lines) > 1 and lines[1].strip() else None
    size = s.item_name + 4 if len(main) <= 26 else s.item_name
    if sub:
        r._add_text(
            slide, 0.95, CLAIM_BAND_TOP + 0.26, 11.6, 0.62, [(main, size, p.white, True)]
        )
        r._add_text(
            slide, 0.95, CLAIM_BAND_TOP + 0.92, 11.6, 0.48,
            [(sub, s.section_label + 1, p.cyan, False)],
        )
    else:
        r._add_text(
            slide, 0.95, CLAIM_BAND_TOP + 0.45, 11.6, 0.7, [(main, size, p.white, True)]
        )


def _notes(slide, page: Page) -> None:
    if page.note:
        slide.notes_slide.notes_text_frame.text = page.note


def _node_color(p, i: int, n: int) -> str:
    """沿轨迹从"正常"走到"失控"：蓝→琥珀→红，不是二值跳变。"""
    if n <= 1:
        return p.blue
    if i == n - 1:
        return p.red
    if n >= 3 and i == n - 2:
        return p.amber
    return p.blue


# ---------------- 骨架：track（叙事轨迹） ----------------
def _track(r: Renderer, page: Page) -> None:
    """一条轨迹串起若干节点，节点符号递增代表事态加剧，底部可挂结论带。"""
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    nodes = page.items[:4]
    n = len(nodes)
    if n == 0:
        _notes(slide, page)
        return

    limit = CLAIM_BAND_TOP - 0.15 if page.claim else CONTENT_BOTTOM
    y_track = y0 + (limit - y0) * 0.66
    # 节点横向等距铺满，卡宽随节点数自适应
    span0, span1 = 2.1, 11.0
    step = (span1 - span0) / (n - 1) if n > 1 else 0.0
    card_w = min(3.8, max(2.4, step - 0.35)) if n > 1 else 3.8

    # 轨迹线覆盖节点范围，两端标注方向
    _rect(slide, 1.35, y_track - 0.02, 10.4, 0.04, p.mute)
    r._add_text(slide, 0.70, y_track + 0.12, 0.62, 0.35, [("起点", s.footnote, p.mute, False)])
    r._add_text(slide, 11.35, y_track + 0.12, 0.80, 0.35, [("终局", s.footnote, p.mute, False)])

    for i, item in enumerate(nodes):
        cx = span0 + step * i
        # 直径递增表达"沿轨迹放大"
        d = 0.30 + (0.28 * i / (n - 1) if n > 1 else 0.0)
        color = _node_color(p, i, n)
        _circle(slide, cx, y_track, d, color)
        r._add_text(
            slide, cx - card_w / 2, y_track - 2.05, card_w, 0.48,
            [(item.name, s.item_name, p.dark, True)], align=CENTER,
        )
        if item.desc:
            r._add_text(
                slide, cx - card_w / 2, y_track - 1.57, card_w, 0.58,
                [(item.desc, s.body - 2, p.mute, False)], align=CENTER,
            )
        if item.value:
            r._add_text(
                slide, cx - card_w / 2, y_track - 0.95, card_w, 0.40,
                [(item.value, s.caption, color, True)], align=CENTER,
            )

    if page.claim:
        _claim_band(r, slide, page, theme)
    _notes(slide, page)


# ---------------- 骨架：stat（数据特写） ----------------
def _value_size(text: str) -> int:
    """按字符长度自适应字号，避免长数字溢出。"""
    n = len(text)
    if n <= 3:
        return 66
    if n <= 5:
        return 52
    if n <= 7:
        return 42
    return 34


def _stat(r: Renderer, page: Page) -> None:
    """横向并列若干指标：大数字主导，短线分隔，整块在内容区居中，底部可挂结论带。"""
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    items = page.items[:4]
    n = len(items)
    if n == 0:
        _notes(slide, page)
        return

    limit = CLAIM_BAND_TOP - 0.15 if page.claim else CONTENT_BOTTOM
    x0, x1 = 1.00, 12.33
    step = (x1 - x0) / n
    # 块高由内容决定，再在内容区垂直居中——不靠撑满底板制造空卡片
    block_h = 1.30 + 0.16 + 0.50 + 0.80
    top = y0 + max(0.10, (limit - y0 - block_h) / 2)

    for i, item in enumerate(items):
        cx = x0 + step * (i + 0.5)
        inner = step - 0.55
        value = item.value or "—"
        r._add_text(
            slide, cx - inner / 2, top, inner, 1.30,
            [(value, _value_size(value), p.blue, True)], align=CENTER, anchor=MIDDLE,
        )
        _rect(slide, cx - 0.60, top + 1.42, 1.20, 0.06, p.blue)
        r._add_text(
            slide, cx - inner / 2, top + 1.58, inner, 0.50,
            [(item.name, s.item_name, p.dark, True)], align=CENTER,
        )
        if item.desc:
            r._add_text(
                slide, cx - inner / 2, top + 2.14, inner, 0.85,
                [(item.desc, s.body - 3, p.mute, False)], align=CENTER,
            )

    if page.claim:
        _claim_band(r, slide, page, theme)
    _notes(slide, page)


# ---------------- 骨架：topology（分层架构） ----------------
def _topology(r: Renderer, page: Page) -> None:
    """自上而下的分层架构：层条 + 左侧层级标识 + 层间箭头，底座层加重。"""
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    layers = page.items[:5]
    n = len(layers)
    if n == 0:
        _notes(slide, page)
        return

    gap = 0.30 if n >= 4 else 0.40
    box_h = min(1.10, (CONTENT_BOTTOM - y0 - gap * (n - 1)) / n)
    x, w = 1.00, 11.33
    label_w = 1.72

    for i, item in enumerate(layers):
        y = y0 + i * (box_h + gap)
        fill = p.tint if i % 2 == 0 else p.tint_alt
        _rect(slide, x, y, w, box_h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        # 左侧层级标识：底座层用最深色，其余统一主蓝，指向"越往下越硬"
        _rect(
            slide, x + 0.04, y + 0.08, 0.10, box_h - 0.16,
            p.dark if i == n - 1 else p.blue,
        )
        r._add_text(
            slide, x + 0.36, y, label_w, box_h,
            [(item.name, s.item_name, p.dark, True)], anchor=MIDDLE,
        )
        if item.desc:
            r._add_text(
                slide, x + 0.36 + label_w, y, w - label_w - 0.90, box_h,
                [(item.desc, s.body - 2, p.mute, False)], anchor=MIDDLE,
            )
        if i < n - 1:
            _rect(
                slide, x + w / 2 - 0.14, y + box_h + 0.04, 0.28, gap - 0.08,
                p.blue, shape=MSO_SHAPE.DOWN_ARROW,
            )
    _notes(slide, page)


REGISTRY: dict[str, Callable[[Renderer, Page], None]] = {
    "track": _track,
    "stat": _stat,
    "topology": _topology,
}


def render_skeleton(r: Renderer, page: Page) -> None:
    """按 page.skeleton 分发；未知骨架直接报错，不静默降级。"""
    key = page.skeleton or ""
    fn = REGISTRY.get(key)
    if fn is None:
        raise ValueError(f"未知骨架 skeleton={key!r}，可选 {tuple(REGISTRY)}")
    fn(r, page)


def skeleton_keys() -> tuple[str, ...]:
    return tuple(REGISTRY)
