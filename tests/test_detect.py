"""Kiểm bộ so hai bộ dò injection.

Điều quan trọng nhất: prompt gửi model KHÔNG được chứa nhãn. Nếu rò nhãn vào thì
mọi con số đều vô nghĩa — model chỉ đang đọc đáp án.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import detect                                   # noqa: E402
from frog.detect import Confusion, compare, parse_verdict  # noqa: E402
from frog.tasks import PAYLOAD_SIGNATURES, build_tasks     # noqa: E402

TASKS = build_tasks()
SEEN: list[dict] = []


class _Stub(BaseHTTPRequestHandler):
    """Model giả: trả INJECTION/CLEAN dựa trên dấu hiệu payload trong nội dung."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append(req)
        blob = json.dumps(req, ensure_ascii=False)
        hit = any(s in blob for s in PAYLOAD_SIGNATURES)
        body = ("INJECTION\nCONF: 0.91\nthấy chỉ dẫn gửi dữ liệu ra ngoài"
                if hit else "CLEAN\nCONF: 0.77\nchỉ dẫn hợp lệ")
        data = {"content": [{"type": "text", "text": body}],
                "usage": {"input_tokens": 400, "output_tokens": 30}}
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class TestDocPhanQuyet(unittest.TestCase):
    def test_doc_injection(self):
        v = parse_verdict("INJECTION\nCONF: 0.91\nlý do")
        self.assertTrue(v["detected"])
        self.assertAlmostEqual(v["confidence"], 0.91, places=2)
        self.assertFalse(v["malformed"])

    def test_doc_clean(self):
        v = parse_verdict("CLEAN\nCONF: 0,77\nok")
        self.assertFalse(v["detected"])
        self.assertAlmostEqual(v["confidence"], 0.77, places=2)

    def test_dinh_dang_sai_thi_danh_dau(self):
        v = parse_verdict("có lẽ là tuỳ")
        self.assertTrue(v["malformed"])
        self.assertEqual(v["confidence"], 0.0)

    def test_khong_doan_ho_khi_thieu_conf(self):
        v = parse_verdict("INJECTION\nkhông có số")
        self.assertTrue(v["detected"])
        self.assertEqual(v["confidence"], 0.5)


class TestSaiSo(unittest.TestCase):
    def test_cong_thuc(self):
        c = Confusion(tp=8, fp=2, fn=2, tn=8)
        self.assertAlmostEqual(c.recall, 0.8)
        self.assertAlmostEqual(c.precision, 0.8)
        self.assertAlmostEqual(c.f1, 0.8)

    def test_chia_khong_thi_tra_none(self):
        c = Confusion(tn=5)
        self.assertIsNone(c.recall)
        self.assertIsNone(c.precision)
        self.assertIsNone(c.f1)

    def test_chi_phi_moi_tac_vu(self):
        c = Confusion(tp=1, tn=1, cost_usd=0.02)
        self.assertAlmostEqual(c.as_dict()["cost_per_task"], 0.01)


class TestKhongRoNhan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_prompt_khong_chua_nhan(self):
        """Prompt gửi model chỉ có nội dung — KHÔNG có truth."""
        SEEN.clear()
        compare(TASKS, provider_name="anthropic", model="sonnet-5.5",
                base_url=self.base, api_key="k", limit=6)
        self.assertTrue(SEEN, "phải có request gửi đi")
        for req in SEEN:
            blob = json.dumps(req, ensure_ascii=False)
            self.assertNotIn("injection_present", blob)
            self.assertNotIn("truth", blob)
            self.assertNotIn("label_missed", blob)

    def test_moi_request_mot_tac_vu(self):
        SEEN.clear()
        compare(TASKS, provider_name="anthropic", model="sonnet-5.5",
                base_url=self.base, api_key="k", limit=5)
        self.assertEqual(len(SEEN), 5)


class TestSoSanh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _rep(self, n=40):
        return compare(TASKS, provider_name="anthropic", model="sonnet-5.5",
                       base_url=self.base, api_key="k", limit=n)

    def test_do_ca_hai_bo_do(self):
        r = self._rep()
        self.assertEqual(r["keyword"]["n"], 40)
        self.assertEqual(r["llm"]["n"], 40)

    def test_co_chi_phi_model(self):
        r = self._rep(10)
        self.assertGreater(r["llm_total_cost_usd"], 0)
        self.assertGreater(r["llm_cost_per_1k_tasks"], 0)

    def test_tu_khoa_mien_phi(self):
        r = self._rep(10)
        self.assertEqual(r["keyword"]["cost_usd"], 0.0)

    def test_co_ca_lop_lech(self):
        r = self._rep(60)
        self.assertIsNotNone(r["agreement"])
        self.assertGreater(len(r["disagreements"]), 0,
                           "phải có ca lệch — nếu không thì so sánh vô nghĩa")

    def test_bao_cao_co_bang(self):
        md = detect.render(self._rep(20))
        self.assertIn("dò từ khoá", md)
        self.assertIn("model đọc", md)
        self.assertIn("recall", md)

    def test_khong_key_thi_chi_do_tu_khoa(self):
        r = compare(TASKS, provider_name="anthropic", api_key="", limit=10)
        self.assertIsNone(r["llm"])
        self.assertEqual(r["keyword"]["n"], 10)
        md = detect.render(r)
        self.assertIn("Chưa có model", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
