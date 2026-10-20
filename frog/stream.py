"""Streaming SSE — đọc dần phản hồi của model, vẫn dùng urllib thuần."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Iterator

from .providers import BaseProvider, ProviderError


def _open(provider: BaseProvider, path: str, payload: dict, headers: dict):
    req = urllib.request.Request(f"{provider.base_url}{path}",
                                 data=json.dumps(payload).encode(), method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("accept", "text/event-stream")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        return urllib.request.urlopen(req, timeout=provider.timeout)
    except urllib.error.HTTPError as e:
        raise ProviderError(f"{provider.name}: HTTP {e.code} — "
                            f"{e.read().decode('utf-8','replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"{provider.name}: không kết nối được — {e.reason}") from None


def _sse(resp) -> Iterator[dict]:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def stream(provider: BaseProvider, system: str, user: str,
           on_text: Callable[[str], None] | None = None) -> tuple[str, dict]:
    """Chạy một lượt có streaming. Trả (toàn văn, usage)."""
    emit = on_text or (lambda _s: None)
    if provider.name == "anthropic":
        return _stream_anthropic(provider, system, user, emit)
    return _stream_openai(provider, system, user, emit)


def _stream_anthropic(p, system, user, emit) -> tuple[str, dict]:
    resp = _open(p, "/v1/messages", {
        "model": p.model, "max_tokens": p.max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}], "stream": True,
    }, {"x-api-key": p.api_key or "", "anthropic-version": "2023-06-01"})
    parts: list[str] = []
    usage = {"in": 0, "out": 0}
    with resp:
        for ev in _sse(resp):
            t = ev.get("type")
            if t == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    parts.append(d["text"])
                    emit(d["text"])
            elif t == "message_start":
                usage["in"] = int(((ev.get("message") or {}).get("usage") or {}).get("input_tokens", 0))
            elif t == "message_delta":
                u = ev.get("usage") or {}
                if u.get("output_tokens"):
                    usage["out"] = int(u["output_tokens"])
    return "".join(parts), usage


def _stream_openai(p, system, user, emit) -> tuple[str, dict]:
    resp = _open(p, "/v1/chat/completions", {
        "model": p.model, "max_tokens": p.max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }, {"authorization": f"Bearer {p.api_key or ''}"})
    parts: list[str] = []
    usage = {"in": 0, "out": 0}
    seen_usage = False
    error = ""
    with resp:
        for ev in _sse(resp):
            if ev.get("error"):
                body = ev["error"]
                error = (body.get("message") if isinstance(body, dict) else str(body)) or "lỗi từ model"
                continue
            for ch in (ev.get("choices") or []):
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                    emit(piece)
            u = ev.get("usage") or {}
            if u:
                seen_usage = True
                usage["in"] = int(u.get("prompt_tokens", usage["in"]))
                usage["out"] = int(u.get("completion_tokens", usage["out"]))
    if error and not parts:
        raise ProviderError(f"{p.name}: {error}")
    if not seen_usage:
        usage["unknown"] = True
    return "".join(parts), usage
