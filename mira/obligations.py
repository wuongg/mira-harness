"""Check thoát 0 và tiêu chí được xác minh là hai việc khác nhau.

`check:` cũ vẫn chạy khi người dùng đã cấp lệnh, nhưng chỉ ghi check_passed.
Muốn criterion_verified thì lệnh phải chứng minh đúng câu tiêu chí và artifact
thuộc run hiện tại.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_PREFIX = "check:"
_EXIT = re.compile(r"\[mã thoát (\d+)\]")
_EXIT_ONLY = "chỉ mã thoát của lệnh này"
CRITERIA_SCHEMA = 1
_OBJECT_KEYS = {"schema", "id", "text", "cmd", "proves", "artifact"}


def _declared_check(criterion: str) -> str | None:
    text = (criterion or "").strip()
    if not text.lower().startswith(_PREFIX):
        return None
    cmd = text[len(_PREFIX):].strip()
    return cmd or None


def _string_item(text: str) -> dict:
    return {
        "schema": 0,
        "id": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "text": text,
        "cmd": _declared_check(text) or "",
        "proves": "",
        "artifact": "",
    }


def _object_item(raw: dict) -> tuple[dict | None, str]:
    extra = set(raw) - _OBJECT_KEYS
    if extra:
        return None, "tiêu chí có khóa lạ"
    if raw.get("schema") != CRITERIA_SCHEMA:
        return None, "schema tiêu chí không hỗ trợ"
    cid = raw.get("id")
    if not isinstance(cid, str) or not cid.strip():
        return None, "id tiêu chí trống"
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, "tiêu chí thiếu text"
    cmd = raw.get("cmd", "")
    proves = raw.get("proves", "")
    artifact = raw.get("artifact", "")
    for name, value in (("cmd", cmd), ("proves", proves), ("artifact", artifact)):
        if not isinstance(value, str):
            return None, f"tiêu chí có {name} không phải chuỗi"
    rel = artifact.replace("\\", "/").strip()
    if rel.startswith("/") or ".." in Path(rel).parts:
        return None, "artifact thoát khỏi gốc"
    return {
        "schema": CRITERIA_SCHEMA,
        "id": cid.strip(),
        "text": text.strip(),
        "cmd": cmd.strip(),
        "proves": proves.strip(),
        "artifact": rel,
    }, ""


def validate_criteria(items) -> tuple[list[dict] | None, str]:
    """Cùng một luật cho intake, brief, contract và obligations."""
    if not isinstance(items, list) or not items:
        return None, "brief thiếu acceptance_criteria"
    seen: set[str] = set()
    out: list[dict] = []
    for raw in items:
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return None, "tiêu chí chuỗi trống"
            item = _string_item(text)
        elif isinstance(raw, dict):
            item, why = _object_item(raw)
            if item is None:
                return None, why
        else:
            return None, "tiêu chí không phải chuỗi hoặc object"
        if item["id"] in seen:
            return None, "id tiêu chí trùng"
        seen.add(item["id"])
        out.append(item)
    return out, ""


def criterion_command(raw) -> str | None:
    parsed, _why = validate_criteria([raw])
    if not parsed:
        return None
    return parsed[0]["cmd"] or None


def _through_shell(cmd: str, root: Path) -> tuple[str, int | None, str]:
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
        return "checked", code, "lệnh check thoát 0"
    return "failed", code, f"lệnh check thoát {code}"


def _bound_artifact(root: Path, rel: str, run_id: str,
                    records: dict | None) -> dict | None:
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    rec = (records or {}).get(rel)
    if not isinstance(rec, dict) or rec.get("run_id") != run_id:
        return None
    path = (root / rel).resolve()
    base = root.resolve()
    if path != base and base not in path.parents:
        return None
    if not path.is_file():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != rec.get("sha256"):
        return None
    return {"path": rel, "sha256": digest, "run_id": run_id}


def judge_obligations(criteria: list, steps: list[dict] | None = None,
                      evidence: dict | None = None, *, cwd: Path | None = None,
                      granted: set[str] | None = None, run_id: str | None = None,
                      artifacts: dict | None = None) -> list[dict]:
    """steps và diff không phải proof. Artifact phải đúng hash và đúng run_id."""
    del steps, evidence
    allowed = set(granted or ())
    root = Path(cwd).resolve() if cwd is not None else None
    parsed, why = validate_criteria(criteria)
    if parsed is None:
        return [{
            "criterion": "",
            "criterion_id": "",
            "kind": "manual",
            "proves": "",
            "artifact": None,
            "check_passed": False,
            "criterion_verified": False,
            "state": "blocked",
            "reason": why,
            "ref": None,
        }]
    rows = []
    for item in parsed:
        cmd = item["cmd"] or None
        base = {
            "criterion": item["text"],
            "criterion_id": item["id"],
            "kind": "command" if cmd else "manual",
            "proves": item["proves"] or (_EXIT_ONLY if cmd else ""),
            "artifact": None,
            "check_passed": False,
            "criterion_verified": False,
        }
        if not cmd:
            rows.append({
                **base, "state": "needs_confirmation",
                "reason": "tiêu chí không kiểm tự động, cần xác nhận",
                "ref": None,
            })
            continue
        if cmd not in allowed:
            rows.append({
                **base, "state": "pending",
                "reason": "tiêu chí do model đề xuất — chưa được cấp quyền chạy",
                "ref": {"kind": "check", "criterion_id": item["id"], "cmd": cmd,
                        "via": "run_shell"},
            })
            continue
        if root is None or not root.is_dir():
            rows.append({
                **base, "state": "blocked",
                "reason": "không có thư mục gốc để đưa vào run_shell",
                "ref": {"kind": "check", "criterion_id": item["id"], "cmd": cmd,
                        "via": "run_shell"},
            })
            continue
        state, code, reason = _through_shell(cmd, root)
        passed = state == "checked"
        bound = None
        claim = item["proves"]
        if passed and claim and claim == item["text"] and item["artifact"] and run_id:
            bound = _bound_artifact(root, item["artifact"], run_id, artifacts)
        verified = bound is not None
        if verified:
            state = "verified"
            reason = "lệnh và artifact cùng run xác minh đúng câu tiêu chí"
        rows.append({
            **base,
            "state": state,
            "reason": reason,
            "proves": claim or _EXIT_ONLY,
            "artifact": bound,
            "check_passed": passed,
            "criterion_verified": verified,
            "ref": {"kind": "check", "criterion_id": item["id"], "cmd": cmd,
                    "via": "run_shell", "root": str(root), "exit": code},
        })
    return rows


def unproven(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not row.get("criterion_verified")]
