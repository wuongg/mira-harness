"""mira giao --run phải gọi execute_plan. Test không tự viết kết quả đúng."""
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
    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        if "INTAKE" in blob:
            text = json.dumps(_Stub.brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["calc"],"confidence":0.9}'
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"da sua add"}}</tool>'
        else:
            text = (
                '<tool>{"name":"edit_file","args":{"path":"calc.py",'
                '"old":"return a - b","new":"return a + b"}}</tool>'
            )
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
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _mira(root: Path, base: str, args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
    return subprocess.run(
        [sys.executable, "-m", "mira", "giao", *args, "--cwd", str(root),
         "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
         "--price-in", "1000,0", "--max-tokens", "256"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


class GiaoExecuteTest(unittest.TestCase):
    def test_worker_sua_file_qua_tool(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        brief = _brief(cmd)
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _mira(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stderr + opened.stdout)
                run = next(line.split(": ", 1)[1].strip()
                           for line in opened.stdout.splitlines() if line.startswith("Run: "))
                ran = _mira(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("bàn giao: đủ", ran.stdout)
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
                self.assertTrue((root / ".mira" / "runs" / run / "checkpoint.json").is_file())
                self.assertFalse((root / ".mira-giao").exists())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_check_only_khong_goi_la_xong(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        brief = _brief(cmd)
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                opened = _mira(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = next(line.split(": ", 1)[1].strip()
                           for line in opened.stdout.splitlines() if line.startswith("Run: "))
                checked = _mira(root, base, ["--run", run, "--grant", cmd, "--check-only"])
                self.assertNotEqual(checked.returncode, 0, checked.stdout)
                self.assertIn("chưa phải hoàn thành nhiệm vụ", checked.stdout)
                self.assertNotIn("bàn giao: đủ", checked.stdout)
                self.assertFalse((root / ".mira" / "runs" / run / "checkpoint.json").exists())
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
