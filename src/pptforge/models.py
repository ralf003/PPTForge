"""声明式数据模型：Deck / Page / Item，可从 YAML 加载并校验。

agent 只描述意图（页型、标题、要点、备注），不写坐标；
坐标由确定性渲染引擎计算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 受支持的页型
ROLES = ("cover", "section", "content", "summary")


@dataclass
class Item:
    """一条结构化要点：名称 + 简短描述。"""

    name: str
    desc: str | None = None


@dataclass
class Page:
    role: str
    title: str
    subtitle: str | None = None
    items: list[Item] = field(default_factory=list)
    note: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.role not in ROLES:
            problems.append(f"未知页型 role={self.role!r}，可选 {ROLES}")
        if not self.title.strip():
            problems.append("页面标题不能为空")
        if self.role == "content" and not self.items:
            problems.append("content 页至少需要一个 item")
        return problems


@dataclass
class Deck:
    title: str
    pages: list[Page] = field(default_factory=list)
    author: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.title.strip():
            problems.append("Deck 标题不能为空")
        if not self.pages:
            problems.append("Deck 至少需要一页")
        for i, page in enumerate(self.pages, start=1):
            for p in page.validate():
                problems.append(f"第{i}页：{p}")
        return problems

    # ---- 构造 ----
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deck:
        pages: list[Page] = []
        for raw in data.get("pages", []):
            items = [
                Item(name=str(it["name"]), desc=it.get("desc"))
                for it in raw.get("items", [])
            ]
            pages.append(
                Page(
                    role=raw.get("role", "content"),
                    title=str(raw["title"]),
                    subtitle=raw.get("subtitle"),
                    items=items,
                    note=raw.get("note"),
                )
            )
        return cls(
            title=str(data["title"]),
            pages=pages,
            author=data.get("author"),
        )

    @classmethod
    def from_yaml(cls, text: str) -> Deck:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("YAML 顶层必须是映射结构")
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: str | Path) -> Deck:
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))
