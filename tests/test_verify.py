"""P1-03: plan_hash SHA256 và xích trace.jsonl."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from frog import team
from frog.pipeline import verify_trace, write_trace_chain


def _chain(directory: Path) -> Path:
    write_trace_chain(
        directory, "ab" * 32,
        [{"role": "worker", "text": "xong"}, {"role": "verifier", "text": "PASS"}],
        None)
    return directory


class VerifyTest(unittest.TestCase):
    def test_khong_sua_verify_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = _chain(Path(tmp) / "run")
            code, reason = verify_trace(directory)
        self.assertEqual(code, 0, reason)

    def test_sua_mot_ky_tu_verify_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = _chain(Path(tmp) / "run")
            path = directory / "trace.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace("xong", "xonk", 1),
                            encoding="utf-8")
            code, reason = verify_trace(directory)
            self.assertEqual(code, 1)
            self.assertIn("lệch", reason)
            self.assertNotIn("xonk", reason)

    def test_xoa_mot_dong_verify_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = _chain(Path(tmp) / "run")
            path = directory / "trace.jsonl"
            rows = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(rows[:1] + rows[2:]) + "\n", encoding="utf-8")
            code, _reason = verify_trace(directory)
        self.assertEqual(code, 1)

    def test_chen_mot_dong_verify_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = _chain(Path(tmp) / "run")
            path = directory / "trace.jsonl"
            rows = path.read_text(encoding="utf-8").splitlines()
            extra = json.dumps({"kind": "chen", "prev_hash": "0" * 64, "hash": "f" * 64})
            path.write_text("\n".join(rows[:1] + [extra] + rows[1:]) + "\n", encoding="utf-8")
            code, _reason = verify_trace(directory)
        self.assertEqual(code, 1)

    def test_plan_hash_la_sha256(self):
        hints = dict(surface="read_only", labels=["internal"], records=50, dollars=0)
        first = team.build_plan("soạn báo cáo", **hints)
        second = team.build_plan("soạn báo cáo", **hints)
        self.assertEqual(first.plan_hash, second.plan_hash)
        self.assertEqual(len(first.plan_hash), 64)
        self.assertRegex(first.plan_hash, r"^[0-9a-f]{64}$")
        old = f"{abs(hash((first.task.id, first.gate_tier))) % 10**12:012d}"
        self.assertNotEqual(first.plan_hash, old)

    def test_frog_verify_thu_muc_bi_sua(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = _chain(Path(tmp) / "run")
            path = directory / "trace.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace("PASS", "PASC", 1),
                            encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [sys.executable, "-m", "frog", "verify", str(directory)],
                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lệch", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
