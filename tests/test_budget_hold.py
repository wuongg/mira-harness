"""Giữ chỗ trước khi gọi. Hai luồng không cùng vượt trần."""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from mira import team
from mira.providers import ProviderError
from mira.team import TeamPlan, execute_plan, make_task


class _Slow:
    calls = 0
    lock = threading.Lock()
    fail = False

    def __init__(self, *_a, **_k):
        self.name = "fake"
        self.attempts = 1

    def available(self):
        return True

    def call(self, _system, _user):
        if _Slow.fail:
            raise ProviderError("máy giả trả lỗi sau khi gửi")
        with _Slow.lock:
            _Slow.calls += 1
        time.sleep(0.2)
        return "xong", {"in": 1, "out": 1}


def _plan():
    plan = TeamPlan(
        task_text="làm việc X", lane=2, floor=2, floor_reason="thu",
        capability="write_external", gate_tier=3, gate_minutes=25.0,
        dual_approval=True, roles=["worker"], roles_reason="thu",
        task=make_task("làm việc X", surface="write_external"), cap_usd=1.5)
    plan.declared_price = (0.0, 1_000_000.0)
    return plan


class BudgetHoldTest(unittest.TestCase):
    def setUp(self):
        _Slow.calls = 0
        _Slow.fail = False

    def test_luong_thu_hai_khong_goi_khi_het_cho(self):
        with patch.object(team, "provider_for", lambda model, name=None, **kw: _Slow()):
            res = execute_plan(_plan(), workers=2, max_tokens=1, api_key="k")
        self.assertEqual(_Slow.calls, 1)
        self.assertEqual(res["status"], "stopped_budget")
        self.assertEqual(res["ledger"]["reserved"], 0.0)
        self.assertLessEqual(res["ledger"]["total_usd"], 1.5)

    def test_loi_sau_khi_gui_khong_coi_la_mien_phi(self):
        _Slow.fail = True
        with patch.object(team, "provider_for", lambda model, name=None, **kw: _Slow()):
            res = execute_plan(_plan(), workers=1, max_tokens=1, api_key="k")
        self.assertEqual(res["ledger"]["total_usd"], 0.0)
        self.assertGreater(res["ledger"]["uncertain_usd"], 0.0)
        self.assertEqual(res["ledger"]["reserved"], 0.0)
        self.assertTrue(res["steps"][0].get("uncertain"))
        self.assertEqual(res["ledger"]["uncertain"][0]["reason"],
                         "request có thể đã được xử lý")


if __name__ == "__main__":
    unittest.main(verbosity=2)
