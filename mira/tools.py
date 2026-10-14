"""Công cụ cho agent — có cổng xin phép, có Executor là cửa ghi duy nhất.

Mọi đường dẫn bị khoá trong thư mục gốc. Ghi và chạy lệnh phải qua cổng.
Chế độ quyền giống Claude Code: plan · default · acceptEdits · bypass.
"""
from __future__ import annotations

import ast
import difflib
import ipaddress
import json
import os
import py_compile
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_SHELL_CAP = 8000


@dataclass
class ShellResult:
    """Kết quả lệnh, tách khỏi chuỗi hiển thị."""
    permission: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False
    display: str = ""


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= _SHELL_CAP:
        return text, False
    return text[:_SHELL_CAP], True


def _shell_display(result: ShellResult) -> str:
    if result.display:
        return result.display
    if result.timed_out:
        return "LỖI: quá thời gian"
    if result.exit_code is None:
        return "LỖI: không có mã thoát"
    if not (result.stdout or "").strip() and not (result.stderr or "").strip():
        body = "lệnh chạy xong, không có đầu ra."
    else:
        body = result.stdout or ""
        if result.stderr:
            body += "\n[stderr]\n" + result.stderr
        body = body[:_SHELL_CAP]
    return f"[mã thoát {result.exit_code}]\n{body}"


MODES = ("plan", "default", "acceptEdits", "bypass")


def _shell_env() -> dict:
    """Bản sao môi trường đã bỏ khóa API. Process con không được thấy khóa."""
    from .keys import ENV
    banned = set(ENV.values())
    return {name: value for name, value in os.environ.items()
            if name not in banned and not name.endswith("_API_KEY")}

_MEDIUM = {"write_file", "edit_file", "multi_edit"}
_HIGH = {"delete_file", "run_shell", "fetch_url", "web_search", "task",
        "install_skill", "mcp_list", "mcp_call"}


def risk_of(tool: str) -> str:
    """Mức rủi ro của một công cụ. Không quyết định có hỏi người dùng hay không."""
    if tool in _HIGH:
        return "high"
    if tool in _MEDIUM:
        return "medium"
    return "low"


def needs_confirm(mode: str, risk: str) -> bool:
    """Chính sách duyệt. plan từ chối trước khi tới đây."""
    if mode in ("bypass", "plan") or risk == "low":
        return False
    if mode == "acceptEdits" and risk == "medium":
        return False
    return True


def observable_for_tool(tool: str) -> dict:
    """Nguồn cho t1a_policy. Không lấy từ lời model."""
    obs = {"tool_surface": "read_only", "reversibility": "C1",
           "records": 0, "dollars": 0, "data_labels": [], "output_type": "enum"}
    if tool in ("write_file", "edit_file", "multi_edit"):
        obs["tool_surface"] = "write_sandbox"
        obs["reversibility"] = "C2"
    elif tool in ("delete_file", "run_shell", "fetch_url", "web_search", "task",
                  "install_skill", "mcp_list", "mcp_call"):
        obs["tool_surface"] = "egress_new"
        obs["reversibility"] = "C3"
    return obs


class _LaneSource:
    def __init__(self, observable: dict):
        self.observable = observable


def shape_of(task: str) -> str:
    """Khối do câu việc quyết. Kết quả tool không được đổi khối này."""
    text = task or ""
    write = re.search(r"sửa|đổi|ghi|thành", text, re.IGNORECASE) is not None
    named = "https://" in text or re.search(
        r"[\w./\\-]+\.(?:py|txt|md|json|toml|ini|yml|yaml|cfg|csv)\b", text) is not None
    command = re.search(r"\b(?:python|pytest)\b", text) is not None
    read = re.search(r"đọc|tóm tắt|giải thích", text, re.IGNORECASE) is not None
    if write and named:
        return "edit"
    if command and not write:
        return "run"
    if read and named:
        return "read"
    return "ask"


def lane_for_tool(tool: str, untrusted: bool = False) -> int:
    """Làn của tool. Skill đã mở thì sàn nội dung không tin được cộng như build_plan."""
    from .pipeline import dynamic_floor, t1a_policy
    obs = observable_for_tool(tool)
    lane = int(t1a_policy(_LaneSource(obs))["lane_base"])
    if not untrusted:
        return lane
    richer = dict(obs)
    richer["untrusted_content"] = True
    richer["isolation_proven_by_code"] = False
    richer["isolation_sound"] = False
    richer["isolation_hash_logged"] = False
    floor = dynamic_floor(_LaneSource(richer), {"probation_ok": False})
    if floor["floor"] >= 2:
        lane = max(lane, int(floor["floor"]) - 1)
    return lane


_MUTATIONS = ("write_file", "edit_file", "multi_edit", "delete_file", "run_shell")
_WRITES = ("write_file", "edit_file", "multi_edit")


def _ignore_workspace(_dir: str, names: list[str]) -> list[str]:
    skip = []
    for name in names:
        if name in (".git", "__pycache__", ".venv") or name == ".env" or name.startswith(".env."):
            skip.append(name)
    return skip


def _split_shell(cmd: str) -> list[str]:
    """Tách lệnh như run_shell. Trên Windows, đường dẫn có '\\' được thử lại."""
    argv = shlex.split(cmd, posix=True)
    if os.name != "nt" or not argv or _shell_token_runs(argv[0]):
        return argv
    alt = [_strip_shell_quotes(token) for token in shlex.split(cmd, posix=False)]
    if alt and _shell_token_runs(alt[0]):
        return alt
    return argv


