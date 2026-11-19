"""Director（导演）：冻结一页的论点与页型，设大纲确认门。

Director 不做证据收集，只决定"这一页要让读者接受什么判断"。
产物 PageBrief 冻结后，下游角色不得偏离其唯一主张。
"""

from __future__ import annotations

from pptforge.roles.llm import LLMBackend, extract_json
from pptforge.roles.schemas import PageBrief

_DIRECTOR_PROMPT = """你是 PPTForge 的 Director（导演），负责为单页 PPT 定调。
输入主题：{topic}
目标受众：{audience}
倾向页型：{page_role}

要求：
1. 用一句可被检验的判断句给出本页唯一主张（claim），不要现象罗列，不要正确的废话。
2. 选定页型 page_role，取值 cover/section/content/summary。
3. 给出 2-4 条图面原则（principles），图面只放结构化关键词与判断句，解释进备注。
4. 只输出 JSON，字段：topic, claim, page_role, audience, principles。
"""


class Director:
    def __init__(self, backend: LLMBackend) -> None:
        self.backend = backend

    def brief_page(
        self,
        topic: str,
        audience: str = "通用技术听众",
        page_role: str = "content",
    ) -> PageBrief:
        prompt = _DIRECTOR_PROMPT.format(
            topic=topic, audience=audience, page_role=page_role
        )
        data = extract_json(self.backend.complete(prompt))
        brief = PageBrief(
            topic=str(data.get("topic", topic)),
            claim=str(data["claim"]),
            page_role=str(data.get("page_role", page_role)),
            audience=str(data.get("audience", audience)),
            principles=[str(x) for x in data.get("principles", [])],
        )
        problems = brief.validate()
        if problems:
            raise ValueError("Director 产物校验失败：" + "；".join(problems))
        return brief
