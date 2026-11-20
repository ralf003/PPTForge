"""评审委员会回归：RV001–RV008 每条规则至少一个正例与一个反例。

确定性规则不依赖网络；图片用例由 Pillow 现场合成到 tmp_path，不读仓库素材。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pptforge.models import Deck, Item, Page
from pptforge.roles.llm import ReplayBackend
from pptforge.roles.reviewer import Finding, Reviewer, Verdict


def _page(**overrides: object) -> Page:
    defaults: dict[str, object] = {
        "role": "content",
        "title": "本页唯一判断句",
        "subtitle": None,
        "items": [Item(name="要点一", desc="短描述")],
        "note": "证据与缺口留档在备注",
        "skeleton": "track",
        "claim": None,
        "image": None,
    }
    defaults.update(overrides)
    return Page(**defaults)  # type: ignore[arg-type]


def _find(verdict: Verdict, code: str) -> list[Finding]:
    return [f for f in verdict.findings if f.code == code]


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    img = Image.new("RGB", (1200, 675), (11, 31, 58))
    out = tmp_path / "photo.jpg"
    img.save(out, quality=85)
    return out

# ---- RV001：备注为空 ----


def test_rv001_flags_empty_note() -> None:
    verdict = Reviewer().review_page(_page(note=None))
    assert len(_find(verdict, "RV001")) == 1
    assert verdict.criticals[0].fix


def test_rv001_blank_note_counts_as_empty() -> None:
    verdict = Reviewer().review_page(_page(note="   "))
    assert _find(verdict, "RV001")


def test_rv001_passes_with_note() -> None:
    verdict = Reviewer().review_page(_page(note="证据：来源A；缺口：待补"))
    assert not _find(verdict, "RV001")


# ---- RV002：content 页无骨架 ----


def test_rv002_flags_content_without_skeleton() -> None:
    verdict = Reviewer().review_page(_page(skeleton=None))
    assert len(_find(verdict, "RV002")) == 1


def test_rv002_passes_with_skeleton() -> None:
    verdict = Reviewer().review_page(_page(skeleton="track"))
    assert not _find(verdict, "RV002")


# ---- RV003：hero/split 缺图 ----


def test_rv003_flags_hero_without_image() -> None:
    verdict = Reviewer().review_page(_page(skeleton="hero", image=None))
    assert len(_find(verdict, "RV003")) == 1


def test_rv003_flags_missing_image_file(tmp_path: Path) -> None:
    verdict = Reviewer().review_page(
        _page(skeleton="split", image=str(tmp_path / "nope.jpg"))
    )
    assert _find(verdict, "RV003")


def test_rv003_passes_with_existing_image(photo: Path) -> None:
    verdict = Reviewer().review_page(_page(skeleton="hero", image=str(photo)))
    assert not _find(verdict, "RV003")


# ---- RV004：条目描述过长 ----


def test_rv004_flags_long_desc() -> None:
    long_desc = "单步高成功率在长链路上指数级坍缩错误沿轨迹持续传播"
    verdict = Reviewer().review_page(_page(items=[Item(name="要点", desc=long_desc)]))
    hits = _find(verdict, "RV004")
    assert len(hits) == 1
    assert "items[0].desc" in hits[0].target


def test_rv004_passes_with_short_desc() -> None:
    verdict = Reviewer().review_page(_page(items=[Item(name="要点", desc="压成关键词")]))
    assert not _find(verdict, "RV004")


# ---- RV005：stat 条目缺量化值 ----


def test_rv005_flags_stat_item_without_value() -> None:
    verdict = Reviewer().review_page(
        _page(skeleton="stat", items=[Item(name="指标一", desc="无值")])
    )
    assert len(_find(verdict, "RV005")) == 1


def test_rv005_passes_with_values() -> None:
    verdict = Reviewer().review_page(
        _page(
            skeleton="stat",
            items=[Item(name="指标一", desc="有值", value="90% → 12%")],
        )
    )
    assert not _find(verdict, "RV005")


# ---- RV006：图面命中成熟度/状态词 ----


@pytest.mark.parametrize("word", ["已开源", "演进中", "尚未", "待定", "TODO", "进行中"])
def test_rv006_flags_maturity_word_on_screen(word: str) -> None:
    verdict = Reviewer().review_page(_page(title=f"方案{word}，待评审"))
    assert _find(verdict, "RV006")


def test_rv006_flags_maturity_word_in_item_fields() -> None:
    verdict = Reviewer().review_page(
        _page(items=[Item(name="模块", desc="能力待定，后续补齐")])
    )
    assert _find(verdict, "RV006")


def test_rv006_passes_clean_screen() -> None:
    verdict = Reviewer().review_page(
        _page(
            subtitle="只放判断句",
            claim="工程化是规模化前提",
            items=[Item(name="误差级联", desc="沿轨迹放大", value="90% → 12%")],
        )
    )
    assert not _find(verdict, "RV006")


# ---- RV007：标题过长 ----


def test_rv007_flags_long_title() -> None:
    verdict = Reviewer().review_page(
        _page(title="这是一个明显超过二十八个字上限的长标题把论证细节都挤进了图面")
    )
    assert len(_find(verdict, "RV007")) == 1


def test_rv007_passes_short_title() -> None:
    verdict = Reviewer().review_page(_page(title="标题只留判断句"))
    assert not _find(verdict, "RV007")


# ---- RV008：首页封面 / 末页结论 ----


def test_rv008_flags_missing_cover_and_summary() -> None:
    deck = Deck(
        title="测试稿",
        pages=[_page(role="content"), _page(role="content")],
    )
    verdict = Reviewer().review(deck)
    hits = _find(verdict, "RV008")
    assert len(hits) == 2
    assert hits[0].severity == "info"


def test_rv008_passes_with_cover_and_summary() -> None:
    deck = Deck(
        title="测试稿",
        pages=[_page(role="cover"), _page(role="summary")],
    )
    verdict = Reviewer().review(deck)
    assert not _find(verdict, "RV008")


# ---- 后端语义评审：critical 必须降级为 warning ----


def test_semantic_findings_never_become_critical() -> None:
    backend = ReplayBackend(
        {
            "Reviewer（评审委员会）": json.dumps(
                {
                    "findings": [
                        {
                            "code": "SEM-1",
                            "severity": "critical",
                            "target": "P1 / title",
                            "message": "语义判断不可复现",
                            "fix": "人工复核",
                        }
                    ]
                }
            )
        }
    )
    verdict = Reviewer(backend).review_page(_page())
    semantic = [f for f in verdict.findings if f.code == "SEM-1"]
    assert len(semantic) == 1
    assert semantic[0].severity == "warning"
    assert verdict.ok, "语义 critical 降级后不得阻断交付"


def test_semantic_review_silent_on_bad_backend_output() -> None:
    backend = ReplayBackend({"Reviewer（评审委员会）": "不是 JSON"})
    verdict = Reviewer().review_page(_page())
    assert verdict.ok
    assert verdict.findings == []


# ---- Verdict 聚合语义 ----


def test_verdict_ok_and_criticals() -> None:
    verdict = Verdict(
        findings=[
            Finding("RV001", "critical", "P1", "缺备注", "补 note"),
            Finding("RV004", "warning", "P1", "描述长", "压关键词"),
        ]
    )
    assert not verdict.ok
    assert len(verdict.criticals) == 1
    assert "RV001" in verdict.format()
