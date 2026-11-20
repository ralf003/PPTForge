"""角色产物 schema：角色之间的结构化交接契约。

判断类角色（Director/Researcher/...）由可替换 LLM 后端承担，
但产物必须落到确定性 dataclass 并通过校验，禁止把自由文本直接传给下游。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pptforge.models import ROLES, SKELETONS


@dataclass
class PageBrief:
    """Director 产物：一页的定调（冻结后下游不得偏离）。"""

    topic: str
    claim: str
    page_role: str
    audience: str = "通用技术听众"
    principles: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.topic.strip():
            problems.append("页面主题不能为空")
        if not self.claim.strip():
            problems.append("本页唯一主张不能为空")
        if self.page_role not in ROLES:
            problems.append(f"页型 {self.page_role!r} 不受支持，可选 {ROLES}")
        return problems


@dataclass
class ClaimCard:
    """Researcher 产物：一张主张卡（claim/support/evidence/gap）。"""

    claim: str
    support: str
    evidence: list[str] = field(default_factory=list)
    gap: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.claim.strip():
            problems.append("claim 不能为空")
        if not self.support.strip():
            problems.append("support 不能为空")
        # evidence 与 gap 至少其一：暂无可核验证据时允许只在 gap 标注，
        # 不逼迫往 evidence 里塞占位证据；两者皆空才报错。
        if not self.evidence and not (self.gap and self.gap.strip()):
            problems.append("evidence 至少一条；暂无可核验证据时必须在 gap 标注信息缺口")
        return problems


@dataclass
class ResearchBrief:
    """Researcher 对一页的完整研究产物。"""

    brief: PageBrief
    cards: list[ClaimCard] = field(default_factory=list)

    def validate(self) -> list[str]:
        problems = self.brief.validate()
        if not self.cards:
            problems.append("Researcher 至少产出一张主张卡")
        for i, card in enumerate(self.cards, start=1):
            for p in card.validate():
                problems.append(f"主张卡{i}：{p}")
        return problems


@dataclass
class DeckPagePlan:
    """DeckBrief 中一页的冻结规划：页型、唯一主张、骨架（仅 content 允许）。

    与 PageBrief 的区别：PageBrief 是逐页独立定调的产物，本结构是整份大纲
    一次冻结时的一页，页序与跨页衔接由 DeckBrief 统一校验。
    """

    topic: str
    claim: str
    page_role: str
    skeleton: str | None = None
    principles: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.topic.strip():
            problems.append("页面主题不能为空")
        if not self.claim.strip():
            problems.append("本页唯一主张不能为空")
        if self.page_role not in ROLES:
            problems.append(f"页型 {self.page_role!r} 不受支持，可选 {ROLES}")
        if self.page_role == "content":
            if self.skeleton is None:
                problems.append("content 页必须冻结一个骨架，否则会被 RV002 拦截")
            elif self.skeleton not in SKELETONS:
                problems.append(
                    f"骨架 {self.skeleton!r} 不受支持，可选 {SKELETONS}"
                )
        elif self.skeleton is not None:
            problems.append(
                f"{self.page_role} 页走基础页型，不得挂骨架（收到 {self.skeleton!r}）"
            )
        return problems


@dataclass
class DeckBrief:
    """Director 一次冻结的整份大纲：论点链主线 + 逐页规划 + 页序硬约束。

    冻结后下游不得偏离：content 页的研究与设计都以对应 DeckPagePlan 为准，
    封面/结论的衔接由本结构的页序规则保证，而不是出片后再补。
    """

    title: str
    audience: str
    pages: list[DeckPagePlan]
    thesis: str = ""

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.title.strip():
            problems.append("Deck 标题不能为空")
        if not self.thesis.strip():
            problems.append("论点链主线 thesis 不能为空")
        if not self.pages:
            problems.append("Deck 至少需要一页")
        for i, plan in enumerate(self.pages, start=1):
            for p in plan.validate():
                problems.append(f"第{i}页：{p}")
        if self.pages:
            if self.pages[0].page_role != "cover":
                problems.append("页序错误：首页必须是 cover 封面页")
            if self.pages[-1].page_role != "summary":
                problems.append("页序错误：末页必须是 summary 结论页")
        # 论点链必须在推进：完全相同的 claim 不允许出现两次
        seen: set[str] = set()
        for i, plan in enumerate(self.pages, start=1):
            key = plan.claim.strip()
            if key in seen:
                problems.append(f"第{i}页主张与前页重复：{key!r}，论点链不得原地重复")
            seen.add(key)
        return problems
