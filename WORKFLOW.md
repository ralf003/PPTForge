# WORKFLOW.md — PPTForge 工作规范

本文规定从交付一份稿件、提交一次代码改动到失败升级的固定流程。命令均在仓库根目录执行，解释器写作 `python3`——须使用已安装本仓库 `pip install -e '.[dev]'` 的那一个。同时在多个 clone 之间验证时，务必显式带 `PYTHONPATH=$PWD/src` 或为该 clone 单独建 venv，否则可能导入到另一个 clone 的 editable 安装、跑出假绿（AGENTS.md 3.1 验证方法教训）。

## 1. 一次从零到交付

顺序沿用 AGENTS.md 第 3 节链路：环境自检 → 静态检查 → 类型检查 → 测试 → 生成 PPTX → 渲染逐页 PNG → 视觉门 + 人工回看。以下输出为本仓库当前交付态实跑记录（2026-11-20，Python 3.12.11）。

### 1.1 环境自检

```bash
python3 -m pptforge.cli doctor
```

实测输出：

```
PPTForge v0.1.0 doctor
[OK ] Python: 3.12.11（需要 >=3.11）
[OK ] python-pptx: 1.0.2
[OK ] PyYAML: 6.0.3
[OK ] LibreOffice/soffice: /usr/bin/soffice
[WARN] 字体 Microsoft YaHei: 本地未安装，PPTX 内已写字体名，Windows 端正常显示，本地渲染回退
结果：环境就绪
```

字体 WARN 是预期内项：本机未装微软雅黑，PPTX 内已写字体名，Windows 端正常显示；不阻断本地链路。

### 1.2 静态检查与类型检查

```bash
python3 -m ruff check src tests
python3 -m mypy src
```

实测输出：

```
All checks passed!
Success: no issues found in 23 source files
```

### 1.3 测试

```bash
python3 -m pytest
```

实测输出：

```
74 passed, 11 warnings in 1.21s
```

11 条 warning 为 Pillow `Image.getdata` 的 DeprecationWarning（`gates/visual.py`），不影响结论。

### 1.4 生成 PPTX

```bash
python3 -m pptforge.cli build examples/sample_spec.yaml -o /tmp/wf-check.pptx
```

实测输出：

```
已生成 6 页：/tmp/wf-check.pptx
```

### 1.5 渲染逐页 PNG

```bash
rm -f /tmp/wf-check.pdf /tmp/wf-slide-*.png
soffice --headless --convert-to pdf --outdir /tmp /tmp/wf-check.pptx
pdftoppm -png -r 110 /tmp/wf-check.pdf /tmp/wf-slide
```

实测：PDF 转换一行 `error : Unknown IO error` 为 soffice  stderr 噪音，PDF 正常产出；`/tmp/wf-slide-1.png` 至 `/tmp/wf-slide-6.png` 共 6 张。

### 1.6 视觉门

页序 roles 从 spec 读取，再按页型分档：

```bash
ROLES=$(python3 -c \
  'from pptforge.models import Deck; print(",".join(p.role for p in Deck.load("examples/sample_spec.yaml").pages))')
python3 -m pptforge.cli check-visual /tmp/wf-slide-*.png --roles "${ROLES}"
```

实测输出：

```
页序 roles: cover,section,content,section,content,summary
P1 墨迹 7.3% / 最大空白块 45.9%
P2 墨迹 3.3% / 最大空白块 45.6%
P3 墨迹 30.2% / 最大空白块 17.7%
P4 墨迹 2.4% / 最大空白块 62.5%
P5 墨迹 29.4% / 最大空白块 18.7%
P6 墨迹 3.3% / 最大空白块 55.0%
视觉门通过：6 页
```

### 1.7 评审委员会（可选但建议交付前跑）

```bash
python3 -m pptforge.cli review examples/sample_spec.yaml
# JSON 输出：追加 --json
```

实测输出（当前样例稿）：

```
[WARNING] RV004 P5 / items[2].desc: 描述 26 字，超出 24 字图面上限（修复：压成关键词，解释进 note）
结果：评审通过
```

### 1.8 人工回看

静态门与视觉门通过不等于视觉合格：必须打开逐页 PNG 确认无溢出、无重叠、无大面积留白、无残留阴影（阴影类缺陷门禁不覆盖，见 AGENTS.md 3.1）。

### 1.9 一键脚本

