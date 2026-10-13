"""Đọc log unittest và in một annotation cho mỗi test đỏ.

Không gọi mạng. Dòng tiếng Việt trong thông báo lỗi được viết dạng ASCII
để bước này không chết trên console cp1252 trước khi annotation kịp ra.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _clip(block: str) -> str:
    lines = []
    for line in block.splitlines()[:30]:
        lines.append(line[:500])
    return "\n".join(lines)


def _escape(text: str) -> str:
    return (
        text.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _blocks(text: str) -> list[str]:
    lines = text.splitlines()
    found: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("FAIL:") or line.startswith("ERROR:"):
            chunk = [line]
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if nxt.startswith("FAIL:") or nxt.startswith("ERROR:"):
                    break
                if nxt.startswith("Ran ") or nxt.startswith("FAILED (") or nxt.startswith("OK"):
                    break
                if nxt.startswith("===="):
                    break
                chunk.append(nxt)
                if len(chunk) >= 30:
                    index += 1
                    break
                index += 1
            found.append("\n".join(chunk))
            continue
        index += 1
    if found:
        return found
    names = []
    for line in lines:
        if line.endswith(" FAIL") or line.endswith(" ERROR"):
            names.append(line)
    return names


def annotate(path: Path, code: int) -> int:
    """In annotation. Trả 0 khi discover xanh, mã discover khi có khối fail."""
    path = Path(path)
    if code == 0:
        return 0
    if not path.is_file():
        print("::error::khong co unittest.txt")
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = _blocks(text)
    if not blocks:
        print(f"::error::unittest thoat {code} nhung log khong co khoi fail")
        return 1
    for block in blocks:
        print("::error::" + _escape(_clip(block)))
    return code


def main(argv: list[str]) -> int:
    _utf8_stdout()
    if len(argv) != 3:
        print("::error::thieu doi so log va ma thoat")
        return 1
    try:
        code = int(argv[2])
    except ValueError:
        print("::error::ma thoat khong phai so")
        return 1
    return annotate(Path(argv[1]), code)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
