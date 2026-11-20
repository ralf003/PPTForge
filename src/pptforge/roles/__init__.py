"""角色编排层：Director / Researcher / Designer / Reviewer 及结构化产物。

Designer 当前是模块级确定性函数集合（design / repair / pick_skeleton），
不设独立类；角色名对应 `pptforge.roles.designer` 模块。
"""

from pptforge.roles.designer import design, pick_skeleton, repair
from pptforge.roles.director import Director
from pptforge.roles.llm import (
    LLMBackend,
    OpenAICompatibleBackend,
    ReplayBackend,
    default_backend,
    extract_json,
)
from pptforge.roles.pipeline import Delivery, Pipeline, ReviewExhaustedError
from pptforge.roles.researcher import Researcher
from pptforge.roles.reviewer import Finding, Reviewer, Verdict
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief

__all__ = [
    "Director",
    "Researcher",
    "Reviewer",
    "Pipeline",
    "Delivery",
    "ReviewExhaustedError",
    "Finding",
    "Verdict",
    "design",
    "repair",
    "pick_skeleton",
    "LLMBackend",
    "OpenAICompatibleBackend",
    "ReplayBackend",
    "default_backend",
    "extract_json",
    "ClaimCard",
    "PageBrief",
    "ResearchBrief",
]
