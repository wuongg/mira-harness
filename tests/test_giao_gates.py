"""Cổng team không bị tiêu chí ghi đè. Provider là HTTP giả, không phải model thật."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _brief(cmd: str) -> dict:
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
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class _Stub(BaseHTTPRequestHandler):
    mode = "ok"
    brief: dict = {}

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        if _Stub.mode == "http":
            raw = b'{"error":"down"}'
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if "INTAKE" in blob:
            text = json.dumps(_Stub.brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            verdict = "FAIL" if _Stub.mode == "verifier-fail" else "PASS"
            text = json.dumps({
                "verdict": verdict, "reasons": ["khop"], "evidence": ["tep"],
                "confidence": 0.9,
            }, ensure_ascii=False)
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
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
    _Stub.mode = "ok"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _mira(root: Path, base: str, args: list[str], price: str | None = "1000,0"):
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
        [sys.executable, "-m", "mira", "giao", *args, "--cwd", str(root),
         "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
         "--max-tokens", "256",
         *(["--price-in", price] if price else [])],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


class GateOverrideTest(unittest.TestCase):
    def _open(self, root: Path, base: str) -> str:
        opened = _mira(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
        self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
        return _id(opened.stdout)

    def _assert_not_delivered(self, ran):
        self.assertNotEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertNotIn("bàn giao: đủ", ran.stdout)
        self.assertNotIn("bàn giao: người dùng xác nhận", ran.stdout)

    def test_provider_loi_validator_cu_van_dat_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                run = self._open(root, base)
                _Stub.mode = "http"
                ran = _mira(root, base, ["--run", run, "--grant", cmd])
                self._assert_not_delivered(ran)
                self.assertIn("error", ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_het_ngan_sach_validator_dat_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                run = self._open(root, base)
                ran = _mira(root, base, ["--run", run, "--grant", cmd], price="1000000,0")
                self._assert_not_delivered(ran)
                self.assertIn("stopped_budget", ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_verifier_fail_validator_dat_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                run = self._open(root, base)
                _Stub.mode = "verifier-fail"
                ran = _mira(root, base, ["--run", run, "--grant", cmd])
                self._assert_not_delivered(ran)
                self.assertIn("verified", ran.stdout)
                self.assertIn("withheld", ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_bi_chan_validator_dat_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                run = self._open(root, base)
                ran = _mira(root, base, ["--run", run, "--grant", cmd], price=None)
                self._assert_not_delivered(ran)
                self.assertIn("blocked", ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()
