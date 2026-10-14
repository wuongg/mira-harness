"""Tiêu chí check chỉ chạy khi người dùng đã cấp đúng lệnh, qua run_shell.

Lệnh do model ghi trong brief không được tự chạy. shell=False không phải cấp quyền.
Bản sao của run_shell không phải sandbox.
"""
from __future__ import annotations

import re
from pathlib import Path

_PREFIX = "check:"
_EXIT = re.compile(r"\[mã thoát (\d+)\]")


def _declared_check(criterion: str) -> str | None:
    text = (criterion or "").strip()
    if not text.lower().startswith(_PREFIX):
        return None
    cmd = text[len(_PREFIX):].strip()
    return cmd or None


def _through_shell(cmd: str, root: Path) -> tuple[str, int | None, str]:
    """Cùng cửa run_shell. Từ chối hoặc chặn thì không có mã thoát."""
    from .tools import Session

    def approve(tool: str, args: dict) -> bool:
        return tool == "run_shell" and str(args.get("cmd") or "") == cmd

    text = Session(root=root, mode="default", approve=approve).run_shell(cmd, timeout=30)
    if text.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN")):
        return "blocked", None, text.splitlines()[0]
    if text.startswith("LỖI:"):
        return "unproven", None, text.splitlines()[0]
    found = _EXIT.match(text)
    if not found:
        return "unproven", None, "run_shell không trả mã thoát"
    code = int(found.group(1))
    if code == 0:
        return "proven", code, "lệnh check thoát 0"
    return "failed", code, f"lệnh check thoát {code}"


def judge_obligations(criteria: list[str], steps: list[dict] | None = None,
                      evidence: dict | None = None, *, cwd: Path | None = None,
                      granted: set[str] | None = None) -> list[dict]:
    """steps và diff không phải proof. granted là lệnh người dùng đã đưa, không phải lời model."""
    del steps, evidence
    allowed = set(granted or ())
    root = Path(cwd).resolve() if cwd is not None else None
    rows = []
    for raw in criteria:
        text = (raw or "").strip()
        cmd = _declared_check(text)
        if cmd is None:
            rows.append({
                "criterion": text, "state": "unproven",
                "reason": "tiêu chí không khai lệnh check",
                "ref": None,
            })
            continue
        if cmd not in allowed:
            rows.append({
                "criterion": text, "state": "pending",
                "reason": "tiêu chí do model đề xuất — chưa được cấp quyền chạy",
                "ref": {"kind": "check", "cmd": cmd, "via": "run_shell"},
            })
            continue
        if root is None or not root.is_dir():
            rows.append({
                "criterion": text, "state": "blocked",
                "reason": "không có thư mục gốc để đưa vào run_shell",
                "ref": {"kind": "check", "cmd": cmd, "via": "run_shell"},
            })
            continue
        state, code, reason = _through_shell(cmd, root)
        rows.append({
            "criterion": text, "state": state, "reason": reason,
            "ref": {"kind": "check", "cmd": cmd, "via": "run_shell",
                    "root": str(root), "exit": code},
        })
    return rows


def unproven(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("state") != "proven"]
