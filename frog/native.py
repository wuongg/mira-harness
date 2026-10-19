"""Native tool-calling — bỏ giao thức văn bản, dùng đúng API của từng hãng.

Vì sao phải làm: giao thức văn bản (`<tool>{...}</tool>`) dễ vỡ theo ba cách đã
gặp thật — model nhắc lại tên thẻ trong văn xuôi, JSON hỏng, và không gọi được
nhiều công cụ trong một lượt. Native tool-calling lo cả ba ở tầng giao thức.

Kiến trúc: một dạng TRUNG LẬP duy nhất, mỗi hãng dịch ra/từ định dạng dây của mình.

  trung lập (nội bộ)                    Anthropic                  OpenAI / tương thích
  ─────────────────────────────────────────────────────────────────────────────────
  {"type":"text","text":...}            content block "text"       message.content
  {"type":"tool_use","id","name",        content block "tool_use"   message.tool_calls[]
     "input":{...}}
  {"type":"tool_result",                 content block              message role "tool"
     "tool_use_id","content","is_error"}  "tool_result"
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Iterator

from .providers import BaseProvider, ProviderError, retry_open

# ------------------------------------------------------------------ schema công cụ
SCHEMAS: dict[str, dict] = {
    "read_file": {"description": "Đọc một cửa sổ dòng (mặc định 100), có số dòng",
                  "properties": {"path": {"type": "string", "description": "đường dẫn tương đối"},
                                 "start": {"type": "integer", "description": "dòng bắt đầu, mặc định 1"},
                                 "n": {"type": "integer", "description": "số dòng, mặc định 100"},
                                 "symbol": {"type": "string", "description": "tên hàm hoặc lớp, nhảy tới dòng đó"}},
                  "required": ["path"]},
    "list_dir": {"description": "Liệt kê nội dung thư mục",
                 "properties": {"path": {"type": "string"}}, "required": []},
    "grep": {"description": "Liệt kê tệp khớp và số lần, không đổ nội dung dòng",
             "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
             "required": ["pattern"]},
    "write_file": {"description": "GHI một tệp (cần người dùng duyệt)",
                   "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                   "required": ["path", "content"]},
    "run_shell": {"description": "CHẠY một lệnh shell trong thư mục gốc (cần người dùng duyệt)",
                  "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]},
    "finish": {"description": "Kết thúc và trả tóm tắt",
               "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    "glob": {"description": "Tìm tệp theo mẫu glob (ví dụ **/*.py)",
             "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
             "required": ["pattern"]},
    "edit_file": {"description": "Sửa tại chỗ: thay đoạn old bằng new trong một tệp (cần duyệt)",
                  "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                 "new": {"type": "string"}, "count": {"type": "integer"}},
                  "required": ["path", "old", "new"]},
    "delete_file": {"description": "XOÁ một tệp (luôn cần người dùng duyệt)",
                    "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "fetch_url": {"description": "Tải nội dung một URL http/https (cần duyệt — thoát mạng)",
                  "properties": {"url": {"type": "string"}}, "required": ["url"]},
    "todo_write": {"description": "Ghi danh sách việc cần làm của lượt này",
                   "properties": {"items": {"type": "array", "items": {"type": "string"}}},
                   "required": ["items"]},
    "multi_edit": {"description": "Sửa nhiều chỗ trong một/nhiều tệp, một lượt (cần duyệt)",
                   "properties": {"edits": {"type": "array", "items": {
                       "type": "object",
                       "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                      "new": {"type": "string"}, "count": {"type": "integer"}},
                       "required": ["path", "old", "new"]}}},
                   "required": ["edits"]},
    "web_search": {"description": "Tìm trên web (cần duyệt — thoát mạng)",
                   "properties": {"query": {"type": "string"}, "n": {"type": "integer"},
                                  "provider": {"type": "string"}}, "required": ["query"]},
    "install_skill": {"description": "Tải một SKILL.md qua https vào catalog. Không tải script.",
                      "properties": {"url": {"type": "string"}}, "required": ["url"]},
    "mcp_list": {"description": "Liệt kê tool của một server MCP https",
                 "properties": {"url": {"type": "string"}}, "required": ["url"]},
    "mcp_call": {"description": "Gọi một tool MCP https. Kết quả là dữ liệu không tin.",
                 "properties": {"url": {"type": "string"}, "tool": {"type": "string"},
                                "arguments": {"type": "object"}},
                 "required": ["url", "tool"]},
    "task": {"description": "Giao một việc nhỏ cho agent con rồi nhận tóm tắt",
             "properties": {"task": {"type": "string"}, "max_turns": {"type": "integer"},
                            "max_budget_usd": {"type": "number"}}, "required": ["task"]},
    "plan_skills": {"description": "Ghi thứ tự skill sẽ mở, không đọc thân",
                    "properties": {"names": {"type": "array", "items": {"type": "string"}}},
                    "required": ["names"]},
    "use_skill": {"description": "Mở đúng một thân skill đã có trong catalog",
                  "properties": {"name": {"type": "string"}}, "required": ["name"]},
    "read_skill_file": {"description": "Đọc một file kèm của skill đã mở, không chạy script",
                        "properties": {"name": {"type": "string"}, "path": {"type": "string"}},
                        "required": ["name", "path"]},
}


def neutral_tools(names: list[str] | None = None) -> list[dict]:
    out = []
    for name, spec in SCHEMAS.items():
        if names and name not in names:
            continue
        out.append({"name": name, "description": spec["description"],
                    "input_schema": {"type": "object",
                                     "properties": spec["properties"],
                                     "required": spec["required"]}})
    return out


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in tools]


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}} for t in tools]


# ------------------------------------------------------------------ dịch tham số
def _as_blocks(content) -> list[dict]:
    """Lịch sử lưu chữ thường. Vòng sau vẫn đọc được như khối."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content or "")}]
    blocks = []
    for item in content:
        if isinstance(item, str):
            blocks.append({"type": "text", "text": item})
        elif isinstance(item, dict) and item.get("type"):
            blocks.append(item)
    return blocks


