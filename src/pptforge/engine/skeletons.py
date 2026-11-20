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

# 各骨架正文条目容量上限；超容量抛 ValueError，不静默截断。
# hero 不消费 items，不设容量口径。
SKELETON_CAPACITY: dict[str, int] = {
    "track": 4,
    "stat": 4,
    "topology": 5,
    "split": 4,
}


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
    """一条轨迹串起若干节点，节点符号递增代表事态加剧，底部可挂结论带。

    单 body 项时切换居中放大版式：隐藏仅多元素才有意义的轨迹线与
    起点/终局标签，节点与文案在内容区水平 + 垂直居中；不加撑满底板。
    """
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    nodes = page.items
    n = len(nodes)

    limit = CLAIM_BAND_TOP - 0.15 if page.claim else CONTENT_BOTTOM

    if n == 1:
        item = nodes[0]
        color = _node_color(p, 0, 1)
        cx = theme.slide_width_in / 2
        block_w = 7.6
        d = 0.70
        desc_h = 0.62 if item.desc else 0.0
        value_h = 0.50 if item.value else 0.0
        block_h = d + 0.16 + 0.60 + (0.16 + desc_h if item.desc else 0.0)
        block_h += 0.16 + value_h if item.value else 0.0
        top = y0 + max(0.10, (limit - y0 - block_h) / 2)

        cy = top + d / 2
        # 居中强调细线：保留轨迹语义并切断中段侧带；不加撑满底板
        _rect(slide, cx - 5.17, cy - 0.02, 10.33, 0.04, p.mute)
        _circle(slide, cx, cy, d, color)
        ty = top + d + 0.16
        r._add_text(
            slide, cx - block_w / 2, ty, block_w, 0.60,
            [(item.name, s.item_name + 6, p.dark, True)], align=CENTER,
        )
        ty += 0.60 + (0.16 if item.desc else 0.0)
        if item.desc:
            r._add_text(
                slide, cx - block_w / 2, ty, block_w, desc_h,
                [(item.desc, s.body, p.mute, False)], align=CENTER,
            )
            ty += desc_h + 0.16
        if item.value:
            r._add_text(
                slide, cx - block_w / 2, ty, block_w, value_h,
                [(item.value, s.caption + 4, color, True)], align=CENTER,
            )

        if page.claim:
            _claim_band(r, slide, page, theme)
        _notes(slide, page)
        return

    y_track = y0 + (limit - y0) * 0.66
    # 节点横向等距铺满，卡宽随节点数自适应
    span0, span1 = 2.1, 11.0
    step = (span1 - span0) / (n - 1) if n > 1 else 0.0
    card_w = min(3.8, max(2.4, step - 0.35))

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
    """横向并列若干指标：大数字主导，短线分隔，整块在内容区居中，底部可挂结论带。

    单 body 项时为居中放大版式：指标块占满内容宽度、字号上调一档，
    不再预留多列间距；不加撑满底板。
    """
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    items = page.items
    n = len(items)

    limit = CLAIM_BAND_TOP - 0.15 if page.claim else CONTENT_BOTTOM
    x0, x1 = 1.00, 12.33
    step = (x1 - x0) / n

    if n == 1:
        item = items[0]
        cx = (x0 + x1) / 2
        inner = x1 - x0 - 1.0
        raw_value = item.value
        rule_w = x1 - x0

        if raw_value and raw_value.strip():
            value = raw_value.strip()
            block_h = 1.50 + 0.16 + 0.50 + 0.85
            top = y0 + max(0.10, (limit - y0 - block_h) / 2)
            r._add_text(
                slide, cx - inner / 2, top, inner, 1.50,
                [(value, min(66, _value_size(value) + 8), p.blue, True)],
                align=CENTER, anchor=MIDDLE,
            )
            _rect(slide, cx - rule_w / 2, top + 1.62, rule_w, 0.06, p.blue)
            r._add_text(
                slide, cx - inner / 2, top + 1.78, inner, 0.50,
                [(item.name, s.item_name + 2, p.dark, True)], align=CENTER,
            )
            if item.desc:
                r._add_text(
                    slide, cx - inner / 2, top + 2.34, inner, 0.85,
                    [(item.desc, s.body, p.mute, False)], align=CENTER,
                )
        else:
            # 无量化值：不渲染大号占位符；名称作为主元素落在一条全宽内容条内
            # （与 topology 层条同一组件语言，条体承载名称、非装饰空底板），
            # desc 居中其下，保留 stat 风格短强调线。
            bar_h = 1.60 if not item.desc else 1.30
            block_h = bar_h + 0.16 + (0.85 if item.desc else 0.0)
            top = y0 + max(0.10, (limit - y0 - block_h) / 2)
            _rect(slide, x0, top, x1 - x0, bar_h, p.tint, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
            _rect(slide, x0 + 0.04, top + 0.08, 0.10, bar_h - 0.16, p.dark)
            r._add_text(
                slide, x0 + 0.36, top, inner, bar_h,
                [(item.name, min(36, s.item_name + 12), p.dark, True)],
                align=CENTER, anchor=MIDDLE,
            )
            _rect(slide, cx - 1.20, top + bar_h + 0.12, 2.40, 0.06, p.blue)
            if item.desc:
                r._add_text(
                    slide, cx - inner / 2, top + bar_h + 0.28, inner, 0.85,
                    [(item.desc, s.body, p.mute, False)], align=CENTER,
                )
        if page.claim:
            _claim_band(r, slide, page, theme)
        _notes(slide, page)
        return

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
    """自上而下的分层架构：层条 + 左侧层级标识 + 层间箭头，底座层加重。

    单 body 项时为居中放大版式：层条加高并在内容区垂直居中，
    层间箭头本就无第二节点可指，自动隐藏；不加撑满底板。
    """
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.bg)
    y0 = _header(r, slide, page, theme)

    layers = page.items
    n = len(layers)

    limit = CLAIM_BAND_TOP - 0.15 if page.claim else CONTENT_BOTTOM
    x, w = 1.00, 11.33
    label_w = 1.72

    if n == 1:
        item = layers[0]
        box_h = min(2.20, limit - y0)
        top = y0 + max(0.10, (limit - y0 - box_h) / 2)
        fill = p.tint
        _rect(slide, x, top, w, box_h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        _rect(slide, x + 0.04, top + 0.08, 0.10, box_h - 0.16, p.dark)
        r._add_text(
            slide, x + 0.36, top, label_w, box_h,
            [(item.name, s.item_name + 2, p.dark, True)], anchor=MIDDLE,
        )
        if item.desc:
            r._add_text(
                slide, x + 0.36 + label_w, top, w - label_w - 0.90, box_h,
                [(item.desc, s.body, p.mute, False)], anchor=MIDDLE,
            )
        if page.claim:
            _claim_band(r, slide, page, theme)
        _notes(slide, page)
        return

    gap = 0.30 if n >= 4 else 0.40
    # 有结论带时只在其上方排布，与 track/stat 共用同一垂直边界；
    # 层条撑满可用高度（设 1.60 上限保版式），修掉 n<4 时底部整片留白。
    box_h = min(1.60, (limit - y0 - gap * (n - 1)) / n)

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
    if page.claim:
        _claim_band(r, slide, page, theme)
    _notes(slide, page)


# ---------------- 骨架：hero（全幅图） ----------------
HERO_BAND_H = 2.60


def _fill_picture(slide, path: str, x: float, y: float, w: float, h: float):
    """按目标框裁剪铺满，不拉伸变形。"""
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    iw, ih = pic.image.size  # (px_w, px_h)
    if not iw or not ih:
        return pic
    img_r, box_r = iw / ih, w / h
    if img_r > box_r:  # 图更宽 → 左右各裁一半
        cut = (1 - box_r / img_r) / 2
        pic.crop_left = cut
        pic.crop_right = cut
    elif img_r < box_r:  # 图更高 → 上下各裁一半
        cut = (1 - img_r / box_r) / 2
        pic.crop_top = cut
        pic.crop_bottom = cut
    return pic


def _hero(r: Renderer, page: Page) -> None:
    """全幅图打底，底部实色带压标题与判断句；不用半透明，避免跨端渲染差异。"""
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.dark)
    if page.image:
        _fill_picture(slide, page.image, 0, 0, theme.slide_width_in, theme.slide_height_in)

    band_y = theme.slide_height_in - HERO_BAND_H
    _rect(slide, 0, band_y, theme.slide_width_in, HERO_BAND_H, p.dark)
    _rect(slide, 0.92, band_y + 0.40, 0.12, 0.66, p.cyan)
    r._add_text(
        slide, 1.18, band_y + 0.30, 11.2, 0.92,
        [(page.title, s.cover_title - 10, p.white, True)],
    )
    if page.subtitle:
        r._add_text(
            slide, 1.18, band_y + 1.24, 11.2, 0.52,
            [(page.subtitle, s.cover_sub - 6, p.cyan, False)],
        )
    if page.claim:
        main = (page.claim or "").split("\n")[0]
        r._add_text(
            slide, 1.18, band_y + 1.82, 11.2, 0.52, [(main, s.body - 4, p.white, False)]
        )
    _notes(slide, page)


