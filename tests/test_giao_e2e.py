"""Đầu-cuối bằng tiến trình thật. Provider HTTP giả không phải chất lượng model."""
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


def _env(root: Path, extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
        if name.startswith("MIRA_PRICE"):
            env.pop(name)
    if extra:
        env.update(extra)
    return env


def _cmd(root: Path, base: str, args: list[str]) -> list[str]:
    return [sys.executable, "-m", "frog", "giao", *args, "--cwd", str(root),
            "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
            "--price-in", "1000,0", "--max-tokens", "256"]


def _frog(root: Path, base: str, args: list[str]):
    return subprocess.run(
        _cmd(root, base, args), cwd=str(root), env=_env(root),
        capture_output=True, text=True, encoding="utf-8")


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


class EndToEndTest(unittest.TestCase):
    def _open(self, root: Path, base: str, cmd: str) -> str:
        (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
        self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
        return _id(opened.stdout)

    def _kill_at(self, root: Path, base: str, run: str, cmd: str, pause: str):
        flag = root / "pause.txt"
        proc = subprocess.Popen(
            _cmd(root, base, ["--run", run, "--grant", cmd]),
            cwd=str(root),
            env=_env(root, {"MIRA_PAUSE": pause, "MIRA_PAUSE_FLAG": str(flag)}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.time() + 20
        while time.time() < deadline and not flag.exists():
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        err = b""
        if not flag.exists():
            err = proc.stderr.read() if proc.stderr else b""
        self.assertTrue(flag.exists(), err.decode("utf-8", "replace"))
        hits = _Stub.hits
        proc.kill()
        proc.wait(timeout=10)
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        return hits

    def test_kill_truoc_promote_roi_tiep_mot_lan(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run = self._open(root, base, cmd)
                hits = self._kill_at(root, base, run, cmd, "before-promote")
                self.assertIn("return a - b", (root / "calc.py").read_text(encoding="utf-8"))
                cont = _frog(root, base, ["--run", run])
                self.assertEqual(cont.returncode, 0, cont.stdout + cont.stderr)
                self.assertEqual(_Stub.hits, hits)
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
                stamp = (root / "calc.py").stat().st_mtime_ns
                time.sleep(0.05)
                again = _frog(root, base, ["--run", run])
                self.assertEqual(_Stub.hits, hits)
                self.assertEqual((root / "calc.py").stat().st_mtime_ns, stamp, again.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_kill_sau_promote_khong_ghi_lai(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run = self._open(root, base, cmd)
                hits = self._kill_at(root, base, run, cmd, "after-promote")
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
                stamp = (root / "calc.py").stat().st_mtime_ns
                time.sleep(0.05)
                cont = _frog(root, base, ["--run", run])
                self.assertEqual(cont.returncode, 0, cont.stdout + cont.stderr)
                self.assertEqual(_Stub.hits, hits)
                self.assertEqual((root / "calc.py").stat().st_mtime_ns, stamp)
                self.assertIn("đã bàn giao", cont.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_hai_tien_trinh_mot_run(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run = self._open(root, base, cmd)
                before = _Stub.hits
                first = subprocess.Popen(
                    _cmd(root, base, ["--run", run, "--grant", cmd]),
                    cwd=str(root), env=_env(root),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                second = subprocess.Popen(
                    _cmd(root, base, ["--run", run, "--grant", cmd]),
                    cwd=str(root), env=_env(root),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out1, err1 = first.communicate(timeout=40)
                out2, err2 = second.communicate(timeout=40)
                self.assertEqual(first.returncode, 0, out1.decode("utf-8", "replace") + err1.decode("utf-8", "replace"))
                self.assertIn(second.returncode, (0, 2), out2.decode("utf-8", "replace") + err2.decode("utf-8", "replace"))
                state = json.loads((root / ".frog" / "runs" / run / "handoff.json").read_text(encoding="utf-8"))
                self.assertEqual(state["phase"], "delivered")
                text1 = out1.decode("utf-8", "replace")
                text2 = out2.decode("utf-8", "replace")
                self.assertTrue("không gọi lại" in text1 or "không gọi lại" in text2, text1 + "\n---\n" + text2)
                self.assertLessEqual(_Stub.hits - before, 4, str(_Stub.hits - before))
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()
