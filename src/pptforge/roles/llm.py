"""可替换 LLM 后端：角色只依赖 LLMBackend 协议，不绑定具体厂商。

- OpenAICompatibleBackend：标准 chat completions，任意 OpenAI 兼容端点可接
  （豆包/方舟/OpenAI/本地 vLLM），凭据走环境变量，不写进仓库。
- ReplayBackend：确定性回放，用于无凭据环境的离线测试与演示。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Protocol


class LLMBackend(Protocol):
    def complete(self, prompt: str) -> str:  # pragma: no cover - 协议声明
        ...


class ReplayBackend:
    """按预置响应回放；responses 为 prompt 关键词 -> 响应文本，或默认响应队列。"""

    def __init__(self, responses: dict[str, str] | None = None, default: str = "") -> None:
        self._responses = responses or {}
        self._default = default

    def complete(self, prompt: str) -> str:
        for key, resp in self._responses.items():
            if key in prompt:
                return resp
        return self._default


class OpenAICompatibleBackend:
    """OpenAI Chat Completions 兼容后端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("PPTFORGE_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("PPTFORGE_LLM_API_KEY", "")
        self.model = model or os.environ.get("PPTFORGE_LLM_MODEL", "")
        self._timeout = timeout
        if not self.base_url or not self.model:
            raise ValueError("需配置 PPTFORGE_LLM_BASE_URL 与 PPTFORGE_LLM_MODEL")

    def complete(self, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM 后端返回 {exc.code}：{body[:300]}") from exc
        return data["choices"][0]["message"]["content"]


def extract_json(text: str):
    """从 LLM 输出提取 JSON，兼容 markdown 代码块与前后缀文字。"""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    raw = fenced.group(1).strip() if fenced else text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"输出中未找到 JSON 对象：{text[:120]}")
    return json.loads(raw[start : end + 1])


def default_backend() -> LLMBackend:
    """按环境变量选择后端；无配置时报错，由调用方决定回放或显式传入。"""
    if os.environ.get("PPTFORGE_LLM_BASE_URL") and os.environ.get("PPTFORGE_LLM_MODEL"):
        return OpenAICompatibleBackend()
    raise ValueError(
        "未配置 LLM 后端：请设置 PPTFORGE_LLM_BASE_URL/PPTFORGE_LLM_API_KEY/PPTFORGE_LLM_MODEL，"
        "或显式传入 ReplayBackend。"
    )
