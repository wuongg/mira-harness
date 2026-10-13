"""Suite đối kháng: schema, báo cáo theo nhóm, không gọi model."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from mira.bench import adversarial_path, load_cases, run_adversarial, run_eval


class AdversarialTest(unittest.TestCase):
    def test_du_nam_muoi_dong_dung_schema(self):
        cases = load_cases(adversarial_path())
        self.assertEqual(len(cases), 50)
        axes = {row["axis"] for row in cases}
        self.assertEqual(axes, {"lenh_an", "gia_danh", "lo_key", "path_escape", "homoglyph", "tieng_viet"})
        for row in cases:
            self.assertIn(row["expected"], ("block", "allow"))
            self.assertTrue(row["input"])

    def test_suite_cu_khong_doi(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_eval()
        text = buf.getvalue()
        self.assertNotIn("lenh_an", text)
        self.assertIn("qua", text)
        self.assertIn(code, (0, 1))

    def test_bao_cao_co_sau_nhom(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_adversarial()
        text = buf.getvalue()
        self.assertEqual(code, 0)
        for slug in ("lenh_an", "gia_danh", "lo_key", "path_escape", "homoglyph", "tieng_viet"):
            self.assertIn(slug, text)
        self.assertIn("precision", text)
        self.assertIn("recall", text)
        self.assertIn("không phải shadow RNG", text)

    def test_khong_goi_model(self):
        def boom(*_a, **_k):
            raise AssertionError("không được dựng provider")

        with patch("mira.team.provider_for", boom), patch("mira.providers.provider_for", boom):
            code = run_adversarial()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
