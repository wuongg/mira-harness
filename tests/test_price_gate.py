"""Model không có giá thì không được gọi. Giá khai trên lệnh thì dùng đúng số đó."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import team  # noqa: E402

HITS = {"n": 0}


class _Prov:
    name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str):
        HITS["n"] += 1
        return "KẾT QUẢ", {"in": 1_000_000, "out": 0}


class PriceGateTest(unittest.TestCase):
    def setUp(self):
        HITS["n"] = 0

    def test_model_la_bi_chan_truoc_http(self):
        plan = team.build_plan("soạn báo cáo", surface="read_only", labels=["public"])
        with patch("frog.team.provider_for", lambda *a, **k: _Prov()):
            res = team.execute_plan(plan, model_override="khong-co", provider_name="anthropic",
                                    api_key="k", on_step=lambda m: None)
        self.assertEqual(HITS["n"], 0)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("chưa có giá", res["fail_reason"] or "")

    def test_khai_gia_thi_nhan_dung_va_dung_tran(self):
        plan = team.build_plan("soạn báo cáo", surface="read_only", labels=["public"])
        plan.declared_price = (2.0, 2.0)
        plan.cap_usd = 1.0
        with patch("frog.team.provider_for", lambda *a, **k: _Prov()):
            res = team.execute_plan(plan, model_override="khong-co", provider_name="anthropic",
                                    api_key="k", on_step=lambda m: None)
        self.assertEqual(res["ledger"]["total_usd"], 2.0)
        self.assertTrue(res["ledger"]["declared_by_user"])
        self.assertEqual(res["status"], "stopped_budget")

    def test_dry_run_van_dem_token_khong_can_gia(self):
        plan = team.build_plan("soạn báo cáo", surface="read_only", labels=["public"])
        res = team.execute_plan(plan, model_override="khong-co", dry_run=True,
                                on_step=lambda m: None)
        self.assertNotEqual(res["status"], "blocked")
        self.assertEqual(res["ledger"]["tokens_in"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
