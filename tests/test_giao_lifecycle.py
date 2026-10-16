"""Vòng đời một run. Đếm request HTTP giả và lần promote. Không phải model thật."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _calc_brief(cmd: str) -> dict:
    return {
        "goal": "Sua calc.py thanh phep cong",
        "deliverables": ["calc.py"],
        "acceptance_criteria": [{
            "schema": 1, "id": "add-ok", "text": "add(2, 3) in ra 5",
            "validator": {
                "kind": "behavior", "cmd": cmd, "expects_exit": 0,
                "expects_stdout": "5", "does_not_prove": "khong kiem ham khac",
            },
        }],
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _report_brief() -> dict:
    return {
        "goal": "Ghi report.md",
        "deliverables": ["report.md"],
        "acceptance_criteria": [
            {
                "schema": 1, "id": "src", "text": "bao cao co dong nguon",
                "validator": {
                    "kind": "contains", "path": "report.md",
                    "must_contain": ["Nguon:"], "must_not_contain": [],
                },
            },
            {"schema": 1, "id": "tone", "text": "giong van phong de doc"},
        ],
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class _Stub(BaseHTTPRequestHandler):
    brief: dict = {}
    hits = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        _Stub.hits += 1
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        if "INTAKE" in blob:
            text = json.dumps(_Stub.brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
        elif "report.md" in blob:
            call = {"name": "write_file", "args": {
                "path": "report.md", "content": "Nguon: so tay\n"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        else:
            call = {"name": "edit_file", "args": {
                "path": "calc.py", "old": "return a - b", "new": "return a + b"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 30, "output_tokens": 40}}
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


def _frog(root: Path, base: str, args: list[str]):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
        if name.startswith("MIRA_PRICE"):
            env.pop(name)
    return subprocess.run(
        [sys.executable, "-m", "frog", "giao", *args, "--cwd", str(root),
         "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
         "--price-in", "1000,0", "--max-tokens", "256"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


class LifecycleTest(unittest.TestCase):
    def test_mo_lai_run_da_ban_giao_khong_them_call(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_calc_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                hits = _Stub.hits
                stamp = (root / "calc.py").stat().st_mtime_ns
                time.sleep(0.05)
                for _ in range(2):
                    again = _frog(root, base, ["--run", run])
                    self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                    self.assertIn("đã bàn giao", again.stdout)
                    self.assertEqual(_Stub.hits, hits)
                    self.assertEqual((root / "calc.py").stat().st_mtime_ns, stamp)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_xac_nhan_khong_chay_lai_worker(self):
        srv, base = _serve(_report_brief())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertNotEqual(ran.returncode, 0, ran.stdout)
                self.assertIn("chờ xác nhận", ran.stdout)
                self.assertFalse((root / "report.md").exists())
                hits = _Stub.hits
                confirmed = _frog(root, base, [
                    "--run", run, "--confirm", "tone", "--artifact", "report.md"])
                self.assertEqual(confirmed.returncode, 0, confirmed.stdout + confirmed.stderr)
                self.assertEqual(_Stub.hits, hits)
                self.assertIn("Nguon:", (root / "report.md").read_text(encoding="utf-8"))
                stamp = (root / "report.md").stat().st_mtime_ns
                time.sleep(0.05)
                again = _frog(root, base, ["--run", run])
                self.assertEqual(_Stub.hits, hits)
                self.assertEqual((root / "report.md").stat().st_mtime_ns, stamp)
                self.assertIn("đã bàn giao", again.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_chi_phi_gom_intake_va_thuc_thi(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_calc_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("chi phí tích lũy", ran.stdout)
                state = json.loads((root / ".frog" / "runs" / run / "handoff.json").read_text(encoding="utf-8"))
                roles = [row["role"] for row in state["ledger"]["rows"]]
                self.assertIn("intake", roles)
                self.assertGreater(state["ledger"]["total_usd"], 0)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_chay_lai_phai_la_attempt_moi(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_calc_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(ran.returncode, 0, ran.stdout)
                hits = _Stub.hits
                quiet = _frog(root, base, ["--run", run])
                self.assertEqual(_Stub.hits, hits, quiet.stdout)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                retried = _frog(root, base, ["--run", run, "--retry"])
                self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
                self.assertGreater(_Stub.hits, hits)
                state = json.loads((root / ".frog" / "runs" / run / "handoff.json").read_text(encoding="utf-8"))
                self.assertEqual(state["attempt"], 2)
                self.assertEqual(len(state["history"]), 1)
                self.assertEqual(state["history"][0]["attempt"], 1)
                self.assertGreaterEqual(state["ledger"]["total_usd"], state["history"][0]["cost_usd"])
        finally:
            srv.shutdown()
            srv.server_close()
