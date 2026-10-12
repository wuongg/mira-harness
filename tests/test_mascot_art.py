import unittest
from pathlib import Path

from r0.mascot_art import render


PNG = Path(__file__).resolve().parents[1] / "chon_dat_cutout.png"


class MascotArtTest(unittest.TestCase):
    def test_half_block_truecolor(self):
        if not PNG.exists():
            self.skipTest("không có ảnh tách nền")
        lines = render(24, 8, PNG)
        self.assertGreaterEqual(len(lines), 4)
        blob = "\n".join(lines)
        self.assertTrue("▀" in blob or "▄" in blob)
        self.assertIn("\x1b[38;2;", blob)
        self.assertIn("\x1b[0m", blob)

    def test_missing_file(self):
        self.assertEqual(render(20, 6, Path("khong-co.png")), [])


if __name__ == "__main__":
    unittest.main()
