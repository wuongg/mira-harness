"""Ngân sách ngữ cảnh: câu việc và hai bước cuối, không cắt im lặng."""
import unittest

from frog.team import ROLE_USER, budget_context, policy_of, role_prompt


class ContextBudgetTest(unittest.TestCase):
    def test_duoi_nguong_la_full(self):
        out = budget_context("viec ngan", ["mot buoc ngan"])
        self.assertEqual(out["policy"], "full")
        self.assertIn("mot buoc ngan", out["prev"])
        self.assertIn("viec ngan", out["task"])

    def test_buoc_cu_bi_tom_tat_giu_hai_buoc_cuoi(self):
        steps = [
            "mo dau\n" + ("x" * 40) + "BI_MAT_CU_XXXX",
            "buoc hai binh thuong",
            "MOI_B3",
            "MOI_B4",
        ]
        out = budget_context("YEU_CAU_GOC", steps)
        self.assertEqual(out["policy"], "summarized")
        blob = out["task"] + "\n" + out["prev"]
        self.assertIn("YEU_CAU_GOC", blob)
        self.assertIn("MOI_B3", blob)
        self.assertIn("MOI_B4", blob)
        self.assertIn("đã tóm tắt", blob)
        self.assertNotIn("BI_MAT_CU_XXXX", blob)

    def test_verifier_khong_thay_cat_im_lang(self):
        old = ("A" * 15000) + "BI_MAT_CU_XXXX"
        steps = [old, "giua", "MOI_B3", "MOI_B4"]
        prompt, policy = role_prompt("verifier", "YEU_CAU_GOC", steps, {})
        self.assertIn(policy, ("summarized", "truncated"))
        self.assertIn("YÊU CẦU GỐC", prompt)
        self.assertIn("YEU_CAU_GOC", prompt)
        self.assertIn("MOI_B3", prompt)
        self.assertIn("MOI_B4", prompt)
        self.assertNotIn("BI_MAT_CU_XXXX", prompt)
        self.assertTrue("đã tóm tắt" in prompt or "đã cắt theo chính sách" in prompt)
        silent = ROLE_USER["verifier"].format(task="YEU_CAU_GOC", prev="\n\n".join(steps)[:12000])
        self.assertNotIn("MOI_B3", silent)
        self.assertNotEqual(prompt, silent)

    def test_oracle_cung_cua_voi_verifier(self):
        old = ("B" * 15000) + "BI_MAT_ORACLE"
        steps = [old, "giua", "OR_B3", "OR_B4"]
        prompt, policy = role_prompt("oracle", "YEU_CAU_GOC", steps, {})
        self.assertIn(policy, ("summarized", "truncated"))
        self.assertIn("YÊU CẦU GỐC", prompt)
        self.assertIn("YEU_CAU_GOC", prompt)
        self.assertIn("OR_B3", prompt)
        self.assertIn("OR_B4", prompt)
        self.assertNotIn("BI_MAT_ORACLE", prompt)
        self.assertTrue("đã tóm tắt" in prompt or "đã cắt theo chính sách" in prompt)

    def test_trace_ghi_context_policy(self):
        self.assertEqual(policy_of({"role": "worker", "context_policy": "summarized"}), "summarized")
        self.assertEqual(policy_of({"role": "worker", "context_policy": "truncated"}), "truncated")
        self.assertEqual(policy_of({"role": "worker", "text": "trace cu"}), "full")


if __name__ == "__main__":
    unittest.main(verbosity=2)
