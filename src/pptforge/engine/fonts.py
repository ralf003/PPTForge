"""字体辅助：同时设置 latin 与 eastAsia 字体，保证中文正确显示。"""

from __future__ import annotations

from pptx.oxml.ns import qn
from pptx.text.text import _Paragraph, _Run

from pptforge.theme import FONT_FAMILY


def set_run_font(run: _Run, family: str = FONT_FAMILY) -> None:
    """把 run 的 latin、ea、cs 字体统一设为指定字体名。"""

    run.font.name = family
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        element = rPr.find(qn(tag))
        if element is None:
            element = rPr.makeelement(qn(tag), {})
            rPr.append(element)
        element.set("typeface", family)


def apply_paragraph_font(paragraph: _Paragraph, family: str = FONT_FAMILY) -> None:
    """对段落内所有 run 统一字体。"""

    for run in paragraph.runs:
        set_run_font(run, family)
