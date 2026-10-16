"""Brief object phải đi qua CLI tới bước kiểm. Chuỗi cũ vẫn hợp lệ."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from frog.contract import contract_diff
from frog.intake import brief_hash, load_brief_file
from frog.team import resume_team, write_checkpoint

ROOT = Path(__file__).resolve().parents[1]


def _shell() -> dict:
    return {"planner": "", "worker": "", "verifier": ""}


def _brief(criteria) -> dict:
    return {
        "goal": "tom tat tai lieu cong khai",
        "deliverables": ["mot doan"],
        "acceptance_criteria": criteria,
        "constraints": [],
        "assumptions": [],
        "questions": [],
        "per_role_hints": _shell(),
    }


def _obj(cid: str, text: str, cmd: str) -> dict:
    return {
        "schema": 1,
        "id": cid,
        "text": text,
        "cmd": cmd,
        "proves": "",
        "artifact": "",
    }


class _Srv(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        return


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        return

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        self.rfile.read(n)
        data = {"content": [{"type": "text", "text": "xong"}],
                "usage": {"input_tokens": 2, "output_tokens": 1}}
        blob = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


class CriteriaSchemaTest(unittest.TestCase):
    def test_cli_nap_object_va_toi_buoc_kiem(self):
        cmd = sys.executable + " -c \"raise SystemExit(0)\""
        brief = _brief([_obj("crit-exit", "lenh thoat 0 la buoc kiem", cmd)])
        srv = _Srv(("127.0.0.1", 0), _Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / "brief.json"
                path.write_text(json.dumps(brief), encoding="utf-8")
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT)
                env["PYTHONIOENCODING"] = "utf-8"
                env["ANTHROPIC_API_KEY"] = "local"
                proc = subprocess.run(
                    [sys.executable, "-m", "frog", "team", brief["goal"],
                     "--intake", "off", "--brief", str(path), "--require-evidence",
                     "--surface", "read_only", "--labels", "public",
                     "--records", "10", "--dollars", "0", "--approve",
                     "--provider", "anthropic", "--base-url", url,
                     "--price-in", "1000,0", "--max-tokens", "64",
                     "--oracle", "off", "--out", "out"],
                    cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=30)
                text = (proc.stdout or b"").decode("utf-8", "replace")
                held = root / "out" / "withheld.json"
                self.assertNotEqual(proc.returncode, 8, text)
                self.assertIn("crit-exit", text + (held.read_text(encoding="utf-8") if held.exists() else ""))
                self.assertTrue(held.exists(), text)
                rows = json.loads(held.read_text(encoding="utf-8")).get("obligations") or []
                self.assertEqual(rows[0]["criterion_id"], "crit-exit")
                self.assertIn(rows[0]["state"], ("checked", "unverified", "blocked", "failed", "unproven"))
        finally:
            srv.shutdown()

    def test_cli_tu_choi_id_trung(self):
        cmd = "py -c \"raise SystemExit(0)\""
        brief = _brief([
            _obj("same", "cau mot", cmd),
            _obj("same", "cau hai", cmd),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [sys.executable, "-m", "frog", "team", "tom tat",
                 "--intake", "off", "--brief", str(path), "--require-evidence",
                 "--surface", "read_only", "--labels", "public",
                 "--records", "10", "--dollars", "0", "--out", "out"],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=20)
            text = (proc.stdout or b"").decode("utf-8", "replace")
            self.assertEqual(proc.returncode, 8, text)
            self.assertIn("trùng", text)

    def test_contract_khong_bo_object(self):
        old_item = _obj("c1", "co so", "py -c \"raise SystemExit(0)\"")
        new_item = dict(old_item)
        new_item["text"] = "co bang"
        diff = contract_diff(_brief([old_item]), _brief([new_item]))
        self.assertTrue(diff["invalidates"])
        self.assertEqual(diff["scope"], "run")
        blob = " ".join(diff["added_criteria"] + diff["removed_criteria"])
        self.assertIn("c1", blob)
        self.assertIn("co bang", blob)

    def test_chuoi_cu_van_nap_duoc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(_brief(["check: py -c \"raise SystemExit(0)\""])),
                            encoding="utf-8")
            obj, why = load_brief_file(path)
            self.assertIsNotNone(obj, why)
            self.assertIsInstance(obj["acceptance_criteria"][0], str)

    def test_doi_object_huy_ca_run(self):
        old = _brief([_obj("c1", "co so", "py -c \"raise SystemExit(0)\"")])
        new = _brief([_obj("c1", "co bang", "py -c \"raise SystemExit(0)\"")])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_checkpoint(root, {
                "id": "run1", "version": 1, "next_index": 0,
                "task": "tom tat tai lieu cong khai", "steps": [],
                "ledger": {"rows": [], "total_usd": 0.0, "total_in": 0,
                           "total_out": 0, "subagent_runs": 0},
                "staging": None, "status": "ok", "fail_reason": None,
                "brief": old, "brief_hash": brief_hash(old),
                "hints": {"surface": "read_only", "labels": ["public"], "records": 10,
                          "dollars": 0, "reversibility": "C1", "output_type": "free_string"},
                "workers": 1,
            })
            code, res = resume_team(root, "run1", brief=new)
        self.assertEqual(code, 2)
        self.assertEqual(res["contract_diff"]["scope"], "run")
        self.assertIn("c1", " ".join(res["contract_diff"]["lines"]))

    def test_id_trong_bi_tu_choi(self):
        item = _obj("   ", "co so", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(_brief([item])), encoding="utf-8")
            obj, why = load_brief_file(path)
            self.assertIsNone(obj)
            self.assertIn("trống", why)


if __name__ == "__main__":
    unittest.main(verbosity=2)
