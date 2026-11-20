"""角色编排回归测试：Director/Researcher/Pipeline（回放后端驱动）。"""

from __future__ import annotations

import json

import pytest

from pptforge.roles import Pipeline, ReplayBackend
from pptforge.roles.director import Director
from pptforge.roles.researcher import Researcher
from pptforge.roles.schemas import ClaimCard, PageBrief


def _backend() -> ReplayBackend:
    director = json.dumps(
        {
            "topic": "测试主题",
            "claim": "本页核心判断",
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
                    "support": "机制解释",
                    "evidence": ["来源A"],
                    "gap": None,
                }
            ]
        },
        ensure_ascii=False,
    )
    return ReplayBackend(
        {
            "Director（导演）": director,
            "Researcher（研究专家）": researcher,
        }
    )


def test_director_produces_brief() -> None:
    brief = Director(_backend()).brief_page("测试主题")
    assert brief.claim == "本页核心判断"
    assert brief.page_role == "content"
    assert brief.validate() == []


def test_researcher_produces_cards() -> None:
    brief = Director(_backend()).brief_page("测试主题")
    result = Researcher(_backend()).research(brief)
    assert len(result.cards) == 1
    assert result.cards[0].evidence == ["来源A"]
    assert result.validate() == []


def test_pipeline_end_to_end() -> None:
    result = Pipeline(_backend()).run("测试主题", audience="技术决策者")
    assert result.brief.claim == "本页核心判断"
    assert result.cards[0].claim == "子判断一"


def test_gate_can_block() -> None:
    with pytest.raises(RuntimeError):
        Pipeline(_backend()).run("测试主题", gate=lambda _: False)


def test_invalid_llm_output_rejected() -> None:
    bad = ReplayBackend(
        {
            "Director（导演）": json.dumps(
                {"topic": "t", "claim": "", "page_role": "content"},
                ensure_ascii=False,
            )
        }
    )
    with pytest.raises(ValueError):
        Director(bad).brief_page("t")


# ---- Researcher 组装层负向集：畸形结构统一归一化为 ValueError ----


def _research_brief() -> PageBrief:
    return PageBrief(topic="测试主题", claim="本页核心判断", page_role="content")


def _researcher(payload: str) -> Researcher:
    return Researcher(ReplayBackend({"Researcher（研究专家）": payload}))


_BAD_CASES: list[tuple[str, str]] = [
    ("空 cards", json.dumps({"cards": []}, ensure_ascii=False)),
    ("缺 claim", json.dumps({"cards": [{"support": "支持句"}]}, ensure_ascii=False)),
    ("缺 support", json.dumps({"cards": [{"claim": "主张"}]}, ensure_ascii=False)),
    ("cards 非 list", json.dumps({"cards": "not-a-list"}, ensure_ascii=False)),
    ("cards 为 null", json.dumps({"cards": None}, ensure_ascii=False)),
    ("evidence 标量字符串", json.dumps(
        {"cards": [{"claim": "x", "support": "s", "evidence": "论文A 2026"}]},
        ensure_ascii=False)),
    ("evidence 为 dict", json.dumps(
        {"cards": [{"claim": "x", "support": "s", "evidence": {"url": "x"}}]},
        ensure_ascii=False)),
    ("evidence 含非字符串", json.dumps(
        {"cards": [{"claim": "x", "support": "s", "evidence": [123]}]},
        ensure_ascii=False)),
    ("evidence 全空白", json.dumps(
        {"cards": [{"claim": "x", "support": "s", "evidence": ["", "   "]}]},
        ensure_ascii=False)),
]


@pytest.mark.parametrize("name,payload", _BAD_CASES)
def test_researcher_rejects_malformed_cards(name: str, payload: str) -> None:
    with pytest.raises(ValueError, match="Researcher 产物校验失败"):
        _researcher(payload).research(_research_brief())


def test_card_allows_gap_without_evidence() -> None:
    """暂无可核验证据时，gap 非空即合规，不再逼迫编造占位证据。"""
    card = ClaimCard(claim="x", support="s", evidence=[], gap="信息不足，未能证实")
    assert card.validate() == []


def test_card_rejects_empty_evidence_and_gap() -> None:
    card = ClaimCard(claim="x", support="s", evidence=[], gap=None)
    assert any("evidence" in p for p in card.validate())
