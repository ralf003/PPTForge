"""角色编排层：Director / Researcher 及结构化产物。"""

from pptforge.roles.director import Director
from pptforge.roles.llm import (
    LLMBackend,
    OpenAICompatibleBackend,
    ReplayBackend,
    default_backend,
    extract_json,
)
from pptforge.roles.pipeline import Pipeline
from pptforge.roles.researcher import Researcher
from pptforge.roles.schemas import ClaimCard, PageBrief, ResearchBrief

__all__ = [
    "Director",
    "Researcher",
    "Pipeline",
    "LLMBackend",
    "OpenAICompatibleBackend",
    "ReplayBackend",
    "default_backend",
    "extract_json",
    "ClaimCard",
    "PageBrief",
    "ResearchBrief",
]
