"""角色编排回归测试：Director/Researcher/Pipeline（回放后端驱动）。"""

from __future__ import annotations

import json

import pytest

from pptforge.roles import Pipeline, ReplayBackend
from pptforge.roles.director import Director
from pptforge.roles.researcher import Researcher


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
