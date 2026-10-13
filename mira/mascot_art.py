"""In con chồn đất từ ảnh đã tách nền.

Terminal thường không dán được file ảnh. Khi nó làm được (Windows Terminal,
Kitty, iTerm) thì đưa đúng ảnh vào, chỉ thu nhỏ. Còn lại thì hạ ảnh xuống
vài dòng ký tự nửa khối.
"""
from __future__ import annotations

import base64
import os
import struct
import sys
import zlib
from pathlib import Path

_PNG = Path(__file__).resolve().parents[1] / "chon_dat_cutout.png"
_CACHE: tuple[int, int, bytes] | None = None


def _read_png(path: Path) -> tuple[int, int, bytes]:
    """Đọc PNG RGBA 8-bit, không phụ thuộc thư viện ngoài."""
    global _CACHE
    if _CACHE is not None and _CACHE[0] and path == _PNG:
        return _CACHE
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("không phải PNG")
    i = 8
    width = height = 0
    idat = bytearray()
    while i < len(data):
        ln, typ = struct.unpack(">I4s", data[i:i + 8])
        chunk = data[i + 8:i + 8 + ln]
        if typ == b"IHDR":
            width, height, bit, color, *_rest = struct.unpack(">IIBBBBB", chunk)
            if bit != 8 or color != 6:
                raise ValueError("chỉ nhận PNG RGBA 8-bit")
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        i += 12 + ln
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        filt = raw[pos]
        pos += 1
        row = bytearray(raw[pos:pos + stride])
        pos += stride
        if filt == 1:
            for x in range(4, stride):
                row[x] = (row[x] + row[x - 4]) & 255
        elif filt == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif filt == 3:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif filt == 4:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                up = prev[x]
                ul = prev[x - 4] if x >= 4 else 0
                row[x] = (row[x] + _paeth(left, up, ul)) & 255
        elif filt != 0:
            raise ValueError(f"bộ lọc PNG lạ: {filt}")
        rows.append(bytes(row))
        prev = row
    packed = b"".join(rows)
    if path == _PNG:
        _CACHE = (width, height, packed)
    return width, height, packed


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    da, db, dc = abs(p - a), abs(p - b), abs(p - c)
    if da <= db and da <= dc:
        return a
    if db <= dc:
        return b
    return c


def _crop(w: int, h: int, px: bytes, alpha: int = 24) -> tuple[int, int, int, int]:
    """Ôm đầu và hai tay. Bỏ mầm cây hai bên và bớt đất tối phía dưới."""
    col = [0] * w
    row = [0] * h
    # Chỉ đếm phần trên để đất trải ngang không kéo luôn mầm cây hai bên vào khung.
    y_body = int(h * 0.62)
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            if px[base + x * 4 + 3] >= alpha:
                row[y] += 1
                if y < y_body:
                    col[x] += 1
    xs = [i for i, n in enumerate(col) if n > 8]
    ys = [i for i, n in enumerate(row) if n > 8]
    if not xs or not ys:
        return 0, 0, w, h
    # Đoạn ngang dày nhất là thân con chồn, không phải mầm cây rời.
    best_a = best_b = xs[0]
    start = prev = xs[0]
    for x in xs[1:]:
        if x > prev + 12:
            if prev - start > best_b - best_a:
                best_a, best_b = start, prev
            start = x
        prev = x
    if prev - start > best_b - best_a:
        best_a, best_b = start, prev
    y0, y1 = ys[0], ys[-1]
    y1 = y0 + int((y1 - y0 + 1) * 0.70)
    return best_a, y0, best_b + 1, min(h, y1)


def _sample(px: bytes, w: int, x0: int, y0: int, cw: int, ch: int,
            cols: int, rows: int) -> list[list[tuple[int, int, int, int]]]:
    """Mỗi ô lấy màu chiếm đa số. Trung bình màu sẽ trộn má, mắt và lông thành một mảng bệt."""
    out = []
    for r in range(rows * 2):
        sy0 = y0 + int(r * ch / (rows * 2))
        sy1 = y0 + int((r + 1) * ch / (rows * 2))
        if sy1 <= sy0:
            sy1 = sy0 + 1
        line = []
        for c in range(cols):
            sx0 = x0 + int(c * cw / cols)
            sx1 = x0 + int((c + 1) * cw / cols)
            if sx1 <= sx0:
                sx1 = sx0 + 1
            line.append(_majority(px, w, sx0, sy0, min(sx1, x0 + cw), min(sy1, y0 + ch)))
        out.append(line)
    return out


