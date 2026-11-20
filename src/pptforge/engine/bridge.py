"""Engine 与 Pipeline 之间的单一职责桥接。

把角色闭环产出的单页 `Page` 包成 `Deck` 落盘，再重新打开产物跑静态门：
- 静态门通过：返回产物 `Path`；
- 静态门不通过：抛 `EngineQualityError`，issues 原样透出，禁止静默交付。

视觉门（soffice / pdftoppm / check-visual）不进库方法，只在 `scripts/verify.sh`
与 CI 端到端执行；本模块只吃静态门 `run_gates`。
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from pptforge.engine.renderer import Renderer
from pptforge.gates.checks import GateReport, run_gates
from pptforge.models import Deck, Page
from pptforge.theme import Theme


class EngineQualityError(RuntimeError):
    """静态门不通过时抛出；issues 原样保留门侧发现的问题，供升级人工。"""

    def __init__(self, issues: list[str]) -> None:
        self.issues = list(issues)
        super().__init__("静态质量门未通过：" + "；".join(self.issues))


def render_with_report(
    page: Page,
    output: str | Path,
    deck_title: str | None = None,
    theme: Theme | None = None,
) -> tuple[Path, GateReport]:
    """渲染单页并跑静态门，返回产物路径与门报告；门只跑一次供上层复用。"""
    deck = Deck(title=deck_title or page.title, pages=[page])
    out = Renderer(theme).save(deck, output)
    report = run_gates(Presentation(str(out)))
    return out, report


def render_verified(
    page: Page,
    output: str | Path,
    deck_title: str | None = None,
    theme: Theme | None = None,
) -> Path:
    """渲染单页并过静态门；不通过抛 `EngineQualityError`，通过返回产物路径。"""
    out, report = render_with_report(page, output, deck_title, theme)
    if not report.ok:
        raise EngineQualityError(report.issues)
    return out
