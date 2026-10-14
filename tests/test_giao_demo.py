"""Luồng phiếu giao việc bằng CLI thật và provider giả."""
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

BRIEF_A = None
BRIEF_B = None
BRIEF_C = None


def _brief(goal, criteria, deliverables, constraints):
    return {
        "goal": goal,
        "deliverables": deliverables,
        "acceptance_criteria": criteria,
        "constraints": constraints,
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
        if "BAO-CAO" in blob:
            text = json.dumps(BRIEF_C, ensure_ascii=False)
        elif "HOA-DON" in blob:
            text = json.dumps(BRIEF_B, ensure_ascii=False)
        else:
            text = json.dumps(BRIEF_A, ensure_ascii=False)
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 20, "output_tokens": 40}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
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
         "--price-in", "1000,0", "--max-tokens", "64"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


def _run_id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


class GiaoDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global BRIEF_A, BRIEF_B, BRIEF_C
        cls.cmd = shlex.join([
            sys.executable, "-c",
            "import calc; print(calc.add(2, 3))",
        ])
        BRIEF_A = _brief(
            "Sua ham add",
            [{
                "schema": 1, "id": "add-ok", "text": "add(2, 3) in ra 5",
                "validator": {
                    "kind": "behavior", "cmd": cls.cmd, "expects_exit": 0,
                    "expects_stdout": "5",
                    "does_not_prove": "khong kiem ham khac",
                },
            }],
            ["calc.py"], ["khong doi ten ham"])
        BRIEF_B = _brief(
            "Tao danh sach hoa don",
            [{
                "schema": 1, "id": "inv", "text": "moi phan tu co invoice_id",
                "validator": {
                    "kind": "json_keys", "path": "rows.json", "expect": "array",
                    "required": ["invoice_id"], "forbidden": ["token"],
                },
            }],
            ["rows.json"], ["khong ghi token"])
        BRIEF_C = _brief(
            "Viet bao cao",
            [
                {
                    "schema": 1, "id": "src", "text": "bao cao co dong nguon",
                    "validator": {
                        "kind": "contains", "path": "report.md",
                        "must_contain": ["Nguon:"], "must_not_contain": [],
                    },
                },
                {"schema": 1, "id": "tone", "text": "giong van phong de doc"},
            ],
            ["report.md"], ["khong bi dat so lieu"])
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_sua_ham_va_kiem_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
            opened = _mira(root, self.base, ["Sua ham add va kiem bang test"])
            self.assertEqual(opened.returncode, 0, opened.stderr)
            self.assertIn("[tự động]", opened.stdout)
            self.assertIn("Duyệt phiếu không cấp", opened.stdout)
            run = _run_id(opened.stdout)
            state = json.loads((root / ".mira-giao" / run / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["grants"], [])
            blocked = _mira(root, self.base, ["--run", run, "--approve-brief"])
            self.assertEqual(blocked.returncode, 4, blocked.stdout)
            self.assertIn("pending", blocked.stdout)
            self.assertIn("bàn giao: chưa", blocked.stdout)
            wrong = _mira(root, self.base, ["--run", run, "--grant", "echo sai"])
            self.assertEqual(wrong.returncode, 2, wrong.stdout)
            self.assertIn("không thuộc", wrong.stdout)
            self.assertNotIn("bàn giao: đủ", wrong.stdout)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            passed = _mira(root, self.base, ["--run", run, "--grant", self.cmd])
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("verified", passed.stdout)
            self.assertIn("bàn giao: đủ", passed.stdout)
            self.assertEqual(opened.stdout.count("Bước tiếp:"), 1)

    def test_json_khoa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rows.json").write_text("[{}]", encoding="utf-8")
            opened = _mira(root, self.base, ["Tao HOA-DON co invoice_id"])
            self.assertEqual(opened.returncode, 0, opened.stderr)
            self.assertIn("[tự động]", opened.stdout)
            self.assertIn("(không có lệnh)", opened.stdout)
            run = _run_id(opened.stdout)
            bad = _mira(root, self.base, ["--run", run, "--approve-brief"])
            self.assertEqual(bad.returncode, 4, bad.stdout)
            self.assertIn("failed", bad.stdout)
            self.assertNotIn("bàn giao: đủ", bad.stdout)
            (root / "rows.json").write_text(
                '[{"invoice_id":"a"},{"invoice_id":"b"}]', encoding="utf-8")
            good = _mira(root, self.base, ["--run", run])
            self.assertEqual(good.returncode, 0, good.stdout)
            self.assertIn("verified", good.stdout)

    def test_bao_cao_tu_dong_va_nguoi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.md").write_text("Nguon: so tay\n", encoding="utf-8")
            opened = _mira(root, self.base, ["Viet BAO-CAO co nguon va giong van"])
            self.assertEqual(opened.returncode, 0, opened.stderr)
            self.assertIn("[tự động]", opened.stdout)
            self.assertIn("[cần người xác nhận]", opened.stdout)
            run = _run_id(opened.stdout)
            done = _mira(root, self.base, ["--run", run, "--approve-brief"])
            self.assertEqual(done.returncode, 4, done.stdout)
            self.assertIn("verified", done.stdout)
            self.assertIn("needs_confirmation", done.stdout)
            self.assertIn("bàn giao: chưa", done.stdout)

    def test_doi_yeu_cau_khong_dung_duyet_cu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            opened = _mira(root, self.base, ["Sua ham add", "--approve-brief"])
            run = _run_id(opened.stdout)
            _mira(root, self.base, ["--run", run, "--grant", self.cmd])
            changed = _mira(root, self.base, ["--run", run, "--change", "Them ham nhan"])
            self.assertEqual(changed.returncode, 2, changed.stdout)
            self.assertIn("Yêu cầu đã đổi", changed.stdout)
            self.assertIn(run, changed.stdout)
            self.assertIn("Bước tiếp:", changed.stdout)
            self.assertIn("--previous", changed.stdout)
            fresh = _mira(root, self.base, ["Them ham nhan", "--previous", run, "--approve-brief"])
            self.assertEqual(fresh.returncode, 0, fresh.stderr)
            new_id = _run_id(fresh.stdout)
            self.assertNotEqual(new_id, run)
            self.assertIn("Nối với run cũ", fresh.stdout)
            new_state = json.loads((root / ".mira-giao" / new_id / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(new_state["grants"], [])
            self.assertEqual(new_state["previous"], run)
            rerun = _mira(root, self.base, ["--run", new_id])
            self.assertIn("pending", rerun.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
