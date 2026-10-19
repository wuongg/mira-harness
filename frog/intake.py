"""Tầng intake: brief là dữ liệu, không phải cổng. Làn vẫn do build_plan quyết."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path

from .team import Ledger, _worker_for_disk

BRIEF_KEYS = (
    "goal", "deliverables", "acceptance_criteria", "constraints",
    "assumptions", "questions", "per_role_hints",
)
HINT_ROLES = ("planner", "worker", "verifier")
FORBIDDEN = {"surface", "lane", "floor", "labels", "records", "dollars", "roles", "gate"}

LABEL = "validator do code đề xuất"

INTAKE_SYSTEM = (
    "Bạn là INTAKE. Trả đúng một object JSON với các khóa goal, deliverables, "
    "acceptance_criteria, constraints, assumptions, questions, per_role_hints. "
    "Không được trả surface, lane, floor, labels, records, dollars, roles hay gate. "
    "acceptance_criteria là danh sách chuỗi. Mỗi chuỗi là một tiêu chí chữ. "
    "Không viết validator. "
    "deliverables chỉ được lấy từ danh sách file workspace đi kèm, đúng đường dẫn, không bịa path. "
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
    return _check_validators(obj, parsed)


def _deliverable_names(value) -> list[str]:
    names = []
    for item in value or []:
        if isinstance(item, str) and item.strip():
            names.append(item.replace("\\", "/").strip())
    return names


def _check_validators(obj: dict, parsed: list[dict]) -> tuple[bool, str]:
    """Thiếu validator thì để manual. Validator có path phải nằm trong deliverables."""
    names = _deliverable_names(obj.get("deliverables"))
    for item in parsed:
        validator = item.get("validator")
        if not validator:
            continue
        path = str(validator.get("path") or "")
        if path and path not in names:
            return False, "validator path ngoài deliverables"
    return True, ""


def _pick_deliverable(names: list[str], suffixes: set[str], text: str) -> str:
    hits = [name for name in names if Path(name).suffix.lower() in suffixes]
    named = [name for name in hits if name in text or Path(name).name in text]
    if len(named) == 1:
        return named[0]
    if len(hits) == 1:
        return hits[0]
    return ""


def _safe_literal(value) -> bool:
    if isinstance(value, (int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_safe_literal(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _safe_literal(item) for key, item in value.items())
    return False


def _parse_args(raw: str):
    text = raw.strip()
    expr = f"({text},)" if text else "()"
    try:
        value = ast.literal_eval(expr)
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, tuple) or not _safe_literal(value):
        return None
    return value


def _parse_expected(raw: str):
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return None
    if isinstance(value, (list, dict, tuple)) or not _safe_literal(value):
        return None
    return value


def _behavior_spec(path: str, text: str) -> dict | None:
    module = Path(path).stem
    if not module.isidentifier():
        return None
    found = re.finditer(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([^)]*)\s*\)\s*(?:==|bằng|bang|trả|tra)\s*"
        r"(-?\d+(?:\.\d+)?|\"[^\"\n]*\"|'[^'\n]*')",
        text, re.IGNORECASE)
    checks = []
    for match in found:
        name, args, expected = match.group(1), match.group(2), match.group(3)
        parsed_args = _parse_args(args)
        parsed_expected = _parse_expected(expected)
        if parsed_args is None or parsed_expected is None or not name.isidentifier():
            return None
        rendered = ", ".join(repr(item) for item in parsed_args)
        checks.append(f"{module}.{name}({rendered}) == {parsed_expected!r}")
    if not checks:
        return None
    source = "import " + module + "; print('ok' if " + " and ".join(checks) + " else 'no')"
    return {
        "kind": "behavior",
        "cmd": shlex.join([sys.executable, "-c", source]),
        "expects_exit": 0,
        "expects_stdout": "ok",
        "does_not_prove": "không chứng minh lời gọi khác",
    }


def _json_keys(text: str) -> list[str]:
    quoted = re.findall(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""", text)
    if quoted:
        return list(dict.fromkeys(quoted))
    match = re.search(
        r"(?:có|co)\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*(?:,|và|va)\s*[A-Za-z_][A-Za-z0-9_]*)+)",
        text, re.IGNORECASE)
    if not match:
        return []
    parts = re.split(r"\s*(?:,|và|va)\s*", match.group(1), flags=re.IGNORECASE)
    return [part for part in parts if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part)]


def _json_spec(path: str, text: str) -> dict | None:
    keys = _json_keys(text)
    if not keys:
        return None
    expect = "array" if re.search(
        r"phần tử|phan tu|mảng|mang|\barray\b|danh sách|danh sach", text, re.IGNORECASE) else "object"
    return {
        "kind": "json_keys",
        "path": path,
        "required": keys,
        "forbidden": [],
        "expect": expect,
        "allow_empty": False,
    }


