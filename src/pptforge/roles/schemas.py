"""角色产物 schema：角色之间的结构化交接契约。

判断类角色（Director/Researcher/...）由可替换 LLM 后端承担，
但产物必须落到确定性 dataclass 并通过校验，禁止把自由文本直接传给下游。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pptforge.models import ROLES


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
        if not self.evidence:
            problems.append("evidence 至少一条，缺失证据应在 gap 标注而非留空")
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
