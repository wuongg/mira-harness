"""Đo bộ nghiệm thu. API trả phí chỉ mở cho host OpenAI đã duyệt ngân sách."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALUE = ROOT / "eval" / "value"
TASKS = VALUE / "tasks"
CHECKS = VALUE / "checks"
FREEZE = VALUE / "frozen.sha256"
PROBE = VALUE / "probe.json"
CANARY = "MIRAVALUECANARY7f3a"
OFFICIAL_MODEL = "claude-sonnet-5-5"
# Bản ghi lần đối chiếu Anthropic 2026-10-14. Probe đọc model từ probe.json, không từ hằng này.
OFFICIAL = {
    "provider": "anthropic",
    "model": OFFICIAL_MODEL,
    "endpoint": "https://api.anthropic.com/v1/messages",
    "price_in_usd_per_mtok": 2.0,
    "price_out_usd_per_mtok": 10.0,
    "cache_write_5m_usd_per_mtok": 2.5,
    "cache_write_1h_usd_per_mtok": 4.0,
    "cache_read_usd_per_mtok": 0.1,
    "source": "https://platform.claude.com/docs/en/models/sonnet-5-5/overview",
    "pricing_source": "https://platform.claude.com/docs/en/about-claude/pricing",
    "verified_on": "2026-10-14",
}
PROGRESS_SCHEMA = 1
OPENAI_BASE = "https://api.openai.com"
BUDGET_LINE = "DUYỆT NGÂN SÁCH: (a) OpenAI rẻ, trần $2"
USER_ACTIONS = ("approve", "grant", "confirm", "change", "retry", "kill", "resume", "new_run", "run")


def canonical_bytes(raw: bytes) -> bytes:
    """Văn bản UTF-8 chuẩn hóa newline. Nhị phân giữ nguyên byte."""
    if b"\0" in raw:
        return raw
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return raw.replace(b"\r\n", b"\n")


def file_digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path.read_bytes())).hexdigest()


def _rel_files() -> list[Path]:
    files = sorted(CHECKS.glob("V*.py"))
    files += sorted(TASKS.glob("*/task.json"))
    files += sorted(path for path in TASKS.glob("*/workspace/*") if path.is_file())
    return files


def freeze_text() -> str:
    lines = []
    for path in _rel_files():
        lines.append(f"{file_digest(path)}  {path.relative_to(VALUE).as_posix()}")
    return "\n".join(lines) + "\n"


def verify_freeze() -> str:
    current = freeze_text()
    saved = FREEZE.read_text(encoding="utf-8").replace("\r\n", "\n") if FREEZE.is_file() else ""
    if current != saved:
        raise SystemExit("đóng băng không khớp")
    return current


def harness_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def load_tasks() -> list[dict]:
    rows = []
    for path in sorted(TASKS.glob("*/task.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        spec["id"] = path.parent.name
        spec["workspace"] = path.parent / "workspace"
        spec["check"] = CHECKS / f"{spec['id']}.py"
        rows.append(spec)
    if len(rows) != 12:
        raise SystemExit(f"cần 12 nhiệm vụ, thấy {len(rows)}")
    return rows


def run_check_result(spec: dict, workspace: Path, timeout: int = 30) -> dict:
    """status pass/fail là kết quả nhiệm vụ. error là lỗi phép kiểm hoặc hạ tầng."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(spec["check"]), str(workspace)],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        err = (exc.stderr or b"")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return {"exit": None, "status": "error", "reason": "timeout " + err[-400:]}
    except OSError as exc:
        return {"exit": None, "status": "error", "reason": f"không chạy phép kiểm: {exc}"}
    err = proc.stderr or ""
    if proc.returncode == 0 and "Traceback" not in err:
        return {"exit": 0, "status": "pass", "reason": ""}
    if proc.returncode == 1 and "Traceback" not in err:
        return {"exit": 1, "status": "fail", "reason": ""}
    reason = err.strip() or f"exit {proc.returncode}"
    return {"exit": proc.returncode, "status": "error", "reason": reason[-400:]}


def run_check(spec: dict, workspace: Path) -> int:
    result = run_check_result(spec, workspace)
    if result["status"] == "pass":
        return 0
    if result["status"] == "fail":
        return 1
    return 2


def classify(expect: str, delivered: bool, check, side_effect: bool) -> str:
    """Một nhãn. check là 0, 1, hoặc 'error'. Không phải điểm thông minh."""
    if check == "error":
        return "check_error"
    if expect != "deliver" and delivered:
        return "withhold_violated"
    if side_effect:
        return "side_effect"
    if delivered and check != 0:
        return "false_complete"
    if expect == "deliver" and delivered and check == 0:
        return "completed_correct"
    if expect == "deliver" and not delivered and check == 0:
        return "false_block"
    if expect != "deliver" and not delivered and check == 0:
        return "correct_withhold"
    return "not_complete"


