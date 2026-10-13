"""Tiêu chí chỉ được chứng minh bằng lệnh check mà harness tự chạy.

Chép nguyên câu tiêu chí vào evidence, hoặc file đổi byte, không phải proof.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

_PREFIX = "check:"


def _declared_check(criterion: str) -> str | None:
    text = (criterion or "").strip()
    if not text.lower().startswith(_PREFIX):
        return None
    cmd = text[len(_PREFIX):].strip()
    return cmd or None


def _can_run(token: str) -> bool:
    return Path(token).is_file() or shutil.which(token) is not None


def _argv(cmd: str) -> list[str]:
    """POSIX trước. Trên Windows, đường dẫn có '\\' chỉ sống ở chế độ non-POSIX."""
    argv = shlex.split(cmd, posix=True)
    if os.name != "nt" or not argv or _can_run(argv[0]):
        return argv
    alt = [_strip_quotes(token) for token in shlex.split(cmd, posix=False)]
    if alt and _can_run(alt[0]):
        return alt
    return argv


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _run_check(cmd: str, cwd: Path) -> tuple[int | None, str]:
    argv = _argv(cmd)
    if not argv:
        return None, "lệnh check rỗng"
    from .tools import _shell_env
    try:
        proc = subprocess.run(
            argv, shell=False, cwd=str(cwd), timeout=30,
            capture_output=True, text=True, env=_shell_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, type(exc).__name__
    return proc.returncode, ""


def judge_obligations(criteria: list[str], steps: list[dict] | None = None,
                      evidence: dict | None = None, *, cwd: Path | None = None) -> list[dict]:
    """steps và diff file không được dùng làm proof. cwd là nơi chạy check."""
    del steps, evidence
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
        if root is None or not root.is_dir():
            rows.append({
                "criterion": text, "state": "unproven",
                "reason": "không có thư mục để chạy check",
                "ref": {"kind": "check", "cmd": cmd},
            })
            continue
        code, why = _run_check(cmd, root)
        ref = {"kind": "check", "cmd": cmd, "cwd": str(root), "exit": code}
        if code == 0:
            rows.append({
                "criterion": text, "state": "proven",
                "reason": "lệnh check thoát 0",
                "ref": ref,
            })
        elif code is None:
            rows.append({
                "criterion": text, "state": "unproven",
                "reason": f"không chạy được check: {why}",
                "ref": ref,
            })
        else:
            rows.append({
                "criterion": text, "state": "failed",
                "reason": f"lệnh check thoát {code}",
                "ref": ref,
            })
    return rows


def unproven(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("state") != "proven"]
