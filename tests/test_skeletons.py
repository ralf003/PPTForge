"""骨架库回归测试：每个骨架生成的页面必须通过全部质量门。"""

from __future__ import annotations

import pytest
from pptx import Presentation

from pptforge.engine.renderer import render_deck
from pptforge.engine.skeletons import skeleton_keys
from pptforge.gates.checks import run_gates
from pptforge.models import SKELETONS, Deck, Item, Page

TRACK_PAGE = Page(
    role="content",
    skeleton="track",
    title="规模化的瓶颈是长程轨迹与治理，不是模型能力",
    items=[
        Item(name="轨迹拉长", desc="单任务步数跨数量级", value="90% → 12%"),
        Item(name="偏差累积", desc="跳步·误引·livelock"),
        Item(name="成本失控", desc="上下文反复重放", value="180万→6万"),
    ],
    claim="治理必须内建在运行时，而不是事后补测。",
    note="完整主张留档在此。",
)

STAT_PAGE = Page(
    role="content",
    skeleton="stat",
    title="三个量化指标界定了问题边界",
    items=[
        Item(name="长程任务成功率", desc="超过 40 步后", value="12%"),
        Item(name="单任务 token", desc="未压缩轨迹", value="180万"),
        Item(name="压缩后 token", desc="加治理后", value="6万"),
    ],
)

TOPO_PAGE = Page(
    role="content",
    skeleton="topology",
    title="四层分工：判断在上，约束在下",
    items=[
        Item(name="接入层", desc="指令解析 / 权限校验 / 人类闸口"),
        Item(name="编排层", desc="Director / Researcher / Designer"),
        Item(name="能力层", desc="检索 / 渲染 / 质量门 / 工具调用"),
        Item(name="底座层", desc="确定性引擎 / 布局计算 / OOXML 修复"),
    ],
)


def _deck(page: Page) -> Deck:
    return Deck(title="骨架测试", pages=[page])


def _build(page: Page, tmp_path, name: str) -> Presentation:
    out = render_deck(_deck(page), tmp_path / f"{name}.pptx")
    return Presentation(str(out))


@pytest.mark.parametrize(
    "page,name", [(TRACK_PAGE, "track"), (STAT_PAGE, "stat"), (TOPO_PAGE, "topology")]
)
def test_each_skeleton_passes_gates(page: Page, name: str, tmp_path) -> None:
    prs = _build(page, tmp_path, name)
    report = run_gates(prs)
    assert report.ok, f"{name} 骨架未通过门禁：{report.issues}"


def test_registry_matches_model_contract() -> None:
    """模型层声明的骨架必须与引擎注册表一致，避免提示了却不支持。"""
    assert set(skeleton_keys()) == set(SKELETONS)


def test_unknown_skeleton_raises(tmp_path) -> None:
    bad = Page(role="content", skeleton="grid", title="不存在的骨架")
    with pytest.raises(ValueError, match="未知骨架"):
        render_deck(_deck(bad), tmp_path / "bad.pptx")


def test_no_skeleton_falls_back_to_content(tmp_path) -> None:
    """未指定骨架时仍走基础页型，保证向后兼容。"""
    page = Page(role="content", title="基础页型", items=[Item(name="要点", desc="说明")])
    prs = _build(page, tmp_path, "plain")
    assert len(prs.slides) == 1


def test_track_claim_band_is_rendered(tmp_path) -> None:
    """结论带必须落成整幅深色条，而非普通文字框。"""
    prs = _build(TRACK_PAGE, tmp_path, "track_band")
    slide = prs.slides[0]
    full_width_bands = [
        sh
        for sh in slide.shapes
        if sh.width > prs.slide_width * 0.95 and sh.height > 914400
    ]
    assert full_width_bands, "未找到整幅结论带"
