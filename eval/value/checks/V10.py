from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) / "price.txt"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    return 1 if any(ch.isdigit() for ch in text) else 0


if __name__ == "__main__":
    sys.exit(main())