def _majority(px: bytes, w: int, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    counts: dict[tuple[int, int, int], int] = {}
    total = opaque = 0
    for y in range(y0, y1):
        row = y * w * 4
        for x in range(x0, x1):
            i = row + x * 4
            total += 1
            if px[i + 3] < 24:
                continue
            opaque += 1
            key = (px[i] >> 4, px[i + 1] >> 4, px[i + 2] >> 4)
            counts[key] = counts.get(key, 0) + 1
    if total == 0 or opaque * 2 < total or not counts:
        return (0, 0, 0, 0)
    key = max(counts, key=counts.__getitem__)
    return (key[0] << 4 | 8, key[1] << 4 | 8, key[2] << 4 | 8, 255)


def _cell(top: tuple[int, int, int, int], bot: tuple[int, int, int, int]) -> str:
    ta, ba = top[3] >= 24, bot[3] >= 24
    if not ta and not ba:
        return " "
    if ta and not ba:
        return f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m▀"
    if ba and not ta:
        return f"\x1b[38;2;{bot[0]};{bot[1]};{bot[2]}m▄"
    return (f"\x1b[38;2;{top[0]};{top[1]};{top[2]}"
            f";48;2;{bot[0]};{bot[1]};{bot[2]}m▀")


def render(cols: int, rows: int | None = None, path: Path | None = None) -> list[str]:
    """Trả các dòng ANSI. `rows` là số dòng terminal; bỏ trống thì giữ tỉ lệ ảnh."""
    src = path or _PNG
    if not src.exists():
        return []
    w, h, px = _read_png(src)
    x0, y0, x1, y1 = _crop(w, h, px)
    cw, ch = x1 - x0, y1 - y0
    cols = max(8, cols)
    if rows is None:
        rows = max(4, round(cols * ch / cw / 2))
    rows = max(4, rows)
    samples = _sample(px, w, x0, y0, cw, ch, cols, rows)
    lines = []
    for r in range(rows):
        parts = [_cell(samples[r * 2][c], samples[r * 2 + 1][c]) for c in range(cols)]
        # bỏ khoảng trống thừa bên phải
        text = "".join(parts).rstrip()
        if text:
            text += "\x1b[0m"
        lines.append(text)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def fit(term_cols: int, term_rows: int) -> list[str]:
    """Vừa cửa sổ mà không bóp dọc. Hết chỗ thì thu cột, giữ tỉ lệ đầu và mặt."""
    cols = max(28, min(64, term_cols - 2))
    max_rows = max(8, term_rows - 8)
    art = render(cols)
    if len(art) > max_rows:
        cols = max(28, int(cols * max_rows / len(art)))
        art = render(cols)
    return art


def _nearest(px: bytes, w: int, x0: int, y0: int, cw: int, ch: int,
             dw: int, dh: int) -> bytes:
    """Lấy đúng điểm giữa mỗi ô. Không trộn màu."""
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        sy = y0 + min(ch - 1, int((y + 0.5) * ch / dh))
        row = sy * w * 4
        for x in range(dw):
            sx = x0 + min(cw - 1, int((x + 0.5) * cw / dw))
            i = row + sx * 4
            o = (y * dw + x) * 4
            if px[i + 3] < 24:
                continue
            out[o:o + 3] = px[i:i + 3]
            out[o + 3] = 255
    return bytes(out)


def _bounds(w: int, h: int, px: bytes, alpha: int = 24) -> tuple[int, int, int, int]:
    """Khung đúng phần có hình, gồm cả đầu, tay và đất — không cắt mất mặt."""
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        row = y * w * 4
        for x in range(w):
            if px[row + x * 4 + 3] < alpha:
                continue
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
    if maxx < 0:
        return 0, 0, w, h
    return minx, miny, maxx + 1, maxy + 1


def _boxed(dw: int, dh: int, path: Path | None = None) -> bytes | None:
    """Ảnh thu vào khung dw×dh, căn giữa, phần thừa trong suốt."""
    src = path or _PNG
    if not src.exists() or dw < 1 or dh < 1:
        return None
    w, h, px = _read_png(src)
    x0, y0, x1, y1 = _bounds(w, h, px)
    cw, ch = x1 - x0, y1 - y0
    if dw / dh > cw / ch:
        ih = dh
        iw = max(1, round(ih * cw / ch))
    else:
        iw = dw
        ih = max(1, round(iw * ch / cw))
    small = _nearest(px, w, x0, y0, cw, ch, iw, ih)
    out = bytearray(dw * dh * 4)
    ox = (dw - iw) // 2
    oy = (dh - ih) // 2
    for y in range(ih):
        src_row = y * iw * 4
        dst = ((oy + y) * dw + ox) * 4
        out[dst:dst + iw * 4] = small[src_row:src_row + iw * 4]
    return bytes(out)


def _face_box(w: int, h: int, px: bytes) -> tuple[int, int, int, int]:
    """Đầu, mặt và hai chân. Cắt bớt đất phía dưới, giữ mầm cây sát má."""
    x0, _y0, x1, _y1 = _crop(w, h, px)
    ys = []
    for y in range(h):
        row = y * w * 4
        for x in range(x0, x1):
            if px[row + x * 4 + 3] >= 24:
                ys.append(y)
                break
    if not ys:
        return x0, _y0, x1, _y1
    top = ys[0]
    bot = top + int((ys[-1] - top + 1) * 0.84)
    return x0, top, x1, min(h, bot)


# Logo vẽ đúng cỡ ô chữ, theo mặt trong ảnh: một mắt mở, một mắt nháy, lưỡi, mầm cây.
_LOGO = (
    "......DDDDDDDD......",
    "....DDBBBBBBBBBD....",
    "...DBBBBBBBBBBBBD...",
    "..DBBBBBBBBBBBBBBD..",
    "..DBWWKBBBBBDDDBBD..",
    "..DBBWKBBBBBBKBBBD..",
    ".DDBPPBCCCCCCBPPBD..",
    "..DBPPBCCKKCCBPPD...",
    "..DDBBBCCTTTCBBBD...",
    "...DDBBBBBBBBBDD....",
    "....DDDDBBBBDDD.....",
    "..GG................",
    ".GgG................",
)
_LOGO_PAL = {
    "B": (98, 66, 48),
    "D": (58, 38, 28),
    "C": (230, 178, 138),
    "P": (232, 120, 104),
    "K": (32, 20, 18),
    "W": (245, 236, 228),
    "T": (220, 90, 90),
    "G": (72, 160, 70),
    "g": (120, 200, 90),
}


def logo() -> list[str]:
    """Mỗi điểm ảnh là một ô nền. Không thu ảnh, nên mặt không bị vỡ."""
    width = max(len(row) for row in _LOGO)
    lines = []
    for row in _LOGO:
        row = row.ljust(width)
        parts: list[str] = []
        prev: tuple[int, int, int] | None = None
        for ch in row:
            color = _LOGO_PAL.get(ch)
            if color is None:
                if prev is not None:
                    parts.append("\x1b[0m")
                    prev = None
                parts.append(" ")
            else:
                if color != prev:
                    r, g, b = color
                    parts.append(f"\x1b[48;2;{r};{g};{b}m")
                    prev = color
                parts.append(" ")
        if prev is not None:
            parts.append("\x1b[0m")
        lines.append("".join(parts))
    return lines


def mark(cols: int = 32, rows: int = 11) -> list[str]:
    """Mặt nhỏ nhưng còn mắt nháy, má và lưỡi. Mỗi ô chữ là hai điểm ảnh gốc."""
    if not _PNG.exists() or cols < 1 or rows < 1:
        return []
    w, h, px = _read_png(_PNG)
    x0, y0, x1, y1 = _face_box(w, h, px)
    raw = _nearest(px, w, x0, y0, x1 - x0, y1 - y0, cols, rows * 2)
    lines = []
    for r in range(rows):
        parts = []
        for c in range(cols):
            i = ((r * 2) * cols + c) * 4
            j = i + cols * 4
            top = (raw[i], raw[i + 1], raw[i + 2], raw[i + 3])
            bot = (raw[j], raw[j + 1], raw[j + 2], raw[j + 3])
            parts.append(_cell(top, bot))
        lines.append("".join(parts) + "\x1b[0m")
    return lines


def sprite(cols: int = 16, rows: int | None = None) -> list[str]:
    """Bản bằng ký tự, khi terminal không hiện được file ảnh."""
    cols = max(8, cols)
    if not _PNG.exists():
        return []
    if rows is None:
        w, h, px = _read_png(_PNG)
        x0, y0, x1, y1 = _bounds(w, h, px)
        rows = max(4, round(cols * (y1 - y0) / (x1 - x0) / 2))
    rows = max(4, rows)
    raw = _boxed(cols, rows * 2)
    if not raw:
        return []
    lines = []
    for r in range(rows):
        parts = []
        for c in range(cols):
            i = ((r * 2) * cols + c) * 4
            j = i + cols * 4
            top = (raw[i], raw[i + 1], raw[i + 2], raw[i + 3])
            bot = (raw[j], raw[j + 1], raw[j + 2], raw[j + 3])
            parts.append(_cell(top, bot))
        text = "".join(parts).rstrip()
        if text:
            text += "\x1b[0m"
        lines.append(text)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _cell_px() -> tuple[int, int]:
    if os.name != "nt":
        return 8, 16
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class INFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("nFont", ctypes.c_ulong),
                ("dwFontSize", COORD),
                ("FontFamily", ctypes.c_uint),
                ("FontWeight", ctypes.c_uint),
                ("FaceName", ctypes.c_wchar * 32),
            ]

        k = ctypes.windll.kernel32
        info = INFO()
        info.cbSize = ctypes.sizeof(INFO)
        if k.GetCurrentConsoleFontEx(k.GetStdHandle(-11), False, ctypes.byref(info)):
            x, y = int(info.dwFontSize.X), int(info.dwFontSize.Y)
            if x >= 4 and y >= 8:
                return x, y
    except Exception:
        pass
    return 8, 16


