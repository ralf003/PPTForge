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

# 受支持的骨架（可复用确定性版式）；具体布局由 engine/skeletons 实现
SKELETONS = ("track", "stat", "topology")


@dataclass
class Item:
    """一条结构化要点：名称 + 描述 + 可选关键量化与短标。"""

    name: str
    desc: str | None = None
    value: str | None = None
    label: str | None = None


@dataclass
class Page:
    role: str
    title: str
    subtitle: str | None = None
    items: list[Item] = field(default_factory=list)
    note: str | None = None
    # 骨架：为空时按 role 走基础四页型
    skeleton: str | None = None
    # 结论句：track 等骨架用它渲染底部结论带
    claim: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.role not in ROLES:
            problems.append(f"未知页型 role={self.role!r}，可选 {ROLES}")
        if not self.title.strip():
            problems.append("页面标题不能为空")
        if self.skeleton is not None and self.skeleton not in SKELETONS:
            problems.append(
                f"未知骨架 skeleton={self.skeleton!r}，可选 {SKELETONS}"
            )
        if self.role == "content" and not self.items and self.skeleton is None:
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
                Item(
                    name=str(it["name"]),
                    desc=it.get("desc"),
                    value=it.get("value"),
                    label=it.get("label"),
                )
                for it in raw.get("items", [])
            ]
            pages.append(
                Page(
                    role=raw.get("role", "content"),
                    title=str(raw["title"]),
                    subtitle=raw.get("subtitle"),
                    items=items,
                    note=raw.get("note"),
                    skeleton=raw.get("skeleton"),
                    claim=raw.get("claim"),
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
