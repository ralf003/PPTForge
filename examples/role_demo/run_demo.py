"""真实页面端到端演示：Director → Researcher → 可渲染 PPTX。

当前环境无外部 LLM 凭据，用真实求证得到的 fixture 经 ReplayBackend 驱动同一套 Pipeline；
配置 OpenAI 兼容后端后，同样的代码直接由真实 LLM 驱动。
ResearchBrief -> Page 的映射是确定性适配（Designer 雏形），后续由 Designer 角色替换。
"""

from __future__ import annotations

import json
from pathlib import Path

from pptforge.models import Deck, Item, Page
from pptforge.roles import Pipeline, ReplayBackend
from pptforge.roles.schemas import ResearchBrief

HERE = Path(__file__).resolve().parent


def _load(name: str) -> str:
    return json.dumps(json.loads((HERE / name).read_text(encoding="utf-8")), ensure_ascii=False)


def to_page(result: ResearchBrief) -> Page:
    items = [Item(name=card.claim, desc=card.support) for card in result.cards]
    evidence_lines = []
    for i, card in enumerate(result.cards, start=1):
        for ev in card.evidence:
            evidence_lines.append(f"卡{i}证据：{ev}")
        if card.gap:
            evidence_lines.append(f"卡{i}信息缺口：{card.gap}")
    note = "；".join(evidence_lines)
    return Page(
        role=result.brief.page_role,
        title=result.brief.topic,
        items=items,
        note=note,
    )


def main(out_path: str | Path) -> Path:
    backend = ReplayBackend(
        {
            "Director（导演）": _load("director.json"),
            "Researcher（研究专家）": _load("researcher.json"),
        }
    )
    result = Pipeline(backend).run("智能体规模化的核心挑战", audience="技术决策者")
    assert result.validate() == []

    page = to_page(result)
    deck = Deck(title="智能体规模化的核心挑战", pages=[page])
    assert deck.validate() == []

    from pptforge.engine.renderer import render_deck

    return render_deck(deck, out_path)


if __name__ == "__main__":
    out = main(HERE / "role_demo.pptx")
    print("已生成真实页面：", out)
