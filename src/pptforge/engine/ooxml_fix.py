"""OOXML 修复：把图表的负轴 ID 规范化为唯一正整数。

python-pptx 可能生成超出 PowerPoint 无符号 int32 范围的负轴 ID，
LibreOffice 能容忍但 PowerPoint 打开会触发修复。保存前统一修复。
"""

from __future__ import annotations

from pptx.oxml.ns import qn
from pptx.presentation import Presentation

# PowerPoint 安全的正整数轴 ID 上限（留余量）
_MAX_SAFE_ID = 2_000_000_000


def fix_chart_axis_ids(prs: Presentation) -> int:
    """修复全部图表的轴 ID，返回修复的图表数量。"""

    fixed = 0
    next_id = 1000

    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_chart:
                continue
            chart_space = shape.chart._chartSpace
            id_elements = chart_space.iter(qn("c:axId"))
            cross_elements = chart_space.iter(qn("c:crossAx"))

            # 建立旧值 -> 新值映射
            remap: dict[str, str] = {}
            for el in id_elements:
                value = el.get("val")
                if value is None:
                    continue
                if int(value) <= 0 or int(value) > _MAX_SAFE_ID:
                    if value not in remap:
                        remap[value] = str(next_id)
                        next_id += 1

            if not remap:
                continue

            for el in list(chart_space.iter(qn("c:axId"))) + list(
                chart_space.iter(qn("c:crossAx"))
            ):
                value = el.get("val")
                if value in remap:
                    el.set("val", remap[value])
            fixed += 1

    return fixed
