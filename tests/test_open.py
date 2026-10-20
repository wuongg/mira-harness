import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import frog.cli as cli
import frog.repl as repl_mod


class OpenTest(unittest.TestCase):
    def setUp(self):
        self._resolve = cli.__dict__  # noqa
        import frog.keys as keys
        self.keys = keys
        self._orig_resolve = keys.resolve
        self._orig_repl = repl_mod.repl
        self._orig_setup = keys.prompt_setup
        self._orig_interactive = cli.interactive
        self.calls = []

    def tearDown(self):
        self.keys.resolve = self._orig_resolve
        repl_mod.repl = self._orig_repl
        self.keys.prompt_setup = self._orig_setup
        cli.interactive = self._orig_interactive

    def _set_keys(self, present):
        def resolve(p):
            return ("sk-x", "file") if p in present else (None, "")
        self.keys.resolve = resolve

    def test_opens_repl_when_key_present(self):
        self._set_keys({"anthropic"})
        repl_mod.repl = lambda a: self.calls.append(("repl", a.model)) or 0
        self.assertEqual(cli._open(), 0)
        self.assertEqual(self.calls[0][0], "repl")

    def test_first_run_prompts_then_opens(self):
        state = {"n": 0}

        def resolve(p):
            return ("sk-x", "file") if state["n"] > 0 else (None, "")

        self.keys.resolve = resolve
        self.keys.prompt_setup = lambda *a, **k: state.__setitem__("n", 1)
        repl_mod.repl = lambda a: self.calls.append("repl") or 0
        self.assertEqual(cli._open(), 0)
        self.assertIn("repl", self.calls)

    def test_first_run_no_key_falls_back_to_menu(self):
        self._set_keys(set())
        self.keys.prompt_setup = lambda *a, **k: 0
        cli.interactive = lambda: self.calls.append("menu") or 0
        self.assertEqual(cli._open(), 0)
        self.assertIn("menu", self.calls)

    def test_pick_model_by_provider(self):
        self._set_keys({"openrouter"})
        self.assertEqual(cli._pick_model(), "anthropic/claude-sonnet-4.5")
        self._set_keys({"openrouter", "anthropic"})
        from frog.providers import agent_binding
        model, prov = agent_binding("sonnet-5.5", None)
        self.assertEqual(prov, "openrouter")
        self.assertEqual(model, "anthropic/claude-sonnet-4.5")
        from frog.providers import OpenRouterProvider
        self.assertEqual(OpenRouterProvider("anthropic/claude-sonnet-4.5", api_key="k", max_tokens=4096).max_tokens, 512)
        self._set_keys({"openai"})
        self.assertEqual(cli._pick_model(), "gpt-5.6-sol")
        self._set_keys({"xai"})
        self.assertEqual(cli._pick_model(), "grok-4.7")
        self._set_keys({"anthropic"})
        self.assertEqual(cli._pick_model(), "sonnet-5.5")
        self._set_keys({"openrouter"})
        model, prov = agent_binding("sonnet-5.5", None, "http://localhost:20128")
        self.assertEqual(prov, "openrouter")
        self.assertEqual(model, "sonnet-5.5")
        from frog.providers import choose_proxy_model
        self.assertEqual(choose_proxy_model(["cu/claude-4.5-sonnet", "cu/default"]), "cu/default")
        from frog.team import model_for, slot_models
        routed = slot_models("9router")
        self.assertEqual(model_for("worker", None, role_models=routed), "cu/gpt-5.6-sol-high")
        self.assertEqual(model_for("verifier", None, role_models=routed),
                         "cu/claude-opus-5-thinking-high")
        self.assertIsNone(slot_models("anthropic"))
        from frog.providers import ProviderError, decode_completion
        body = 'data: {"error":{"message":"Cursor AgentService returned an empty turn","type":"api_error"}}\n\ndata: [DONE]\n\n'
        with self.assertRaises(ProviderError) as caught:
            decode_completion(body)
        self.assertIn("empty turn", str(caught.exception))
        done = decode_completion('data: {"choices":[{"delta":{"content":"chào"}}]}\n\ndata: [DONE]\n')
        self.assertEqual(done["choices"][0]["message"]["content"], "chào")

    def test_menu_subcommand_exists(self):
        p = cli.build_parser()
        a = p.parse_args(["menu"])
        self.assertTrue(callable(a.func))

    def test_menu_chi_nam_lenh_nguoi_dung(self):
        buf = io.StringIO()
        with patch("builtins.input", return_value="q"), redirect_stdout(buf):
            self.assertEqual(cli.interactive(), 0)
        text = buf.getvalue()
        for label in ("frog giao", "frog team", "frog agent", "frog keys", "frog doctor"):
            self.assertIn(label, text)
        self.assertNotIn("320", text)
        self.assertNotIn("phiếu", text)
        self.assertNotIn("shadow", text.lower())
        bench = cli.build_parser().parse_args(["bench"])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(bench.func(bench), 0)
        self.assertIn("công cụ benchmark nội bộ", out.getvalue())


if __name__ == "__main__":
    unittest.main()
