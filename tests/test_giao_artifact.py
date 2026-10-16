"""Artifact của một run không được lấy từ run khác hay từ file cũ ở cây nguồn."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _brief() -> dict:
    return {
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


class _Stub(BaseHTTPRequestHandler):
    brief: dict = {}
    report = "Nguon: A\n"

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
        else:
            call = {"name": "write_file", "args": {
                "path": "report.md", "content": _Stub.report}}
            text = "<tool>" + json.dumps(call, ensure_ascii=False) + "</tool>"
        body = {"content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 30, "output_tokens": 40}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
    _Stub.brief = _brief()
    _Stub.report = "Nguon: A\n"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _frog(root: Path, base: str, args: list[str]):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["ANTHROPIC_API_KEY"] = "local"
    for name in list(env):
        if name.endswith("_API_KEY") and name != "ANTHROPIC_API_KEY":
            env.pop(name)
        if name.startswith("MIRA_PRICE"):
            env.pop(name)
    return subprocess.run(
        [sys.executable, "-m", "frog", "giao", *args, "--cwd", str(root),
         "--provider", "anthropic", "--base-url", base, "--model", "claude-test",
         "--price-in", "1000,0", "--max-tokens", "256"],
        cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8")


def _id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Run: "):
            return line.split(": ", 1)[1].strip()
    raise AssertionError(text)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactRunTest(unittest.TestCase):
    def test_xac_nhan_khong_lan_giua_hai_run(self):
        srv, base = _serve()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _Stub.report = "Nguon: A\n"
                opened = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run_a = _id(opened.stdout)
                ran_a = _frog(root, base, ["--run", run_a])
                self.assertIn("chờ xác nhận", ran_a.stdout, ran_a.stdout)
                state_a = json.loads((root / ".frog" / "runs" / run_a / "handoff.json").read_text(encoding="utf-8"))
                names = [str(path.relative_to(state_a["staging"])) for path in Path(state_a["staging"]).rglob("*")]
                staged_a = Path(state_a["staging"]) / "report.md"
                self.assertTrue(staged_a.is_file(), "\n".join(names) + "\n" + ran_a.stdout)
                hash_a = _sha(staged_a)
                _Stub.report = "Nguon: B\n"
                opened_b = _frog(root, base, ["Ghi report.md", "--approve-brief"])
                run_b = _id(opened_b.stdout)
                ran_b = _frog(root, base, ["--run", run_b])
                self.assertIn("chờ xác nhận", ran_b.stdout, ran_b.stdout)
                (root / "report.md").write_text("Nguon: CU\n", encoding="utf-8")
                old_hash = _sha(root / "report.md")
                confirmed = _frog(root, base, [
                    "--run", run_a, "--confirm", "tone", "--artifact", "report.md"])
                self.assertEqual(confirmed.returncode, 0, confirmed.stdout + confirmed.stderr)
                state_a = json.loads((root / ".frog" / "runs" / run_a / "handoff.json").read_text(encoding="utf-8"))
                staged_b = Path(json.loads((root / ".frog" / "runs" / run_b / "handoff.json").read_text(encoding="utf-8"))["staging"]) / "report.md"
                self.assertEqual(staged_b.read_text(encoding="utf-8"), "Nguon: B\n")
                row = state_a["confirmations"][0]
                self.assertEqual(row["sha256"], hash_a)
                self.assertNotEqual(row["sha256"], old_hash)
                self.assertNotEqual(row["sha256"], _sha(staged_b))
                self.assertEqual(row["run_id"], run_a)
                self.assertEqual((root / "report.md").read_text(encoding="utf-8"), "Nguon: A\n")
                from frog.handoff import _load, _save, apply_confirmations
                saved_b = _load(root, run_b)
                saved_b["confirmations"] = [dict(row)]
                _save(root, saved_b)
                judged = apply_confirmations(saved_b, list(saved_b["obligations"]), root)
                tone = next(item for item in judged if item["criterion_id"] == "tone")
                self.assertNotEqual(tone.get("state"), "user_confirmed")
        finally:
            srv.shutdown()
            srv.server_close()
