# DESIGN.md — PPTForge 架构设计与实现现状

## 1. 这份文档回答什么

本文回答"PPTForge 当前代码实际做成了什么、哪些还没做、每个判断由哪段代码兜底"，不是功能说明书；所有结论对应到具体类名、函数名、常量或实测输出，未实现项逐条标注。

## 2. 三个本质判断

### 2.1 坐标不能由 agent 产出

坐标是渲染器与画布尺寸之间的私有契约。当前实现里，角色层只产出语义字段：`designer.design()` 返回 `Page`（标题、条目、骨架、结论句、备注），不含任何位置参数；全部几何由 `engine/skeletons.py` 在骨架内推导，渲染层 `Renderer` 只负责把几何落成 OOXML。

如果让 agent 直接写 `Inches(...)` 坐标：同一页换画布尺寸（16:9 与 4:3、不同投影分辨率）后位置必然错；坐标散落在提示词产出里，长度、换行差异都会让版面崩，且错误无法靠规则收敛——每改一次内容就要重调一次坐标。AGENTS.md 3.1 已把"手写 `Inches(...)` 的脚本视为技术债，不再新增"列为铁律。

### 2.2 版式必须沉淀成可测试资产，而不是每次重新生成

版式沉淀在 `REGISTRY`（`engine/skeletons.py`），五个骨架 `track / stat / topology / hero / split` 对应确定性函数 `_track / _stat / _topology / _hero / _split`，并与 `models.SKELETONS` 白名单一一相等（CI 有 `test_registry_matches_model_contract` 断言）。Designer 只做"选骨架 + 填内容"：`pick_skeleton()` 按主题词返回 `topology / stat / track`。

如果版式每次由模型当场生成：同一类内容两次产出的位置关系不可比，测试无法断言"这一页排得对"；版式缺陷只能靠人眼逐张看，回归一次就要重看全稿。骨架作为资产后，版式正确性由骨架测试（`tests/test_skeletons.py`、`tests/test_picture_skeletons.py`）固定下来，新增内容只验证语义是否填对。

### 2.3 验收必须分层

现状门禁分三层，各层判的维度互不重叠：结构正确性（静态门吃 PPTX）、观感空旷度（视觉门吃渲染后 PNG）、审美与意图（人工确认位）。

如果不分层：用结构检查去判留白，框都在但页面是空的，检不出来；用像素指标去判内容对错，指标再漂亮也可能是错话；让一个 LLM 打分同时覆盖三层，判决不可复现、无法归因，CI 无法执行。三层之间也不能互相替代——静态门看不出"视觉上是不是空"（`gates/visual.py` 模块docstring 明确写了这一点），视觉门不判语义与审美。

## 3. 分层与数据流

```
spec.yaml
   │  Deck.load（models.Deck.load / Deck.validate / Page.validate）
   ▼
Deck / Page / Item（结构化声明，无语义以外的自由文本）
   │
   ▼ 角色层（产物落 dataclass，过各自 validate 后才交下游）
Director.brief_page ──▶ PageBrief ──gate(Gate)──▶ Researcher.research
                                                  ──▶ ResearchBrief(含 ClaimCard[])
                                                          │
                                                          ▼
                                              Designer: design / repair
                                                          │
                                                          ▼
                                                       Page
                                                          │
                              Reviewer.review_page ──▶ Verdict(Finding[])
                                                          │
   ┌────────────────────────────────────────────────────┘
   │ critical 未过：repair 确定性修复后重评（max_iter 轮）；耗尽抛 ReviewExhaustedError
   ▼
骨架层：REGISTRY 按 Page.skeleton 分发，几何由骨架函数推导（engine/skeletons.py）
   ▼
渲染层：Renderer.render / Renderer.save → 原生可编辑 PPTX（OOXML），保存前 fix_chart_axis_ids
   ▼
门禁层（产物侧）：
  静态门 run_gates（吃 PPTX 结构）
  视觉门 run_visual_gates（吃逐页 PNG）
  人工视觉确认位（审美与意图，AGENTS.md 第 1 节保留）
```

