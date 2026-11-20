"""像素级视觉门回归：空页、大片留白、深底满版、页型分档与确定性。

测试自己合成 PNG，不依赖渲染产物与 LibreOffice，保证 CI 干净环境可跑。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pptforge.gates.visual import analyze, run_visual_gates

BG = (244, 246, 250)
INK = (11, 31, 58)
W, H = 1467, 825


def _blank(path: Path) -> Path:
    Image.new("RGB", (W, H), BG).save(path)
    return path


def _dense(path: Path) -> Path:
    """铺满结构：左右两栏 + 底部深色带，模拟正常内容页。"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([80, 60, 900, 130], fill=INK)
    for i in range(4):
        top = 230 + i * 120
        d.rectangle([100, top, 620, top + 55], fill=INK)
        d.rectangle([760, top, 1340, top + 55], fill=(31, 111, 235))
    d.rectangle([0, 640, W, H], fill=(11, 31, 58))
    img.save(path)
    return path


def _top_void(path: Path) -> Path:
    """病态页：内容全挤在下三分之一，上半屏空着——配图被缩成插图的典型症状。"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 640, W, H], fill=(11, 31, 58))
    for i in range(2):
        top = 700 + i * 55
        d.rectangle([100, top, 700, top + 35], fill=INK)
    img.save(path)
    return path


def _dark_section(path: Path) -> Path:
    """深底满版分隔页：同色大面积是设计，中间只有一行白字。"""
    img = Image.new("RGB", (W, H), (11, 31, 58))
    d = ImageDraw.Draw(img)
    d.rectangle([120, 330, 700, 380], fill=(255, 255, 255))
    d.rectangle([120, 395, 520, 425], fill=(34, 211, 238))
    img.save(path)
    return path


def _sixty_void(path: Path) -> Path:
    """浅底页，上 60% 空着：低于封面阈值、高于内容页阈值。"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([100, 520, W - 100, 780], fill=INK)
    img.save(path)
    return path


def test_blank_page_reports_empty(tmp_path: Path) -> None:
    v = analyze(_blank(tmp_path / "b.png"), page=1)
    assert v.ink_ratio < 0.15
    assert v.issues, "全空页必须报出来"
    assert "空页" in v.issues[0]


def test_dense_page_passes(tmp_path: Path) -> None:
    v = analyze(_dense(tmp_path / "dense.png"), page=2)
    assert not v.issues, v.issues
    assert v.ink_ratio > 0.15


def test_large_void_is_reported(tmp_path: Path) -> None:
    v = analyze(_top_void(tmp_path / "void.png"), page=3)
    assert v.issues, "上半屏空必须报出来"
    assert any("留白" in i for i in v.issues), v.issues


def test_dark_full_bleed_page_passes(tmp_path: Path) -> None:
    """深底分隔页不能因为同色大面积被判留白。"""
    v = analyze(_dark_section(tmp_path / "dark.png"), page=1)
    assert not v.issues, v.issues


def test_pure_dark_page_still_reported(tmp_path: Path) -> None:
    """纯深底、无字无图，仍是空页——放宽不等于放行。"""
    plain = Image.new("RGB", (W, H), (11, 31, 58))
    plain.save(tmp_path / "plain.png")
    v = analyze(tmp_path / "plain.png", page=1)
    assert v.issues, "纯底色页必须报出来"


def test_role_tier_separates_design_from_defect(tmp_path: Path) -> None:
    """同一张浅底空图：封面容忍，内容页拦截。"""
    p = _sixty_void(tmp_path / "sixty.png")
    assert not analyze(p, page=1, role="cover").issues
    assert analyze(p, page=1, role="content").issues


def test_analysis_is_deterministic(tmp_path: Path) -> None:
    p = _dense(tmp_path / "det.png")
    a = analyze(p, page=1)
    b = analyze(p, page=1)
    assert (a.ink_ratio, a.max_empty_ratio, a.empty_box) == (
        b.ink_ratio,
        b.max_empty_ratio,
        b.empty_box,
    )


def test_run_visual_gates_aggregates(tmp_path: Path) -> None:
    report = run_visual_gates(
        [_dense(tmp_path / "ok.png"), _blank(tmp_path / "bad.png")]
    )
    assert not report.ok
    assert len(report.pages) == 2
    assert any("第 2 页" in i for i in report.issues), report.issues
