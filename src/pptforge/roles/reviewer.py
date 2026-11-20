"""评审委员会：把"这页能不能交"变成可复现的判决，而不是主观印象。

`backend=None` 时是纯确定性规则：无网络、可复现、可在 CI 干净环境跑。
`backend` 提供时额外跑一轮语义评审，JSON findings 合并进来；但语义判断
不可复现，不得单独构成 critical，最多降为 warning（硬门只由确定性规则把守）。
"""

from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

from pptforge.models import Deck, Page
from pptforge.roles.llm import LLMBackend, extract_json

SEVERITIES = ("critical", "warning", "info")

# 成熟度/状态词：这类进度信息属于备注口径，不占图面
MATURITY_WORDS = ("已开源", "演进中", "尚未", "待定", "TODO", "进行中")

# 依赖配图的骨架
IMAGE_SKELETONS = ("hero", "split")

_DESC_LIMIT = 24
_TITLE_LIMIT = 28

_REVIEW_PROMPT = """你是 PPTForge 的 Reviewer（评审委员会），对单页语义做补充审查。
只挑确定性规则覆盖不到、且读者一眼会困惑的问题；不要重复报结构校验已拦截的项。

页面内容：
{page_text}

要求：
1. 只输出 JSON，字段 findings，为数组，每项含 code, severity, target, message, fix。
2. severity 只能取 critical/warning/info；但注意：你的判断不可复现，
   调用方会把 critical 一律降级为 warning，不要把可被规则判定的硬缺陷交给你。
3. target 定位到页与字段，如 "P3 / items[2].desc"。
"""


@dataclass
class Finding:
    """一条可复现的评审发现：稳定规则码 + 级别 + 定位 + 事实 + 修复方向。"""

    code: str  # 稳定规则码，RV001 起，永不复用
    severity: str  # critical / warning / info
    target: str  # 定位：如 "P3 / items[2].desc"、"P1"
    message: str  # 问题是什么（事实）
    fix: str  # 可执行的修复方向（打回必须带这一项）


@dataclass
class Verdict:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """无 critical 即放行；warning/info 不阻断交付。"""
        return not self.criticals

    @property
    def criticals(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "critical"]

    def format(self) -> str:
        """逐条人读输出，供 CLI 打印。"""
        if not self.findings:
            return "评审通过：无 finding"
        lines: list[str] = []
        for f in self.findings:
            lines.append(
                f"[{f.severity.upper()}] {f.code} {f.target}: {f.message}"
                f"（修复：{f.fix}）"
            )
        return "\n".join(lines)


