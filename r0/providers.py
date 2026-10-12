"""Nhà cung cấp model — dùng urllib thuần, KHÔNG thêm thư viện ngoài.

Key đọc từ biến môi trường, không bao giờ ghi ra tệp, không bao giờ in ra.
Có `base_url` để trỏ vào server giả khi kiểm thử.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def _file_key(name: str) -> str | None:
    """Khoá lưu trong ~/.r0/keys.json (do `r0-shadow keys` ghi)."""
    try:
        from . import keys
        return keys.get(name)
    except Exception:                               # noqa: BLE001
        return None


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    name = "base"
    default_base = ""

    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None, timeout: int = 180,
                 max_tokens: int = 4096):
        self.model = model
        # None = chưa truyền -> đọc biến môi trường.
        # ""   = CỐ Ý không có key -> KHÔNG được rơi về môi trường.
        # Phân biệt hai thứ này: nếu không, một chỗ gọi truyền chuỗi rỗng sẽ âm thầm
        # dùng key thật của môi trường, và mọi bài kiểm "thiếu key" thành vô nghĩa.
        self.api_key = ((self._key_from_env() or _file_key(self.name))
                        if api_key is None else (api_key or None))
        self.base_url = (base_url or self.default_base).rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _key_from_env(self) -> str | None:
        raise NotImplementedError

    def available(self) -> bool:
        return bool(self.api_key)

    def call(self, system: str, user: str) -> tuple[str, dict]:
        raise NotImplementedError

    def _post(self, path: str, payload: dict, headers: dict) -> dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("content-type", "application/json")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ProviderError(f"{self.name}: HTTP {e.code} — {detail}") from None
        except urllib.error.URLError as e:
            raise ProviderError(f"{self.name}: không kết nối được {url} — {e.reason}") from None


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    default_base = "https://api.anthropic.com"

    def _key_from_env(self):
        return os.environ.get("ANTHROPIC_API_KEY")

    def call(self, system: str, user: str) -> tuple[str, dict]:
        data = self._post("/v1/messages", {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }, {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage", {}) or {}
        return text, {"in": int(u.get("input_tokens", 0)), "out": int(u.get("output_tokens", 0))}


class OpenAICompatProvider(BaseProvider):
    """OpenAI và mọi endpoint tương thích (xAI, DeepSeek, local llama.cpp…)."""
    name = "openai"
    default_base = "https://api.openai.com"
    env_key = "OPENAI_API_KEY"

    def _key_from_env(self):
        return os.environ.get(self.env_key)

    def call(self, system: str, user: str) -> tuple[str, dict]:
        data = self._post("/v1/chat/completions", {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, {"authorization": f"Bearer {self.api_key or ''}"})
        ch = (data.get("choices") or [{}])[0]
        text = (ch.get("message") or {}).get("content") or ""
        u = data.get("usage", {}) or {}
        return text, {"in": int(u.get("prompt_tokens", 0)), "out": int(u.get("completion_tokens", 0))}


class XAIProvider(OpenAICompatProvider):
    name = "xai"
    default_base = "https://api.x.ai"
    env_key = "XAI_API_KEY"


REGISTRY = {"anthropic": AnthropicProvider, "openai": OpenAICompatProvider, "xai": XAIProvider}

# tên model -> nhà cung cấp, để tự chọn khi không truyền --provider
BY_MODEL = (("claude", "anthropic"), ("opus", "anthropic"), ("sonnet", "anthropic"),
            ("haiku", "anthropic"), ("grok", "xai"))


def provider_for(model: str, name: str | None = None, **kw) -> BaseProvider:
    if name:
        if name not in REGISTRY:
            raise ProviderError(f"không biết provider {name!r}; có: {', '.join(REGISTRY)}")
        cls = REGISTRY[name]
    else:
        cls = OpenAICompatProvider
        low = model.lower()
        for needle, prov in BY_MODEL:
            if needle in low:
                cls = REGISTRY[prov]
                break
    return cls(model=model, **kw)


def detect_available() -> list[str]:
    """Nhà cung cấp nào có key trong môi trường."""
    return [n for n, cls in REGISTRY.items() if cls(model="x").available()]
