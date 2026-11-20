"""Deck 级大纲冻结与非 content 页生产的离线确定性回归。

覆盖 schema 校验（页序/骨架/重复主张）、ReplayBackend 驱动 brief_deck、
build_from_brief 端到端五页、非 content 页留档与不调用 Researcher、
Deck 确认门阻断。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pptx import Presentation

from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import Pipeline
from pptforge.roles.schemas import DeckBrief, DeckPagePlan

TOPIC = "智能体操作系统的确定性质量保障"
AUDIENCE = "技术决策者"
PLANS_RAW = [
    ("cover", "封面定调：质量保障是工程问题", None),
    ("section", "第一章：缺陷从哪里来", None),
    ("content", "误差沿长链级联坍缩", "track"),
    ("content", "分层拓扑内建治理面", "topology"),
    ("summary", "质量门确定性阻断缺陷交付", None),
]
CONTENT_CLAIMS = ("误差沿长链级联坍缩", "分层拓扑内建治理面")


def _director_deck() -> str:
    pages = [
        {
            "topic": TOPIC,
            "claim": claim,
            "page_role": role,
            "skeleton": skeleton,
            "principles": ["图面只放判断句", "解释进备注"],
        }
        for role, claim, skeleton in PLANS_RAW
    ]
    return json.dumps(
        {
            "title": "PPTForge Deck 级冻结验收",
            "audience": AUDIENCE,
            "thesis": "确定性质量门把视觉缺陷拦在交付前",
            "pages": pages,
        },
        ensure_ascii=False,
    )


def _researcher(claim: str) -> str:
    return json.dumps(
        {
            "cards": [
                {
                    "claim": claim,
                    "support": "确定性回放产出的机制解释",
                    "evidence": ["离线门禁记录"],
                    "gap": None,
                },
                {
                    "claim": f"{claim}的治理结论",
                    "support": "质量门内建在执行链路中",
                    "evidence": ["闭环验收日志"],
                    "gap": None,
                },
            ]
        },
        ensure_ascii=False,
    )


def _responses() -> dict[str, str]:
    responses = {claim: _researcher(claim) for claim in CONTENT_CLAIMS}
    responses["一次冻结整份 Deck"] = _director_deck()
    return responses


def _pipeline() -> Pipeline:
    return Pipeline(ReplayBackend(_responses()))


# ---- schema 校验 ----

def test_content_plan_requires_skeleton() -> None:
    problems = DeckPagePlan(topic="t", claim="c", page_role="content").validate()
    assert any("必须冻结一个骨架" in p for p in problems)


def test_non_content_plan_rejects_skeleton() -> None:
    problems = DeckPagePlan(
        topic="t", claim="c", page_role="cover", skeleton="track"
    ).validate()
    assert any("不得挂骨架" in p for p in problems)


def test_plan_rejects_unknown_role_and_empty_claim() -> None:
    problems = DeckPagePlan(topic="t", claim=" ", page_role="unknown").validate()
    assert any("不受支持" in p for p in problems)
    assert any("唯一主张不能为空" in p for p in problems)


def test_deck_brief_requires_cover_first_and_summary_last() -> None:
    plans = [
        DeckPagePlan(topic="t", claim="c1", page_role="section"),
        DeckPagePlan(topic="t", claim="c2", page_role="summary"),
    ]
    problems = DeckBrief(title="T", audience=AUDIENCE, pages=plans).validate()
    assert any("首页必须是 cover" in p for p in problems)


def test_deck_brief_rejects_duplicate_claim() -> None:
    plans = [
        DeckPagePlan(topic="t", claim="相同主张", page_role="cover"),
        DeckPagePlan(
            topic="t", claim="相同主张", page_role="content", skeleton="track"
        ),
        DeckPagePlan(topic="t", claim="结论主张", page_role="summary"),
    ]
    problems = DeckBrief(title="T", audience=AUDIENCE, pages=plans).validate()
    assert any("主张与前页重复" in p for p in problems)


def test_deck_brief_rejects_empty_pages_and_title() -> None:
    problems = DeckBrief(title=" ", audience=AUDIENCE, pages=[]).validate()
    assert any("标题不能为空" in p for p in problems)
    assert any("至少需要一页" in p for p in problems)


# ---- 端到端 ----

def test_brief_deck_returns_frozen_structure() -> None:
    brief = _pipeline().brief_deck(TOPIC, AUDIENCE)
    assert isinstance(brief, DeckBrief)
    assert [p.page_role for p in brief.pages] == [r for r, _, _ in PLANS_RAW]
    assert brief.validate() == []


def test_build_from_brief_end_to_end(tmp_path: Path) -> None:
    pipe = _pipeline()
    brief = pipe.brief_deck(TOPIC, AUDIENCE)
    out = tmp_path / "brief.pptx"
    result = pipe.build_from_brief(brief, out)

    assert result.pptx == out
    assert result.gate_report.ok
    assert len(result.deliveries) == 5
    roles = [d.page.role for d in result.deliveries]
    assert roles == ["cover", "section", "content", "content", "summary"]
    assert len(Presentation(str(out)).slides) == 5


def test_noncontent_pages_have_notes_and_no_skeleton(tmp_path: Path) -> None:
    pipe = _pipeline()
    brief = pipe.brief_deck(TOPIC, AUDIENCE)
    result = pipe.build_from_brief(brief, tmp_path / "b.pptx")
    for delivery in result.deliveries:
        page = delivery.page
        if page.role != "content":
            assert page.skeleton is None
            assert page.note and page.note.strip()


def test_deck_gate_block_aborts_before_production(tmp_path: Path) -> None:
    pipe = _pipeline()
    brief = pipe.brief_deck(TOPIC, AUDIENCE)
    with pytest.raises(RuntimeError, match="大纲确认门未放行"):
        pipe.build_from_brief(brief, tmp_path / "x.pptx", gate=lambda _b: False)
    assert not (tmp_path / "x.pptx").exists()


def test_researcher_only_runs_for_content_pages() -> None:
    class CountingBackend:
        def __init__(self, inner: ReplayBackend) -> None:
            self.inner = inner
            self.research_calls = 0

        def complete(self, prompt: str) -> str:
            if "Researcher（研究专家）" in prompt:
                self.research_calls += 1
            return self.inner.complete(prompt)

    backend = CountingBackend(ReplayBackend(_responses()))
    pipe = Pipeline(backend)
    brief = pipe.brief_deck(TOPIC, AUDIENCE)
    pipe.build_from_brief(brief, Path("/tmp/count_brief.pptx"))
    # 只有两个 content 页触发研究，cover/section/summary 不触发
    assert backend.research_calls == 2