def to_anthropic_messages(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        blocks = []
        for b in _as_blocks(m.get("content")):
            if b["type"] == "text":
                blocks.append({"type": "text", "text": b["text"]})
            elif b["type"] == "tool_use":
                blocks.append({"type": "tool_use", "id": b["id"], "name": b["name"],
                               "input": b.get("input") or {}})
            elif b["type"] == "tool_result":
                blocks.append({"type": "tool_result", "tool_use_id": b["tool_use_id"],
                               "content": b["content"],
                               **({"is_error": True} if b.get("is_error") else {})})
        if blocks:
            out.append({"role": m["role"], "content": blocks})
    return out


def to_openai_messages(msgs: list[dict]) -> list[dict]:
    out = []
    for m in msgs:
        if m["role"] == "assistant":
            blocks = _as_blocks(m.get("content"))
            text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
            calls = [b for b in blocks if b["type"] == "tool_use"]
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = [{"id": b["id"], "type": "function",
                                      "function": {"name": b["name"],
                                                   "arguments": json.dumps(b.get("input") or {},
                                                                           ensure_ascii=False)}}
                                     for b in calls]
            out.append(msg)
        else:
            for b in _as_blocks(m.get("content")):
                if b["type"] == "text":
                    out.append({"role": "user", "content": b["text"]})
                elif b["type"] == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                "content": b["content"]})
    return out


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


# ------------------------------------------------------------------ đọc phản hồi
def blocks_from_anthropic(data: dict) -> list[dict]:
    out = []
    for b in data.get("content") or []:
        t = b.get("type")
        if t == "text" and b.get("text"):
            out.append({"type": "text", "text": b["text"]})
        elif t == "tool_use":
            out.append({"type": "tool_use", "id": b.get("id") or f"call_{len(out)}",
                        "name": b.get("name") or "", "input": _args(b.get("input"))})
    return out


def blocks_from_openai(data: dict) -> list[dict]:
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    out = []
    if msg.get("content"):
        out.append({"type": "text", "text": msg["content"]})
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        out.append({"type": "tool_use", "id": c.get("id") or f"call_{len(out)}",
                    "name": fn.get("name") or "", "input": _args(fn.get("arguments"))})
    return out


def usage_from(data: dict, provider_name: str) -> dict:
    if provider_name == "anthropic":
        u = data.get("usage") or {}
        return {"in": int(u.get("input_tokens", 0)), "out": int(u.get("output_tokens", 0))}
    u = data.get("usage") or {}
    return {"in": int(u.get("prompt_tokens", 0)), "out": int(u.get("completion_tokens", 0))}


# ------------------------------------------------------------------ streaming
def _sse(resp) -> Iterator[dict]:
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def converse(provider: BaseProvider, system: str, msgs: list[dict],
             tools: list[dict], on_text: Callable[[str], None] | None = None,
             stream_it: bool = True) -> tuple[list[dict], dict]:
    """Một lượt model có công cụ. Trả (khối trung lập, usage)."""
    emit = on_text or (lambda _s: None)
    if provider.name == "anthropic":
        return _converse_anthropic(provider, system, msgs, tools, emit, stream_it)
    return _converse_openai(provider, system, msgs, tools, emit, stream_it)


def _request(provider: BaseProvider, path: str, payload: dict, headers: dict, stream_it: bool):
    req = urllib.request.Request(f"{provider.base_url}{path}",
                                 data=json.dumps(payload).encode(), method="POST")
    req.add_header("content-type", "application/json")
    if stream_it:
        req.add_header("accept", "text/event-stream")
    for k, v in headers.items():
        req.add_header(k, v)
    rng = getattr(provider, "_rng", None)
    if rng is None:
        import random
        rng = random.Random()
    try:
        resp, provider.attempts = retry_open(
            req, provider.timeout, name=provider.name, rng=rng)
    except ProviderError as e:
        provider.attempts = e.attempts
        raise
    return resp


