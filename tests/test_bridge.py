"""Engine 接入 Pipeline 闭环的离线确定性回归。

成功路径：ReplayBackend 驱动 `Pipeline.build_pptx`，断言产物存在、可被
`Presentation` 重开、单页、静态门通过、`PptxDelivery` 三字段类型正确，
且 `iterations` 与 `build_page` 一致；再直调 `render_verified` 做同类断言。
失败路径：monkeypatch 桥接模块内引用的 `run_gates` 返回违规报告，断言
`EngineQualityError` 原样透传 issues。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pptx import Presentation

from pptforge.engine import bridge
from pptforge.gates.checks import GateReport
from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import (
    DeckDelivery,
    DeckPageSpec,
    Delivery,
    Pipeline,
    PptxDelivery,
)


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


def _assert_single_slide(path: Path) -> None:
    prs = Presentation(str(path))
    assert len(prs.slides) == 1


def test_build_pptx_produces_gated_slide(tmp_path: Path) -> None:
    pipe = Pipeline(_backend())
    before = pipe.build_page("失败机理")

    out = tmp_path / "e2e.pptx"
    result = pipe.build_pptx("失败机理", out, deck_title="闭环验收")

    assert isinstance(result, PptxDelivery)
    assert isinstance(result.delivery, Delivery)
    assert isinstance(result.gate_report, GateReport)
    assert result.pptx == out
    assert out.exists() and out.stat().st_size > 0
    _assert_single_slide(out)
    assert result.gate_report.ok
    assert result.delivery.iterations == before.iterations


def test_render_verified_direct(tmp_path: Path) -> None:
    delivery = Pipeline(_backend()).build_page("失败机理")

    out = tmp_path / "direct.pptx"
    path = bridge.render_verified(delivery.page, out, deck_title="直调验收")

    assert path == out
    assert out.exists() and out.stat().st_size > 0
    _assert_single_slide(out)


def test_render_verified_raises_on_gate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    delivery = Pipeline(_backend()).build_page("失败机理")
    bad = GateReport(issues=["P1 故意违规"])
    monkeypatch.setattr(bridge, "run_gates", lambda _prs: bad)

    with pytest.raises(bridge.EngineQualityError) as exc:
        bridge.render_verified(delivery.page, tmp_path / "bad.pptx")

    assert exc.value.issues == ["P1 故意违规"]


def test_build_deck_produces_gated_multi_slide(tmp_path: Path) -> None:
    pipe = Pipeline(_backend())
    specs = [
        DeckPageSpec(topic="失败机理", skeleton="track"),
        DeckPageSpec(topic="失败机理", skeleton="topology"),
        DeckPageSpec(topic="失败机理", skeleton="track"),
    ]

    out = tmp_path / "deck.pptx"
    result = pipe.build_deck(specs, out, deck_title="多页验收")

    assert isinstance(result, DeckDelivery)
    assert result.pptx == out
    assert len(result.deliveries) == 3
    assert result.gate_report.ok
    assert len(Presentation(str(out)).slides) == 3


def test_build_deck_rejects_empty_specs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="至少需要一个页面规格"):
        Pipeline(_backend()).build_deck([], tmp_path / "empty.pptx")


def test_render_deck_verified_direct(tmp_path: Path) -> None:
    pipe = Pipeline(_backend())
    delivery = pipe.build_page("失败机理")
    from pptforge.models import Deck

    deck = Deck(title="直调多页", pages=[delivery.page, delivery.page])
    out = tmp_path / "deck.pptx"

    path = bridge.render_deck_verified(deck, out)

    assert path == out
    assert len(Presentation(str(out)).slides) == 2


def test_render_deck_verified_raises_on_gate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    delivery = Pipeline(_backend()).build_page("失败机理")
    from pptforge.models import Deck

    deck = Deck(title="坏多页", pages=[delivery.page])
    monkeypatch.setattr(
        bridge, "run_gates", lambda _prs: GateReport(issues=["P2 故意违规"])
    )

    with pytest.raises(bridge.EngineQualityError) as exc:
        bridge.render_deck_verified(deck, tmp_path / "bad.pptx")

    assert exc.value.issues == ["P2 故意违规"]
