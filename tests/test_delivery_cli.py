"""Sáu phản chứng bàn giao qua CLI và provider HTTP giả."""
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


def _criteria_report() -> list:
    return [
        {
            "schema": 1, "id": "src", "text": "bao cao co SOURCE",
            "validator": {
                "kind": "contains", "path": "report.md",
                "must_contain": ["SOURCE"], "must_not_contain": [],
            },
        },
        {"schema": 1, "id": "tone", "text": "giong van phong de doc"},
    ]


def _brief_calc(cmd: str, extra: list | None = None) -> dict:
    criteria = [{
        "schema": 1, "id": "add-ok", "text": "add(2, 3) in ra 5",
        "validator": {
            "kind": "behavior", "cmd": cmd, "expects_exit": 0,
            "expects_stdout": "5", "does_not_prove": "khong kiem ham khac",
        },
    }]
    if extra:
        criteria.extend(extra)
    return {
        "goal": "Sua calc.py thanh phep cong",
        "deliverables": ["calc.py"],
        "acceptance_criteria": criteria,
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


def _brief_files() -> dict:
    return {
        "goal": "Ghi a.txt va b.txt",
        "deliverables": ["a.txt", "b.txt"],
        "acceptance_criteria": [
            {
                "schema": 1, "id": "a", "text": "a co AAA",
                "validator": {
                    "kind": "contains", "path": "a.txt",
                    "must_contain": ["AAA"], "must_not_contain": [],
                },
            },
            {
                "schema": 1, "id": "b", "text": "b co BBB",
                "validator": {
                    "kind": "contains", "path": "b.txt",
                    "must_contain": ["BBB"], "must_not_contain": [],
                },
            },
        ],
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class _Stub(BaseHTTPRequestHandler):
    brief: dict = {}
    mode = "calc"
    hits = 0
    writes = 0

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
        elif _Stub.mode == "two" and _Stub.writes < 2:
            name = "a.txt" if _Stub.writes == 0 else "b.txt"
            content = "AAA\n" if name == "a.txt" else "BBB\n"
            _Stub.writes += 1
            call = {"name": "write_file", "args": {"path": name, "content": content}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
        elif _Stub.mode == "report":
            call = {"name": "write_file", "args": {"path": "report.md", "content": "SOURCE\n"}}
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


def _serve(brief: dict, mode: str):
    _Stub.brief = brief
    _Stub.mode = mode
    _Stub.hits = 0
    _Stub.writes = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
        if name.startswith("MIRA_PRICE"):
            env.pop(name)
    env.pop("MIRA_PAUSE", None)
    env.pop("MIRA_PAUSE_FLAG", None)
    if extra:
        env.update(extra)
    return env


def _cmd(root: Path, base: str, args: list[str]) -> list[str]:
    return [sys.executable, "-m", "frog", "giao", *args, "--cwd", str(root),
            "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
            "--price-in", "1000,0", "--max-tokens", "256"]


def _frog(root: Path, base: str, args: list[str]):
    return subprocess.run(
        _cmd(root, base, args), cwd=str(root), env=_env(),
        capture_output=True, text=True, encoding="utf-8", timeout=90)


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


def _state(root: Path, run: str) -> dict:
    return json.loads((root / ".mira" / "runs" / run / "handoff.json").read_text(encoding="utf-8"))


class DeliveryCliTest(unittest.TestCase):
    def test_1_artifact_doi_truoc_xac_nhan(self):
        brief = {
            "goal": "Ghi report.md", "deliverables": ["report.md"],
            "acceptance_criteria": _criteria_report(),
            "constraints": [], "assumptions": [], "questions": [],
            "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
        }
        srv, base = _serve(brief, "report")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                run = _id(opened.stdout)
                first = _frog(root, base, ["--run", run])
                self.assertNotEqual(first.returncode, 0, first.stdout)
                self.assertIn("SOURCE", (Path(_state(root, run)["staging"]) / "report.md").read_text(encoding="utf-8"))
                (Path(_state(root, run)["staging"]) / "report.md").write_text(
                    "NO REQUIRED CONTENT\n", encoding="utf-8")
                done = _frog(root, base, ["--run", run, "--confirm", "tone", "--artifact", "report.md"])
                self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn("bàn giao: đủ", done.stdout)
                self.assertFalse((root / "report.md").exists())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_2_dependency_doi_artifact_chinh_giu_nguyen(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief_calc(cmd), "calc")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                (root / "dep.txt").write_text("v1\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                flag = root / "pause.txt"
                proc = subprocess.Popen(
                    _cmd(root, base, ["--run", run, "--grant", cmd]),
                    cwd=str(root),
                    env=_env({"MIRA_PAUSE": "before-promote", "MIRA_PAUSE_FLAG": str(flag)}),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                deadline = time.time() + 30
                while time.time() < deadline and not flag.exists():
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                self.assertTrue(flag.exists(), "không dừng trước promote")
                staging = Path(_state(root, run)["staging"])
                (staging / "dep.txt").write_text("v2\n", encoding="utf-8")
                out, err = proc.communicate(timeout=40)
                text = out.decode("utf-8", "replace") + err.decode("utf-8", "replace")
                self.assertNotEqual(proc.returncode, 0, text)
                self.assertIn("hết hiệu lực", text)
                self.assertIn("return a - b", (root / "calc.py").read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_3_doi_sau_xac_nhan_truoc_promote(self):
        brief = {
            "goal": "Ghi report.md", "deliverables": ["report.md"],
            "acceptance_criteria": _criteria_report(),
            "constraints": [], "assumptions": [], "questions": [],
            "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
        }
        srv, base = _serve(brief, "report")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run = _id(opened.stdout)
                first = _frog(root, base, ["--run", run])
                self.assertNotEqual(first.returncode, 0, first.stdout)
                flag = root / "pause.txt"
                proc = subprocess.Popen(
                    _cmd(root, base, ["--run", run, "--confirm", "tone", "--artifact", "report.md"]),
                    cwd=str(root),
                    env=_env({"MIRA_PAUSE": "before-promote", "MIRA_PAUSE_FLAG": str(flag)}),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                deadline = time.time() + 30
                while time.time() < deadline and not flag.exists():
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                self.assertTrue(flag.exists(), "không dừng trước promote")
                (Path(_state(root, run)["staging"]) / "report.md").write_text(
                    "NO REQUIRED CONTENT\n", encoding="utf-8")
                out, err = proc.communicate(timeout=40)
                text = out.decode("utf-8", "replace") + err.decode("utf-8", "replace")
                self.assertNotEqual(proc.returncode, 0, text)
                self.assertNotIn("bàn giao: đủ", text)
                self.assertFalse((root / "report.md").exists())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_4_kill_giua_hai_file(self):
        srv, base = _serve(_brief_files(), "two")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                opened = _frog(root, base, ["Ghi a.txt và b.txt", "--approve-brief"])
                run = _id(opened.stdout)
                flag = root / "pause.txt"
                proc = subprocess.Popen(
                    _cmd(root, base, ["--run", run]),
                    cwd=str(root),
                    env=_env({"MIRA_PAUSE": "mid-promote", "MIRA_PAUSE_FLAG": str(flag)}),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                deadline = time.time() + 30
                while time.time() < deadline and not flag.exists():
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                self.assertTrue(flag.exists(), "không dừng giữa promote")
                proc.kill()
                proc.wait(timeout=10)
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
                saved = _state(root, run)
                self.assertEqual(saved["phase"], "executing")
                self.assertFalse(saved["promoted"])
                self.assertFalse((root / "b.txt").is_file())
                self.assertTrue((Path(saved["staging"]) / "b.txt").is_file())
                self.assertNotEqual(_state(root, run)["phase"], "delivered")
                report = root / ".mira" / "runs" / run / "handoff.md"
                body = report.read_text(encoding="utf-8") if report.is_file() else ""
                self.assertNotIn("bàn giao: đủ", body)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_5_mo_lai_khong_goi_them(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief_calc(cmd), "calc")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                done = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                hits = _Stub.hits
                stamp = (root / "calc.py").stat().st_mtime_ns
                time.sleep(0.05)
                again = _frog(root, base, ["--run", run])
                self.assertEqual(again.returncode, 0, again.stdout)
                self.assertIn("không gọi lại", again.stdout)
                self.assertEqual(_Stub.hits, hits)
                self.assertEqual((root / "calc.py").stat().st_mtime_ns, stamp)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_6_khong_doi_van_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief_calc(cmd), "calc")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                done = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("bàn giao: đủ", done.stdout)
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()