def _converse_anthropic(p, system, msgs, tools, emit, stream_it) -> tuple[list[dict], dict]:
    payload = {"model": p.model, "max_tokens": p.max_tokens, "system": system,
               "messages": to_anthropic_messages(msgs),
               "tools": to_anthropic_tools(tools)}
    if not stream_it:
        with _request(p, "/v1/messages", payload,
                      {"x-api-key": p.api_key or "", "anthropic-version": "2023-06-01"},
                      False) as r:
            data = json.loads(r.read().decode("utf-8"))
        return blocks_from_anthropic(data), usage_from(data, "anthropic")

    payload["stream"] = True
    resp = _request(p, "/v1/messages", payload,
                    {"x-api-key": p.api_key or "", "anthropic-version": "2023-06-01"}, True)
    blocks: list[dict] = []
    cur: dict | None = None
    frag: list[str] = []
    usage = {"in": 0, "out": 0}
    with resp:
        for ev in _sse(resp):
            t = ev.get("type")
            if t == "message_start":
                usage["in"] = int((((ev.get("message") or {}).get("usage")) or {}).get("input_tokens", 0))
            elif t == "content_block_start":
                cb = ev.get("content_block") or {}
                if cb.get("type") == "tool_use":
                    cur = {"type": "tool_use", "id": cb.get("id") or "", "name": cb.get("name") or ""}
                    frag = []
                elif cb.get("type") == "text":
                    cur = {"type": "text", "text": ""}
            elif t == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    if cur and cur["type"] == "text":
                        cur["text"] += d["text"]
                    emit(d["text"])
                elif d.get("type") == "input_json_delta" and cur is not None:
                    frag.append(d.get("partial_json") or "")
            elif t == "content_block_stop":
                if cur is not None:
                    if cur["type"] == "tool_use":
                        cur["input"] = _args("".join(frag))
                    blocks.append(cur)
                    cur = None
            elif t == "message_delta":
                u = ev.get("usage") or {}
                if u.get("output_tokens"):
                    usage["out"] = int(u["output_tokens"])
    return [b for b in blocks if b["type"] != "text" or b["text"]], usage


def _converse_openai(p, system, msgs, tools, emit, stream_it) -> tuple[list[dict], dict]:
    from .providers import afford_tokens
    try:
        return _openai_once(p, system, msgs, tools, emit, stream_it)
    except ProviderError as e:
        afford = afford_tokens(str(e))
        if p.name != "openrouter" or not afford or afford >= p.max_tokens:
            raise
        p.max_tokens = afford
        return _openai_once(p, system, msgs, tools, emit, stream_it)


def _openai_once(p, system, msgs, tools, emit, stream_it) -> tuple[list[dict], dict]:
    body_msgs = [{"role": "system", "content": system}] + to_openai_messages(msgs)
    limit_key = "max_completion_tokens" if p.name == "openai" else "max_tokens"
    payload = {"model": p.model, limit_key: p.max_tokens, "messages": body_msgs,
               "tools": to_openai_tools(tools), "tool_choice": "auto"}
    headers = {"authorization": f"Bearer {p.api_key or ''}"}
    if not stream_it:
        with _request(p, "/v1/chat/completions", payload, headers, False) as r:
            data = json.loads(r.read().decode("utf-8"))
        return blocks_from_openai(data), usage_from(data, "openai")

    payload["stream"] = True
    payload["stream_options"] = {"include_usage": True}
    resp = _request(p, "/v1/chat/completions", payload, headers, True)
    blocks: list[dict] = []
    text_parts: list[str] = []
    acc: dict[int, dict] = {}
    usage = {"in": 0, "out": 0}
    with resp:
        for ev in _sse(resp):
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    text_parts.append(d["content"])
                    emit(d["content"])
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", 0)
                    slot = acc.setdefault(i, {"id": "", "name": "", "args": []})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"].append(fn["arguments"])
            u = ev.get("usage") or {}
            if u:
                usage["in"] = int(u.get("prompt_tokens", usage["in"]))
                usage["out"] = int(u.get("completion_tokens", usage["out"]))
    if "".join(text_parts).strip():
        blocks.append({"type": "text", "text": "".join(text_parts)})
    for i in sorted(acc):
        s = acc[i]
        blocks.append({"type": "tool_use", "id": s["id"] or f"call_{i}",
                       "name": s["name"], "input": _args("".join(s["args"]))})
    return blocks, usage


def text_of(blocks: list[dict]) -> str:
    return "".join(b.get("text", "") for b in blocks if b["type"] == "text")


def tool_calls(blocks: list[dict]) -> list[dict]:
    return [b for b in blocks if b["type"] == "tool_use"]
