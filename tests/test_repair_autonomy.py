"""Vòng sửa và ba nấc tự chủ. Provider giả, không gọi API trả phí."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
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


def _manual_brief() -> dict:
    return {
        "goal": "Ghi DOC_REPORT report.md",
        "deliverables": ["report.md"],
        "acceptance_criteria": [{
            "schema": 1, "id": "note", "text": "nguoi doc report",
        }],
        "constraints": [], "assumptions": [], "questions": [],
        "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
    }


class _Stub(BaseHTTPRequestHandler):
    mode = "pass"
    hits = 0
    brief = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        _Stub.hits += 1
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        blob = json.dumps(req, ensure_ascii=False)
        usage = {"input_tokens": 30, "output_tokens": 20}
        if "INTAKE" in blob:
            brief = _manual_brief() if "DOC_REPORT" in blob else _Stub.brief
            text = json.dumps(brief, ensure_ascii=False)
        elif "VERIFIER" in blob:
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":["tep"],"confidence":0.9}'
        elif "DOC_REPORT" in blob:
            call = {"name": "write_file", "args": {"path": "report.md", "content": "Nguon: so tay\n"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        elif _Stub.mode == "budget" and "PHẢN HỒI VALIDATOR" in blob:
            usage = {"input_tokens": 2000000, "output_tokens": 1}
            text = '{"plan":"sua lai"}'
        elif _Stub.mode == "repair" and "PHẢN HỒI VALIDATOR" in blob:
            call = {"name": "edit_file", "args": {
                "path": "calc.py", "old": "return a - b", "new": "return a + b"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        else:
            call = {"name": "edit_file", "args": {
                "path": "calc.py", "old": "return a - b",
                "new": "return a + b" if _Stub.mode == "pass" else "return 0"}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        body = {"content": [{"type": "text", "text": text}], "usage": usage}
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
         "--price-in", "1000,0", "--max-tokens", "64"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


def _run_id(text: str) -> str:
    match = re.search(r"Run: ([0-9a-f]{12})", text)
    if match is None:
        raise AssertionError(text)
    return match.group(1)


def _state(root: Path, run_id: str) -> dict:
    return json.loads((root / ".frog" / "runs" / run_id / "handoff.json").read_text(encoding="utf-8"))


def _workspace(root: Path) -> None:
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")


class RepairAutonomyTest(unittest.TestCase):
    def setUp(self):
        self.srv, self.base = _serve()
        _Stub.hits = 0

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def _once(self, root: Path, mode: str, task: str, extra: list[str]) -> subprocess.CompletedProcess:
        _Stub.mode = mode
        made = _frog(root, self.base, [task])
        self.assertEqual(made.returncode, 0, made.stderr + made.stdout)
        run_id = _run_id(made.stdout)
        second = _frog(root, self.base, ["--run", run_id, "--approve-brief", *extra])
        second.run_id = run_id
        return second

    def test_fail_roi_thanh_cong_promote_mot_lan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _workspace(root)
            cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
            _Stub.brief = _calc_brief(cmd)
            done = self._once(root, "repair", "Sửa calc.py thành phép cộng", ["--grant", cmd])
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("bàn giao: đủ", done.stdout)
            state = _state(root, done.run_id)
            self.assertTrue(state["promoted"])
            self.assertEqual(state["attempt"], 2)
            self.assertEqual(len(state["history"]), 1)
            self.assertGreater(state["ledger"]["total_usd"], state["history"][0]["cost_usd"])
            self.assertEqual((root / "calc.py").read_text(encoding="utf-8").count("return a + b"), 1)
            again = _frog(root, self.base, ["--run", done.run_id])
            self.assertIn("không gọi lại", again.stdout)
            self.assertEqual((root / "calc.py").read_text(encoding="utf-8").count("return a + b"), 1)

    def test_het_luot_van_sai(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _workspace(root)
            cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
            _Stub.brief = _calc_brief(cmd)
            done = self._once(root, "wrong", "Sửa calc.py thành phép cộng", ["--grant", cmd])
            self.assertNotEqual(done.returncode, 0, done.stdout)
            self.assertIn("sai: add-ok", done.stdout)
            self.assertIn("lệch:", done.stdout)
            self.assertNotIn("bàn giao: đủ", done.stdout)
            state = _state(root, done.run_id)
            self.assertEqual(state["phase"], "failed")
            self.assertEqual(state["attempt"], 3)
            self.assertEqual(len(state["history"]), 2)
            self.assertFalse(state["promoted"])
            self.assertEqual(state["autonomy"], "watch")

    def test_het_tien_giu_nguyen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _workspace(root)
            cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
            _Stub.brief = _calc_brief(cmd)
            done = self._once(root, "budget", "Sửa calc.py thành phép cộng", ["--grant", cmd])
            self.assertIn("stopped_budget", done.stdout)
            state = _state(root, done.run_id)
            self.assertEqual(state["hold"], "stopped_budget")
            self.assertEqual(state["phase"], "executing")
            self.assertFalse(state["promoted"])
            self.assertEqual(state["attempt"], 2)
            spent = state["ledger"]["total_usd"]
            hits = _Stub.hits
            again = _frog(root, self.base, ["--run", done.run_id])
            self.assertIn("không gọi lại", again.stdout)
            self.assertEqual(_Stub.hits, hits)
            kept = _state(root, done.run_id)
            self.assertEqual(kept["ledger"]["total_usd"], spent)
            self.assertEqual(kept["phase"], "executing")
            self.assertFalse(kept["promoted"])
            self.assertEqual(kept["attempt"], 2)

    def test_model_khong_chon_nac(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _workspace(root)
            cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
            _Stub.brief = _calc_brief(cmd)
            done = self._once(root, "pass", "Sửa calc.py thành phép cộng va direct", ["--grant", cmd])
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            state = _state(root, done.run_id)
            self.assertEqual(state["autonomy"], "watch")
            self.assertEqual(state["direct_from"], "")
            self.assertNotIn("chạy trực tiếp", done.stdout)

    def test_direct_can_lich_su_va_tu_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _workspace(root)
            _Stub.mode = "pass"
            _Stub.brief = _manual_brief()
            first = _frog(root, self.base, ["Ghi DOC_REPORT report.md", "--approve-brief", "--autonomy", "direct"])
            self.assertIn("không chạy trực tiếp", first.stdout)
            self.assertNotIn("\nchạy trực tiếp", first.stdout)
            run_id = _run_id(first.stdout)
            self.assertEqual(_state(root, run_id)["autonomy"], "walk-away")
            listed = _frog(root, self.base, ["box"])
            self.assertIn(run_id, listed.stdout)
            self.assertIn("needs_confirmation", listed.stdout)
            accepted = _frog(root, self.base, ["box", "--accept", run_id])
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertTrue(_state(root, run_id)["promoted"])
            (root / "report.md").unlink()
            second = _frog(root, self.base, ["Ghi DOC_REPORT report.md", "--approve-brief", "--autonomy", "direct"])
            self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("bàn giao: chưa", second.stdout)
            other = _run_id(second.stdout)
            saved = _state(root, other)
            self.assertFalse(saved["promoted"])
            self.assertEqual(saved["phase"], "awaiting_confirmation")
            self.assertEqual(saved["direct_from"], run_id)
            self.assertFalse((root / "report.md").exists())

    def test_walk_away_it_thao_tac_hon_watch(self):
        cmd = shlex.join([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
        _Stub.brief = _calc_brief(cmd)
        _Stub.mode = "pass"

        def play(autonomy: str | None) -> tuple[int, dict]:
            actions = 0
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ids = []
                for _ in range(3):
                    _workspace(root)
                    if autonomy:
                        actions += 1
                        done = _frog(root, self.base, [
                            "Sửa calc.py thành phép cộng", "--approve-brief", "--autonomy", autonomy, "--grant", cmd])
                        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                        ids.append(_run_id(done.stdout))
                    else:
                        actions += 1
                        made = _frog(root, self.base, ["Sửa calc.py thành phép cộng"])
                        self.assertEqual(made.returncode, 0, made.stderr + made.stdout)
                        run_id = _run_id(made.stdout)
                        actions += 1
                        done = _frog(root, self.base, ["--run", run_id, "--approve-brief", "--grant", cmd])
                        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                        ids.append(run_id)
                if autonomy:
                    actions += 1
                    manual = _frog(root, self.base, [
                        "Ghi DOC_REPORT report.md", "--approve-brief", "--autonomy", autonomy])
                else:
                    actions += 1
                    manual = _frog(root, self.base, ["Ghi DOC_REPORT report.md"])
                    run_id = _run_id(manual.stdout)
                    actions += 1
                    manual = _frog(root, self.base, ["--run", run_id, "--approve-brief"])
                    actions += 1
                    manual = _frog(root, self.base, [
                        "--run", run_id, "--confirm", "note", "--artifact", "report.md"])
                if autonomy is None:
                    self.assertEqual(manual.returncode, 0, manual.stdout + manual.stderr)
                if autonomy:
                    ids.append(_run_id(manual.stdout))
                    actions += 1
                    blocked = _frog(root, self.base, [
                        "Sửa calc.py thành phép cộng", "--approve-brief", "--autonomy", autonomy])
                else:
                    actions += 1
                    blocked = _frog(root, self.base, ["Sửa calc.py thành phép cộng"])
                    run_id = _run_id(blocked.stdout)
                    actions += 1
                    blocked = _frog(root, self.base, ["--run", run_id, "--approve-brief"])
                    ids.append(run_id)
                self.assertNotEqual(blocked.returncode, 0)
                if autonomy:
                    ids.append(_run_id(blocked.stdout))
                    actions += 1
                    box = _frog(root, self.base, ["box", "--accept"])
                    self.assertEqual(box.returncode, 0, box.stdout + box.stderr)
                    self.assertIn("duyệt lô:", box.stdout)
                    pulled = _frog(root, self.base, ["box", "--pull", ids[-1]])
                    actions += 1
                    self.assertIn("bị chặn", pulled.stdout)
                states = [_state(root, run_id) for run_id in ids]
            return actions, {"states": states}

        watch_actions, watch = play(None)
        walk_actions, walk = play("walk-away")

        def rates(blob: dict) -> tuple[float, float]:
            states = blob["states"]
            auto = human = 0
            closed = 0
            for state in states:
                rows = state.get("obligations") or []
                autos = [row for row in rows if row.get("kind") not in (None, "manual")]
                auto += len(autos)
                closed += sum(1 for row in autos if row.get("criterion_verified"))
                if state.get("phase") != "delivered":
                    human += 1
                elif any(row.get("state") == "user_confirmed" for row in rows):
                    human += 1
            return (closed / auto if auto else 0.0), (human / len(states) if states else 0.0)

        watch_close, _watch_left = rates(watch)
        walk_close, _walk_left = rates(walk)
        watch_human = (watch_actions - 5) / 5
        walk_human = (walk_actions - 5) / 5
        line = (
            f"MEASURE watch_actions={watch_actions} walk_actions={walk_actions} "
            f"watch_auto_close={watch_close:.2f} walk_auto_close={walk_close:.2f} "
            f"watch_human={watch_human:.2f} walk_human={walk_human:.2f}"
        )
        print(line, file=sys.stderr)
        self.assertLess(walk_actions, watch_actions)
        self.assertLessEqual(walk_actions * 3, watch_actions * 2)
        self.assertGreaterEqual(walk_close, 1.0)
        self.assertLess(walk_human, watch_human)