两点现状约束（详见第 7 节）：

- `Pipeline.build_page()` 闭环在 `Page` 处结束，本身不经过骨架层与渲染层；`Pipeline.build_pptx()` 在其后经 `engine/bridge.py` 接骨架层与渲染层出单页 PPTX 并过静态门。CLI `build` 路径仍独立走 YAML spec。
- 角色层一次只处理一页，没有 Deck 级多页编排。

## 4. 角色职责与交接契约

| 角色 | 形态 | 产出 dataclass | 校验入口 | 边界 |
| --- | --- | --- | --- | --- |
| Director | 类 `Director`（`roles/director.py`） | `PageBrief`（topic / claim / page_role / audience / principles） | `PageBrief.validate()`：topic、claim 非空，page_role ∈ `ROLES` | 只定本页唯一主张与页型，不收集证据；产物校验失败抛 `ValueError` |
| Researcher | 类 `Researcher`（`roles/researcher.py`） | `ResearchBrief`（brief + `ClaimCard[]`）；`ClaimCard` 含 claim / support / evidence / gap | `ResearchBrief.validate()` → 逐卡 `ClaimCard.validate()`：claim、support 非空，evidence 至少一条 | 证据不足写进 `gap`，禁止编造；当前后端不具备联网能力，接地需调用方提供后端 |
| Designer | **模块级函数集合**（`roles/designer.py`）：`design` / `repair` / `pick_skeleton`，无独立角色类 | `Page` | `design()` 先跑 `ResearchBrief.validate()`；`repair()` 修复后跑 `Page.validate()` | 只产语义与骨架选择，不产坐标；确定性规则是 LLM 不可用时的替身 |
| Reviewer | 类 `Reviewer`（`roles/reviewer.py`） | `Verdict`（`Finding[]`：code / severity / target / message / fix） | `Verdict.ok`：无 critical 即放行；warning / info 不阻断 | `backend=None` 纯确定性零网络；接后端时语义 findings 最高 warning，不构成硬门 |
| Engine（渲染引擎） | 类 `Renderer`（`engine/renderer.py`）+ 骨架函数（`engine/skeletons.py`）+ 桥接 `engine/bridge.py` | PPTX 文件 | `Renderer.render()` 先跑 `Deck.validate()`；`bridge.render_verified` 重开产物跑 `run_gates` | 经 `bridge` 被 `Pipeline.build_pptx` 接入单页闭环（静态门不通过抛 `EngineQualityError`）；CLI `cmd_build` 仍直调 `Renderer().save(deck, output)` |

交接纪律（`roles/pipeline.py` 模块docstring）：角色之间只传递经过校验的结构化产物，禁止把原始外部文本直接拼进下游 prompt。

`Pipeline` 的三条入口：

- `Pipeline.run()`：保持旧语义，只串 Director → gate → Researcher，返回 `ResearchBrief`，不进 Designer 与 Reviewer。
- `Pipeline.build_page()`：完整单页闭环 Director → gate → Researcher → Designer → Reviewer；不合格走 `repair` 重评，返回 `Delivery(page, verdict, iterations)`。
- `Pipeline.build_pptx()`：在 `build_page` 之上接 Engine——`bridge.render_with_report` 包 `Deck` 渲染、重开产物跑静态门，返回 `PptxDelivery(pptx, delivery, gate_report)`；静态门不通过抛 `EngineQualityError`。`build_page` / `run` 的签名、返回值与异常行为不变。

LLM 后端通过 `LLMBackend` Protocol 解耦：`ReplayBackend` 用于离线测试与演示；`OpenAICompatibleBackend` 接任意 OpenAI 兼容端点，凭据走环境变量；`extract_json()` 兼容 markdown 代码块与前后缀文字。

