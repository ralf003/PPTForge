"""命令行入口：doctor 环境自检、build 渲染、validate 校验。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from pptforge import __version__
from pptforge.engine.renderer import Renderer
from pptforge.models import Deck
from pptforge.roles.reviewer import Reviewer
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


def cmd_review(spec: Path, as_json: bool) -> int:
    """跑评审委员会；有 critical 时 exit 1。"""
    deck = Deck.load(spec)
    verdict = Reviewer().review(deck)
    if as_json:
        payload = {
            "ok": verdict.ok,
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "target": f.target,
                    "message": f.message,
                    "fix": f.fix,
                }
                for f in verdict.findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(verdict.format())
        if verdict.ok:
            print("结果：评审通过")
        else:
            print(f"结果：{len(verdict.criticals)} 条 critical，未通过")
    return 0 if verdict.ok else 1


def cmd_check_visual(
    pngs: Sequence[Path],
    min_ink: float | None,
    max_empty: float | None,
    roles: Sequence[str] | None = None,
) -> int:
    """对渲染后的逐页 PNG 跑视觉门：空页与大片留白。"""
    from pptforge.gates.visual import run_visual_gates

    missing = [p for p in pngs if not p.exists()]
    if missing:
        print("找不到渲染图：")
        for p in missing:
            print(" - " + str(p))
        return 2

    # 不显式给阈值时按页型分档：封面与分隔页的留白是设计，内容页的留白是缺陷
    report = run_visual_gates(pngs, roles=roles, min_ink=min_ink, max_empty=max_empty)
    for page in report.pages:
        print(
            f"P{page.page} 墨迹 {page.ink_ratio:.1%} / 最大空白块 {page.max_empty_ratio:.1%}"
        )
    if report.ok:
        print(f"视觉门通过：{len(report.pages)} 页")
        return 0
    print("视觉门未通过：")
    for issue in report.issues:
        print(" - " + issue)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pptforge", description="声明式工程化 PPT 工具链")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="环境自检")

    p_build = sub.add_parser("build", help="从 spec 渲染 PPTX")
    p_build.add_argument("spec", type=Path, help="YAML spec 文件")
    p_build.add_argument("-o", "--output", type=Path, required=True, help="输出 PPTX 路径")

    p_val = sub.add_parser("validate", help="仅校验 spec")
    p_val.add_argument("spec", type=Path, help="YAML spec 文件")

    p_rev = sub.add_parser("review", help="跑评审委员会，逐条打印 findings")
    p_rev.add_argument("spec", type=Path, help="YAML spec 文件")
    p_rev.add_argument("--json", action="store_true", help="以 JSON 输出 findings")

    p_vis = sub.add_parser(
        "check-visual", help="对渲染后的逐页 PNG 跑视觉门（空页与大片留白）"
    )
    p_vis.add_argument("pngs", type=Path, nargs="+", help="逐页渲染图（按页序）")
    p_vis.add_argument("--min-ink", type=float, default=None, help="非背景像素占比下限")
    p_vis.add_argument("--max-empty", type=float, default=None, help="单一空白块面积上限")
    p_vis.add_argument(
        "--roles",
        default=None,
        help="按页序给页型，逗号分隔（cover,section,content,summary），用于分档阈值",
    )
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
    if args.command == "review":
        return cmd_review(args.spec, args.json)
    if args.command == "check-visual":
        roles = args.roles.split(",") if args.roles else None
        return cmd_check_visual(args.pngs, args.min_ink, args.max_empty, roles)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
