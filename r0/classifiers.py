"""Bộ phân loại T1b CẮM ĐƯỢC — chọn bằng tham số dòng lệnh, không sửa code.

    --classifier keyword   dò từ khoá tất định (miễn phí, mặc định)
    --classifier llm       gọi model đọc nội dung (cần API key)

Cả hai trả về CÙNG một dạng kết quả nên phần còn lại của đường ống không đổi, và
hai chế độ so được với nhau trên cùng một thước.

Ranh giới I3 vẫn nguyên: cả hai chỉ là BỘ DÒ, không sinh nhãn. Prompt gửi model
CHỈ chứa nội dung — không chứa `truth`. Có test khẳng định điều này.

Cache: kết quả model được lưu theo (provider, model, hash nội dung). Chạy lại cùng
bộ tác vụ KHÔNG tính tiền lần hai, và số đo vẫn tái lập được.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import config as C
from .detect import DETECT_SYSTEM, DETECT_USER, build_provider, parse_verdict
from .pipeline import t1b_classifier


def _shape(raised: bool, conf: float, evidence: list[str], model: str,
           decided_by: str, **extra) -> dict[str, Any]:
    d = {"choice": "nghi ngờ cao" if conf >= 0.85 else ("nghi ngờ" if raised else "bình thường"),
         "confidence": round(conf, 4), "raised": raised,
         "evidence": evidence, "n_evidence": len(evidence),
         "model": model, "decided_by": decided_by}
    d.update(extra)
    return d


class KeywordClassifier:
    """Dò từ khoá tất định — mặc định, miễn phí, không cần mạng."""

    name = "keyword"
    model = None

    def __init__(self) -> None:
        self.calls = 0
        self.errors = 0
        self.cache_hits = 0
        self.cost_usd = 0.0

    def classify(self, t: Any) -> dict[str, Any]:
        self.calls += 1
        return t1b_classifier(t)


class LLMClassifier:
    """Model đọc nội dung. Chỉ TƯ VẤN, chỉ NÂNG mức nghi ngờ (I5)."""

    name = "llm"

    def __init__(self, provider, cache_dir: str | Path | None = None) -> None:
        self.provider = provider
        self.model = provider.model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.errors = 0
        self.cache_hits = 0
        self.cost_usd = 0.0

    # ------------------------------------------------------------- cache
    def _key(self, t: Any) -> str:
        content = t.observable.get("content", "")
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"{self.provider.name}-{self.model}-{h}"

    def _cache_path(self, key: str) -> Path | None:
        return (self.cache_dir / f"{key}.json") if self.cache_dir else None

    # ---------------------------------------------------------- phân loại
    def classify(self, t: Any) -> dict[str, Any]:
        key = self._key(t)
        p = self._cache_path(key)
        if p and p.exists():
            try:
                cached = json.loads(p.read_text(encoding="utf-8"))
                self.calls += 1
                self.cache_hits += 1
                return {**cached, "cached": True}
            except Exception:                       # noqa: BLE001 — cache hỏng thì gọi lại
                pass

        self.calls += 1
        try:
            text, usage = self.provider.call(
                DETECT_SYSTEM, DETECT_USER.format(content=t.observable.get("content", "")))
        except Exception as e:                      # noqa: BLE001 — lỗi mạng/HTTP
            self.errors += 1
            return _shape(False, 0.5, [], self.model, "llm-error", error=str(e)[:200])

        v = parse_verdict(text)
        price = C.PRICES.get(self.model)
        cost = ((usage.get("in", 0) * price["in"] + usage.get("out", 0) * price["out"]) / 1e6
                if price else 0.0)
        self.cost_usd += cost
        evidence = [v["rationale"]] if v.get("rationale") else []
        out = _shape(v["detected"], v["confidence"], evidence, self.model, "llm-read",
                     malformed=v["malformed"], cost_usd=round(cost, 8),
                     tokens={"in": usage.get("in", 0), "out": usage.get("out", 0)},
                     cached=False)
        if p:
            try:
                p.write_text(json.dumps({k: x for k, x in out.items() if k != "cached"},
                                        ensure_ascii=False), encoding="utf-8")
            except Exception:                       # noqa: BLE001
                pass
        return out

    def summary(self) -> dict[str, Any]:
        return {"mode": self.name, "model": self.model, "provider": self.provider.name,
                "calls": self.calls, "cache_hits": self.cache_hits, "errors": self.errors,
                "cost_usd": round(self.cost_usd, 6),
                "priced": self.model in C.PRICES}


def build_classifier(mode: str = "keyword", *, provider_name: str | None = None,
                     model: str | None = None, base_url: str | None = None,
                     api_key: str | None = None,
                     cache_dir: str | Path | None = None) -> tuple[Any, str | None]:
    """Dựng bộ phân loại theo tham số. Trả (đối tượng, thông báo lỗi hoặc None).

    Cố ý KHÔNG tự hạ về `keyword` khi thiếu key: hạ âm thầm sẽ làm bảng số trông
    như đo bằng model trong khi thật ra đo bằng code — một lời nói dối về đo lường.
    """
    if mode == "keyword":
        return KeywordClassifier(), None
    if mode != "llm":
        return None, f"không biết classifier {mode!r}; có: keyword, llm"

    model = model or C.ROLE_MODEL["classifier"]
    try:
        prov = build_provider(provider_name, model, base_url, api_key)
    except Exception as e:                          # noqa: BLE001
        return None, f"không dựng được provider: {e}"
    if not prov.available():
        key = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
               "xai": "XAI_API_KEY"}.get(prov.name, "API key")
        return None, (f"cần API key cho {prov.name} — đặt biến môi trường {key} "
                      f"hoặc truyền --api-key")
    return LLMClassifier(prov, cache_dir=cache_dir), None
