"""frog giao --run phải gọi execute_plan. Test không tự viết kết quả đúng."""
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
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        elif "<result>" in blob:
            text = '<tool>{"name":"finish","args":{"summary":"xong"}}</tool>'
        elif "rows.json" in blob:
            call = {"name": "write_file", "args": {
                "path": "rows.json", "content": '[{"invoice_id":"a"}]'}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif "label.txt" in blob:
            call = {"name": "write_file", "args": {
                "path": "label.txt", "content": "BAN NHAP"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif "report.md" in blob:
            call = {"name": "write_file", "args": {
                "path": "report.md", "content": "Nguon: so tay\n"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif "sum_to.py" in blob:
            call = {"name": "edit_file", "args": {
                "path": "sum_to.py", "old": "range(n)", "new": "range(n + 1)"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif "SAI" in blob:
            call = {"name": "edit_file", "args": {
                "path": "calc.py", "old": "return a - b", "new": "return 0"}}
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
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _frog(root: Path, base: str, args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
    return subprocess.run(
        [sys.executable, "-m", "frog", "giao", *args, "--cwd", str(root),
         "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
         "--price-in", "1000,0", "--max-tokens", "256"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


class GiaoExecuteTest(unittest.TestCase):
    def test_validator_di_het_giao_den_promote(self):
        brief = {
            "goal": "Sua sum_to",
            "deliverables": ["sum_to.py"],
            "acceptance_criteria": [{
                "schema": 1, "id": "sum", "text": "sum_to(3) == 6",
                "validator": {
                    "kind": "contains", "path": "sum_to.py",
                    "must_contain": ["range(n + 1)"], "must_not_contain": [],
                },
            }],
            "constraints": [], "assumptions": [], "questions": [],
            "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
        }
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "sum_to.py").write_text(
                    "def sum_to(n):\n    return range(n)\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa sum_to.py", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("bàn giao: đủ", ran.stdout)
                self.assertIn("range(n + 1)", (root / "sum_to.py").read_text(encoding="utf-8"))
                self.assertIn("kiểm trên bản staged (hash ", ran.stdout)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_worker_sua_file_qua_tool(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        brief = _brief(cmd)
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stderr + opened.stdout)
                run = next(line.split(": ", 1)[1].strip()
                           for line in opened.stdout.splitlines() if line.startswith("Run: "))
                ran = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("bàn giao: đủ", ran.stdout)
                self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
                self.assertTrue((root / ".frog" / "runs" / run / "checkpoint.json").is_file())
                self.assertFalse((root / ".frog-giao").exists())
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
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = next(line.split(": ", 1)[1].strip()
                           for line in opened.stdout.splitlines() if line.startswith("Run: "))
                checked = _frog(root, base, ["--run", run, "--grant", cmd, "--check-only"])
                self.assertNotEqual(checked.returncode, 0, checked.stdout)
                self.assertIn("chưa phải hoàn thành nhiệm vụ", checked.stdout)
                self.assertNotIn("bàn giao: đủ", checked.stdout)
                self.assertFalse((root / ".frog" / "runs" / run / "checkpoint.json").exists())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_worker_tao_json(self):
        brief = {
            "goal": "Ghi rows.json",
            "deliverables": ["rows.json"],
            "acceptance_criteria": [{
                "schema": 1, "id": "inv", "text": "moi phan tu co invoice_id",
                "validator": {
                    "kind": "json_keys", "path": "rows.json", "expect": "array",
                    "required": ["invoice_id"], "forbidden": ["token"],
                },
            }],
            "constraints": [], "assumptions": [], "questions": [],
            "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
        }
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "rows.json").write_text("[]\n", encoding="utf-8")
                opened = _frog(root, base, ["Ghi rows.json", "--approve-brief"])
                self.assertEqual(opened.returncode, 0, opened.stderr + opened.stdout)
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("verified", ran.stdout)
                loaded = json.loads((root / "rows.json").read_text(encoding="utf-8"))
                self.assertEqual(loaded[0]["invoice_id"], "a")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_walk_away_ban_giao_manual_co_nhan(self):
        brief = {
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
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "report.md").write_text("", encoding="utf-8")
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief",
                                            "--autonomy", "walk-away"])
                self.assertNotEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                self.assertIn("bàn giao: chưa", opened.stdout)
                self.assertNotIn("bàn giao dựa trên verifier", opened.stdout)
                self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_watch_khong_ban_giao_manual(self):
        brief = {
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
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "report.md").write_text("", encoding="utf-8")
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertNotEqual(ran.returncode, 0)
                self.assertIn("bàn giao: chưa", ran.stdout)
                self.assertNotIn("bàn giao dựa trên verifier", ran.stdout)
                self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_worker_tao_bao_cao(self):
        brief = {
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
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "report.md").write_text("", encoding="utf-8")
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertNotEqual(ran.returncode, 0, ran.stdout)
                self.assertIn("verified", ran.stdout)
                self.assertIn("needs_confirmation", ran.stdout)
                self.assertIn("bàn giao: chưa", ran.stdout)
                self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "")
                staged = list((root / ".frog" / "staging").glob("**/*.withheld/report.md"))
                self.assertTrue(staged, ran.stdout)
                self.assertIn("Nguon:", staged[0].read_text(encoding="utf-8"))
                again = _frog(root, base, ["--run", run, "--confirm", "tone", "--artifact", "report.md"])
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertIn("người dùng xác nhận", again.stdout)
                self.assertIn("user_confirmed", again.stdout)
                self.assertIn("Nguon:", (root / "report.md").read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_walk_away_validator_fail_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py SAI", "--approve-brief",
                                            "--autonomy", "walk-away"])
                self.assertNotEqual(opened.returncode, 0, opened.stdout)
                self.assertNotIn("bàn giao dựa trên verifier", opened.stdout)
                self.assertIn("return a - b", (root / "calc.py").read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_worker_lam_sai_khong_ban_giao(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py SAI", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run, "--grant", cmd])
                self.assertNotEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertNotIn("bàn giao: đủ", ran.stdout)
                self.assertIn("return a - b", (root / "calc.py").read_text(encoding="utf-8"))
                staged = list((root / ".frog" / "staging").glob("**/*.withheld/calc.py"))
                self.assertTrue(staged, ran.stdout)
                self.assertIn("return 0", staged[0].read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_khong_cap_quyen_khong_thuc_thi(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                ran = _frog(root, base, ["--run", run])
                self.assertEqual(ran.returncode, 8, ran.stdout)
                self.assertIn("không thực thi", ran.stdout)
                self.assertIn("return a - b", (root / "calc.py").read_text(encoding="utf-8"))
                self.assertFalse((root / ".frog" / "runs" / run / "checkpoint.json").exists())
        finally:
            srv.shutdown()
            srv.server_close()

    def test_doi_yeu_cau_khong_dung_grant_cu(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        srv, base = _serve(_brief(cmd))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
                opened = _frog(root, base, ["Sửa calc.py thành phép cộng", "--approve-brief"])
                run = _id(opened.stdout)
                changed = _frog(root, base, ["--run", run, "--change", "Ghi rows.json"])
                self.assertEqual(changed.returncode, 2, changed.stdout)
                self.assertIn(run, changed.stdout)
                fresh = _frog(root, base, ["Ghi rows.json", "--previous", run, "--approve-brief"])
                new_id = _id(fresh.stdout)
                state = json.loads((root / ".frog" / "runs" / new_id / "handoff.json").read_text(encoding="utf-8"))
                self.assertEqual(state["grants"], [])
                self.assertEqual(state["previous"], run)
                ran = _frog(root, base, ["--run", new_id])
                self.assertNotIn("bàn giao: đủ", ran.stdout + ran.stderr)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_v09_ban_nhap_khong_ban_giao_du_verifier_pass(self):
        brief = {
            "goal": "Ghi noi dung BAN NHAP vao tep label.txt.",
            "deliverables": ["Tệp ghost.py chua code"],
            "acceptance_criteria": [
                "Tệp có tên chính xác là label.txt.",
                "Nội dung tệp là \"BAN NHAP\".",
            ],
            "constraints": [],
            "assumptions": [],
            "questions": [],
            "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
        }
        srv, base = _serve(brief)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "label.txt").write_text("BAN CUOI\n", encoding="utf-8")
                opened = _frog(root, base, [
                    "Ghi label.txt là BAN NHAP", "--approve-brief", "--autonomy", "walk-away"])
                run = _id(opened.stdout)
                self.assertNotEqual(opened.returncode, 0, opened.stdout + opened.stderr)
                self.assertIn("chờ người chọn file", opened.stdout)
                self.assertNotIn("bàn giao dựa trên verifier", opened.stdout)
                self.assertFalse((root / "ghost.py").exists())
                self.assertEqual((root / "label.txt").read_text(encoding="utf-8"), "BAN CUOI\n")
                state = json.loads((root / ".frog" / "runs" / run / "handoff.json").read_text(encoding="utf-8"))
                self.assertFalse(state["promoted"])
                self.assertIn("pending_files", state)
                self.assertEqual(state["brief"]["deliverables"], ["Tệp ghost.py chua code"])
                trace = (root / ".frog" / "runs" / run / "trace.jsonl").read_text(encoding="utf-8")
                self.assertIn("\"source\": \"workspace\"", trace)
        finally:
            srv.shutdown()
            srv.server_close()


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
