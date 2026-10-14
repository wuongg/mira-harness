from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1])
    try:
        spec = importlib.util.spec_from_file_location("value_mod", root / "names.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ok = mod.get_name({"name": "An"}) == "An"
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
