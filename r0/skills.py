"""Skill mở từng tầng, bản đồ ký hiệu, trí nhớ việc đã kiểm.

Catalog chỉ có tên và mô tả. Thân SKILL.md chỉ trả khi gọi đúng một skill.
Bản đồ Python lấy từ ast, cache theo thời điểm sửa file, trần khoảng 1000 token.
Fact chỉ được ghi khi verifier đã PASS.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

MAP_TOKEN_CAP = 1000
FACT_CHAR_CAP = 800
_SKIP = {".git", "__pycache__", ".venv", ".mira"}


def estimate_tokens(text: str) -> int:
    """Ước lượng token bằng độ dài chữ. Không kéo tokenizer ngoài."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end < 0:
        return {}, raw
    meta: dict[str, str] = {}
    for line in raw[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    body = raw[end + 4:].lstrip("\n")
    return meta, body


def load_skills(root: Path) -> list[dict]:
    """Đọc catalog. Mỗi phần tử có name, description, body. Body không đưa vào prompt."""
    base = Path(root) / ".mira" / "skills"
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.glob("*/SKILL.md")):
        meta, body = _frontmatter(path.read_text(encoding="utf-8"))
        name = meta.get("name") or path.parent.name
        if name != path.parent.name:
            continue
        desc = meta.get("description") or ""
        if not desc:
            continue
        out.append({"name": name, "description": desc, "body": body.strip()})
    return out


def catalog_text(skills: list[dict]) -> str:
    lines = [f"- {s['name']}: {s['description']}" for s in skills]
    return "SKILL (chỉ tên và lúc nào dùng):\n" + "\n".join(lines)


def skill_body(root: Path, name: str) -> str | None:
    for skill in load_skills(root):
        if skill["name"] == name:
            return skill["body"]
    return None


def parse_skill_line(text: str) -> list[str]:
    """Planner ghi một dòng SKILLS: a, b. Tên lạ bị bỏ ở chỗ gọi."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("SKILLS:"):
            rest = stripped.split(":", 1)[1]
            return [part.strip() for part in rest.split(",") if part.strip()]
    return []


def _py_symbols(src: str) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: list[str] = []

    def _args(node: ast.AST) -> str:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ""
        names = [a.arg for a in node.args.args]
        return ", ".join(names)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"def {node.name}({_args(node)})")
        elif isinstance(node, ast.ClassDef):
            out.append(f"class {node.name}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(f"  def {item.name}({_args(item)})")
    return out


def repo_map(root: Path, task: str = "") -> str:
    """Bản đồ file, hàm, lớp, chữ ký. File đổi thì chỉ tính lại file đó."""
    root = Path(root)
    cache_path = root / ".mira" / "map.json"
    cache: dict = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    files: dict[str, dict] = {}
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIP for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        mtime = path.stat().st_mtime
        old = cache.get(rel) if isinstance(cache.get(rel), dict) else None
        if old and old.get("mtime") == mtime and isinstance(old.get("symbols"), list):
            symbols = old["symbols"]
        else:
            symbols = _py_symbols(path.read_text(encoding="utf-8", errors="replace"))
        files[rel] = {"mtime": mtime, "symbols": symbols}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
    words = {w.lower() for w in re.findall(r"\w{3,}", task or "")}
    ordered = sorted(files, key=lambda rel: (0 if any(w in rel.lower() for w in words) else 1, rel))
    lines: list[str] = []
    for rel in ordered:
        block = [rel] + [f"  {sym}" for sym in files[rel]["symbols"]]
        trial = "\n".join(lines + block)
        if lines and estimate_tokens(trial) > MAP_TOKEN_CAP:
            break
        lines.extend(block)
        if estimate_tokens("\n".join(lines)) > MAP_TOKEN_CAP:
            break
    return "\n".join(lines)


def remember_fact(root: Path, task: str, text: str) -> None:
    """Ghi một dòng việc đã kiểm. Chỉ chỗ verifier PASS được gọi hàm này."""
    bit = (text or "").strip()
    if not bit:
        return
    path = Path(root) / ".mira" / "facts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"task": (task or "")[:200], "text": bit[:400]}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def recall_facts(root: Path, task: str, cap: int = FACT_CHAR_CAP) -> str:
    """Lấy vài dòng có từ trùng câu việc, có trần ký tự."""
    path = Path(root) / ".mira" / "facts.jsonl"
    if not path.is_file():
        return ""
    want = {w.lower() for w in re.findall(r"\w{3,}", task or "")}
    scored: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        blob = f"{rec.get('task', '')} {rec.get('text', '')}"
        score = len(want & {w.lower() for w in re.findall(r"\w{3,}", blob)})
        if score:
            scored.append((score, str(rec.get("text") or "").strip()))
    scored.sort(key=lambda item: -item[0])
    out: list[str] = []
    used = 0
    for _score, bit in scored:
        if not bit or used + len(bit) > cap:
            break
        out.append(bit)
        used += len(bit) + 1
    return "\n".join(out)


def context_block(root: Path, task: str) -> str:
    """Phần thêm vào prompt: catalog, bản đồ, fact. Không có thân skill."""
    parts: list[str] = []
    skills = load_skills(root)
    if skills:
        cat = catalog_text(skills)
        parts.append(cat + f"\n(catalog: {len(skills)} skill, {estimate_tokens(cat)} token)")
    mapped = repo_map(root, task)
    if mapped:
        parts.append("BẢN ĐỒ KÝ HIỆU:\n" + mapped)
    facts = recall_facts(root, task)
    if facts:
        parts.append("VIỆC ĐÃ KIỂM:\n" + facts)
    return "\n\n".join(parts)
