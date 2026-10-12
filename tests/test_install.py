import os
import tempfile
import unittest
from pathlib import Path

from r0.install_path import install, render_shim


class InstallShimTest(unittest.TestCase):
    def test_shim_goi_module_khong_tao_exe(self):
        root = Path(r"C:\src\mira install")
        text = render_shim(root)
        self.assertIn("python -m r0", text)
        self.assertIn("mira install", text)
        self.assertNotIn("mira.exe", text)

    def test_install_ghi_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            info = install(root=Path(r"C:\src\mira"), dest_dir=Path(d), update_path=False)
            self.assertTrue(info["shim"].is_file())
            name = info["shim"].name
            self.assertIn(name, ("mira.cmd", "mira"))
            self.assertNotIn(".exe", name)
            body = info["shim"].read_bytes()
            self.assertIn(b"python -m r0", body)
            if os.name == "nt":
                self.assertIn(b"\r\n", body)


if __name__ == "__main__":
    unittest.main()
