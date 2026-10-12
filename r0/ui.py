"""Trình bày trên terminal — không dùng thư viện ngoài.

Phong cách: tối giản kiểu terminal hiện đại — một điểm nhấn màu xanh, chữ xám cho
phần phụ, số căn phải. KHÔNG tự tô nền (tôn trọng terminal của bạn), chỉ tô chữ.

Tự tắt màu khi đầu ra bị chuyển hướng (pipe/ghi tệp) hoặc khi có NO_COLOR,
để `r0-shadow report > bao-cao.txt` vẫn ra văn bản sạch.

Đổi hệ màu: R0_THEME=light cho terminal nền sáng (mặc định: dark).
"""
from __future__ import annotations

import os
import shutil
import sys

# ---------------------------------------------------------------- hệ màu
# Chỉ dùng mã 256 màu. Một điểm nhấn duy nhất (xanh) + thang xám. Không tô nền.
_PALETTES = {
    "dark": {"accent": "38;5;39", "bright": "38;5;255", "text": "38;5;252",
             "dim": "38;5;245", "faint": "38;5;240", "ok": "38;5;42",
             "warn": "38;5;214", "bad": "38;5;203", "reset": "0", "bold": "1", "dimstyle": "2"},
    "light": {"accent": "38;5;25", "bright": "38;5;232", "text": "38;5;236",
              "dim": "38;5;243", "faint": "38;5;250", "ok": "38;5;28",
              "warn": "38;5;130", "bad": "38;5;124", "reset": "0", "bold": "1", "dimstyle": "2"},
}

# Bí danh tên cũ -> tên trong hệ màu, để mã cũ không vỡ.
_ALIAS = {"grey": "dim", "cyan": "accent", "blue": "accent", "green": "ok",
          "red": "bad", "yellow": "warn", "magenta": "accent"}


def _theme_name() -> str:
    t = (os.environ.get("R0_THEME") or "").strip().lower()
    if t in _PALETTES:
        return t
    # COLORFGBG="fg;bg": nền sáng khi bg >= 7
    cf = os.environ.get("COLORFGBG")
    if cf:
        try:
            if int(cf.split(";")[-1]) >= 7:
                return "light"
        except ValueError:
            pass
    return "dark"


_THEME = _theme_name()


