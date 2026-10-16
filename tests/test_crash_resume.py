"""Ngắt tiến trình thật rồi resume. Không dùng snapshot trong cùng process."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Hold(BaseHTTPRequestHandler):
    worker_posts = 0
    verifier_posts = 0
    release = threading.Event()

    def log_message(self, *_a):
        return

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}
        system = str(body.get("system") or "")
        if "VERIFIER" in system:
            _Hold.verifier_posts += 1
            _Hold.release.wait(8)
            text = '{"verdict":"PASS","reasons":["khop"],"evidence":[],"confidence":0.9}'
        else:
            _Hold.worker_posts += 1
            text = "xong"
        data = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 2, "output_tokens": 1}}
        blob = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        return


def _serve():
    srv = _Server(("127.0.0.1", 0), _Hold)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _run(root: Path, url: str, resume: str | None, brief: Path | None,
         extra: dict | None = None, approve: bool = False):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    for name in list(env):
        if name.endswith("_API_KEY"):
            env.pop(name, None)
    env["ANTHROPIC_API_KEY"] = "local"
    if extra:
        env.update(extra)
    cmd = [sys.executable, "-m", "frog", "team"]
    if resume:
        cmd += ["--resume", resume]
    else:
        cmd += ["tom tat tai lieu cong khai", "--intake", "off",
                "--surface", "write_external", "--labels", "internal",
                "--records", "10", "--dollars", "0"]
    cmd += ["--provider", "anthropic", "--base-url", url,
            "--price-in", "1000,0", "--max-tokens", "64", "--oracle", "off",
            "--out", "out"]
    if brief is not None:
        cmd += ["--brief", str(brief)]
    if approve:
        cmd += ["--approve"]
    return subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)


class CrashResumeTest(unittest.TestCase):
    def setUp(self):
        _Hold.worker_posts = 0
        _Hold.verifier_posts = 0
        _Hold.release = threading.Event()

    def test_kill_sau_worker_khong_goi_lai_worker(self):
        srv, url = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                proc = _run(root, url, None, None)
                deadline = time.time() + 15
                data = None
                while time.time() < deadline:
                    hits = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                    if hits:
                        try:
                            data = json.loads(hits[0].read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            data = None
                        if data and int(data.get("next_index") or 0) >= 1:
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(data)
                self.assertGreaterEqual(int(data["next_index"]), 1)
                proc.kill()
                proc.wait(timeout=10)
                _Hold.release.set()
                workers_after_kill = _Hold.worker_posts
                second = _run(root, url, data["id"], None)
                out, err = second.communicate(timeout=20)
                self.assertEqual(_Hold.worker_posts, workers_after_kill)
                saved = json.loads(
                    (root / ".mira" / "runs" / data["id"] / "checkpoint.json").read_text(
                        encoding="utf-8"))
                self.assertGreaterEqual(len(saved["ledger"]["rows"]), 1)
                self.assertEqual(
                    [row["role"] for row in saved["ledger"]["rows"]].count("worker"), 1)
        finally:
            _Hold.release.set()
            srv.shutdown()

    def test_doi_brief_sau_kill_khong_dung_ket_qua_cu(self):
        srv, url = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                proc = _run(root, url, None, None)
                deadline = time.time() + 15
                data = None
                while time.time() < deadline:
                    hits = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                    if hits:
                        try:
                            data = json.loads(hits[0].read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            data = None
                        if data and int(data.get("next_index") or 0) >= 1:
                            break
                    time.sleep(0.05)
                proc.kill()
                proc.wait(timeout=10)
                _Hold.release.set()
                brief = {
                    "goal": "tom tat",
                    "deliverables": ["bang so"],
                    "acceptance_criteria": ["co nguon"],
                    "constraints": [],
                    "assumptions": [],
                    "questions": [],
                    "per_role_hints": {"planner": "", "worker": "", "verifier": ""},
                }
                path = root / "brief.json"
                path.write_text(json.dumps(brief), encoding="utf-8")
                # Checkpoint từ lần chạy không có brief. Gắn brief khác hash.
                data["brief"] = dict(brief)
                data["brief"]["deliverables"] = ["mot doan"]
                data["brief_hash"] = "cu"
                (root / ".mira" / "runs" / data["id"] / "checkpoint.json").write_text(
                    json.dumps(data), encoding="utf-8")
                second = _run(root, url, data["id"], path)
                out, _err = second.communicate(timeout=20)
                text = (out or b"").decode("utf-8", "replace")
                self.assertNotEqual(second.returncode, 0)
                self.assertIn("không tiếp tục", text)
                saved = json.loads(
                    (root / ".mira" / "runs" / data["id"] / "checkpoint.json").read_text(
                        encoding="utf-8"))
                self.assertEqual(saved["brief"]["deliverables"], ["mot doan"])
        finally:
            _Hold.release.set()
            srv.shutdown()

    def test_kill_luc_ghi_checkpoint_khong_nhan_file_dut(self):
        srv, url = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                flag = root / "pause.txt"
                proc = _run(root, url, None, None, extra={
                    "MIRA_PAUSE": "checkpoint",
                    "MIRA_PAUSE_FLAG": str(flag),
                })
                deadline = time.time() + 15
                while time.time() < deadline and not flag.exists():
                    time.sleep(0.05)
                self.assertTrue(flag.exists(), "chưa tới lúc ghi checkpoint")
                proc.kill()
                proc.wait(timeout=10)
                _Hold.release.set()
                self.assertEqual(list((root / ".mira" / "runs").glob("*/checkpoint.json")), [])
                tmps = list((root / ".mira" / "runs").glob("*/*.json.tmp"))
                self.assertEqual(len(tmps), 1)
                payload = json.loads(tmps[0].read_text(encoding="utf-8"))
                before = _Hold.worker_posts
                second = _run(root, url, payload["id"], None)
                out, _err = second.communicate(timeout=20)
                text = (out or b"").decode("utf-8", "replace")
                self.assertEqual(second.returncode, 2)
                self.assertIn("checkpoint", text)
                self.assertEqual(_Hold.worker_posts, before)
                self.assertFalse((root / "out" / "result.md").exists())
        finally:
            _Hold.release.set()
            srv.shutdown()

    def test_kill_truoc_ban_giao_roi_resume_mot_lan(self):
        srv, url = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                flag = root / "pause.txt"
                _Hold.release.set()
                proc = _run(root, url, None, None, approve=True, extra={
                    "MIRA_PAUSE": "handoff",
                    "MIRA_PAUSE_FLAG": str(flag),
                })
                deadline = time.time() + 20
                while time.time() < deadline and not flag.exists():
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                err = b""
                if not flag.exists():
                    err = proc.stderr.read() if proc.stderr else b""
                self.assertTrue(flag.exists(), err.decode("utf-8", "replace"))
                proc.kill()
                proc.wait(timeout=10)
                before = _Hold.worker_posts
                self.assertEqual(list((root / "out").glob("*/result.md")), [])
                hits = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                data = json.loads(hits[0].read_text(encoding="utf-8"))
                second = _run(root, url, data["id"], None, approve=True)
                second.communicate(timeout=20)
                self.assertEqual(_Hold.worker_posts, before)
                self.assertEqual(len(list((root / "out").glob("*/result.md"))), 1)
                rows = json.loads(hits[0].read_text(encoding="utf-8"))["ledger"]["rows"]
                self.assertEqual([row["role"] for row in rows].count("worker"), 1)
        finally:
            _Hold.release.set()
            srv.shutdown()

    def test_doi_artifact_sau_kill_khong_ban_giao(self):
        from frog.team import tree_hash
        srv, url = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                proc = _run(root, url, None, None)
                deadline = time.time() + 15
                data = None
                while time.time() < deadline:
                    hits = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                    if hits:
                        try:
                            data = json.loads(hits[0].read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            data = None
                        if data and int(data.get("next_index") or 0) >= 1:
                            break
                    time.sleep(0.05)
                proc.kill()
                proc.wait(timeout=10)
                _Hold.release.set()
                self.assertIsNotNone(data)
                stage = Path(data["staging"]) if data.get("staging") else (
                    root / ".mira" / "staging" / data["id"])
                stage.mkdir(parents=True, exist_ok=True)
                note = stage / "note.txt"
                note.write_text("mot", encoding="utf-8")
                data["staging"] = str(stage)
                data["staging_hash"] = tree_hash(stage)
                dest = root / ".mira" / "runs" / data["id"] / "checkpoint.json"
                dest.write_text(json.dumps(data), encoding="utf-8")
                note.write_text("hai", encoding="utf-8")
                before = _Hold.worker_posts
                second = _run(root, url, data["id"], None, approve=True)
                out, _err = second.communicate(timeout=20)
                text = (out or b"").decode("utf-8", "replace")
                self.assertEqual(second.returncode, 2)
                self.assertIn("artifact đã đổi", text)
                self.assertEqual(_Hold.worker_posts, before)
                self.assertFalse((root / "out" / "result.md").exists())
        finally:
            _Hold.release.set()
            srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