def _contains_spec(path: str, text: str) -> dict | None:
    quoted = re.findall(r"""["']([^"'\n]{1,80})["']""", text)
    caps = re.findall(r"\b[A-Z][A-Z0-9]+(?:\s+[A-Z][A-Z0-9]+)*\b", text)
    must = list(dict.fromkeys(quoted or caps))
    must = [item for item in must if item != path and item != Path(path).name]
    if not must:
        return None
    return {"kind": "contains", "path": path, "must_contain": must, "must_not_contain": []}


def _infer_validator(text: str, names: list[str]) -> dict | None:
    source = _pick_deliverable(names, {".py"}, text)
    if source:
        spec = _behavior_spec(source, text)
        if spec:
            return spec
    data = _pick_deliverable(names, {".json"}, text)
    if data:
        spec = _json_spec(data, text)
        if spec:
            return spec
    doc = _pick_deliverable(names, {".md", ".txt"}, text)
    if doc:
        return _contains_spec(doc, text)
    return None


_HIDDEN_DIRS = frozenset({".mira", ".frog", "out", "__pycache__"})


def workspace_files(root: Path) -> list[str]:
    """Tên file tương đối. Không đọc nội dung, không lộ thư mục nội bộ."""
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = Path(rel).parts
        if any(part.startswith(".") or part in _HIDDEN_DIRS for part in parts):
            continue
        found.append(rel)
    return found


def declared_path(text: str) -> str | None:
    """Path tương đối đã khai trong brief. Câu chữ thì không phải path."""
    raw = text.replace("\\", "/").strip()
    if not raw or any(ch.isspace() for ch in raw):
        return None
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
        return None
    parts = tuple(part for part in raw.split("/") if part != "")
    if not parts or any(part in (".", "..") or part.startswith(".") for part in parts):
        return None
    return "/".join(parts)


def match_deliverable(text: str, files: list[str]) -> str | None:
    """exact rồi fuzzy. Nhiều ứng viên thì không chọn."""
    raw = text.replace("\\", "/").strip()
    if raw in files:
        return raw
    by_base: dict[str, list[str]] = {}
    for rel in files:
        by_base.setdefault(Path(rel).name, []).append(rel)
    if raw in by_base and len(by_base[raw]) == 1:
        return by_base[raw][0]
    hits = [rel for rel in files if Path(rel).name and Path(rel).name in raw]
    if len(hits) == 1:
        return hits[0]
    return None


