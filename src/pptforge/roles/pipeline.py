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
from pathlib import Path

from pptforge.engine import bridge
from pptforge.gates.checks import GateReport
from pptforge.models import Deck, Page
from pptforge.roles.designer import design, design_page, design_summary, repair
from pptforge.roles.director import Director
from pptforge.roles.llm import LLMBackend
from pptforge.roles.researcher import Researcher
from pptforge.roles.reviewer import Reviewer, Verdict
from pptforge.roles.schemas import (
    DeckBrief,
    DeckPagePlan,
    PageBrief,
    ResearchBrief,
)

# 确认门：接收冻结的 PageBrief，返回是否放行
Gate = Callable[[PageBrief], bool]

# Deck 级确认门：接收一次冻结的整份 DeckBrief，返回是否放行
DeckGate = Callable[[DeckBrief], bool]


def auto_gate(_brief: PageBrief) -> bool:
    return True


def auto_deck_gate(_brief: DeckBrief) -> bool:
    return True


@dataclass
class Delivery:
    """闭环交付物：最终页、最后一次判决、实际评审轮数。"""

    page: Page
    verdict: Verdict
    iterations: int


@dataclass
class PptxDelivery:
    """闭环出片交付物：PPTX 路径、角色层 Delivery、静态门报告。"""

    pptx: Path
    delivery: Delivery
    gate_report: GateReport


@dataclass
class DeckPageSpec:
    """多页 Deck 中一页的输入规格：逐页独立走闭环，页间不共享上下文。"""

    topic: str
    audience: str = "通用技术听众"
    page_role: str = "content"
    skeleton: str | None = None


@dataclass
class DeckDelivery:
    """多页闭环出片交付物：PPTX 路径、逐页 Delivery 列表、整份静态门报告。"""

    pptx: Path
    deliveries: list[Delivery]
    gate_report: GateReport


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

    def build_pptx(
        self,
        topic: str,
        output: str | Path,
        audience: str = "通用技术听众",
        page_role: str = "content",
        gate: Gate = auto_gate,
        skeleton: str | None = None,
        *,
        deck_title: str | None = None,
    ) -> PptxDelivery:
        """单页闭环出片：`build_page` 之后接 Engine 渲染并过静态门。

        `build_page` 逻辑一字不改；静态门不通过抛 `EngineQualityError`，
        返回的 `PptxDelivery` 携带产物路径、角色层 Delivery 与静态门报告。
        """
        delivery = self.build_page(topic, audience, page_role, gate, skeleton)
        pptx, report = bridge.render_with_report(
            delivery.page, output, deck_title=deck_title
        )
        if not report.ok:
            raise bridge.EngineQualityError(report.issues)
        return PptxDelivery(pptx=pptx, delivery=delivery, gate_report=report)

    def build_deck(
        self,
        specs: list[DeckPageSpec],
        output: str | Path,
        *,
        deck_title: str | None = None,
        gate: Gate = auto_gate,
    ) -> DeckDelivery:
        """多页闭环出片：逐页跑 `build_page`，组装成 Deck 后整份过静态门。

        注意当前 Designer 只产出 role=content 的页，cover/section/summary
        暂不能经此链路生成；逐页确认门按页调用，Deck 级论点链冻结
        （Director 一次冻结整份大纲）是后续独立工作项。
        """
        if not specs:
            raise ValueError("build_deck 至少需要一个页面规格")
        deliveries: list[Delivery] = []
        for spec in specs:
            deliveries.append(
                self.build_page(
                    spec.topic,
                    spec.audience,
                    spec.page_role,
                    gate,
                    spec.skeleton,
                )
            )
        deck = Deck(
            title=deck_title or f"PPTForge {len(specs)} 页 Deck",
            pages=[d.page for d in deliveries],
        )
        pptx, report = bridge.render_deck_with_report(deck, output)
        if not report.ok:
            raise bridge.EngineQualityError(report.issues)
        return DeckDelivery(pptx=pptx, deliveries=deliveries, gate_report=report)

    # ---- Deck 级大纲冻结 + 非 content 页生产（#39） ----

    def brief_deck(
        self,
        topic: str,
        audience: str = "通用技术听众",
        structure: tuple[str, ...] | None = None,
    ) -> DeckBrief:
        """委托 Director 一次冻结整份大纲，可单独确认后再出片。"""
        return self.director.brief_deck(topic, audience, structure)

    def _run_content_plan(self, plan: DeckPagePlan) -> Delivery:
        """content 页：冻结规划 → 研究 → 设计 → 打回循环，逻辑与 build_page 同构。"""
        page_brief = PageBrief(
            topic=plan.topic,
            claim=plan.claim,
            page_role="content",
            audience=self._audience,
            principles=list(plan.principles),
        )
        research = self.researcher.research(page_brief)
        page = design_page(plan, research, deck_title=self._deck_title)
        verdict = self.reviewer.review_page(page, 1)
        iterations = 1
        while not verdict.ok and iterations < self.max_iter:
            page = repair(research, page, verdict)
            verdict = self.reviewer.review_page(page, 1)
            iterations += 1
        if not verdict.ok:
            raise ReviewExhaustedError(verdict, iterations)
        return Delivery(page=page, verdict=verdict, iterations=iterations)

    def _run_static_plan(
        self, plan: DeckPagePlan, page_no: int, content_pages: list[Page] | None
    ) -> Delivery:
        """cover/section/summary：不经研究直接出页，review 出现 critical 即构造缺陷。"""
        if plan.page_role == "summary":
            page = design_summary(
                plan, content_pages or [], deck_title=self._deck_title
            )
        else:
            page = design_page(plan, None, deck_title=self._deck_title)
        verdict = self.reviewer.review_page(page, page_no)
        if not verdict.ok:
            # 非 content 页没有 repair 路径：critical 说明出页构造有 bug，直接暴露不静默
            raise RuntimeError(
                f"{plan.page_role} 页（P{page_no}）评审出现 critical："
                + "；".join(f.message for f in verdict.criticals)
            )
        return Delivery(page=page, verdict=verdict, iterations=1)

    def build_from_brief(
        self,
        brief: DeckBrief,
        output: str | Path,
        gate: DeckGate = auto_deck_gate,
    ) -> DeckDelivery:
        """按冻结大纲出整份 Deck：页型分流，整份过静态门。

        cover/section 不跑 Researcher；content 走研究与打回循环；
        summary 在所有 content 完成后基于其判断句汇总。
        """
        if not gate(brief):
            raise RuntimeError("Deck 大纲确认门未放行，已中止（未进入生产阶段）")

        # 暂存出片上下文，供内部方法使用，避免长参数列表
        self._audience = brief.audience
        self._deck_title = brief.title

        deliveries: list[Delivery] = []
        content_pages: list[Page] = []
        for i, plan in enumerate(brief.pages, start=1):
            if plan.page_role == "content":
                delivery = self._run_content_plan(plan)
                content_pages.append(delivery.page)
                deliveries.append(delivery)
            else:
                deliveries.append(
                    self._run_static_plan(plan, i, content_pages)
                )

        deck = Deck(title=brief.title, pages=[d.page for d in deliveries])
        pptx, report = bridge.render_deck_with_report(deck, output)
        if not report.ok:
            raise bridge.EngineQualityError(report.issues)
        return DeckDelivery(pptx=pptx, deliveries=deliveries, gate_report=report)
