# ops — 运维脚本

仓库一次性运维操作的可执行脚本。脚本只做声明式配置，凭据由运行环境提供，禁止把密钥写入仓库。

## branch-protection.sh

配置 `main` 分支保护，落地"核心质量门阻断、渲染回看非阻断"的人机边界：

- **required status check 只设 `quality`**：核心质量门（Ruff/Mypy/Pytest/静态质量门/泄漏扫描）全绿才允许合并。
- `render-preview` 不设为 required：apt 安装 LibreOffice 的环境抖动不阻断合并。
- `required_approving_review_count = 0`：技术正确性由质量硬门与评审委员会裁决，不要求人工 approval；人只保留意图/授权与最终视觉确认。
- 禁止 force push 与删除分支，admin 同样受规则约束。
执行（需 admin 凭据，二选一）：

```bash
gh auth login            # 方式一：gh 登录态
export GITHUB_TOKEN=<admin PAT>   # 方式二：令牌
./ops/branch-protection.sh
```

当前会话未配置 admin 凭据，脚本已就绪、待凭据可用时执行一次；执行后可用
`gh api repos/ralf003/PPTForge/branches/main/protection` 回读验证。

## verify.sh（本地一键全套验收）

`scripts/verify.sh` 在本地跑与 CI 同款的完整链路，作为交付前自检；任一步失败立即非零退出并指明失败步骤，末尾打印通过/失败与总耗时。

用法：

```bash
bash scripts/verify.sh                # 全量：静态检查 + 测试 + 渲染 + 视觉门
bash scripts/verify.sh --skip-visual  # 跳过 soffice / pdftoppm / check-visual
```

解释器优先使用仓库内 `.venv/bin/python`，其次 `python3` / `python`；脚本启动时会打印实际使用的解释器与版本。

### 与 CI 的对应关系

| verify.sh 步骤 | 对应 CI job |
|---|---|
| doctor 环境自检 | 本地前置自检（quality job 未单列 doctor） |
| ruff check src tests | quality · Ruff |
| mypy src | quality · Mypy |
| pytest | quality · Pytest |
| build 生成 PPTX | quality · 渲染示例并跑质量门；render-preview · build |
| soffice 转 PDF | render-preview · 安装LibreOffice并渲染逐页回看 |
| pdftoppm 逐页出图 | render-preview · 安装LibreOffice并渲染逐页回看 |
| check-visual 视觉门 | render-preview · 视觉门：check-visual 逐页回看 |

### `--skip-visual` 的边界

- 仅跳过 soffice 转 PDF、pdftoppm 出图、check-visual 视觉门三段；doctor / ruff / mypy / pytest / build 照跑。
- 适用场景：没有 LibreOffice / poppler-utils 的环境做静态链路自检。
- 跳过视觉门不等于视觉合格：视觉门必须吃渲染后的 PNG，不能从 PPTX 结构估算（见 AGENTS 3.2）。交付前必须在装有 soffice 的环境跑一次全量 `bash scripts/verify.sh`。
