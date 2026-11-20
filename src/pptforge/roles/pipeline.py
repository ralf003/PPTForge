"""角色编排器：串联 Director → gate → Researcher → Designer → Reviewer 闭环。

角色之间只传递经过校验的结构化产物，禁止把原始外部文本直接拼进下游 prompt（防污染）。
确认门 gate 默认自动通过（全自动模式）；需要人工/外部授权时可注入自定义 gate。

`run()` 保持既有语义：只串 Director → Researcher，返回 ResearchBrief。
`build_page()` 是完整闭环：Designer 出页 → Reviewer 判决，不合格则 repair 后重评，
最多 `max_iter` 轮（含首轮），耗尽抛 ReviewExhaustedError，异常内带最后一次 Verdict。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pptforge.models import Page
from pptforge.roles.designer import design, repair
from pptforge.roles.director import Director
from pptforge.roles.llm import LLMBackend
from pptforge.roles.researcher import Researcher
from pptforge.roles.reviewer import Reviewer, Verdict
from pptforge.roles.schemas import PageBrief, ResearchBrief

# 确认门：接收冻结的 PageBrief，返回是否放行
Gate = Callable[[PageBrief], bool]


def auto_gate(_brief: PageBrief) -> bool:
    return True


@dataclass
class Delivery:
    """闭环交付物：最终页、最后一次判决、实际评审轮数。"""

    page: Page
    verdict: Verdict
    iterations: int


class ReviewExhaustedError(RuntimeError):
    """打回轮次耗尽仍有 critical；异常内带最后一次 Verdict，供升级人工。"""

    def __init__(self, verdict: Verdict, iterations: int) -> None:
        self.verdict = verdict
        self.iterations = iterations
        super().__init__(
            f"评审打回 {iterations} 轮后仍未通过：{len(verdict.criticals)} 条 critical"
        )


class Pipeline:
    def __init__(
        self,
        backend: LLMBackend,
        *,
        reviewer: Reviewer | None = None,
        max_iter: int = 3,
    ) -> None:
        self.director = Director(backend)
        self.researcher = Researcher(backend)
        self.reviewer = reviewer or Reviewer(None)
        self.max_iter = max_iter

    def run(
        self,
        topic: str,
        audience: str = "通用技术听众",
        page_role: str = "content",
        gate: Gate = auto_gate,
    ) -> ResearchBrief:
        brief = self.director.brief_page(
            topic=topic, audience=audience, page_role=page_role
        )
        if not gate(brief):
            raise RuntimeError("大纲确认门未放行，已中止（未进入研究阶段）")
        return self.researcher.research(brief)

    def build_page(
        self,
        topic: str,
        audience: str = "通用技术听众",
        page_role: str = "content",
        gate: Gate = auto_gate,
        skeleton: str | None = None,
    ) -> Delivery:
        """Director → gate → Researcher → Designer → Reviewer 闭环。"""
        brief = self.director.brief_page(
            topic=topic, audience=audience, page_role=page_role
        )
        if not gate(brief):
            raise RuntimeError("大纲确认门未放行，已中止（未进入研究阶段）")
        research = self.researcher.research(brief)

        page = design(research, skeleton=skeleton)
        verdict = self.reviewer.review_page(page, 1)
        iterations = 1
        while not verdict.ok and iterations < self.max_iter:
            page = repair(research, page, verdict)
            verdict = self.reviewer.review_page(page, 1)
            iterations += 1

        if not verdict.ok:
            raise ReviewExhaustedError(verdict, iterations)
        return Delivery(page=page, verdict=verdict, iterations=iterations)
