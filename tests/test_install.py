import os
import tempfile
import unittest
from pathlib import Path

from frog.install_path import install, render_shim


class InstallShimTest(unittest.TestCase):
    def test_shim_goi_module_khong_tao_exe(self):
        root = Path(r"C:\src\frog install")
        text = render_shim(root)
        self.assertIn("python -m frog", text)
        self.assertIn("frog install", text)
        self.assertNotIn("frog.exe", text)

    def test_install_ghi_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            info = install(root=Path(r"C:\src\frog"), dest_dir=Path(d), update_path=False)
            self.assertTrue(info["shim"].is_file())
            name = info["shim"].name
            self.assertIn(name, ("frog.cmd", "frog"))
            self.assertNotIn(".exe", name)
            body = info["shim"].read_bytes()
            self.assertIn(b"python -m frog", body)
            if os.name == "nt":
                self.assertIn(b"\r\n", body)


if __name__ == "__main__":
    unittest.main()