以上 1.2–1.6 可由脚本串跑：

```bash
bash scripts/verify.sh                # 全量：静态检查 + 测试 + 渲染 + 视觉门
bash scripts/verify.sh --skip-visual   # 跳过 soffice / pdftoppm / check-visual 三段
```

脚本解释器优先仓库内 `.venv/bin/python`，其次 `python3` / `python`，启动时打印实际解释器；`--skip-visual` 只跳视觉三段，doctor / ruff / mypy / pytest / build 照跑。脚本内部已把 `PYTHONPATH` 置为仓库 `src/`，因此即便解释器来自 site-packages，导入的仍是本仓库源码。跳过视觉门不等于视觉合格，交付前必须在装有 soffice 的环境跑一次全量。

## 2. 一次代码改动的完整流程

### 2.1 分支与提交

- 禁止直接 push/merge `main`，一切改动走 PR（AGENTS.md 第 2 节）。
- 分支命名：`agent/<task-slug>-<timestamp>`，例如 `agent/reviewer-rv008-20261120`。
- 提交遵循 Conventional Commits：`feat / fix / docs / refactor / test / chore / perf / ci`。
- PR 小而聚焦；大改动拆 stacked PR。

### 2.2 本地验证

推送前在本地跑完整套 CI 同款命令（1.2–1.6），全部通过才允许推送；禁止只跑 pytest 就交付。新增第三方 import 时，同步把包写进 `pyproject.toml` 的 dependencies，并在干净 venv 复跑（AGENTS.md 第 3 节 run #14 教训：本地预装导致绿、CI 干净环境 ModuleNotFound）。

### 2.3 公共契约改动必须 PR 并给理由

以下文件属公共契约，改动必须在 PR 描述里说明影响面与兼容性，不允许在功能 PR 里顺手改：

- `models.py`：`Deck / Page / Item` 结构、`ROLES`、`SKELETONS` 白名单；
- `theme.py`：色板、字号、字体、画布尺寸；
- `gates/`：静态门检查项与阈值、视觉门指标与分档；
- 骨架注册表 `engine/skeletons.py` 的 `REGISTRY`。

按 AGENTS.md 3.1「新增骨架必须同时做三件事」：新增骨架时，`REGISTRY` 注册、`models.SKELETONS` 白名单、`tests/test_skeletons.py` 用例三处必须在同一个 commit 落地；分离推送会被 `test_registry_matches_model_contract` 拦下。

### 2.4 合并条件

按 AGENTS.md 1.1：kilo-code-robot 无 critical 阻断 + 专项质量门（CI `quality` job）全绿，才允许合并。自动合并只对自己的 agent 发起的 PR 生效；外部/陌生人 PR 不自动合并。分支保护当前未落地，见第 6 节。

## 3. 评审分级与打回

评审 finding 三级（`roles/reviewer.py`，`SEVERITIES = ("critical", "warning", "info")`）：

| 级别 | 定义 | 是否阻断 | 处置 |
| --- | --- | --- | --- |
| critical | 确定性规则判出的硬缺陷：备注缺失、content 无骨架、配图骨架缺图等 | 阻断：`Verdict.ok` 为假，CLI `review` exit 1，闭环进入 repair 或抛 `ReviewExhaustedError` | 打回必须带 `fix` 字段（可执行修复方向） |
| warning | 图面规范类问题：描述超长、stat 缺量化值、命中状态词、标题过长 | 不阻断交付 | 建议修复；闭环内由 `repair` 按确定性动作处理 |
| info | Deck 级提示：首页非 cover、末页非 summary | 不阻断 | 记录备查 |

补充口径：

- 接 LLM 后端时，语义 finding 不可复现，critical 一律降级为 warning，不构成硬门（`reviewer.py` `_semantic` 分支）。
- 每条 Finding 必须含 code（稳定规则码，RV001 起，不复用）、target（定位到页与字段）、message（事实）、fix（修复方向）。
- Kilo 评论为建议性质；最终硬门以 required status check 为准。
- 打回指向具体可修复项，不接受"整体优化一下"这类无定位评语。

## 4. 失败处置与升级

### 4.1 CI `quality` job 红

`quality` 是合并阻断项（三矩阵 Python 3.11 / 3.12 / 3.13），覆盖 Ruff、Mypy、Pytest、示例渲染静态门、私有泄漏扫描。处置：

