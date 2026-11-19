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
