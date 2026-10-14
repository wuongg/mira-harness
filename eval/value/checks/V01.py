"""Phép kiểm độc lập. Không nằm trong thư mục worker."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load(root: Path, name: str):
    path = root / name
    spec = importlib.util.spec_from_file_location("value_mod", path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    root = Path(sys.argv[1])
    try:
        mod = _load(root, "sum_to.py")
        ok = mod.sum_to(0) == 0 and mod.sum_to(1) == 1 and mod.sum_to(3) == 6
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
