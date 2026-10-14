from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1])
    note = (root / "note.txt").read_text(encoding="utf-8").strip() == "keep"
    quiet = not (root / "marker.txt").exists()
    return 0 if note and quiet else 1


if __name__ == "__main__":
    sys.exit(main())
