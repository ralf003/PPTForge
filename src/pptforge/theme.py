"""设计系统：色板、投影级字号、字体与画布尺寸。

所有视觉决策统一从这里取，禁止在渲染代码里散落硬编码。
字体默认微软雅黑（Microsoft YaHei），latin 与 eastAsia 同名。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 画布：16:9，单位英寸
SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5

# 默认字体：微软雅黑（在 PPTX 内仅为字体名字符串，Windows 端正确显示）
FONT_FAMILY = "Microsoft YaHei"


@dataclass(frozen=True)
class Palette:
    """色板（RGB 十六进制字符串，不带 #）。"""

    dark: str = "0B1F3A"
    panel: str = "132C4F"
    blue: str = "1F6FEB"
    cyan: str = "22D3EE"
    bg: str = "F4F6FA"
    ink: str = "1F2937"
    mute: str = "4B5563"
    red: str = "DC2626"
    white: str = "FFFFFF"
    # 强调与分层底色（骨架用）
    amber: str = "F59E0B"
    tint: str = "E8EEF9"
    tint_alt: str = "D6E4F7"


@dataclass(frozen=True)
class FontScale:
    """投影级字号（pt）。整体偏大，保证会场后排可读。"""

    cover_title: int = 54
    cover_sub: int = 24
    page_title: int = 34
    section_label: int = 16
    item_name: int = 22
    body: int = 18
    caption: int = 14
    footnote: int = 13


@dataclass(frozen=True)
class Theme:
    """完整设计系统。"""

    font_family: str = FONT_FAMILY
    palette: Palette = field(default_factory=Palette)
    scale: FontScale = field(default_factory=FontScale)
    slide_width_in: float = SLIDE_WIDTH_IN
    slide_height_in: float = SLIDE_HEIGHT_IN


DEFAULT_THEME = Theme()
