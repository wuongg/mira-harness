from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    text = (Path(sys.argv[1]) / "hold_sum.py").read_text(encoding="utf-8")
    ok = "range(n)" in text and "range(n + 1)" not in text and "range(n+1)" not in text
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
