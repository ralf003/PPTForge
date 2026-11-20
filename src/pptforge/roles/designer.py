"""Designer：把主张卡压成图面语言，并选定骨架。

契约：本角色只产出 `Page`（骨架 + 标题 + 条目 + 结论句），**不产出任何坐标**。
坐标由 engine/skeletons.py 推导，因此同一份产物在任何画布尺寸下都成立。

`compress` 与 `pick_skeleton` 都可注入；默认实现是确定性规则，定位为
LLM 不可用时的替身——规则不会写出"跳步·误引·越界·livelock"这种结构化工整短句，
接上真实后端后应替换为 LLM 判断，但仍必须只回吐语义，不许吐坐标。
"""

from __future__ import annotations

import re

from pptforge.models import Item, Page
from pptforge.roles.schemas import ResearchBrief

# 只认带量纲的数：arXiv 编号、年份、步数都不该被当成指标
_METRIC = re.compile(r"\d+(?:\.\d+)?(?:%|万|亿|倍)")


def _short_name(claim: str, limit: int = 8) -> str:
    """claim 的"机制名"通常在冒号前，取它；过长则截断。"""
    head = re.split(r"[：:]", claim, maxsplit=1)[0].strip()
    return head if len(head) <= limit else head[:limit]


def _short_desc(support: str, limit: int = 16) -> str:
    """取第一个分句，避免整段论证挤进图面。"""
    head = re.split(r"[，,。；;]", support, maxsplit=1)[0].strip()
    return head if len(head) <= limit else head[:limit]


def _key_value(support: str, evidence: list[str], limit: int = 3) -> str | None:
    """找出两条带量纲的可比数，排成"旧 → 新"；找不到就留给图面空白。"""
    text = " ".join([support, *evidence])
    nums = [m.group(0) for m in _METRIC.finditer(text)]
    uniq = list(dict.fromkeys(nums))
    if len(uniq) >= 2:
        return f"{uniq[0]} → {uniq[1]}"
    if len(uniq) == 1:
        return uniq[0]
    return None


def pick_skeleton(brief: ResearchBrief) -> str:
    """按内容形态选骨架：分层→topology，纯指标→stat，其余→track。"""
    topic = brief.brief.topic
    if any(k in topic for k in ("层", "架构", "分层", "栈", "组件")):
        return "topology"
    if any(k in topic for k in ("指标", "占比", "数量", "数字")):
        return "stat"
    return "track"


def design(brief: ResearchBrief, skeleton: str | None = None) -> Page:
    """主张卡 → 一页可渲染的 Page。最后一张卡升格为结论带（它是"往哪走"）。"""
    problems = brief.validate()
    if problems:
        raise ValueError("研究产物校验失败：" + "；".join(problems))

    cards = brief.cards
    sk = skeleton or pick_skeleton(brief)
    # 最后一张卡是"往哪走"：主张作结论带主句，support 压成支撑句
    claim = None
    if len(cards) >= 2:
        claim = f"{cards[-1].claim}\n{_short_desc(cards[-1].support, 30)}"

    body_cards = cards[:-1] if claim else cards
    if sk == "stat":
        items = [
            Item(
                name=_short_name(c.claim, 10),
                desc=_short_desc(c.support),
                value=_key_value(c.support, c.evidence),
            )
            for c in body_cards
        ]
    else:
        items = [
            Item(
                name=_short_name(c.claim),
                desc=_short_desc(c.support),
                value=_key_value(c.support, c.evidence),
            )
            for c in body_cards
        ]

    # 证据与缺口一律进备注，不占图面
    note = "\n".join(
        f"[{i}] {c.claim}\n支持：{c.support}\n证据：" + "；".join(c.evidence)
        + (f"\n缺口：{c.gap}" if c.gap else "")
        for i, c in enumerate(cards, start=1)
    )

    return Page(
        role="content",
        skeleton=sk,
        title=brief.brief.claim,
        items=items,
        claim=claim,
        note=note,
    )
