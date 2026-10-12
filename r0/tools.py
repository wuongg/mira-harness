"""Công cụ cho agent — có cổng xin phép, có Executor là cửa ghi duy nhất.

Mọi đường dẫn bị khoá trong thư mục gốc. Ghi và chạy lệnh phải qua cổng.
Chế độ quyền giống Claude Code: plan · default · acceptEdits · bypass.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MODES = ("plan", "default", "acceptEdits", "bypass")

TOOL_SPECS = {
    "read_file": "đọc một tệp trong thư mục này",
    "list_dir": "liệt kê thư mục",
    "glob": "tìm tệp theo mẫu, ví dụ **/*.py",
    "grep": "tìm một chuỗi trong các tệp",
    "write_file": "ghi một tệp, cần bạn cho phép",
    "edit_file": "sửa một đoạn trong tệp, cần bạn cho phép",
    "multi_edit": "sửa nhiều chỗ một lượt, cần bạn cho phép",
    "delete_file": "xoá một tệp, luôn cần bạn cho phép",
    "fetch_url": "tải một trang http hoặc https, cần bạn cho phép",
    "web_search": "tìm trên web, cần bạn cho phép",
    "run_shell": "chạy một lệnh trong thư mục này, cần bạn cho phép",
    "todo_write": "ghi việc cần làm của lượt này",
    "task": "giao một việc nhỏ rồi nhận tóm tắt",
    "finish": "kết thúc và trả lời",
}

# Bộ tìm kiếm web cắm được. Khoá đọc từ biến môi trường hoặc ~/.r0/keys.json.
SEARCH_ENV = {"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY", "serper": "SERPER_API_KEY"}

TOOL_BLOCK = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.S)


def _search_key(prov: str) -> str | None:
    k = os.environ.get(SEARCH_ENV.get(prov, ""))
    if k:
        return k
    try:
        from . import keys
        return keys.get(prov)
    except Exception:                               # noqa: BLE001
        return None


def clip_result(text: str, limit: int | None = None) -> str:
    """Cắt kết quả trước khi đưa vào hội thoại. Phần bị cắt vẫn nằm trong audit."""
    from . import config as C
    cap = limit or C.TOOL_RESULT_CHARS
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n... (đã cắt, còn {len(text) - cap} ký tự)"


def _denied_path(root: Path, path: Path) -> bool:
    """Không đưa bí mật của dự án vào hội thoại."""
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return True
    if ".git" in rel.parts:
        return True
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    if name in {"id_rsa", "id_ed25519", "credentials.json"}:
        return True
    return False


def _https_block_reason(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "LỖI: chỉ nhận https"
    host = parsed.hostname
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        return "LỖI: không tải địa chỉ nội bộ"
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443)
    except socket.gaierror as e:
        return f"LỖI: {e}"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return "LỖI: không tải địa chỉ nội bộ"
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return "LỖI: không tải địa chỉ nội bộ"
    return None


class _GuardRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _https_block_reason(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(req, timeout: int = 30) -> str:
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(400_000).decode("utf-8", "replace")


def _do_search(prov: str, key: str, query: str, n: int) -> list[dict]:
    """Gọi API tìm kiếm. Tách riêng để test thay được (monkeypatch)."""
    if prov == "tavily":
        body = json.dumps({"api_key": key, "query": query, "max_results": n}).encode()
        req = urllib.request.Request("https://api.tavily.com/search", data=body, method="POST")
        req.add_header("content-type", "application/json")
        data = json.loads(_open(req))
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": (r.get("content") or "")[:300]} for r in data.get("results", [])]
    if prov == "brave":
        url = ("https://api.search.brave.com/res/v1/web/search?q="
               + urllib.parse.quote(query) + f"&count={n}")
        req = urllib.request.Request(url)
        req.add_header("X-Subscription-Token", key)
        req.add_header("Accept", "application/json")
        data = json.loads(_open(req))
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": (r.get("description") or "")[:300]}
                for r in (data.get("web", {}) or {}).get("results", [])]
    if prov == "serper":
        body = json.dumps({"q": query, "num": n}).encode()
        req = urllib.request.Request("https://google.serper.dev/search", data=body, method="POST")
        req.add_header("content-type", "application/json")
        req.add_header("X-API-KEY", key)
        data = json.loads(_open(req))
        return [{"title": r.get("title", ""), "url": r.get("link", ""),
                 "snippet": (r.get("snippet") or "")[:300]} for r in data.get("organic", [])]
    raise ValueError(f"bộ tìm lạ: {prov}")


@dataclass
class ToolEvent:
    name: str
    args: dict
    result: str
    ok: bool
    approved: bool | None = None
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {"name": self.name, "args": self.args, "ok": self.ok,
                "approved": self.approved, "seconds": round(self.seconds, 3),
                "result_preview": self.result[:400]}


@dataclass
class Session:
    """Trạng thái một phiên: quyền, lịch sử, sổ cái công cụ."""
    root: Path
    mode: str = "default"
    events: list[ToolEvent] = field(default_factory=list)
    approve: Callable[[str, dict], bool] | None = None
    audit: list[dict] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)
    depth: int = 0
    max_depth: int = 3
    spawn: Callable | None = None
    allow_always: set[str] = field(default_factory=set)
    budget_left: float | None = None
    trace: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.root = Path(self.root).resolve()

    # ------------------------------------------------------------ tiện ích
    def _resolve(self, rel: str) -> Path:
        """Khóa trong thư mục gốc, kể cả khi một symlink trỏ ra ngoài."""
        current = self.root
        for part in Path(rel).parts:
            if part in ("", "."):
                continue
            if part == "..":
                current = current.parent
            else:
                current = current / part
            if current.is_symlink():
                target = current.resolve()
                if target != self.root and self.root not in target.parents:
                    raise PermissionError(f"symlink thoát thư mục gốc: {rel}")
            if current != self.root and self.root not in current.parents:
                raise PermissionError(f"ngoài thư mục gốc: {rel}")
        p = current.resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"ngoài thư mục gốc: {rel}")
        return p

    def _grant_key(self, tool: str, args: dict) -> str:
        if tool == "run_shell":
            return "shell:" + str(args.get("cmd") or "")
        if tool == "fetch_url":
            return "url:" + str(args.get("url") or "")
        if tool == "web_search":
            return "search:" + str(args.get("query") or "")
        return tool + ":" + str(args.get("path") or "")

    def _allow(self, tool: str, args: dict) -> bool:
        """Cổng xin phép. Trả True/False — không phán đoán bằng LLM."""
        if self.mode == "bypass":
            return True
        key = self._grant_key(tool, args)
        if key in self.allow_always:
            return True
        if tool in ("write_file", "edit_file", "multi_edit") and self.mode == "acceptEdits":
            return True
        if tool in ("write_file", "edit_file", "multi_edit",
                    "run_shell", "delete_file", "fetch_url", "web_search"):
            if not self.approve:
                return False
            verdict = self.approve(tool, args)
            if verdict == "always":
                self.allow_always.add(key)
                return True
            return bool(verdict)
        return True

    def _arg_outside(self, arg: str) -> bool:
        if not arg or arg.startswith("-") or "://" in arg:
            return False
        looks_path = arg.startswith(".") or Path(arg).is_absolute() or "/" in arg or "\\" in arg
        if not looks_path:
            return False
        try:
            candidate = Path(arg)
            p = candidate.resolve() if candidate.is_absolute() else (self.root / arg).resolve()
        except OSError:
            return True
        return p != self.root and self.root not in p.parents

    # ------------------------------------------------------------- công cụ
    def read_file(self, path: str, max_bytes: int = 200_000) -> str:
        p = self._resolve(path)
        if _denied_path(self.root, p):
            return f"BỊ CHẶN: không đọc {path}."
        if not p.is_file():
            return f"LỖI: không có tệp {path}"
        b = p.read_bytes()[:max_bytes]
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return f"(tệp nhị phân, {p.stat().st_size} byte, không hiển thị)"

    def list_dir(self, path: str = ".") -> str:
        p = self._resolve(path)
        if not p.is_dir():
            return f"LỖI: không có thư mục {path}"
        out = []
        for x in sorted(p.iterdir()):
            if x.name in (".git", "__pycache__", ".venv"):
                continue
            out.append(("D " if x.is_dir() else "F ") + x.name
                       + (f"  ({x.stat().st_size}B)" if x.is_file() else ""))
        return "\n".join(out) or "(trống)"

    def grep(self, pattern: str, path: str = ".", max_hits: int = 60) -> str:
        p = self._resolve(path)
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"LỖI pattern: {e}"
        hits: list[str] = []
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in files:
            if any(s in f.parts for s in (".git", "__pycache__", ".venv")):
                continue
            if _denied_path(self.root, f):
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{f.relative_to(self.root)}:{i}: {line.strip()[:160]}")
                        if len(hits) >= max_hits:
                            return "\n".join(hits) + f"\n... (cắt ở {max_hits} kết quả)"
            except Exception:
                continue
        return "\n".join(hits) or "(không thấy)"

    def write_file(self, path: str, content: str) -> str:
        """CỬA GHI DUY NHẤT (I1). Không có đường nào khác chạm đĩa."""
        p = self._resolve(path)
        if self.mode == "plan":
            return ("BỊ CHẶN: đang ở chế độ plan — không được ghi. "
                    "Hãy trình bày đề xuất và để người dùng tự đổi chế độ.")
        if not self._allow("write_file", {"path": path, "bytes": len(content)}):
            return f"NGƯỜI DÙNG TỪ CHỐI ghi {path}."
        self._snapshot(p, "write_file")
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        self.audit.append({"action": "write_file", "path": str(p.relative_to(self.root)),
                           "bytes": len(content), "mode": self.mode, "overwrote": existed})
        return f"đã ghi {path} ({len(content)} ký tự)" + (" [ghi đè]" if existed else " [mới]")

    def glob(self, pattern: str, path: str = ".", limit: int = 200) -> str:
        base = self._resolve(path)
        if not base.is_dir():
            return f"LỖI: không có thư mục {path}"
        out: list[str] = []
        for f in sorted(base.glob(pattern or "*")):
            if any(s in f.parts for s in (".git", "__pycache__", ".venv")):
                continue
            out.append(("D " if f.is_dir() else "F ") + str(f.relative_to(self.root)))
            if len(out) >= limit:
                out.append(f"... (cắt ở {limit})")
                break
        return "\n".join(out) or "(không khớp)"

    def edit_file(self, path: str, old: str, new: str, count: int = 0) -> str:
        """Sửa tại chỗ: thay `old` bằng `new`. count=0 -> thay TẤT CẢ chỗ khớp."""
        p = self._resolve(path)
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không được sửa."
        if not p.is_file():
            return f"LỖI: không có tệp {path}"
        if not old:
            return "LỖI: thiếu `old` (đoạn cần thay)"
        text = p.read_text(encoding="utf-8")
        if old not in text:
            return f"LỖI: không thấy đoạn cần thay trong {path}"
        n_rep = min(count, text.count(old)) if count and count > 0 else text.count(old)
        if not self._allow("edit_file", {"path": path, "n": n_rep}):
            return f"NGƯỜI DÙNG TỪ CHỐI sửa {path}."
        self._snapshot(p, "edit_file")
        p.write_text(text.replace(old, new, n_rep if (count and count > 0) else -1),
                     encoding="utf-8")
        self.audit.append({"action": "edit_file", "path": str(p.relative_to(self.root)),
                           "replaced": n_rep, "mode": self.mode})
        return f"đã sửa {path}: thay {n_rep} chỗ"

    def delete_file(self, path: str) -> str:
        p = self._resolve(path)
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không xoá."
        if not p.exists():
            return f"LỖI: không có {path}"
        if p.is_dir():
            return f"LỖI: {path} là thư mục — không xoá thư mục"
        if not self._allow("delete_file", {"path": path}):
            return f"NGƯỜI DÙNG TỪ CHỐI xoá {path}."
        self._snapshot(p, "delete_file")
        p.unlink()
        self.audit.append({"action": "delete_file", "path": str(p.relative_to(self.root)),
                           "mode": self.mode})
        return f"đã xoá {path}"

    def fetch_url(self, url: str, max_bytes: int = 200_000) -> str:
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không gọi mạng."
        blocked = _https_block_reason(url)
        if blocked:
            return blocked
        if not self._allow("fetch_url", {"url": url}):
            return f"NGƯỜI DÙNG TỪ CHỐI tải {url}."
        self.audit.append({"action": "fetch_url", "url": url, "mode": self.mode})
        req = urllib.request.Request(url, headers={"user-agent": "r0-shadow/1.0"})
        opener = urllib.request.build_opener(_GuardRedirect)
        try:
            with opener.open(req, timeout=30) as r:
                return r.read(max_bytes).decode("utf-8", "replace")
        except Exception as e:                          # noqa: BLE001
            return f"LỖI: {type(e).__name__}: {e}"

    def todo_write(self, items) -> str:
        if isinstance(items, str):
            items = [items]
        self.todos = [str(x) for x in (items or [])]
        lines = [f"{i}. {t}" for i, t in enumerate(self.todos, 1)]
        return "kế hoạch:\n" + ("\n".join(lines) or "(trống)")

    def multi_edit(self, edits) -> str:
        """Sửa nhiều chỗ trong một/nhiều tệp, MỘT lượt. Kiểm HẾT trước, rồi mới ghi."""
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không được sửa."
        if not isinstance(edits, list) or not edits:
            return "LỖI: cần danh sách `edits`"
        problems: list[str] = []
        plans: list[tuple] = []
        for i, e in enumerate(edits, 1):
            if not isinstance(e, dict):
                problems.append(f"#{i}: mục không phải object")
                continue
            path, old, new = e.get("path", ""), e.get("old", ""), e.get("new", "")
            if not path or not old:
                problems.append(f"#{i}: thiếu path/old")
                continue
            p = self._resolve(path)
            if not p.is_file():
                problems.append(f"#{i}: không có tệp {path}")
                continue
            if old not in p.read_text(encoding="utf-8"):
                problems.append(f"#{i}: không thấy đoạn cần thay trong {path}")
                continue
            plans.append((p, path, old, new, int(e.get("count", 0) or 0)))
        if problems:
            return "LỖI: chưa sửa gì (kiểm trước thất bại) —\n" + "\n".join(problems)
        if not self._allow("multi_edit", {"files": len({str(p) for p, *_ in plans}),
                                          "edits": len(plans)}):
            return "NGƯỜI DÙNG TỪ CHỐI sửa nhiều chỗ."
        done = []
        for p, path, old, new, cnt in plans:
            self._snapshot(p, "multi_edit")
            text = p.read_text(encoding="utf-8")
            n = min(cnt, text.count(old)) if cnt > 0 else text.count(old)
            p.write_text(text.replace(old, new, n if cnt > 0 else -1), encoding="utf-8")
            self.audit.append({"action": "multi_edit", "path": str(p.relative_to(self.root)),
                               "replaced": n, "mode": self.mode})
            done.append(f"{path}: {n} chỗ")
        return "đã sửa:\n" + "\n".join(done)

    def web_search(self, query: str, n: int = 5, provider: str | None = None) -> str:
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không gọi mạng."
        if not query:
            return "LỖI: thiếu `query`"
        if not self._allow("web_search", {"query": query}):
            return f"NGƯỜI DÙNG TỪ CHỐI tìm: {query}"
        prov = provider or os.environ.get("R0_SEARCH_PROVIDER") or "tavily"
        if prov not in SEARCH_ENV:
            return f"LỖI: không biết bộ tìm {prov!r}; có: {', '.join(SEARCH_ENV)}"
        key = _search_key(prov)
        if not key:
            return (f"LỖI: chưa có khoá tìm kiếm cho {prov} — chạy "
                    f"`r0-shadow keys set --provider {prov}`")
        self.audit.append({"action": "web_search", "query": query,
                           "provider": prov, "mode": self.mode})
        try:
            rows = _do_search(prov, key, query, max(1, min(int(n or 5), 10)))
        except Exception as e:                      # noqa: BLE001
            return f"LỖI: {type(e).__name__}: {e}"
        if not rows:
            return "(không có kết quả)"
        return "\n".join(
            f"{i}. {r.get('title', '')}\n   {r.get('url', '')}\n   {r.get('snippet', '')}"
            for i, r in enumerate(rows, 1))

    def task(self, task: str, max_turns: int = 12, max_budget_usd=None) -> str:
        """Giao một việc cho agent CON rồi nhận tóm tắt. Có trần độ sâu."""
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không giao việc."
        if self.spawn is None:
            return "LỖI: phiên này không giao được việc cho agent con."
        if self.depth >= self.max_depth:
            return f"LỖI: chạm trần độ sâu đội con ({self.max_depth})."
        if not task:
            return "LỖI: thiếu `task`"
        res = self.spawn(task, self.depth + 1, int(max_turns or 12), max_budget_usd)
        if isinstance(res, str):
            return res
        head = f"agent con [{res.get('status')}] · {res.get('turns', 0)} lượt"
        c = res.get("costUsd")
        if c is not None:
            head += f" · ${c:.4f}"
        return head + "\n" + str(res.get("final") or res.get("error") or "(không có tóm tắt)")

    # ------------------------------------------- mốc hoàn tác · diff · ghi nhớ
    def _snapshot(self, p: Path, action: str) -> None:
        """Lưu bản TRƯỚC khi sửa, để `/undo` trả lại được."""
        before = None
        binary = False
        if p.exists() and p.is_file():
            data = p.read_bytes()
            try:
                before = data.decode("utf-8")
            except UnicodeDecodeError:
                before = data
                binary = True
        self.snapshots.append({"path": str(p.relative_to(self.root)),
                               "action": action, "before": before, "binary": binary})

    def undo_last(self) -> str:
        if not self.snapshots:
            return "chưa có thay đổi nào để hoàn tác"
        s = self.snapshots.pop()
        p = self._resolve(s["path"])
        if s["before"] is None:
            if p.exists():
                p.unlink()
            self.audit.append({"action": "undo", "path": s["path"], "mode": self.mode})
            return f"đã hoàn tác: xoá {s['path']} (tệp do agent tạo mới)"
        p.parent.mkdir(parents=True, exist_ok=True)
        if s.get("binary"):
            p.write_bytes(s["before"])
        else:
            p.write_text(s["before"], encoding="utf-8")
        self.audit.append({"action": "undo", "path": s["path"], "mode": self.mode})
        return f"đã hoàn tác: trả {s['path']} về bản trước"

    def diff_summary(self) -> str:
        if not self.snapshots:
            return "chưa sửa gì trong phiên này"
        import difflib
        rows: list[str] = []
        for s in self.snapshots:
            p = self._resolve(s["path"])
            now = p.read_text(encoding="utf-8") if p.exists() else ""
            before = s["before"] if isinstance(s["before"], str) else ""
            d = list(difflib.unified_diff(before.splitlines(),
                                          now.splitlines(), lineterm=""))
            plus = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
            minus = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
            rows.append(f"{s['path']}  +{plus} −{minus}")
        return "đã đổi trong phiên:\n" + "\n".join(rows)

    def memory_path(self) -> Path:
        return self.root / "MIRA.md"

    def load_memory(self) -> str:
        p = self.memory_path()
        try:
            return p.read_text(encoding="utf-8") if p.is_file() else ""
        except OSError:
            return ""

    def memory_for_prompt(self) -> str:
        from . import config as C
        text = self.load_memory()
        cap = C.MEMORY_PROMPT_CHARS
        if len(text) <= cap:
            return text
        return text[:cap] + "\n... (đã cắt MIRA.md — đọc tệp nếu cần phần sau)"

    def save_memory(self, text: str) -> str:
        """Ghi nhớ đi qua cùng cửa với write_file."""
        result = self.write_file("MIRA.md", text)
        if result.startswith(("BỊ CHẶN", "NGƯỜI DÙNG TỪ CHỐI", "LỖI")):
            return result
        return str(self.memory_path())

    def run_shell(self, cmd: str, timeout: int = 60) -> str:
        """Chạy đối số, không qua shell. Đối số là đường dẫn thì phải nằm trong gốc."""
        if self.mode == "plan":
            return "BỊ CHẶN: đang ở chế độ plan — không chạy lệnh."
        if not self._allow("run_shell", {"cmd": cmd}):
            return f"NGƯỜI DÙNG TỪ CHỐI chạy: {cmd}"
        try:
            argv = shlex.split(cmd, posix=True)
        except ValueError as e:
            return f"LỖI: lệnh không tách được đối số: {e}"
        if not argv:
            return "LỖI: thiếu lệnh"
        for arg in argv[1:]:
            if self._arg_outside(arg):
                return f"BỊ CHẶN: lệnh trỏ ra ngoài thư mục gốc: {arg}"
        self.audit.append({"action": "run_shell", "cmd": cmd, "mode": self.mode})
        try:
            r = subprocess.run(argv, shell=False, cwd=str(self.root), timeout=timeout,
                               capture_output=True, text=True)
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            return f"[mã thoát {r.returncode}]\n{out[:8000] or '(không có đầu ra)'}"
        except subprocess.TimeoutExpired:
            return f"LỖI: quá {timeout}s"
        except Exception as e:
            return f"LỖI: {type(e).__name__}: {e}"

    def call(self, name: str, args: dict) -> tuple[str, ToolEvent]:
        import time
        t0 = time.time()
        approved = None
        if name == "read_file":
            res = self.read_file(args.get("path", ""))
        elif name == "list_dir":
            res = self.list_dir(args.get("path", "."))
        elif name == "grep":
            res = self.grep(args.get("pattern", ""), args.get("path", "."))
        elif name == "write_file":
            res = self.write_file(args.get("path", ""), args.get("content", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN"))
        elif name == "glob":
            res = self.glob(args.get("pattern", "*"), args.get("path", "."))
        elif name == "edit_file":
            res = self.edit_file(args.get("path", ""), args.get("old", ""),
                                 args.get("new", ""), int(args.get("count", 0) or 0))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "delete_file":
            res = self.delete_file(args.get("path", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "fetch_url":
            res = self.fetch_url(args.get("url", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "todo_write":
            res = self.todo_write(args.get("items") or args.get("todos"))
        elif name == "multi_edit":
            res = self.multi_edit(args.get("edits"))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "web_search":
            res = self.web_search(args.get("query", ""), args.get("n", 5),
                                  args.get("provider"))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "task":
            res = self.task(args.get("task", ""), args.get("max_turns", 12),
                            args.get("max_budget_usd"))
        elif name == "run_shell":
            res = self.run_shell(args.get("cmd", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN"))
        else:
            res = f"LỖI: không có công cụ {name}"
        ev = ToolEvent(name=name, args=args, result=res,
                       ok=not res.startswith(("LỖI", "NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN")),
                       approved=approved, seconds=time.time() - t0)
        self.events.append(ev)
        safe = {}
        for k, v in (args or {}).items():
            if k in ("content", "new", "old"):
                safe[k] = f"({len(str(v))} ký tự)"
            else:
                safe[k] = str(v)[:120]
        self.trace.append({"tool": name, "ok": ev.ok, "args": safe})
        return res, ev


def parse_tool(text: str) -> tuple[str, dict] | None:
    """Tìm khối <tool>{...}</tool> trong đầu ra model."""
    m = TOOL_BLOCK.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        try:
            obj = json.loads(m.group(1).replace("'", '"'))
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict) or "name" not in obj:
        return None
    return str(obj["name"]), dict(obj.get("args") or {})


AGENT_SYSTEM = """Bạn là Mira — trợ lý trong terminal. Bạn vừa TRÒ CHUYỆN bình thường,
vừa làm việc trong thư mục gốc khi được giao việc.

