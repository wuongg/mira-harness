"""Dòng nhập có GHOST TEXT inline + Tab điền — chỉ dùng thư viện chuẩn.

Kiểu fish/Claude Code: gợi ý hiện MỜ ngay sau con trỏ (không in danh sách riêng),
ấn Tab (hoặc →) là điền nốt. Nhiều khả năng thì Tab xoay vòng qua từng khả năng.

Vì sao tự viết: `readline` KHÔNG có trên Windows. Để chạy cả hai nơi mà không kéo
thư viện ngoài:
  * Windows -> `msvcrt` (có sẵn)
  * Unix    -> `termios`/`tty` (có sẵn), chế độ raw để vẽ lại từng phím
  * Không phải terminal -> `input()` để script không treo

Phần logic là hàm thuần — kiểm được không cần TTY.
"""
from __future__ import annotations

import sys

COMMANDS = [
    "/help", "/mode", "/model", "/team", "/tools", "/cost", "/audit",
    "/diff", "/undo", "/memory", "/compact", "/menu", "/keys",
    "/clear", "/save", "/sessions", "/resume", "/exit",
]

ARG_HINTS = {
    "/mode": ["plan", "default", "acceptEdits", "bypass"],
    "/model": ["sonnet-5.5", "opus-5.5", "haiku-5.5", "gpt-6-astra", "gpt-6-luna",
               "gpt-5.6-sol", "grok-4.7"],
    "/team": ["on", "off"],
    "/keys": ["status", "set", "clear", "path", "anthropic", "openai", "xai",
              "tavily", "brave", "serper"],
}


# ------------------------------------------------------------- hàm thuần
def common_prefix(items: list[str]) -> str:
    if not items:
        return ""
    s = items[0]
    for it in items[1:]:
        while s and not it.startswith(s):
            s = s[:-1]
    return s


def matches(line: str) -> list[str]:
    if not line.startswith("/"):
        return []
    parts = line.split(" ")
    if len(parts) == 1:
        return [c for c in COMMANDS if c.startswith(parts[0])]
    return [a for a in ARG_HINTS.get(parts[0], []) if a.startswith(parts[-1])]


def ghost(line: str, cycle: int = 0) -> str:
    """Phần còn thiếu để điền trọn khả năng tốt nhất — in mờ sau con trỏ."""
    ms = matches(line)
    if not ms:
        return ""
    typed = line.split(" ")[-1]
    if len(ms) == 1:
        cand = ms[0]
    else:
        cp = common_prefix(ms)
        cand = cp if len(cp) > len(typed) else ms[cycle % len(ms)]
    return cand[len(typed):]


def accept(line: str, cycle: int = 0) -> tuple[str, int]:
    """Tab: điền trọn khả năng đang gợi ý. Trả (dòng mới, tổng số khả năng)."""
    ms = matches(line)
    if not ms:
        return line, 0
    parts = line.split(" ")
    typed = parts[-1]
    if len(ms) == 1:
        parts[-1] = ms[0]
    else:
        cp = common_prefix(ms)
        if len(cp) > len(typed):
            parts[-1] = cp                      # mở rộng tới tiền tố chung
            return " ".join(parts), len(ms)
        parts[-1] = ms[cycle % len(ms)]
    return " ".join(parts) + " ", len(ms)


def apply_completion(line: str) -> tuple[str, list[str]]:
    """Giữ lại cho tương thích: điền rồi trả kèm danh sách khả năng."""
    new, _ = accept(line)
    return new, matches(line)


# ------------------------------------------------------------- đọc một dòng
def _fallback(prompt: str) -> str:
    return input(prompt)


def _visible_len(prompt: str, buf: str, gh: str) -> int:
    import re
    strip = lambda s: re.sub(r"\x1b\[[0-9;]*m", "", s)   # noqa: E731
    return len(strip(prompt)) + len(buf) + len(gh)


