"""Phiếu giao việc rồi bàn giao. Dùng intake và validator sẵn có.

Duyệt phiếu không cấp quyền chạy lệnh. Mỗi lệnh phải được nêu đúng chuỗi.
Hash phát hiện phiếu hoặc state đã đổi. Hash không chống người sửa trực tiếp file.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .intake import LABEL, brief_hash, code_proposed_commands, run_intake, validate_brief, workspace_files
from .obligations import criterion_commands, judge_obligations, validate_criteria

_AUTO = {"contains", "json_keys", "shape", "behavior"}
_RUN_ID = re.compile(r"^[0-9a-f]{12}$")
_PHASES = {
    "awaiting_approval", "awaiting_grant", "ready", "executing",
    "awaiting_confirmation", "failed", "delivered",
}
_PHASE_LABEL = {
    "awaiting_approval": "chờ duyệt",
    "awaiting_grant": "chờ quyền",
    "ready": "chờ chạy",
    "executing": "đang thực thi",
    "awaiting_confirmation": "chờ xác nhận",
    "failed": "thất bại",
    "delivered": "đã bàn giao",
}
_STATE_FIELDS = (
    "id", "request", "brief", "brief_hash", "approved", "approved_hash",
    "grants", "confirmations", "previous",
    "phase", "attempt", "history", "ledger", "obligations", "hold",
    "staging", "promoted", "want_deliver", "manifest",
)
_SAVE_LOCK = threading.Lock()
_LOCK_HELD = threading.local()


class HandoffError(Exception):
    """Lỗi phiếu có câu tiếng Việt. CLI in câu này, không in traceback."""


def _check_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise HandoffError("run id không hợp lệ")


def _dir(root: Path, run_id: str) -> Path:
    _check_run_id(run_id)
    root = Path(root).resolve()
    new_base = (root / ".frog" / "runs").resolve()
    old_base = (root / ".mira" / "runs").resolve()
    new_path = (new_base / run_id).resolve()
    old_path = (old_base / run_id).resolve()
    if (old_path / "handoff.json").is_file() and not (new_path / "handoff.json").is_file():
        base, path = old_base, old_path
    else:
        base, path = new_base, new_path
    if path != base and base not in path.parents:
        raise HandoffError("run thoát khỏi thư mục")
    return path


def _state_hash(state: dict) -> str:
    body = {key: state.get(key) for key in _STATE_FIELDS}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _confirm_ok(item) -> bool:
    return (isinstance(item, dict)
            and set(item) == {"criterion_id", "artifact", "sha256", "brief_hash", "run_id"}
            and all(isinstance(item[key], str) and item[key] for key in item))


def _grant_ok(item) -> bool:
    return (isinstance(item, dict) and set(item) == {"cmd", "brief_hash"}
            and isinstance(item["cmd"], str) and isinstance(item["brief_hash"], str))


def _history_ok(item) -> bool:
    return (isinstance(item, dict)
            and set(item) == {"attempt", "phase", "cost_usd"}
            and isinstance(item["attempt"], int) and item["phase"] in _PHASES
            and isinstance(item["cost_usd"], (int, float)))


_EXTRAS = ("autonomy", "repair", "direct_from", "normalization", "pending_files")
_AUTONOMY = {"watch", "walk-away", "direct"}
_REPAIR_MAX = 2


def _repair_ok(item) -> bool:
    return (isinstance(item, dict)
            and set(item) == {"criterion_id", "delta", "evidence", "attempt"}
            and isinstance(item["criterion_id"], str) and isinstance(item["delta"], str)
            and isinstance(item["evidence"], str) and isinstance(item["attempt"], int))


def _empty_ledger() -> dict:
    return {
        "rows": [], "total_usd": 0.0, "total_in": 0, "total_out": 0,
        "subagent_runs": 0, "reserved": 0.0, "uncertain_usd": 0.0,
        "uncertain": [], "requests": [],
    }


def _manifest_ok(blob) -> bool:
    if blob is None:
        return True
    if not isinstance(blob, dict) or set(blob) != {"run_id", "attempt", "brief_hash", "files"}:
        return False
    if not isinstance(blob["run_id"], str) or not isinstance(blob["attempt"], int):
        return False
    if not isinstance(blob["brief_hash"], str) or not isinstance(blob["files"], list):
        return False
    for item in blob["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            return False
        if not isinstance(item["path"], str) or not isinstance(item["sha256"], str):
            return False
        if not item["path"] or not item["sha256"]:
            return False
        parts = Path(item["path"]).parts
        if not parts or ".." in parts or Path(item["path"]).is_absolute():
            return False
    return True


def _ledger_shape(blob) -> bool:
    return (isinstance(blob, dict) and isinstance(blob.get("rows"), list)
            and isinstance(blob.get("total_usd"), (int, float))
            and isinstance(blob.get("requests"), list))


def _ledger_blob(ledger) -> dict:
    return {
        "rows": list(ledger.rows),
        "total_usd": round(ledger.total_usd, 6),
        "total_in": ledger.total_in,
        "total_out": ledger.total_out,
        "subagent_runs": ledger.subagent_runs,
        "reserved": round(ledger.reserved, 6),
        "uncertain_usd": round(ledger.uncertain_usd, 6),
        "uncertain": list(ledger.uncertain),
        "requests": list(ledger.requests),
    }


def _read_text(path: Path) -> str:
    last: Exception | None = None
    for _ in range(30):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError as exc:
            last = exc
            time.sleep(0.05)
    raise HandoffError("run đang được thao tác") from last


def _load(root: Path, run_id: str) -> dict:
    _check_run_id(run_id)
    path = _dir(root, run_id) / "handoff.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    try:
        state = json.loads(_read_text(path))
    except json.JSONDecodeError:
        raise HandoffError("state hỏng: JSON cụt") from None
    if not isinstance(state, dict):
        raise HandoffError("state hỏng: sai schema")
    unknown = set(state) - set(_STATE_FIELDS) - {"state_hash"} - set(_EXTRAS)
    if unknown or not set(_STATE_FIELDS) <= set(state):
        raise HandoffError("state hỏng: sai schema")
    extra = {key: state.pop(key) for key in _EXTRAS if key in state}
    if state.get("id") != run_id or not isinstance(state.get("request"), str):
        raise HandoffError("state hỏng: sai schema")
    if not isinstance(state.get("approved"), bool) or not isinstance(state.get("approved_hash"), str):
        raise HandoffError("state hỏng: sai schema")
    previous = state.get("previous")
    if previous is not None and (not isinstance(previous, str) or _RUN_ID.fullmatch(previous) is None):
        raise HandoffError("state hỏng: previous không hợp lệ")
    grants = state.get("grants")
    if not isinstance(grants, list) or not all(_grant_ok(item) for item in grants):
        raise HandoffError("state hỏng: grant sai schema")
    confirmations = state.get("confirmations")
    if not isinstance(confirmations, list) or not all(_confirm_ok(item) for item in confirmations):
        raise HandoffError("state hỏng: xác nhận sai schema")
    if state.get("phase") not in _PHASES or not isinstance(state.get("attempt"), int) or state["attempt"] < 1:
        raise HandoffError("state hỏng: sai schema")
    history = state.get("history")
    if not isinstance(history, list) or not all(_history_ok(item) for item in history):
        raise HandoffError("state hỏng: sai schema")
    if not _ledger_shape(state.get("ledger")) or not isinstance(state.get("obligations"), list):
        raise HandoffError("state hỏng: sai schema")
    if not isinstance(state.get("hold"), str) or not isinstance(state.get("staging"), str):
        raise HandoffError("state hỏng: sai schema")
    if not isinstance(state.get("promoted"), bool) or not isinstance(state.get("want_deliver"), bool):
        raise HandoffError("state hỏng: sai schema")
    if not _manifest_ok(state.get("manifest")):
        raise HandoffError("state hỏng: manifest sai schema")
    ok, why = validate_brief(state.get("brief"))
    if not ok:
        raise HandoffError(f"state hỏng: {why}")
    if state.get("brief_hash") != brief_hash(state["brief"]):
        raise HandoffError("phiếu không khớp hash đã lưu")
    if state.get("state_hash") != _state_hash(state):
        raise HandoffError("trạng thái không khớp hash")
    choice = extra.get("autonomy")
    state["autonomy"] = choice if choice in _AUTONOMY else "watch"
    repair = extra.get("repair")
    if repair is None:
        repair = []
    if not isinstance(repair, list) or not all(_repair_ok(item) for item in repair):
        raise HandoffError("state hỏng: sai schema")
    state["repair"] = repair
    origin = extra.get("direct_from")
    if origin is None:
        origin = ""
    if not isinstance(origin, str):
        raise HandoffError("state hỏng: sai schema")
    state["direct_from"] = origin
    filled = extra.get("normalization")
    if filled is None:
        filled = []
    if not isinstance(filled, list) or not all(isinstance(item, str) for item in filled):
        raise HandoffError("state hỏng: sai schema")
    state["normalization"] = filled
    pending = extra.get("pending_files")
    if pending is None:
        pending = ""
    if not isinstance(pending, str):
        raise HandoffError("state hỏng: sai schema")
    state["pending_files"] = pending
    return state


def _save(root: Path, state: dict) -> None:
    """Cùng cách với checkpoint: file tạm rồi os.replace."""
    _check_run_id(state["id"])
    ok, why = validate_brief(state["brief"])
    if not ok:
        raise HandoffError(why)
    state["brief_hash"] = brief_hash(state["brief"])
    state["state_hash"] = _state_hash(state)
    folder = _dir(root, state["id"])
    dest = folder / "handoff.json"
    with _SAVE_LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        for _ in range(20):
            try:
                os.replace(tmp, dest)
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            raise HandoffError("run đang được thao tác")


def _argv(args: list[str]) -> str:
    argv = [sys.executable, "-m", "frog", "giao", *args]
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def classify(raw) -> str:
    parsed, _why = validate_criteria([raw])
    if not parsed:
        return "human"
    kind = (parsed[0].get("validator") or {}).get("kind")
    return "auto" if kind in _AUTO else "human"


def grant_commands(brief: dict) -> list[str]:
    found: list[str] = []
    for item in brief.get("acceptance_criteria") or []:
        for cmd in criterion_commands(item):
            if cmd not in found:
                found.append(cmd)
    return found


def preview(brief: dict, run_id: str, filled: list[str] | None = None) -> str:
    lines = [
        f"Run: {run_id}",
        f"Mục tiêu: {brief.get('goal') or ''}",
        "Bàn giao:",
    ]
    for item in brief.get("deliverables") or []:
        lines.append(f"- {item}")
    if not brief.get("deliverables"):
        lines.append("- (không có)")
    lines.append("Ràng buộc:")
    for item in brief.get("constraints") or []:
        lines.append(f"- {item}")
    if not brief.get("constraints"):
        lines.append("- (không có)")
    lines.append("Tiêu chí:")
    for item in brief.get("acceptance_criteria") or []:
        parsed, _why = validate_criteria([item])
        if not parsed:
            lines.append(f"- [cần người xác nhận] {item}")
            continue
        row = parsed[0]
        label = "tự động" if classify(item) == "auto" else "cần người xác nhận"
        lines.append(f"- [{label}] {row['id']}: {row['text']}")
    lines.append("Lệnh cần cấp quyền:")
    commands = grant_commands(brief)
    if not commands:
        lines.append("- (không có lệnh)")
    for cmd in commands:
        lines.append(f"- {cmd}")
    lines.append("Duyệt phiếu không cấp các lệnh này.")
    for item in brief.get("assumptions") or []:
        if isinstance(item, str) and item.startswith(LABEL):
            lines.append(item)
    if filled:
        lines.append("đã điền thay: " + ", ".join(filled))
    lines.append("Hash phát hiện phiếu đổi, không chống người sửa trực tiếp file.")
    if commands:
        grant_bits = ["--run", run_id]
        for cmd in commands:
            grant_bits.extend(["--grant", cmd])
        lines.append("Bước tiếp: " + _argv(grant_bits))
    else:
        lines.append("Bước tiếp: " + _argv(["--run", run_id]))
    for item in brief.get("acceptance_criteria") or []:
        if classify(item) != "human":
            continue
        parsed, _why = validate_criteria([item])
        if not parsed:
            continue
        lines.append("Xác nhận tay: " + _argv(
            ["--run", run_id, "--confirm", parsed[0]["id"], "--artifact", "<tệp>"]))
    return "\n".join(lines)


def open_run(root: Path, request: str, brief: dict, previous: str | None = None,
             ledger: dict | None = None) -> dict:
    ok, why = validate_brief(brief)
    if not ok:
        raise HandoffError(why)
    if previous is not None:
        _check_run_id(previous)
    state = {
        "id": uuid.uuid4().hex[:12],
        "request": request,
        "brief": brief,
        "brief_hash": brief_hash(brief),
        "approved": False,
        "approved_hash": "",
        "grants": [],
        "confirmations": [],
        "previous": previous,
        "phase": "awaiting_approval",
        "attempt": 1,
        "history": [],
        "ledger": ledger if ledger is not None else _empty_ledger(),
        "obligations": [],
        "hold": "",
        "staging": "",
        "promoted": False,
        "want_deliver": False,
        "manifest": None,
    }
    _save(root, state)
    return state


def approve(root: Path, run_id: str) -> dict:
    state = _load(root, run_id)
    state["approved"] = True
    state["approved_hash"] = state["brief_hash"]
    for cmd in code_proposed_commands(state["brief"]):
        row = {"cmd": cmd, "brief_hash": state["brief_hash"]}
        if row not in state["grants"]:
            state["grants"].append(row)
    if state["phase"] in ("awaiting_approval", "awaiting_grant", "ready"):
        granted = {item["cmd"] for item in state["grants"] if item.get("brief_hash") == state["brief_hash"]}
        missing = [cmd for cmd in grant_commands(state["brief"]) if cmd not in granted]
        state["phase"] = "awaiting_grant" if missing else "ready"
    _save(root, state)
    return state


def _approval_current(state: dict) -> bool:
    return bool(state.get("approved")) and state.get("approved_hash") == state.get("brief_hash")


def remember_grant(root: Path, run_id: str, cmd: str) -> dict:
    state = _load(root, run_id)
    if not _approval_current(state):
        raise HandoffError("chưa duyệt phiếu này")
    if cmd not in grant_commands(state["brief"]):
        raise HandoffError("lệnh không thuộc phiếu đã duyệt")
    row = {"cmd": cmd, "brief_hash": state["brief_hash"]}
    if row not in state["grants"]:
        state["grants"].append(row)
    _save(root, state)
    return state


def _find_artifact(root: Path, rel: str, staging: str = "") -> Path | None:
    """File của đúng run. Staging đang chờ thì không lấy file cũ ở cây nguồn."""
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or not rel.strip():
        raise HandoffError("artifact không hợp lệ")
    base = Path(root).resolve()
    if staging:
        folder = Path(staging).resolve()
        stage_roots = [(base / name / "staging").resolve() for name in (".frog", ".mira")]
        if not any(folder == root or root in folder.parents for root in stage_roots):
            raise HandoffError("staging thoát khỏi gốc")
        cand = (folder / rel).resolve()
        if cand != folder and folder not in cand.parents:
            return None
        return cand if cand.is_file() else None
    cand = (base / rel).resolve()
    if cand != base and base not in cand.parents:
        return None
    if not cand.is_file():
        return None
    stage_roots = [(base / name / "staging").resolve() for name in (".frog", ".mira")]
    if any(cand == root or root in cand.parents for root in stage_roots):
        return None
    return cand


def _artifact_file(root: Path, state: dict, rel: str) -> Path | None:
    pending = bool(state.get("staging")) and not state.get("promoted")
    return _find_artifact(root, rel, state.get("staging") or "" if pending else "")


def confirm(root: Path, run_id: str, criterion_id: str, artifact: str) -> dict:
    """Chỉ CLI người dùng gọi được. Model không có cửa này."""
    state = _load(root, run_id)
    if not _approval_current(state):
        raise HandoffError("chưa duyệt phiếu này")
    parsed, _why = validate_criteria(state["brief"]["acceptance_criteria"])
    item = next((row for row in parsed or [] if row["id"] == criterion_id), None)
    if item is None:
        raise HandoffError("không có tiêu chí")
    if item.get("validator"):
        raise HandoffError("tiêu chí này kiểm tự động")
    found = _artifact_file(root, state, artifact)
    if found is None:
        raise HandoffError("không có artifact")
    digest = hashlib.sha256(found.read_bytes()).hexdigest()
    row = {"criterion_id": criterion_id, "artifact": artifact.replace("\\", "/"),
           "sha256": digest, "brief_hash": state["brief_hash"], "run_id": state["id"]}
    state["confirmations"] = [item for item in state["confirmations"]
                              if item["criterion_id"] != criterion_id]
    state["confirmations"].append(row)
    _save(root, state)
    return state


def apply_confirmations(state: dict, rows: list[dict], root: Path) -> list[dict]:
    for row in rows:
        if row.get("criterion_verified"):
            continue
        match = next((item for item in state.get("confirmations") or []
                      if item["criterion_id"] == row.get("criterion_id")
                      and item["brief_hash"] == state["brief_hash"]
                      and item.get("run_id") == state["id"]), None)
        if match is None:
            continue
        found = _artifact_file(root, state, match["artifact"])
        digest = hashlib.sha256(found.read_bytes()).hexdigest() if found else ""
        row["criterion_verified"] = False
        if digest != match["sha256"]:
            row["state"] = "needs_confirmation"
            row["reason"] = "artifact đã đổi, xác nhận cũ hết hiệu lực"
            row["does_not_prove"] = row["reason"]
            continue
        row["state"] = "user_confirmed"
        row["reason"] = "người dùng xác nhận"
        row["proves"] = ""
        row["does_not_prove"] = "không phải kiểm chứng tự động"
    # I5: nấc direct là chính sách code. Model không được chốt tiêu chí thủ công.
    if state.get("autonomy") == "direct" and state.get("direct_from"):
        known = _direct_settled_ids(root, state["direct_from"])
        for row in rows:
            if row.get("criterion_verified") or row.get("kind") != "manual":
                continue
            if row.get("state") == "needs_confirmation" and row.get("criterion_id") in known:
                row["state"] = "direct"
                row["reason"] = "chạy trực tiếp"
                row["does_not_prove"] = "không phải validator của lượt này"
    return rows


def _settled(row: dict) -> bool:
    return bool(row.get("criterion_verified")) or row.get("state") in (
        "user_confirmed", "direct", "verifier_accepted")


def _mark_verifier_delivery(rows: list[dict], autonomy: str, res: dict) -> None:
    from .team import tree_hash
    staging = str(res.get("staging") or "")
    actual = tree_hash(Path(staging)) if staging and Path(staging).is_dir() else ""
    if not verifier_delivery(
            rows, autonomy, str(res.get("verifier_verdict") or ""),
            str(res.get("staged_hash") or ""), actual):
        return
    for row in rows:
        if row.get("kind") == "manual" and not _settled(row):
            row["state"] = "verifier_accepted"
            row["reason"] = "bàn giao dựa trên verifier — chưa xác nhận tay"
            row["does_not_prove"] = "không phải xác nhận tay"
            row["staged_hash"] = actual
            row["checked_on"] = "staged"


def verifier_delivery(rows: list[dict], autonomy: str, verdict: str,
                      expected_hash: str, actual_hash: str) -> bool:
    """Bàn giao chỉ dựa trên verifier là cấm."""
    del rows, autonomy, verdict, expected_hash, actual_hash
    return False


def _machine_text(text: str, names: list[str]) -> bool:
    if any(name and name in text for name in names):
        return True
    if "==" in text or "bằng" in text:
        return True
    return bool(re.search(r"\b[\w.]+\s*\(", text))


def bare_deliverable(brief: dict) -> bool:
    """Deliverable hoặc tiêu chí kiểm được chưa có validator thì chưa được promote."""
    names = [item.replace("\\", "/").strip()
             for item in brief.get("deliverables") or []
             if isinstance(item, str) and item.strip()]
    parsed, _why = validate_criteria(brief.get("acceptance_criteria") or [])
    if not parsed:
        return bool(names)
    for item in parsed:
        if item.get("validator"):
            continue
        if item.get("cmd") or _machine_text(item.get("text") or "", names):
            return True
    if not names:
        return False
    covered: set[str] = set()
    for item in parsed:
        validator = item.get("validator") or {}
        if not validator:
            continue
        path = str(validator.get("path") or "")
        if path:
            covered.add(path)
        if validator.get("kind") == "behavior":
            cmd = str(validator.get("cmd") or "")
            for name in names:
                stem = Path(name).stem
                if stem and re.search(r"\b" + re.escape(stem) + r"\b", cmd):
                    covered.add(name)
    return any(name not in covered for name in names)


def _delivery(rows: list[dict]) -> tuple[str, int]:
    if not rows or not all(_settled(row) for row in rows):
        return "bàn giao: chưa", 4
    if any(row.get("state") == "verifier_accepted" for row in rows):
        return "bàn giao dựa trên verifier — chưa xác nhận tay", 0
    if any(row.get("state") == "user_confirmed" for row in rows):
        return "bàn giao: người dùng xác nhận", 0
    return "bàn giao: đủ", 0


def request_change(old: str, new: str, old_id: str) -> str:
    diff = "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"run {old_id}", tofile="yêu cầu mới"))
    if not diff:
        diff = "(không có khác biệt dòng)\n"
    return (
        "Yêu cầu đã đổi.\n"
        f"Run cũ: {old_id}\n"
        "Khác biệt:\n"
        f"{diff}"
        "Tạo run mới. Duyệt và lệnh của run cũ không được dùng lại.\n"
        "Bước tiếp: " + _argv([new, "--previous", old_id])
    )


def _active_grants(state: dict) -> set[str]:
    allowed = set(grant_commands(state["brief"]))
    bound = state["brief_hash"]
    return {item["cmd"] for item in state["grants"]
            if item["brief_hash"] == bound and item["cmd"] in allowed}


def _blocked(state: dict) -> tuple[list[dict], str, int] | None:
    if _approval_current(state):
        return None
    text = ("duyệt cũ hết hiệu lực vì phiếu đã đổi" if state.get("approved")
            else "chưa duyệt phiếu — không chạy")
    return [], text, 8


def _write_table(root: Path, run_id: str, body: str) -> None:
    (_dir(root, run_id) / "handoff.md").write_text(body, encoding="utf-8")


def check_only(root: Path, run_id: str) -> tuple[list[dict], str, int]:
    """Chỉ đọc file và chạy validator. Không phải hoàn thành nhiệm vụ."""
    state = _load(root, run_id)
    refused = _blocked(state)
    if refused:
        return refused
    rows = apply_confirmations(state, judge_obligations(
        list(state["brief"]["acceptance_criteria"]),
        cwd=root, granted=_active_grants(state), run_id=run_id,
        brief_hash=state["brief_hash"]), root)
    passed = bool(rows) and all(row.get("criterion_verified") for row in rows)
    status = ("kiểm file: đạt — chưa phải hoàn thành nhiệm vụ" if passed
              else "kiểm file: chưa — chưa phải hoàn thành nhiệm vụ")
    body = render_table(state["request"], rows) + "\n" + status
    _write_table(root, run_id, body)
    return rows, body, 4


def _run_folders(root: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for name in (".frog", ".mira"):
        base = root / name / "runs"
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.name in seen or not (child / "handoff.json").is_file():
                continue
            seen.add(child.name)
            found.append(child)
    return found


def _load_any(root: Path, run_id: str) -> dict | None:
    try:
        return _load(root, run_id)
    except (OSError, HandoffError, FileNotFoundError):
        return None


def _criterion_ids(brief: dict) -> tuple[str, ...]:
    rows, _why = validate_criteria(brief.get("acceptance_criteria"))
    if not rows:
        return tuple()
    return tuple(sorted(row["id"] for row in rows))


def _direct_settled_ids(root: Path, run_id: str) -> set[str]:
    prior = _load_any(root, run_id)
    if prior is None or prior.get("phase") != "delivered":
        return set()
    return {
        row.get("criterion_id") for row in prior.get("obligations") or []
        if row.get("criterion_verified") or row.get("state") in ("user_confirmed", "direct")
    }


def _latest_verified(root: Path, brief: dict, exclude: str) -> str:
    """Run delivered gần nhất cùng bộ id tiêu chí. Không hỏi model."""
    kind = _criterion_ids(brief)
    if not kind:
        return ""
    found = ""
    found_at = -1.0
    for folder in _run_folders(root):
        if folder.name == exclude:
            continue
        state = _load_any(root, folder.name)
        if state is None or state.get("phase") != "delivered":
            continue
        if _criterion_ids(state.get("brief") or {}) != kind:
            continue
        if set(kind) - _direct_settled_ids(root, state["id"]):
            continue
        stamp = (folder / "handoff.json").stat().st_mtime
        if stamp >= found_at:
            found_at = stamp
            found = state["id"]
    return found


def apply_autonomy(root: Path, run_id: str, choice: str | None) -> tuple[dict, str]:
    """Người chọn nấc. Code hạ direct khi chưa có lịch sử verified cùng loại."""
    state = _load(root, run_id)
    if choice not in _AUTONOMY:
        choice = state.get("autonomy") or "watch"
    note = ""
    if choice == "direct":
        prior = _latest_verified(root, state["brief"], run_id)
        if not prior:
            choice = "walk-away"
            state["direct_from"] = ""
            note = "không chạy trực tiếp — chưa có lịch sử verified cùng loại"
        else:
            state["direct_from"] = prior
    else:
        state["direct_from"] = ""
    state["autonomy"] = choice
    _save(root, state)
    return state, note


def _repair_targets(rows: list[dict]) -> list[dict]:
    notes = []
    for row in rows or []:
        if row.get("kind") in (None, "manual"):
            continue
        if row.get("criterion_verified") or row.get("state") not in ("failed", "unverified"):
            continue
        notes.append({
            "criterion_id": str(row.get("criterion_id") or ""),
            "delta": str(row.get("reason") or row.get("does_not_prove") or ""),
            "evidence": str(row.get("evidence") or row.get("proves") or ""),
        })
    return notes


def _feedback_block(notes: list[dict]) -> str:
    lines = ["PHẢN HỒI VALIDATOR"]
    for note in notes:
        lines.append(f"- criterion_id: {note['criterion_id']}")
        lines.append(f"  lệch: {note['delta']}")
        lines.append(f"  evidence: {note['evidence']}")
    return "\n".join(lines)


def _exact_failures(rows: list[dict]) -> str:
    lines = []
    for note in _repair_targets(rows):
        lines.append(
            f"sai: {note['criterion_id']} | lệch: {note['delta']} | evidence: {note['evidence']}"
        )
    return "\n".join(lines)


def _annotate(state: dict, rows: list[dict], body: str) -> str:
    extra = []
    if state.get("autonomy") == "direct" and state.get("direct_from"):
        extra.append("chạy trực tiếp")
    if state.get("phase") == "failed" or state.get("hold") == "stopped_budget":
        failed = _exact_failures(rows)
        if failed:
            extra.append(failed)
    if state.get("hold") == "stopped_budget":
        extra.append("stopped_budget")
    if not extra:
        return body
    return body + "\n" + "\n".join(extra)


def _phase_line(state: dict) -> str:
    return "vòng đời: " + _PHASE_LABEL[state["phase"]]


def _cost_line(state: dict) -> str:
    usd = float(state["ledger"].get("total_usd") or 0)
    return f"chi phí tích lũy: ${usd:.6f}"


def _make_plan(state: dict, price):
    from . import config as C
    from .team import ROLES_BY_LANE, build_plan
    plan = build_plan(
        state["request"], surface="write_sandbox", labels=["internal"],
        records=50, dollars=0.0, reversibility="C1", output_type="free_string")
    if plan.lane < 1:
        plan.lane = 1
        plan.roles = list(ROLES_BY_LANE[1])
        plan.cap_usd = C.BUDGET[1]["cap"]
    plan.brief = state["brief"]
    plan.brief_hash = state["brief_hash"]
    plan.criteria_origin = "user"
    plan.require_evidence = True
    plan.granted_cmds = _active_grants(state)
    plan.stage_worker = True
    plan.declared_price = price
    return plan


def _view(root: Path, state: dict) -> tuple[list[dict], str, int]:
    path = _dir(root, state["id"]) / "handoff.md"
    saved = path.read_text(encoding="utf-8") if path.is_file() else ""
    code = 0 if state["phase"] == "delivered" else (4 if state["phase"] == "awaiting_confirmation" else 3)
    body = "\n".join(part for part in (
        saved, _phase_line(state), _cost_line(state), "không gọi lại") if part)
    return list(state.get("obligations") or []), body, code


def begin_retry(root: Path, run_id: str) -> dict:
    """Attempt mới trên cùng sổ cái. Không cấp ngân sách mới."""
    state = _load(root, run_id)
    if state["phase"] not in ("delivered", "failed"):
        raise HandoffError("chỉ chạy lại run đã kết thúc")
    state["history"].append({
        "attempt": state["attempt"],
        "phase": state["phase"],
        "cost_usd": float(state["ledger"].get("total_usd") or 0),
    })
    state["attempt"] += 1
    state["phase"] = "ready"
    state["obligations"] = []
    state["hold"] = ""
    state["confirmations"] = []
    state["staging"] = ""
    state["promoted"] = False
    state["want_deliver"] = False
    state["manifest"] = None
    _save(root, state)
    return state


def _acquire_run(root: Path, run_id: str):
    """Một tiến trình giữ lock. Cùng tiến trình gọi lồng nhau thì không xin lại."""
    depth = getattr(_LOCK_HELD, "depth", 0)
    if depth:
        _LOCK_HELD.depth = depth + 1
        return _LOCK_HELD.token
    token = _lock_os(root, run_id)
    _LOCK_HELD.depth = 1
    _LOCK_HELD.token = token
    return token


def _release_run(token) -> None:
    depth = getattr(_LOCK_HELD, "depth", 0)
    if depth > 1:
        _LOCK_HELD.depth = depth - 1
        return
    _LOCK_HELD.depth = 0
    _LOCK_HELD.token = None
    _unlock_os(token)


def _lock_os(root: Path, run_id: str):
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, "Local\\frog-giao-" + run_id)
        if not handle:
            raise HandoffError("run đang được thao tác")
        waited = kernel.WaitForSingleObject(handle, 30000)
        if waited not in (0, 0x00000080):
            kernel.CloseHandle(handle)
            raise HandoffError("run đang được thao tác")
        return handle
    import fcntl
    path = _dir(root, run_id) / "run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.time() + 30
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if time.time() > deadline:
                    raise HandoffError("run đang được thao tác")
                time.sleep(0.05)
    except Exception:
        os.close(fd)
        raise


def _unlock_os(token) -> None:
    if token is None:
        return
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.ReleaseMutex(token)
        kernel.CloseHandle(token)
        return
    import fcntl
    try:
        fcntl.flock(token, fcntl.LOCK_UN)
    except OSError:
        pass
    os.close(token)


def _capture_manifest(root: Path, state: dict) -> dict:
    from .team import _rel_skipped
    folder = Path(state["staging"]) if state.get("staging") else None
    files = []
    if folder is not None and folder.is_dir():
        for path in sorted(item for item in folder.rglob("*") if item.is_file()):
            rel = path.relative_to(folder)
            if _rel_skipped(rel):
                continue
            dest = root / rel
            new = path.read_bytes()
            old = dest.read_bytes() if dest.is_file() else None
            if old == new:
                continue
            files.append({"path": rel.as_posix(), "sha256": hashlib.sha256(new).hexdigest()})
    return {
        "run_id": state["id"],
        "attempt": state["attempt"],
        "brief_hash": state["brief_hash"],
        "files": files,
    }


def seal_manifest(root: Path, run_id: str) -> dict:
    """Niêm tập file sẽ promote. Gọi lại không lấy byte mới."""
    state = _load(root, run_id)
    current = state.get("manifest")
    if isinstance(current, dict) and current.get("run_id") == state["id"] and current.get("attempt") == state["attempt"]:
        return state
    state["manifest"] = _capture_manifest(root, state)
    _save(root, state)
    return state


def promote_sealed(root: Path, state: dict) -> str:
    """Copy đúng byte đã niêm. Không chạy lại lệnh. Chuỗi rỗng là khớp."""
    from .team import _test_pause
    manifest = state.get("manifest")
    if not isinstance(manifest, dict):
        return "chưa có manifest bàn giao"
    if manifest.get("run_id") != state["id"] or manifest.get("brief_hash") != state["brief_hash"]:
        return "manifest không thuộc run này"
    if manifest.get("attempt") != state["attempt"]:
        return "manifest không thuộc lần thử này"
    folder = Path(state["staging"]) if state.get("staging") else None
    pending = []
    root = Path(root).resolve()
    for item in manifest.get("files") or []:
        rel = Path(item["path"])
        dest = (root / rel).resolve()
        if dest != root and root not in dest.parents:
            return "path thoát khỏi thư mục"
        digest = item["sha256"]
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
            continue
        src = (folder / rel) if folder is not None else None
        if src is None or not src.is_file():
            return "thiếu file trong manifest"
        if hashlib.sha256(src.read_bytes()).hexdigest() != digest:
            return "tập file đổi trước promote"
        pending.append((src, dest, digest))
    for index, (src, dest, digest) in enumerate(pending):
        if index:
            _test_pause("mid-promote")
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(src), str(dest))
        if not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            return "byte sau promote không khớp manifest"
    return ""


def _checked_rows(state: dict, root: Path) -> list[dict]:
    from .obligations import refresh_evidence
    base = Path(state["staging"]) if state.get("staging") and not state.get("promoted") else root
    if not Path(base).is_dir():
        base = root
    return refresh_evidence(
        list(state.get("obligations") or []), Path(base), state["brief_hash"],
        state["brief"]["acceptance_criteria"], exact_tree=not bool(state.get("promoted")))


def _finish_saved(root: Path, state: dict) -> tuple[list[dict], str, int]:
    """Team đã xong. Không gọi model. Promote tối đa một lần."""
    rows = apply_confirmations(state, _checked_rows(state, root), root)
    status, code = _delivery(rows)
    reason = ""
    if code == 0 and state.get("want_deliver") and not state.get("promoted"):
        reason = promote_sealed(root, state)
        if not reason:
            state["promoted"] = True
    if reason:
        state["phase"] = "failed"
        status, code = f"bàn giao: chặn — {reason}", 3
    elif code == 0 and (state.get("want_deliver") or state.get("promoted")):
        state["phase"] = "delivered"
    elif state.get("hold") == "needs_confirmation":
        state["phase"] = "awaiting_confirmation"
        status, code = "bàn giao: chưa", 4
    else:
        state["phase"] = "failed"
        if code == 0:
            status, code = "bàn giao: chặn", 3
    state["obligations"] = rows
    _save(root, state)
    body = _annotate(state, rows, "\n".join([
        render_table(state["request"], rows), status,
        _phase_line(state), _cost_line(state),
    ]))
    _write_table(root, state["id"], body)
    return rows, body, code


def _record(root: Path, state: dict, res: dict, ledger, rows: list[dict],
            status: str, code: int, deliver: bool) -> tuple[list[dict], str, int]:
    from .team import _test_pause
    state["obligations"] = rows
    state["hold"] = str(res.get("hold") or "")
    state["ledger"] = _ledger_blob(ledger)
    state["staging"] = str(res.get("staging") or "")
    state["want_deliver"] = bool(deliver)
    state["phase"] = "executing"
    if state["staging"] and not isinstance(state.get("manifest"), dict):
        state["manifest"] = _capture_manifest(root, state)
    _save(root, state)
    _test_pause("before-promote")
    if deliver:
        rows = apply_confirmations(state, _checked_rows(state, root), root)
        status, code = _delivery(rows)
        if code != 0:
            deliver = False
    reason = ""
    if deliver and not state["promoted"]:
        reason = promote_sealed(root, state)
        if reason:
            deliver = False
            status, code = f"bàn giao: chặn — {reason}", 3
        else:
            state["promoted"] = True
        _save(root, state)
    _test_pause("after-promote")
    if deliver:
        state["phase"] = "delivered"
    elif bare_deliverable(state["brief"]):
        state["phase"] = "awaiting_confirmation"
    elif res.get("hold") == "needs_confirmation" and res.get("status") == "withheld":
        state["phase"] = "awaiting_confirmation"
    else:
        state["phase"] = "failed"
    _save(root, state)
    edited = any(step.get("edited") for step in res.get("steps") or [])
    head = "worker: đã sửa trong staging" if edited else "worker: không sửa"
    accepted = next((row for row in rows if row.get("state") == "verifier_accepted"), None)
    if accepted:
        trace = _dir(root, state["id"]) / "trace.jsonl"
        trace.parent.mkdir(parents=True, exist_ok=True)
        with trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "verifier_delivery",
                "text": "bàn giao dựa trên verifier — chưa xác nhận tay",
                "staged_hash": accepted.get("staged_hash") or "",
            }, ensure_ascii=False) + "\n")
    body = _annotate(state, rows, "\n".join([
        head, render_table(state["request"], rows), status,
        _phase_line(state), _cost_line(state),
    ]))
    _write_table(root, state["id"], body)
    return rows, body, code


def settle(root: Path, run_id: str) -> tuple[list[dict], str, int]:
    """Xác nhận tay sau khi worker xong. Không gọi model và không promote lần hai."""
    state = _load(root, run_id)
    rows = apply_confirmations(state, _checked_rows(state, root), root)
    status, code = _delivery(rows)
    deliver = state.get("hold") == "needs_confirmation" and code == 0 and not state["promoted"]
    if deliver:
        from .team import _test_pause
        _test_pause("before-promote")
        rows = apply_confirmations(state, _checked_rows(state, root), root)
        status, code = _delivery(rows)
        deliver = code == 0 and not state["promoted"]
    if deliver:
        reason = promote_sealed(root, state)
        if reason:
            deliver = False
            code = 4
            status = "bàn giao: chưa — " + reason
        else:
            state["promoted"] = True
            state["phase"] = "delivered"
    elif code == 0 and state["promoted"]:
        state["phase"] = "delivered"
    else:
        state["phase"] = "awaiting_confirmation"
        code = 4 if code == 0 else code
        status = "bàn giao: chưa"
    state["obligations"] = rows
    _save(root, state)
    body = _annotate(state, rows, "\n".join([
        render_table(state["request"], rows), status,
        _phase_line(state), _cost_line(state),
    ]))
    _write_table(root, run_id, body)
    return rows, body, code


def execute(root: Path, run_id: str, *, provider: str | None, model: str | None,
            base_url: str | None, max_tokens: int, price,
            resume: bool = False) -> tuple[list[dict], str, int]:
    """Chạy team/execute_plan trên ledger và checkpoint đã có của run."""
    lock = _acquire_run(root, run_id)
    try:
        return _execute_locked(
            root, run_id, provider=provider, model=model, base_url=base_url,
            max_tokens=max_tokens, price=price, resume=resume)
    finally:
        _release_run(lock)


def _execute_locked(root: Path, run_id: str, *, provider: str | None, model: str | None,
                    base_url: str | None, max_tokens: int, price,
                    resume: bool = False) -> tuple[list[dict], str, int]:
    state = _load(root, run_id)
    if state.get("pending_files"):
        return [], "chờ người chọn file: " + state["pending_files"] + "\n" + _phase_line(state), 4
    if state.get("hold") == "stopped_budget":
        return _view(root, state)
    if state["phase"] == "executing" and (
            state.get("want_deliver") or state.get("promoted") or state.get("obligations")):
        return _finish_saved(root, state)
    if state["phase"] == "delivered":
        return _view(root, state)
    if state["phase"] == "failed":
        return _view(root, state)
    if state["phase"] == "awaiting_confirmation":
        return _view(root, state)
    refused = _blocked(state)
    if refused:
        return refused
    needed = grant_commands(state["brief"])
    if needed and not _active_grants(state):
        state["phase"] = "awaiting_grant"
        _save(root, state)
        return [], "chưa cấp lệnh — không thực thi\n" + _phase_line(state), 8
    from .team import execute_plan, ledger_from_checkpoint, load_checkpoint
    resume_steps = None
    resume_staging = None
    if resume or state["phase"] == "executing":
        data = load_checkpoint(root, state["id"])
        led = ledger_from_checkpoint(data["ledger"])
        resume_steps = list(data.get("steps") or [])
        resume_staging = data.get("staging")
    else:
        led = ledger_from_checkpoint(state["ledger"])
    frozen = None
    res: dict = {}
    rows: list[dict] = []
    for repair_round in range(_REPAIR_MAX + 1):
        plan = _make_plan(state, price)
        if frozen is None:
            frozen = plan.cap_usd
        elif plan.cap_usd is not None and frozen is not None and plan.cap_usd > frozen + 1e-9:
            raise HandoffError("cấm tự tăng trần")
        plan.cap_usd = frozen
        if state.get("repair"):
            plan.task_text += "\n\n" + _feedback_block(state["repair"])
        state["phase"] = "executing"
        state["ledger"] = _ledger_blob(led)
        _save(root, state)
        res = execute_plan(
            plan, provider_name=provider, model_override=model, base_url=base_url,
            max_tokens=max_tokens, root=root, run_id=state["id"], oracle="off",
            ledger=led, on_step=lambda _m: None,
            resume_steps=resume_steps, resume_staging=resume_staging,
            book_attempt=state["attempt"])
        resume_steps = None
        resume_staging = None
        state = _load(root, run_id)
        fresh = list(res.get("obligations") or [])
        rows = apply_confirmations(state, fresh or list(state.get("obligations") or []), root)
        if res.get("status") == "stopped_budget":
            state["ledger"] = _ledger_blob(led)
            state["obligations"] = rows
            state["hold"] = "stopped_budget"
            state["want_deliver"] = False
            state["phase"] = "executing"
            state["staging"] = str(res.get("staging") or state.get("staging") or "")
            _save(root, state)
            body = _annotate(state, rows, "\n".join([
                "bàn giao: chặn — stopped_budget",
                _phase_line(state), _cost_line(state),
            ]))
            _write_table(root, run_id, body)
            return rows, body, 3
        targets = _repair_targets(rows)
        if res.get("status") in ("error", "blocked") or not targets or repair_round >= _REPAIR_MAX:
            break
        state["history"].append({
            "attempt": state["attempt"],
            "phase": "failed",
            "cost_usd": round(float(led.total_usd), 6),
        })
        for note in targets:
            state["repair"].append({
                "criterion_id": note["criterion_id"],
                "delta": note["delta"],
                "evidence": note["evidence"],
                "attempt": state["attempt"],
            })
        state["attempt"] += 1
        state["ledger"] = _ledger_blob(led)
        state["obligations"] = rows
        state["manifest"] = None
        _save(root, state)
    _mark_verifier_delivery(rows, state.get("autonomy") or "watch", res)
    criteria_line, criteria_code = _delivery(rows)
    team_status = res.get("status") or "error"
    # PASS của verifier không miễn validator. deliver chỉ theo hàng tiêu chí.
    if team_status == "ok" or (
            res.get("hold") == "needs_confirmation" and team_status == "withheld"):
        status, code = criteria_line, criteria_code
        deliver = criteria_code == 0
    else:
        status, code = f"bàn giao: chặn — {team_status}", 3
        deliver = False
    if res.get("verifier_verdict") == "PASS" and criteria_code != 0:
        deliver = False
    if not deliver and res.get("fail_reason"):
        status += " — " + str(res["fail_reason"])
    if state.get("autonomy") == "walk-away" and criteria_code != 0:
        deliver = False
    if bare_deliverable(state["brief"]):
        deliver = False
        status, code = "bàn giao: chưa", 4
    return _record(root, state, res, led, rows, status, code, deliver)


def render_table(request: str, rows: list[dict]) -> str:
    del request
    labels = {
        "verified": "validator đã kiểm",
        "user_confirmed": "người dùng xác nhận",
        "direct": "chạy trực tiếp",
        "verifier_accepted": "bàn giao dựa trên verifier — chưa xác nhận tay",
        "needs_confirmation": "chưa chứng minh",
        "pending": "chưa cấp lệnh",
        "failed": "validator không đạt",
        "blocked": "bị chặn",
        "unverified": "chưa chứng minh",
        "unproven": "chưa chứng minh",
    }
    lines = ["id | tiêu chí | kết quả | phép kiểm | chứng minh | không chứng minh",
             "--- | --- | --- | --- | --- | ---"]
    for row in rows:
        state = row.get("state") or ""
        label = labels.get(state, state)
        if state and label != state:
            label = f"{state} — {label}"
        if row.get("evidence_status"):
            label = f"{label} — {row['evidence_status']}"
        if row.get("checked_on") == "staged" and row.get("staged_hash"):
            label = f"{label} — kiểm trên bản staged (hash {row['staged_hash']})"
        lines.append(" | ".join([
            row.get("criterion_id") or "",
            (row.get("criterion") or "").replace("\n", " "),
            label,
            row.get("kind") or "",
            (row.get("proves") or "").replace("\n", " "),
            (row.get("does_not_prove") or "").replace("\n", " "),
        ]))
    return "\n".join(lines)


def _price(raw: str | None):
    if not raw:
        return None
    left, right = [float(part) for part in str(raw).split(",")]
    return left, right


def _queue_items(root: Path) -> list[tuple[dict, list[str]]]:
    items = []
    for folder in _run_folders(root):
        state = _load_any(root, folder.name)
        if state is None or state.get("phase") == "delivered":
            continue
        reasons: list[str] = []
        if state.get("phase") == "awaiting_grant":
            reasons.append("bị chặn: chưa cấp lệnh")
        for row in state.get("obligations") or []:
            if row.get("state") in ("needs_confirmation", "blocked", "pending"):
                reasons.append(
                    f"{row.get('state')}: {row.get('criterion_id')} — "
                    f"{row.get('reason') or row.get('does_not_prove') or ''}"
                )
        if state.get("phase") == "awaiting_confirmation" and not reasons:
            reasons.append("chờ xác nhận")
        if state.get("phase") not in ("awaiting_confirmation", "awaiting_grant") and not reasons:
            continue
        if reasons:
            items.append((state, reasons))
    return items


def _accept_queued(root: Path, state: dict) -> int:
    if state.get("phase") != "awaiting_confirmation":
        return 0
    taken = 0
    for row in list(state.get("obligations") or []):
        if row.get("state") != "needs_confirmation" or row.get("kind") != "manual":
            continue
        artifact = ""
        for name in state["brief"].get("deliverables") or []:
            if _artifact_file(root, state, str(name)):
                artifact = str(name)
                break
        if not artifact:
            continue
        confirm(root, state["id"], row["criterion_id"], artifact)
        taken += 1
    if taken:
        settle(root, state["id"])
    return taken


def cmd_box(args) -> int:
    """Hàng đợi bàn giao. Một lần gọi --accept là một thao tác người dùng."""
    root = Path(getattr(args, "cwd", None) or ".").resolve()
    pull = getattr(args, "pull", None)
    accept = getattr(args, "accept", None)
    items = _queue_items(root)
    if pull:
        chosen = [item for item in items if item[0]["id"] == pull]
        if not chosen:
            print(f"không có {pull} trong hàng đợi")
            return 2
        state, reasons = chosen[0]
        print(f"{state['id']} {state['phase']}")
        print("\n".join(reasons))
        return 0
    if accept is not None:
        chosen = items if accept in ("*", "all") else [item for item in items if item[0]["id"] == accept]
        if accept not in ("*", "all") and not chosen:
            print(f"không có {accept} trong hàng đợi")
            return 2
        taken = 0
        for state, _reasons in chosen:
            taken += _accept_queued(root, state)
        print(f"duyệt lô: {taken}")
        return 0
    if not items:
        print("hàng đợi trống")
        return 0
    print("hàng đợi:")
    for state, reasons in items:
        print(f"- {state['id']} {state['phase']}")
        for reason in reasons:
            print(f"  {reason}")
    return 0


def cmd_giao(args) -> int:
    root = Path(getattr(args, "cwd", None) or ".").resolve()
    run_id = getattr(args, "run", None)
    if getattr(args, "task", None) == "box" and not run_id:
        return cmd_box(args)
    changed = getattr(args, "change", None)
    if run_id and changed:
        try:
            state = _load(root, run_id)
        except FileNotFoundError:
            print(f"không có run {run_id}")
            return 2
        except HandoffError as exc:
            print(str(exc))
            return 2
        print(request_change(state["request"], changed, run_id))
        return 2
    if run_id:
        try:
            lock = _acquire_run(root, run_id)
        except HandoffError as exc:
            print(str(exc))
            return 2
        try:
            try:
                if getattr(args, "approve_brief", False):
                    approve(root, run_id)
                else:
                    state = _load(root, run_id)
                    if not _approval_current(state):
                        print("chưa duyệt phiếu — không chạy" if not state.get("approved")
                              else "duyệt cũ hết hiệu lực vì phiếu đã đổi")
                        return 8
                if getattr(args, "autonomy", None):
                    _chosen, note = apply_autonomy(root, run_id, args.autonomy)
                    if note:
                        print(note)
                for cmd in getattr(args, "grant", None) or []:
                    remember_grant(root, run_id, cmd)
                if getattr(args, "retry", False):
                    begin_retry(root, run_id)
                if getattr(args, "confirm", None):
                    confirm(root, run_id, args.confirm, getattr(args, "artifact", None) or "")
                state = _load(root, run_id)
                if getattr(args, "check_only", False):
                    _rows, body, code = check_only(root, run_id)
                elif state["phase"] == "awaiting_confirmation" and getattr(args, "confirm", None):
                    _rows, body, code = settle(root, run_id)
                else:
                    _rows, body, code = execute(
                        root, run_id, provider=getattr(args, "provider", None),
                        model=getattr(args, "model", None),
                        base_url=getattr(args, "base_url", None),
                        max_tokens=int(getattr(args, "max_tokens", 4096) or 4096),
                        price=_price(getattr(args, "price_in", None)))
            except FileNotFoundError:
                print(f"không có run {run_id}")
                return 2
            except HandoffError as exc:
                print(str(exc))
                return 2
            print(body)
            return code
        finally:
            _release_run(lock)
    task = getattr(args, "task", None)
    if not task:
        print("thiếu yêu cầu")
        return 2
    from . import config as C
    from .providers import provider_for
    from .team import Ledger
    model = args.model or C.ROLE_MODEL["planner"]
    prov = provider_for(model, args.provider, base_url=args.base_url,
                        max_tokens=args.max_tokens)
    if not prov.available():
        print("thiếu key cho intake")
        return 8
    led = Ledger()
    files = workspace_files(root)
    got = run_intake(task, prov, led, clarify_max=0, ask=lambda _q: "",
                     model=model, declared_price=_price(getattr(args, "price_in", None)),
                     files=files)
    if not got["ok"] or got["brief"] is None:
        failed = root / ".frog" / "runs" / "intake-failed"
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "handoff.json").write_text(json.dumps({
            "id": "intake-failed",
            "attempt": 1,
            "phase": "failed",
            "ledger": _ledger_blob(led),
            "steps": [],
        }, ensure_ascii=False), encoding="utf-8")
        print(got["reason"] or "brief hỏng")
        return 8
    state = open_run(root, task, got["brief"], previous=getattr(args, "previous", None),
                     ledger=_ledger_blob(led))
    trace = _dir(root, state["id"]) / "trace.jsonl"
    with trace.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "kind": "workspace_files",
            "source": "workspace",
            "files": files,
        }, ensure_ascii=False) + "\n")
        if got.get("mapping"):
            handle.write(json.dumps({
                "kind": "deliverable_map",
                "map": got["mapping"],
                "text": "khớp deliverable",
            }, ensure_ascii=False) + "\n")
    if got.get("pending"):
        state["pending_files"] = str(got["pending"])
        _save(root, state)
        with trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "pending_files",
                "text": state["pending_files"],
            }, ensure_ascii=False) + "\n")
        print(state["pending_files"])
    filled = list(got.get("normalization") or [])
    proposed = list(got.get("proposed") or [])
    if proposed:
        trace = _dir(root, state["id"]) / "trace.jsonl"
        with trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "proposed_validator",
                "ids": proposed,
                "text": LABEL,
            }, ensure_ascii=False) + "\n")
    if filled:
        state["normalization"] = filled
        _save(root, state)
        trace = _dir(root, state["id"]) / "trace.jsonl"
        with trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "normalization",
                "filled": filled,
                "text": "đã điền thay: " + ", ".join(filled),
            }, ensure_ascii=False) + "\n")
    if getattr(args, "approve_brief", False):
        state = approve(root, state["id"])
    note = ""
    if getattr(args, "autonomy", None):
        state, note = apply_autonomy(root, state["id"], args.autonomy)
    print(preview(state["brief"], state["id"], state.get("normalization") or []))
    print(f"Hash phiếu: {state['brief_hash']}")
    if note:
        print(note)
    if state.get("previous"):
        print(f"Nối với run cũ: {state['previous']}")
        try:
            old = _load(root, state["previous"])
        except FileNotFoundError:
            old = {}
        if old.get("grants"):
            print("Không mang lệnh đã cấp của run cũ sang.")
    if getattr(args, "approve_brief", False) and state.get("autonomy") in ("walk-away", "direct"):
        for cmd in getattr(args, "grant", None) or []:
            remember_grant(root, state["id"], cmd)
        _rows, body, code = execute(
            root, state["id"], provider=getattr(args, "provider", None),
            model=model, base_url=getattr(args, "base_url", None),
            max_tokens=int(getattr(args, "max_tokens", 4096) or 4096),
            price=_price(getattr(args, "price_in", None)))
        print(body)
        return code
    return 0
