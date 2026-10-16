"""Nhà cung cấp model — dùng urllib thuần, KHÔNG thêm thư viện ngoài.

Key đọc từ biến môi trường, không bao giờ ghi ra tệp, không bao giờ in ra.
Có `base_url` để trỏ vào server giả khi kiểm thử.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request


def _file_key(name: str) -> str | None:
    """Khoá lưu trong ~/.frog/keys.json (do `frog keys` ghi)."""
    try:
        from . import keys
        return keys.get(name)
    except Exception:                               # noqa: BLE001
        return None


class ProviderError(RuntimeError):
    def __init__(self, message: str, attempts: int = 0):
        super().__init__(message)
        self.attempts = attempts


def retry_open(request, timeout, *, name: str, rng: random.Random, sleep=time.sleep):
    """Tối đa 3 lần urlopen. Chỉ 429 và 5xx được chờ rồi thử lại."""
    url = getattr(request, "full_url", "")
    last = None
    for attempt in range(1, 4):
        try:
            return urllib.request.urlopen(request, timeout=timeout), attempt
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            try:
                e.close()
            except Exception:                               # noqa: BLE001
                pass
            err = ProviderError(f"{name}: HTTP {e.code} — {detail}", attempt)
            retry = e.code == 429 or 500 <= int(e.code) <= 599
            if not retry or attempt == 3:
                raise err from None
            last = err
            base = 0.5 if attempt == 1 else 1.0
            sleep(base + rng.uniform(0, 0.25))
        except urllib.error.URLError as e:
            raise ProviderError(
                f"{name}: không kết nối được {url} — {e.reason}", attempt) from None
    raise last


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
        self.attempts = 0
        self._rng = random.Random()

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
            resp, self.attempts = retry_open(
                req, self.timeout, name=self.name, rng=self._rng)
        except ProviderError as e:
            self.attempts = e.attempts
            raise
        with resp:
            return json.loads(resp.read().decode("utf-8"))


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


class OpenRouterProvider(OpenAICompatProvider):
    """Một khoá, nhiều model. Endpoint giống OpenAI."""
    name = "openrouter"
    default_base = "https://openrouter.ai/api"
    env_key = "OPENROUTER_API_KEY"

    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None, timeout: int = 180,
                 max_tokens: int = 512):
        # OpenRouter giữ credit theo trần token xin trước. 4096 dễ vượt số dư khoá.
        super().__init__(model, api_key=api_key, base_url=base_url, timeout=timeout,
                         max_tokens=min(int(max_tokens or 512), 512))

    def call(self, system: str, user: str) -> tuple[str, dict]:
        try:
            return self._complete(system, user)
        except ProviderError as e:
            afford = afford_tokens(str(e))
            if not afford or afford >= self.max_tokens:
                raise
            self.max_tokens = afford
            return self._complete(system, user)

    def _complete(self, system: str, user: str) -> tuple[str, dict]:
        data = self._post("/v1/chat/completions", {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, {"authorization": f"Bearer {self.api_key or ''}",
            "HTTP-Referer": "https://github.com/wuongg/mira-harness",
            "X-Title": "frog"})
        ch = (data.get("choices") or [{}])[0]
        text = (ch.get("message") or {}).get("content") or ""
        u = data.get("usage", {}) or {}
        return text, {"in": int(u.get("prompt_tokens", 0)), "out": int(u.get("completion_tokens", 0))}


REGISTRY = {"openrouter": OpenRouterProvider, "anthropic": AnthropicProvider,
            "openai": OpenAICompatProvider, "xai": XAIProvider}


def afford_tokens(detail: str) -> int | None:
    """Số token OpenRouter còn cho phép khi trả 402."""
    found = re.search(r"can only afford (\d+)", detail or "")
    if not found:
        return None
    count = int(found.group(1))
    return count if count >= 1 else None

# tên model -> nhà cung cấp, để tự chọn khi không truyền --provider
BY_MODEL = (("claude", "anthropic"), ("opus", "anthropic"), ("sonnet", "anthropic"),
            ("haiku", "anthropic"), ("grok", "xai"))


def agent_binding(model: str, provider_name: str | None = None) -> tuple[str, str | None]:
    """Có khoá OpenRouter thì phiên agent đi OpenRouter. Khoá hãng khác không được gọi thay."""
    from . import config as C
    from .keys import resolve
    if provider_name and provider_name != "openrouter":
        return model, provider_name
    if resolve("openrouter")[0]:
        chosen = model if model and "/" in model else C.OPENROUTER_MODEL
        return chosen, "openrouter"
    return model, provider_name


def provider_for(model: str, name: str | None = None, **kw) -> BaseProvider:
    if name:
        if name not in REGISTRY:
            raise ProviderError(f"không biết provider {name!r}; có: {', '.join(REGISTRY)}")
        cls = REGISTRY[name]
    else:
        low = model.lower()
        if "/" in low:
            cls = REGISTRY["openrouter"]
        else:
            cls = OpenAICompatProvider
            for needle, prov in BY_MODEL:
                if needle in low:
                    cls = REGISTRY[prov]
                    break
    return cls(model=model, **kw)


def detect_available() -> list[str]:
    """Nhà cung cấp nào có key trong môi trường."""
    return [n for n, cls in REGISTRY.items() if cls(model="x").available()]
