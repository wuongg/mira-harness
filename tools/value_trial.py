"""Đo bộ nghiệm thu. Không phải executor thứ hai và không gọi API trả phí."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def _rel_files() -> list[Path]:
    files = sorted(CHECKS.glob("V*.py")) + sorted(TASKS.glob("*/task.json"))
    return files


def freeze_text() -> str:
    lines = []
    for path in _rel_files():
        data = path.read_bytes().replace(b"\r\n", b"\n")
        digest = hashlib.sha256(data).hexdigest()
        lines.append(f"{digest}  {path.relative_to(VALUE).as_posix()}")
    return "\n".join(lines) + "\n"


def verify_freeze() -> str:
    current = freeze_text()
    saved = FREEZE.read_text(encoding="utf-8").replace("\r\n", "\n") if FREEZE.is_file() else ""
    if current != saved:
        raise SystemExit("phép kiểm đã đổi so với bản đóng băng")
    return current


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


def run_check(spec: dict, workspace: Path) -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(spec["check"]), str(workspace)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode


def classify(expect: str, delivered: bool, check_exit: int, side_effect: bool) -> str:
    """Một nhãn vận hành. Không phải điểm thông minh."""
    if side_effect:
        return "side_effect"
    if delivered and check_exit != 0:
        return "false_complete"
    if expect == "deliver" and delivered and check_exit == 0:
        return "completed_correct"
    if expect == "deliver" and not delivered and check_exit == 0:
        return "false_block"
    if expect != "deliver" and not delivered and check_exit == 0:
        return "correct_withhold"
    return "not_complete"


def extra_files(spec: dict, workspace: Path) -> list[str]:
    allowed = set(spec.get("allow") or [])
    found = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        if rel not in allowed and not rel.startswith(".mira/"):
            found.append(rel)
    return found


class _Stub(BaseHTTPRequestHandler):
    brief = {}
    hits = 0

    def log_message(self, *_args):
        return

    def do_POST(self):
        _Stub.hits += 1
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        if "INTAKE" in blob:
            text = json.dumps(_Stub.brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        else:
            text = '<tool>{"name":"finish","args":{"summary":"khong sua"}}</tool>'
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 20, "output_tokens": 10}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve(brief: dict):
    _Stub.brief = brief
    _Stub.hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT)
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if "KEY" in name or "TOKEN" in name or "SECRET" in name:
            if name != "ANTHROPIC_API_KEY":
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


def _giao(cwd: Path, base: str, bits: list[str], env: dict | None = None, timeout: int = 90):
    cmd = [sys.executable, "-m", "mira", "giao", *bits, "--cwd", str(cwd),
           "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
           "--price-in", "1000,0", "--max-tokens", "256"]
    return _run(cmd, cwd, env or _env(), timeout)


def _team(cwd: Path, base: str, spec: dict, brief_path: Path):
    # `mira team` không có --cwd. Thư mục làm việc là cwd của tiến trình.
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


def _secret(text: str) -> bool:
    lowered = text.lower()
    return "sk-" in lowered or "api_key" in lowered or "bearer " in lowered


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
    if "total_in" in ledger:
        return ledger
    return {}


def smoke_task(spec: dict, base: str, config: str, dest: Path) -> dict:
    dest = Path(dest).resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(spec["workspace"], dest)
    brief_path = dest.parent / f"{spec['id']}-brief.json"
    brief_path.write_text(json.dumps(spec["brief"], ensure_ascii=False), encoding="utf-8")
    interventions = list(spec.get("interventions") or [])
    calls = 0
    elapsed = 0.0
    logs = []
    delivered = False
    exit_code = None
    interrupt_reached = None
    change_rejected = False
    if config == "B":
        interventions = ["supplied-brief"]
        proc, hits, dur, text = _team(dest, base, spec, brief_path)
        calls += hits
        elapsed += dur
        logs.append(text)
        exit_code = proc.returncode
        delivered = proc.returncode == 0 and "đã làm" in text
    else:
        proc, hits, dur, text = _giao(dest, base, [spec["prompt"], "--approve-brief"])
        calls += hits
        elapsed += dur
        logs.append(text)
        run = _run_id(text)
        if spec["id"] == "V12":
            proc, hits, dur, text = _giao(dest, base, ["--run", run])
            calls += hits
            elapsed += dur
            logs.append(text)
            exit_code = proc.returncode
            delivered = False
        elif spec["id"] == "V11":
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
            interrupt_reached = flag.exists()
            if flag.exists():
                proc_p.kill()
            proc_p.wait(timeout=10)
            out = (proc_p.stdout.read() if proc_p.stdout else b"").decode("utf-8", "replace")
            err = (proc_p.stderr.read() if proc_p.stderr else b"").decode("utf-8", "replace")
            logs.append(out + "\n" + err)
            calls += _Stub.hits - before_hits
            elapsed += time.perf_counter() - started
            delivered = False
        else:
            proc, hits, dur, text = _giao(dest, base, ["--run", run])
            calls += hits
            elapsed += dur
            logs.append(text)
            exit_code = proc.returncode
            delivered = proc.returncode == 0 and ("bàn giao: đủ" in text or "bàn giao: người dùng xác nhận" in text)
            if spec.get("change"):
                first_exit = exit_code
                proc, hits, dur, text = _giao(dest, base, ["--run", run, "--change", spec["change"]])
                calls += hits
                elapsed += dur
                logs.append(text)
                if proc.returncode == 2:
                    exit_code = first_exit
                    change_rejected = True
                else:
                    exit_code = proc.returncode
                    delivered = proc.returncode == 0 and ("bàn giao: đủ" in text or "bàn giao: người dùng xác nhận" in text)
    blob = "\n".join(logs)
    check_exit = run_check(spec, dest)
    side = extra_files(spec, dest)
    ledger = _ledger(dest)
    outcome = "not_run" if exit_code == 2 else classify(spec["expect"], delivered, check_exit, bool(side))
    return {
        "id": spec["id"],
        "config": config,
        "provider": "fake",
        "model_quality": "not_evaluated",
        "expect": spec["expect"],
        "harness_exit": exit_code,
        "interrupt_reached": interrupt_reached,
        "change_rejected": change_rejected,
        "harness_claimed_delivery": delivered,
        "check_exit": check_exit,
        "outcome": outcome,
        "user_interventions": interventions,
        "intervention_count": len(interventions),
        "retries": 0,
        "http_calls": calls,
        "usage_in": ledger.get("total_in"),
        "usage_out": ledger.get("total_out"),
        "usage_usd": ledger.get("total_usd"),
        "seconds": round(elapsed, 3),
        "side_effect_files": side,
        "secret_in_log": _secret(blob),
        "cost_note": "usage của provider giả, không phải hóa đơn",
    }


def smoke(config: str, only: str | None = None) -> dict:
    verify_freeze()
    tasks = load_tasks()
    if only:
        tasks = [item for item in tasks if item["id"] == only]
    srv, base = _serve(tasks[0]["brief"])
    _assert_local(base)
    rows = []
    try:
        base_dir = Path(tempfile.mkdtemp(prefix="mira-value-smoke-"))
        for spec in tasks:
            _Stub.brief = spec["brief"]
            rows.append(smoke_task(spec, base, config, base_dir / spec["id"]))
    finally:
        srv.shutdown()
        srv.server_close()
    return {"config": config, "provider": "fake", "model_quality": "not_evaluated", "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["freeze", "verify", "check", "smoke"])
    parser.add_argument("--config", choices=["A", "B"], default="A")
    parser.add_argument("--only", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--out", default=None)
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
        print(run_check(spec, Path(args.workspace)))
        return 0
    report = smoke(args.config, args.only)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    if any(row["secret_in_log"] for row in report["rows"]):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
