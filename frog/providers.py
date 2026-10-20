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
import urllib.parse
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


def decode_completion(raw: str) -> dict:
    """JSON một cục, hoặc SSE `data:`. Lỗi trong SSE thành ProviderError, không vỡ json.loads."""
    text = (raw or "").strip()
    if not text:
        raise ProviderError("phản hồi rỗng")
    if not text.startswith("data:"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"phản hồi không phải JSON: {exc}") from exc
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ProviderError(msg or "lỗi từ model")
        if not isinstance(data, dict):
            raise ProviderError("phản hồi không phải JSON")
        return data
    parts: list[str] = []
    err = ""
    usage = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("error"):
            body = event["error"]
            err = body.get("message") if isinstance(body, dict) else str(body)
            continue
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        choice = (event.get("choices") or [{}])[0] if event.get("choices") else {}
        delta = choice.get("delta") or choice.get("message") or {}
        bit = delta.get("content") or ""
        if bit:
            parts.append(bit)
    if err and not parts:
        raise ProviderError(err)
    return {"choices": [{"message": {"content": "".join(parts)}}], "usage": usage}


def openai_usage(data: dict) -> dict:
    """SSE không kèm usage thì đánh dấu unknown. Không biết token không có nghĩa là 0 đồng."""
    if "usage" in data and data["usage"] is None:
        return {"in": 0, "out": 0, "unknown": True}
    u = data.get("usage") or {}
    return {"in": int(u.get("prompt_tokens", 0)), "out": int(u.get("completion_tokens", 0))}


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
            return decode_completion(resp.read().decode("utf-8"))


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
            "max_completion_tokens" if self.name == "openai" else "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, {"authorization": f"Bearer {self.api_key or ''}"})
        ch = (data.get("choices") or [{}])[0]
        text = (ch.get("message") or {}).get("content") or ""
        return text, openai_usage(data)


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
        return text, openai_usage(data)


SUBSCRIPTION_NOTE = "uncertain (subscription quota)"


class NineRouterProvider(OpenAICompatProvider):
    """9router cục bộ. Model id truyền nguyên, ví dụ cu/claude-opus-5-thinking-high.

    Gói thuê bao: sổ ghi uncertain, không có $/token và không có $0.
    """
    name = "9router"
    default_base = "http://localhost:20120"
    env_key = "NINE_ROUTER_API_KEY"
    base_env = "NINE_ROUTER_BASE_URL"
    billing = "subscription"

    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None, timeout: int = 180,
                 max_tokens: int = 4096):
        super().__init__(model, api_key=api_key,
                         base_url=base_url or os.environ.get(self.base_env),
                         timeout=timeout, max_tokens=max_tokens)

    def call(self, system: str, user: str) -> tuple[str, dict]:
        try:
            return super().call(system, user)
        except ProviderError as exc:
            raise ProviderError(self.explain(str(exc)), exc.attempts) from None

    def explain(self, detail: str) -> str:
        """Lỗi kèm việc cần làm. Model không có thì liệt kê model khả dụng."""
        if "không kết nối được" in detail:
            return (f"{detail}. Kiểm tra 9router đang chạy, rồi chỉ địa chỉ bằng --base-url "
                    f"hoặc {self.base_env} (mặc định {self.default_base}).")
        if re.search(r"HTTP 40[13]\b", detail):
            return (f"{detail}. 9router từ chối khóa: đặt {self.env_key} bằng khóa "
                    "ở trang Endpoint & Key của 9router.")
        if re.search(r"HTTP (400|404)\b", detail) or "model_not_found" in detail:
            ids, _why = probe_models(self.base_url, self.api_key)
            if ids and self.model not in ids:
                return unknown_model_message(self.model, ids)
        return detail


REGISTRY = {"openrouter": OpenRouterProvider, "anthropic": AnthropicProvider,
            "openai": OpenAICompatProvider, "xai": XAIProvider,
            "9router": NineRouterProvider}


def missing_key_text(prov) -> str:
    """Thiếu khóa thì nói đúng tên biến môi trường của nhà cung cấp đó."""
    from .keys import ENV
    env = ENV.get(getattr(prov, "name", ""), "")
    text = f"thiếu key cho {prov.name} — đặt {env}" if env else f"thiếu key cho {prov.name}"
    if prov.name == "9router":
        text += " (khóa ở trang Endpoint & Key của 9router), hoặc frog keys set --provider 9router"
    return text


def model_flags(model: str) -> list[str]:
    """Nhãn theo id model. Họ fable không có zero data retention."""
    return ["no_zdr"] if "fable" in (model or "").lower() else []


