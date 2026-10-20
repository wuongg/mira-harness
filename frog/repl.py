"""REPL tương tác — kiểu phiên làm việc của Claude Code, nhưng định tuyến theo làn của SPEC.

    r0-shadow chat                 # mở phiên
    r0-shadow chat --mode plan     # chỉ đề xuất, không ghi
    r0-shadow chat --resume <id>   # mở lại phiên cũ

Slash command: /help /mode /model /team /tools /cost /clear /save /sessions /resume /exit
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from . import config as C
from . import ui
from .agent import run_turn
from .lineedit import read_line
from .tools import MODES, TOOL_SPECS, Session

_hist: list[str] = []

SESS_DIR = Path.home() / ".frog" / "sessions"

HELP = """
  /help                 trợ giúp
  /mode <chế độ>        đổi quyền
                          plan            chỉ bàn, không ghi, không chạy lệnh
                          default         hỏi trước khi ghi hoặc chạy lệnh
                          acceptEdits     ghi tệp không hỏi, vẫn hỏi khi chạy lệnh
                          bypass          không hỏi gì
  /model <tên>          đổi model (đang dùng {default})
  /team on|off          bật hoặc tắt đội nhiều vai
  /tools                công cụ đang có
  /cost                 token và tiền của phiên này
  /audit                đã ghi gì, đã chạy lệnh gì
  /diff                 tệp đã đổi, thêm hoặc bớt bao nhiêu dòng
  /undo                 hoàn tác lần sửa gần nhất
  /memory [nội dung]    xem hoặc ghi nhớ của dự án (MIRA.md)
  /compact              rút gọn hội thoại, giữ vài lượt gần nhất
  /menu                 bốn việc chạy ở terminal, sau khi thoát phiên
  /keys                 nhập khoá API
  /clear                xoá hội thoại, giữ sổ tiền
  /save                 lưu phiên
  /sessions             các phiên đã lưu
  /resume <id>          mở lại một phiên
  /exit                 thoát
