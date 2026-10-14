"""Phiếu giao việc rồi bàn giao. Dùng intake và validator sẵn có.

Duyệt phiếu không cấp quyền chạy lệnh. Mỗi lệnh phải được nêu đúng chuỗi.
"""
from __future__ import annotations

import difflib
import json
import uuid
from pathlib import Path

from .intake import brief_hash, canonical_brief, run_intake, validate_brief
from .obligations import criterion_commands, judge_obligations, validate_criteria

_AUTO = {"contains", "json_keys", "shape", "behavior"}


def _dir(root: Path, run_id: str) -> Path:
    return root / ".mira-giao" / run_id


def _load(root: Path, run_id: str) -> dict:
    path = _dir(root, run_id) / "state.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _save(root: Path, state: dict) -> None:
    folder = _dir(root, state["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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
    if commands:
        grant_flags = " ".join(f'--grant "{cmd}"' for cmd in commands)
        lines.append(f"Bước tiếp: py -3 -m mira giao --run {run_id} {grant_flags}")
    else:
        lines.append(f"Bước tiếp: py -3 -m mira giao --run {run_id}")
    return "\n".join(lines)


def open_run(root: Path, request: str, brief: dict, previous: str | None = None) -> dict:
    ok, why = validate_brief(brief)
    if not ok:
        raise ValueError(why)
    state = {
        "id": uuid.uuid4().hex[:8],
        "request": request,
        "brief": brief,
        "brief_hash": brief_hash(brief),
        "approved": False,
        "grants": [],
        "previous": previous,
    }
    _save(root, state)
    return state


def approve(root: Path, run_id: str) -> dict:
    state = _load(root, run_id)
    state["approved"] = True
    _save(root, state)
    return state


def remember_grant(root: Path, run_id: str, cmd: str) -> dict:
    state = _load(root, run_id)
    if cmd not in state["grants"]:
        state["grants"].append(cmd)
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


def execute(root: Path, run_id: str) -> tuple[list[dict], str, int]:
    state = _load(root, run_id)
    if not state.get("approved"):
        text = "chưa duyệt phiếu — không chạy"
        return [], text, 8
    rows = judge_obligations(
        list(state["brief"]["acceptance_criteria"]),
        cwd=root, granted=set(state.get("grants") or []), run_id=run_id)
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
        print(request_change(state["request"], changed, run_id))
        return 2
    if run_id:
        try:
            if getattr(args, "approve_brief", False):
                approve(root, run_id)
            else:
                state = _load(root, run_id)
                if not state.get("approved"):
                    print("chưa duyệt phiếu — không chạy")
                    return 8
        except FileNotFoundError:
            print(f"không có run {run_id}")
            return 2
        for cmd in getattr(args, "grant", None) or []:
            remember_grant(root, run_id, cmd)
        _rows, body, code = execute(root, run_id)
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
