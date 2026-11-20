"""闭环回归：打回一轮修复通过、max_iter 耗尽抛异常且异常带 verdict、轮次计数正确。

回放后端驱动 Director/Researcher；Reviewer 默认纯确定性，不依赖网络。
"""

from __future__ import annotations

import json

import pytest

from pptforge.models import Item, Page
from pptforge.roles.designer import design, repair
from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import Delivery, Pipeline, ReviewExhaustedError
from pptforge.roles.reviewer import Finding, Reviewer, Verdict
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief


def _backend() -> ReplayBackend:
    director = json.dumps(
        {
            "topic": "智能体长程任务失败机理",
            "claim": "规模化的瓶颈在长程轨迹与治理",
            "page_role": "content",
            "audience": "技术决策者",
            "principles": ["只放判断句"],
        },
        ensure_ascii=False,
    )
    researcher = json.dumps(
        {
            "cards": [
                {
                    "claim": "子判断一",
                    "support": "机制解释短",
                    "evidence": ["来源A"],
                    "gap": None,
                }
            ]
        },
        ensure_ascii=False,
    )
    return ReplayBackend(
        {"Director（导演）": director, "Researcher（研究专家）": researcher}
    )


def _brief() -> ResearchBrief:
    return ResearchBrief(
        brief=PageBrief(topic="失败机理", claim="判断句", page_role="content"),
        cards=[ClaimCard(claim="卡一", support="支持句", evidence=["证据一"])],
    )


class _FirstRoundMissingNote(Reviewer):
    """首轮模拟一条 RV001（备注缺失），次轮起交给确定性规则。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.calls = 0

    def review_page(self, page: Page, page_no: int = 1) -> Verdict:
        verdict = super().review_page(page, page_no)
        self.calls += 1
        if self.calls == 1:
            verdict.findings.append(
                Finding("RV001", "critical", "P1 / note", "模拟备注缺失", "补 note")
            )
        return verdict


def test_clean_page_passes_on_first_round() -> None:
    delivery = Pipeline(_backend()).build_page("失败机理")
    assert isinstance(delivery, Delivery)
    assert delivery.verdict.ok
    assert delivery.iterations == 1


def test_repair_loop_passes_after_one_round() -> None:
    reviewer = _FirstRoundMissingNote()
    delivery = Pipeline(_backend(), reviewer=reviewer).build_page("失败机理")
    assert delivery.verdict.ok
    assert delivery.iterations == 2
    assert delivery.page.note, "修复后备注必须留档"
    assert reviewer.calls == 2


def test_exhausted_raises_with_verdict_and_iterations() -> None:
    pipe = Pipeline(_backend(), max_iter=3)
    with pytest.raises(ReviewExhaustedError) as exc:
        # hero 骨架缺图：RV003 不修复，循环必然耗尽
        pipe.build_page("失败机理", skeleton="hero")
    err = exc.value
    assert err.iterations == 3
    assert not err.verdict.ok
    assert "RV003" in [f.code for f in err.verdict.findings]


def test_max_iter_one_counts_one_round() -> None:
    pipe = Pipeline(_backend(), max_iter=1)
    with pytest.raises(ReviewExhaustedError) as exc:
        pipe.build_page("失败机理", skeleton="hero")
    assert exc.value.iterations == 1


def test_repair_returns_new_page_and_keeps_input() -> None:
    brief = _brief()
    long_desc = "很长的描述" * 5
    page = Page(
        role="content",
        title="判断句",
        skeleton="track",
        items=[Item(name="一", desc=long_desc)],
        note="旧备注",
    )
    verdict = Verdict(
        findings=[
            Finding("RV001", "critical", "P1 / note", "备注缺", "补 note"),
            Finding("RV004", "warning", "P1 / items[0].desc", "描述长", "压关键词"),
        ]
    )

    repaired = repair(brief, page, verdict)

    assert repaired is not page
    # 入参不得被原地修改
    assert page.note == "旧备注"
    assert page.items[0].desc == long_desc
    # 修复后：备注重建、描述截断
    assert repaired.note != "旧备注"
    assert len(repaired.items[0].desc or "") <= 25
    assert repaired.validate() == []


def test_design_produces_subtitle_from_principles() -> None:
    delivery = Pipeline(_backend()).build_page("失败机理")
    assert delivery.page.subtitle == "只放判断句"


def test_repair_rv006_moves_maturity_word_to_note() -> None:
    brief = _brief()
    page = Page(
        role="content",
        title="方案已开源",
        skeleton="track",
        items=[Item(name="模块", desc="能力待定")],
        note="原备注",
    )
    verdict = Verdict(
        findings=[Finding("RV006", "warning", "P1 / title", "状态词", "移入备注")]
    )

    repaired = repair(brief, page, verdict)

    assert "已开源" not in repaired.title
    assert "待定" not in (repaired.items[0].desc or "")
    assert "状态词移入备注" in (repaired.note or "")
    # 入参标题不得被原地改动
    assert page.title == "方案已开源"


def test_design_without_principles_subtitle_is_none() -> None:
    brief = ResearchBrief(
        brief=PageBrief(topic="t", claim="判断句", page_role="content", principles=[]),
        cards=[ClaimCard(claim="卡一", support="支持句", evidence=["证据一"])],
    )
    assert design(brief).subtitle is None
