"""Chuyển model / nhà cung cấp khi lần gọi chính chết hoặc hết hạn mức.

Không đổi khóa, không bịa giá. Chỉ thử nhà đã có khóa. Tắt bằng FROG_NO_FAILOVER=1.
"""
from __future__ import annotations

import os
import re

from . import config as C

# Lỗi đáng thử chỗ khác. 401 cùng nhà thường là khóa sai — vẫn thử nhà khác.
_FAILOVER_RE = re.compile(
    r"HTTP 429|HTTP 5\d\d|HTTP 402|HTTP 404|HTTP 401|HTTP 403|"
    r"không kết nối|timed? ?out|empty turn|model_not_found|"
    r"can only afford|quota|rate.?limit|insufficient|overloaded|"
    r"không có model|phản hồi rỗng|AgentService",
    re.I,
)


def enabled() -> bool:
    return os.environ.get("FROG_NO_FAILOVER", "").strip().lower() not in ("1", "true", "yes")


def is_failoverable(detail: str | BaseException) -> bool:
    text = str(detail or "")
    if not text:
        return False
    if "chạm trần" in text and "gói thuê bao" in text:
        return True
    if "chưa có giá" in text:
        return True
    return bool(_FAILOVER_RE.search(text))


def _models_for(provider: str) -> list[str]:
    listed = list(C.FAILOVER_MODELS.get(provider) or [])
    if provider == "openrouter" and C.OPENROUTER_MODEL not in listed:
        listed = [C.OPENROUTER_MODEL] + listed
    return listed


def _provider_of_model(model: str, hint: str | None) -> str | None:
    from .providers import _class_for, ProviderError
    try:
        return _class_for(model, hint).name
    except ProviderError:
        return hint


def failover_chain(model: str, provider: str | None, *, role: str = "") -> list[tuple[str, str]]:
    """Danh sách (provider, model) theo thứ tự thử. Phần tử đầu là chỗ đang chọn."""
    from .keys import resolve

    primary_p = provider or _provider_of_model(model, None) or "openai"
    primary_m = model or (_models_for(primary_p) or [C.ROLE_MODEL.get("worker", "gpt-5.6-sol")])[0]
    out: list[tuple[str, str]] = [(primary_p, primary_m)]
    seen = {(primary_p, primary_m)}

    def add(pname: str, mname: str) -> None:
        key = (pname, mname)
        if key in seen or not mname:
            return
        if not resolve(pname)[0]:
            return
        seen.add(key)
        out.append(key)

    # Cùng nhà, model khác (ưu tiên map theo vai nếu có).
    slot = None
    if role:
        from .roles import POOL, SLOT
        kind = (POOL[role].kind if role in POOL else None)
        if kind:
            slot = SLOT.get(kind)
        if provider == "9router" or primary_p == "9router":
            prefer = C.NINE_ROUTER_ROLE_MODEL.get(slot or "") or C.NINE_ROUTER_ROLE_MODEL.get(
                "worker")
            if prefer:
                add(primary_p, prefer)
        elif slot and slot in C.ROLE_MODEL:
            add(primary_p, C.ROLE_MODEL[slot])
    for m in _models_for(primary_p):
        add(primary_p, m)

    # Nhà khác có khóa, model mặc định của nhà đó.
    for pname in C.FAILOVER_PROVIDERS:
        if pname == primary_p:
            continue
        for m in _models_for(pname):
            add(pname, m)
            break

    return out[: max(1, int(getattr(C, "FAILOVER_MAX", 3)))]