def use_color(force: bool | None = None) -> bool:
    if force is not None:
        return force
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _prefer_utf8() -> None:
    """Windows console mặc định (cp1258) không in được tiếng Việt — chuyển UTF-8."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_prefer_utf8()
_COLOR = use_color()


def set_color(force: bool | None) -> None:
    global _COLOR
    _COLOR = use_color(force)


def c(text, *styles) -> str:
    """Tô chữ. `styles` nhận tên trong hệ màu hoặc tên cũ (grey/cyan/...)."""
    if not _COLOR or not styles:
        return str(text)
    pal = _PALETTES[_THEME]
    codes = []
    for s in styles:
        key = _ALIAS.get(s, s)
        if key in pal:
            codes.append(pal[key])
    if not codes:
        return str(text)
    return "\x1b[" + ";".join(codes) + "m" + str(text) + "\x1b[0m"


def term_width(default: int = 100) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def term_height(default: int = 24) -> int:
    try:
        return shutil.get_terminal_size((100, default)).lines
    except Exception:
        return default


# ---------------------------------------------------------------- khối cơ bản
def hr(ch: str = "─", n: int = 0, style: str = "faint") -> None:
    print(c(ch * (n or min(term_width(), 96)), style))


def title(text: str) -> None:
    print()
    print(c("  " + text, "bright", "bold"))


def section(text: str) -> None:
    """Tiêu đề mục — chữ thường, xám, có gạch mảnh bên dưới."""
    w = min(term_width(), 96)
    print()
    print(c("  " + text, "dim"))
    print(c("  " + "─" * min(w - 2, len(text) + 8), "faint"))


def kv(k: str, v, w: int = 26) -> None:
    print(f"  {c(k.ljust(w), 'dim')} {v}")


def note(text: str, kind: str = "info") -> None:
    """Một dòng trạng thái. Không dùng icon — chỉ chữ, màu nói mức độ."""
    label = {"info": "", "ok": "xong", "warn": "chú ý", "bad": "lỗi"}[kind]
    col = {"info": "dim", "ok": "ok", "warn": "warn", "bad": "bad"}[kind]
    if label:
        print(f"  {c(label, col)}  {text}")
    else:
        print(f"  {text}")


def table(headers, rows, align=None, indent: int = 2) -> None:
    align = align or ["l"] * len(headers)
    cells = [[str(x) for x in r] for r in rows]
    w = []
    for i, h in enumerate(headers):
        m = len(str(h))
        for r in cells:
            m = max(m, len(r[i]))
        w.append(m)
    pad = " " * indent

    def fmt(row, bold=False, style=None):
        out = []
        for i, x in enumerate(row):
            s = x.rjust(w[i]) if align[i] == "r" else x.ljust(w[i])
            out.append(c(s, "bright", "bold") if bold else (c(s, style) if style else s))
        return pad + "  ".join(out)

    print(c(fmt([str(h) for h in headers]), "accent", "bold"))
    print(c(pad + "  ".join("─" * x for x in w), "faint"))
    for r in cells:
        print(fmt(r))


def bar(v: float, vmax: float, n: int = 22, ch: str = "█") -> str:
    if vmax <= 0:
        return ""
    k = max(0, min(n, int(round(n * v / vmax))))
    return c(ch * k, "accent") + c("·" * (n - k), "faint")


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def money(x: float) -> str:
    return f"${x:,.4f}".replace(",", " ")


# ------------------------------------------------------- chữ khối (pixel font)
# Lưới 3×5. Dùng cho con số lớn ở màn thống kê.
_FONT = {
    "0": ["███", "█ █", "█ █", "█ █", "███"],
    "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "2": ["███", "  █", "███", "█  ", "███"],
    "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"],
    "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"],
    "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"],
    "9": ["███", "█ █", "███", "  █", "███"],
    ".": ["   ", "   ", "   ", "   ", " █ "],
    ",": ["   ", "   ", "   ", " █ ", "█  "],
    ":": ["   ", " █ ", "   ", " █ ", "   "],
    "-": ["   ", "   ", "███", "   ", "   "],
    "$": [" █ ", "███", "██ ", "███", " █ "],
    "%": ["█ █", "  █", " █ ", "█  ", "█ █"],
    "/": ["  █", "  █", " █ ", "█  ", "█  "],
    "+": ["   ", " █ ", "███", " █ ", "   "],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "M": ["█ █", "███", "█ █", "█ █", "█ █"],
    "K": ["█ █", "██ ", "███", "█ █", "█ █"],
    "B": ["██ ", "█ █", "██ ", "█ █", "██ "],
    "G": ["███", "█  ", "█ █", "█ █", "███"],
    "h": ["█  ", "███", "█ █", "█ █", "█ █"],
    "s": [" ██", "█  ", " █ ", "  █", "██ "],
    "x": ["   ", "█ █", " █ ", "█ █", "   "],
}


def big(text: str, style: str = "bright") -> list[str]:
    """Trả về các dòng chữ khối cho `text`. Ký tự lạ -> khối rỗng."""
    rows = ["", "", "", "", ""]
    for i, ch in enumerate(str(text).upper()):
        g = _FONT.get(ch, ["███", "█ █", "█ █", "█ █", "███"])
        for r in range(5):
            rows[r] += g[r] + (" " if i < len(str(text)) - 1 else "")
    return [c(r, style, "bold") for r in rows]


def print_big(text: str, style: str = "bright", indent: int = 2) -> None:
    for line in big(text, style):
        print(" " * indent + line)


# ------------------------------------------------------------------ linh vật
# Chồn đất 5 dòng, cùng cách Claude Code vẽ Clawd: khối vuông, một màu, đứng cạnh chữ.
# Tai trên đỉnh, mắt là góc khuyết ▛ ▜, thân đứng, hai chân.
MASCOT = [
    "  ▗▄ ▄▖",
    " ▐▛███▜▌",
    "  ▝▀▀▀▘",
    "   ▐▌▐▌",
    "  ▗▘ ▝▖",
]


def masthead(meta: list[str] | None = None, indent: int = 2, style: str = "accent") -> None:
    """Linh vật bên trái, chữ bên phải — đúng khung đầu phiên của Claude Code."""
    meta = list(meta or [])
    pad = " " * indent
    width = max(len(line.rstrip()) for line in MASCOT)
    for i in range(max(len(MASCOT), len(meta))):
        left = (MASCOT[i] if i < len(MASCOT) else "").rstrip().ljust(width)
        right = meta[i] if i < len(meta) else ""
        line = pad + c(left, style)
        if str(right):
            line += "   " + str(right)
        print(line)


def print_mascot(style: str = "accent", indent: int = 2, caption: str = "") -> None:
    meta = [c(caption, "dim")] if caption else None
    masthead(meta, indent=indent, style=style)


# ------------------------------------------------------------------ lưới chấm
HEAT_CHARS = {0: "·", 1: "▪", 2: "■", 3: "█"}


def heat(cells: list[list[int]], *, row_labels=None, col_labels=None,
         indent: int = 2, cell_w: int = 1, gap: int = 0) -> None:
    """Lưới chấm kiểu đồ thị đóng góp. `cells[r][c]` = cường độ 0..3."""
    ncol = max((len(r) for r in cells), default=0)
    lab = max((len(str(x)) for x in (row_labels or [])), default=0)
    pad = " " * indent
    if col_labels:
        line = pad + " " * (lab + 1)
        for i in range(ncol):
            lab_i = str(col_labels[i]) if i < len(col_labels) else ""
            line += lab_i[:cell_w].ljust(cell_w + gap)
        print(c(line, "faint"))
    for r, row in enumerate(cells):
        line = pad
        if row_labels and r < len(row_labels):
            line += c(str(row_labels[r]).ljust(lab), "dim") + " "
        else:
            line += " " * (lab + 1)
        for i in range(ncol):
            v = row[i] if i < len(row) else 0
            ch = HEAT_CHARS.get(max(0, min(3, int(v))), "·")
            style = {0: "faint", 1: "dim", 2: "accent", 3: "accent"}[max(0, min(3, int(v)))]
            line += c(ch.ljust(cell_w), style) + " " * gap
        print(line)


def legend_heat(labels=("0", "1", "2", "3"), indent: int = 2) -> None:
    parts = []
    for i, t in enumerate(labels):
        style = ["faint", "dim", "accent", "accent"][min(i, 3)]
        parts.append(c(HEAT_CHARS[min(i, 3)], style) + c(f" {t}", "faint"))
    print(" " * indent + "   ".join(parts))


def footer(text: str, indent: int = 2) -> None:
    print()
    print(c(" " * indent + text, "faint"))


def badge(text: str, kind: str = "accent") -> str:
    return c(f" {text} ", kind, "bold")
