"""Kiểm tiêu đề commit trong một range. Chỉ thư viện chuẩn."""
from __future__ import annotations

import re
import subprocess
import sys

SUBJECT = re.compile(r"^\[[A-Z0-9-]+\] \S")
HIDDEN = (0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060)


def _out(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def check_range(spec: str) -> int:
    proc = subprocess.run(
        ["git", "log", "--format=%s%x00%H", spec],
        capture_output=True, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        if err:
            _out(err)
        return 1
    raw = proc.stdout.decode("utf-8")
    if not raw.strip():
        return 0
    failed = 0
    for line in raw.splitlines():
        if "\0" not in line:
            continue
        subject, sha = line.split("\0", 1)
        reasons: list[str] = []
        if not SUBJECT.match(subject):
            reasons.append("thieu ID")
        if len(subject) > 72:
            reasons.append("dai hon 72")
        seen: set[int] = set()
        for ch in subject:
            code = ord(ch)
            if code in HIDDEN and code not in seen:
                seen.add(code)
                reasons.append(f"ky tu an U+{code:04X}")
        if reasons:
            failed = 1
            _out(f"{sha[:7]} " + "; ".join(reasons))
    return failed


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1 or ".." not in argv[0]:
        _out("thieu range A..B")
        return 1
    return check_range(argv[0])


if __name__ == "__main__":
    raise SystemExit(main())