class Reviewer:
    def __init__(self, backend: LLMBackend | None = None) -> None:
        self.backend = backend

    # ---- 入口 ----

    def review_page(self, page: Page, page_no: int = 1) -> Verdict:
        findings = self._deterministic(page, page_no)
        if self.backend is not None:
            findings.extend(self._semantic(page, page_no))
        return Verdict(findings)

    def review(self, deck: Deck) -> Verdict:
        findings: list[Finding] = []
        for i, page in enumerate(deck.pages, start=1):
            findings.extend(self.review_page(page, i).findings)
        findings.extend(self._deck_level(deck))
        return Verdict(findings)

    # ---- 确定性规则 RV001–RV008 ----

    def _deterministic(self, page: Page, page_no: int) -> list[Finding]:
        prefix = f"P{page_no}"
        findings: list[Finding] = []

        # RV001 critical：备注为空，证据/缺口/口径没有留档位置
        if not (page.note and page.note.strip()):
            findings.append(
                Finding(
                    "RV001",
                    "critical",
                    f"{prefix} / note",
                    "备注为空：证据、缺口与口径未留档",
                    "把证据、缺口与口径写进 note",
                )
            )

        # RV002 critical：content 页未选骨架，落到三行均分的基础版式
        if page.role == "content" and page.skeleton is None:
            findings.append(
                Finding(
                    "RV002",
                    "critical",
                    f"{prefix} / skeleton",
                    "content 页未选骨架",
                    "按内容形态选一个骨架（track/stat/topology/hero/split）",
                )
            )

        # RV003 critical：hero/split 骨架缺配图或文件不存在
        if page.skeleton in IMAGE_SKELETONS:
            missing = not page.image or not Path(page.image).exists()
            if missing:
                findings.append(
                    Finding(
                        "RV003",
                        "critical",
                        f"{prefix} / image",
                        f"骨架 {page.skeleton} 依赖配图，但 image 为空或文件不存在",
                        "补一张本地配图，或改用不依赖图的骨架",
                    )
                )

        # RV004 warning：条目描述过长，解释应进备注
        for i, item in enumerate(page.items):
            if item.desc and len(item.desc.strip()) > _DESC_LIMIT:
                findings.append(
                    Finding(
                        "RV004",
                        "warning",
                        f"{prefix} / items[{i}].desc",
                        f"描述 {len(item.desc.strip())} 字，超出 {_DESC_LIMIT} 字图面上限",
                        "压成关键词，解释进 note",
                    )
                )

        # RV005 warning：stat 骨架条目缺量化值
        if page.skeleton == "stat":
            for i, item in enumerate(page.items):
                if item.value is None:
                    findings.append(
                        Finding(
                            "RV005",
                            "warning",
                            f"{prefix} / items[{i}].value",
                            "stat 骨架条目缺量化值",
                            "补量化指标，或把骨架降为 track",
                        )
                    )

        # RV006 warning：图面字段命中成熟度/状态词，应移入备注
        screen_fields = self._screen_fields(page)
        for field_name, text in screen_fields:
            if not text:
                continue
            hit = next((w for w in MATURITY_WORDS if w in text), None)
            if hit is not None:
                findings.append(
                    Finding(
                        "RV006",
                        "warning",
                        f"{prefix} / {field_name}",
                        f"图面命中状态/成熟度词「{hit}」",
                        "把该状态词移入 note，图面只留判断句",
                    )
                )

        # RV007 warning：标题过长，标题只留判断句
        if page.title and len(page.title.strip()) > _TITLE_LIMIT:
            findings.append(
                Finding(
                    "RV007",
                    "warning",
                    f"{prefix} / title",
                    f"标题 {len(page.title.strip())} 字，超出 {_TITLE_LIMIT} 字上限",
                    "标题只留判断句，细节进 note",
                )
            )

        return findings

    def _deck_level(self, deck: Deck) -> list[Finding]:
        findings: list[Finding] = []
        if not deck.pages:
            return findings
        if deck.pages[0].role != "cover":
            findings.append(
                Finding(
                    "RV008",
                    "info",
                    "P1",
                    "首页不是 cover 封面页",
                    "补一张封面页",
                )
            )
        last = len(deck.pages)
        if deck.pages[-1].role != "summary":
            findings.append(
                Finding(
                    "RV008",
                    "info",
                    f"P{last}",
                    "末页不是 summary 结论页",
                    "补一张结论页",
                )
            )
        return findings

    @staticmethod
    def _screen_fields(page: Page) -> list[tuple[str, str | None]]:
        fields: list[tuple[str, str | None]] = [
            ("title", page.title),
            ("subtitle", page.subtitle),
            ("claim", page.claim),
        ]
        for i, item in enumerate(page.items):
            fields.append((f"items[{i}].name", item.name))
            fields.append((f"items[{i}].desc", item.desc))
            fields.append((f"items[{i}].value", item.value))
        return fields

    # ---- 可选语义评审（不可复现，最高 warning） ----

    def _semantic(self, page: Page, page_no: int) -> list[Finding]:
        assert self.backend is not None
        screen = [
            f"{name}: {text}"
            for name, text in self._screen_fields(page)
            if text
        ]
        page_text = "\n".join(
            [f"role: {page.role}", f"skeleton: {page.skeleton or '—'}", *screen]
        )
        try:
            data = extract_json(self.backend.complete(_REVIEW_PROMPT.format(page_text=page_text)))
        except (
            ValueError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            RuntimeError,
            urllib.error.URLError,
            OSError,
        ):
            # 解析失败，或传输 / HTTP / 后端不可用：语义评审静默缺席，不阻断确定性判决
            return []
        raw_findings = data.get("findings", [])
        if not isinstance(raw_findings, list):
            return []

        findings: list[Finding] = []
        for entry in raw_findings:
            if not isinstance(entry, dict):
                continue
            severity = str(entry.get("severity", "warning"))
            if severity not in SEVERITIES:
                severity = "warning"
            # 不可复现的语义判断不得做硬门：critical 一律降级为 warning
            if severity == "critical":
                severity = "warning"
            findings.append(
                Finding(
                    code=str(entry.get("code", "RV-SEM")),
                    severity=severity,
                    target=str(entry.get("target", f"P{page_no}")),
                    message=str(entry.get("message", "")),
                    fix=str(entry.get("fix", "")),
                )
            )
        return findings
