import json
import tempfile
import unittest
from pathlib import Path

from frog.bench import run_eval, run_one
from frog.repl import save_session
from frog.tools import Session


class EvalTest(unittest.TestCase):
    def test_hai_viec_deu_qua(self):
        root = Path(__file__).resolve().parents[1] / "eval" / "bench" / "tasks"
        rows = [run_one(p) for p in sorted(root.iterdir()) if (p / "task.json").is_file()]
        names = [r["name"] for r in rows]
        self.assertEqual(
            names,
            ["command_done", "forgot_fact", "missing_file", "plan_no_write",
             "remember_next", "role_recruit", "script_unopened", "skill_deleted",
             "stray_command", "stray_content", "stray_path", "swap_values",
             "tool_limit", "use_skill"])
        by = {r["name"]: r for r in rows}
        self.assertEqual(by["use_skill"]["skills"], "sua-gia-tri")
        self.assertEqual(by["missing_file"]["skills"], "kem")
        self.assertEqual(by["tool_limit"]["skills"], "gioi-han")
        self.assertEqual(by["skill_deleted"]["skills"], "mot,hai")
        self.assertTrue(all(r["ok"] for r in rows))
        self.assertGreater(by["swap_values"]["costUsd"], 0)
        self.assertTrue(all(r["layer"] in ("governance", "verification", "context", "tool") for r in rows))
        self.assertEqual(run_eval(root), 0)

    def test_so_su_kien_vao_jsonl(self):
        from frog import repl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("xin chao\n", encoding="utf-8")
            session = Session(root=root, mode="acceptEdits", approve=lambda t, a: True)
            session.log_event("model_turn", turn=1, protocol="text")
            session.call("read_file", {"path": "a.txt"})
            session.log_event("stop", reason="xong")
            kinds = [row["kind"] for row in session.trace]
            self.assertEqual(kinds[0], "model_turn")
            self.assertIn("tool_call", kinds)
            self.assertIn("tool_result", kinds)
            self.assertEqual(kinds[-1], "stop")
            old = repl.SESS_DIR
            repl.SESS_DIR = Path(tmp) / "sessions"
            try:
                path = save_session("t1", [{"role": "user", "content": "doc"}], list(session.trace), {})
                lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            finally:
                repl.SESS_DIR = old
            saved = [line["kind"] for line in lines if line.get("type") == "event"]
            self.assertEqual(saved, kinds)


if __name__ == "__main__":
    unittest.main()
