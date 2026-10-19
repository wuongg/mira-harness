"""Check thoát 0 và tiêu chí được xác minh là hai việc khác nhau.

`check:` cũ vẫn chạy khi người dùng đã cấp lệnh. command_passed chỉ là mã thoát.
artifact_integrity chỉ là hash và run-id. criterion_verified chỉ khi một validator
xác định chạy đúng. Câu proves trùng tiêu chí là khai báo, không phải chứng minh.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_PREFIX = "check:"
_EXIT_ONLY = "chỉ mã thoát của lệnh này"
CRITERIA_SCHEMA = 1
_OBJECT_KEYS = {
    "schema", "id", "text", "cmd", "proves", "artifact", "validator",
    "outcome", "source_sha256", "source_path",
}
OUTCOMES = ("file_thay_doi", "ket_qua_moi", "nhan_dinh")


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
        "validator": None,
        "outcome": "",
        "source_sha256": "",
        "source_path": "",
    }


def _str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _rel_path(value: str) -> tuple[str | None, str]:
    rel = value.replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None, "artifact thoát khỏi gốc"
    return rel, ""


def _parse_validator(raw) -> tuple[dict | None, str]:
    if not isinstance(raw, dict):
        return None, "validator không phải object"
    kind = raw.get("kind")
    if kind == "contains":
        path, why = _rel_path(str(raw.get("path") or ""))
        must = raw.get("must_contain", [])
        ban = raw.get("must_not_contain", [])
        if path is None:
            return None, why
        if not _str_list(must) or not _str_list(ban) or not (must or ban):
            return None, "validator contains thiếu chuỗi"
        if set(raw) - {"kind", "path", "must_contain", "must_not_contain"}:
            return None, "validator có khóa lạ"
        return {"kind": "contains", "path": path, "must_contain": list(must),
                "must_not_contain": list(ban)}, ""
    if kind == "json_keys":
        path, why = _rel_path(str(raw.get("path") or ""))
        required = raw.get("required", [])
        forbidden = raw.get("forbidden", [])
        expect = raw.get("expect", "object")
        allow_empty = raw.get("allow_empty", False)
        if path is None:
            return None, why
        if not _str_list(required) or not _str_list(forbidden) or not required:
            return None, "validator json_keys thiếu khóa"
        if expect not in ("object", "array"):
            return None, "validator json_keys expect không hỗ trợ"
        if not isinstance(allow_empty, bool):
            return None, "validator json_keys allow_empty sai kiểu"
        if set(raw) - {"kind", "path", "required", "forbidden", "expect", "allow_empty"}:
            return None, "validator có khóa lạ"
        return {"kind": "json_keys", "path": path, "required": list(required),
                "forbidden": list(forbidden), "expect": expect,
                "allow_empty": allow_empty}, ""
    if kind == "shape":
        path, why = _rel_path(str(raw.get("path") or ""))
        suffixes = raw.get("suffixes", [])
        if path is None:
            return None, why
        if not _str_list(suffixes) or not suffixes:
            return None, "validator shape thiếu đuôi"
        if set(raw) - {"kind", "path", "suffixes", "non_empty"}:
            return None, "validator có khóa lạ"
        return {"kind": "shape", "path": path, "suffixes": list(suffixes),
                "non_empty": bool(raw.get("non_empty", False))}, ""
    if kind == "behavior":
        cmd = raw.get("cmd")
        expects = raw.get("expects_exit", 0)
        stdout = raw.get("expects_stdout", "")
        limit = raw.get("does_not_prove", "")
        if not isinstance(cmd, str) or not cmd.strip():
            return None, "validator behavior thiếu lệnh"
        if not isinstance(expects, int) or not isinstance(stdout, str) or not isinstance(limit, str):
            return None, "validator behavior sai kiểu"
        if not stdout.strip() or not limit.strip():
            return None, "validator behavior thiếu đầu ra hoặc giới hạn"
        if set(raw) - {"kind", "cmd", "expects_exit", "expects_stdout", "does_not_prove"}:
            return None, "validator có khóa lạ"
        return {"kind": "behavior", "cmd": cmd.strip(), "expects_exit": expects,
                "expects_stdout": stdout, "does_not_prove": limit.strip()}, ""
    return None, "không có validator phù hợp"


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
    rel = ""
    if artifact.strip():
        rel, why = _rel_path(artifact)
        if rel is None:
            return None, why
    validator = None
    if "validator" in raw and raw.get("validator") not in (None, ""):
        validator, why = _parse_validator(raw.get("validator"))
        if validator is None:
            return None, why
    outcome = raw.get("outcome", "")
    if outcome not in ("", *OUTCOMES):
        return None, "outcome không hỗ trợ"
    source_sha = raw.get("source_sha256", "")
    source_path = raw.get("source_path", "")
    if not isinstance(source_sha, str) or not isinstance(source_path, str):
        return None, "nguồn file gốc sai kiểu"
    source_rel = ""
    if source_path.strip():
        source_rel, why = _rel_path(source_path)
        if source_rel is None:
            return None, why
    return {
        "schema": CRITERIA_SCHEMA,
        "id": cid.strip(),
        "text": text.strip(),
        "cmd": cmd.strip(),
        "proves": proves.strip(),
        "artifact": rel,
        "validator": validator,
        "outcome": outcome,
        "source_sha256": source_sha.strip(),
        "source_path": source_rel,
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


def criterion_commands(raw) -> list[str]:
    parsed, _why = validate_criteria([raw])
    if not parsed:
        return []
    item = parsed[0]
    cmds = [item["cmd"]] if item["cmd"] else []
    validator = item.get("validator") or {}
    if validator.get("kind") == "behavior" and validator.get("cmd"):
        cmds.append(validator["cmd"])
    return cmds


def criterion_command(raw) -> str | None:
    cmds = criterion_commands(raw)
    return cmds[0] if cmds else None


def _shell_result(cmd: str, root: Path):
    from .tools import Session

    def approve(tool: str, args: dict) -> bool:
        return tool == "run_shell" and str(args.get("cmd") or "") == cmd

    return Session(root=root, mode="default", approve=approve).run_shell_result(cmd, timeout=30)


def _through_shell(cmd: str, root: Path) -> tuple[str, int | None, str, str]:
    result = _shell_result(cmd, root)
    text = result.display
    if result.permission in ("denied", "blocked"):
        return "blocked", None, text.splitlines()[0], text
    if result.timed_out or result.permission == "error" or result.exit_code is None:
        reason = text.splitlines()[0] if text else "run_shell không trả mã thoát"
        return "unproven", result.exit_code, reason, text
    if result.exit_code == 0:
        return "checked", result.exit_code, "lệnh check thoát 0", text
    return "failed", result.exit_code, f"lệnh check thoát {result.exit_code}", text


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


def _read_inside(root: Path, rel: str) -> tuple[Path | None, str]:
    path = (root / rel).resolve()
    base = root.resolve()
    if path != base and base not in path.parents:
        return None, "path thoát khỏi gốc"
    if not path.is_file():
        return None, "không có file"
    return path, ""


def _text_sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def source_changed(item: dict, root: Path | None) -> bool:
    """file_thay_doi chỉ đúng khi file khác bản gốc."""
    if item.get("outcome") != "file_thay_doi":
        return True
    rel = item.get("source_path") or (item.get("validator") or {}).get("path") or ""
    if not rel or root is None or not root.is_dir():
        return False
    path, _why = _read_inside(root, rel)
    if path is None:
        return False
    current = _text_sha(path.read_text(encoding="utf-8", errors="replace"))
    original = item.get("source_sha256") or ""
    if not original:
        return True
    return current != original


def _apply_validator(spec: dict, root: Path | None, allowed: set[str]) -> dict:
    """Trả proves là việc kiểm thật sự làm. Claim của người dùng không được chép vào đây."""
    kind = spec["kind"]
    if kind == "behavior":
        cmd = spec["cmd"]
        if cmd not in allowed:
            return {"state": "pending", "verified": False, "command_passed": False,
                    "reason": "tiêu chí do model đề xuất — chưa được cấp quyền chạy",
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        if root is None or not root.is_dir():
            return {"state": "blocked", "verified": False, "command_passed": False,
                    "reason": "không có thư mục gốc để đưa vào run_shell",
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        result = _shell_result(cmd, root)
        if result.permission in ("denied", "blocked"):
            return {"state": "blocked", "verified": False, "command_passed": False,
                    "reason": result.display.splitlines()[0],
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        if result.timed_out:
            return {"state": "unverified", "verified": False, "command_passed": False,
                    "reason": "lệnh quá thời gian, đầu ra chưa đủ để kết luận",
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        if result.permission == "error" or result.exit_code is None:
            return {"state": "unproven", "verified": False, "command_passed": False,
                    "reason": result.display.splitlines()[0] if result.display else "không có mã thoát",
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        exit_ok = result.exit_code == spec["expects_exit"]
        found = spec["expects_stdout"] in result.stdout
        if result.truncated and not found:
            return {"state": "unverified", "verified": False, "command_passed": exit_ok,
                    "reason": "đầu ra bị cắt, chưa đủ để kết luận",
                    "proves": "", "does_not_prove": spec["does_not_prove"]}
        passed = exit_ok and found
        if not passed and exit_ok:
            reason = "đầu ra không chứa chuỗi đã khai"
        elif passed:
            reason = "lệnh được cấp quyền cho đúng mã thoát và chuỗi đầu ra"
        else:
            reason = f"lệnh check thoát {result.exit_code}"
        return {
            "state": "verified" if passed else "failed",
            "verified": passed,
            "command_passed": passed,
            "reason": reason,
            "proves": "mã thoát và một chuỗi trên stdout đã khai",
            "does_not_prove": spec["does_not_prove"],
        }
    if root is None or not root.is_dir():
        return {"state": "blocked", "verified": False, "command_passed": False,
                "reason": "không có thư mục gốc", "proves": "", "does_not_prove": ""}
    path, why = _read_inside(root, spec["path"])
    if path is None:
        return {"state": "failed", "verified": False, "command_passed": False,
                "reason": why, "proves": "", "does_not_prove": ""}
    if kind == "contains":
        body = path.read_text(encoding="utf-8", errors="replace")
        missing = [bit for bit in spec["must_contain"] if bit not in body]
        present = [bit for bit in spec["must_not_contain"] if bit in body]
        ok = not missing and not present
        return {
            "state": "verified" if ok else "failed",
            "verified": ok,
            "command_passed": False,
            "reason": "đủ chuỗi đã khai" if ok else "thiếu hoặc còn chuỗi bị cấm",
            "proves": "file chứa hoặc không chứa các chuỗi đã khai",
            "does_not_prove": "không chạy mã và không suy ra hành vi",
        }
    if kind == "json_keys":
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"state": "failed", "verified": False, "command_passed": False,
                    "reason": "không phải JSON", "proves": "",
                    "does_not_prove": "không kiểm giá trị ngoài khóa đã khai"}

        def keys_ok(item) -> bool:
            return (isinstance(item, dict)
                    and all(key in item for key in spec["required"])
                    and not any(key in item for key in spec["forbidden"]))

        if spec["expect"] == "object":
            ok = keys_ok(loaded)
            reason = "object đủ khóa đã khai" if ok else "JSON lệch khóa hoặc không phải object"
            proves = "object JSON có đúng các khóa đã khai"
        elif not isinstance(loaded, list):
            ok = False
            reason = "JSON không phải mảng"
            proves = ""
        elif not loaded and not spec.get("allow_empty"):
            ok = False
            reason = "mảng rỗng không được cho phép"
            proves = ""
        else:
            bad = [item for item in loaded if not keys_ok(item)]
            ok = not bad
            reason = ("từng phần tử là object và đủ khóa đã khai" if ok
                      else "phần tử không phải object hoặc lệch khóa")
            proves = "từng phần tử là object và có đúng các khóa đã khai"
        return {
            "state": "verified" if ok else "failed",
            "verified": ok,
            "command_passed": False,
            "reason": reason,
            "proves": proves,
            "does_not_prove": "không kiểm giá trị ngoài khóa đã khai",
        }
    if kind == "shape":
        ok = any(path.name.endswith(suffix) for suffix in spec["suffixes"])
        if spec["non_empty"] and path.stat().st_size == 0:
            ok = False
        return {
            "state": "verified" if ok else "failed",
            "verified": ok,
            "command_passed": False,
            "reason": "đúng đuôi file đã khai" if ok else "sai đuôi hoặc file trống",
            "proves": "file tồn tại và đúng đuôi đã khai",
            "does_not_prove": "không kiểm nội dung file",
        }
    return {"state": "unverified", "verified": False, "command_passed": False,
            "reason": "không có validator phù hợp", "proves": "", "does_not_prove": ""}


def _validator_sha(spec: dict) -> str:
    blob = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _manifest(root: Path) -> list[dict]:
    rows = []
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        rel = item.relative_to(root).as_posix()
        rows.append({"path": rel, "sha256": hashlib.sha256(item.read_bytes()).hexdigest()})
    return rows


def bind_evidence(spec: dict, root: Path, brief_hash: str) -> dict:
    """Hash đúng phần đã kiểm. Behavior là manifest của cả cây, không phải một file."""
    record = {
        "brief_hash": brief_hash,
        "validator_sha256": _validator_sha(spec),
        "scope": "file",
        "paths": [],
        "tree_sha256": "",
    }
    if spec.get("kind") == "behavior":
        from .team import tree_hash
        record["scope"] = "tree"
        record["paths"] = _manifest(root)
        record["tree_sha256"] = tree_hash(root)
        return record
    rel = str(spec.get("path") or "")
    digest = ""
    path, _why = _read_inside(root, rel) if rel else (None, "")
    if path is not None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record["paths"] = [{"path": rel, "sha256": digest}]
    return record


def _paths_match(stored_paths: list, cwd: Path) -> bool:
    if not stored_paths:
        return False
    for item in stored_paths:
        rel = str(item.get("path") or "")
        digest = str(item.get("sha256") or "")
        file = cwd / rel
        if not digest or not file.is_file():
            return False
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            return False
    return True


def _evidence_matches(stored: dict, current: dict, cwd: Path, exact_tree: bool) -> bool:
    if stored.get("brief_hash") != current.get("brief_hash"):
        return False
    if stored.get("validator_sha256") != current.get("validator_sha256"):
        return False
    if stored.get("scope") != current.get("scope"):
        return False
    if stored.get("scope") == "tree":
        if exact_tree:
            return bool(stored.get("tree_sha256")) and stored.get("tree_sha256") == current.get("tree_sha256")
        return _paths_match(list(stored.get("paths") or []), cwd)
    stored_paths = {(item.get("path"), item.get("sha256")) for item in stored.get("paths") or []}
    current_paths = {(item.get("path"), item.get("sha256")) for item in current.get("paths") or []}
    return bool(stored_paths) and stored_paths == current_paths and all(item[1] for item in stored_paths)


def refresh_evidence(rows: list[dict], cwd: Path, brief_hash: str, criteria: list,
                     exact_tree: bool = True) -> list[dict]:
    """Đối chiếu hash đã lưu. Không chạy lại lệnh."""
    parsed, _why = validate_criteria(criteria)
    by_id = {item["id"]: item for item in parsed or []}
    root = Path(cwd)
    for row in rows:
        if not row.get("criterion_verified"):
            continue
        spec = (by_id.get(row.get("criterion_id")) or {}).get("validator")
        stored = row.get("evidence")
        if not isinstance(stored, dict) or not spec or not root.is_dir():
            row["evidence_status"] = "chưa kiểm lại"
            row["criterion_verified"] = False
            row["state"] = "chưa kiểm lại"
            row["reason"] = "chưa kiểm lại kết quả tự động"
            row["does_not_prove"] = row["reason"]
            continue
        current = bind_evidence(spec, root, brief_hash)
        if _evidence_matches(stored, current, root, exact_tree):
            row["evidence_status"] = "còn hiệu lực"
            continue
        row["evidence_status"] = "hết hiệu lực"
        row["criterion_verified"] = False
        row["state"] = "hết hiệu lực"
        row["reason"] = "artifact đã đổi, kết quả tự động hết hiệu lực"
        row["does_not_prove"] = row["reason"]
    return rows


def judge_obligations(criteria: list, steps: list[dict] | None = None,
                      evidence: dict | None = None, *, cwd: Path | None = None,
                      granted: set[str] | None = None, run_id: str | None = None,
                      artifacts: dict | None = None, validators: bool = True,
                      brief_hash: str = "", surface: str = "") -> list[dict]:
    """steps và diff không phải proof. Hash chỉ là danh tính file. proves trùng câu là khai báo."""
    del steps, evidence
    allowed = set(granted or ())
    root = Path(cwd).resolve() if cwd is not None else None
    parsed, why = validate_criteria(criteria)
    if parsed is None:
        return [{
            "criterion": "", "criterion_id": "", "kind": "manual", "proves": "",
            "does_not_prove": "", "artifact": None, "claim": "",
            "check_passed": False, "command_passed": False,
            "artifact_integrity": False, "criterion_verified": False,
            "state": "blocked", "reason": why, "ref": None,
        }]
    rows = []
    for item in parsed:
        cmd = item["cmd"] or None
        bound = None
        integrity = False
        if item["artifact"] and root is not None and run_id:
            bound = _bound_artifact(root, item["artifact"], run_id, artifacts)
            integrity = bound is not None
        command_passed = False
        exit_code = None
        command_state = ""
        command_reason = ""
        if cmd:
            if cmd not in allowed:
                command_state = "pending"
                command_reason = "tiêu chí do model đề xuất — chưa được cấp quyền chạy"
            elif root is None or not root.is_dir():
                command_state = "blocked"
                command_reason = "không có thư mục gốc để đưa vào run_shell"
            else:
                command_state, exit_code, command_reason, _shown = _through_shell(cmd, root)
                command_passed = command_state == "checked"
        validator = item.get("validator")
        applied = None
        if validator and not validators:
            applied = {"state": "unverified", "verified": False, "command_passed": False,
                       "reason": "validator không chạy vì brief không phải của người dùng",
                       "proves": "", "does_not_prove": "không chứng minh tiêu chí"}
        elif validator:
            applied = _apply_validator(validator, root, allowed)
            if applied.get("command_passed"):
                command_passed = True
        verified = bool(applied and applied.get("verified"))
        if item.get("outcome") == "ket_qua_moi" and (item.get("validator") or {}).get("kind") == "contains":
            banned = ((item.get("validator") or {}).get("must_not_contain") or [])
            if not banned:
                verified = False
                applied = {
                    "state": "failed", "verified": False, "command_passed": False,
                    "reason": "ket_qua_moi thiếu giá trị cũ",
                    "proves": "", "does_not_prove": "không chứng minh nội dung mới",
                }
        if verified and not source_changed(item, root):
            verified = False
            applied = {
                "state": "failed", "verified": False, "command_passed": False,
                "reason": "file không khác file gốc",
                "proves": "", "does_not_prove": "không chứng minh file đã đổi",
            }
        if command_state == "pending" and not verified:
            state = "pending"
            reason = command_reason
        elif applied and applied["state"] in (
                "pending", "failed", "blocked", "verified", "unverified"):
            state = "verified" if verified else applied["state"]
            reason = applied["reason"]
        elif command_state == "blocked":
            state, reason = "blocked", command_reason
        elif command_state == "failed":
            state, reason = "failed", command_reason
        elif command_state == "unproven":
            state, reason = "unproven", command_reason
        elif command_passed or integrity:
            state = "unverified"
            reason = "lệnh hoặc hash không chứng minh câu tiêu chí"
        elif not cmd and not validator:
            state = "needs_confirmation"
            reason = "tiêu chí không kiểm tự động, cần xác nhận"
        else:
            state = "unverified"
            reason = "không có validator phù hợp"
        proves = (applied or {}).get("proves") or (_EXIT_ONLY if command_passed else "")
        bound_evidence = None
        evidence_status = ""
        if validator and root is not None and root.is_dir():
            bound_evidence = bind_evidence(validator, root, brief_hash)
            if verified:
                evidence_status = "còn hiệu lực"
        staged_hash = ""
        if surface == "staged" and validator and root is not None:
            rel = str(validator.get("path") or "")
            file = (root / rel) if rel else None
            if file is not None and file.is_file():
                staged_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        rows.append({
            "criterion": item["text"],
            "criterion_id": item["id"],
            "kind": (validator or {}).get("kind") if validator else ("command" if cmd else "manual"),
            "claim": item.get("proves") or "",
            "proves": proves,
            "does_not_prove": (applied or {}).get("does_not_prove") or "",
            "artifact": bound,
            "evidence": bound_evidence,
            "evidence_status": evidence_status,
            "check_passed": command_passed,
            "command_passed": command_passed,
            "artifact_integrity": integrity,
            "criterion_verified": verified,
            "state": state,
            "reason": reason,
            "checked_on": "staged" if surface == "staged" else "",
            "staged_hash": staged_hash,
            "ref": {"kind": "check", "criterion_id": item["id"], "cmd": cmd,
                    "via": "run_shell", "exit": exit_code} if cmd else None,
        })
    return rows


def unproven(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not row.get("criterion_verified")]
