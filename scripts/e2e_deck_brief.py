"""端到端脚本：ReplayBackend 驱动 Deck 级大纲冻结 + 非 content 页生产。

验证 `Pipeline.brief_deck` 一次冻结整份大纲，`build_from_brief` 按页型分流
出 cover/section/content/summary，整份同时过静态门与逐页视觉门。

用法：
    python scripts/e2e_deck_brief.py [输出.pptx]
默认输出 `/tmp/verify_brief.pptx`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import Pipeline

TOPIC = "智能体操作系统的确定性质量保障"
AUDIENCE = "技术决策者"

# 冻结的五页结构：封面 → 章节 → 两内容页 → 结论
PLANS = [
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
        for role, claim, skeleton in PLANS
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


# 每个 content 主轴对应的三张独立主张卡（机制名互不相同，避免节点/层条同名）
CARD_SETS: dict[str, tuple[str, str, str]] = {
    "误差沿长链级联坍缩": (
        "误差累积：单步偏差逐级放大",
        "长链传导：偏差跨节点不收敛",
        "误差沿长链级联坍缩",
    ),
    "分层拓扑内建治理面": (
        "分层隔离：故障约束在层内",
        "治理内建：管控面随拓扑下沉",
        "分层拓扑内建治理面",
    ),
}


def _researcher(claim: str) -> str:
    c1, c2, c3 = CARD_SETS[claim]
    return json.dumps(
        {
            "cards": [
                {
                    "claim": c1,
                    "support": "确定性回放产出的机制解释",
                    "evidence": ["离线门禁记录"],
                    "gap": None,
                },
                {
                    "claim": c2,
                    "support": "约束沿链路逐级传导",
                    "evidence": ["链路回放"],
                    "gap": None,
                },
                {
                    "claim": c3,
                    "support": "质量门内建在执行链路中",
                    "evidence": ["闭环验收日志"],
                    "gap": None,
                },
            ]
        },
        ensure_ascii=False,
    )


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/verify_brief.pptx")
    # content 的 claim 键先注册：researcher prompt 含 claim，先命中 claim 键；
    # deck director prompt 不含具体 content claim，不会被 claim 键误匹配。
    responses: dict[str, str] = {claim: _researcher(claim) for claim in CONTENT_CLAIMS}
    responses["一次冻结整份 Deck"] = _director_deck()

    pipe = Pipeline(ReplayBackend(responses))
    brief = pipe.brief_deck(TOPIC, AUDIENCE)
    assert [p.page_role for p in brief.pages] == [r for r, _, _ in PLANS]

    result = pipe.build_from_brief(brief, output)
    roles = [d.page.role for d in result.deliveries]
    print(
        f"已产出：{result.pptx}（页数：{len(result.deliveries)}，页型：{','.join(roles)}，"
        f"静态门通过：{result.gate_report.ok}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