def snapshot(root: Path) -> dict[str, str]:
    found = {}
    if not root.is_dir():
        return found
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".frog/") or rel.startswith(".mira/") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        found[rel] = file_digest(path)
    return found


def workspace_delta(before: dict[str, str], after: dict[str, str], mutable: list[str]) -> dict:
    allowed = set(mutable or [])
    added = sorted(rel for rel in after if rel not in before and rel not in allowed)
    deleted = sorted(rel for rel in before if rel not in after)
    modified = sorted(
        rel for rel in before
        if rel in after and before[rel] != after[rel] and rel not in allowed)
    return {"added": added, "deleted": deleted, "modified": modified}


def support_for(spec: dict, config: str) -> dict:
    needs = {
        "change": bool(spec.get("change")),
        "interrupt": spec["id"] == "V11",
        "missing_grant": spec["id"] == "V12",
    }
    if config == "A":
        return {key: ("in_scenario" if value else "not_in_scenario") for key, value in needs.items()}
    return {key: ("not_applicable" if value else "not_in_scenario") for key, value in needs.items()}


def comparable(spec: dict) -> bool:
    return not spec.get("change") and spec["id"] not in {"V11", "V12"}


class _Stub(BaseHTTPRequestHandler):
    brief = {}
    hits = 0
    script: list[int] = []
    usage = True
    hold = False

    def log_message(self, *_args):
        return

    def do_POST(self):
        _Stub.hits += 1
        n = int(self.headers.get("content-length", 0))
        raw_req = self.rfile.read(n) or b"{}"
        code = _Stub.script.pop(0) if _Stub.script else 200
        if code != 200:
            body = b'{"error":"stub"}'
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if _Stub.hold:
            while _Stub.hold:
                time.sleep(0.05)
            return
        req = json.loads(raw_req.decode("utf-8"))
        blob = json.dumps(req, ensure_ascii=False)
        if "INTAKE" in blob:
            text = json.dumps(_Stub.brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        else:
            text = '<tool>{"name":"finish","args":{"summary":"khong sua"}}</tool>'
        body = {"content": [{"type": "text", "text": text}]}
        if _Stub.usage:
            body["usage"] = {"input_tokens": 20, "output_tokens": 10}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve(brief: dict):
    _Stub.brief = brief
    _Stub.hits = 0
    _Stub.script = []
    _Stub.usage = True
    _Stub.hold = False
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT)
    env["ANTHROPIC_API_KEY"] = CANARY
    for name in list(env):
        if name != "ANTHROPIC_API_KEY" and ("KEY" in name or "TOKEN" in name or "SECRET" in name):
            env.pop(name, None)
        if name.startswith("FROG_PRICE") or name.startswith("MIRA_PRICE"):
            env.pop(name, None)
    env.pop("FROG_PAUSE", None)
    env.pop("FROG_PAUSE_FLAG", None)
    env.pop("MIRA_PAUSE", None)
    env.pop("MIRA_PAUSE_FLAG", None)
    if extra:
        env.update(extra)
    return env


def _assert_local(base: str) -> None:
    if not base.startswith("http://127.0.0.1:"):
        raise SystemExit("smoke chỉ được gọi 127.0.0.1")


def _run(args: list[str], cwd: Path, env: dict, timeout: int = 90):
    before = _Stub.hits
    started = time.perf_counter()
    proc = subprocess.run(
        args, cwd=str(cwd), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout)
    elapsed = time.perf_counter() - started
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc, _Stub.hits - before, elapsed, text


def _giao(cwd: Path, base: str, bits: list[str], env: dict | None = None, timeout: int = 90,
          max_tokens: str = "256", price: str = "1000,0",
          provider: str = "anthropic", model: str = "claude-test"):
    cmd = [sys.executable, "-m", "frog", "giao", *bits, "--cwd", str(cwd),
           "--provider", provider, "--base-url", base, "--model", model,
           "--price-in", price, "--max-tokens", max_tokens]
    return _run(cmd, cwd, env or _env(), timeout)


def budget_line_present(report_text: str | None = None) -> bool:
    if report_text is None:
        path = ROOT / "docs" / "history" / "OVERNIGHT-REPORT.md"
        report_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return any(line.strip() == BUDGET_LINE for line in report_text.splitlines())


def _openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or ""
    if key:
        return key
    if os.name != "nt":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            value, _ = winreg.QueryValueEx(reg, "OPENAI_API_KEY")
    except OSError:
        return ""
    return value or ""


def _openai_child_env() -> dict | None:
    key = _openai_key()
    if not key:
        return None
    env = _env()
    env.pop("ANTHROPIC_API_KEY", None)
    env["OPENAI_API_KEY"] = key
    return env


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[REDACTED]")
    return text