def flag_warning(model: str) -> str:
    if "no_zdr" in model_flags(model):
        return (f"{model} gắn nhãn no_zdr: phía cung cấp có thể giữ dữ liệu gửi đi. "
                "Đừng gửi dữ liệu nhạy cảm.")
    return ""


def unknown_model_message(model: str, ids: list[str], limit: int = 12) -> str:
    import difflib
    close = difflib.get_close_matches(model, ids, n=limit, cutoff=0.0)
    more = len(ids) - len(close)
    tail = f" và {more} model khác (frog doctor --models để xem đủ)" if more > 0 else ""
    return f"9router không có model {model}. Model khả dụng gần nhất: {', '.join(close)}{tail}."


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


def official_openrouter(base_url: str | None) -> bool:
    """Không có địa chỉ, hoặc đúng host OpenRouter. Proxy cục bộ không đi nhánh này."""
    if not base_url:
        return True
    host = urllib.parse.urlparse(base_url).netloc.lower()
    return host.endswith("openrouter.ai")


def choose_proxy_model(ids: list[str]) -> str:
    """Model auto của proxy, ví dụ cu/default. Không có thì lấy id đầu."""
    for item in ids:
        if item.endswith("/default"):
            return item
    return ids[0] if ids else ""


def probe_models(base_url: str, api_key: str | None, timeout: int = 15) -> tuple[list[str], str]:
    """GET /v1/models. Trả (id, lý do khi không có id)."""
    url = base_url.rstrip("/") + "/v1/models"
    req = urllib.request.Request(url, headers={"authorization": f"Bearer {api_key or ''}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code} tại {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return [], f"không kết nối được {url} — {getattr(e, 'reason', e)}"
    except json.JSONDecodeError:
        return [], f"{url} không trả JSON"
    rows = data.get("data") if isinstance(data, dict) else None
    ids = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("id"):
            ids.append(str(row["id"]))
        elif isinstance(row, str) and row:
            ids.append(row)
    return ids, "" if ids else f"{url} không trả model nào"


def list_proxy_models(base_url: str, api_key: str | None) -> list[str]:
    """GET /v1/models. Danh sách rỗng nếu proxy không trả id."""
    return probe_models(base_url, api_key)[0]


def agent_binding(model: str, provider_name: str | None = None,
                  base_url: str | None = None) -> tuple[str, str | None]:
    """Có khoá OpenRouter thì phiên agent đi OpenRouter. Khoá hãng khác không được gọi thay.

    Proxy tự đặt địa chỉ thì giữ model đã chọn. Không đổi thành slug Anthropic.
    Model `cu/` là id của 9router, không gửi sang OpenRouter.
    """
    from . import config as C
    from .keys import resolve
    if provider_name in (None, "9router") and (model or "").lower().startswith("cu/"):
        return model, "9router"
    if provider_name and provider_name != "openrouter":
        return model, provider_name
    if resolve("openrouter")[0] and official_openrouter(base_url):
        chosen = model if model and "/" in model else C.OPENROUTER_MODEL
        return chosen, "openrouter"
    if resolve("openrouter")[0] and base_url:
        return model, "openrouter"
    return model, provider_name


def _class_for(model: str, name: str | None = None):
    if name:
        if name not in REGISTRY:
            raise ProviderError(f"không biết provider {name!r}; có: {', '.join(REGISTRY)}")
        return REGISTRY[name]
    low = (model or "").lower()
    if low.startswith("cu/"):
        return REGISTRY["9router"]
    if "/" in low:
        return REGISTRY["openrouter"]
    for needle, prov in BY_MODEL:
        if needle in low:
            return REGISTRY[prov]
    return OpenAICompatProvider


def provider_for(model: str, name: str | None = None, **kw) -> BaseProvider:
    return _class_for(model, name)(model=model, **kw)


def auto_provider() -> str | None:
    """Chỉ có khóa 9router, không có khóa hãng nào cho model mặc định, thì đi 9router."""
    from .keys import resolve
    if not resolve("9router")[0]:
        return None
    if any(resolve(name)[0] for name in ("anthropic", "openai", "openrouter", "xai")):
        return None
    return "9router"


def billing_of(model: str, name: str | None = None) -> str:
    """'subscription' hoặc 'metered'. Không dựng provider, không đọc khóa."""
    try:
        cls = _class_for(model, name)
    except ProviderError:
        return "metered"
    return getattr(cls, "billing", "metered")


def detect_available() -> list[str]:
    """Nhà cung cấp nào có key trong môi trường."""
    return [n for n, cls in REGISTRY.items() if cls(model="x").available()]
