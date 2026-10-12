"""Bộ chấm vài việc local. Mỗi việc đi qua vòng lặp agent, rồi mới kiểm tra.

Model giả chỉ trả các khối công cụ đã ghi trong task. Không dùng lane_usage.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .agent import run_turn
from .tools import Session


class _Scripted:
    """Trả lần lượt các câu trả lời, kèm usage cố định."""

    name = "script"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)

    def available(self) -> bool:
        return True

    def call(self, _system: str, _user: str) -> tuple[str, dict]:
        text = self.replies.pop(0) if self.replies else "xong"
        return text, {"in": 150, "out": 30}


def task_root() -> Path:
    here = Path(__file__).resolve().parents[1] / "eval" / "tasks"
    if here.is_dir():
        return here
    return Path.cwd() / "eval" / "tasks"


def _check(root: Path, spec: dict) -> bool:
    kind = spec.get("type")
    path = root / spec.get("path", "")
    if kind == "contains":
        if not path.is_file():
            return False
        return spec.get("text", "") in path.read_text(encoding="utf-8")
    if kind == "absent":
        return not path.exists()
    raise ValueError(f"không có kiểu kiểm tra {kind}")


def run_one(folder: Path) -> dict:
    spec = json.loads((folder / "task.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in (spec.get("files") or {}).items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        session = Session(root=root, mode=spec.get("mode") or "acceptEdits",
                          approve=lambda _t, _a: True)
        session.checker = lambda: _check(root, spec["check"])
        res = run_turn(task=spec.get("prompt") or folder.name, session=session,
                       model="sonnet-5.5", protocol="text", no_stream=True,
                       provider=_Scripted(spec.get("replies") or []),
                       on_text=lambda _s: None)
        layer = "governance"
        for row in reversed(session.trace):
            if row.get("kind") == "stop":
                layer = row.get("layer") or layer
                break
        return {
            "name": folder.name,
            "ok": bool(res.get("status") == "ok" and _check(root, spec["check"])),
            "turns": res.get("turns") or 0,
            "costUsd": res.get("costUsd") or 0.0,
            "layer": layer,
        }


def run_eval(root: Path | None = None) -> int:
    base = root or task_root()
    folders = sorted(p for p in base.iterdir() if (p / "task.json").is_file()) if base.is_dir() else []
    if not folders:
        print("không có việc trong eval/tasks")
        return 2
    rows = [run_one(folder) for folder in folders]
    passed = sum(1 for row in rows if row["ok"])
    turns = sum(row["turns"] for row in rows)
    cost = sum(row["costUsd"] for row in rows)
    for row in rows:
        mark = "qua" if row["ok"] else "fail"
        print(f"{row['name']}\t{mark}\t{row['turns']} vòng\t${row['costUsd']:.4f}\t{row['layer']}")
    print(f"{passed}/{len(rows)} qua\t{turns} vòng\t${cost:.4f}")
    return 0 if passed == len(rows) else 1
