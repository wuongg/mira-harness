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
import uuid
from pathlib import Path

from .intake import brief_hash, run_intake, validate_brief
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
    "staging", "promoted",
)
_SAVE_LOCK = threading.Lock()


class HandoffError(Exception):
    """Lỗi phiếu có câu tiếng Việt. CLI in câu này, không in traceback."""


def _check_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise HandoffError("run id không hợp lệ")


def _dir(root: Path, run_id: str) -> Path:
    _check_run_id(run_id)
    base = (Path(root).resolve() / ".mira" / "runs").resolve()
    path = (base / run_id).resolve()
    if path != base and base not in path.parents:
        raise HandoffError("run thoát khỏi thư mục")
    return path


def _state_hash(state: dict) -> str:
    body = {key: state.get(key) for key in _STATE_FIELDS}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _confirm_ok(item) -> bool:
    return (isinstance(item, dict)
            and set(item) == {"criterion_id", "artifact", "sha256", "brief_hash"}
            and all(isinstance(item[key], str) and item[key] for key in item))


def _grant_ok(item) -> bool:
    return (isinstance(item, dict) and set(item) == {"cmd", "brief_hash"}
            and isinstance(item["cmd"], str) and isinstance(item["brief_hash"], str))


def _history_ok(item) -> bool:
    return (isinstance(item, dict)
            and set(item) == {"attempt", "phase", "cost_usd"}
            and isinstance(item["attempt"], int) and item["phase"] in _PHASES
            and isinstance(item["cost_usd"], (int, float)))


def _empty_ledger() -> dict:
    return {
        "rows": [], "total_usd": 0.0, "total_in": 0, "total_out": 0,
        "subagent_runs": 0, "reserved": 0.0, "uncertain_usd": 0.0,
        "uncertain": [], "requests": [],
    }


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


def _load(root: Path, run_id: str) -> dict:
    _check_run_id(run_id)
    path = _dir(root, run_id) / "handoff.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HandoffError("state hỏng: JSON cụt") from None
    if not isinstance(state, dict) or set(state) != set(_STATE_FIELDS) | {"state_hash"}:
        raise HandoffError("state hỏng: sai schema")
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
    if not isinstance(state.get("promoted"), bool):
        raise HandoffError("state hỏng: sai schema")
    ok, why = validate_brief(state.get("brief"))
    if not ok:
        raise HandoffError(f"state hỏng: {why}")
    if state.get("brief_hash") != brief_hash(state["brief"]):
        raise HandoffError("phiếu không khớp hash đã lưu")
    if state.get("state_hash") != _state_hash(state):
        raise HandoffError("trạng thái không khớp hash")
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
        os.replace(tmp, dest)


def _argv(args: list[str]) -> str:
    argv = [sys.executable, "-m", "mira", "giao", *args]
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


def preview(brief: dict, run_id: str) -> str:
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
    }
    _save(root, state)
    return state


def approve(root: Path, run_id: str) -> dict:
    state = _load(root, run_id)
    state["approved"] = True
    state["approved_hash"] = state["brief_hash"]
    if state["phase"] in ("awaiting_approval", "awaiting_grant", "ready"):
        state["phase"] = "awaiting_grant" if grant_commands(state["brief"]) else "ready"
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


def _find_artifact(root: Path, rel: str) -> Path | None:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or not rel.strip():
        raise HandoffError("artifact không hợp lệ")
    base = Path(root).resolve()
    names = [base / rel]
    staging = base / ".mira" / "staging"
    if staging.is_dir():
        names.extend(staging.glob(f"*.withheld/{rel}"))
        names.extend(staging.glob(f"*/{rel}"))
    for cand in names:
        if not cand.is_file():
            continue
        resolved = cand.resolve()
        if resolved == base or base in resolved.parents:
            return resolved
    return None


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
    found = _find_artifact(root, artifact)
    if found is None:
        raise HandoffError("không có artifact")
    digest = hashlib.sha256(found.read_bytes()).hexdigest()
    row = {"criterion_id": criterion_id, "artifact": artifact.replace("\\", "/"),
           "sha256": digest, "brief_hash": state["brief_hash"]}
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
                      and item["brief_hash"] == state["brief_hash"]), None)
        if match is None:
            continue
        found = _find_artifact(root, match["artifact"])
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
    return rows


def _settled(row: dict) -> bool:
    return bool(row.get("criterion_verified")) or row.get("state") == "user_confirmed"


def _delivery(rows: list[dict]) -> tuple[str, int]:
    if not rows or not all(_settled(row) for row in rows):
        return "bàn giao: chưa", 4
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
        cwd=root, granted=_active_grants(state), run_id=run_id), root)
    passed = bool(rows) and all(row.get("criterion_verified") for row in rows)
    status = ("kiểm file: đạt — chưa phải hoàn thành nhiệm vụ" if passed
              else "kiểm file: chưa — chưa phải hoàn thành nhiệm vụ")
    body = render_table(state["request"], rows) + "\n" + status
    _write_table(root, run_id, body)
    return rows, body, 4


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
    _save(root, state)
    return state