## 5. 门禁三层与各自判不了什么

### 5.1 静态门（结构正确）

入口 `run_gates(prs)`，返回 `GateReport(issues)`，`ok` 为无 issue。覆盖的检查项：

| 检查 | 函数 | 关键常量 |
| --- | --- | --- |
| 字体名与字号下限 | `_check_fonts` | `MIN_RUN_SIZE = 13`；字体须为 `FONT_FAMILY`（Microsoft YaHei） |
| 元素越界 | `_check_bounds` | `_TOL_EMU`（贴边允许，实质越界拦截） |
| WCAG 对比度 | `_check_contrast` | `CONTRAST_BODY = 4.5`、`CONTRAST_LARGE = 3.0`、`LARGE_TEXT_PT = 18`、`BOLD_LARGE_TEXT_PT = 14` |
| 文本容量溢出 | `_check_text_overflow` | `OVERFLOW_TOL_IN = 0.10` |
| 文本框区域重叠 | `_check_text_overlap` | `OVERLAP_MIN_AREA = 0.15` 平方英寸 |
| OOXML 轴 ID 修复 | `fix_chart_axis_ids`（`engine/ooxml_fix.py`） | 渲染保存前执行，不是 `checks.py` 内的 issue 检查 |

静态门判不了：

- 页面视觉上是否空旷、是否大片留白（结构上框都在，不等于不空）；
- 配色是否协调、审美是否合格；
- 中文文本宽度是按全角 1.0 / 半角 0.55 em 估算（`_char_em`），不是真实排版度量，临界字数可能误判或漏判；
- 肉眼才看得见的渲染缺陷（如残留阴影，见 AGENTS.md 3.1 阴影教训），只能靠渲染回看。

### 5.2 视觉门（观感空旷）

入口 `run_visual_gates(pngs, roles=...)`，返回 `VisualReport`；单页分析 `analyze()`，按页型取阈值 `limits_for()`。两项指标：

- 墨迹覆盖率 `ink_ratio`：非背景像素占比，网格 `GRID_W = 160` × `GRID_H = 90`，与背景色差阈值 `INK_DIFF = 24.0`；
- 最大空白块 `max_empty_ratio`：单一背景色连续矩形占画布面积，立柱直方图 + 单调栈计算。

分页型阈值 `ROLE_LIMITS`：

| 页型 | 墨迹下限 | 空白块上限 |
| --- | --- | --- |
| cover | 0.02 | 0.72 |
| section | 0.02 | 0.70 |
| summary | 0.02 | 0.60 |
| content | `MIN_INK_RATIO = 0.15` | `MAX_EMPTY_BLOCK = 0.28` |

深底满版页豁免：背景亮度 `DARK_LUMA_MAX = 90.0` 且背景占比超 `DARK_SHARE_MIN = 0.45` 时，只判"是否有字"，不判留白。

视觉门判不了：

- 内容对错、论点质量、语义是否成立；
- 审美偏好、配色与层级设计的好坏；
- 网格粒度以下的细粒度排版问题（局部字间距、小字压盖可能漏检）；
- 图片本身内容是否正确、图表数据是否准确——它只统计像素分布。

### 5.3 人工视觉确认位

AGENTS.md 第 1 节明确：视觉美学最终交付保留人工确认位；人只介入意图/价值取舍与超出预设边界的授权。CI 的 `render-preview` job 把逐页 PNG 与 `/tmp/visual-report.txt` 作为 artifact 上传，供人工回看；该 job `continue-on-error: true`，不阻断合并。

人工位不重复判结构与像素指标；结构与空旷度已由前两层给出机器可复现的结论。

## 6. 打回闭环的真实行为

### 6.1 闭环参数与终止条件