def _png_bytes(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    return out + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _rle(chars: list[str]) -> str:
    out = []
    i = 0
    n = len(chars)
    while i < n:
        j = i + 1
        while j < n and chars[j] == chars[i]:
            j += 1
        count = j - i
        if count >= 3:
            out.append(f"!{count}{chars[i]}")
        else:
            out.append(chars[i] * count)
        i = j
    return "".join(out)


def _closest(pal: dict[tuple[int, int, int], int], key: tuple[int, int, int]) -> int:
    kr, kg, kb = key
    best_i = 0
    best_d = 1 << 30
    for (r, g, b), i in pal.items():
        d = (r - kr) * (r - kr) + (g - kg) * (g - kg) + (b - kb) * (b - kb)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _sixel(rgba: bytes, w: int, h: int) -> str:
    shift = 3
    pal: dict[tuple[int, int, int], int] = {}
    idx: list[int] = []
    for i in range(0, len(rgba), 4):
        if rgba[i + 3] < 24:
            idx.append(-1)
            continue
        key = (rgba[i] >> shift, rgba[i + 1] >> shift, rgba[i + 2] >> shift)
        n = pal.get(key)
        if n is None:
            if len(pal) >= 255:
                n = _closest(pal, key)
            else:
                n = len(pal)
                pal[key] = n
        idx.append(n)
    if not idx:
        pal.clear()
        for i in range(0, len(rgba), 4):
            if rgba[i + 3] < 24:
                idx.append(-1)
                continue
            key = (rgba[i] >> 4, rgba[i + 1] >> 4, rgba[i + 2] >> 4)
            n = pal.get(key)
            if n is None:
                n = len(pal)
                pal[key] = n
            idx.append(n)
        shift = 4
    if not pal:
        return ""
    span = 1 << (8 - shift)
    top = max(1, span - 1)
    parts = [f"\x1bP0;0;8q\"1;1;{w};{h}"]
    for key, n in pal.items():
        r, g, b = (round(c * 100 / top) for c in key)
        parts.append(f"#{n};2;{r};{g};{b}")
    for band in range((h + 5) // 6):
        for n in range(len(pal)):
            chars: list[str] = []
            used = False
            for x in range(w):
                bits = 0
                for bit in range(6):
                    y = band * 6 + bit
                    if y < h and idx[y * w + x] == n:
                        bits |= 1 << bit
                        used = True
                chars.append(chr(63 + bits))
            if used:
                parts.append(f"#{n}{_rle(chars)}$")
        parts.append("-")
    parts.append("\x1b\\")
    return "".join(parts)


def _kitty(png: bytes, cols: int, rows: int) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    chunks = [b64[i:i + 4096] for i in range(0, len(b64), 4096)] or [""]
    parts = []
    for i, ch in enumerate(chunks):
        more = 1 if i < len(chunks) - 1 else 0
        if i == 0:
            parts.append(
                f"\x1b_Ga=T,f=100,t=d,q=2,C=1,c={cols},r={rows},m={more};{ch}\x1b\\"
            )
        else:
            parts.append(f"\x1b_Gm={more};{ch}\x1b\\")
    return "".join(parts)


def _proto() -> str:
    if not sys.stdout.isatty():
        return ""
    forced = (os.environ.get("MIRA_IMAGE") or "").strip().lower()
    if forced in ("off", "0", "no"):
        return ""
    if forced in ("sixel", "kitty", "iterm"):
        return forced
    term = os.environ.get("TERM", "")
    prog = os.environ.get("TERM_PROGRAM", "")
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term or "ghostty" in term:
        return "kitty"
    if prog == "iTerm.app":
        return "iterm"
    if prog in ("WezTerm", "Warp") or os.environ.get("WEZTERM_PANE"):
        return "kitty"
    if os.environ.get("WT_SESSION") or prog == "Windows Terminal":
        return "sixel"
    return ""


def embed(cols: int = 14, rows: int = 8) -> tuple[str, int, int] | None:
    """Đưa đúng file ảnh vào ô `cols`×`rows`. None nếu terminal không hiện ảnh."""
    kind = _proto()
    if not kind or not _PNG.exists():
        return None
    try:
        cw_px, ch_px = _cell_px()
        cols = max(8, cols)
        rows = max(4, rows)
        rgba = _boxed(cols * cw_px, rows * ch_px)
        if not rgba:
            return None
        pw, ph = cols * cw_px, rows * ch_px
        if kind == "sixel":
            seq = _sixel(rgba, pw, ph)
        elif kind == "iterm":
            b64 = base64.b64encode(_png_bytes(pw, ph, rgba)).decode("ascii")
            seq = f"\x1b]1337;File=inline=1;width={cols};height={rows};preserveAspectRatio=1:{b64}\a"
        else:
            seq = _kitty(_png_bytes(pw, ph, rgba), cols, rows)
        if not seq:
            return None
        return seq, rows, cols
    except Exception:
        return None


_IDX = Path(__file__).with_name("tui_palette_256.txt")
_GRID: list[list[int]] | None = None


def _palette() -> list[list[int]]:
    """Lưới 80×26 từ ANSI đã đưa. Màu 0 là nền, không tô."""
    global _GRID
    if _GRID is not None:
        return _GRID
    rows = []
    try:
        for line in _IDX.read_text(encoding="ascii").splitlines():
            if line.strip():
                rows.append([int(n) for n in line.split(",")])
    except OSError:
        rows = []
    _GRID = rows
    return rows


def _paint_row(row: list[int]) -> str:
    out: list[str] = []
    prev = 0
    for color in row:
        if color == 0:
            if prev:
                out.append("\x1b[0m")
                prev = 0
            out.append(" ")
        else:
            if color != prev:
                out.append(f"\x1b[48;5;{color}m")
                prev = color
            out.append(" ")
    if prev:
        out.append("\x1b[0m")
    return "".join(out)


def card_art(cols: int, rows: int) -> list[str]:
    """Thu ANSI 80×26 vào số cột và dòng cho trước."""
    grid = _palette()
    if not grid or cols < 1 or rows < 1:
        return []
    src_h, src_w = len(grid), len(grid[0])
    if cols == src_w and rows == src_h:
        scaled = grid
    else:
        scaled = []
        for y in range(rows):
            sy = min(src_h - 1, (y * src_h) // rows)
            scaled.append([grid[sy][min(src_w - 1, (x * src_w) // cols)] for x in range(cols)])
    return [_paint_row(row) for row in scaled]
