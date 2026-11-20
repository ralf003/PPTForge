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
from pptforge.roles.reviewer import MATURITY_WORDS, Verdict
from pptforge.roles.schemas import ClaimCard, ResearchBrief

# 只认带量纲的数：arXiv 编号、年份、步数都不该被当成指标
_METRIC = re.compile(r"\d+(?:\.\d+)?(?:%|万|亿|倍)")

_DESC_LIMIT = 24
_TITLE_LIMIT = 28


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


def _build_note(cards: list[ClaimCard]) -> str:
    """证据与缺口一律进备注，不占图面。"""
    return "\n".join(
        f"[{i}] {c.claim}\n支持：{c.support}\n证据：" + "；".join(c.evidence)
        + (f"\n缺口：{c.gap}" if c.gap else "")
        for i, c in enumerate(cards, start=1)
    )


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

    # 副标题取 Director 冻结的第一条图面原则；没有就留 None，禁止编造
    subtitle = brief.brief.principles[0] if brief.brief.principles else None

    return Page(
        role="content",
        skeleton=sk,
        title=brief.brief.claim,
        subtitle=subtitle,
        items=items,
        claim=claim,
        note=_build_note(cards),
    )


def repair(brief: ResearchBrief, page: Page, verdict: Verdict) -> Page:
    """按 verdict 里的 finding.code 做确定性修复，返回新 Page，不改入参。

    找不到对应修复的 code 原样保留；RV003（缺图）不修复——图无法凭空造，
    保持 finding 让打回循环耗尽后升级人工。修复后重新跑 Page.validate()。
    """
    problems = brief.validate()
    if problems:
        raise ValueError("研究产物校验失败：" + "；".join(problems))

    codes = {f.code for f in verdict.findings}
    new = Page(
        role=page.role,
        title=page.title,
        subtitle=page.subtitle,
        items=[Item(name=i.name, desc=i.desc, value=i.value, label=i.label) for i in page.items],
        note=page.note,
        skeleton=page.skeleton,
        claim=page.claim,
        image=page.image,
    )

    # RV001：备注缺失，从主张卡重建证据/缺口/口径留档
    if "RV001" in codes:
        new.note = _build_note(brief.cards)

    # RV002：content 页无骨架，按内容形态重选
    if "RV002" in codes:
        new.skeleton = pick_skeleton(brief)

    # RV004：描述压到关键词长度，超出截断加省略号
    if "RV004" in codes:
        for item in new.items:
            if item.desc and len(item.desc.strip()) > _DESC_LIMIT:
                item.desc = item.desc.strip()[:_DESC_LIMIT] + "…"

    # RV005：stat 条目补不出量化值时，骨架降为 track，不再强求大数字
    if "RV005" in codes and new.skeleton == "stat":
        new.skeleton = "track"

    # RV006：状态/成熟度词从图面字段剔除，追加进备注
    if "RV006" in codes:
        new.note = _strip_maturity(new)

    # RV007：标题截断到判断句长度
    if "RV007" in codes and new.title and len(new.title.strip()) > _TITLE_LIMIT:
        new.title = new.title.strip()[:_TITLE_LIMIT] + "…"

    problems = new.validate()
    if problems:
        raise ValueError("修复后校验失败：" + "；".join(problems))
    return new


def _strip_maturity(page: Page) -> str | None:
    """把图面字段里的成熟度/状态词移进备注。

    标题剔除后若为空会丢判断句，此时回退原标题；该条 RV006 保持命中，
    交由循环耗尽后升级人工，不伪造一个空标题。
    """
    moved: list[str] = []

    def clean(text: str | None) -> str | None:
        if not text:
            return text
        out = text
        for word in MATURITY_WORDS:
            if word in out:
                moved.append(word)
                out = out.replace(word, "")
        stripped = re.sub(r"\s+", " ", out).strip(" ，,；;：:")
        return stripped or None

    page.title = clean(page.title) or page.title
    page.subtitle = clean(page.subtitle)
    page.claim = clean(page.claim)
    for item in page.items:
        item.name = clean(item.name) or item.name
        item.desc = clean(item.desc)
        item.value = clean(item.value)

    suffix = "状态词移入备注：" + "、".join(dict.fromkeys(moved)) if moved else None
    if suffix is None:
        return page.note
    return f"{page.note}\n{suffix}" if page.note else suffix