def _record(root: Path, state: dict, res: dict, ledger, rows: list[dict],
            status: str, code: int, deliver: bool) -> tuple[list[dict], str, int]:
    from .team import promote_staging
    state["obligations"] = rows
    state["hold"] = str(res.get("hold") or "")
    state["ledger"] = _ledger_blob(ledger)
    state["staging"] = str(res.get("staging") or "")
    if deliver and not state["promoted"]:
        folder = Path(state["staging"]) if state["staging"] else None
        if folder is not None and folder.is_dir():
            promote_staging(root, folder, [])
        state["promoted"] = True
        state["phase"] = "delivered"
    elif res.get("hold") == "needs_confirmation" and res.get("status") == "withheld":
        state["phase"] = "awaiting_confirmation"
    else:
        state["phase"] = "failed" if not deliver else "delivered"
    _save(root, state)
    edited = any(step.get("edited") for step in res.get("steps") or [])
    head = "worker: đã sửa trong staging" if edited else "worker: không sửa"
    body = "\n".join([
        head, render_table(state["request"], rows), status,
        _phase_line(state), _cost_line(state),
    ])
    _write_table(root, state["id"], body)
    return rows, body, code


def settle(root: Path, run_id: str) -> tuple[list[dict], str, int]:
    """Xác nhận tay sau khi worker xong. Không gọi model và không promote lần hai."""
    state = _load(root, run_id)
    rows = apply_confirmations(state, list(state["obligations"]), root)
    status, code = _delivery(rows)
    deliver = state.get("hold") == "needs_confirmation" and code == 0 and not state["promoted"]
    if deliver:
        folder = Path(state["staging"]) if state["staging"] else None
        if folder is not None and folder.is_dir():
            from .team import promote_staging
            promote_staging(root, folder, [])
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
    body = "\n".join([
        render_table(state["request"], rows), status,
        _phase_line(state), _cost_line(state),
    ])
    _write_table(root, run_id, body)
    return rows, body, code


def execute(root: Path, run_id: str, *, provider: str | None, model: str | None,
            base_url: str | None, max_tokens: int, price,
            resume: bool = False) -> tuple[list[dict], str, int]:
    """Chạy team/execute_plan trên ledger và checkpoint đã có của run."""
    state = _load(root, run_id)
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
    plan = _make_plan(state, price)
    resume_steps = None
    resume_staging = None
    if resume or state["phase"] == "executing":
        data = load_checkpoint(root, state["id"])
        led = ledger_from_checkpoint(data["ledger"])
        resume_steps = list(data.get("steps") or [])
        resume_staging = data.get("staging")
    else:
        led = ledger_from_checkpoint(state["ledger"])
    state["phase"] = "executing"
    _save(root, state)
    res = execute_plan(
        plan, provider_name=provider, model_override=model, base_url=base_url,
        max_tokens=max_tokens, root=root, run_id=state["id"], oracle="off",
        ledger=led, on_step=lambda _m: None,
        resume_steps=resume_steps, resume_staging=resume_staging)
    state = _load(root, run_id)
    rows = apply_confirmations(state, list(res.get("obligations") or []), root)
    criteria_line, criteria_code = _delivery(rows)
    team_status = res.get("status") or "error"
    if team_status == "ok":
        status, code = criteria_line, criteria_code
        deliver = criteria_code == 0
    elif res.get("hold") == "needs_confirmation" and team_status == "withheld":
        status, code = criteria_line, criteria_code
        deliver = criteria_code == 0
    else:
        status, code = f"bàn giao: chặn — {team_status}", 3
        deliver = False
    if not deliver and res.get("fail_reason"):
        status += " — " + str(res["fail_reason"])
    return _record(root, state, res, led, rows, status, code, deliver)


def render_table(request: str, rows: list[dict]) -> str:
    del request
    labels = {
        "verified": "validator đã kiểm",
        "user_confirmed": "người dùng xác nhận",
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


def cmd_giao(args) -> int:
    root = Path(getattr(args, "cwd", None) or ".").resolve()
    run_id = getattr(args, "run", None)
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
            if getattr(args, "approve_brief", False):
                approve(root, run_id)
            else:
                state = _load(root, run_id)
                if not _approval_current(state):
                    print("chưa duyệt phiếu — không chạy" if not state.get("approved")
                          else "duyệt cũ hết hiệu lực vì phiếu đã đổi")
                    return 8
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
    got = run_intake(task, prov, led, clarify_max=0, ask=lambda _q: "",
                     model=model, declared_price=_price(getattr(args, "price_in", None)))
    if not got["ok"] or got["brief"] is None:
        print(got["reason"] or "brief hỏng")
        return 8
    state = open_run(root, task, got["brief"], previous=getattr(args, "previous", None),
                     ledger=_ledger_blob(led))
    if getattr(args, "approve_brief", False):
        state = approve(root, state["id"])
    print(preview(state["brief"], state["id"]))
    print(f"Hash phiếu: {state['brief_hash']}")
    if state.get("previous"):
        print(f"Nối với run cũ: {state['previous']}")
        try:
            old = _load(root, state["previous"])
        except FileNotFoundError:
            old = {}
        if old.get("grants"):
            print("Không mang lệnh đã cấp của run cũ sang.")
    return 0
