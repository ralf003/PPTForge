"""质量门：对生成的 PPTX 做静态硬检查。

P0 覆盖字体名与投影级字号；视觉/对比度/溢出由渲染回看与后续门补充。
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.oxml.ns import qn
from pptx.presentation import Presentation

from pptforge.theme import FONT_FAMILY

# 投影级最小字号（pt），脚注为全稿下限
MIN_RUN_SIZE = 13


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


def run_gates(prs: Presentation) -> GateReport:
    issues: list[str] = []
    for slide_idx, slide in enumerate(prs.slides, start=1):
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
                            snippet = run.text[:20]
                            issues.append(
                                f"P{slide_idx} 字号 {size_pt}pt 低于下限"
                                f" {MIN_RUN_SIZE}：{snippet!r}"
                            )
    return GateReport(issues)
