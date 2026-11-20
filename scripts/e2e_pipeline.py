"""端到端脚本：ReplayBackend 驱动 `Pipeline.build_pptx` 产出单页 PPTX。

供 `scripts/verify.sh` 在视觉门阶段调用；离线、确定性，不接真实后端。
脚本不依赖可执行位，由 verify.sh 用解释器执行。

用法：
    python scripts/e2e_pipeline.py [输出.pptx]
默认输出 `/tmp/verify_e2e.pptx`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pptforge.roles.llm import ReplayBackend
from pptforge.roles.pipeline import Pipeline

DIRECTOR = json.dumps(
    {
        "topic": "智能体长程任务失败机理",
        "claim": "规模化的瓶颈在长程轨迹与治理",
        "page_role": "content",
        "audience": "技术决策者",
        "principles": ["只放判断句"],
    },
    ensure_ascii=False,
)

RESEARCHER = json.dumps(
    {
        "cards": [
            {
                "claim": "误差级联",
                "support": "单步高成功率在长链路上指数级坍缩",
                "evidence": ["链路回放记录"],
                "gap": None,
            },
            {
                "claim": "轨迹幻觉",
                "support": "沿任务序列产生结构性偏离与空转",
                "evidence": ["轨迹日志"],
                "gap": None,
            },
            {
                "claim": "治理内建运行时",
                "support": "把质量门与回环内建在执行链路中",
                "evidence": ["门禁记录"],
                "gap": None,
            },
        ]
    },
    ensure_ascii=False,
)


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/verify_e2e.pptx")
    backend = ReplayBackend(
        {"Director（导演）": DIRECTOR, "Researcher（研究专家）": RESEARCHER}
    )
    result = Pipeline(backend).build_pptx(
        "失败机理", output, deck_title="端到端闭环验收"
    )
    print(
        f"已产出：{result.pptx}（静态门通过：{result.gate_report.ok}，"
        f"评审轮次：{result.delivery.iterations}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
