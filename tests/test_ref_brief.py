"""Brief người viết, bỏ intake. 0 API. Chốt được thì harness không phải nghẽn."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "eval" / "value" / "tasks"
CHECKS = ROOT / "eval" / "value" / "checks"

_FILES = {
    "sum_to.py": "def sum_to(n):\n    total = 0\n    for i in range(n + 1):\n        total += i\n    return total\n",
    "nums.py": "def median(nums):\n    ordered = sorted(nums)\n    return ordered[len(ordered) // 2]\n",
    "people.json": "[{\"id\": \"1\", \"name\": \"An\"}, {\"id\": \"2\", \"name\": \"Bo\"}]\n",
}


class _Stub(BaseHTTPRequestHandler):
    seen: list[str] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        _Stub.seen.append(blob)
        if "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
        else:
            name = next((item for item in _FILES if item in blob), "")
            call = {"name": "write_file", "args": {"path": name, "content": _FILES.get(name, "")}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 30, "output_tokens": 40}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _text_sha(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _brief(task_id: str, outcome: str, root: Path, forbid: list[str] | None = None) -> dict:
    spec = json.loads((TASKS / task_id / "task.json").read_text(encoding="utf-8"))
    brief = spec["brief"]
    item = brief["acceptance_criteria"][0]
    validator = item["validator"]
    path = validator["path"]
    item["outcome"] = outcome
    item["source_path"] = path
    source = root / path
    item["source_sha256"] = _text_sha(source) if source.is_file() else ""
    if forbid:
        validator["must_not_contain"] = forbid
    return brief


class RefBriefTest(unittest.TestCase):
    def test_brief_nguoi_viet_chot_duoc_khong_goi_intake(self):
        cases = (
            ("V01", "ket_qua_moi", ["for i in range(n):"]),
            ("V03", "file_thay_doi", None),
            ("V05", "file_thay_doi", None),
        )
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            for task_id, outcome, forbid in cases:
                with self.subTest(task_id):
                    _Stub.seen = []
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        shutil.copytree(TASKS / task_id / "workspace", root, dirs_exist_ok=True)
                        brief = _brief(task_id, outcome, root, forbid)
                        path = root / "brief.json"
                        path.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
                        spec = json.loads((TASKS / task_id / "task.json").read_text(encoding="utf-8"))
                        env = os.environ.copy()
                        env["PYTHONIOENCODING"] = "utf-8"
                        env["PYTHONPATH"] = str(ROOT)
                        env["ANTHROPIC_API_KEY"] = "local"
                        for name in list(env):
                            if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
                                env.pop(name)
                        ran = subprocess.run(
                            [sys.executable, "-m", "frog", "giao", spec["prompt"],
                             "--brief", str(path), "--approve-brief", "--autonomy", "walk-away",
                             "--cwd", str(root), "--provider", "anthropic", "--base-url", base,
                             "--model", "claude-test", "--price-in", "1000,0", "--max-tokens", "256"],
                            cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")
                        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                        self.assertIn("bàn giao: đủ", ran.stdout)
                        self.assertFalse(any("INTAKE" in item for item in _Stub.seen))
                        checked = subprocess.run(
                            [sys.executable, str(CHECKS / f"{task_id}.py"), str(root)],
                            capture_output=True, text=True)
                        self.assertEqual(checked.returncode, 0, ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()


class _Split(BaseHTTPRequestHandler):
    models: list[str] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        _Split.models.append(str(req.get("model") or ""))
        blob = json.dumps(req, ensure_ascii=False)
        if "INTAKE" in blob:
            text = json.dumps({
                "goal": "Sua", "deliverables": ["nums.py"],
                "acceptance_criteria": ["giong van de doc"],
                "constraints": [], "assumptions": [], "questions": [],
                "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
            })
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        else:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 10, "output_tokens": 10}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class IntakeTierTest(unittest.TestCase):
    def test_intake_dung_model_manh_worker_giu_model_re(self):
        _Split.models = []
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Split)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "nums.py").write_text("def median(nums):\n    return 0\n", encoding="utf-8")
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONPATH"] = str(ROOT)
                env["ANTHROPIC_API_KEY"] = "local"
                for name in list(env):
                    if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
                        env.pop(name)
                subprocess.run(
                    [sys.executable, "-m", "frog", "giao", "Sửa nums.py",
                     "--intake-model", "gpt-5.6-sol", "--approve-brief",
                     "--autonomy", "walk-away", "--cwd", str(root),
                     "--provider", "anthropic", "--base-url", base,
                     "--model", "claude-test", "--price-in", "1000,0", "--max-tokens", "256"],
                    cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(_Split.models[0], "gpt-5.6-sol")
                self.assertIn("claude-test", _Split.models[1:])
                self.assertNotIn("gpt-5.6-sol", _Split.models[1:])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
