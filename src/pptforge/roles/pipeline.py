"""角色编排器：串联 Director → Researcher，含大纲冻结确认门。

角色之间只传递经过校验的结构化产物，禁止把原始外部文本直接拼进下游 prompt（防污染）。
确认门 gate 默认自动通过（全自动模式）；需要人工/外部授权时可注入自定义 gate。
"""

from __future__ import annotations

from collections.abc import Callable

from pptforge.roles.director import Director
from pptforge.roles.llm import LLMBackend
from pptforge.roles.researcher import Researcher
from pptforge.roles.schemas import PageBrief, ResearchBrief

# 确认门：接收冻结的 PageBrief，返回是否放行
Gate = Callable[[PageBrief], bool]


def auto_gate(_brief: PageBrief) -> bool:
    return True


class Pipeline:
    def __init__(self, backend: LLMBackend) -> None:
        self.director = Director(backend)
        self.researcher = Researcher(backend)

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