def _shell_token_runs(token: str) -> bool:
    return Path(token).is_file() or shutil.which(token) is not None


def _strip_shell_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _shell_argv(work: Path, argv: list[str]) -> list[str]:
    """Linux có bwrap thì cắt mạng và chỉ cho ghi trong bản sao."""
    bwrap = shutil.which("bwrap") if sys.platform.startswith("linux") else None
    if not bwrap:
        return argv
    return [
        bwrap, "--unshare-net", "--die-with-parent",
        "--ro-bind", "/", "/",
        "--bind", str(work), str(work),
        "--chdir", str(work),
        "--",
        *argv,
    ]

TOOL_SPECS = {
    "read_file": "đọc một cửa sổ dòng trong tệp (mặc định 100 dòng, có số dòng)",
    "list_dir": "liệt kê thư mục",
    "glob": "tìm tệp theo mẫu, ví dụ **/*.py",
    "grep": "liệt kê tệp khớp và số lần, không đổ nội dung dòng",
    "write_file": "ghi một tệp, cần bạn cho phép",
    "edit_file": "sửa một đoạn trong tệp, cần bạn cho phép",
    "multi_edit": "sửa nhiều chỗ một lượt, cần bạn cho phép",
    "delete_file": "xoá một tệp, luôn cần bạn cho phép",
    "fetch_url": "tải một trang http hoặc https, cần bạn cho phép",
    "web_search": "tìm trên web, cần bạn cho phép",
    "install_skill": "tải một SKILL.md qua https và cài vào catalog, cần bạn cho phép",
    "mcp_list": "xem tool của một server MCP https, cần bạn cho phép",
    "mcp_call": "gọi một tool MCP https, kết quả là dữ liệu không tin, cần bạn cho phép",
    "run_shell": "chạy một lệnh trong thư mục này, cần bạn cho phép",
    "todo_write": "ghi việc cần làm của lượt này",
    "task": "giao một việc nhỏ rồi nhận tóm tắt",
    "plan_skills": "ghi thứ tự skill sẽ mở, không đọc thân",
    "use_skill": "mở đúng một thân skill đã có trong catalog",
    "read_skill_file": "đọc một file kèm của skill đã mở, không chạy script",
    "finish": "kết thúc và trả lời",
}

# Bộ tìm kiếm web cắm được. Khoá đọc từ biến môi trường hoặc ~/.mira/keys.json.
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
        rel = path.resolve().relative_to(root.resolve())
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


def _python_syntax(source: str) -> str | None:
    """Kiểm cú pháp trong bộ nhớ tạm. Lỗi thì không cho ghi."""
    fd, name = tempfile.mkstemp(suffix=".py")
    cfile = name + "c"
    try:
        os.write(fd, source.encode("utf-8"))
        os.close(fd)
        fd = -1
        py_compile.compile(name, cfile=cfile, doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)
    finally:
        if fd >= 0:
            os.close(fd)
        for leftover in (name, cfile):
            try:
                os.unlink(leftover)
            except OSError:
                pass


def _short_diff(before: str, after: str, limit: int = 30) -> str:
    lines = list(difflib.unified_diff(
        (before or "").splitlines(), (after or "").splitlines(), lineterm=""))
    if not lines:
        return ""
    return "\n".join(lines[:limit])


def _symbol_line(source: str, name: str, suffix: str = ".py") -> int | None:
    if suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                return node.lineno
        return None
    if suffix == ".go":
        pattern = rf"func\s+(?:\([^)]*\)\s*)?{re.escape(name)}\b"
    else:
        pattern = rf"(?:function|class)\s+{re.escape(name)}\b"
    for index, line in enumerate(source.splitlines(), 1):
        if re.search(pattern, line):
            return index
    return None


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
    if prov == "ddg":
        return _do_search_ddg(query, n)
    raise ValueError(f"bộ tìm lạ: {prov}")


def parse_search_html(html: str, n: int) -> list[dict]:
    """Lấy link https từ trang kết quả. Không chạy gì trong trang."""
    rows: list[dict] = []
    for match in re.finditer(r'href="([^"]+)"[^>]*>(.*?)</a>', html or "", re.S):
        url = urllib.parse.unquote(match.group(1))
        if "uddg=" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = (query.get("uddg") or [url])[0]
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if not url.startswith("https://") or not title:
            continue
        rows.append({"title": title, "url": url, "snippet": ""})
        if len(rows) >= n:
            break
    return rows


def _https_text(url: str, limit: int) -> str:
    blocked = _https_block_reason(url)
    if blocked:
        return blocked
    req = urllib.request.Request(url, headers={"user-agent": "mira/1.0"})
    opener = urllib.request.build_opener(_GuardRedirect)
    try:
        with opener.open(req, timeout=30) as response:
            return response.read(limit).decode("utf-8", "replace")
    except Exception as e:                          # noqa: BLE001
        return f"LỖI: {type(e).__name__}: {e}"


def _mcp_text(result: dict) -> str:
    from .skills import UNTRUSTED_MARK
    tools = result.get("tools")
    if isinstance(tools, list):
        lines = []
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                lines.append(f"- {tool.get('name')}: {tool.get('description') or ''}")
        body = "\n".join(lines) or "(không có tool)"
        return f"{UNTRUSTED_MARK}\n{body}"
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    body = "\n".join(parts).strip() or json.dumps(result, ensure_ascii=False)[:2000]
    return f"{UNTRUSTED_MARK}\n{body[:8000]}"


