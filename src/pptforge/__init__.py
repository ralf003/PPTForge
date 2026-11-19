"""PPTForge：声明式工程化 PPT 生产工具链。

产出本地可编辑 PPTX，覆盖「从零生成」与「现有 PPT 优化」两个场景。
"""

__version__ = "0.1.0"

from pptforge.models import Deck, Page
from pptforge.theme import Theme

__all__ = ["Deck", "Page", "Theme", "__version__"]
