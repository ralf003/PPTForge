#!/usr/bin/env bash
# 配置 main 分支保护：required status check 只设 quality，render-preview 非阻断。
# 技术正确性由 quality 硬门 + 评审委员会裁决，人不做代码对错判断，故不要求人工 approval。
# 需具备 admin 权限的凭据：gh 登录态，或 GITHUB_TOKEN 环境变量。
set -euo pipefail

OWNER="ralf003"
REPO="PPTForge"
BRANCH="main"

read -r -d '' BODY <<'JSON' || true
{
  "required_status_checks": {
    "strict": false,
    "checks": [ { "context": "quality" } ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false
}
JSON

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh api -X PUT "repos/$OWNER/$REPO/branches/$BRANCH/protection" --input - <<<"$BODY"
  echo "已通过 gh 配置分支保护"
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  curl -fsSL -X PUT \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$OWNER/$REPO/branches/$BRANCH/protection" \
    -d "$BODY"
  echo "已通过 curl 配置分支保护"
else
  echo "错误：未检测到 gh 登录态或 GITHUB_TOKEN，无法配置。" >&2
  echo "请先 'gh auth login' 或 'export GITHUB_TOKEN=<admin PAT>' 后重跑本脚本。" >&2
  exit 1
fi
