"""Request được ghi dispatched trước khi gửi. Gián đoạn không xóa khoản đó."""
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
from types import SimpleNamespace

from mira.agent import _priced_call
from mira.intake import charged_call
from mira.providers import ProviderError
from mira.team import Ledger

ROOT = Path(__file__).resolve().parents[1]


class _Prov:
    name = "anthropic"
    max_tokens = 1

    def __init__(self, usage, fail=False):
        self.usage = usage
        self.fail = fail
        self.states: list[list[str]] = []

    def available(self):
        return True

    def call(self, system, user):
        self.states.append([row["state"] for row in self.ledger.requests])
        if self.fail:
            raise ProviderError("đứt")
        return "xong", self.usage


class RequestLedgerTest(unittest.TestCase):
    def test_dispatched_truoc_khi_tra_loi_va_vuot_uoc_luong(self):
        ledger = Ledger()
        seen = []
        ledger.on_persist = lambda: seen.append([dict(row) for row in ledger.requests])
        prov = _Prov({"in": 1, "out": 10})
        prov.ledger = ledger
        text, usage, usd, rid = ledger.tracked_call(
            "worker", "sonnet-5.5", prov, "sys", "user", {"in": 0, "out": 1_000_000},
            source="cli", max_out=1, declared_by_user=True)
        self.assertEqual(text, "xong")
        self.assertEqual(prov.states[0], ["dispatched"])
        self.assertEqual(ledger.requests[0]["state"], "settled")
        self.assertTrue(ledger.requests[0]["exceeded"])
        self.assertGreater(usd, ledger.requests[0]["hold"])
        self.assertIn("không phải trần", ledger.requests[0]["estimate"])
        self.assertTrue(any(row["state"] == "dispatched" for snap in seen for row in snap))

    def test_intake_cung_so_request(self):
        ledger = Ledger()
        prov = _Prov({"in": 2, "output": 1})
        prov.usage = {"in": 2, "out": 1}
        prov.ledger = ledger
        text, meta = charged_call(ledger, "intake", "sonnet-5.5", prov, "sys", "user",
                                  declared_price=(0, 1))
        self.assertEqual(text, "xong")
        self.assertEqual(ledger.requests[0]["role"], "intake")
        self.assertEqual(ledger.requests[0]["state"], "settled")
        self.assertTrue(meta.get("request_id"))

    def test_worker_agent_ghi_request(self):
        ledger = Ledger()
        prov = _Prov({"in": 1, "out": 1})
        prov.ledger = ledger
        session = SimpleNamespace(ledger=ledger, declared_price=(0, 1))
        text, usage = _priced_call(session, prov, "sonnet-5.5", "sys", "user")
        self.assertEqual(text, "xong")
        self.assertEqual(ledger.requests[0]["state"], "settled")
        self.assertEqual(usage["out"], 1)

    def test_loi_sau_khi_gui_la_uncertain(self):
        ledger = Ledger()
        prov = _Prov({"in": 1, "out": 1}, fail=True)
        prov.ledger = ledger
        with self.assertRaises(ProviderError):
            ledger.tracked_call(
                "prompt_writer", "sonnet-5.5", prov, "sys", "user",
                {"in": 0, "out": 1}, source="cli", max_out=1)
        self.assertEqual(ledger.requests[0]["state"], "uncertain")
        self.assertGreater(ledger.uncertain_usd, 0)
        self.assertEqual(ledger.reserved, 0)


class _Hold(BaseHTTPRequestHandler):
    release = threading.Event()

    def log_message(self, *_a):
        return

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        self.rfile.read(n)
        _Hold.release.wait(8)
        data = {"content": [{"type": "text", "text": "xong"}],
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


class InterruptRequestTest(unittest.TestCase):
    def test_kill_giua_request_roi_resume_con_khoan_chua_doi_soat(self):
        _Hold.release = threading.Event()
        srv = _Server(("127.0.0.1", 0), _Hold)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT)
                env["PYTHONIOENCODING"] = "utf-8"
                env["ANTHROPIC_API_KEY"] = "local"
                cmd = [sys.executable, "-m", "mira", "team", "tom tat tai lieu cong khai",
                       "--intake", "off", "--surface", "read_only", "--labels", "public",
                       "--records", "10", "--dollars", "0", "--provider", "anthropic",
                       "--base-url", url, "--price-in", "1000,0", "--max-tokens", "64",
                       "--oracle", "off", "--out", "out"]
                proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                deadline = time.time() + 15
                data = None
                while time.time() < deadline:
                    hits = list((root / ".mira" / "runs").glob("*/checkpoint.json"))
                    if hits:
                        try:
                            data = json.loads(hits[0].read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            data = None
                        reqs = (data or {}).get("ledger", {}).get("requests") or []
                        if any(row.get("state") == "dispatched" for row in reqs):
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(data)
                self.assertTrue(any(row.get("state") == "dispatched"
                                    for row in data["ledger"]["requests"]))
                open_id = next(row["id"] for row in data["ledger"]["requests"]
                               if row["state"] == "dispatched")
                proc.kill()
                proc.wait(timeout=10)
                _Hold.release.set()
                second = subprocess.run(
                    [sys.executable, "-m", "mira", "team", "--resume", data["id"],
                     "--provider", "anthropic", "--base-url", url,
                     "--price-in", "1000,0", "--max-tokens", "64", "--oracle", "off",
                     "--out", "out"],
                    cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=30)
                saved = json.loads(
                    (root / ".mira" / "runs" / data["id"] / "checkpoint.json").read_text(
                        encoding="utf-8"))
                rows = saved["ledger"]["requests"]
                old = next(row for row in rows if row["id"] == open_id)
                self.assertEqual(old["state"], "uncertain")
                self.assertGreater(saved["ledger"]["uncertain_usd"], 0)
                self.assertNotEqual(second.returncode, None)
        finally:
            _Hold.release.set()
            srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
