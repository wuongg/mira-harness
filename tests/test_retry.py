"""Retry 429/5xx: không charge lần thất bại, không thử lại 4xx."""
from __future__ import annotations

import io
import json
import random
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from frog import team
from frog.providers import AnthropicProvider, ProviderError, retry_open
from frog.team import Ledger


def _body():
    payload = {"content": [{"type": "text", "text": "xong"}],
               "usage": {"input_tokens": 120, "output_tokens": 40}}

    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    return _Resp()


def _http(code: int, url: str = "http://127.0.0.1/v1/messages"):
    return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b"no"))


class RetryTest(unittest.TestCase):
    def _plan(self):
        return team.build_plan(
            "tóm tắt tài liệu công khai", surface="read_only",
            labels=["public"], records=10, dollars=0)

    def test_429_roi_200_chi_charge_mot_lan(self):
        seen = {"n": 0}

        def fake_open(_req, timeout=None):
            seen["n"] += 1
            if seen["n"] == 1:
                raise _http(429)
            return _body()

        charged = []
        real = Ledger.charge

        def wrapped(self, *a, **k):
            charged.append(1)
            return real(self, *a, **k)

        with patch("frog.providers.urllib.request.urlopen", fake_open), \
                patch("frog.providers.time.sleep", lambda _s: None), \
                patch.object(Ledger, "charge", wrapped):
            res = team.execute_plan(
                self._plan(), provider_name="anthropic",
                base_url="http://127.0.0.1", api_key="k", on_step=lambda _m: None)
        self.assertEqual(seen["n"], 2)
        self.assertEqual(res["steps"][0]["attempt"], 2)
        self.assertEqual(len(charged), 1)
        self.assertGreater(res["ledger"]["total_usd"], 0)

    def test_400_khong_thu_lai(self):
        seen = {"n": 0}

        def fake_open(_req, timeout=None):
            seen["n"] += 1
            raise _http(400)

        charged = []
        with patch("frog.providers.urllib.request.urlopen", fake_open), \
                patch.object(Ledger, "charge", lambda *a, **k: charged.append(1)):
            res = team.execute_plan(
                self._plan(), provider_name="anthropic",
                base_url="http://127.0.0.1", api_key="k", on_step=lambda _m: None)
        self.assertEqual(seen["n"], 1)
        self.assertEqual(charged, [])
        self.assertEqual(res["ledger"]["total_usd"], 0)
        self.assertIn("error", res["steps"][0])
        self.assertEqual(res["steps"][0]["attempt"], 1)

    def test_503_du_ba_lan_khong_charge(self):
        seen = {"n": 0}

        def fake_open(_req, timeout=None):
            seen["n"] += 1
            raise _http(503)

        p = AnthropicProvider(model="claude-x", api_key="k", base_url="http://127.0.0.1")
        with patch("frog.providers.urllib.request.urlopen", fake_open), \
                patch("frog.providers.time.sleep", lambda _s: None):
            with self.assertRaises(ProviderError):
                p.call("SYS", "USER")
        self.assertEqual(seen["n"], 3)
        self.assertEqual(p.attempts, 3)

        charged = []
        seen["n"] = 0
        with patch("frog.providers.urllib.request.urlopen", fake_open), \
                patch("frog.providers.time.sleep", lambda _s: None), \
                patch.object(Ledger, "charge", lambda *a, **k: charged.append(1)):
            res = team.execute_plan(
                self._plan(), provider_name="anthropic",
                base_url="http://127.0.0.1", api_key="k", on_step=lambda _m: None)
        self.assertEqual(seen["n"], 3)
        self.assertEqual(charged, [])
        self.assertEqual(res["steps"][0]["attempt"], 3)
        self.assertIn("error", res["steps"][0])
        self.assertEqual(res["ledger"]["total_usd"], 0)

    def test_sleep_dung_0_5_roi_1(self):
        slept = []

        def fake_open(_req, timeout=None):
            raise _http(503)

        req = urllib.request.Request("http://127.0.0.1/v1/messages", data=b"{}", method="POST")
        with patch("frog.providers.urllib.request.urlopen", fake_open):
            with self.assertRaises(ProviderError):
                retry_open(req, 1, name="anthropic", rng=random.Random(0), sleep=slept.append)
        self.assertEqual(len(slept), 2)
        self.assertGreaterEqual(slept[0], 0.5)
        self.assertLessEqual(slept[0], 0.75)
        self.assertGreaterEqual(slept[1], 1.0)
        self.assertLessEqual(slept[1], 1.25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