`Pipeline.__init__(backend, reviewer=None, max_iter=3)`：`max_iter` 含首轮。`build_page()` 流程：首轮 `design()` 出页 → `Reviewer.review_page()` 判决；`verdict.ok` 为假且 `iterations < max_iter` 时，调 `repair(research, page, verdict)` 后重评；耗尽仍有 critical，抛 `ReviewExhaustedError(verdict, iterations)`，异常对象带最后一次 `Verdict` 与实际轮数，供升级人工。

### 6.2 repair 的确定性动作

`repair()` 按 finding.code 分支处理，返回新 `Page`，不改入参；无对应修复分支的 code 原样保留。已实现的修复：

| 规则码 | 修复动作 |
| --- | --- |
| RV001 | 从主张卡重建备注 `_build_note(brief.cards)` |
| RV002 | 按内容形态重选骨架 `pick_skeleton(brief)` |
| RV004 | 超出 `_DESC_LIMIT = 24` 字的 desc 截断加省略号 |
| RV005 | stat 条目补不出量化值时，骨架降为 `track` |
| RV006 | 成熟度/状态词从图面字段剔除并追加进备注 `_strip_maturity` |
| RV007 | 超出 `_TITLE_LIMIT = 28` 字的标题截断加省略号 |
| RV003 | **不修复**：配图无法凭空生成，保持 finding 让循环耗尽后升级人工 |

修复后重新跑 `Page.validate()`，失败抛 `ValueError`。

### 6.3 一条必须写明的结构性事实

确定性 `design()` 的产出恒为：备注由 `_build_note(cards)` 必然生成；骨架由 `skeleton or pick_skeleton(brief)` 必然选定（`pick_skeleton` 只返回 `topology / stat / track`）；`image` 字段从不设置。因此在纯离线链路里，首轮判决**不会自然命中** RV001（备注为空）、RV002（content 无骨架）、RV003（配图骨架缺图）。

现有测试中可恢复分支是两条人工触发路径：测试子类化 `Reviewer` 在首轮注入一条 RV001（`tests/test_pipeline_loop.py` 的 `_FirstRoundMissingNote`）；或直接构造未加工的 `Page` 喂给 `repair()`。RV003 耗尽路径由 `skeleton="hero"` 直喂触发。

结论：**"端到端自动修复已验证"这一说法不成立**。闭环机制（打回、修复、重评、超限升级）有单测覆盖，但可恢复 critical 在纯离线自然链路里不会出现；接真实后端后该分支能否被真实触发、修复是否收敛，尚未验证。

### 6.4 语义评审路径现状

`Reviewer(backend)` 时额外跑一轮 `_semantic()`：后端输出 JSON findings，解析失败或非法时静默缺席，不阻断确定性判决；语义 finding 的 critical 一律降级为 warning（`reviewer.py` 中 severity == "critical" 改写为 "warning"）。该路径目前只有 `ReplayBackend` 单测覆盖（`tests/test_reviewer.py` 的 `test_semantic_findings_never_become_critical`、`test_semantic_review_silent_on_bad_backend_output`），**未接真实 LLM 验证过产出质量**。

## 7. 已实现 / 未实现清单

### 7.1 已实现

