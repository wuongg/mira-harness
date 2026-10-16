"""--yes và bypass chỉ được khi bề mặt nằm trong vùng đọc hoặc sandbox."""
from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from frog.agent import cmd_agent


def _ok(**kw):
    return {"status": "ok", "error": None, "final": "xong",
            "usage": {"in": 1, "out": 1}, "turns": 1,
            "toolSummary": {"calls": 0, "tools": []},
            "seconds": 0, "model": "sonnet-5.5", "provider": "anthropic",
            "costUsd": 0, "stopReason": "xong", "audit": [],
            "protocol": "text", "trace": [], "convo": []}


def _args(root: Path, **kw) -> Namespace:
    base = dict(cwd=str(root), mode="default", yes=False, model=None, provider=None,
                base_url=None, max_tokens=64, no_stream=True, protocol="text",
                max_turns=1, price_in=None, max_budget_usd=None, task="đọc ghi chú",
                json=True, session_id=None, surface="read_only", labels="internal")
    base.update(kw)
    return Namespace(**base)


class YesGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _go(self, **kw):
        calls = []

        def run_turn(**_k):
            calls.append(1)
            return _ok()

        with patch("frog.agent.run_turn", run_turn):
            code = cmd_agent(_args(self.root, **kw))
        return code, calls

    def test_yes_read_only_duoc(self):
        code, calls = self._go(yes=True)
        self.assertNotEqual(code, 7)
        self.assertEqual(calls, [1])

    def test_yes_write_sandbox_duoc(self):
        code, calls = self._go(yes=True, surface="write_sandbox")
        self.assertNotEqual(code, 7)
        self.assertEqual(calls, [1])

    def test_yes_egress_bi_chan(self):
        code, calls = self._go(yes=True, surface="egress_new")
        self.assertEqual(code, 7)
        self.assertEqual(calls, [])

    def test_yes_write_external_bi_chan(self):
        code, calls = self._go(yes=True, surface="write_external")
        self.assertEqual(code, 7)
        self.assertEqual(calls, [])

    def test_bypass_confidential_bi_chan(self):
        code, calls = self._go(mode="bypass", surface="write_sandbox", labels="confidential")
        self.assertEqual(code, 7)
        self.assertEqual(calls, [])

    def test_bypass_restricted_bi_chan(self):
        code, calls = self._go(mode="bypass", surface="write_sandbox", labels="restricted")
        self.assertEqual(code, 7)
        self.assertEqual(calls, [])

    def test_yes_internal_write_sandbox_van_duoc(self):
        code, calls = self._go(yes=True, surface="write_sandbox", labels="internal")
        self.assertNotEqual(code, 7)
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
