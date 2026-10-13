import os
import tempfile
import unittest

import mira.native as N
from mira.agent import run_turn
from mira.tools import AGENT_SYSTEM, Session


class CasualChatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "x"
        self._conv = N.converse

    def tearDown(self):
        self.tmp.cleanup()
        N.converse = self._conv
        if self._env is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._env

    def test_greeting_needs_no_tool_native(self):
        N.converse = lambda *a, **k: (
            [{"type": "text", "text": "Chào anh! Mình là Mira."}], {"in": 9, "out": 6})
        r = run_turn(task="hello", session=Session(root=self.tmp.name),
                     model="sonnet-5.5", protocol="native")
        self.assertEqual(r["status"], "ok")
        self.assertIn("Mira", r["final"])
        self.assertEqual(r["toolSummary"]["calls"], 0)

    def test_greeting_needs_no_tool_text(self):
        from mira import providers as P
        orig = P.AnthropicProvider.call
        P.AnthropicProvider.call = lambda self, system, user: (
            "Chào bạn, mình giúp gì được?", {"in": 9, "out": 6})
        try:
            r = run_turn(task="hi", session=Session(root=self.tmp.name),
                         model="sonnet-5.5", protocol="text", no_stream=True)
        finally:
            P.AnthropicProvider.call = orig
        self.assertEqual(r["status"], "ok")
        self.assertIn("giúp gì", r["final"])
        self.assertEqual(r["toolSummary"]["calls"], 0)

    def test_text_protocol_accepts_new_tools(self):
        from mira.agent import TOOL_NAMES
        for t in ("edit_file", "multi_edit", "glob", "web_search", "task"):
            self.assertIn(t, TOOL_NAMES)

    def test_system_prompt_allows_chat(self):
        self.assertIn("TRÒ CHUYỆN THƯỜNG", AGENT_SYSTEM)
        self.assertIn("KHÔNG cần gọi công cụ", AGENT_SYSTEM)


if __name__ == "__main__":
    unittest.main()
