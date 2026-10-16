"""Chuỗi giá: --price-in thắng file, file thắng env, không có thì chặn."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frog import config as C  # noqa: E402
from frog import team  # noqa: E402
from frog.prices import load_prices  # noqa: E402

HITS = {"n": 0}
_FIXTURE = """
# ghi chú
[models."sonnet-5.5"]
in = 3.0
out = 3.0
cache_write = 1.0
[models."broken"]
in = 1.0
"""


class _Prov:
    name = "anthropic"

    def available(self) -> bool:
        return True

    def call(self, system, user, **_k):
        HITS["n"] += 1
        return "KẾT QUẢ", {"in": 1_000_000, "out": 0}


def _run(model="sonnet-5.5", declared=None, cap=None):
    plan = team.build_plan("soạn báo cáo", surface="read_only", labels=["internal"])
    plan.declared_price = declared
    if cap is not None:
        plan.cap_usd = cap
    with patch("frog.team.provider_for", lambda *a, **k: _Prov()):
        return team.execute_plan(plan, model_override=model, on_step=lambda _m: None)


class PricesTest(unittest.TestCase):
    def setUp(self):
        HITS["n"] = 0

    def test_price_in_thang_file(self):
        table = {"sonnet-5.5": {"in": 3.0, "out": 3.0}}
        with patch.dict(C.PRICES, table, clear=True), \
             patch.dict(os.environ, {"MIRA_PRICE_SONNET_5_5": "9,9"}):
            res = _run(declared=(1.0, 1.0))
        self.assertEqual(res["ledger"]["total_usd"], 1.0)
        self.assertIn("cli", res["ledger"]["price_sources"])
        self.assertTrue(res["ledger"]["declared_by_user"])

    def test_file_thang_env(self):
        table = {"sonnet-5.5": {"in": 3.0, "out": 3.0}}
        with patch.dict(C.PRICES, table, clear=True), \
             patch.dict(os.environ, {"MIRA_PRICE_SONNET_5_5": "9,9"}):
            res = _run()
        self.assertEqual(res["ledger"]["total_usd"], 3.0)
        self.assertIn("file", res["ledger"]["price_sources"])
        self.assertFalse(res["ledger"]["declared_by_user"])

    def test_env_khi_khong_co_trong_file(self):
        with patch.dict(C.PRICES, {}, clear=True), \
             patch.dict(os.environ, {"MIRA_PRICE_SONNET_5_5": "4,4"}):
            res = _run()
        self.assertEqual(HITS["n"], 1)
        self.assertEqual(res["ledger"]["total_usd"], 4.0)
        self.assertIn("env", res["ledger"]["price_sources"])

    def test_khong_co_nguon_nao_thi_chan(self):
        env = os.environ.copy()
        env.pop("MIRA_PRICE_KHONG_CO", None)
        with patch.dict(C.PRICES, {}, clear=True), patch.dict(os.environ, env, clear=True):
            res = _run(model="khong-co")
        self.assertEqual(HITS["n"], 0)
        self.assertEqual(res["status"], "blocked")

    def test_gia_file_cham_tran_thi_dung(self):
        table = {"sonnet-5.5": {"in": 7.0, "out": 7.0}}
        env = os.environ.copy()
        env.pop("MIRA_PRICE_SONNET_5_5", None)
        with patch.dict(C.PRICES, table, clear=True), patch.dict(os.environ, env, clear=True):
            res = _run(cap=1.0)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertEqual(res["ledger"]["total_usd"], 7.0)
        self.assertNotEqual(res["ledger"]["total_usd"], C.UNKNOWN_PRICE["in"])

    def test_parser_mini_khop_tomllib(self):
        mini = load_prices(_FIXTURE, force_mini=True)
        self.assertEqual(mini["sonnet-5.5"]["in"], 3.0)
        self.assertNotIn("broken", mini)
        shipped = Path(__file__).resolve().parents[1] / "frog" / "prices.toml"
        text = shipped.read_text(encoding="utf-8")
        self.assertIn("sonnet-5.5", load_prices(text, force_mini=True))
        if sys.version_info >= (3, 11):
            self.assertEqual(load_prices(text, force_mini=True), load_prices(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
