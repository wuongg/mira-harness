from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) / "iso.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        ok = lines == ["2026-10-14", "2026-02-01"]
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
