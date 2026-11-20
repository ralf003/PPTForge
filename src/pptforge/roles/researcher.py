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
        if not isinstance(data, dict):
            raise ValueError("Researcher 产物校验失败：后端输出顶层必须是 JSON 对象")
        raw_cards = data.get("cards", [])
        if not isinstance(raw_cards, list):
            raise ValueError("Researcher 产物校验失败：cards 必须是数组")

        cards: list[ClaimCard] = []
        problems: list[str] = []
        for i, raw in enumerate(raw_cards, start=1):
            if not isinstance(raw, dict):
                problems.append(f"主张卡{i}：结构非法，必须是对象")
                continue
            claim = raw.get("claim")
            support = raw.get("support")
            if not isinstance(claim, str) or not claim.strip():
                problems.append(f"主张卡{i}：claim 缺失或为空")
                continue
            if not isinstance(support, str) or not support.strip():
                problems.append(f"主张卡{i}：support 缺失或为空")
                continue

            raw_evidence = raw.get("evidence", [])
            if raw_evidence is None:
                raw_evidence = []
            if not isinstance(raw_evidence, list):
                # 标量 / dict 不做隐式转换（避免字符串被逐字符拆开、dict 取键）
                problems.append(f"主张卡{i}：evidence 必须是字符串数组")
                continue
            evidence: list[str] = []
            evidence_bad = False
            for entry in raw_evidence:
                if not isinstance(entry, str):
                    evidence_bad = True
                    break
                entry = entry.strip()
                if entry:
                    evidence.append(entry)
            if evidence_bad:
                problems.append(f"主张卡{i}：evidence 条目必须是字符串")
                continue

            gap = raw.get("gap")
            gap_text = gap.strip() if isinstance(gap, str) and gap.strip() else None
            cards.append(
                ClaimCard(
                    claim=claim.strip(),
                    support=support.strip(),
                    evidence=evidence,
                    gap=gap_text,
                )
            )

        if problems:
            raise ValueError("Researcher 产物校验失败：" + "；".join(problems))

        result = ResearchBrief(brief=brief, cards=cards)
        problems = result.validate()
        if problems:
            raise ValueError("Researcher 产物校验失败：" + "；".join(problems))
        return result