"""

MODE_LABEL = {
    "plan": "chỉ bàn, không ghi",
    "default": "hỏi trước khi ghi",
    "acceptEdits": "ghi không cần hỏi",
    "bypass": "làm luôn, không hỏi",
}


def _sess_path(sid: str) -> Path:
    return SESS_DIR / f"{sid}.jsonl"


def _new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def save_session(sid: str, history: list[dict], events: list[dict], meta: dict,
                 trace: list[dict] | None = None) -> Path:
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    p = _sess_path(sid)
    with p.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "meta", **meta}, ensure_ascii=False) + "\n")
        if trace is not None:
            for row in trace:
                if row.get("kind") == "message":
                    line = {"type": "message", "role": row.get("role"), "content": row.get("content")}
                else:
                    line = {"type": "event", **row}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        else:
            for m in history:
                f.write(json.dumps({"type": "message", **m}, ensure_ascii=False) + "\n")
            for e in events:
                f.write(json.dumps({"type": "event", **e}, ensure_ascii=False) + "\n")
    return p


def load_trace(sid: str) -> tuple[list[dict], dict]:
    """Đọc jsonl thành đúng một sổ, giữ thứ tự."""
    p = _sess_path(sid)
    if not p.exists():
        return [], {}
    trace: list[dict] = []
    meta: dict = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        t = o.pop("type", None)
        if t == "message":
            trace.append({"kind": "message", "role": o.get("role"), "content": o.get("content")})
        elif t == "event":
            trace.append(o)
        elif t == "meta":
            meta = o
    return trace, meta


def load_session(sid: str) -> tuple[list[dict], list[dict], dict]:
    p = _sess_path(sid)
    if not p.exists():
        return [], [], {}
    hist, evs, meta = [], [], {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        t = o.pop("type", None)
        if t == "message":
            hist.append(o)
        elif t == "event":
            evs.append(o)
        elif t == "meta":
            meta = o
    return hist, evs, meta


def list_sessions(n: int = 12) -> list[dict]:
    if not SESS_DIR.exists():
        return []
    out = []
    for p in sorted(SESS_DIR.glob("*.jsonl"), key=lambda x: -x.stat().st_mtime)[:n]:
        meta = {}
        try:
            first = p.read_text(encoding="utf-8").splitlines()[0]
            meta = json.loads(first)
        except Exception:
            pass
        out.append({"id": p.stem, "mtime": time.strftime("%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                    "model": meta.get("model"), "turns": meta.get("turns"),
                    "task": (meta.get("first_task") or "")[:60]})
    return out


def _short_path(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    if text.lower().startswith(home.lower()):
        return "~" + text[len(home):]
    return text


def _vis(text: str) -> int:
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


def _pad(text: str, width: int) -> str:
    extra = width - _vis(text)
    if extra > 0:
        return text + " " * extra
    return text


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _center(text: str, width: int) -> str:
    if len(text) >= width:
        return text[:width]
    gap = width - len(text)
    return " " * (gap // 2) + text + " " * (gap - gap // 2)


def banner(session: Session, model: str, team_mode: bool) -> None:
    """Khung chào trải hết chiều ngang. Logo mặt chồn vẽ đúng cỡ ô, không thu ảnh."""
    from .cli import VERSION
    from .mascot_art import logo

    quyen = MODE_LABEL.get(session.mode, session.mode)
    if team_mode:
        quyen += " · có đội"
    colored = ui.c("x", "dim") != "x"
    # Cột viền phải. Không vẽ tới cột cuối — terminal đẩy ký tự đó xuống dòng dưới.
    edge_col = max(48, ui.term_width() - 4)
    picture = None
    left_w = 36 if edge_col >= 72 else edge_col - 2
    right_w = edge_col - left_w - 3 if edge_col >= 72 else 0
    art = logo() if colored else []
    img_cols = 22
    img_rows = len(art) if art else 7
    if not colored:
        img_cols, img_rows = 14, 7
    elif art:
        img_rows = len(art)
    _welcome_card(
        version=VERSION,
        model=model,
        quyen=quyen,
        path=_short_path(session.root),
        root=session.root,
        width=edge_col,
        edge_col=edge_col,
        left_w=left_w,
        right_w=right_w,
        colored=colored,
        art=art,
        picture=picture,
        img_cols=img_cols,
        img_rows=img_rows,
    )


def _emit_edge(body: str, border: str, edge_col: int) -> None:
    """Viền phải đứng ở cột edge_col, không nằm trong chuỗi dài bằng bề ngang."""
    sys.stdout.write(f"{body}\x1b[{edge_col}G{border}\n")
    sys.stdout.flush()


def _warm(text: str, colored: bool, bold: bool = False) -> str:
    if not colored:
        return text
    weight = "1;" if bold else ""
    return f"\x1b[{weight}38;2;196;122;82m{text}\x1b[0m"


_SKIP_NAMES = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache"}


def _git_branch(root: Path) -> str:
    git = root / ".git"
    try:
        if git.is_file():
            line = git.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                git = Path(line.split(":", 1)[1].strip())
                if not git.is_absolute():
                    git = (root / git).resolve()
        text = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if text.startswith("ref: "):
        return text.rsplit("/", 1)[-1]
    return text[:7]


def _memory_line(root: Path) -> str:
    try:
        lines = (root / "MIRA.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return "chưa có MIRA.md"
    for line in lines:
        text = line.strip().lstrip("#").strip()
        if text:
            return text
    return "MIRA.md đang trống"


def _folder_names(root: Path) -> list[str]:
    try:
        items = [p for p in root.iterdir() if p.name not in _SKIP_NAMES and not p.name.startswith(".")]
    except OSError:
        return []
    items.sort(key=lambda p: (p.is_file(), p.name.lower()))
    return [p.name + ("/" if p.is_dir() else "") for p in items]


def _wrap_names(names: list[str], width: int) -> list[str]:
    if width < 4:
        return []
    if not names:
        return [" thư mục trống"]
    rows: list[str] = []
    cur = ""
    names = [n if len(n) <= width - 1 else n[: width - 2] + "…" for n in names]
    for name in names:
        piece = name if not cur else "  " + name
        lead = "" if cur else " "
        if len(lead + cur + piece) > width and cur:
            rows.append(cur)
            cur = " " + name
        else:
            cur = (cur or " ") + (piece if cur else name)
    if cur:
        rows.append(cur)
    return rows


def _col_widths(width: int) -> list[int]:
    if width >= 78:
        n = 3
    elif width >= 52:
        n = 2
    else:
        n = 1
    gap = 2 * (n - 1)
    base = (width - gap) // n
    widths = [base] * n
    widths[-1] += width - gap - base * n
    return widths


def _cell(text: str, width: int, paint) -> str:
    return _pad(paint(_clip(text, width)), width)


def _right_panel(root: Path, width: int, rows: int, colored: bool) -> list[str]:
    """Điền cột phải: gợi ý, thư mục đang mở, tên tệp. Không thêm chiều cao khung."""
    branch = _git_branch(root)
    folder = [
        " " + (root.name or str(root)),
        " nhánh " + branch if branch else " không có git",
        " " + _memory_line(root),
    ]
    blocks = [
        (" Gợi ý", [
            " Cứ gõ việc cần làm.",
            " /help để xem lệnh.",
            " /exit để thoát.",
        ]),
        (" Thư mục", folder),
        (" Lệnh", [
            " /mode đổi quyền",
            " /model đổi model",
            " /memory ghi nhớ",
        ]),
    ]
    widths = _col_widths(width)
    blocks = blocks[:len(widths)]
    lines: list[str] = []

    def paint_head(text: str) -> str:
        return _warm(text, colored, bold=True)

    def paint_rule(text: str) -> str:
        return _warm(text, colored)

    def paint_body(text: str) -> str:
        return ui.c(text, "text")

    heads, rules, bodies = [], [], []
    for i, (title, body) in enumerate(blocks):
        w = widths[i]
        heads.append(_cell(title, w, paint_head))
        rules.append(_cell(" " + "─" * max(1, w - 1), w, paint_rule))
        bodies.append([_cell(line, w, paint_body) for line in body])
    gap = "  " if len(widths) > 1 else ""
    lines.append(gap.join(heads))
    lines.append(gap.join(rules))
    for i in range(3):
        lines.append(gap.join(col[i] if i < len(col) else " " * widths[n] for n, col in enumerate(bodies)))

    room = rows - len(lines) - 3
    if room > 0:
        lines.append(" " * width)
        lines.append(_pad(paint_head(" Trong thư mục"), width))
        lines.append(_pad(paint_rule(" " + "─" * max(1, width - 1)), width))
        wrapped = _wrap_names(_folder_names(root), width)
        if len(wrapped) > room:
            wrapped = wrapped[:room]
            tail = wrapped[-1].rstrip()
            if len(tail) + 2 <= width:
                wrapped[-1] = tail + " …"
        for line in wrapped:
            lines.append(_pad(paint_body(line), width))
    return [_pad(line, width) for line in lines[:rows]]


def _welcome_card(version: str, model: str, quyen: str, path: str, root: Path, width: int,
                  edge_col: int, left_w: int, right_w: int, colored: bool, art: list[str],
                  picture: tuple[str, int, int] | None, img_cols: int, img_rows: int) -> None:
    split = right_w > 0
    blank = " " * left_w
    if picture:
        slot = [blank for _ in range(img_rows)]
    elif art:
        slot = [_pad(_center_art(line, left_w), left_w) for line in art]
        slot.extend(blank for _ in range(img_rows - len(slot)))
        slot = slot[:img_rows]
    else:
        slot = [_pad(_center(line, left_w), left_w) for line in ui.MASCOT]
        slot.extend(blank for _ in range(img_rows - len(slot)))

    left = [
        blank,
        _pad(ui.c(_center("Chào lại", left_w), "bright"), left_w),
        blank,
    ]
    slot_at = len(left)
    left.extend(slot)
    left.extend([
        blank,
        _pad(ui.c("  " + _clip(model, left_w - 2), "dim"), left_w),
        _pad(ui.c("  " + _clip(quyen, left_w - 2), "dim"), left_w),
        _pad(ui.c("  " + _clip(path, left_w - 2), "faint"), left_w),
    ])
    if split:
        right = _right_panel(root, right_w, len(left), colored)
        while len(right) < len(left):
            right.append(" " * right_w)
    else:
        right = []
        left.extend([
            _pad("", left_w),
            _pad(ui.c("  Cứ gõ việc cần làm.", "text"), left_w),
            _pad(ui.c("  /help để xem lệnh.", "text"), left_w),
            _pad(ui.c("  /exit để thoát.", "text"), left_w),
        ])

    title = f"─ frog {version} "
    top_fill = max(0, width - 2 - len(title))
    top = _warm("╭" + title + "─" * top_fill, colored)
    if split:
        bottom = _warm("╰" + "─" * left_w + "┴" + "─" * right_w, colored)
    else:
        bottom = _warm("╰" + "─" * left_w, colored)

    print()
    _emit_edge(top, _warm("╮", colored), edge_col)
    edge = _warm("│", colored)
    for i, line in enumerate(left):
        body = edge + line + (edge + right[i] if split else "")
        _emit_edge(body, edge, edge_col)
    _emit_edge(bottom, _warm("╯", colored), edge_col)
    if picture:
        seq, _rows, cols = picture
        pad = max(0, (left_w - cols) // 2)
        # Thêm 1 vì còn dòng viền dưới, con trỏ đang ở dòng ngay sau khung.
        up = len(left) - slot_at + 1
        # Con trỏ đang ở dòng dưới khung. Nhảy lên ô ảnh, vẽ, rồi trả lại.
        sys.stdout.write(f"\x1b7\x1b[{up}A\x1b[{2 + pad}G{seq}\x1b8")
        sys.stdout.flush()


def _center_art(line: str, width: int) -> str:
    visible = _vis(line)
    if visible >= width:
        return line
    gap = width - visible
    return " " * (gap // 2) + line + " " * (gap - gap // 2)


def _message_text(content) -> str:
    if isinstance(content, list):
        return " ".join(str(x.get("text") or x.get("content") or "") for x in content if isinstance(x, dict))
    return str(content or "")


def view_for_model(trace: list[dict]) -> list[dict]:
    """Dựng hội thoại gửi model từ sổ. Không xoá sự kiện gốc."""
    messages = [e for e in trace if e.get("kind") == "message"]
    rows = [{"role": e.get("role") or "user", "content": e.get("content") or ""} for e in messages]
    condensed = [e for e in trace if e.get("kind") == "condensed"]
    if not condensed:
        return rows
    last = condensed[-1]
    count_at = int(last.get("message_count") or 0)
    kept = int(last["kept"]) if last.get("kept") is not None else 6
    start = max(0, count_at - kept)
    summary = last.get("summary") or ""
    return [{"role": "user", "content": summary}, *rows[start:]]


def condense_trace(trace: list[dict], audit: list[dict] | None = None) -> tuple[str, dict | None]:
    """Tóm tắt local. Có sổ sửa thì dùng dòng sổ, không lấy 120 ký tự đầu."""
    view = view_for_model(trace)
    if audit is None and len(view) <= 6:
        return "Hội thoại còn ngắn, chưa cần rút gọn.", None
    if audit is not None:
        lines = [f"{row.get('action')} {row.get('path')}"
                 for row in audit
                 if row.get("action") in ("write_file", "edit_file", "multi_edit")]
        summary = "TÓM TẮT SỔ SỬA:\n" + ("\n".join(lines) or "(chưa sửa)")
    else:
        old = view[:-6]
        lines = []
        for msg in old:
            text = _message_text(msg.get("content")).strip().splitlines()
            if not text or not text[0].strip():
                continue
            lines.append(f"- {msg.get('role', '?')}: {text[0][:120]}")
        summary = "TÓM TẮT CÁC LƯỢT TRƯỚC:\n" + ("\n".join(lines[:40]) or "(không có nội dung)")
    dropped = max(0, len(view) - 6)
    count = sum(1 for e in trace if e.get("kind") == "message")
    event = {"kind": "condensed", "dropped": dropped, "kept": 6,
             "summary": summary, "message_count": count}
    return f"Đã rút gọn: gộp {dropped} tin cũ, giữ 6 tin gần nhất.", event


def _ask_approval(tool: str, args: dict) -> bool:
    print()
    if tool == "write_file":
        print("  " + ui.c("ghi", "warn", "bold") + f"  {args.get('path')}"
              + ui.c(f"    {args.get('bytes', '?')} ký tự", "dim"))
    else:
        print("  " + ui.c("chạy", "warn", "bold") + f"  {args.get('cmd')}")
    try:
        answer = input(ui.c("  cho phép không?  y = có, n = không, a = luôn cho phép  ", "bold")).strip().lower()
        if answer in ("a", "always", "luôn", "luon"):
            return "always"
        return answer in ("y", "yes", "có", "co")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def repl(args) -> int:
    root = Path(args.cwd or ".").resolve()
    if not root.is_dir():
        ui.note(f"Không có thư mục {root}.", "bad")
        return 2
    sid = args.resume or _new_session_id()
    history: list[dict] = []
    events: list[dict] = []
    meta = {"session": sid}
    loaded: list[dict] = []
    if args.resume:
        loaded, meta = load_trace(args.resume)
        history = view_for_model(loaded)
        ui.note(f"Mở lại phiên {args.resume}, {len(history)} lượt.", "ok")

    mode = args.mode
    if mode == "bypass":
        from .agent import auto_approve_allowed
        if not auto_approve_allowed("read_only", ["internal"]):
            ui.note("bypass không hợp lệ với bề mặt này. Giữ default.", "warn")
            mode = "default"
    session = Session(root=root, mode=mode, approve=_ask_approval)
    session.trace.extend(loaded)
    from .providers import agent_binding, choose_proxy_model, list_proxy_models, official_openrouter
    base = getattr(args, "base_url", None) or os.environ.get("FROG_BASE_URL")
    args.base_url = base
    explicit = getattr(args, "model", None)
    if base and not official_openrouter(base) and explicit in (None, "", C.OPENROUTER_MODEL):
        from .keys import resolve
        ids = list_proxy_models(base, resolve("openrouter")[0])
        picked = choose_proxy_model(ids)
        if picked:
            explicit = picked
            ui.note(f"Model: {picked}.", "ok")
        else:
            ui.note("Proxy không trả model nào. Không gửi slug Anthropic.", "bad")
            return 2
    model, args.provider = agent_binding(
        explicit or C.ROLE_MODEL["worker"], getattr(args, "provider", None), base)
    team_mode = bool(args.team)
    cost_total = 0.0
    tok_total = {"in": 0, "out": 0}
    turns = 0

    banner(session, model, team_mode)
    if args.task:
        _one_turn(args.task, session, model, args, history, events, team_mode)
        return 0

    while True:
        print()
        try:
            line = read_line(ui.c("> ", "accent", "bold"), history=_hist).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        _hist.append(line)

        # ---------------------------------------------------- slash command
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""
            if cmd in ("exit", "quit", "q"):
                break
            elif cmd == "help":
                print(HELP.format(default=C.ROLE_MODEL["worker"]))
            elif cmd == "mode":
                if arg in MODES:
                    if arg == "bypass":
                        from .agent import auto_approve_allowed
                        if not auto_approve_allowed("read_only", ["internal"]):
                            ui.note("bypass không hợp lệ với bề mặt này. Giữ quyền cũ.", "warn")
                            arg = ""
                    if arg in MODES:
                        session.mode = arg
                        ui.note(f"Quyền: {MODE_LABEL[arg]}.",
                                "warn" if arg in ("plan", "bypass") else "ok")
                else:
                    ui.note("Chọn plan, default, acceptEdits hoặc bypass.", "warn")
            elif cmd == "model":
                if arg:
                    from .providers import agent_binding
                    model, args.provider = agent_binding(arg, getattr(args, "provider", None))
                    ui.note(f"Model: {model}.", "ok")
                else:
                    ui.note(f"Model hiện tại: {model}.", "info")
            elif cmd == "team":
                team_mode = arg.lower() in ("on", "1", "true", "bật", "bat")
                ui.note("Đội nhiều vai: bật." if team_mode else "Đội nhiều vai: tắt. Chỉ một vai làm việc.",
                        "ok" if team_mode else "info")
            elif cmd == "tools":
                ui.table(["công cụ", "việc"], [[k, v] for k, v in TOOL_SPECS.items()], ["l", "l"])
            elif cmd == "cost":
                _print_cost(cost_total, tok_total, turns, model)
            elif cmd == "audit":
                if not session.audit:
                    ui.note("Chưa ghi tệp nào, chưa chạy lệnh nào.", "info")
                else:
                    ui.table(["hành động", "đối tượng", "chế độ"],
                             [[a["action"], a.get("path") or a.get("cmd", "")[:50], a.get("mode", "")]
                              for a in session.audit], ["l", "l", "l"])
            elif cmd == "diff":
                print(session.diff_summary())
            elif cmd == "undo":
                ui.note(session.undo_last(), "ok")
            elif cmd == "memory":
                if arg:
                    ui.note(f"Đã ghi vào {session.save_memory(arg)}.", "ok")
                else:
                    m = session.load_memory()
                    ui.note(m or "Chưa có ghi nhớ. Gõ /memory rồi đến nội dung cần nhớ.", "info")
            elif cmd == "compact":
                note, condensed = condense_trace(session.trace)
                if condensed:
                    session.log_event("condensed", layer="context",
                                      **{k: v for k, v in condensed.items() if k != "kind"})
                history[:] = view_for_model(session.trace)
                ui.note(note, "ok" if note.startswith("Đã") else "info")
            elif cmd == "menu":
                ui.section("Bốn việc, chạy ở terminal sau khi gõ /exit")
                ui.table(["việc", "lệnh"], [
                    ["1  Mở phiên", "frog"],
                    ["2  Xem nhật ký", "frog logs"],
                    ["3  Bảng số", "frog dash"],
                    ["4  Nhập khoá API", "/keys  hoặc  frog keys"],
                ], ["l", "l"])
                ui.note("Bạn đang ở trong phiên. Cứ gõ việc, không cần gõ frog.", "info")
            elif cmd == "keys":
                from .keys import prompt_setup
                prompt_setup()
            elif cmd == "clear":
                count = sum(1 for e in session.trace if e.get("kind") == "message")
                session.log_event("condensed", dropped=count, kept=0, layer="context",
                                  summary="(đã xoá hội thoại)", message_count=count)
                history[:] = view_for_model(session.trace)
                ui.note("Đã xoá hội thoại. Sổ tiền vẫn giữ.", "ok")
            elif cmd == "save":
                p = save_session(sid, history, events,
                                 {**meta, "model": model, "turns": turns,
                                  "mode": session.mode, "cost_usd": cost_total,
                                  "tokens": dict(tok_total),
                                  "first_task": meta.get("first_task", "")},
                                 trace=session.trace)
                ui.note(f"Đã lưu: {p}", "ok")
            elif cmd == "sessions":
                rows = list_sessions()
                if not rows:
                    ui.note("Chưa có phiên nào.", "info")
                else:
                    ui.table(["id", "lúc", "model", "lượt", "việc"],
                             [[r["id"], r["mtime"], r["model"] or "", r["turns"] or "", r["task"]] for r in rows],
                             ["l", "l", "l", "r", "l"])
            elif cmd == "resume":
                if not arg:
                    ui.note("Gõ /resume rồi đến mã phiên.", "warn")
                else:
                    loaded_now, m = load_trace(arg)
                    if not loaded_now:
                        ui.note(f"Không có phiên {arg}.", "bad")
                    else:
                        session.trace[:] = loaded_now
                        history[:] = view_for_model(session.trace)
                        meta, sid = m, arg
                        ui.note(f"Đã mở {arg}, {len(history)} lượt.", "ok")
            else:
                ui.note(f"Không có lệnh /{cmd}. Gõ /help.", "warn")
            continue

        # ------------------------------------------ gõ nhầm lệnh shell trong phiên
        low = line.strip().lower()
        if (low == "frog" or low.startswith("frog ") or low.startswith("r0-shadow")
                or low.startswith("python -m r0") or low.startswith("py -m r0")):
            ui.note("Bạn đang ở trong phiên, không cần gõ frog nữa.", "warn")
            ui.note("Cứ gõ việc cần làm. /menu để xem bốn việc, /exit để thoát.", "info")
            continue

        # ------------------------------------------------------- một lượt
        t0 = time.time()
        if team_mode:
            _team_turn(line, session, args)
            print(ui.c(f"  {time.time() - t0:.1f}s", "dim"))
        else:
            from .providers import agent_binding
            model, args.provider = agent_binding(model, getattr(args, "provider", None))
            r = _one_turn(line, session, model, args, history, events, team_mode)
            if r:
                cost_total += r.get("costUsd") or 0.0
                tok_total["in"] += r["usage"]["in"]
                tok_total["out"] += r["usage"]["out"]
                turns += r.get("turns", 0)
                if not meta.get("first_task"):
                    meta["first_task"] = line
                _status_line(model, r.get("turns", 0), r.get("usage") or {"in": 0, "out": 0},
                             r.get("costUsd"), time.time() - t0, cost_total,
                             (r.get("toolSummary") or {}).get("calls", 0))
            else:
                print(ui.c(f"  {time.time() - t0:.1f}s", "dim"))

    if session.trace or history:
        p = save_session(sid, history, events,
                         {**meta, "model": model, "turns": turns,
                          "mode": session.mode, "cost_usd": cost_total,
                          "tokens": dict(tok_total)},
                         trace=session.trace)
        print()
        ui.note(f"Phiên đã lưu: {p}", "info")
    return 0


def _one_turn(task: str, session: Session, model: str, args, history, events, team_mode) -> dict | None:
    def show_tool(name, a):
        brief = a.get("cmd") or a.get("path") or a.get("pattern") or ""
        print()
        print("  " + ui.c(name, "accent") + ui.c(f"  {str(brief)[:90]}", "dim"))
    view = view_for_model(session.trace)
    res = run_turn(task=task, session=session, model=model,
                   provider_name=args.provider, base_url=args.base_url,
                   max_tokens=args.max_tokens, history=view,
                   price_in=_declared_price(args),
                   protocol=getattr(args, "protocol", "auto"),
                   no_stream=getattr(args, "no_stream", False),
                   max_turns=getattr(args, "max_turns", 0) or None,
                   max_budget_usd=getattr(args, "max_budget_usd", None),
                   on_text=lambda s: print(s, end="", flush=True),
                   on_tool=show_tool,
                   on_note=lambda m: print(ui.c(f"  · {m}", "grey")))
    print()
    if res.get("convo"):
        for msg in res["convo"][len(view):]:
            session.log_event("message", role=msg.get("role") or "user",
                              content=_message_text(msg.get("content")))
        history[:] = view_for_model(session.trace)
    for row in session.trace:
        if row not in events:
            events.append(row)
    if res["status"] == "blocked":
        ui.note(f"Bị chặn: {res['error']}", "bad")
        return None
    if res["status"] == "error":
        _err_note(res.get("error") or "")
        return None
    c = res.get("costUsd")
    if res.get("convo"):
        history.clear()
        history.extend(res["convo"])
    return res


def _team_turn(task: str, session: Session, args) -> None:
    """Định tuyến theo làn của SPEC rồi chạy đội nhiều vai."""
    from .team import build_plan, cursor_rows, execute_plan, load_cursor_team
    hints = dict(surface="write_sandbox" if session.mode in ("default", "acceptEdits") else "read_only",
                 labels=["internal"], records=100, dollars=0.0)
    plan = build_plan(task, **hints)
    loaded = load_cursor_team(plan.roles, getattr(args, "base_url", None))
    if loaded:
        base, role_models, worker_models = loaded
        ui.table(["vai", "model"], cursor_rows(plan.roles, role_models, worker_models), ["l", "l"])
        ui.kv("làn", f"{plan.lane} · sàn {plan.floor} · cổng tầng {plan.gate_tier}")
        if plan.gate_tier >= 3:
            ui.note("Việc này cần hai người duyệt.", "warn")
        res = execute_plan(plan, provider_name="openrouter", base_url=base,
                           role_models=role_models, worker_models=worker_models,
                           root=session.root,
                           on_step=lambda m: print("  " + m))
    else:
        ui.table(["vai", "model"], [[r, C.ROLE_MODEL.get(r, "?")] for r in plan.roles], ["l", "l"])
        ui.kv("làn", f"{plan.lane} · sàn {plan.floor} · cổng tầng {plan.gate_tier}")
        if plan.gate_tier >= 3:
            ui.note("Việc này cần hai người duyệt.", "warn")
        res = execute_plan(plan, provider_name=None, root=session.root,
                           on_step=lambda m: print("  " + m))
    called = [s for s in (res.get("steps") or []) if s and not s.get("budget") and s.get("model")]
    if called:
        from .team import checkpoint_path
        ui.note(f"Trace: {checkpoint_path(session.root, res['id'])}", "info")
    if res["status"] not in ("ok",):
        _err_note(res.get("fail_reason") or "")
    ui.note(f"Trạng thái: {res['status']}" + (f". {res['fail_reason']}" if res["fail_reason"] else ""),
            "ok" if res["status"] == "ok" else "warn")


def _tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _status_line(model, turns, tok, turn_cost, dt, session_cost, calls=0) -> None:
    """Dòng trạng thái in dưới mỗi lượt agent — kiểu Claude Code CLI."""
    w = min(ui.term_width(), 72)
    print(ui.c("  " + "─" * (w - 2), "faint"))
    seg = [ui.c(model, "accent", "bold"), f"{turns} lượt",
           f"{_tok(tok['in'])} vào  {_tok(tok['out'])} ra"]
    if calls:
        seg.append(f"{calls} công cụ")
    seg.append(f"${turn_cost:.4f}" if turn_cost is not None else "chưa có giá")
    seg.append(f"{dt:.1f}s")
    seg.append(ui.c(f"phiên ${session_cost:.4f}", "bright", "bold"))
    print("  " + ui.c(" · ", "faint").join(seg))


def _declared_price(args) -> tuple[float, float] | None:
    raw = getattr(args, "price_in", None)
    if not raw:
        return None
    left, sep, right = str(raw).partition(",")
    if not sep:
        return None
    try:
        return float(left), float(right)
    except ValueError:
        return None


def _err_note(err: str) -> None:
    """Báo lỗi gọi model — dịch lỗi xác thực thành việc cần làm."""
    low = err.lower()
    if any(s in low for s in ("401", "403", "authentication", "invalid x-api-key",
                              "invalid_api_key", "unauthorized", "api key")):
        ui.note("Khoá API không dùng được, nên model không trả lời.", "bad")
        ui.note("Gõ /keys để nhập lại, hoặc thoát rồi chạy frog keys set.", "info")
        ui.note(f"Chi tiết: {err[:160]}", "info")
    elif "402" in low or "more credits" in low or "can only afford" in low:
        ui.note("Số dư OpenRouter không đủ cho trần token của lượt này.", "bad")
        ui.note("Nạp thêm credit tại openrouter.ai, hoặc thoát rồi vào frog lại.", "info")
    else:
        ui.note(err, "bad")


def _print_cost(cost: float, tok: dict, turns: int, model: str) -> None:
    ui.kv("model", model)
    ui.kv("số lượt", turns)
    ui.kv("token", f"{tok['in']} vào + {tok['out']} ra = {tok['in'] + tok['out']}")
    priced = model in C.PRICES
    ui.kv("chi phí", f"${cost:.6f}" if priced else "chưa có bảng giá cho model này")
    ui.kv("trần phiên", f"${C.SESSION_CAP:.2f}"
          + (ui.c("  đã vượt", "warn", "bold") if cost > C.SESSION_CAP else ""))
