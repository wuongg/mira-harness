from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) / "people.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        ok = rows == [{"id": "1", "name": "An"}, {"id": "2", "name": "Bo"}]
    except Exception:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
