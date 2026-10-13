"""Kiểm bộ phân loại cắm được: keyword vs llm, cache, và ranh giới không rò nhãn."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mira.classifiers import KeywordClassifier, LLMClassifier, build_classifier  # noqa: E402
from mira.pipeline import t1b_classifier                                          # noqa: E402
from mira.tasks import PAYLOAD_SIGNATURES, build_tasks                             # noqa: E402

TASKS = build_tasks()
SEEN: list[dict] = []


class _Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append(req)
        hit = any(s in json.dumps(req, ensure_ascii=False) for s in PAYLOAD_SIGNATURES)
        body = ("INJECTION\nCONF: 0.91\ncó chỉ dẫn ngoài" if hit
                else "CLEAN\nCONF: 0.77\nchỉ dẫn hợp lệ")
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


class TestKeyword(unittest.TestCase):
    def test_giong_ham_goc(self):
        k = KeywordClassifier()
        t = TASKS[0]
        self.assertEqual(k.classify(t)["raised"], t1b_classifier(t)["raised"])

    def test_mien_phi(self):
        k = KeywordClassifier()
        for t in TASKS[:20]:
            k.classify(t)
        self.assertEqual(k.cost_usd, 0.0)
        self.assertEqual(k.calls, 20)


class TestLLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _mk(self, cache=None):
        from mira.detect import build_provider
        prov = build_provider("anthropic", "sonnet-5.5", self.base, "k")
        return LLMClassifier(prov, cache_dir=cache)

    def test_dang_ket_qua_tuong_thich(self):
        r = self._mk().classify(TASKS[0])
        for k in ("choice", "confidence", "raised", "evidence", "n_evidence", "model"):
            self.assertIn(k, r)

    def test_tinh_tien(self):
        c = self._mk()
        c.classify(TASKS[0])
        self.assertGreater(c.cost_usd, 0)
        self.assertTrue(c.summary()["priced"])

    def test_cache_khong_goi_lan_hai(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._mk(cache=d)
            t = TASKS[0]
            SEEN.clear()
            a = c.classify(t)
            n1 = len(SEEN)
            b = c.classify(t)
            self.assertEqual(len(SEEN), n1, "lần hai phải lấy từ cache, không gọi lại")
            self.assertEqual(a["raised"], b["raised"])
            self.assertTrue(b["cached"])
            self.assertEqual(c.cache_hits, 1)

    def test_cache_lam_chi_phi_dung_lai(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._mk(cache=d)
            c.classify(TASKS[0])
            cost1 = c.cost_usd
            c.classify(TASKS[0])
            self.assertEqual(c.cost_usd, cost1, "cache hit không được tính thêm tiền")

    def test_prompt_khong_chua_nhan(self):
        SEEN.clear()
        self._mk().classify(TASKS[0])
        blob = json.dumps(SEEN[0], ensure_ascii=False)
        for bad in ("injection_present", "truth", "label_missed"):
            self.assertNotIn(bad, blob)

    def test_loi_mang_thi_ghi_nhan_khong_vo(self):
        from mira.detect import build_provider
        prov = build_provider("anthropic", "sonnet-5.5", "http://127.0.0.1:1", "k")
        c = LLMClassifier(prov)
        r = c.classify(TASKS[0])
        self.assertFalse(r["raised"], "lỗi thì KHÔNG được nâng mức")
        self.assertEqual(c.errors, 1)


class TestBuildClassifier(unittest.TestCase):
    def test_mac_dinh_la_keyword(self):
        c, err = build_classifier("keyword")
        self.assertIsNone(err)
        self.assertEqual(c.name, "keyword")

    def test_thieu_key_thi_bao_loi_chu_khong_ha_ve_keyword(self):
        c, err = build_classifier("llm", provider_name="anthropic", api_key="")
        self.assertIsNone(c, "KHÔNG được âm thầm hạ về keyword")
        self.assertIn("API key", err)

    def test_ten_sai_thi_bao_loi(self):
        c, err = build_classifier("gpt5")
        self.assertIsNone(c)
        self.assertIn("không biết", err)

    def test_co_key_thi_dung_duoc(self):
        c, err = build_classifier("llm", provider_name="anthropic", model="sonnet-5.5",
                                  api_key="k")
        self.assertIsNone(err)
        self.assertEqual(c.name, "llm")


class TestChayVaoDuongOng(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = _serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_shadowrun_dung_classifier_cam_duoc(self):
        import random
        from mira.pipeline import ShadowRun
        from mira.detect import build_provider
        prov = build_provider("anthropic", "sonnet-5.5", self.base, "k")
        clf = LLMClassifier(prov)
        run = ShadowRun(tasks=TASKS[:25], rng=random.Random(1), classifier=clf)
        trace = run.run()
        self.assertEqual(len(trace), 25)
        self.assertTrue(all(r["classifier"]["decided_by"] == "llm-read" for r in trace))
        self.assertGreater(clf.cost_usd, 0)

    def test_shadowrun_mac_dinh_van_la_tu_khoa(self):
        import random
        from mira.pipeline import ShadowRun
        run = ShadowRun(tasks=TASKS[:10], rng=random.Random(1))
        trace = run.run()
        self.assertTrue(all(r["classifier"]["decided_by"] == "content-scan" for r in trace))


if __name__ == "__main__":
    unittest.main(verbosity=2)
