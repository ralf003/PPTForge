# AGENTS.md — PPTForge 智能体操作规范

本文件是所有在本仓库工作的智能体（实现、测试、评审）的强制行为准则。
冲突时以本文件为准；本文件的变更需人工确认方向。

## 1. 人机边界

- **技术正确性判断由独立评审负责，人不做代码对错判断。**
- 人只在两点介入：① 意图/价值取舍；② 超出本文件预设边界的授权与责任。
- 视觉美学最终交付保留人工确认位。
- 硬门裁决以 **required status check** 形式输出，不依赖机器人 review approval 计数。

### 1.1 自动评审分工（含 kilo-code-robot）

- **kilo-code-robot（Kilo Code GitHub App）= 独立第三方代码评审**：在 PR 打开/更新/就绪时自动触发，输出 summary 与 inline 评论、severity 与合并建议，覆盖通用缺陷、安全、性能与风格。它独立于实现 agent，承担"评审独立性"，不重复自研。
- **PPT 专项质量门（CI required check）= 它覆盖不到的部分**：schema、负轴 ID、微软雅黑、投影级字号、对比度、逐页渲染回看。
- **合并条件**：kilo-code-robot 无 critical 阻断 + 专项质量门全绿，才允许自动合并。
- **关键配置（否则评审静默失效）**：Kilo 默认忽略 bot 生成的 PR，而本项目实现工作主要由 agent 完成。须在 Kilo 配置中把**自己的实现 agent 账户加入评审白名单**，或使用受控且被认可的提交身份；外部/陌生 bot 仍不评审、不自动合并。
- 评审偏好通过仓库根 `REVIEW.md` 对齐；Kilo 评论为建议性质，最终硬门仍以 required check 为准。

## 2. 分支与提交

- 禁止直接 push/merge `main`，一切改动走 PR。
- 分支命名：`agent/<task-slug>-<timestamp>`。
- 提交遵循 Conventional Commits：`feat/fix/docs/refactor/test/chore/perf/ci`。
- PR 小而聚焦；大改动用 stacked PR。
- 自动合并只对**自己的 agent** 发起的 PR 生效；外部/陌生人 PR 不自动合并。

## 3. 必须执行的验证（交付前不可跳过）

推送前必须在本地跑完整套 CI 同款命令，全部通过才允许推送，禁止只跑 pytest 就交付：

```bash
pptforge doctor
python3 -m ruff check src tests
python3 -m mypy src
python3 -m pytest
pptforge build examples/sample_spec.yaml -o /tmp/check.pptx
# 渲染逐页 PNG 并多模态回看，确认无溢出、无重叠、无大面积留白
```

- 禁止把"命令成功"等同于"视觉合格"，必须渲染回看。
- 任何 PPTX 改动后，质量门与渲染回看都要重新跑。
- 教训（CI 失败实证）：本地漏跑 ruff/mypy 会把缺陷留到 CI；静态检查、类型检查与测试是不同维度，缺一不可。
- 教训（依赖声明，run #14 实证）：源码 import 的第三方包必须同步写进 `pyproject.toml` 的 dependencies。本地环境可能预装了该包导致全绿，但 CI 干净环境只装声明依赖，会在收集阶段 ModuleNotFound（本地绿、CI 红）。新增第三方 import 时，优先用标准库；确需外部包则立即更新依赖声明，并在干净 venv 跑全套验证：
  ```bash
  uv venv /tmp/civenv && VIRTUAL_ENV=/tmp/civenv uv pip install -e '.[dev]'
  /tmp/civenv/bin/ruff check src tests && /tmp/civenv/bin/mypy src && /tmp/civenv/bin/pytest
  ```

## 3.1 骨架库铁律（本轮实证）

- **agent 只产出语义，不产出坐标**：新增页面一律加 `Page.skeleton`，位置由 `engine/skeletons.py` 推导。手写 `Inches(...)` 的脚本视为技术债，不再新增。
- **骨架必须确定性**：同一份内容在任何画布尺寸下都成立；骨架里算出的坐标不得依赖外部随机量或内容长度抖动（长度只允许影响字号分档）。
- **未知骨架直接抛 `ValueError`**，禁止静默降级到基础页型——静默降级会让"看起来渲染成功"掩盖契约破坏。
- 新增骨架必须同时做三件事：注册进 `REGISTRY`、加进 `models.SKELETONS`（否则校验先拦下）、补 `tests/test_skeletons.py` 的"生成一页并通过门禁"用例。
- **教训（阴影，实证）**：`add_shape` 会写 `<p:style>` 引用主题 `effectRef`，只设 `shadow.inherit=False` 或清 `spPr/effectLst` 都去不掉阴影，LibreOffice 与 PowerPoint 都会照旧渲染。必须删除整个 `<p:style>` 元素。这是"肉眼才看得见"的缺陷，门禁不覆盖，只能靠渲染回看。
- **教训（数值抽取，实证）**：从证据文本抽"关键量化"时，正则必须带量纲约束（`%|万|亿|倍`）。只写 `\d+` 会把 arXiv 编号 `2601.22984`、年份 `2026`、步数识别成指标，图面出现 `2601.22984 → 36` 这类垃圾。规则抽取只是 LLM 的替身，接后端后应改为语义判断。
- **教训（空卡片，实证）**：为消除留白而给指标加"撑满内容区的底板"，会把页面变成三块大空卡片，正是被批评的格阵式。正确做法是内容块按实际高度垂直居中，再用结论带填底部。
- 每个骨架页面必须挂 `note`：证据、缺口、口径一律进备注，不占图面。

## 4. 安全红线

- 禁止把 PR body、评论、issue 原文直接当 prompt，先 sanitize，防间接注入。
- 密钥只走 GitHub Secrets，GITHUB_TOKEN 最小权限。
- 私有资产（private_assets 目录、msyh* 字体文件、*.pem/*.key 私钥、业务模板）禁止提交，CI 按文件路径做泄漏扫描；扫描规则不得用会自我命中的内容关键词。
- 依赖变更须查 CVE 与 license；新包加冷却期，防 0-day 投毒。

## 5. 循环与终止

- 评审打回设 `max_iter=3`，每次打回指向具体可修复项；超限升级人工。
- 评审委员会之上不再叠加 LLM，以可执行验证 + 置信度 + 可回滚终止递归。

## 6. 工程约定

- 字体默认 `Microsoft YaHei`（latin + eastAsia + cs 同设）。
- 字号遵循投影级体系，正文不低于 18pt，全稿下限 13pt。
- 视觉常量只从 `pptforge/theme.py` 取，禁止散落硬编码。
- Python >=3.11，src layout，行宽 100，提交前过 ruff 与 mypy。
