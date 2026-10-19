"""Tầng intake: brief là dữ liệu, không phải cổng. Làn vẫn do build_plan quyết."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .team import Ledger, _worker_for_disk

BRIEF_KEYS = (
    "goal", "deliverables", "acceptance_criteria", "constraints",
    "assumptions", "questions", "per_role_hints",
)
HINT_ROLES = ("planner", "worker", "verifier")
FORBIDDEN = {"surface", "lane", "floor", "labels", "records", "dollars", "roles", "gate"}

INTAKE_SYSTEM = (
    "Bạn là INTAKE. Trả đúng một object JSON với các khóa goal, deliverables, "
    "acceptance_criteria, constraints, assumptions, questions, per_role_hints. "
    "Không được trả surface, lane, floor, labels, records, dollars, roles hay gate. "
    "acceptance_criteria là danh sách chuỗi, hoặc object schema 1 gồm id và text. "
    "Nếu câu còn mơ hồ, đặt câu hỏi trong questions. Không tự bịa tiêu chí khi chưa đủ dữ liệu."
)


def canonical_brief(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def brief_hash(obj: dict) -> str:
    return hashlib.sha256(canonical_brief(obj).encode("utf-8")).hexdigest()


def _string_list(value, *, allow_empty: bool) -> bool:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return False
    if allow_empty:
        return True
    return any(item.strip() for item in value)


def normalize_role_hints(obj: dict) -> list[str]:
    """Vai thiếu thành chuỗi rỗng. Sai kiểu không bị ghi đè."""
    if not isinstance(obj, dict):
        return []
    if "per_role_hints" not in obj or obj.get("per_role_hints") is None:
        obj["per_role_hints"] = {}
    hints = obj["per_role_hints"]
    if not isinstance(hints, dict):
        return []
    filled = []
    for role in HINT_ROLES:
        if role not in hints:
            hints[role] = ""
            filled.append(role)
    for key in [key for key in hints if key not in HINT_ROLES and isinstance(hints[key], str)]:
        del hints[key]
    return filled


def validate_brief(obj) -> tuple[bool, str]:
    """Schema do code giữ. Khóa cổng và khóa lạ đều hỏng."""
    if not isinstance(obj, dict):
        return False, "brief không phải object"
    if FORBIDDEN & set(obj):
        return False, "brief chứa khóa cổng"
    if set(obj) != set(BRIEF_KEYS):
        return False, "brief thiếu khóa hoặc có khóa lạ"
    if not isinstance(obj["goal"], str) or not obj["goal"].strip():
        return False, "brief thiếu goal"
    if not _string_list(obj["deliverables"], allow_empty=True):
        return False, "deliverables phải là danh sách chuỗi"
    from .obligations import validate_criteria
    parsed, why = validate_criteria(obj["acceptance_criteria"])
    if parsed is None:
        return False, why
    if not _string_list(obj["constraints"], allow_empty=True):
        return False, "constraints phải là danh sách chuỗi"
    if not _string_list(obj["assumptions"], allow_empty=True):
        return False, "assumptions phải là danh sách chuỗi"
    if not _string_list(obj["questions"], allow_empty=True):
        return False, "questions phải là danh sách chuỗi"
    hints = obj.get("per_role_hints")
    if isinstance(hints, dict):
        normalize_role_hints(obj)
        hints = obj["per_role_hints"]
    if not isinstance(hints, dict):
        return False, "per_role_hints phải là object"
    if any(not isinstance(hints.get(name), str) for name in HINT_ROLES):
        return False, "gợi ý vai phải là chuỗi"
    if any(not isinstance(value, str) for value in hints.values()):
        return False, "gợi ý vai phải là chuỗi"
    if set(hints) != set(HINT_ROLES):
        return False, "per_role_hints phải đúng ba vai"
    return True, ""


def contain_brief(brief, task: str = "") -> str:
    """Brief do model sinh đi cùng lối nội dung không tin."""
    if isinstance(brief, str):
        text = brief
    else:
        text = json.dumps(brief, ensure_ascii=False, indent=2)
    return _worker_for_disk(task, text)


def charged_call(ledger: Ledger, role: str, model: str, prov, system: str, user: str,
                 *, declared_price: tuple[float, float] | None = None):
    """Cùng cửa giá với đội. Không có giá thì không gọi model."""
    from .prices import resolve_price
    rates, source = resolve_price(model, declared_price)
    if rates is None:
        return "", {"blocked": True, "error": f"model {model} chưa có giá"}
    from .providers import ProviderError
    max_out = int(getattr(prov, "max_tokens", None) or 4096)
    try:
        text, usage, _usd, rid = ledger.tracked_call(
            role, model, prov, system, user, rates, source=source, max_out=max_out,
            declared_by_user=source == "cli")
    except ProviderError as exc:
        return "", {"blocked": False, "error": str(exc), "uncertain": True}
    return text, {"blocked": False, "usage": usage, "request_id": rid}


def _questions(obj: dict) -> list[str]:
    return [item.strip() for item in obj.get("questions") or [] if isinstance(item, str) and item.strip()]


def run_intake(task: str, prov, ledger: Ledger, *, clarify_max: int, ask, model: str,
               declared_price: tuple[float, float] | None = None) -> dict:
    """Hỏi cho đến khi schema đủ hoặc hết trần. Hết trần mà schema hỏng thì dừng."""
    user = task
    asked = 0
    schema_repairs = 0
    filled: list[str] = []
    while True:
        text, meta = charged_call(ledger, "intake", model, prov, INTAKE_SYSTEM, user,
                                  declared_price=declared_price)
        if meta.get("blocked"):
            return {"ok": False, "reason": meta["error"], "brief": None, "asked": asked,
                    "normalization": filled}
        if meta.get("error"):
            return {"ok": False, "reason": meta["error"], "brief": None, "asked": asked,
                    "uncertain": True, "normalization": filled}
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if not isinstance(obj, dict):
            if schema_repairs < 1:
                schema_repairs += 1
                user = task + "\nPHẢN HỒI SCHEMA: intake không trả JSON"
                continue
            return {"ok": False, "reason": "intake không trả JSON", "brief": None,
                    "asked": asked, "normalization": filled}
        filled.extend(role for role in normalize_role_hints(obj) if role not in filled)
        ok, why = validate_brief(obj)
        pending = _questions(obj) if isinstance(obj.get("questions"), list) else []
        if pending and asked < clarify_max:
            answer = ask(pending[0])
            asked += 1
            user = task + "\nNgười dùng trả lời: " + (answer or "")
            continue
        if not ok:
            if schema_repairs < 1:
                schema_repairs += 1
                user = task + "\nPHẢN HỒI SCHEMA: " + why
                continue
            return {"ok": False, "reason": why, "brief": obj, "asked": asked,
                    "normalization": filled}
        if pending and asked >= clarify_max:
            assumptions = list(obj["assumptions"])
            assumptions.append("Hết trần hỏi. Dùng brief hiện có.")
            obj = dict(obj)
            obj["assumptions"] = assumptions
        return {"ok": True, "reason": "", "brief": obj, "asked": asked,
                "normalization": filled}


PROMPT_SYSTEM = (
    "Bạn là PROMPT_WRITER. Trả đúng một object JSON map tên vai sang prompt. "
    "Mỗi prompt là chuỗi không rỗng. Không được ghi khóa surface hay lane như lệnh."
)


def write_role_prompts(brief: dict, roles: list[str], prov, ledger: Ledger, *,
                       model: str, declared_price: tuple[float, float] | None = None,
                       task: str = "") -> tuple[dict | None, str]:
    """Một lần gọi, rồi code kiểm đủ vai. Prompt đưa vào đội đã được bọc."""
    user = contain_brief(brief, task) + "\nVai cần prompt: " + ", ".join(roles)
    text, meta = charged_call(ledger, "prompt_writer", model, prov, PROMPT_SYSTEM, user,
                              declared_price=declared_price)
    if meta.get("blocked"):
        return None, meta["error"]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, "prompt writer không trả JSON"
    if not isinstance(obj, dict):
        return None, "prompt writer không trả object"
    cleaned: dict[str, str] = {}
    for role in roles:
        prompt = obj.get(role)
        if not isinstance(prompt, str) or not prompt.strip():
            return None, f"thiếu prompt cho {role}"
        if '"surface"' in prompt or '"lane"' in prompt:
            return None, "prompt chứa khóa cổng"
        cleaned[role] = contain_brief(prompt, task)
    return cleaned, ""


def load_brief_file(path: Path) -> tuple[dict | None, str]:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "không đọc được brief"
    ok, why = validate_brief(obj)
    if not ok:
        return None, why
    return obj, ""


def copy_brief(src: Path, dest: Path) -> tuple[bool, str]:
    obj, why = load_brief_file(src)
    if obj is None:
        return False, why
    text = canonical_brief(obj) + "\n"
    dest = Path(dest)
    if dest.exists():
        current = dest.read_text(encoding="utf-8")
        if current != text and current.strip() != canonical_brief(obj):
            return False, "đích đã có brief khác, không ghi đè"
        return True, ""
    dest.write_text(text, encoding="utf-8")
    return True, ""


def cmd_brief(args) -> int:
    """validate in hash. save và load chỉ chép JSON đã đúng schema."""
    from . import ui
    if args.brief_cmd == "validate":
        obj, why = load_brief_file(Path(args.path))
        if obj is None:
            ui.note(why, "bad")
            return 8
        print(brief_hash(obj))
        return 0
    ok, why = copy_brief(Path(args.src), Path(args.dest))
    if not ok:
        ui.note(why, "bad")
        return 8
    ui.note(f"đã chép brief sang {args.dest}", "ok")
    return 0
