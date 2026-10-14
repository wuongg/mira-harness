from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) / "merged.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        ok = rows == [
            {"id": "a", "city": "Hue", "score": 3},
            {"id": "b", "city": "Ha Noi", "score": 5},
        ]
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