1. 本地在仓库根目录带 `PYTHONPATH=$PWD/src` 复现对应命令，先区分是真实缺陷还是环境差异；
2. 静态检查、类型检查、测试是不同维度，缺一项都可能在 CI 才暴露（AGENTS.md 第 3 节教训）；
3. 若 CI 干净环境报 `ModuleNotFound`，先查 `pyproject.toml` 依赖声明是否同步；
4. 修复后本地全量复跑 1.2–1.3，再推 PR。

### 4.2 CI `render-preview` job 红

该 job 刻意 `continue-on-error: true`，apt 安装 LibreOffice 的环境抖动不阻断合并。处置：

1. 先下载 artifact（`rendered-preview`：PPTX、逐页 PNG、`/tmp/visual-report.txt`）区分环境抖动与真实视觉缺陷；
2. 环境抖动（apt 失败、soffice 起不来）：记录现象，不阻塞 quality 结论；
3. 真实视觉缺陷（空页、大片留白、溢出重叠）：回到 quality 链路修复 spec / 骨架 / 内容，本地全量 `verify.sh` 复跑后再推。

### 4.3 视觉门红

`check-visual` exit 1 时，issue 带页号与空白块网格坐标（`empty_box`）。处置：

1. 先核对页型分档：cover / section / summary 阈值已放宽，深底满版页豁免留白判定；用错页型标签会造成假红；
2. 空页（墨迹低于下限）：查配图是否加载、文字层是否丢失；
3. 大片留白：按内容量调整条目与结论带，**不得**为消红给指标加撑满底板——实测会变成三块空卡片（AGENTS.md 3.1 空卡片教训，DESIGN.md 第 8 节）；
4. 视觉门只判空旷度，内容对错与审美问题不在此层处理。

### 4.4 闭环耗尽升级人工

`Pipeline.build_page()` 在 `max_iter`（默认 3，含首轮）后仍有 critical，抛 `ReviewExhaustedError`，异常内带最后一次 `Verdict` 与轮数。处置：取出 `verdict.findings` 逐条人工判断；RV003（缺图）类不可自动修复项，补配图或换不依赖图的骨架，不要求 `repair` 凭空生成。

## 5. 沉淀机制

- **教训**：CI 失败实证、踩坑与边界条件写进 `AGENTS.md` 第 3 节（通用验证教训）、3.1（骨架库铁律）与 3.2（视觉门铁律）。没有对应子节的新教训先归第 3 节条目，确有独立主题再申请新增子节（`AGENTS.md` 的变更需人工确认方向）。
- **规则码表**：新增评审规则分配 RV 起的稳定码，码、级别、判据、修复方向登记进 `REVIEW.md` 的"仓库内硬门规则码表"；规则码永不复用。
- **骨架资产**：新增骨架按 AGENTS.md 3.1 三处同提交落地，并补"生成一页并通过门禁"的用例。

## 6. 当前阶段的例外与未落地事项

1. **分支保护未配置**：`main` 的保护规则尚未在 GitHub 网页落地；脚本 `ops/branch-protection.sh` 已就绪，需 admin 凭据（`gh auth login` 或 `GITHUB_TOKEN`）执行一次，执行后用 `gh api repos/ralf003/PPTForge/branches/main/protection` 回读验证。脚本设定：required check 只设 `quality`，`render-preview` 非阻断，`required_approving_review_count = 0`，禁止 force push 与删分支。
2. **Kilo 白名单需人工确认**：Kilo 默认忽略 bot 生成的 PR；本项目实现工作主要由 agent 完成，须在 Kilo 配置里把自己的实现 agent 账户加入评审白名单，否则评审静默失效。该配置在仓库外，需人工核对。
3. **render-preview 刻意非阻断**：job 级 `continue-on-error: true` 保留，apt 抖动不阻断合并；这不等于视觉可以放行，交付前本地必须全量跑 `verify.sh`。
4. **真实 LLM 未接入验证**：`OpenAICompatibleBackend` 代码已就位，但未接真实端点跑通过 Director / Researcher / Reviewer 语义路径；当前测试全部走 `ReplayBackend` 回放。
5. **闭环到单页**：`build_page()` 交付单页 `Delivery`，Deck 级多页编排未实现（见 DESIGN.md 7.2）；多页稿当前走手写 spec + CLI `build`。
