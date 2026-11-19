"""Designer 实证：同一份 researcher.json，输出视觉设计页而非文字堆。

本脚本扮演 Designer 角色：读 ResearchBrief，决定视觉语法（叙事轨迹 + 递进节点 + 结论带），
再交给 Engine 原生绘制。对比 role_demo（四行文字堆）证明设计层不可省。
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

from pptforge.engine.renderer import Renderer, _rgb
from pptforge.roles.schemas import ResearchBrief

HERE = Path(__file__).resolve().parent

# ---- Designer 的视觉决策（集中声明，不散落）----
TRACK_Y = 4.9
NODE_XS = (2.55, 6.55, 10.55)
NODE_D = (0.30, 0.44, 0.58)  # 直径递进 = 级联放大
NODE_COLORS = ("1F6FEB", "F59E0B", "DC2626")  # 正常 -> 偏移 -> 失控
CARD_W = 3.8
KEY_FACTS = ("90% → 12%", "跳步·误引·livelock", "180万→6万")


def load_brief() -> ResearchBrief:
    from pptforge.roles import Pipeline, ReplayBackend

    def _text(name: str) -> str:
        return json.dumps(
            json.loads((HERE / name).read_text(encoding="utf-8")), ensure_ascii=False
        )

    backend = ReplayBackend(
        {
            "Director（导演）": _text("director.json"),
            "Researcher（研究专家）": _text("researcher.json"),
        }
    )
    return Pipeline(backend).run("智能体规模化的核心挑战", audience="技术决策者")


def _rect(slide, x, y, w, h, color):
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _circle(slide, cx, cy, d, color):
    shape = slide.shapes.add_shape(
        9, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def build(brief: ResearchBrief) -> Renderer:
    t = Renderer().theme
    p, s = t.palette, t.scale
    r = Renderer()
    slide = r._add_slide(p.bg)

    # 标题区：Designer 把长主张抽象为可单行承载的标题，完整表述进备注
    _rect(slide, 0.75, 0.55, 0.12, 0.72, p.blue)
    r._add_text(
        slide, 1.0, 0.45, 11.4, 0.95,
        [("规模化的瓶颈是长程轨迹与治理，不是模型能力", s.page_title - 2, p.dark, True)],
    )
    # 一句口径：只讲图面读法，不重复标题含义
    r._add_text(
        slide, 1.0, 1.5, 11.4, 0.45,
        [("偏差沿同一任务链条逐段放大，右侧最严重", s.section_label + 2, p.mute, False)],
    )

    # 叙事轨迹：一条线串起三个失效点，方向即恶化方向
    _rect(slide, 1.35, TRACK_Y - 0.02, 10.0, 0.04, p.mute)
    r._add_text(
        slide, 0.7, TRACK_Y + 0.12, 0.62, 0.35,
        [("起点", s.footnote, p.mute, False)],
    )
    r._add_text(
        slide, 11.5, TRACK_Y + 0.12, 0.8, 0.35,
        [("终局", s.footnote, p.mute, False)],
    )

    # 三个失效点：圆圈递进放大 = 偏差沿轨迹放大
    # 每点挂一条最硬的关键量化，让图有数据密度；完整证据仍进备注
    for i, (card, cx, d, color, fact) in enumerate(
        zip(brief.cards[:3], NODE_XS, NODE_D, NODE_COLORS, KEY_FACTS)
    ):
        _circle(slide, cx, TRACK_Y, d, color)
        # 机制名（上方，判断句）
        r._add_text(
            slide, cx - CARD_W / 2, 2.90, CARD_W, 0.48,
            [(card.claim.split("：")[0], s.item_name, p.dark, True)],
            align=PP_ALIGN.CENTER,
        )
        # 机制解释（一句话）
        detail = card.claim.split("：")[-1] if "：" in card.claim else card.support
        r._add_text(
            slide, cx - CARD_W / 2, 3.42, CARD_W, 0.60,
            [(detail, s.body - 2, p.mute, False)],
            align=PP_ALIGN.CENTER,
        )
        # 关键量化（紧贴轨迹上方，短促有力）
        # 浅底不用 cyan（对比度仅 1.67，投影看不清），改深蓝/红
        r._add_text(
            slide, cx - CARD_W / 2, 4.06, CARD_W, 0.40,
            [(fact, s.caption, p.blue if i < 2 else p.red, True)],
            align=PP_ALIGN.CENTER,
        )

    # 结论带：第 4 张卡升格为全幅结论，而非并列第四行
    _rect(slide, 0, 5.95, t.slide_width_in, 1.55, p.dark)
    last = brief.cards[3]
    r._add_text(
        slide, 0.95, 6.08, 11.6, 0.6,
        [(last.claim, s.item_name + 4, p.white, True)],
    )
    r._add_text(
        slide, 0.95, 6.72, 11.6, 0.5,
        [(last.support, s.section_label, p.cyan, False)],
    )

    # 证据与缺口全部进备注，不占图面；标题是压缩版，完整主张也留档
    lines = [f"完整主张：{brief.brief.claim}"]
    for i, card in enumerate(brief.cards, 1):
        for ev in card.evidence:
            lines.append(f"卡{i}证据：{ev}")
        if card.gap:
            lines.append(f"卡{i}信息缺口：{card.gap}")
    slide.notes_slide.notes_text_frame.text = "；".join(lines)
    return r


if __name__ == "__main__":
    out = HERE / "designer_demo.pptx"
    build(load_brief()).prs.save(str(out))
    print("已生成设计版：", out)
