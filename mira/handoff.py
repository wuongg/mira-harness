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
import threading
import uuid
from pathlib import Path

from .intake import brief_hash, run_intake, validate_brief
from .obligations import criterion_commands, judge_obligations, validate_criteria

_AUTO = {"contains", "json_keys", "shape", "behavior"}
_RUN_ID = re.compile(r"^[0-9a-f]{8}$")
_STATE_FIELDS = (
    "id", "request", "brief", "brief_hash", "approved", "approved_hash",
    "grants", "previous",
)
_SAVE_LOCK = threading.Lock()


class HandoffError(Exception):
    """Lỗi phiếu có câu tiếng Việt. CLI in câu này, không in traceback."""


def _check_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise HandoffError("run id không hợp lệ")


def _dir(root: Path, run_id: str) -> Path:
    _check_run_id(run_id)
    base = (Path(root).resolve() / ".mira-giao").resolve()
    path = (base / run_id).resolve()
    if path != base and base not in path.parents:
        raise HandoffError("run thoát khỏi thư mục")
    return path


def _state_hash(state: dict) -> str:
    body = {key: state.get(key) for key in _STATE_FIELDS}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _grant_ok(item) -> bool:
    return (isinstance(item, dict) and set(item) == {"cmd", "brief_hash"}
            and isinstance(item["cmd"], str) and isinstance(item["brief_hash"], str))


def _load(root: Path, run_id: str) -> dict:
    _check_run_id(run_id)
    path = _dir(root, run_id) / "state.json"
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
    dest = folder / "state.json"
    with _SAVE_LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, dest)


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
        grant_flags = " ".join(f'--grant "{cmd}"' for cmd in commands)
        lines.append(f"Bước tiếp: py -3 -m mira giao --run {run_id} {grant_flags}")
    else:
        lines.append(f"Bước tiếp: py -3 -m mira giao --run {run_id}")
    return "\n".join(lines)


def open_run(root: Path, request: str, brief: dict, previous: str | None = None) -> dict:
    ok, why = validate_brief(brief)
    if not ok:
        raise HandoffError(why)
    if previous is not None:
        _check_run_id(previous)
    state = {
        "id": uuid.uuid4().hex[:8],
        "request": request,
        "brief": brief,
        "brief_hash": brief_hash(brief),
        "approved": False,
        "approved_hash": "",
        "grants": [],
        "previous": previous,
    }
    _save(root, state)
    return state


def approve(root: Path, run_id: str) -> dict:
    state = _load(root, run_id)
    state["approved"] = True
    state["approved_hash"] = state["brief_hash"]
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
        f"Bước tiếp: py -3 -m mira giao \"{new}\" --previous {old_id}"
    )


def _active_grants(state: dict) -> set[str]:
    allowed = set(grant_commands(state["brief"]))
    bound = state["brief_hash"]
    return {item["cmd"] for item in state["grants"]
            if item["brief_hash"] == bound and item["cmd"] in allowed}


def execute(root: Path, run_id: str) -> tuple[list[dict], str, int]:
    state = _load(root, run_id)
    if not _approval_current(state):
        text = "duyệt cũ hết hiệu lực vì phiếu đã đổi" if state.get("approved") else "chưa duyệt phiếu — không chạy"
        return [], text, 8
    rows = judge_obligations(
        list(state["brief"]["acceptance_criteria"]),
        cwd=root, granted=_active_grants(state), run_id=run_id)
    table = render_table(state["request"], rows)
    delivered = all(row.get("criterion_verified") for row in rows) and bool(rows)
    status = "bàn giao: đủ" if delivered else "bàn giao: chưa"
    body = table + "\n" + status
    (_dir(root, run_id) / "handoff.md").write_text(body, encoding="utf-8")
    return rows, body, 0 if delivered else 4


def render_table(request: str, rows: list[dict]) -> str:
    lines = ["yêu cầu | kết quả | phép kiểm | bằng chứng | chưa chứng minh",
             "--- | --- | --- | --- | ---"]
    for row in rows:
        proven = bool(row.get("criterion_verified"))
        evidence = row.get("proves") or row.get("reason") or ""
        gap = "" if proven else (row.get("does_not_prove") or row.get("reason") or "chưa chứng minh")
        lines.append(" | ".join([
            request.replace("\n", " "),
            row.get("state") or "",
            row.get("kind") or "",
            evidence.replace("\n", " "),
            gap.replace("\n", " "),
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
            _rows, body, code = execute(root, run_id)
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
    got = run_intake(task, prov, Ledger(), clarify_max=0, ask=lambda _q: "",
                     model=model, declared_price=_price(getattr(args, "price_in", None)))
    if not got["ok"] or got["brief"] is None:
        print(got["reason"] or "brief hỏng")
        return 8
    state = open_run(root, task, got["brief"], previous=getattr(args, "previous", None))
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
