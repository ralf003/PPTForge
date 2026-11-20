"""确定性渲染引擎：把 Deck 渲染为本地可编辑 PPTX。

agent 不写坐标；本模块按页型与内容量计算位置，保证投影级字号、
微软雅黑字体、不溢出，并在保存前修复 OOXML 轴 ID。
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from pptforge.engine.fonts import apply_paragraph_font
from pptforge.engine.ooxml_fix import fix_chart_axis_ids
from pptforge.models import Deck, Item, Page
from pptforge.theme import Theme


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


class Renderer:
    def __init__(self, theme: Theme | None = None) -> None:
        self.theme = theme or Theme()
        t = self.theme
        self.prs = Presentation()
        self.prs.slide_width = Inches(t.slide_width_in)
        self.prs.slide_height = Inches(t.slide_height_in)
        self._blank_layout = self.prs.slide_layouts[6]

    def _add_slide(self, bg_color: str):
        slide = self.prs.slides.add_slide(self._blank_layout)
        rect = slide.shapes.add_shape(
            1,  # MSO_SHAPE.RECTANGLE
            Inches(0),
            Inches(0),
            self.prs.slide_width,
            self.prs.slide_height,
        )
        rect.fill.solid()
        rect.fill.fore_color.rgb = _rgb(bg_color)
        rect.line.fill.background()
        rect.shadow.inherit = False
        return slide

    def _add_text(
        self,
        slide,
        x: float,
        y: float,
        w: float,
        h: float,
        lines: list[tuple[str, int, str, bool]],
        anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
        align: PP_ALIGN = PP_ALIGN.LEFT,
    ):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        for i, (text, size, color, bold) in enumerate(lines):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = align
            run = para.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = _rgb(color)
            apply_paragraph_font(para, self.theme.font_family)
        return box

    # ---- 页型 ----
    def _cover(self, page: Page) -> None:
        p = self.theme.palette
        s = self.theme.scale
        slide = self._add_slide(p.dark)
        # 左侧蓝色强调竖条
        bar = slide.shapes.add_shape(
            1, Inches(0.9), Inches(2.55), Inches(0.14), Inches(2.0)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = _rgb(p.cyan)
        bar.line.fill.background()
        bar.shadow.inherit = False

        lines = [(page.title, s.cover_title, p.white, True)]
        if page.subtitle:
            lines.append((page.subtitle, s.cover_sub, p.cyan, False))
        self._add_text(slide, 1.25, 2.4, 11.0, 2.4, lines)
        if page.note:
            slide.notes_slide.notes_text_frame.text = page.note

    def _section(self, page: Page) -> None:
        p = self.theme.palette
        s = self.theme.scale
        slide = self._add_slide(p.panel)
        lines = [(page.title, s.page_title + 6, p.white, True)]
        if page.subtitle:
            lines.append((page.subtitle, s.cover_sub, p.cyan, False))
        self._add_text(
            slide, 1.0, 2.7, 11.3, 2.0, lines, anchor=MSO_ANCHOR.MIDDLE
        )
        if page.note:
            slide.notes_slide.notes_text_frame.text = page.note

    def _content(self, page: Page) -> None:
        p = self.theme.palette
        s = self.theme.scale
        slide = self._add_slide(p.bg)
        # 标题 + 强调竖条
        bar = slide.shapes.add_shape(
            1, Inches(0.7), Inches(0.55), Inches(0.12), Inches(0.7)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = _rgb(p.blue)
        bar.line.fill.background()
        bar.shadow.inherit = False
        self._add_text(
            slide, 0.95, 0.5, 11.6, 0.9,
            [(page.title, s.page_title, p.dark, True)],
        )
        self._layout_items(slide, page.items)
        if page.note:
            slide.notes_slide.notes_text_frame.text = page.note

    def _layout_items(self, slide, items: list[Item]) -> None:
        p = self.theme.palette
        s = self.theme.scale
        top = 1.7
        available = 5.4
        # 条目在可用垂直空间内均匀撑满，避免下半页留白
        row_h = available / max(1, len(items))
        for i, item in enumerate(items):
            y = top + i * row_h
            lines = [(item.name, s.item_name, p.blue, True)]
            if item.desc:
                lines.append((item.desc, s.body, p.mute, False))
            self._add_text(
                slide, 0.95, y, 11.5, row_h, lines, anchor=MSO_ANCHOR.MIDDLE
            )

    def _summary(self, page: Page) -> None:
        p = self.theme.palette
        s = self.theme.scale
        slide = self._add_slide(p.dark)
        self._add_text(
            slide, 0.9, 0.7, 11.5, 1.0,
            [(page.title, s.page_title, p.cyan, True)],
        )
        lines: list[tuple[str, int, str, bool]] = []
        for item in page.items:
            lines.append((item.name, s.item_name, p.white, True))
            if item.desc:
                lines.append((item.desc, s.body, p.cyan, False))
        self._add_text(
            slide, 0.95, 1.8, 11.5, 5.0, lines, anchor=MSO_ANCHOR.MIDDLE
        )
        if page.note:
            slide.notes_slide.notes_text_frame.text = page.note

    # ---- 主流程 ----
    def _dispatch(self, page: Page) -> None:
        """有骨架则交给骨架库（坐标由骨架算），否则退回基础四页型。"""
        if page.skeleton:
            from pptforge.engine.skeletons import render_skeleton

            render_skeleton(self, page)
            return
        {
            "cover": self._cover,
            "section": self._section,
            "content": self._content,
            "summary": self._summary,
        }[page.role](page)

    def render(self, deck: Deck) -> None:
        problems = deck.validate()
        if problems:
            raise ValueError("Deck 校验失败：" + "；".join(problems))
        for page in deck.pages:
            self._dispatch(page)
        fix_chart_axis_ids(self.prs)

    def save(self, deck: Deck, path: str | Path) -> Path:
        self.render(deck)
        out = Path(path)
        self.prs.save(str(out))
        return out


def render_deck(deck: Deck, path: str | Path, theme: Theme | None = None) -> Path:
    return Renderer(theme).save(deck, path)
