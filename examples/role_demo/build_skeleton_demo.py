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
IMG_DIR = HERE.resolve().parents[2] / "assets" / "final"


def picture(name: str) -> str | None:
    """配图不随仓库分发（二进制），存在则用，不存在则骨架自动退化。"""
    p = IMG_DIR / name
    return str(p) if p.exists() else None


def hero_page() -> Page:
    return Page(
        role="content",
        skeleton="hero",
        title="智能体能不能自己把关自己的代码",
        subtitle="从人在环中，到人在环上",
        claim="技术对错交给评审委员会，人只保留意图与授权。",
        image=picture("cover_gen.jpg"),
        note="配图：image_gen 生成的概念图，2047×1152，无文字。",
    )


def split_page() -> Page:
    return Page(
        role="content",
        skeleton="split",
        title="三层把关",
        subtitle="各自只回答一个问题",
        items=[
            Item(name="能不能合", desc="评审委员会输出硬门，全绿才合并"),
            Item(name="错在哪", desc="变异测试与二阶验证，抓测试本身的漏洞"),
            Item(name="值不值得", desc="人只判断意图与授权，不判断代码对错"),
        ],
        image=picture("p2_robot.jpg"),
        note="配图：真实照片，用已知 ID 从 CDN 取回 1920×1280 原图。",
    )


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
    """stat / topology 两页用于验证骨架对其它内容形态的承载力。

    图面只留结构化名称与数值；口径、假设与待核实项一律进 note。
    """
    stat = Page(
        role="content",
        skeleton="stat",
        title="三个量化指标界定了问题边界",
        items=[
            Item(name="长程成功率", desc="超 40 步任务", value="12%"),
            Item(name="未治理 token", desc="单任务轨迹重放", value="180万"),
            Item(name="治理后 token", desc="确定性控制介入", value="6万"),
        ],
        claim="瓶颈在治理成本，不在单步能力。",
        note="口径：12% 为厂商口径、步数假设待核实；token 数据来自 UK AISI 红队实验。",
    )
    topo = Page(
        role="content",
        skeleton="topology",
        title="四层分工：判断在上，约束在下",
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
    deck = Deck(
        title="骨架库实证",
        author="PPTForge",
        pages=[hero_page(), track_page, *extra_pages(), split_page()],
    )
    out = render_deck(deck, HERE / "skeleton_demo.pptx")
    report = run_gates(Presentation(str(out)))
    print(f"已生成：{out}")
    print("质量门：", "通过" if report.ok else "未通过", report.issues or "")
    return out


if __name__ == "__main__":
    main()
