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
    "/model": ["anthropic/claude-sonnet-4.5", "sonnet-5.5", "opus-5.5", "haiku-5.5", "gpt-6-astra", "gpt-6-luna",
               "gpt-5.6-sol", "grok-4.7"],
    "/team": ["on", "off"],
    "/keys": ["status", "set", "clear", "path", "openrouter", "anthropic", "openai", "xai",
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


def apply_console_key(buf: str, cycle: int, history: list[str], hist_i: int,
                      vk: int, ch: str) -> tuple[str, int, int, str]:
    """Một phím console. 'à' (U+00E0) là chữ, không phải phím mũi tên."""
    if ch == "\x03":
        return buf, cycle, hist_i, "interrupt"
    if ch in ("\r", "\n") or vk == 0x0D:
        return buf, cycle, hist_i, "submit"
    if ch == "\x04":
        return buf, cycle, hist_i, "eof"
    if ch in ("\x08", "\x7f") or vk == 0x08:
        return buf[:-1], 0, hist_i, "redraw"
    if ch == "\t" or vk == 0x09:
        new, n = accept(buf, cycle)
        cycle = cycle + 1 if n > 1 and new.endswith(" ") else 0
        return new, cycle, hist_i, "redraw"
    if vk == 0x26 and history and not (ch and ch.isprintable()):
        hist_i = max(0, hist_i - 1)
        return history[hist_i], 0, hist_i, "redraw"
    if vk == 0x28 and history and not (ch and ch.isprintable()):
        hist_i = min(len(history), hist_i + 1)
        text = history[hist_i] if hist_i < len(history) else ""
        return text, 0, hist_i, "redraw"
    if vk == 0x27 and not (ch and ch.isprintable()):
        new, _ = accept(buf, cycle)
        return new, 0, hist_i, "redraw"
    if ch and ch.isprintable():
        return buf + ch, 0, hist_i, "redraw"
    return buf, cycle, hist_i, "redraw"


def _visible_len(prompt: str, buf: str, gh: str) -> int:
    import re
    strip = lambda s: re.sub(r"\x1b\[[0-9;]*m", "", s)   # noqa: E731
    return len(strip(prompt)) + len(buf) + len(gh)


def rewind_prefix(typed: int, width: int) -> str:
    """Từ chỗ con trỏ, ngay sau phần đã gõ, về đầu dòng prompt."""
    width = width if width > 0 else 1
    row = typed // width
    if row <= 0:
        return "\r"
    return f"\x1b[{row}A\r"


def place_after_typed(typed: int, total: int, width: int) -> str:
    """Sau khi in hết `total` cột, đặt con trỏ ngay sau `typed` cột."""
    width = width if width > 0 else 1
    end_row, _end_col = divmod(total, width)
    row, col = divmod(typed, width)
    out = f"\x1b[{end_row - row}A" if end_row > row else ""
    out += "\r"
    if col:
        out += f"\x1b[{col}C"
    return out


def _draw(prompt: str, buf: str, gh: str, drawn: list, dim: str, reset: str) -> None:
    """Vẽ lại cả đoạn đã xuống hàng. Con trỏ đặt ngay sau phần gõ."""
    from . import ui
    width = max(1, ui.term_width())
    typed = _visible_len(prompt, buf, "")
    sys.stdout.write(rewind_prefix(drawn[0], width))
    sys.stdout.write("\x1b[J")
    tail = (dim + gh + reset) if gh else ""
    sys.stdout.write(prompt + buf + tail)
    if gh:
        sys.stdout.write(place_after_typed(typed, typed + len(gh), width))
    sys.stdout.flush()
    drawn[0] = typed


def _finish_line() -> None:
    sys.stdout.write("\x1b[J\n")
    sys.stdout.flush()


def _console_keys():
    """Đọc phím Unicode. Trả (mã phím ảo, ký tự)."""
    import ctypes
    from ctypes import wintypes

    class _Char(ctypes.Union):
        _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char)]

    class _Key(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", _Char),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class _Event(ctypes.Union):
        _fields_ = [("KeyEvent", _Key), ("_pad", ctypes.c_char * 32)]

    class _Record(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _Event)]

    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReadConsoleInputW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_Record), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.ReadConsoleInputW.restype = wintypes.BOOL
    handle = kernel.GetStdHandle(-10)
    mode = wintypes.DWORD()
    kernel.GetConsoleMode(handle, ctypes.byref(mode))
    kernel.SetConsoleMode(handle, mode.value & ~0x0006)
    try:
        while True:
            rec = _Record()
            got = wintypes.DWORD()
            if not kernel.ReadConsoleInputW(handle, ctypes.byref(rec), 1, ctypes.byref(got)):
                break
            if rec.EventType != 1 or not rec.Event.KeyEvent.bKeyDown:
                continue
            ch = rec.Event.KeyEvent.uChar.UnicodeChar or ""
            yield rec.Event.KeyEvent.wVirtualKeyCode, ch
    finally:
        kernel.SetConsoleMode(handle, mode.value)


def _console_pending() -> int:
    """Số phím còn trong hàng đợi. Dán nhiều dòng thì Enter là xuống dòng, chưa gửi."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetNumberOfConsoleInputEvents.restype = wintypes.BOOL
    waiting = wintypes.DWORD()
    handle = kernel.GetStdHandle(-10)
    if not kernel.GetNumberOfConsoleInputEvents(handle, ctypes.byref(waiting)):
        return 0
    return int(waiting.value)


def _read_windows(prompt: str, history: list[str]) -> str:
    from . import ui

    dim, reset = ("\x1b[2m", "\x1b[0m") if ui.use_color() else ("", "")
    buf, hist_i, cycle = "", len(history), 0
    drawn = [0]
    _draw(prompt, buf, ghost(buf), drawn, dim, reset)
    for vk, ch in _console_keys():
        buf, cycle, hist_i, action = apply_console_key(buf, cycle, history, hist_i, vk, ch)
        if action == "submit":
            if _console_pending():
                buf += "\n"
            else:
                _finish_line()
                return buf
        elif action == "interrupt":
            _finish_line()
            raise KeyboardInterrupt
        if action == "eof":
            if not buf:
                raise EOFError
            continue
        _draw(prompt, buf, ghost(buf, cycle), drawn, dim, reset)
    raise EOFError


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
                _finish_line()
                return buf
            if c == "\x03":
                _finish_line()
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
