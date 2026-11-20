"""Director（导演）：冻结一页的论点与页型，设大纲确认门。

Director 不做证据收集，只决定"这一页要让读者接受什么判断"。
产物 PageBrief 冻结后，下游角色不得偏离其唯一主张。
"""

from __future__ import annotations

from pptforge.roles.llm import LLMBackend, extract_json
from pptforge.roles.schemas import DeckBrief, DeckPagePlan, PageBrief

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

_DECK_DIRECTOR_PROMPT = """你是 PPTForge 的 Director（导演），
负责一次冻结整份 Deck 的大纲，而不是逐页定调。
Deck 主题：{topic}
目标受众：{audience}
页型结构提示（按此页序，可在 content 内调整骨架）：{structure}

要求：
1. 给出整份 Deck 标题 title 与一条贯穿全稿的论点链主线 thesis（判断句）。
2. 逐页给出 pages，每页含 topic、claim（本页唯一判断句）、page_role、
   skeleton（content 页必填 track/stat/topology/hero/split，其余页型为 null）、
   principles（2-4 条图面原则）。
3. 首页必须是 cover、末页必须是 summary；各页 claim 不得重复，论点链要逐页推进。
4. 图面只放结构化关键词与判断句，解释进备注；只输出 JSON，
   字段：title, audience, thesis, pages。
"""

# 标准页型结构：封面 → 章节 → 若干内容页 → 结论
DEFAULT_CONTENT_PAGES = 2


def default_structure(n_content: int = DEFAULT_CONTENT_PAGES) -> tuple[str, ...]:
    """无显式结构提示时的标准页型序列。"""
    n = max(1, n_content)
    return ("cover", "section", *(("content",) * n), "summary")


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

    def brief_deck(
        self,
        topic: str,
        audience: str = "通用技术听众",
        structure: tuple[str, ...] | None = None,
    ) -> DeckBrief:
        """一次冻结整份大纲：论点链主线、逐页主张/页型/骨架、页序与衔接。"""
        seq = structure or default_structure()
        prompt = _DECK_DIRECTOR_PROMPT.format(
            topic=topic, audience=audience, structure=",".join(seq)
        )
        data = extract_json(self.backend.complete(prompt))
        raw_pages = data.get("pages", [])
        pages = [
            DeckPagePlan(
                topic=str(p.get("topic", topic)),
                claim=str(p["claim"]),
                page_role=str(p["page_role"]),
                skeleton=(str(p["skeleton"]) if p.get("skeleton") else None),
                principles=[str(x) for x in p.get("principles", [])],
            )
            for p in raw_pages
        ]
        brief = DeckBrief(
            title=str(data.get("title", topic)),
            audience=str(data.get("audience", audience)),
            pages=pages,
            thesis=str(data.get("thesis", "")),
        )
        problems = brief.validate()
        if problems:
            raise ValueError("Director Deck 产物校验失败：" + "；".join(problems))
        return brief