def bind_deliverables(obj: dict, files: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Đổi câu chữ thành path trong danh sách. Không bịa path ngoài danh sách."""
    mapped = []
    missing = []
    rewritten = []
    for item in obj.get("deliverables") or []:
        if not isinstance(item, str):
            missing.append(str(item))
            rewritten.append(item)
            continue
        path = match_deliverable(item, files)
        if path is None:
            path = declared_path(item)
        if path is None:
            missing.append(item)
            rewritten.append(item)
            continue
        mapped.append((item, path))
        rewritten.append(path)
    if missing:
        return mapped, missing
    obj["deliverables"] = rewritten
    assumptions = list(obj.get("assumptions") or [])
    for old, path in mapped:
        note = f"khớp deliverable: {old} -> {path}"
        if note not in assumptions:
            assumptions.append(note)
    obj["assumptions"] = assumptions
    return mapped, []


def original_texts(root: Path, files: list[str]) -> dict[str, str]:
    """Nội dung file gốc. Chỉ để code so validator, không đưa vào prompt."""
    found: dict[str, str] = {}
    root = Path(root)
    for rel in files:
        path = root.joinpath(*Path(rel).parts)
        if not path.is_file():
            continue
        try:
            found[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return found


def _already_in_source(spec: dict, originals: dict[str, str] | None) -> bool:
    """Validator đã đúng trên file chưa sửa thì không chứng minh worker đã sửa."""
    if not originals:
        return False
    path = str(spec.get("path") or "")
    if path not in originals:
        return False
    body = originals[path]
    kind = spec.get("kind")
    if kind == "contains":
        must = [item for item in spec.get("must_contain") or [] if isinstance(item, str) and item]
        return bool(must) and all(item in body for item in must)
    if kind == "json_keys":
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return False
        keys = [item for item in spec.get("required") or [] if isinstance(item, str) and item]
        if not keys:
            return False
        if spec.get("expect") == "array":
            if not isinstance(data, list) or not data:
                return False
            return all(isinstance(row, dict) and all(key in row for key in keys) for row in data)
        return isinstance(data, dict) and all(key in data for key in keys)
    return False


def propose_validators(obj: dict, originals: dict[str, str] | None = None) -> list[str]:
    """Gắn validator suy được. Tiêu chí không suy được giữ manual."""
    from .obligations import validate_criteria
    names = _deliverable_names(obj.get("deliverables"))
    proposed: list[str] = []
    items = []
    for raw in obj.get("acceptance_criteria") or []:
        parsed, _why = validate_criteria([raw])
        if not parsed or parsed[0].get("validator"):
            items.append(raw)
            continue
        spec = _infer_validator(parsed[0]["text"], names)
        if spec is None or _already_in_source(spec, originals):
            items.append(raw)
            continue
        if isinstance(raw, str):
            cid = "c" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            built = {
                "schema": 1, "id": cid, "text": raw.strip(),
                "proves": LABEL, "validator": spec,
            }
        else:
            built = dict(raw)
            built["validator"] = spec
            if not str(built.get("proves") or "").strip():
                built["proves"] = LABEL
            cid = str(built.get("id") or "")
        items.append(built)
        proposed.append(cid)
    if not proposed:
        return []
    trial = dict(obj)
    trial["acceptance_criteria"] = items
    note = LABEL + ": " + ", ".join(proposed)
    assumptions = list(trial.get("assumptions") or [])
    if note not in assumptions:
        assumptions.append(note)
    trial["assumptions"] = assumptions
    ok, _why = validate_brief(trial)
    if not ok:
        return []
    obj["acceptance_criteria"] = items
    obj["assumptions"] = assumptions
    return proposed


def code_proposed_commands(brief: dict) -> list[str]:
    """Lệnh behavior do code gắn. Duyệt brief là duyệt các lệnh này."""
    found = []
    for item in brief.get("acceptance_criteria") or []:
        if not isinstance(item, dict) or item.get("proves") != LABEL:
            continue
        validator = item.get("validator") or {}
        cmd = validator.get("cmd") if isinstance(validator, dict) else ""
        if validator.get("kind") == "behavior" and isinstance(cmd, str) and cmd and cmd not in found:
            found.append(cmd)
    return found


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


def _intake_user(task: str, files: list[str] | None, extra: str = "") -> str:
    lines = [task]
    if files is not None:
        lines.append("File workspace:")
        lines.extend(files or ["(không có file)"])
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def run_intake(task: str, prov, ledger: Ledger, *, clarify_max: int, ask, model: str,
               declared_price: tuple[float, float] | None = None,
               files: list[str] | None = None,
               originals: dict[str, str] | None = None) -> dict:
    """Hỏi cho đến khi schema đủ hoặc hết trần. Hết trần mà schema hỏng thì dừng."""
    user = _intake_user(task, files)
    asked = 0
    schema_repairs = 0
    file_repairs = 0
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
                user = _intake_user(task, files, "PHẢN HỒI SCHEMA: intake không trả JSON")
                continue
            return {"ok": False, "reason": "intake không trả JSON", "brief": None,
                    "asked": asked, "normalization": filled}
        filled.extend(role for role in normalize_role_hints(obj) if role not in filled)
        ok, why = validate_brief(obj)
        pending = _questions(obj) if isinstance(obj.get("questions"), list) else []
        if pending and asked < clarify_max:
            answer = ask(pending[0])
            asked += 1
            user = _intake_user(task, files, "Người dùng trả lời: " + (answer or ""))
            continue
        if not ok:
            if schema_repairs < 1:
                schema_repairs += 1
                user = _intake_user(task, files, "PHẢN HỒI SCHEMA: " + why)
                continue
            return {"ok": False, "reason": why, "brief": obj, "asked": asked,
                    "normalization": filled}
        if pending and asked >= clarify_max:
            assumptions = list(obj["assumptions"])
            assumptions.append("Hết trần hỏi. Dùng brief hiện có.")
            obj = dict(obj)
            obj["assumptions"] = assumptions
        mapping: list[tuple[str, str]] = []
        if files is not None:
            mapping, missing = bind_deliverables(obj, files)
            if missing:
                shown = ", ".join(files) if files else "(không có file)"
                if file_repairs < 1:
                    file_repairs += 1
                    user = _intake_user(
                        task, files,
                        "PHẢN HỒI SCHEMA: deliverable không khớp file workspace. "
                        "Chọn lại từ danh sách: " + shown)
                    continue
                question = "Chọn deliverable từ file workspace: " + shown
                obj["questions"] = list(obj.get("questions") or [])
                if question not in obj["questions"]:
                    obj["questions"].append(question)
                return {"ok": True, "reason": "", "brief": obj, "asked": asked,
                        "normalization": filled, "proposed": [], "pending": question,
                        "files": list(files), "mapping": []}
        proposed = propose_validators(obj, originals)
        return {"ok": True, "reason": "", "brief": obj, "asked": asked,
                "normalization": filled, "proposed": proposed,
                "files": list(files) if files is not None else None,
                "mapping": [{"from": old, "path": path} for old, path in mapping]}


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