TRÒ CHUYỆN THƯỜNG — làm được, và làm trước
- Chào hỏi, hỏi đáp, giải thích, hỏi ý kiến, hỏi kiến thức chung → trả lời TRỰC TIẾP
  bằng văn xuôi, tự nhiên, thân thiện, như một trợ lý bình thường.
- Những lượt như vậy KHÔNG cần gọi công cụ. Đừng gọi công cụ cho có.
- Chỉ gọi công cụ khi thật sự cần chạm vào tệp, chạy lệnh, hoặc tìm thông tin bên ngoài.
- Trả lời bằng đúng ngôn ngữ người dùng đang dùng.

CÔNG CỤ — mỗi lượt gọi TỐI ĐA MỘT công cụ, in đúng khối sau và không viết gì thêm:
<tool>{"name":"read_file","args":{"path":"duong/dan.txt"}}</tool>

Danh sách:
- read_file {"path"} — đọc tệp
- list_dir {"path"} — liệt kê thư mục
- glob {"pattern","path"} — tìm tệp theo mẫu (ví dụ **/*.py)
- grep {"pattern","path"} — tìm trong tệp
- write_file {"path","content"} — GHI tệp (cần người duyệt)
- edit_file {"path","old","new","count"} — SỬA tại chỗ: thay đoạn old bằng new (cần người duyệt)
- multi_edit {"edits":[{"path","old","new","count"}]} — sửa NHIỀU chỗ một lượt (cần người duyệt)
- delete_file {"path"} — XOÁ tệp (luôn cần người duyệt)
- fetch_url {"url"} — tải một URL http/https (cần người duyệt)
- web_search {"query","n"} — tìm trên web (cần người duyệt)
- run_shell {"cmd"} — CHẠY lệnh (cần người duyệt)
- todo_write {"items"} — ghi danh sách việc cần làm
- task {"task","max_turns"} — giao việc nhỏ cho agent con, nhận tóm tắt
- finish {"summary"} — kết thúc

QUY TẮC
1. Muốn biết nội dung tệp thì ĐỌC, không được bịa.
2. Sau mỗi lần gọi, bạn nhận kết quả trong một khối result. Phân tích rồi gọi tiếp hoặc finish.
3. Ghi và chạy lệnh có thể bị TỪ CHỐI — khi đó hãy giải thích và đề xuất cách khác, đừng thử lại y nguyên.
4. Không tự tạo tệp ngoài yêu cầu. Không xoá gì.
5. Khi xong việc được giao, gọi finish kèm tóm tắt. Khi chỉ trò chuyện thì trả lời thẳng,
   KHÔNG cần finish.

GHI CHÚ KỸ THUẬT: thẻ giao thức chỉ có hai là "tool" (bạn phát ra) và "result" (hệ thống trả về).
Không nhắc lại tên thẻ trong văn xuôi của bạn.
"""


def tool_catalog() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in TOOL_SPECS.items())