| 能力 | 代码位置 | 证据 |
| --- | --- | --- |
| 声明式模型与 YAML 加载校验 | `models.py`：`Deck` / `Page` / `Item`、`Deck.load`、`Deck.validate`、`Page.validate` | 页型白名单 `ROLES`，骨架白名单 `SKELETONS` |
| Director 角色 | `roles/director.py`：`Director.brief_page` → `PageBrief` | `PageBrief.validate()` 校验 topic / claim / page_role |
| Researcher 角色 | `roles/researcher.py`：`Researcher.research` → `ResearchBrief` | `ClaimCard.validate()` 要求 evidence 至少一条 |
| Designer 模块函数 | `roles/designer.py`：`design` / `repair` / `pick_skeleton` | 无独立角色类（见 7.2 第 3 条） |
| Reviewer 确定性评审 | `roles/reviewer.py`：`Reviewer.review_page` / `review` → `Verdict` / `Finding` | RV001–RV008；`backend=None` 零网络可复现 |
| 单页闭环编排 | `roles/pipeline.py`：`Pipeline.build_page` → `Delivery` | `max_iter=3`，耗尽抛 `ReviewExhaustedError` 并带最后 Verdict |
| Engine 接入 Pipeline 闭环 | `engine/bridge.py`：`render_verified` / `render_with_report` / `EngineQualityError`；`roles/pipeline.py`：`Pipeline.build_pptx` → `PptxDelivery(pptx, delivery, gate_report)` | `tests/test_bridge.py` 成功/失败两条离线用例；`scripts/verify.sh` e2e 段（`scripts/e2e_pipeline.py` 出单页 → soffice → pdftoppm → `check-visual`） |
| 旧语义研究入口 | `Pipeline.run` | 返回 `ResearchBrief`，不进 Designer / Reviewer |
| 骨架库五个版式 | `engine/skeletons.py`：`REGISTRY`、`render_skeleton`、`skeleton_keys` | `track / stat / topology / hero / split`，未知骨架抛 `ValueError` 不降级 |
| 确定性渲染引擎 | `engine/renderer.py`：`Renderer.render` / `save` / `_dispatch`；`engine/ooxml_fix.py: fix_chart_axis_ids` | 原生可编辑 shape；保存前修轴 ID |
| 静态质量门 | `gates/checks.py`：`run_gates` → `GateReport` | 字体字号 / 越界 / 对比度 / 溢出 / 重叠五类检查 |
| 视觉门 | `gates/visual.py`：`run_visual_gates` / `analyze` / `limits_for` | 墨迹覆盖率、最大空白块，按 `ROLE_LIMITS` 分档，深底满版豁免 |
| CLI 入口 | `cli.py`：`doctor` / `build` / `validate` / `review`（`--json`）/ `check-visual` | `review` 有 critical 时 exit 1 |
| 本地一键验收 | `scripts/verify.sh` | 与 CI 同款链路，支持 `--skip-visual` |
| CI 两条 job | `.github/workflows/ci.yml`：`quality`（三矩阵）、`render-preview` | render-preview 在 pdftoppm 后真跑 `check-visual`，报告 tee 到 `/tmp/visual-report.txt` 并随 artifact 上传；job 级 `continue-on-error: true` |
| LLM 后端抽象 | `roles/llm.py`：`LLMBackend` Protocol、`ReplayBackend`、`OpenAICompatibleBackend`、`extract_json`、`default_backend` | 凭据走环境变量 `PPTFORGE_LLM_BASE_URL / API_KEY / MODEL` |
| 设计系统常量 | `theme.py`：`Theme` / `Palette` / `FontScale` / `FONT_FAMILY` | 画布 13.333 × 7.5 in，16:9 |

### 7.2 未实现