def _draw(prompt: str, buf: str, gh: str, drawn: list, dim: str, reset: str) -> None:
    """Vẽ lại dòng: prompt + phần gõ + ghost mờ; con trỏ đặt ngay sau phần gõ."""
    vis = _visible_len(prompt, buf, gh)
    pad = " " * max(0, drawn[0] - vis)
    tail = (dim + gh + reset) if gh else ""
    sys.stdout.write("\r" + prompt + buf + tail + pad)
    sys.stdout.write("\r" + prompt + buf)      # con trỏ về ngay sau phần gõ
    sys.stdout.flush()
    drawn[0] = vis


def _read_windows(prompt: str, history: list[str]) -> str:
    import msvcrt
    from . import ui

    dim, reset = ("\x1b[2m", "\x1b[0m") if ui.use_color() else ("", "")
    buf, hist_i, cycle = "", len(history), 0
    drawn = [0]
    _draw(prompt, buf, ghost(buf), drawn, dim, reset)
    while True:
        ch = msvcrt.getch()
        if ch in (b"\r", b"\n"):
            sys.stdout.write("\n")
            return buf
        if ch == b"\x03":
            sys.stdout.write("\n")
            raise KeyboardInterrupt
        if ch == b"\x04":
            if not buf:
                raise EOFError
            continue
        if ch in (b"\x08", b"\x7f"):
            buf, cycle = buf[:-1], 0
        elif ch == b"\t":
            new, n = accept(buf, cycle)
            cycle = cycle + 1 if n > 1 and new.endswith(" ") else 0
            buf = new
        elif ch in (b"\x00", b"\xe0"):
            k = msvcrt.getch()
            if k == b"H" and history:
                hist_i = max(0, hist_i - 1)
                buf, cycle = history[hist_i], 0
            elif k == b"P" and history:
                hist_i = min(len(history), hist_i + 1)
                buf, cycle = (history[hist_i] if hist_i < len(history) else ""), 0
            elif k == b"M":                      # → : nhận gợi ý
                buf, _ = accept(buf, cycle)
                cycle = 0
        else:
            try:
                buf += ch.decode("utf-8", "ignore")
            except Exception:                    # noqa: BLE001
                pass
            cycle = 0
        _draw(prompt, buf, ghost(buf, cycle), drawn, dim, reset)


def _read_posix(prompt: str, history: list[str]) -> str:
    import termios
    import tty
    from . import ui

    dim, reset = ("\x1b[2m", "\x1b[0m") if ui.use_color() else ("", "")
    buf, hist_i, cycle = "", len(history), 0
    drawn = [0]
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _draw(prompt, buf, ghost(buf), drawn, dim, reset)
        while True:
            c = sys.stdin.read(1)
            if c in ("\r", "\n"):
                sys.stdout.write("\n")
                return buf
            if c == "\x03":
                sys.stdout.write("\n")
                raise KeyboardInterrupt
            if c == "\x04":
                if not buf:
                    raise EOFError
                continue
            if c in ("\x7f", "\b"):
                buf, cycle = buf[:-1], 0
            elif c == "\t":
                new, n = accept(buf, cycle)
                cycle = cycle + 1 if n > 1 and new.endswith(" ") else 0
                buf = new
            elif c == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A" and history:
                    hist_i = max(0, hist_i - 1)
                    buf, cycle = history[hist_i], 0
                elif seq == "[B" and history:
                    hist_i = min(len(history), hist_i + 1)
                    buf, cycle = (history[hist_i] if hist_i < len(history) else ""), 0
                elif seq == "[C":
                    buf, _ = accept(buf, cycle)
                    cycle = 0
            else:
                buf += c
                cycle = 0
            _draw(prompt, buf, ghost(buf, cycle), drawn, dim, reset)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_line(prompt: str = "> ", history: list[str] | None = None,
              enable: bool = True) -> str:
    """Đọc một dòng: ghost text mờ + Tab/→ để điền (nếu là terminal thật)."""
    hist = history if history is not None else []
    if not enable:
        return _fallback(prompt)
    try:
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:                            # noqa: BLE001
        is_tty = False
    if not is_tty:
        return _fallback(prompt)
    try:
        if sys.platform.startswith("win"):
            return _read_windows(prompt, hist)
        return _read_posix(prompt, hist)
    except (ImportError, OSError, ValueError):
        return _fallback(prompt)
