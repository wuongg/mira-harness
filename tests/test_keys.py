import os
import tempfile
import unittest
from pathlib import Path

from frog import keys


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._p = keys.KEYS_PATH
        keys.KEYS_PATH = Path(self.tmp.name) / "keys.json"
        for v in keys.ENV.values():
            os.environ.pop(v, None)

    def tearDown(self):
        keys.KEYS_PATH = self._p
        self.tmp.cleanup()
        for v in keys.ENV.values():
            os.environ.pop(v, None)

    def test_roundtrip(self):
        keys.set_key("openai", "sk-abcdef123456")
        self.assertEqual(keys.get("openai"), "sk-abcdef123456")

    def test_mask(self):
        self.assertEqual(keys.mask("sk-abcdef123456"), "sk-abc…3456")
        self.assertEqual(keys.mask(None), "—")

    def test_env_wins_over_file(self):
        keys.set_key("openai", "from-file")
        os.environ["OPENAI_API_KEY"] = "from-env"
        self.assertEqual(keys.resolve("openai"), ("from-env", "env"))

    def test_file_fallback(self):
        keys.set_key("xai", "from-file")
        self.assertEqual(keys.resolve("xai"), ("from-file", "file"))

    def test_missing(self):
        self.assertEqual(keys.resolve("anthropic"), (None, ""))

    def test_clear(self):
        keys.set_key("xai", "x")
        keys.set_key("xai", "")
        self.assertIsNone(keys.get("xai"))

    def test_corrupt_file_is_ignored(self):
        keys.KEYS_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(keys.load(), {})

    def test_status_rows_shape(self):
        rows = keys.status_rows()
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(len(r) == 5 for r in rows))


if __name__ == "__main__":
    unittest.main()