def _mcp_rpc(url: str, method: str, params: dict) -> str:
    """JSON-RPC qua https. Không chạy server trên máy này."""
    blocked = _https_block_reason(url)
    if blocked:
        return blocked
    opener = urllib.request.build_opener(_GuardRedirect)
    session = ""

    def post(payload: dict) -> dict:
        nonlocal session
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("content-type", "application/json")
        req.add_header("accept", "application/json, text/event-stream")
        if session:
            req.add_header("mcp-session-id", session)
        with opener.open(req, timeout=30) as response:
            session = response.headers.get("mcp-session-id") or session
            raw = response.read(200_000).decode("utf-8", "replace")
        data = _mcp_payload(raw)
        if data.get("error"):
            message = data["error"].get("message") if isinstance(data["error"], dict) else data["error"]
            raise RuntimeError(str(message))
        result = data.get("result")
        return result if isinstance(result, dict) else {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}

    try:
        post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "mira", "version": "0"}}})
        result = post({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
    except Exception as e:                          # noqa: BLE001
        return f"LỖI: {type(e).__name__}: {e}"
    return _mcp_text(result)


def _mcp_payload(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            bit = line[5:].strip()
            if bit and bit != "[DONE]":
                return json.loads(bit)
    return {}


def _do_search_ddg(query: str, n: int) -> list[dict]:
    url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    html = _https_text(url, 400_000)
    if html.startswith("LỖI"):
        raise RuntimeError(html)
    return parse_search_html(html, n)


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
    lane_seen: int = 0
    checker: Callable[[], bool] | None = None
    stop_layer: str = "governance"
    skill_plan: list[str] = field(default_factory=list)
    skills_opened: list[str] = field(default_factory=list)
    skill_caps: dict = field(default_factory=dict)
    task_text: str = ""
    saw_untrusted: bool = False
    shape: str = ""
    gate_task: str = ""
    role_tools: set | None = None
    child_spent: float = 0.0
    recruited: bool = False
    role_system: str = ""
    halt: bool = False

    def __post_init__(self):
        self.root = Path(self.root).resolve()

    def log_event(self, kind: str, **fields) -> None:
        """Sổ sự kiện gắn thêm. Không sửa dòng đã ghi."""
        row: dict[str, Any] = {"kind": kind}
        for key, value in fields.items():
            if isinstance(value, str) and key not in ("content", "summary") and len(value) > 400:
                value = value[:400] + "…"
            row[key] = value
        self.trace.append(row)

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
        """Hỏi người dùng khi chính sách bảo hỏi. Không tự chọn tool nào phải hỏi."""
        if not needs_confirm(self.mode, risk_of(tool)):
            return True
        key = self._grant_key(tool, args)
        if key in self.allow_always:
            return True
        if not self.approve:
            return False
        verdict = self.approve(tool, args)
        if verdict == "always":
            self.allow_always.add(key)
            return True
        return bool(verdict)

    def _permit(self, tool: str, args: dict, refusal: str) -> str | None:
        """None là được làm. plan chặn mọi việc không ở mức thấp, trước khi hỏi."""
        frozen = self._freeze_block(tool, args)
        if frozen:
            self.stop_layer = "governance"
            return frozen
        lane = lane_for_tool(tool, untrusted=bool(self.skills_opened))
        if self.mode == "plan" and risk_of(tool) != "low":
            self.stop_layer = "governance"
            return "BỊ CHẶN: đang ở chế độ plan — không được làm việc này."
        if not self._allow(tool, args):
            self.stop_layer = "governance"
            return refusal
        self.lane_seen = max(self.lane_seen, lane)
        return None

    def _grader_path(self, path: str) -> bool:
        name = Path(str(path).replace("\\", "/")).name
        return name in {"conftest.py", "pytest.ini", "tox.ini", "sitecustomize.py"} or (
            name.startswith("test_") and name.endswith(".py"))

    def _targets_of(self, tool: str, args: dict) -> list[str]:
        if tool == "fetch_url":
            url = str(args.get("url") or "")
            return [url] if url else []
        if tool in ("run_shell", "multi_edit"):
            return [str(p) for p in (args.get("paths") or []) if p]
        path = str(args.get("path") or "")
        return [path] if path else []

    def _freeze_block(self, tool: str, args: dict) -> str | None:
        """Dữ liệu vừa đọc không được mở path lạ. File người chấm không bị sửa."""
        targets = self._targets_of(tool, args)
        task = self.task_text or ""
        for target in targets:
            if self._grader_path(target) and target not in task:
                return f"BỊ CHẶN: không sửa file người chấm {target}."
        shaped = self._shape_block(tool, args)
        if shaped:
            return shaped
        if self._task_names_file() and tool in (
                "write_file", "edit_file", "multi_edit", "delete_file", "run_shell", "fetch_url"):
            if not (tool == "run_shell" and not targets):
                for target in targets:
                    if target not in task:
                        return f"BỊ CHẶN: {target} không có trong câu việc."
        for target in targets:
            if self._in_skill_tree(target) and target not in task:
                return "BỊ CHẶN: không ghi vào .mira/skills."
        if not self.saw_untrusted:
            return None
        if tool not in ("write_file", "edit_file", "multi_edit", "delete_file", "run_shell", "fetch_url"):
            return None
        if tool == "run_shell" and not targets:
            return "BỊ CHẶN: sau dữ liệu không tin, lệnh không có path trong câu việc."
        for target in targets:
            if target not in task:
                return f"BỊ CHẶN: sau dữ liệu không tin, {target} không có trong câu việc."
        return self._content_block(tool, args)

    def _in_skill_tree(self, target: str) -> bool:
        norm = str(target or "").replace("\\", "/")
        return norm == ".mira/skills" or norm.startswith(".mira/skills/") or "/.mira/skills/" in f"/{norm}"

    def _content_block(self, tool: str, args: dict) -> str | None:
        """Sau dữ liệu không tin, chữ mới phải chứa cụm đứng sau thành."""
        if tool not in ("write_file", "edit_file", "multi_edit"):
            return None
        found = re.search(r"thành\s+(.+?)(?:\s+trong\b|$)", self.task_text or "", re.I)
        if not found:
            return None
        need = found.group(1).strip().strip(".")
        if not need:
            return None
        if tool == "write_file":
            blobs = [str(args.get("content") or "")]
        elif tool == "edit_file":
            blobs = [str(args.get("new") or "")]
        else:
            blobs = [str(item) for item in (args.get("news") or [])]
        if any(need not in blob for blob in blobs):
            return "BỊ CHẶN: nội dung sửa không có cụm sau thành."
        return None

    def _shape_block(self, tool: str, args: dict) -> str | None:
        """Dạng đọc và hỏi không ghi. Dạng chạy không ghi. Shell phải nằm trong câu việc."""
        shape = self.shape or ""
        if not shape:
            return None
        writes = {"write_file", "edit_file", "multi_edit", "delete_file"}
        if shape in ("read", "ask") and tool in writes | {"run_shell", "fetch_url"}:
            return f"BỊ CHẶN: dạng {shape} không làm {tool}."
        if shape == "run" and tool in writes | {"fetch_url", "web_search"}:
            return f"BỊ CHẶN: dạng chạy không làm {tool}."
        if shape in ("edit", "run") and tool == "run_shell":
            cmd = str(args.get("cmd") or "")
            if not cmd or cmd not in (self.task_text or ""):
                return "BỊ CHẶN: lệnh không có trong câu việc."
        return None

    def _task_names_file(self) -> bool:
        """Câu việc đã nêu một file hoặc URL thì path khác không được tự thêm."""
        task = self.task_text or ""
        if "https://" in task:
            return True
        return re.search(
            r"[\w./\\-]+\.(?:py|txt|md|json|toml|ini|yml|yaml|cfg|csv)\b", task) is not None

    def _skill_ceiling(self, tool: str) -> str | None:
        """Skill đã khai trần thì tool ngoài trần bị chặn trước khi hỏi và trước khi nâng làn."""
        from .skills import _HARNESS_TOOLS
        if tool in _HARNESS_TOOLS:
            return None
        caps = [self.skill_caps[name] for name in self.skills_opened
                if isinstance(self.skill_caps.get(name), set)]
        if not caps:
            return None
        allowed: set[str] = set.intersection(*caps)
        if tool in allowed:
            return None
        return f"BỊ CHẶN: skill đang mở không cho phép {tool}."

    def _role_block(self, tool: str) -> str | None:
        """Vai được tuyển chỉ gọi tool đã khai. Trần trống thì không thêm khóa."""
        from .skills import _HARNESS_TOOLS
        allowed = self.role_tools
        if not allowed or tool in _HARNESS_TOOLS or tool in allowed:
            return None
        return f"BỊ CHẶN: vai này không được gọi {tool}."

    def accept_finish(self) -> tuple[bool, str]:
        """finish là lời xin. Làn quyết định sổ phải có tác dụng gì."""
        mutated = any(a.get("action") in _MUTATIONS for a in self.audit)
        if self.lane_seen <= 0:
            if mutated:
                self.stop_layer = "verification"
                return False, "làn 0 nhưng sổ đã có thay đổi"
            self.stop_layer = "governance"
            return True, "xong"
        if self.lane_seen == 1:
            wrote = any(a.get("action") in _WRITES for a in self.audit)
            if not wrote:
                self.stop_layer = "verification"
                return False, "làn 1 chưa có lần ghi hoặc sửa"
            self.stop_layer = "governance"
            return True, "xong"
        if self.checker is None:
            self.stop_layer = "verification"
            return False, "làn 2 thiếu kiểm chứng"
        try:
            ok = bool(self.checker())
        except Exception as e:
            self.stop_layer = "verification"
            return False, f"kiểm chứng lỗi: {type(e).__name__}"
        if not ok:
            self.stop_layer = "verification"
            return False, "kiểm chứng chưa đúng"
        self.stop_layer = "verification"
        return True, "xong"

    def _arg_outside(self, arg: str) -> bool:
        if not arg or arg.startswith("-") or "://" in arg:
            return False
        # Dấu \ cũng là thoát thư mục. Trên Linux Path không cắt \, nên PE02 lọt.
        normalized = arg.replace("\\", "/")
        looks_path = (
            normalized.startswith(".")
            or Path(normalized).is_absolute()
            or "/" in normalized
        )
        if not looks_path:
            return False
        try:
            candidate = Path(normalized)
            p = candidate.resolve() if candidate.is_absolute() else (self.root / normalized).resolve()
        except OSError:
            return True
        return p != self.root and self.root not in p.parents

    def _unopened_skill_arg(self, arg: str) -> str | None:
        """Path trong .mira/skills/<tên> khi tên chưa mở. None nếu không chặn."""
        if not arg or arg.startswith("-") or "://" in arg:
            return None
        looks_path = arg.startswith(".") or Path(arg).is_absolute() or "/" in arg or "\\" in arg
        if not looks_path:
            return None
        try:
            candidate = Path(arg)
            p = candidate.resolve() if candidate.is_absolute() else (self.root / arg).resolve()
        except OSError:
            return None
        skills_root = (self.root / ".mira" / "skills").resolve()
        if p != skills_root and skills_root not in p.parents:
            return None
        try:
            rel = p.relative_to(skills_root)
        except ValueError:
            return None
        name = rel.parts[0] if rel.parts else ""
        if not name or name not in self.skills_opened:
            return f"BỊ CHẶN: script của skill {name or '(trống)'} chưa mở."
        return None

    # ------------------------------------------------------------- công cụ
    def plan_skills(self, names) -> str:
        """Ghi thứ tự skill. Không nạp thân."""
        from .skills import load_skills
        catalog = {s["name"] for s in load_skills(self.root)}
        if isinstance(names, str):
            names = [part.strip() for part in names.split(",") if part.strip()]
        clean = []
        for name in names or []:
            name = str(name).strip()
            if name not in catalog:
                return f"LỖI: không có skill {name}"
            clean.append(name)
        if not clean:
            return "LỖI: chưa có tên skill"
        self.skill_plan = clean
        self.skills_opened = []
        self.skill_caps = {}
        return "thứ tự skill: " + ", ".join(clean)

    def use_skill(self, name: str) -> str:
        """Trả đúng một thân. Tên lạ bị từ chối. Có kế hoạch thì chỉ mở skill kế tiếp."""
        from .skills import load_skills
        wanted = (name or "").strip()
        found = next((s for s in load_skills(self.root) if s["name"] == wanted), None)
        if found is None:
            return f"LỖI: không có skill {wanted}"
        if self.skill_plan:
            idx = len(self.skills_opened)
            nxt = self.skill_plan[idx] if idx < len(self.skill_plan) else ""
            if wanted != nxt:
                return f"LỖI: chưa tới skill {wanted}. Tiếp theo là {nxt or 'hết'}."
        self.skills_opened.append(wanted)
        self.skill_caps[wanted] = found.get("allowed")
        self.log_event("skill_open", name=wanted, layer="tool")
        self.log_event("skill_untrusted", name=wanted, layer="tool")
        from .skills import UNTRUSTED_MARK, skill_file_names
        names = skill_file_names(self.root, wanted)
        listing = ", ".join(names) if names else "(không)"
        return UNTRUSTED_MARK + "\n" + found["body"] + "\nfile kèm: " + listing

    def read_skill_file(self, name: str, path: str) -> str:
        """Đọc một file trong scripts, references hoặc assets của skill đã mở."""
        from .skills import resolve_skill_file
        wanted = (name or "").strip()
        if wanted not in self.skills_opened:
            return f"LỖI: skill {wanted or '(trống)'} chưa mở"
        target = resolve_skill_file(self.root, wanted, path or "")
        if target is None:
            return "LỖI: không đọc file này"
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"(tệp nhị phân, {target.stat().st_size} byte, không hiển thị)"
        return text

    def read_file(self, path: str, start: int = 1, n: int = 100,
                  max_bytes: int = 200_000, symbol: str = "") -> str:
        """Cửa sổ dòng, có số dòng. `symbol` nhảy tới hàm trong bản đồ ast."""
        p = self._resolve(path)
        if _denied_path(self.root, p):
            return f"BỊ CHẶN: không đọc {path}."
        skills_root = (self.root / ".mira" / "skills").resolve()
        if p == skills_root or skills_root in p.parents:
            return "BỊ CHẶN: file skill chỉ mở bằng use_skill hoặc read_skill_file."
        if not p.is_file():
            return f"LỖI: không có tệp {path}"
        raw = p.read_bytes()[:max_bytes]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self.saw_untrusted = True
            return f"(tệp nhị phân, {p.stat().st_size} byte, không hiển thị)"
        lines = text.splitlines()
        total = len(lines)
        if symbol:
            line_no = _symbol_line(text, symbol, p.suffix)
            if line_no is None:
                return f"LỖI: không thấy {symbol} trong {path}"
            start = line_no
        self.saw_untrusted = True
        if total == 0:
            return f"{path}  dòng 0 / 0\n(trống)"
        begin = max(1, int(start or 1))
        width = int(n or 100)
        if width <= 0:
            width = 100
        if begin > total:
            return f"LỖI: {path} chỉ có {total} dòng, không có dòng {begin}"
        chunk = lines[begin - 1:begin - 1 + width]
        end = begin + len(chunk) - 1
        head = f"{path}  dòng {begin}-{end} / {total}"
        if end < total:
            head += f"  (còn {total - end} dòng, đọc tiếp từ {end + 1})"
        body = "\n".join(f"{begin + i}|{line}" for i, line in enumerate(chunk))
        return head + "\n" + body

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
        self.saw_untrusted = True
        return "\n".join(out) or "(trống)"

    def grep(self, pattern: str, path: str = ".", max_hits: int = 60) -> str:
        """Mặc định chỉ tên tệp và số lần khớp. Đoạn chữ thì đọc bằng read_file."""
        p = self._resolve(path)
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"LỖI pattern: {e}"
        counts: dict[str, int] = {}
        seen = 0
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in files:
            if any(s in f.parts for s in (".git", "__pycache__", ".venv")):
                continue
            if _denied_path(self.root, f):
                continue
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if rx.search(line):
                        rel = str(f.relative_to(self.root))
                        counts[rel] = counts.get(rel, 0) + 1
                        seen += 1
                        if seen >= max_hits:
                            break
            except Exception:
                continue
            if seen >= max_hits:
                break
        if not counts:
            self.saw_untrusted = True
            return "(không thấy)"
        rows = [f"{name}  {n} chỗ" for name, n in counts.items()]
        if seen >= max_hits:
            rows.append(f"... (cắt ở {max_hits} kết quả)")
        self.saw_untrusted = True
        return "\n".join(rows)

    def write_file(self, path: str, content: str) -> str:
        """CỬA GHI DUY NHẤT (I1). Không có đường nào khác chạm đĩa."""
        p = self._resolve(path)
        denied = self._permit("write_file", {"path": path, "bytes": len(content), "content": content},
                              f"NGƯỜI DÙNG TỪ CHỐI ghi {path}.")
        if denied:
            return denied
        self._snapshot(p, "write_file")
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        self.audit.append({"action": "write_file", "path": str(p.relative_to(self.root)),
                           "bytes": len(content), "mode": self.mode, "overwrote": existed})
        return f"đã ghi {path} ({len(content)} ký tự)" + (" [ghi đè]" if existed else " [mới]") + _short_diff("", content)

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
        """Sửa tại chỗ: thay `old` bằng `new`. Nhiều chỗ khớp mà không nêu count thì lỗi."""
        p = self._resolve(path)
        if not p.is_file():
            return f"LỖI: không có tệp {path}"
        if not old:
            return "LỖI: thiếu `old` (đoạn cần thay)"
        text = p.read_text(encoding="utf-8")
        hits = text.count(old)
        if old not in text:
            return f"LỖI: không thấy đoạn cần thay trong {path}"
        if (not count or int(count) <= 0) and hits > 1:
            return "LỖI: đoạn cần thay khớp nhiều chỗ."
        n_rep = min(count, hits) if count and count > 0 else hits
        updated = text.replace(old, new, n_rep if (count and count > 0) else 1)
        if p.suffix == ".py":
            err = _python_syntax(updated)
            if err:
                return f"LỖI: cú pháp Python trong {path}: {err}"
        denied = self._permit("edit_file", {"path": path, "n": n_rep, "new": new},
                              f"NGƯỜI DÙNG TỪ CHỐI sửa {path}.")
        if denied:
            return denied
        self._snapshot(p, "edit_file")
        p.write_text(updated, encoding="utf-8")
        self.audit.append({"action": "edit_file", "path": str(p.relative_to(self.root)),
                           "replaced": n_rep, "mode": self.mode})
        return f"đã sửa {path}: thay {n_rep} chỗ\n{_short_diff(text, updated)}\n{self.diff_summary()}"

    def delete_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"LỖI: không có {path}"
        if p.is_dir():
            return f"LỖI: {path} là thư mục — không xoá thư mục"
        denied = self._permit("delete_file", {"path": path}, f"NGƯỜI DÙNG TỪ CHỐI xoá {path}.")
        if denied:
            return denied
        self._snapshot(p, "delete_file")
        p.unlink()
        self.audit.append({"action": "delete_file", "path": str(p.relative_to(self.root)),
                           "mode": self.mode})
        return f"đã xoá {path}"

    def fetch_url(self, url: str, max_bytes: int = 200_000) -> str:
        blocked = _https_block_reason(url)
        if blocked:
            return blocked
        denied = self._permit("fetch_url", {"url": url}, f"NGƯỜI DÙNG TỪ CHỐI tải {url}.")
        if denied:
            return denied
        self.audit.append({"action": "fetch_url", "url": url, "mode": self.mode})
        req = urllib.request.Request(url, headers={"user-agent": "r0-shadow/1.0"})
        opener = urllib.request.build_opener(_GuardRedirect)
        try:
            with opener.open(req, timeout=30) as r:
                body = r.read(max_bytes).decode("utf-8", "replace")
        except Exception as e:                          # noqa: BLE001
            return f"LỖI: {type(e).__name__}: {e}"
        self.saw_untrusted = True
        return body

    def todo_write(self, items) -> str:
        if isinstance(items, str):
            items = [items]
        self.todos = [str(x) for x in (items or [])]
        lines = [f"{i}. {t}" for i, t in enumerate(self.todos, 1)]
        return "kế hoạch:\n" + ("\n".join(lines) or "(trống)")

    def multi_edit(self, edits) -> str:
        """Sửa nhiều chỗ trong một/nhiều tệp, MỘT lượt. Kiểm HẾT trước, rồi mới ghi."""
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
        prepared: list[tuple] = []
        for p, path, old, new, cnt in plans:
            text = p.read_text(encoding="utf-8")
            if cnt <= 0 and text.count(old) > 1:
                return "LỖI: đoạn cần thay khớp nhiều chỗ."
            n = min(cnt, text.count(old)) if cnt > 0 else text.count(old)
            updated = text.replace(old, new, n if cnt > 0 else 1)
            if p.suffix == ".py":
                err = _python_syntax(updated)
                if err:
                    return f"LỖI: cú pháp Python trong {path}: {err}"
            prepared.append((p, path, updated, n))
        denied = self._permit("multi_edit",
                              {"paths": [path for _p, path, _u, _n in prepared],
                               "news": [new for _p, _path, _old, new, _cnt in plans]},
                              "NGƯỜI DÙNG TỪ CHỐI sửa nhiều chỗ.")
        if denied:
            return denied
        done = []
        for p, path, updated, n in prepared:
            self._snapshot(p, "multi_edit")
            p.write_text(updated, encoding="utf-8")
            self.audit.append({"action": "multi_edit", "path": str(p.relative_to(self.root)),
                               "replaced": n, "mode": self.mode})
            done.append(f"{path}: {n} chỗ")
        return "đã sửa:\n" + "\n".join(done)

    def web_search(self, query: str, n: int = 5, provider: str | None = None) -> str:
        if not query:
            return "LỖI: thiếu `query`"
        denied = self._permit("web_search", {"query": query}, f"NGƯỜI DÙNG TỪ CHỐI tìm: {query}")
        if denied:
            return denied
        prov = provider or os.environ.get("R0_SEARCH_PROVIDER") or "tavily"
        if prov not in SEARCH_ENV and prov != "ddg":
            return f"LỖI: không biết bộ tìm {prov!r}; có: {', '.join(SEARCH_ENV)}, ddg"
        if prov in SEARCH_ENV and not _search_key(prov):
            if provider:
                return (f"LỖI: chưa có khoá tìm kiếm cho {prov} — chạy "
                        f"`r0-shadow keys set --provider {prov}`")
            prov = "ddg"
        key = _search_key(prov) if prov in SEARCH_ENV else ""
        self.audit.append({"action": "web_search", "query": query,
                           "provider": prov, "mode": self.mode})
        try:
            rows = _do_search(prov, key, query, max(1, min(int(n or 5), 10)))
        except Exception as e:                      # noqa: BLE001
            return f"LỖI: {type(e).__name__}: {e}"
        if not rows:
            return "(không có kết quả)"
        self.saw_untrusted = True
        return "\n".join(
            f"{i}. {r.get('title', '')}\n   {r.get('url', '')}\n   {r.get('snippet', '')}"
            for i, r in enumerate(rows, 1))

    def install_skill(self, url: str) -> str:
        """Cài đúng một SKILL.md. Không tải script, không ghi đè skill đã có."""
        from .skills import UNTRUSTED_MARK, skill_document, skill_dir
        blocked = _https_block_reason(url)
        if blocked:
            return blocked
        denied = self._permit("install_skill", {"url": url}, f"NGƯỜI DÙNG TỪ CHỐI cài skill {url}.")
        if denied:
            return denied
        text = _https_text(url, 32_000)
        if text.startswith("LỖI"):
            return text
        self.saw_untrusted = True
        parsed = skill_document(text)
        if isinstance(parsed, str):
            return parsed
        name, desc, stored = parsed
        dest = skill_dir(self.root, name)
        if dest.exists():
            return f"LỖI: skill {name} đã có, không ghi đè."
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(stored, encoding="utf-8")
        self.audit.append({"action": "install_skill", "path": f".mira/skills/{name}/SKILL.md",
                           "url": url, "mode": self.mode})
        return (f"{UNTRUSTED_MARK}\nđã cài skill {name}: {desc}\n"
                "Mở bằng use_skill. Không có script kèm theo.")

    def mcp_list(self, url: str) -> str:
        denied = self._permit("mcp_list", {"url": url}, f"NGƯỜI DÙNG TỪ CHỐI MCP {url}.")
        if denied:
            return denied
        text = _mcp_rpc(url, "tools/list", {})
        self.saw_untrusted = True
        return text

    def mcp_call(self, url: str, tool: str, arguments=None) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", tool or ""):
            return "LỖI: tên tool MCP không hợp lệ."
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return "LỖI: arguments phải là object."
        denied = self._permit("mcp_call", {"url": url, "tool": tool},
                              f"NGƯỜI DÙNG TỪ CHỐI gọi MCP {tool}.")
        if denied:
            return denied
        text = _mcp_rpc(url, "tools/call", {"name": tool, "arguments": arguments})
        self.saw_untrusted = True
        return text

    def task(self, task: str, max_turns: int = 12, max_budget_usd=None) -> str:
        """Giao một việc cho agent CON rồi nhận tóm tắt. Có trần độ sâu."""
        if self.spawn is None:
            return "LỖI: phiên này không giao được việc cho agent con."
        if self.depth >= self.max_depth:
            return f"LỖI: chạm trần độ sâu đội con ({self.max_depth})."
        if not task:
            return "LỖI: thiếu `task`"
        denied = self._permit("task", {"task": task}, "NGƯỜI DÙNG TỪ CHỐI giao việc.")
        if denied:
            return denied
        res = self.spawn(task, self.depth + 1, int(max_turns or 12), max_budget_usd)
        if isinstance(res, str):
            return res
        self.child_spent += float(res.get("costUsd") or 0)
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
        """Chuỗi hiển thị cũ. Dữ liệu nằm ở run_shell_result."""
        return self.run_shell_result(cmd, timeout=timeout).display

    def run_shell_result(self, cmd: str, timeout: int = 60) -> ShellResult:
        """Chạy đối số trong bản sao. Không ghi ngược vào cây nguồn.

        Thư mục làm việc là bản sao, không phải sandbox. Không có cô lập tiến trình.
        """
        try:
            argv = _split_shell(cmd)
        except ValueError as e:
            return ShellResult("error", display=f"LỖI: lệnh không tách được đối số: {e}")
        if not argv:
            return ShellResult("error", display="LỖI: thiếu lệnh")
        for arg in argv[1:]:
            blocked = self._unopened_skill_arg(arg)
            if blocked:
                return ShellResult("blocked", display=blocked)
        paths = [arg for arg in argv[1:] if arg and not arg.startswith("-")
                 and ("/" in arg or "\\" in arg or "." in arg)]
        denied = self._permit("run_shell", {"cmd": cmd, "paths": paths},
                              f"NGƯỜI DÙNG TỪ CHỐI chạy: {cmd}")
        if denied:
            return ShellResult("denied", display=denied)
        for arg in argv[1:]:
            if self._arg_outside(arg):
                return ShellResult("blocked", display=f"BỊ CHẶN: lệnh trỏ ra ngoài thư mục gốc: {arg}")
        row = {"action": "run_shell", "cmd": cmd, "mode": self.mode, "exit": None}
        self.audit.append(row)
        work = Path(tempfile.mkdtemp(prefix="mira-sh-"))
        try:
            shutil.copytree(self.root, work, dirs_exist_ok=True, ignore=_ignore_workspace)
            try:
                r = subprocess.run(_shell_argv(work, argv), shell=False, cwd=str(work),
                                   timeout=timeout, capture_output=True, text=True,
                                   env=_shell_env())
            except subprocess.TimeoutExpired as expired:
                stdout, cut_out = _clip(_as_text(expired.stdout))
                stderr, cut_err = _clip(_as_text(expired.stderr))
                return ShellResult(
                    "granted", stdout=stdout, stderr=stderr,
                    timed_out=True, truncated=cut_out or cut_err,
                    display=f"LỖI: quá {timeout}s")
            row["exit"] = r.returncode
            stdout, cut_out = _clip(r.stdout or "")
            stderr, cut_err = _clip(r.stderr or "")
            self.saw_untrusted = True
            result = ShellResult(
                "granted", exit_code=r.returncode, stdout=stdout, stderr=stderr,
                truncated=cut_out or cut_err)
            result.display = _shell_display(result)
            return result
        except Exception as e:
            return ShellResult("error", display=f"LỖI: {type(e).__name__}: {e}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def call(self, name: str, args: dict) -> tuple[str, ToolEvent]:
        import time
        t0 = time.time()
        approved = None
        ceiling = self._skill_ceiling(name)
        role_block = self._role_block(name)
        if ceiling or role_block:
            res = ceiling or role_block
            approved = False
        elif name == "read_file":
            res = self.read_file(args.get("path", ""),
                                 start=int(args.get("start") or 1),
                                 n=int(args.get("n") or 100),
                                 symbol=str(args.get("symbol") or ""))
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
        elif name == "install_skill":
            res = self.install_skill(args.get("url", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "mcp_list":
            res = self.mcp_list(args.get("url", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "mcp_call":
            res = self.mcp_call(args.get("url", ""), args.get("tool", ""), args.get("arguments"))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN", "LỖI"))
        elif name == "task":
            res = self.task(args.get("task", ""), args.get("max_turns", 12),
                            args.get("max_budget_usd"))
        elif name == "run_shell":
            res = self.run_shell(args.get("cmd", ""))
            approved = not res.startswith(("NGƯỜI DÙNG TỪ CHỐI", "BỊ CHẶN"))
        elif name == "plan_skills":
            res = self.plan_skills(args.get("names") or [])
        elif name == "use_skill":
            res = self.use_skill(args.get("name", ""))
        elif name == "read_skill_file":
            res = self.read_skill_file(args.get("name", ""), args.get("path", ""))
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
        self.log_event("tool_call", tool=name, args=safe, layer="tool")
        layer = "tool"
        if res.startswith(("BỊ CHẶN", "NGƯỜI DÙNG TỪ CHỐI")):
            layer = "governance"
        if approved is not None:
            self.log_event("gate", tool=name, allowed=bool(approved), layer=layer)
        self.log_event("tool_result", tool=name, ok=ev.ok, text=clip_result(res), layer=layer)
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
- read_file {"path","start","n","symbol"} — đọc cửa sổ dòng (mặc định 100 dòng, có số dòng). symbol nhảy tới hàm. Hết cửa sổ thì gọi lại với start tiếp theo.
- list_dir {"path"} — liệt kê thư mục
- glob {"pattern","path"} — tìm tệp theo mẫu (ví dụ **/*.py)
- grep {"pattern","path"} — liệt kê tệp khớp và số lần. Muốn đọc đoạn thì gọi read_file.
- write_file {"path","content"} — GHI tệp (cần người duyệt)
- edit_file {"path","old","new","count"} — SỬA tại chỗ: thay đoạn old bằng new (cần người duyệt)
- multi_edit {"edits":[{"path","old","new","count"}]} — sửa NHIỀU chỗ một lượt (cần người duyệt)
- delete_file {"path"} — XOÁ tệp (luôn cần người duyệt)
- fetch_url {"url"} — tải một URL http/https (cần người duyệt)
- web_search {"query","n"} — tìm trên web (cần người duyệt). Không có khoá tìm thì dùng DuckDuckGo.
- install_skill {"url"} — tải một SKILL.md https vào catalog (cần người duyệt). Không tải script.
- mcp_list {"url"} — xem tool của server MCP https (cần người duyệt).
- mcp_call {"url","tool","arguments"} — gọi một tool MCP. Kết quả là dữ liệu không tin, không thêm công cụ.
- run_shell {"cmd"} — CHẠY lệnh (cần người duyệt)
- todo_write {"items"} — ghi danh sách việc cần làm
- task {"task","max_turns"} — giao việc nhỏ cho agent con, nhận tóm tắt
- plan_skills {"names"} — ghi thứ tự skill, chưa đọc thân
- use_skill {"name"} — mở đúng một thân skill trong catalog, kèm tên file đi theo
- read_skill_file {"name","path"} — đọc một file trong scripts, references hoặc assets của skill đã mở
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
