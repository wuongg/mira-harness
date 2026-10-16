"""200 kịch bản seed cố định. Chỉ assert I1, I2, I3, I5, I8."""
import json
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from frog.providers import ProviderError
from frog.team import ROLES_BY_LANE, Ledger, _executor_write, build_plan, execute_plan

_PASS = json.dumps({"verdict": "PASS", "reasons": ["đủ"], "evidence": [], "confidence": 1})
_ORACLE_LOW = json.dumps({"verdict": "PASS", "reasons": ["thấp"], "evidence": [],
                          "confidence": 1, "score": 0.4})
_ORACLE_OK = json.dumps({"verdict": "PASS", "reasons": ["đủ"], "evidence": [],
                         "confidence": 1, "score": 0.9})
SEED = 20261013


def _specs(seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for _ in range(200):
        out.append({
            "workers": rng.choice([1, 2, 3]),
            "depth": rng.choice([0, 1]),
            "fail": rng.choice(["verifier", "oracle", "none"]),
            "boom": rng.choice([False, True]),
            "priced": rng.choice([True, False]),
            "surface": rng.choice(["read_only", "write_sandbox", "write_external"]),
            "edit": rng.choice([False, True]),
        })
    return out


class _Prov:
    name = "anthropic"

    def __init__(self, spec: dict):
        self.spec = spec
        self.n = 0

    def available(self) -> bool:
        return True

    def call(self, system, user, **_k):
        self.n += 1
        if self.spec["boom"] and self.n == 2:
            raise ProviderError("đứt giữa chừng")
        if "VERIFIER" in system and self.spec["fail"] == "verifier":
            return "không phải json", {"in": 1, "out": 1}
        if "ORACLE" in system and self.spec["fail"] == "oracle":
            return _ORACLE_LOW, {"in": 1, "out": 1}
        if "VERIFIER" in system:
            return _PASS, {"in": 1, "out": 1}
        if "ORACLE" in system:
            return _ORACLE_OK, {"in": 1, "out": 1}
        return "1. bước", {"in": 1, "out": 1}


def _turn(task, session, **_k):
    (Path(session.root) / "app.py").write_text("changed\n", encoding="utf-8")
    return {"final": "xong", "usage": {"in": 1, "out": 1}, "seconds": 0.0}


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


class FuzzTest(unittest.TestCase):
    def test_seed_lap_lai_cung_thu_tu(self):
        self.assertEqual(_specs(SEED), _specs(SEED))
        self.assertEqual(len(_specs(SEED)), 200)

    def test_charge_muoi_luong_nam_nghin(self):
        ledger = Ledger()
        price = {"in": 1.0, "out": 1.0}

        def work() -> None:
            for _ in range(5000):
                ledger.charge("worker", "sonnet-5.5", {"in": 1_000_000, "out": 0},
                              "trap", price=price, price_source="file")

        threads = [threading.Thread(target=work) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ledger.rows), 50_000)
        self.assertEqual(ledger.total_usd, 50_000.0)
        self.assertEqual(ledger.summary()["total_usd"], 50_000.0)

    def test_hai_tram_kich_ban_seed_co_dinh(self):
        original = Path.write_text
        for index, spec in enumerate(_specs(SEED)):
            with self.subTest(index=index, **spec):
                self._one(spec, original)

    def _one(self, spec: dict, original) -> None:
        writes: list[Path] = []

        def wrapped(self_path, data, *args, **kwargs):
            writes.append(Path(self_path).resolve())
            return original(self_path, data, *args, **kwargs)

        task = ("sửa app.py cho gọn. Đây là public data"
                if spec["edit"] else "soạn báo cáo. Đây là public data")
        records, dollars = (5000, 3000.0) if spec["surface"] == "write_external" else (50, 0.0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            out = Path(tmp) / "out"
            root.mkdir()
            (root / "app.py").write_text("old\n", encoding="utf-8")
            (root / "secret.txt").write_text("giu\n", encoding="utf-8")
            before = (root / "secret.txt").read_bytes()
            plan = build_plan(task, surface=spec["surface"], labels=["internal"],
                              records=records, dollars=dollars)
            lane = plan.lane
            prov = _Prov(spec)
            with patch("frog.team.provider_for", lambda *a, **k: prov), \
                 patch("frog.agent.run_turn", _turn), \
                 patch.object(Path, "write_text", wrapped):
                res = execute_plan(
                    plan, root=root, workers=spec["workers"], depth=spec["depth"],
                    oracle="on", model_override=None if spec["priced"] else "khong-co",
                    on_step=lambda _m: None)
                if res["status"] == "ok":
                    _executor_write(out, plan, res)
                else:
                    out.mkdir(parents=True, exist_ok=True)
                    (out / "withheld.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual((root / "secret.txt").read_bytes(), before)
            staging = (root / ".frog").resolve()
            for path in writes:
                if _under(path, staging):
                    continue
                if _under(path, out):
                    if res["status"] != "ok":
                        self.assertEqual(path.name, "withheld.json")
                    continue
                self.assertFalse(_under(path, root), path)
            if res["status"] != "ok":
                self.assertEqual(res["promoted"], [])
            self.assertEqual(plan.task.observable["data_labels"], ["internal"])
            self.assertEqual(plan.task.observable["tool_surface"], spec["surface"])
            expected_roles = list(ROLES_BY_LANE[lane])
            if lane == 2:
                expected_roles.append("oracle")
            self.assertEqual(list(plan.roles), expected_roles)
            if lane < 2:
                self.assertFalse(any(step.get("sub") for step in res["steps"]))
            if not spec["priced"]:
                self.assertEqual(prov.n, 0)
                self.assertEqual(res["status"], "blocked")
            elif spec["boom"] and prov.n >= 2:
                self.assertNotEqual(res["status"], "ok")
                self.assertEqual(res["promoted"], [])
            elif lane >= 1 and spec["fail"] == "verifier":
                self.assertNotEqual(res["status"], "ok")
            elif lane == 2 and spec["fail"] == "oracle":
                self.assertEqual(res["status"], "withheld")
            self.assertLessEqual(res["ledger"]["total_usd"], plan.cap_usd + 1e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
