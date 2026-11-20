"""端到端：真实研究产物 → Designer → 骨架渲染 → 质量门，全程零坐标。

与 build_designer_demo.py 的区别：那一版靠手写 Inches() 摆位，
本版只有语义内容，位置由引擎按骨架推导。
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation

from pptforge.engine.renderer import render_deck
from pptforge.gates.checks import run_gates
from pptforge.models import Deck, Item, Page
from pptforge.roles.designer import design
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief

HERE = Path(__file__).parent


def load_brief() -> ResearchBrief:
    raw = json.loads((HERE / "researcher.json").read_text("utf-8"))["cards"]
    return ResearchBrief(
        brief=PageBrief(
            topic="智能体长程任务失败机理",
            claim="规模化的瓶颈是长程轨迹与治理，不是模型能力",
            page_role="content",
        ),
        cards=[ClaimCard(**c) for c in raw],
    )


def extra_pages() -> list[Page]:
    """stat / topology 两页用于验证骨架对其它内容形态的承载力。"""
    stat = Page(
        role="content",
        skeleton="stat",
        title="三个量化指标界定了问题边界",
        subtitle="口径见页面备注",
        items=[
            Item(name="长程成功率", desc="超 40 步任务", value="12%"),
            Item(name="未治理 token", desc="单任务轨迹重放", value="180万"),
            Item(name="治理后 token", desc="确定性控制介入", value="6万"),
        ],
        claim="瓶颈在治理成本，不在单步能力。",
        note="12% 为厂商口径，步数假设待核实；token 数据来自 UK AISI 红队实验。",
    )
    topo = Page(
        role="content",
        skeleton="topology",
        title="四层分工：判断在上，约束在下",
        subtitle="本页层级为通用分工示意",
        items=[
            Item(name="接入层", desc="指令解析 / 权限校验 / 人类闸口"),
            Item(name="编排层", desc="Director / Researcher / Designer"),
            Item(name="能力层", desc="检索 / 渲染 / 质量门 / 工具调用"),
            Item(name="底座层", desc="确定性引擎 / 布局计算 / OOXML 修复"),
        ],
        note="正式架构页需替换为 AIOS 2.0 实际分层与模块名。",
    )
    return [stat, topo]


def main() -> Path:
    track_page = design(load_brief())
    deck = Deck(title="骨架库实证", author="PPTForge", pages=[track_page, *extra_pages()])
    out = render_deck(deck, HERE / "skeleton_demo.pptx")
    report = run_gates(Presentation(str(out)))
    print(f"已生成：{out}")
    print("质量门：", "通过" if report.ok else "未通过", report.issues or "")
    return out


if __name__ == "__main__":
    main()