# ---------------- 骨架：split（左文右图） ----------------
SPLIT_COL_W = 5.05


def _split(r: Renderer, page: Page) -> None:
    """左侧实色文字栏，右侧图满高；文字与图各占一侧，互不压盖。"""
    theme = r.theme
    p, s = theme.palette, theme.scale
    slide = r._add_slide(p.panel)
    if page.image:
        _fill_picture(
            slide, page.image, SPLIT_COL_W, 0,
            theme.slide_width_in - SPLIT_COL_W, theme.slide_height_in,
        )
    _rect(slide, 0, 0, SPLIT_COL_W, theme.slide_height_in, p.panel)
    _rect(slide, 0.62, 0.60, 0.10, 0.60, p.cyan)
    r._add_text(
        slide, 0.88, 0.50, SPLIT_COL_W - 1.3, 0.95,
        [(page.title, s.page_title - 8, p.white, True)],
    )
    if page.subtitle:
        r._add_text(
            slide, 0.88, 1.48, SPLIT_COL_W - 1.3, 0.45,
            [(page.subtitle, s.section_label + 1, p.cyan, False)],
        )

    items = page.items
    top = 2.20
    bottom = 7.02
    row = (bottom - top) / max(1, len(items))
    for item in items:
        r._add_text(
            slide, 0.88, top, SPLIT_COL_W - 1.2, 0.46,
            [(item.name, s.item_name - 2, p.white, True)],
        )
        if item.desc:
            r._add_text(
                slide, 0.88, top + 0.52, SPLIT_COL_W - 1.2, max(0.38, row - 0.58),
                [(item.desc, s.body - 4, p.cyan, False)],
            )
        top += row
    _notes(slide, page)


REGISTRY: dict[str, Callable[[Renderer, Page], None]] = {
    "track": _track,
    "stat": _stat,
    "topology": _topology,
    "hero": _hero,
    "split": _split,
}


def render_skeleton(r: Renderer, page: Page) -> None:
    """按 page.skeleton 分发；未知骨架直接报错，不静默降级。

    带容量口径的骨架在分发前硬校验：空条目页与超容量条目直接抛
    ValueError，不静默退化为标题页、不静默截断多余条目。
    """
    key = page.skeleton or ""
    fn = REGISTRY.get(key)
    if fn is None:
        raise ValueError(f"未知骨架 skeleton={key!r}，可选 {tuple(REGISTRY)}")
    cap = SKELETON_CAPACITY.get(key)
    if cap is not None:
        n = len(page.items)
        if n == 0:
            raise ValueError(f"骨架 {key} 至少需要一个条目，空条目页不静默退化为标题页")
        if n > cap:
            raise ValueError(
                f"骨架 {key} 容量上限 {cap} 条，收到 {n} 条；超出条目不得静默截断"
            )
    fn(r, page)


def skeleton_keys() -> tuple[str, ...]:
    return tuple(REGISTRY)
