#!/usr/bin/env bash
# 本地一键全套验收：跑与 CI 同款的完整链路（quality job + render-preview job）。
#
# 用法：
#   bash scripts/verify.sh               全量：静态检查 + 测试 + 渲染 + 视觉门
#   bash scripts/verify.sh --skip-visual 跳过 soffice / pdftoppm / check-visual 三段
#                                        （无 LibreOffice 环境做静态链路自检）
#
# 任一步失败立即非零退出，并指明失败步骤；末尾打印通过/失败与总耗时。
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

SKIP_VISUAL=0
for arg in "$@"; do
  case "$arg" in
    --skip-visual) SKIP_VISUAL=1 ;;
    *) echo "未知参数：$arg（仅支持 --skip-visual）" >&2; exit 2 ;;
  esac
done

# 解释器选择：仓库内 .venv 优先，其次 python3，再次 python；明确打印用的是哪一个。
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "错误：未找到 python3 / python" >&2; exit 1
fi
# 保证本仓库源码优先于 site-packages（避免导入到别的 clone 的 editable 安装）。
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
echo "解释器：${PYTHON}（$("${PYTHON}" --version 2>&1)）"

# CLI 入口：优先 venv 内可执行文件，避免命中 PATH 上别的同名命令。
if [[ -x "${ROOT}/.venv/bin/pptforge" ]]; then
  PPTFORGE="${ROOT}/.venv/bin/pptforge"
else
  PPTFORGE="$(command -v pptforge)"
fi
echo "CLI：${PPTFORGE}"

SPEC="examples/sample_spec.yaml"
PPTX="/tmp/verify.pptx"
PDF="/tmp/verify.pdf"
SLIDE_PREFIX="/tmp/verify-slide"
SLIDE_GLOB="${SLIDE_PREFIX}-*.png"
E2E_PPTX="/tmp/verify_e2e.pptx"
E2E_PDF="/tmp/verify_e2e.pdf"
E2E_SLIDE_PREFIX="/tmp/verify_e2e-slide"
E2E_SLIDE_GLOB="${E2E_SLIDE_PREFIX}-*.png"

STEP="（未开始）"
trap 'code=$?; echo ""; echo "✗ 验收失败：步骤 [${STEP}] 退出码 ${code}"; exit 1' ERR

START_TS="$(date +%s)"

run_step() {
  STEP="$1"
  shift
  echo ""
  echo "==== [${STEP}] ===="
  "$@"
}

# ---- 对应 quality job：环境自检 / 静态检查 / 类型检查 / 测试 ----
run_step "doctor 环境自检" "${PPTFORGE}" doctor
run_step "ruff 静态检查" "${PYTHON}" -m ruff check src tests
run_step "mypy 类型检查" "${PYTHON}" -m mypy src
run_step "pytest 测试" "${PYTHON}" -m pytest

# ---- 对应 render-preview job：build → soffice → pdftoppm → check-visual ----
run_step "build 生成 PPTX" "${PPTFORGE}" build "${SPEC}" -o "${PPTX}"

if [[ "${SKIP_VISUAL}" -eq 1 ]]; then
  echo ""
  echo "==== [跳过视觉门] --skip-visual：未执行 soffice / pdftoppm / check-visual ===="
else
  # 清理上次残留的 PDF 与 PNG，避免 glob 串入旧页（PPTX 已由 build 覆盖生成）。
  rm -f "${PDF}" ${SLIDE_GLOB}
  run_step "soffice 转 PDF" soffice --headless --convert-to pdf --outdir /tmp "${PPTX}"
  run_step "pdftoppm 逐页出图" pdftoppm -png -r 110 "${PDF}" "${SLIDE_PREFIX}"
  ROLES="$("${PYTHON}" -c \
    'from pptforge.models import Deck; print(",".join(p.role for p in Deck.load("examples/sample_spec.yaml").pages))')"
  echo "页序 roles：${ROLES}"
  run_step "check-visual 视觉门" "${PPTFORGE}" check-visual ${SLIDE_GLOB} --roles "${ROLES}"

  # ---- Engine 接入 Pipeline 闭环：ReplayBackend 出单页 → 渲染 → 视觉门 ----
  run_step "e2e 闭环出片" "${PYTHON}" scripts/e2e_pipeline.py "${E2E_PPTX}"
  rm -f "${E2E_PDF}" ${E2E_SLIDE_GLOB}
  run_step "e2e soffice 转 PDF" soffice --headless --convert-to pdf --outdir /tmp "${E2E_PPTX}"
  run_step "e2e pdftoppm 出图" pdftoppm -png -r 110 "${E2E_PDF}" "${E2E_SLIDE_PREFIX}"
  run_step "e2e check-visual 视觉门" "${PPTFORGE}" check-visual ${E2E_SLIDE_GLOB} --roles content
fi

END_TS="$(date +%s)"
ELAPSED=$((END_TS - START_TS))
echo ""
echo "==== 验收通过，总耗时 ${ELAPSED}s ===="
