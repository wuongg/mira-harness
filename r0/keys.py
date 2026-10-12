"""Cài khoá API cho từng nhà cung cấp — lưu ở ~/.r0/keys.json.

Thứ tự tìm khoá (cái nào có trước thì thắng):
  1. tham số --api-key truyền trực tiếp
  2. biến môi trường (OPENROUTER_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY / XAI_API_KEY)
  3. tệp ~/.r0/keys.json (do lệnh `r0-shadow keys` ghi)

Khoá KHÔNG bao giờ in đầy đủ ra màn hình — chỉ 4 ký tự đầu … 4 ký tự cuối.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import ui

KEYS_PATH = Path.home() / ".r0" / "keys.json"

ENV = {"openrouter": "OPENROUTER_API_KEY",
       "anthropic": "ANTHROPIC_API_KEY",
       "openai": "OPENAI_API_KEY",
       "xai": "XAI_API_KEY",
       "tavily": "TAVILY_API_KEY",
       "brave": "BRAVE_API_KEY",
       "serper": "SERPER_API_KEY"}

LABEL = {"openrouter": "OpenRouter (model của agent)",
         "anthropic": "Anthropic (Claude)",
         "openai": "OpenAI (GPT)",
         "xai": "xAI (Grok)",
         "tavily": "Tavily (tìm kiếm web)",
         "brave": "Brave Search (tìm kiếm web)",
         "serper": "Serper / Google (tìm kiếm web)"}


def load() -> dict:
    try:
        d = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d: dict) -> Path:
    KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEYS_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    try:
        os.chmod(KEYS_PATH, 0o600)      # chỉ chủ sở hữu đọc được (bỏ qua trên Windows)
    except OSError:
        pass
    return KEYS_PATH


def get(provider: str) -> str | None:
    v = load().get(provider)
    return v or None


def resolve(provider: str) -> tuple[str | None, str]:
    """(khoá, nguồn). nguồn: 'env' | 'file' | '' (không có)."""
    env = os.environ.get(ENV.get(provider, ""))
    if env:
        return env, "env"
    v = get(provider)
    if v:
        return v, "file"
    return None, ""


def mask(k: str | None) -> str:
    if not k:
        return "—"
    if len(k) <= 10:
        return k[:2] + "…"
    return k[:6] + "…" + k[-4:]


def set_key(provider: str, key: str) -> Path:
    d = load()
    if key:
        d[provider] = key
    else:
        d.pop(provider, None)
    return save(d)


def status_rows() -> list[list[str]]:
    src_name = {"env": "biến môi trường", "file": "tệp keys.json", "": "—"}
    rows = []
    for prov in ENV:
        k, src = resolve(prov)
        rows.append([prov, LABEL[prov], "có" if k else "chưa",
                     src_name[src], mask(k)])
    return rows


def print_status() -> None:
    ui.section("Khoá API")
    ui.table(["nhà cung cấp", "tên", "trạng thái", "nguồn", "khoá"],
             status_rows(), ["l", "l", "l", "l", "l"])
    ui.footer(f"tệp: {KEYS_PATH}")


def prompt_setup(providers: list[str] | None = None) -> int:
    """Hỏi từng nhà cung cấp, ghi khoá. Gõ trống = giữ nguyên."""
    provs = providers or list(ENV)
    print()
    for prov in provs:
        cur, src = resolve(prov)
        ui.kv(LABEL[prov], (f"đang có ({src}) " + mask(cur)) if cur else "chưa có")
        try:
            v = input(ui.c(f"  nhập khoá {LABEL[prov]} (Enter = bỏ qua): ", "bold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if v:
            set_key(prov, v)
            ui.note(f"Đã lưu khoá {LABEL[prov]}.", "ok")
    print()
    print_status()
    return 0


def cmd_keys(args) -> int:
    action = getattr(args, "action", None) or "status"
    if action == "status":
        print_status()
        return 0
    if action == "set":
        prov = getattr(args, "provider", None)
        return prompt_setup([prov] if prov else None)
    if action == "clear":
        prov = getattr(args, "provider", None)
        if not prov:
            ui.note("Cần chỉ nhà cung cấp để xoá khoá.", "warn")
            return 2
        set_key(prov, "")
        ui.note(f"Đã xoá khoá {LABEL.get(prov, prov)}.", "ok")
        return 0
    if action == "path":
        print(KEYS_PATH)
        return 0
    ui.note(f"hành động lạ: {action}", "warn")
    return 2
