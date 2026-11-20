"""Designer 回归：语义压缩与骨架选择不能把噪声当信号。"""

from __future__ import annotations

import json
from pathlib import Path

from pptforge.models import SKELETONS
from pptforge.roles.designer import _key_value, _short_desc, _short_name, design, pick_skeleton
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief

FIXTURE = Path(__file__).parent.parent / "examples" / "role_demo" / "researcher.json"


def _brief(cards: list[ClaimCard], topic: str = "智能体长程任务失败机理") -> ResearchBrief:
    return ResearchBrief(
        brief=PageBrief(topic=topic, claim="规模化的瓶颈是长程轨迹与治理", page_role="content"),
        cards=cards,
    )


def test_arxiv_ids_are_not_treated_as_metrics() -> None:
    """arXiv 编号与年份没有量纲，不得进图面。"""
    assert _key_value("单步成功率", ["arXiv 2601.22984", "NVIDIA 2026-07"]) is None
    assert _key_value(
        "早期错误传播", ["arXiv 2601.22984：单步90%成功率", "长链坍缩至约12%"]
    ) == "90% → 12%"


def test_short_name_strips_colon_suffix() -> None:
    assert _short_name("误差级联：单步高成功率在长链上非线性坍缩") == "误差级联"
    assert _short_name("轨迹级幻觉：沿轨迹传播的结构性偏离") == "轨迹级幻觉"


def test_short_desc_keeps_first_clause() -> None:
    assert (
        _short_desc("早期小错误沿序列传播，内部推理与外部执行功能错位，但语言仍流畅")
        == "早期小错误沿序列传播"
    )


def test_pick_skeleton_by_topic() -> None:
    card = ClaimCard(claim="分层", support="按层划分", evidence=["e"])
    assert pick_skeleton(_brief([card], topic="AIOS 分层架构")) == "topology"
    assert pick_skeleton(_brief([card], topic="性能指标对比")) == "stat"
    assert pick_skeleton(_brief([card], topic="失败机理")) == "track"


def test_design_from_real_fixture() -> None:
    raw = json.loads(FIXTURE.read_text("utf-8"))["cards"]
    page = design(_brief([ClaimCard(**c) for c in raw]))
    assert page.skeleton in SKELETONS
    assert page.claim, "最后一张卡应升格为结论带"
    assert len(page.items) == len(raw) - 1
    assert "缺口" in page.note, "证据与缺口必须留档在备注"
    assert all(not i.desc or len(i.desc) <= 16 for i in page.items), "说明过长会挤爆图面"
