"""Researcher（研究专家）：围绕 Director 冻结的主张检索、求证、抽象。

产出主张卡（claim/support/evidence/gap）。证据不足时在 gap 标注，
禁止用编造内容填补；当前后端若不具备联网能力，调用方需提供接地后端。
"""

from __future__ import annotations

from pptforge.roles.llm import LLMBackend, extract_json
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief

_RESEARCHER_PROMPT = """你是 PPTForge 的 Researcher（研究专家），围绕给定页面主张做求证。
本页主题：{topic}
本页唯一主张：{claim}
目标受众：{audience}

要求：
1. 拆解为 2-4 张主张卡，每张卡给出可检验的 claim、机制解释 support、可追溯证据 evidence。
2. evidence 必须是可核验来源（论文/官方报告/权威机构/一手数据），禁止编造链接或数字；
   无法证实的内容不要写进 evidence，改在 gap 标注信息缺口。
3. 只输出 JSON，字段：cards，为数组，每项含 claim, support, evidence(字符串数组), gap(可空)。
"""


class Researcher:
    def __init__(self, backend: LLMBackend) -> None:
        self.backend = backend

    def research(self, brief: PageBrief) -> ResearchBrief:
        prompt = _RESEARCHER_PROMPT.format(
            topic=brief.topic, claim=brief.claim, audience=brief.audience
        )
        data = extract_json(self.backend.complete(prompt))
        raw_cards = data.get("cards", [])
        cards = [
            ClaimCard(
                claim=str(c["claim"]),
                support=str(c["support"]),
                evidence=[str(e) for e in c.get("evidence", [])],
                gap=(str(c["gap"]) if c.get("gap") else None),
            )
            for c in raw_cards
        ]
        result = ResearchBrief(brief=brief, cards=cards)
        problems = result.validate()
        if problems:
            raise ValueError("Researcher 产物校验失败：" + "；".join(problems))
        return result
