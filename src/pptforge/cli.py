"""命令行入口：doctor 环境自检、build 渲染、validate 校验。"""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import sys
from pathlib import Path

from pptforge import __version__
from pptforge.engine.renderer import Renderer
from pptforge.models import Deck
from pptforge.theme import FONT_FAMILY


def _check(name: str, ok: bool, detail: str, critical: bool = True) -> tuple[bool, str]:
    mark = "OK " if ok else ("!! " if critical else "WARN")
    return bool(critical and not ok), f"[{mark}] {name}: {detail}"


def cmd_doctor() -> int:
    rows: list[tuple[bool, str]] = []

    rows.append(
        _check(
            "Python",
            sys.version_info >= (3, 11),
            f"{sys.version.split()[0]}（需要 >=3.11）",
        )
    )

    for pkg in ("python-pptx", "PyYAML"):
        try:
            rows.append(_check(pkg, True, importlib.metadata.version(pkg)))
        except importlib.metadata.PackageNotFoundError:
            rows.append(_check(pkg, False, "未安装"))

    soffice = shutil.which("soffice")
    rows.append(
        _check(
            "LibreOffice/soffice",
            soffice is not None,
            soffice or "未找到（渲染回看需要，可选）",
            critical=False,
        )
    )

    # 字体：检查本地是否有微软雅黑；无则说明 Windows 端正常、本地回退（预期内，仅警告）
    fc_match = shutil.which("fc-match")
    font_local = False
    if fc_match:
        import subprocess

        out = subprocess.run(
            ["fc-match", FONT_FAMILY], capture_output=True, text=True
        ).stdout
        font_local = FONT_FAMILY.replace(" ", "") in out.replace(" ", "") or "msyh" in out
    rows.append(
        _check(
            f"字体 {FONT_FAMILY}",
            font_local,
            "本地可用"
            if font_local
            else "本地未安装，PPTX 内已写字体名，Windows 端正常显示，本地渲染回退",
            critical=False,
        )
    )

    has_failure = any(row[0] for row in rows)
    print(f"PPTForge v{__version__} doctor")
    for _failed, line in rows:
        print(line)
    print("结果：" + ("环境就绪" if not has_failure else "存在关键缺失项，请按提示处理"))
    return 1 if has_failure else 0


def cmd_build(spec: Path, output: Path) -> int:
    deck = Deck.load(spec)
    problems = deck.validate()
    if problems:
        print("Spec 校验失败：")
        for p in problems:
            print(" - " + p)
        return 2
    out = Renderer().save(deck, output)
    print(f"已生成 {len(deck.pages)} 页：{out.resolve()}")
    return 0


def cmd_validate(spec: Path) -> int:
    deck = Deck.load(spec)
    problems = deck.validate()
    if problems:
        print("发现问题：")
        for p in problems:
            print(" - " + p)
        return 2
    print(f"Spec 合法：{len(deck.pages)} 页")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pptforge", description="声明式工程化 PPT 工具链")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="环境自检")

    p_build = sub.add_parser("build", help="从 spec 渲染 PPTX")
    p_build.add_argument("spec", type=Path, help="YAML spec 文件")
    p_build.add_argument("-o", "--output", type=Path, required=True, help="输出 PPTX 路径")

    p_val = sub.add_parser("validate", help="仅校验 spec")
    p_val.add_argument("spec", type=Path, help="YAML spec 文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "build":
        return cmd_build(args.spec, args.output)
    if args.command == "validate":
        return cmd_validate(args.spec)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
