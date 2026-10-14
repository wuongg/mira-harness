"""Đo bộ nghiệm thu. Không phải executor thứ hai và không gọi API trả phí."""
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
        if rel.startswith(".mira/") or "__pycache__" in rel or rel.endswith(".pyc"):
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
        if name.startswith("MIRA_PRICE"):
            env.pop(name, None)
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
          max_tokens: str = "256", price: str = "1000,0"):
    cmd = [sys.executable, "-m", "mira", "giao", *bits, "--cwd", str(cwd),
           "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
           "--price-in", price, "--max-tokens", max_tokens]
    return _run(cmd, cwd, env or _env(), timeout)


def _team(cwd: Path, base: str, spec: dict, brief_path: Path):
    cmd = [sys.executable, "-m", "mira", "team", spec["prompt"],
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
    runs = dest / ".mira" / "runs"
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
            flag = dest / ".mira" / "pause.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            if flag.exists():
                flag.unlink()
            cmd = [sys.executable, "-m", "mira", "giao", "--run", run, "--cwd", str(dest),
                   "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
                   "--price-in", "1000,0", "--max-tokens", "256"]
            proc_p = subprocess.Popen(
                cmd, cwd=str(dest),
                env=_env({"MIRA_PAUSE": "before-promote", "MIRA_PAUSE_FLAG": str(flag)}),
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
        base_dir = Path(tempfile.mkdtemp(prefix="mira-value-smoke-"))
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
    text = (ROOT / "mira" / "prices.toml").read_text(encoding="utf-8")
    return set(re.findall(r'\[models\."([^"]+)"\]', text))


def validate_probe_model(model: str, provider: str) -> None:
    if model in toml_model_names():
        raise SystemExit("tên trong prices.toml không phải API ID")
    if model != OFFICIAL_MODEL or provider != "anthropic":
        raise SystemExit("model hoặc provider không khớp nguồn đã xác minh")


def load_probe() -> dict:
    data = json.loads(PROBE.read_text(encoding="utf-8"))
    validate_probe_model(str(data.get("model") or ""), str(data.get("provider") or ""))
    return data


def probe_block_reason(approve_spend: bool, base_url: str | None) -> str:
    if not approve_spend:
        return "locked"
    if not base_url:
        return "missing-base-url"
    if not base_url.startswith("http://127.0.0.1:"):
        return "paid-api-not-approved"
    return ""


def _progress(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(state, ensure_ascii=False, indent=2)
    if canary_in(blob):
        blob = blob.replace(CANARY, "[redacted]")
    path.write_text(blob, encoding="utf-8")


def _stop_reason(state: dict, probe: dict, task_calls: int) -> str:
    if float(state.get("uncertain_usd") or 0) > 0:
        return "uncertain"
    if float(state.get("usage_usd") or 0) >= float(probe["budget_usd"]):
        return "budget"
    if task_calls > int(probe["max_http_per_task"]):
        return "calls"
    return ""


def probe_run(approve_spend: bool, base_url: str | None, progress_path: Path,
              tasks: list[str] | None = None, probe: dict | None = None) -> dict:
    probe = dict(probe or load_probe())
    chosen = list(tasks or probe["tasks"])
    state = {
        "approved": bool(approve_spend),
        "provider": probe["provider"],
        "model": probe["model"],
        "harness_sha": harness_sha(),
        "tasks_started": [],
        "http_attempts": 0,
        "usage_usd": 0.0,
        "uncertain_usd": 0.0,
        "stopped": "",
        "max_tokens": probe["max_tokens"],
        "budget_usd": probe["budget_usd"],
        "max_http_per_task": probe["max_http_per_task"],
    }
    reason = probe_block_reason(approve_spend, base_url)
    if reason:
        state["stopped"] = reason
        _progress(progress_path, state)
        return state
    assert base_url is not None
    _assert_local(base_url)
    price = f"{probe['price_in_usd_per_mtok']},{probe['price_out_usd_per_mtok']}"
    return _probe_loop(probe, chosen, base_url, progress_path, price, state)


def _prepare_dest(spec: dict, dest: Path) -> Path:
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(spec["workspace"], dest)
    return dest


def _probe_loop(probe: dict, chosen: list[str], base_url: str, progress_path: Path,
                price: str, state: dict) -> dict:
    specs = {item["id"]: item for item in load_tasks()}
    base_dir = Path(tempfile.mkdtemp(prefix="mira-value-probe-"))
    _progress(progress_path, state)
    for tid in chosen:
        if float(state["uncertain_usd"]) > 0:
            state["stopped"] = "uncertain"
            break
        if float(state["usage_usd"]) >= float(probe["budget_usd"]):
            state["stopped"] = "budget"
            break
        if state["tasks_started"] and state["http_attempts"] >= int(probe["max_http_per_task"]):
            state["stopped"] = "calls"
            break
        spec = specs[tid]
        _Stub.brief = spec["brief"]
        dest = _prepare_dest(spec, base_dir / tid)
        state["tasks_started"].append(tid)
        _progress(progress_path, state)
        proc, hits, _dur, text = _giao(
            dest, base_url, [spec["prompt"], "--approve-brief"],
            max_tokens=str(probe["max_tokens"]), price=price)
        state["http_attempts"] += hits
        ledger = _ledger(dest)
        state["usage_usd"] = round(float(state["usage_usd"]) + float(ledger.get("total_usd") or 0), 6)
        state["uncertain_usd"] = round(
            float(state["uncertain_usd"]) + float(ledger.get("uncertain_usd") or 0), 6)
        if proc.returncode != 0 and hits and not ledger.get("total_in"):
            state["uncertain_usd"] = max(float(state["uncertain_usd"]), 0.000001)
        if ("HTTP 5" in text or "uncertain" in text) and state["uncertain_usd"] <= 0:
            state["uncertain_usd"] = 0.000001
        if canary_in(text):
            state["canary_leaked"] = True
        missing_usage = (
            proc.returncode == 0 and hits > 0 and not ledger.get("total_in")
            and state["uncertain_usd"] <= 0)
        if state["uncertain_usd"] <= 0 and not missing_usage and proc.returncode in (0, 8):
            run = _run_id(text)
            if run:
                proc, hits, _dur, more = _giao(
                    dest, base_url, ["--run", run],
                    max_tokens=str(probe["max_tokens"]), price=price)
                text += "\n" + more
                state["http_attempts"] += hits
                ledger = _ledger(dest)
                state["usage_usd"] = round(float(ledger.get("total_usd") or 0), 6)
                state["uncertain_usd"] = round(float(ledger.get("uncertain_usd") or 0), 6)
                if ("HTTP 5" in more or "uncertain" in more) and state["uncertain_usd"] <= 0:
                    state["uncertain_usd"] = 0.000001
                if canary_in(more):
                    state["canary_leaked"] = True
                if hits > 0 and not ledger.get("total_in") and state["uncertain_usd"] <= 0:
                    missing_usage = True
        if missing_usage and state["uncertain_usd"] <= 0:
            state["stopped"] = "usage-unknown"
            _progress(progress_path, state)
            break
        task_calls = state["http_attempts"]
        stop = _stop_reason(state, probe, task_calls)
        if stop:
            state["stopped"] = stop
            _progress(progress_path, state)
            if stop == "uncertain":
                break
            break
        if proc.returncode not in (0, 3, 4, 8):
            state["stopped"] = "provider-error"
            _progress(progress_path, state)
            break
        _progress(progress_path, state)
    if not state["stopped"]:
        state["stopped"] = "finished"
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
        state = probe_run(args.approve_spend, args.base_url, progress, chosen)
        text = json.dumps(state, ensure_ascii=False, indent=2)
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