def _team(cwd: Path, base: str, spec: dict, brief_path: Path):
    cmd = [sys.executable, "-m", "frog", "team", spec["prompt"],
           "--brief", str(brief_path), "--intake", "off", "--surface", "write_sandbox",
           "--records", "50", "--dollars", "0", "--reversibility", "C1",
           "--oracle", "off", "--require-evidence",
           "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
           "--price-in", "1000,0", "--max-tokens", "256"]
    return _run(cmd, cwd, _env(), 90)


def _run_id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    return ""


def _claimed(text: str) -> bool:
    return "bàn giao: đủ" in text or "bàn giao: người dùng xác nhận" in text


def canary_in(text: str) -> bool:
    return CANARY in text


def _ledger(dest: Path) -> dict:
    runs = dest / ".frog" / "runs"
    if not runs.is_dir():
        return {}
    newest = None
    for path in runs.glob("*/handoff.json"):
        if newest is None or path.stat().st_mtime >= newest.stat().st_mtime:
            newest = path
    if newest is None:
        for path in runs.glob("*/checkpoint.json"):
            if newest is None or path.stat().st_mtime >= newest.stat().st_mtime:
                newest = path
    if newest is None:
        return {}
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    ledger = data.get("ledger") or {}
    if "total_in" in ledger or "uncertain_usd" in ledger:
        return ledger
    return {}


def _event(events: list, action: str, ok: bool, detail: str = "") -> None:
    events.append({"action": action, "issued": True, "ok": bool(ok), "detail": detail})


