"""Đặt lệnh `frog` vào PATH — gõ ở terminal nào cũng vào phiên.

Giống Claude Code: cài một lần, mở terminal mới, gõ `frog` là vào.
Launcher `.cmd` gọi module Python, không tạo file exe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def render_shim(root: Path) -> str:
    """Nội dung launcher. Windows: file .cmd. Hệ khác: script shell."""
    root_s = str(root).rstrip("\\/")
    if os.name == "nt":
        return (
            "@echo off\r\n"
            "setlocal\r\n"
            f'set "PYTHONPATH={root_s}"\r\n'
            "where python >nul 2>&1\r\n"
            "if %ERRORLEVEL%==0 goto :py\r\n"
            "where py >nul 2>&1\r\n"
            "if %ERRORLEVEL%==0 goto :py_launcher\r\n"
            "echo Python was not found. Install Python 3.9+ and turn on Add to PATH.\r\n"
            "exit /b 1\r\n"
            ":py\r\n"
            "python -m frog %*\r\n"
            "exit /b %ERRORLEVEL%\r\n"
            ":py_launcher\r\n"
            "py -3 -m frog %*\r\n"
            "exit /b %ERRORLEVEL%\r\n"
        )
    escaped = root_s.replace("'", "'\\''")
    return (
        "#!/bin/sh\n"
        f"export PYTHONPATH='{escaped}'${{PYTHONPATH:+:$PYTHONPATH}}\n"
        "if command -v python3 >/dev/null 2>&1; then\n"
        '  exec python3 -m frog "$@"\n'
        "fi\n"
        "if command -v python >/dev/null 2>&1; then\n"
        '  exec python -m frog "$@"\n'
        "fi\n"
        'echo "Python was not found. Install Python 3.9+." >&2\n'
        "exit 1\n"
    )


def shim_name() -> str:
    return "frog.cmd" if os.name == "nt" else "frog"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(path)))


def _has_dir(path_value: str, directory: str) -> bool:
    target = _norm(directory)
    return any(part and _norm(part) == target for part in path_value.split(os.pathsep))


def ensure_user_path(directory: Path) -> tuple[bool, bool, str]:
    """Thêm `directory` vào đầu PATH của người dùng.

    Trả (đã sửa, đang có trên PATH, lỗi). Trên Windows ghi vào registry người dùng
    để terminal mới thấy, không đụng PATH của máy.
    """
    directory = directory.resolve()
    dir_s = str(directory)
    if os.name == "nt":
        return _ensure_windows_path(dir_s)
    return _ensure_posix_path(dir_s)


def _ensure_windows_path(directory: str) -> tuple[bool, bool, str]:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                             winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except OSError as e:
        return False, False, f"không mở được PATH người dùng: {e}"
    try:
        try:
            current, typ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, typ = "", winreg.REG_EXPAND_SZ
        current = current or ""
        if _has_dir(current, directory):
            return False, True, ""
        updated = directory if not current.strip() else directory + os.pathsep + current
        winreg.SetValueEx(key, "Path", 0, typ, updated)
    except OSError as e:
        return False, False, f"không ghi được PATH: {e}"
    finally:
        winreg.CloseKey(key)
    _broadcast_env()
    os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
    return True, True, ""


def _broadcast_env() -> None:
    try:
        import ctypes
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))
    except Exception:
        pass


def _ensure_posix_path(directory: str) -> tuple[bool, bool, str]:
    current = os.environ.get("PATH", "")
    if _has_dir(current, directory):
        return False, True, ""
    rc = Path.home() / ".profile"
    line = f'\n# frog\nexport PATH="{directory}:$PATH"\n'
    try:
        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if directory not in text:
            rc.write_text(text + line, encoding="utf-8")
    except OSError as e:
        return False, False, f"không ghi được {rc}: {e}"
    os.environ["PATH"] = directory + os.pathsep + current
    return True, True, ""


def install(root: Path | None = None, dest_dir: Path | None = None,
            update_path: bool = True) -> dict:
    """Ghi launcher và (mặc định) thêm thư mục của nó vào PATH."""
    root = (root or package_root()).resolve()
    dest = (dest_dir or default_bin_dir()).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    shim = dest / shim_name()
    shim.write_bytes(render_shim(root).encode("utf-8"))
    if os.name != "nt":
        shim.chmod(0o755)
    updated, on_path, err = (False, False, "")
    if update_path:
        updated, on_path, err = ensure_user_path(dest)
    return {"shim": shim, "bin_dir": dest, "root": root,
            "path_updated": updated, "on_path": on_path, "error": err,
            "python": sys.executable}
