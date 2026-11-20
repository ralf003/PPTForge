"""骨架库回归测试：每个骨架生成的页面必须通过全部质量门。"""

from __future__ import annotations

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE

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


# ---- 单 body 项自适应版式 ----


def _single_page(skeleton: str) -> Page:
    return Page(
        role="content",
        skeleton=skeleton,
        title="单条目判断句",
        subtitle="口径句只放判断",
        items=[Item(name="单条机制", desc="单条机制解释", value="12%")],
        claim="结论判断句。",
        note="留档备注",
    )


@pytest.mark.parametrize("skeleton", ["track", "stat", "topology"])
def test_single_item_adaptive_passes_gates(skeleton: str, tmp_path) -> None:
    prs = _build(_single_page(skeleton), tmp_path, f"single_{skeleton}")
    report = run_gates(prs)
    assert report.ok, f"{skeleton} 单条目未通过门禁：{report.issues}"


def test_track_single_hides_multi_node_labels(tmp_path) -> None:
    """单节点不渲染仅多元素才有意义的起点/终局标签。"""
    prs = _build(_single_page("track"), tmp_path, "single_track")
    texts = [
        sh.text_frame.text
        for sh in prs.slides[0].shapes
        if sh.has_text_frame
    ]
    assert not any("起点" in t or "终局" in t for t in texts)


def test_stat_single_item_without_value_passes_gates(tmp_path) -> None:
    """无量化值的 stat 单条目：不出大号占位符，过静态门。"""
    page = Page(
        role="content", skeleton="stat", title="单条目判断句",
        items=[Item(name="核心机制", desc=None, value=None)],
        claim="结论判断句。", note="留档备注",
    )
    prs = _build(page, tmp_path, "stat_no_value")
    report = run_gates(prs)
    assert report.ok, report.issues
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert not any(t.strip() == "—" for t in texts)


def test_topology_single_hides_layer_arrows(tmp_path) -> None:
    """单层级不渲染层间箭头。"""
    prs = _build(_single_page("topology"), tmp_path, "single_topo")

    def _is_arrow(sh) -> bool:
        try:
            return sh.auto_shape_type == MSO_SHAPE.DOWN_ARROW
        except ValueError:
            return False

    arrows = [sh for sh in prs.slides[0].shapes if _is_arrow(sh)]
    assert arrows == []


# ---- 容量硬门：超容量 / 空条目抛错，不静默截断或退化 ----


@pytest.mark.parametrize(
    "skeleton,cap",
    [("track", 4), ("stat", 4), ("split", 4), ("topology", 5)],
)
def test_skeleton_rejects_over_capacity(skeleton: str, cap: int, tmp_path) -> None:
    items = [Item(name=f"要点{i}") for i in range(cap + 1)]
    page = Page(
        role="content", skeleton=skeleton, title="标题", items=items, note="备注"
    )
    with pytest.raises(ValueError, match="容量上限"):
        render_deck(_deck(page), tmp_path / "over.pptx")


@pytest.mark.parametrize("skeleton", ["track", "stat", "topology", "split"])
def test_skeleton_rejects_empty_items(skeleton: str, tmp_path) -> None:
    page = Page(
        role="content", skeleton=skeleton, title="标题", items=[], note="备注"
    )
    with pytest.raises(ValueError, match="至少需要一个条目"):
        render_deck(_deck(page), tmp_path / "empty.pptx")