| 未实现项 | 缺什么 | 影响 |
| --- | --- | --- |
| Deck 级多页编排 | 跨页大纲生成、页序与封面/结论衔接、Deck 级闭环均无；`Director.brief_page` 一次只定一页 | 闭环只能交付单页 `Delivery`；多页稿件目前仍需手写 YAML spec 后走 `build` |
| 真实 LLM 后端产出质量验证 | 缺 `OpenAICompatibleBackend` 接真实端点跑通 Director / Researcher / Reviewer 语义路径并验收的记录 | 真实模型下的结构化产物质量、JSON 输出稳定性、语义 finding 可用性均未验证；离线结论不可外推 |
| 渲染回看 harness 未进库方法 | PPTX → PDF → 逐页 PNG 的转换链路在 `scripts/verify.sh` / CI 外部编排；库内只提供 `gates/visual.py` 的 PNG 判定函数 | 视觉门的产物侧喂数（soffice / pdftoppm）不是库调用；库方法不能独立完成"出片后回看" |
| Designer 独立角色类 | 当前是模块级函数集合，无统一角色对象接口与实例状态 | 不能把系统描述成"五个对等角色对象"；这是形态差异，现有函数职责已闭合 |
| 端到端自动修复的自然链路验证 | 纯离线链路不自然产生可恢复 critical（见 6.3）；缺接后端后真实打回—修复—收敛的用例 | 不能宣称"端到端自动修复已验证"；修复分支目前由注入点或直喂未加工 Page 触发 |
| MCP 入口 | `src/` 内无 MCP server / tool 暴露实现，`connectors/`、`vision/` 包为空 | 现状只有库调用与 CLI 两个入口；旧 README 的"多入口"表述需更正 |
| 既有 PPTX 反向解析与编辑式改造 | 缺读取现有 PPTX、诊断后回写编辑的路径；引擎只做 spec → PPTX 正向渲染 | "现有 PPT 优化"场景当前无代码支撑，属规划方向 |
| Researcher 联网接地检索 | 后端协议只有 `complete(prompt)` 文本补全，无检索工具；`researcher.py` docstring 注明接地需调用方提供后端 | 证据真实性依赖所接后端能力；`ReplayBackend` 回放不产出真实可核验证据 |

## 8. 被否决的方案与理由

1. **让 LLM 直接打分做硬门。** 语义判断不可复现，同一页两次打分可能不同；问题无法归因到稳定规则码，CI 干净环境无法执行，出红也无法定位修什么。现状折中：确定性规则把守硬门（critical 只来自 RV001–RV008），语义 finding 最高 warning（`reviewer.py` 中 critical 强制降级），不阻断交付。
2. **让 agent 手写 Inches 坐标。** 坐标绑定画布尺寸与字体度量，换尺寸即崩；内容长度抖动会带动位置漂移，错误不可收敛，也无法写测试断言。现状契约：`design()` 只回吐语义，坐标全部在骨架内计算（`skeletons.py` 模块docstring："骨架不接收任何坐标参数"）。
3. **为消除留白给指标加撑满内容区的底板。** 实测（AGENTS.md 3.1 空卡片教训）：底板把页面变成三块大空卡片，正是被批评的格阵式。`_stat` 的做法是块高由内容决定、在内容区垂直居中，不靠撑满底板制造空卡片。
4. **未知骨架静默降级到基础页型。** 静默降级会让"看起来渲染成功"掩盖契约破坏：选了不存在的骨架，语义意图没有被正确承载，却不报错。现状：`render_skeleton()` 对未注册骨架直接抛 `ValueError`；`Page.validate()` 先用 `SKELETONS` 白名单拦下。
5. **骨架几何依赖内容长度抖动或随机量。** 同一份内容在不同次运行、不同画布尺寸下必须成立；长度只允许影响字号分档（如 `_value_size` 按字符数选 66/52/42/34pt），不允许改变位置关系。

## 9. 与"直接让 LLM 一键生成 PPT"的本质区别

分歧不在生成质量高低，而在两个工程属性：

- **错误能否收敛。** 一键链路里，版面问题（溢出、重叠、对比度不足、留白过大）混在自然语言产出里，发现后只能整体重来，无法定位到可修复的规则项。本仓库把错误切成可执行判决：静态门与视觉门输出定位到页与字段的 issue，评审 finding 带稳定规则码与 `fix` 方向，`repair()` 按码做确定性修复，超限才升级人工。
- **产物能否审计。** 一键产出的是不可回溯的成片；本仓库的产物是经过 `Deck.validate` / `Page.validate` / 规则判决的结构化 `Page` + 可编辑 OOXML，证据与口径进 `note` 留档，门禁结论可在 CI 干净环境复现。

需要说明：单页五角色端到端出 PPTX 已成立（`build_pptx` 渲染并过静态门，见 7.1）；Deck 级编排、真实后端下的收敛性尚未落地（见 7.2）。
