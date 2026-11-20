"""像素级视觉门：把"空页"和"留白"变成可计算指标。

静态门（checks.py）只看结构，看不出"视觉上是不是空"。本模块要求渲染后的逐页 PNG，
先降采样成固定网格，再判定两件事：

- 空页：非背景像素占比过低。典型原因是配图没加载、文字层全丢，页面只剩底色。
- 最大空白块：画面中单一背景色连续矩形占画布面积过大。这是"上半屏空一片"的量化形式，
  也是配图被缩成小插图后最明显的症状。

算法全程确定性（固定网格 + 直方图最大矩形），同一张图在任何机器上结果一致。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

# 降采样网格：160×90 足以捕捉结构，又不至于把字间距当成空白
GRID_W = 160
GRID_H = 90

# 与背景色的 RGB 欧氏距离阈值：超过即视为"有内容"
INK_DIFF = 24.0

# 非背景像素占比下限：低于此值判为空页
MIN_INK_RATIO = 0.15

# 单一空白块占画布面积上限（真实五页实测 6.2%–20.7%，空页 100%，留出余量后定 28%）
MAX_EMPTY_BLOCK = 0.28

# 分页型阈值（min_ink, max_empty）。封面与分隔页的留白是设计意图，内容页的留白是缺陷，
# 用同一套阈值会把分隔页判成红的，制造假红并让人不再相信门禁。
ROLE_LIMITS: dict[str, tuple[float, float]] = {
    "cover": (0.02, 0.72),
    "section": (0.02, 0.70),
    "summary": (0.02, 0.60),
    "content": (MIN_INK_RATIO, MAX_EMPTY_BLOCK),
}


@dataclass
class PageVisual:
    page: int
    path: str
    ink_ratio: float
    max_empty_ratio: float
    empty_box: tuple[int, int, int, int] = (0, 0, 0, 0)
    issues: list[str] = field(default_factory=list)


@dataclass
class VisualReport:
    pages: list[PageVisual]

    @property
    def issues(self) -> list[str]:
        out: list[str] = []
        for p in self.pages:
            out.extend(p.issues)
        return out

    @property
    def ok(self) -> bool:
        return not self.issues


def _dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _max_empty_rect(rows: list[list[bool]]) -> tuple[float, tuple[int, int, int, int]]:
    """返回（最大全空白矩形占画布比例，矩形 x0/y0/x1/y1）。

    立柱直方图 + 单调栈，O(格数)，无随机性。
    """
    if not rows or not rows[0]:
        return 0.0, (0, 0, 0, 0)
    width = len(rows[0])
    heights = [0] * width
    best_area = 0
    best_box = (0, 0, 0, 0)

    for y, row in enumerate(rows):
        for x, is_empty in enumerate(row):
            heights[x] = heights[x] + 1 if is_empty else 0
        stack: list[tuple[int, int]] = []
        for x in range(width + 1):
            cur = heights[x] if x < width else 0
            start = x
            while stack and stack[-1][1] > cur:
                idx, h = stack.pop()
                area = h * (x - idx)
                if area > best_area:
                    best_area = area
                    best_box = (idx, y - h + 1, x, y + 1)
                start = idx
            stack.append((start, cur))

    total = len(rows) * width
    return (best_area / total if total else 0.0), best_box


def limits_for(role: str | None) -> tuple[float, float]:
    """按页型取（墨迹下限, 空白上限）；未知页型按内容页处理，宁可严不宁可松。"""
    return ROLE_LIMITS.get(role or "content", (MIN_INK_RATIO, MAX_EMPTY_BLOCK))


def analyze(
    png: Path | str,
    page: int = 1,
    min_ink: float = MIN_INK_RATIO,
    max_empty: float = MAX_EMPTY_BLOCK,
    role: str | None = None,
) -> PageVisual:
    if role is not None:
        min_ink, max_empty = limits_for(role)
    path = Path(png)
    img = Image.open(path).convert("RGB").resize((GRID_W, GRID_H), Image.Resampling.BOX)
    pixels = list(img.getdata())
    bg = Counter(pixels).most_common(1)[0][0]

    rows: list[list[bool]] = []
    ink = 0
    for y in range(GRID_H):
        row: list[bool] = []
        for x in range(GRID_W):
            empty = _dist(pixels[y * GRID_W + x], bg) < INK_DIFF
            row.append(empty)
            if not empty:
                ink += 1
        rows.append(row)

    ink_ratio = ink / float(GRID_W * GRID_H)
    max_empty_ratio, box = _max_empty_rect(rows)

    issues: list[str] = []
    name = path.name
    if ink_ratio < min_ink:
        issues.append(
            f"{name}（第 {page} 页）疑似空页：非背景像素仅 {ink_ratio:.1%}（下限 {min_ink:.0%}），"
            "检查配图是否加载、文字层是否丢失"
        )
    if max_empty_ratio > max_empty:
        x0, y0, x1, y1 = box
        issues.append(
            f"{name}（第 {page} 页）存在大片留白：最大空白块占 {max_empty_ratio:.1%}"
            f"（上限 {max_empty:.0%}），位于网格 x{x0}-{x1} / y{y0}-{y1}"
        )
    return PageVisual(
        page=page,
        path=str(path),
        ink_ratio=ink_ratio,
        max_empty_ratio=max_empty_ratio,
        empty_box=box,
        issues=issues,
    )


def run_visual_gates(
    pngs: Sequence[Path | str],
    roles: Sequence[str | None] | None = None,
    min_ink: float | None = None,
    max_empty: float | None = None,
) -> VisualReport:
    pages: list[PageVisual] = []
    for i, png in enumerate(pngs):
        role = roles[i] if roles is not None and i < len(roles) else None
        lo, hi = limits_for(role)
        pages.append(
            analyze(
                png,
                page=i + 1,
                min_ink=lo if min_ink is None else min_ink,
                max_empty=hi if max_empty is None else max_empty,
            )
        )
    return VisualReport(pages=pages)
