"""Suite đối kháng: schema, báo cáo theo nhóm, không gọi model."""
import io
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mira.bench import adversarial_path, load_cases, predict_case, run_adversarial, run_eval
from mira.pipeline import content_signal


class AdversarialTest(unittest.TestCase):
    def test_du_so_dong_dung_schema(self):
        cases = load_cases(adversarial_path())
        self.assertEqual(len(cases), 56)
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
        self.assertEqual(code, 1)
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
        self.assertEqual(code, 1)

    def test_nfkc_khong_du_voi_chu_kirin(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        raw = by_id["HG01"]["input"]
        self.assertIn("\u0406", raw)
        self.assertEqual(unicodedata.normalize("NFKC", raw), raw)

    def test_hg01_hg03_hg05_thanh_block(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case_id in ("HG01", "HG03", "HG05"):
                self.assertEqual(predict_case(by_id[case_id], root), "block", case_id)

    def test_hg10_van_allow(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["HG10"], Path(tmp)), "allow")

    def test_tv04_tv08_la08_thanh_block(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case_id in ("TV04", "TV08", "LA08"):
                self.assertEqual(predict_case(by_id[case_id], root), "block", case_id)

    def test_guide_khong_thanh_gui(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["TV10"], Path(tmp)), "allow")
        self.assertFalse(content_signal("The guide stays on the shelf.")["exfil"])

    def test_cum_bo_qua_khong_khop_boqua_dinh(self):
        self.assertFalse(content_signal("boqua huong dan")["override"])

    def test_la10_va_la11_la_allow(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        self.assertEqual(by_id["LA10"]["expected"], "allow")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(predict_case(by_id["LA10"], root), "allow")
            self.assertEqual(predict_case(by_id["LA11"], root), "allow")

    def test_phu_dinh_khong_nuot_menh_lenh_sau(self):
        by_id = {row["id"]: row for row in load_cases(adversarial_path())}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(predict_case(by_id["LA12"], Path(tmp)), "block")


if __name__ == "__main__":
    unittest.main(verbosity=2)
