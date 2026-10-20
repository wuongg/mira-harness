"""Failover model/provider và vai ngoài danh mục."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frog import failover  # noqa: E402
from frog.providers import ProviderError  # noqa: E402
from frog.roles import EXTRA_CAP, settle, spec_of, validate_settled  # noqa: E402
from frog.team import build_plan, execute_plan  # noqa: E402


ORDER = "trang web giới thiệu frog cần SEO để bạn bè tìm ra"


class FailoverDetectTest(unittest.TestCase):
    def test_loi_dang_failover(self):
        self.assertTrue(failover.is_failoverable("HTTP 429 — rate limit"))
        self.assertTrue(failover.is_failoverable("Cursor AgentService returned an empty turn"))
        self.assertTrue(failover.is_failoverable("can only afford 12 tokens"))
        self.assertFalse(failover.is_failoverable("schema brief hỏng"))

    def test_chuoi_uu_tien_cung_nha_roi_nha_khac(self):
        with patch("frog.keys.resolve", side_effect=lambda n: ("k", "env") if n in (
                "9router", "openai") else (None, None)):
            chain = failover.failover_chain("cu/gpt-5.6-sol-high", "9router", role="qa_reviewer")
        self.assertEqual(chain[0], ("9router", "cu/gpt-5.6-sol-high"))
        providers = [p for p, _ in chain]
        self.assertIn("9router", providers)
        # còn khóa openai thì chuỗi có thể nhảy sang openai sau khi hết slot 9router
        self.assertTrue(any(p == "openai" for p, _ in chain) or len(chain) >= 2)


class SpawnRoleTest(unittest.TestCase):
    def test_intake_sinh_vai_ngoai_danh_muc(self):
        proposal = {
            "size": "nho", "web": True,
            "backend": {"needed": False, "reason": "tĩnh", "roles": []},
            "hired": [
                {"role": "product_manager", "task": "phạm vi", "reason": "pm"},
                {"role": "frontend_engineer", "task": "html", "reason": "fe"},
                {"role": "qa_reviewer", "task": "kiểm", "reason": "qa"},
                {"role": "seo_copywriter", "kind": "make", "title": "SEO copywriter",
                 "task": "viết meta và tiêu đề tìm kiếm", "reason": "đơn cần SEO"},
            ],
            "considered": [],
        }
        st = settle(ORDER, proposal)
        names = [r["role"] for r in st["hired"]]
        self.assertIn("seo_copywriter", names)
        row = next(r for r in st["hired"] if r["role"] == "seo_copywriter")
        self.assertEqual(row["origin_kind"], "extra")
        self.assertEqual(row["kind"], "make")
        self.assertEqual(row["origin"], "intake")
        spec = spec_of(st, "seo_copywriter")
        self.assertIsNotNone(spec)
        self.assertIn("SEO", spec.system_prompt)
        self.assertEqual(validate_settled(st), [])

    def test_cat_qua_tran_extra(self):
        extras = [{"role": f"extra_role_{i}", "kind": "make", "title": f"E{i}",
                   "task": f"việc {i}", "reason": "test"} for i in range(EXTRA_CAP + 2)]
        proposal = {
            "size": "nho", "web": True,
            "backend": {"needed": False, "reason": "tĩnh", "roles": []},
            "hired": [
                {"role": "product_manager", "task": "p", "reason": "r"},
                {"role": "frontend_engineer", "task": "f", "reason": "r"},
                {"role": "qa_reviewer", "task": "q", "reason": "r"},
                *extras,
            ],
            "considered": [],
        }
        st = settle(ORDER, proposal)
        n_extra = sum(1 for r in st["hired"] if r.get("origin_kind") == "extra")
        self.assertEqual(n_extra, EXTRA_CAP)
        self.assertTrue(any("quá" in n for n in st["notes"]))


class FailoverRunTest(unittest.TestCase):
    def test_doi_model_khi_lan_dau_chet(self):
        calls = []

        class BoomThenOk:
            name = "9router"
            billing = "subscription"
            attempts = 1
            max_tokens = 64

            def __init__(self, model, **kw):
                self.model = model

            def available(self):
                return True

            def call(self, system, user):
                calls.append(self.model)
                if self.model == "cu/bad":
                    raise ProviderError("Cursor AgentService returned an empty turn")
                return f"ok:{self.model}", {"in": 1, "out": 1}

        def fake_provider(model, name=None, **kw):
            return BoomThenOk(model)

        plan = build_plan("ping ngắn")
        plan.roles = ["worker"]
        plan.staffing = None

        with patch("frog.team.provider_for", side_effect=fake_provider), \
             patch("frog.failover.failover_chain",
                   return_value=[("9router", "cu/bad"), ("9router", "cu/good")]):
            os.environ.pop("FROG_NO_FAILOVER", None)
            res = execute_plan(plan, provider_name="9router", model_override="cu/bad",
                               max_tokens=64, on_step=lambda m: None)
        self.assertEqual(calls, ["cu/bad", "cu/good"], res)
        worker = next(s for s in res["steps"] if s.get("role") == "worker" and s.get("text"))
        self.assertIn("ok:cu/good", worker["text"])
        self.assertTrue(worker.get("failover_from"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
