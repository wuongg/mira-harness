"""Giá model: --price-in, rồi file đóng gói, rồi env, rồi chặn."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_TABLE = re.compile(r'^\[models\."([^"]+)"\]\s*$')
_NUM = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
_OPTIONAL = ("cache_write", "cache_read")


def _finish(model: str, raw: dict[str, float], out: dict[str, dict]) -> None:
    if "in" not in raw or "out" not in raw:
        return
    row = {"in": raw["in"], "out": raw["out"]}
    for key in _OPTIONAL:
        row[key] = raw.get(key, 0.0)
    out[model] = row


def _parse_mini(text: str) -> dict[str, dict]:
    """Ngữ pháp hẹp: [models.\"tên\"], rồi in/out và hai khóa cache nếu có."""
    out: dict[str, dict] = {}
    model = ""
    raw: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        header = _TABLE.match(stripped)
        if header:
            if model:
                _finish(model, raw, out)
            model = header.group(1)
            raw = {}
            continue
        num = _NUM.match(stripped)
        if model and num and num.group(1) in ("in", "out", *_OPTIONAL):
            raw[num.group(1)] = float(num.group(2))
    if model:
        _finish(model, raw, out)
    return out


def _from_tomllib(text: str) -> dict[str, dict]:
    import tomllib
    data = tomllib.loads(text)
    models = data.get("models") or {}
    out: dict[str, dict] = {}
    for name, row in models.items():
        if not isinstance(row, dict):
            continue
        _finish(str(name), {k: float(row[k]) for k in row if k in ("in", "out", *_OPTIONAL)}, out)
    return out


def load_prices(text: str, *, force_mini: bool = False) -> dict[str, dict]:
    if not force_mini and sys.version_info >= (3, 11):
        return _from_tomllib(text)
    return _parse_mini(text)


def load_prices_file(path: Path) -> dict[str, dict]:
    file = Path(path)
    if not file.is_file():
        return {}
    return load_prices(file.read_text(encoding="utf-8"))


def env_name(model: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in model.upper())
    return "FROG_PRICE_" + cleaned


def legacy_env_name(model: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in model.upper())
    return "MIRA_PRICE_" + cleaned


def resolve_price(model: str, declared: tuple[float, float] | None = None,
                  environ: dict | None = None, table: dict | None = None) -> tuple[dict | None, str]:
    """Chuỗi cứng: cli, file, env, rồi không có giá."""
    if declared is not None:
        return {"in": float(declared[0]), "out": float(declared[1])}, "cli"
    env = os.environ if environ is None else environ
    if table is None:
        from . import config as C
        table = C.PRICES
    row = table.get(model)
    if row:
        return dict(row), "file"
    raw = env.get(env_name(model)) or env.get(legacy_env_name(model)) or env.get("FROG_PRICE")
    pair = _env_pair(raw)
    if pair is not None:
        return {"in": pair[0], "out": pair[1]}, "env"
    return None, ""


def _env_pair(raw: str | None) -> tuple[float, float] | None:
    """`vào,ra` là số. Chữ không phải số thì không có giá, không làm vỡ phiên."""
    if not raw:
        return None
    left, sep, right = str(raw).partition(",")
    if not sep or not left.strip() or not right.strip():
        return None
    try:
        return float(left), float(right)
    except ValueError:
        return None
