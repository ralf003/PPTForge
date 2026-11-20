"""端到端脚本：ReplayBackend 驱动 `Pipeline.build_deck` 产出多页 PPTX。

供 `scripts/verify.sh` 在视觉门阶段调用；离线、确定性，不接真实后端。
三页均为 content 页（当前 Designer 只产 content），分别指定 track/topology/track
骨架，验证多页静态门与逐页视觉门在同一份产物上同时成立。

用法：
    python scripts/e2e_deck_pipeline.py [输出.pptx]
默认输出 `/tmp/verify_deck.pptx`。
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import DeckPageSpec, Pipeline

TOPICS = ("多页主题甲", "多页主题乙", "多页主题丙")
CLAIMS = ("误差沿长链级联坍缩", "分层拓扑内建治理面", "闭环质量门阻断缺陷交付")
SKELETONS = ("track", "topology", "track")


def _director(topic: str, claim: str) -> str:
    import json

    return json.dumps(
        {
            "topic": topic,
            "claim": claim,
            "page_role": "content",
            "audience": "技术决策者",
            "principles": ["图面只放判断句"],
        },
        ensure_ascii=False,
    )


def _researcher(claim: str) -> str:
    import json

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
                    "claim": f"{claim}的次级机制",
                    "support": "约束沿链路逐级传导",
                    "evidence": ["链路回放"],
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


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/verify_deck.pptx")
    # claim 键必须在 topic 键之前：Researcher prompt 同时含 topic 与 claim，
    # 先命中 claim 才不会错拿 Director 响应；Director prompt 不含 claim，落到 topic 键。
    responses: dict[str, str] = {}
    for topic, claim in zip(TOPICS, CLAIMS):
        responses[claim] = _researcher(claim)
    for topic, claim in zip(TOPICS, CLAIMS):
        responses[topic] = _director(topic, claim)

    backend = ReplayBackend(responses)
    specs = [
        DeckPageSpec(topic=t, skeleton=sk)
        for t, sk in zip(TOPICS, SKELETONS)
    ]
    result = Pipeline(backend).build_deck(
        specs, output, deck_title="多页端到端闭环验收"
    )
    print(
        f"已产出：{result.pptx}（页数：{len(result.deliveries)}，"
        f"静态门通过：{result.gate_report.ok}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
