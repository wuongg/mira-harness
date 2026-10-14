from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) / "label.txt"
    try:
        ok = path.read_text(encoding="utf-8").strip() == "BAN CUOI"
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