def smoke_task(spec: dict, base: str, config: str, dest: Path, sha: str) -> dict:
    dest = Path(dest).resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(spec["workspace"], dest)
    before = snapshot(dest)
    brief_path = dest.parent / f"{spec['id']}-brief.json"
    brief_path.write_text(json.dumps(spec["brief"], ensure_ascii=False), encoding="utf-8")
    events: list[dict] = []
    calls = 0
    elapsed = 0.0
    logs = []
    delivered = False
    exit_code = None
    interrupt_status = "not_in_scenario"
    if config == "B":
        proc, hits, dur, text = _team(dest, base, spec, brief_path)
        calls += hits
        elapsed += dur
        logs.append(text)
        exit_code = proc.returncode
        delivered = proc.returncode == 0 and "đã làm" in text
        _event(events, "run", proc.returncode == 0, "team")
        if spec["id"] == "V11":
            interrupt_status = "not_applicable"
    else:
        proc, hits, dur, text = _giao(dest, base, [spec["prompt"], "--approve-brief"])
        calls += hits
        elapsed += dur
        logs.append(text)
        run = _run_id(text)
        _event(events, "approve", bool(run), run)
        if spec["id"] == "V11":
            before_hits = _Stub.hits
            started = time.perf_counter()
            flag = dest / ".frog" / "pause.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            if flag.exists():
                flag.unlink()
            cmd = [sys.executable, "-m", "frog", "giao", "--run", run, "--cwd", str(dest),
                   "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
                   "--price-in", "1000,0", "--max-tokens", "256"]
            proc_p = subprocess.Popen(
                cmd, cwd=str(dest),
                env=_env({"FROG_PAUSE": "before-promote", "FROG_PAUSE_FLAG": str(flag)}),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.time() + 25
            while time.time() < deadline and not flag.exists():
                if proc_p.poll() is not None:
                    break
                time.sleep(0.05)
            reached = flag.exists()
            if reached:
                proc_p.kill()
            proc_p.wait(timeout=10)
            out = (proc_p.stdout.read() if proc_p.stdout else b"").decode("utf-8", "replace")
            err = (proc_p.stderr.read() if proc_p.stderr else b"").decode("utf-8", "replace")
            if proc_p.stdout:
                proc_p.stdout.close()
            if proc_p.stderr:
                proc_p.stderr.close()
            text = out + "\n" + err
            logs.append(text)
            calls += _Stub.hits - before_hits
            elapsed += time.perf_counter() - started
            interrupt_status = "reached" if reached else "not_reached"
            _event(events, "run", True, run)
            _event(events, "kill", reached, interrupt_status)
            delivered = _claimed(text)
        else:
            grant_bits = ["--run", run]
            if spec["id"] == "V12":
                detail = "no-grant"
            else:
                detail = run
            proc, hits, dur, text = _giao(dest, base, grant_bits)
            calls += hits
            elapsed += dur
            logs.append(text)
            exit_code = proc.returncode
            _event(events, "run", proc.returncode not in (2,), detail)
            delivered = _claimed(text)
            if spec.get("change"):
                proc, hits, dur, text = _giao(dest, base, ["--run", run, "--change", spec["change"]])
                calls += hits
                elapsed += dur
                logs.append(text)
                guided = "Tạo run mới" in text
                _event(events, "change", guided, "guidance" if guided else "rejected")
                if guided:
                    proc, hits, dur, text = _giao(
                        dest, base, [spec["change"], "--previous", run, "--approve-brief"])
                    calls += hits
                    elapsed += dur
                    logs.append(text)
                    new_id = _run_id(text)
                    _event(events, "new_run", bool(new_id), new_id)
                    _event(events, "approve", bool(new_id), new_id)
                    if new_id:
                        proc, hits, dur, text = _giao(dest, base, ["--run", new_id])
                        calls += hits
                        elapsed += dur
                        logs.append(text)
                        exit_code = proc.returncode
                        _event(events, "run", proc.returncode not in (2,), new_id)
                        delivered = _claimed(text)
    blob = "\n".join(logs)
    checked = run_check_result(spec, dest)
    check_value = "error" if checked["status"] == "error" else checked["exit"]
    delta = workspace_delta(before, snapshot(dest), list(spec.get("mutable") or []))
    side = delta["added"] + delta["deleted"] + delta["modified"]
    ledger = _ledger(dest)
    if exit_code == 2 and not any(item["action"] == "new_run" for item in events):
        outcome = "not_run"
    else:
        outcome = classify(spec["expect"], delivered, check_value, bool(side))
    issued = [item for item in events if item["issued"] and item["action"] in USER_ACTIONS]
    return {
        "id": spec["id"],
        "config": config,
        "harness_sha": sha,
        "trial_config": {
            "name": config,
            "provider": "fake",
            "model": "claude-test",
            "base_host": "127.0.0.1",
            "max_tokens": 256,
            "price_in_per_mtok": 1000,
            "price_out_per_mtok": 0,
            "oracle": "off",
            "require_evidence": True,
        },
        "provider": "fake",
        "model_quality": "not_evaluated",
        "expect": spec["expect"],
        "comparable": comparable(spec),
        "support": support_for(spec, config),
        "harness_exit": exit_code,
        "interrupt_status": interrupt_status,
        "events": events,
        "intervention_count": len(issued),
        "retries": sum(1 for item in events if item["action"] == "retry"),
        "harness_claimed_delivery": delivered,
        "check_exit": checked["exit"],
        "check_status": checked["status"],
        "check_reason": checked["reason"],
        "outcome": outcome,
        "http_calls": calls,
        "usage_in": ledger.get("total_in"),
        "usage_out": ledger.get("total_out"),
        "usage_usd": ledger.get("total_usd"),
        "uncertain_usd": ledger.get("uncertain_usd"),
        "seconds": round(elapsed, 3),
        "side_effect": delta,
        "canary_leaked": canary_in(blob),
        "canary_note": "chỉ báo canary của lần chạy này có trong log hay không, không chứng minh không rò bí mật khác",
        "cost_note": "usage của provider giả, không phải hóa đơn",
        "effect_note": "số HTTP của A gồm intake và verifier; chưa tách riêng từng cổng",
    }


def smoke(config: str, only: str | None = None) -> dict:
    verify_freeze()
    tasks = load_tasks()
    if only:
        tasks = [item for item in tasks if item["id"] == only]
    sha = harness_sha()
    srv, base = _serve(tasks[0]["brief"])
    _assert_local(base)
    rows = []
    try:
        base_dir = Path(tempfile.mkdtemp(prefix="frog-value-smoke-"))
        for spec in tasks:
            _Stub.brief = spec["brief"]
            rows.append(smoke_task(spec, base, config, base_dir / spec["id"], sha))
    finally:
        srv.shutdown()
        srv.server_close()
    return {
        "config": config,
        "harness_sha": sha,
        "provider": "fake",
        "model_quality": "not_evaluated",
        "rows": rows,
    }


def toml_model_names() -> set[str]:
    text = (ROOT / "frog" / "prices.toml").read_text(encoding="utf-8")
    return set(re.findall(r'\[models\."([^"]+)"\]', text))


def validate_probe_model(model: str, provider: str) -> None:
    """Model và provider lấy từ probe.json. Không ghim một nhà cung cấp trong code."""
    if model in toml_model_names():
        raise SystemExit("tên trong prices.toml không phải API ID")
    if not str(model).strip() or not str(provider).strip():
        raise SystemExit("probe thiếu model hoặc provider")


def load_probe() -> dict:
    data = json.loads(PROBE.read_text(encoding="utf-8"))
    validate_probe_model(str(data.get("model") or ""), str(data.get("provider") or ""))
    for key in ("endpoint", "official_source", "pricing_source", "verified_on", "billing"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise SystemExit("probe.json thiếu nguồn đã ghi")
    if data["billing"] not in ("per_token", "prepaid_credit"):
        raise SystemExit("probe.json thiếu cơ chế tính tiền")
    for key in ("price_in_usd_per_mtok", "price_out_usd_per_mtok", "cache_read_usd_per_mtok"):
        if not isinstance(data.get(key), (int, float)):
            raise SystemExit("probe.json thiếu giá")
    return data


def probe_block_reason(approve_spend: bool, base_url: str | None,
                        report_text: str | None = None) -> str:
    if not approve_spend:
        return "locked"
    if not base_url:
        return "missing-base-url"
    if base_url.startswith("http://127.0.0.1:"):
        return ""
    if base_url.rstrip("/") == OPENAI_BASE and budget_line_present(report_text):
        return ""
    return "paid-api-not-approved"


def _progress(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(state, ensure_ascii=False, indent=2)
    if canary_in(blob):
        blob = blob.replace(CANARY, "[redacted]")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(blob, encoding="utf-8")
    os.replace(tmp, path)


def _ledger_view(data: dict) -> dict | None:
    ledger = data.get("ledger") or {}
    if "requests" not in ledger and "total_usd" not in ledger:
        return None
    return {
        "run_id": str(data.get("id") or ""),
        "attempt": int(data.get("attempt") or 1),
        "total_usd": float(ledger.get("total_usd") or 0),
        "reserved": float(ledger.get("reserved") or 0),
        "uncertain_usd": float(ledger.get("uncertain_usd") or 0),
        "total_in": int(ledger.get("total_in") or 0),
        "total_out": int(ledger.get("total_out") or 0),
        "requests": list(ledger.get("requests") or []),
        "steps": list(data.get("steps") or []),
    }


def _richer(new: dict, old: dict) -> bool:
    def score(item: dict) -> tuple:
        committed = item["total_usd"] + item["reserved"] + item["uncertain_usd"]
        return (len(item["requests"]), len(item["steps"]), committed)
    return score(new) >= score(old)


def collect_run_ledgers(dest: Path) -> list[dict]:
    """Một snapshot mới của cùng run/attempt thay snapshot cũ, không cộng thêm."""
    runs = dest / ".frog" / "runs"
    found: dict[str, dict] = {}
    if not runs.is_dir():
        return []
    for path in runs.glob("*/*"):
        if path.name not in ("handoff.json", "checkpoint.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        view = _ledger_view(data)
        if view is None:
            continue
        if not view["run_id"]:
            view["run_id"] = path.parent.name
        key = f"{view['run_id']}:{view['attempt']}"
        old = found.get(key)
        if old is None or _richer(view, old):
            found[key] = view
    return list(found.values())


def send_count(view: dict) -> int:
    """Số lần urlopen đã hoặc đang gửi, lấy từ sổ harness. reserved chưa gửi thì không tính."""
    attempts: dict[str, int] = {}
    for step in view.get("steps") or []:
        rid = step.get("request_id")
        if rid:
            attempts[str(rid)] = max(int(step.get("attempt") or 1), 1)
    total = 0
    for req in view.get("requests") or []:
        if req.get("state") == "reserved":
            continue
        total += max(attempts.get(str(req.get("id")), 1), int(req.get("attempts") or 1))
    return total


def seal_inflight(view: dict) -> dict:
    """Request đã tạo trước lúc gửi nhưng chưa có usage thì giữ uncertain, không gửi lại."""
    sealed = dict(view)
    requests = []
    extra = 0.0
    for req in view.get("requests") or []:
        item = dict(req)
        if item.get("state") == "dispatched":
            extra += float(item.get("hold") or 0)
            item["state"] = "uncertain"
            requests.append(item)
            continue
        if item.get("state") == "reserved":
            continue
        requests.append(item)
    sealed["requests"] = requests
    sealed["reserved"] = 0.0
    sealed["uncertain_usd"] = round(float(view.get("uncertain_usd") or 0) + extra, 6)
    sealed["inflight_sealed"] = True
    return sealed


def note_runs(book: dict, task_id: str, views: list[dict]) -> None:
    """Sổ cái của một run là tích lũy. Attempt sau thay attempt trước, không cộng thêm."""
    slot = book.setdefault(task_id, {})
    for view in views:
        key = f"{view['run_id']}:{view['attempt']}"
        siblings = [old for old in slot.values() if old.get("run_id") == view["run_id"]]
        if any(_richer(old, view) and not _richer(view, old) for old in siblings):
            continue
        for old_key in [name for name, old in slot.items()
                        if old.get("run_id") == view["run_id"] and name != key]:
            slot.pop(old_key, None)
        old = slot.get(key)
        if old is None or _richer(view, old):
            slot[key] = view


def fold_book(book: dict) -> dict:
    spent = reserved = uncertain = sends = 0.0
    send_n = 0
    for slot in book.values():
        for view in slot.values():
            spent += float(view.get("total_usd") or 0)
            reserved += float(view.get("reserved") or 0)
            uncertain += float(view.get("uncertain_usd") or 0)
            send_n += send_count(view)
    return {
        "spent_usd": round(spent, 6),
        "reserved_usd": round(reserved, 6),
        "uncertain_usd": round(uncertain, 6),
        "http_attempts": send_n,
    }


def task_sends(book: dict, task_id: str) -> int:
    return sum(send_count(view) for view in (book.get(task_id) or {}).values())


def allow_send(book: dict, task_id: str, probe: dict) -> str:
    """Trả lý do chặn. Rỗng nghĩa là còn được gửi request kế tiếp."""
    folded = fold_book(book)
    if folded["uncertain_usd"] > 0:
        return "uncertain"
    if folded["spent_usd"] + folded["reserved_usd"] + folded["uncertain_usd"] >= float(probe["budget_usd"]):
        return "budget"
    if task_sends(book, task_id) >= int(probe["max_http_per_task"]):
        return "loop-suspect"
    if folded["http_attempts"] >= int(probe["max_http_trial"]):
        return "calls"
    return ""


def _config_id(probe: dict, tasks: list[str], sha: str) -> str:
    body = {
        "provider": probe.get("provider"),
        "model": probe.get("model"),
        "endpoint": probe.get("endpoint"),
        "verified_on": probe.get("verified_on"),
        "price_in": probe.get("price_in_usd_per_mtok"),
        "price_out": probe.get("price_out_usd_per_mtok"),
        "budget_usd": probe.get("budget_usd"),
        "max_http_per_task": probe.get("max_http_per_task"),
        "max_http_trial": probe.get("max_http_trial"),
        "max_tokens": probe.get("max_tokens"),
        "tasks": list(tasks),
        "harness_sha": sha,
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blank_state(probe: dict, tasks: list[str], approved: bool) -> dict:
    sha = harness_sha()
    return {
        "schema": PROGRESS_SCHEMA,
        "config_id": _config_id(probe, tasks, sha),
        "approved": bool(approved),
        "provider": probe.get("provider"),
        "model": probe.get("model"),
        "endpoint": probe.get("endpoint"),
        "official_source": probe.get("official_source"),
        "pricing_source": probe.get("pricing_source"),
        "verified_on": probe.get("verified_on"),
        "harness_sha": sha,
        "tasks_started": [],
        "tasks_done": [],
        "books": {},
        "spent_usd": 0.0,
        "reserved_usd": 0.0,
        "uncertain_usd": 0.0,
        "usage_usd": 0.0,
        "http_attempts": 0,
        "real_api_requests": 0,
        "budget_usd": probe.get("budget_usd"),
        "budget_is_estimate": True,
        "budget_note": "Trần so với usage và hold đã ghi trên sổ, không phải hóa đơn nhà cung cấp.",
        "max_tokens": probe.get("max_tokens"),
        "max_http_per_task": probe.get("max_http_per_task"),
        "max_http_trial": probe.get("max_http_trial"),
        "stopped": "",
        "task_logs": {},
    }


def _apply_fold(state: dict) -> None:
    totals = fold_book(state.get("books") or {})
    state["spent_usd"] = totals["spent_usd"]
    state["reserved_usd"] = totals["reserved_usd"]
    state["uncertain_usd"] = totals["uncertain_usd"]
    state["http_attempts"] = totals["http_attempts"]
    state["usage_usd"] = totals["spent_usd"]
    state["real_api_requests"] = 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_progress(path: Path):
    lock = path.with_name(path.name + ".lock")
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            try:
                raw = lock.read_text(encoding="utf-8").strip()
                pid = int(raw or "0")
            except (OSError, ValueError):
                pid = 0
            if _pid_alive(pid):
                return None
            try:
                lock.unlink()
            except OSError:
                return None
            continue
        os.write(fd, str(os.getpid()).encode("ascii"))
        return fd
    return None


def _release_progress(path: Path, fd) -> None:
    if fd is None:
        return
    os.close(fd)
    try:
        path.with_name(path.name + ".lock").unlink()
    except OSError:
        pass


def probe_run(approve_spend: bool, base_url: str | None, progress_path: Path,
              tasks: list[str] | None = None, probe: dict | None = None,
              call_timeout: float = 90) -> dict:
    probe = dict(probe or load_probe())
    chosen = list(tasks or probe["tasks"])
    held = _acquire_progress(progress_path)
    if held is None:
        return {
            "schema": PROGRESS_SCHEMA,
            "stopped": "busy",
            "real_api_requests": 0,
            "http_attempts": 0,
            "budget_is_estimate": True,
        }
    try:
        reason = probe_block_reason(approve_spend, base_url)
        if reason:
            if progress_path.is_file():
                state = json.loads(progress_path.read_text(encoding="utf-8"))
            else:
                state = _blank_state(probe, chosen, approve_spend)
                state["stopped"] = reason
                _progress(progress_path, state)
            state = dict(state)
            state["stopped"] = reason
            state["real_api_requests"] = 0
            return state
        if progress_path.is_file():
            state = json.loads(progress_path.read_text(encoding="utf-8"))
            if int(state.get("schema") or 0) != PROGRESS_SCHEMA:
                state["stopped"] = "schema"
                _progress(progress_path, state)
                return state
            if state.get("config_id") != _config_id(probe, chosen, harness_sha()):
                state["stopped"] = "config-mismatch"
                state["real_api_requests"] = 0
                _progress(progress_path, state)
                return state
        else:
            state = _blank_state(probe, chosen, approve_spend)
        assert base_url is not None
        if float(state.get("uncertain_usd") or 0) > 0 or state.get("stopped") == "uncertain":
            state["stopped"] = "uncertain"
            state["real_api_requests"] = 0
            _apply_fold(state)
            _progress(progress_path, state)
            return state
        local = base_url.startswith("http://127.0.0.1:")
        if local:
            _assert_local(base_url)
        elif _openai_child_env() is None:
            state["stopped"] = "missing-key"
            state["real_api_requests"] = 0
            _progress(progress_path, state)
            return state
        price = f"{probe['price_in_usd_per_mtok']},{probe['price_out_usd_per_mtok']}"
        return _probe_loop(probe, chosen, base_url, progress_path, price, state, call_timeout)
    finally:
        _release_progress(progress_path, held)


def _prepare_dest(spec: dict, dest: Path) -> Path:
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(spec["workspace"], dest)
    return dest


def _remember(state: dict, task_id: str, dest: Path, *, died: bool) -> None:
    views = collect_run_ledgers(dest)
    if died:
        views = [seal_inflight(view) for view in views]
    if not views and died:
        views = [{
            "run_id": "unrecorded",
            "attempt": 1,
            "total_usd": 0.0,
            "reserved": 0.0,
            "uncertain_usd": 0.0,
            "requests": [{"id": "unrecorded", "state": "uncertain", "hold": 0}],
            "steps": [],
            "unpriced": True,
        }]
    note_runs(state["books"], task_id, views)
    _apply_fold(state)


def _call_giao(dest: Path, base: str, bits: list[str], price: str, max_tokens: str,
               timeout: float, provider: str = "anthropic", model: str = "claude-test",
               env: dict | None = None):
    try:
        return _giao(dest, base, bits, env=env, max_tokens=max_tokens, price=price,
                     timeout=timeout, provider=provider, model=model)
    except subprocess.TimeoutExpired:
        return None


def _tokens(task_id: str, book: dict) -> int:
    total = 0
    for view in (book.get(task_id) or {}).values():
        total += int(view.get("total_in") or 0) + int(view.get("total_out") or 0)
    return total


def _mark_unrecorded(state: dict, task_id: str) -> None:
    note_runs(state["books"], task_id, [{
        "run_id": "unrecorded",
        "attempt": 1,
        "total_usd": 0.0,
        "reserved": 0.0,
        "uncertain_usd": 0.0,
        "total_in": 0,
        "total_out": 0,
        "requests": [{"id": "unrecorded", "state": "uncertain", "hold": 0}],
        "steps": [],
        "unpriced": True,
    }])
    _apply_fold(state)


def _clip_log(text: str) -> str:
    if len(text) <= 20000:
        return text
    return text[:4000] + "\n...\n" + text[-8000:]


def _log_call(state: dict, tid: str, code, text: str) -> None:
    logs = state.setdefault("task_logs", {})
    row = logs.setdefault(tid, {"calls": []})
    row["calls"].append({"code": code, "text": _clip_log(text)})
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and code not in (0, None):
        row["reason"] = lines[-1][:500]


def _probe_loop(probe: dict, chosen: list[str], base_url: str, progress_path: Path,
                price: str, state: dict, call_timeout: float) -> dict:
    specs = {item["id"]: item for item in load_tasks()}
    base_dir = Path(tempfile.mkdtemp(prefix="frog-value-probe-"))
    done = set(state.get("tasks_done") or [])
    local = base_url.startswith("http://127.0.0.1:")
    provider = "anthropic" if local else str(probe["provider"])
    model = "claude-test" if local else str(probe["model"])
    child_env = None if local else _openai_child_env()
    secret = "" if child_env is None else child_env.get("OPENAI_API_KEY", "")
    _apply_fold(state)
    _progress(progress_path, state)
    for tid in chosen:
        if tid in done:
            continue
        blocked = allow_send(state["books"], tid, probe)
        if blocked:
            state["stopped"] = blocked
            break
        spec = specs[tid]
        _Stub.brief = spec["brief"]
        dest = _prepare_dest(spec, base_dir / tid)
        state.setdefault("task_logs", {}).setdefault(tid, {"calls": []})["workspace"] = str(dest)
        if tid not in state["tasks_started"]:
            state["tasks_started"].append(tid)
        _progress(progress_path, state)
        open_bits = [spec["prompt"], "--approve-brief"]
        if probe.get("intake_model"):
            open_bits += ["--intake-model", str(probe["intake_model"])]
        outcome = _call_giao(
            dest, base_url, open_bits,
            price, str(probe["max_tokens"]), call_timeout,
            provider=provider, model=model, env=child_env)
        if outcome is None:
            _log_call(state, tid, None, "died")
            _remember(state, tid, dest, died=True)
            state["stopped"] = "uncertain"
            break
        proc, _hits, _dur, text = outcome
        if secret and secret in text:
            state["key_leaked"] = True
            text = _redact(text, secret)
        if canary_in(text):
            state["canary_leaked"] = True
        _log_call(state, tid, proc.returncode, text)
        _remember(state, tid, dest, died=False)
        if proc.returncode != 0:
            if task_sends(state["books"], tid) == 0:
                _mark_unrecorded(state, tid)
                state["stopped"] = "uncertain"
                break
            if state["uncertain_usd"] > 0:
                state["stopped"] = "uncertain"
                break
            if _tokens(tid, state["books"]) == 0:
                state["stopped"] = "usage-unknown"
                break
            state.setdefault("task_errors", {})[tid] = "intake-failed"
            state["tasks_done"].append(tid)
            _progress(progress_path, state)
            continue
        if state["uncertain_usd"] > 0:
            state["stopped"] = "uncertain"
            break
        if proc.returncode == 0 and task_sends(state["books"], tid) > 0 and _tokens(tid, state["books"]) == 0:
            state["stopped"] = "usage-unknown"
            break
        run = _run_id(text)
        blocked = allow_send(state["books"], tid, probe)
        if blocked:
            state["stopped"] = blocked
            break
        if not run:
            state["tasks_done"].append(tid)
            _progress(progress_path, state)
            continue
        outcome = _call_giao(
            dest, base_url, ["--run", run, "--autonomy", "walk-away"],
            price, str(probe["max_tokens"]), call_timeout,
            provider=provider, model=model, env=child_env)
        if outcome is None:
            _log_call(state, tid, None, "died")
            _remember(state, tid, dest, died=True)
            state["stopped"] = "uncertain"
            break
        proc, _hits, _dur, more = outcome
        if secret and secret in more:
            state["key_leaked"] = True
            more = _redact(more, secret)
        if canary_in(more):
            state["canary_leaked"] = True
        _log_call(state, tid, proc.returncode, more)
        _remember(state, tid, dest, died=False)
        if state["uncertain_usd"] > 0 or "uncertain" in more or "HTTP 5" in more:
            state["stopped"] = "uncertain"
            break
        if proc.returncode == 0 and _tokens(tid, state["books"]) == 0:
            state["stopped"] = "usage-unknown"
            break
        if proc.returncode not in (0, 3, 4, 8):
            state["stopped"] = "provider-error"
            break
        blocked = allow_send(state["books"], tid, probe)
        if blocked:
            state["stopped"] = blocked
            break
        state["tasks_done"].append(tid)
        _progress(progress_path, state)
    if not state["stopped"]:
        state["stopped"] = "finished"
    _apply_fold(state)
    state["real_api_requests"] = 0 if local else state["http_attempts"]
    _progress(progress_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["freeze", "verify", "check", "smoke", "probe"])
    parser.add_argument("--config", choices=["A", "B"], default="A")
    parser.add_argument("--only", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--approve-spend", action="store_true")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--progress", default=None)
    parser.add_argument("--tasks", default=None)
    args = parser.parse_args()
    if args.cmd == "freeze":
        FREEZE.write_text(freeze_text(), encoding="utf-8")
        print(FREEZE)
        return 0
    if args.cmd == "verify":
        verify_freeze()
        print("freeze ok")
        return 0
    if args.cmd == "check":
        verify_freeze()
        spec = next(item for item in load_tasks() if item["id"] == args.task)
        result = run_check_result(spec, Path(args.workspace))
        print(result["status"])
        if result["reason"]:
            print(result["reason"])
        if result["status"] == "pass":
            return 0
        if result["status"] == "fail":
            return 1
        return 2
    if args.cmd == "probe":
        progress = Path(args.progress) if args.progress else Path(tempfile.mkdtemp()) / "progress.json"
        chosen = [part for part in (args.tasks or "").split(",") if part] or None
        if args.base_url:
            _Stub.brief = {}
        timeout = 300 if (args.base_url or "").rstrip("/") == OPENAI_BASE else 90
        state = probe_run(args.approve_spend, args.base_url, progress, chosen, call_timeout=timeout)
        text = json.dumps(state, ensure_ascii=False, indent=2)
        secret = _openai_key()
        if secret and secret in text:
            text = _redact(text, secret)
            print("KEY_LEAKED")
        if CANARY in text:
            text = text.replace(CANARY, "[redacted]")
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(text)
        return 0 if state["stopped"] in ("finished", "locked", "paid-api-not-approved") else 2
    report = smoke(args.config, args.only)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if CANARY in text:
        text = text.replace(CANARY, "[redacted]")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    if any(row["canary_leaked"] for row in report["rows"]):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
