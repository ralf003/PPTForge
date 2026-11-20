"""图片骨架（hero/split）回归：测试现场生成图片，不依赖仓库素材。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation

from pptforge.engine.renderer import render_deck
from pptforge.gates.checks import run_gates
from pptforge.models import Deck, Item, Page


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    """生成一张比画布更宽的渐变图，用于验证裁剪铺满不变形。"""
    img = Image.new("RGB", (2000, 1125), (11, 31, 58))
    for x in range(2000, 0, -40):
        for y in range(0, 1125, 40):
            img.paste((31, 111, 235), (x - 40, y, x, y + 40))
    out = tmp_path / "photo.jpg"
    img.save(out, quality=85)
    return out


HERO = Page(
    role="content",
    skeleton="hero",
    title="判断句压在图上，不靠半透明",
    subtitle="全幅图承担视觉，文字只在暗色带里",
    claim="能力不在工具多，在取舍准。",
)


def _page_with_image(page: Page, photo: Path) -> Page:
    page.image = str(photo)
    return page


def _build(page: Page, tmp_path: Path, name: str) -> Presentation:
    out = render_deck(Deck(title="图片骨架", pages=[page]), tmp_path / f"{name}.pptx")
    return Presentation(str(out))


def test_hero_passes_gates(photo: Path, tmp_path: Path) -> None:
    prs = _build(_page_with_image(HERO, photo), tmp_path, "hero")
    report = run_gates(prs)
    assert report.ok, f"hero 未通过门禁：{report.issues}"


def test_split_passes_gates(photo: Path, tmp_path: Path) -> None:
    page = _page_with_image(
        Page(
            role="content",
            skeleton="split",
            title="左文右图",
            subtitle="两栏分工",
            items=[
                Item(name="动机", desc="人很难判断纯 AI 代码"),
                Item(name="机制", desc="评审委员会输出硬门"),
            ],
        ),
        photo,
    )
    prs = _build(page, tmp_path, "split")
    report = run_gates(prs)
    assert report.ok, f"split 未通过门禁：{report.issues}"


def test_hero_without_image_does_not_blank(photo: Path, tmp_path: Path) -> None:
    """缺图时退化为深色底，不能变成白页。"""
    prs = _build(HERO, tmp_path, "hero_noimg")
    slide = prs.slides[0]
    full_bleed = [s for s in slide.shapes if s.width >= prs.slide_width * 0.99]
    assert full_bleed, "缺图时未铺满底板"


def test_split_picture_is_cropped_not_stretched(photo: Path, tmp_path: Path) -> None:
    """图更宽时必须裁左右，不能靠拉伸填满。"""
    page = _page_with_image(
        Page(role="content", skeleton="split", title="裁剪校验", items=[Item(name="一")]),
        photo,
    )
    prs = _build(page, tmp_path, "split_crop")
    pics = [s for s in prs.slides[0].shapes if s.shape_type == 13]
    assert pics, "未找到图片"
    assert pics[0].crop_left > 0.01 and pics[0].crop_right > 0.01, "未做左右裁剪"
