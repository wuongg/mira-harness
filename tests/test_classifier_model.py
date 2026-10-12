import unittest

from r0 import config as C
from r0.pipeline import classifier_cost


class ClassifierModelTest(unittest.TestCase):
    def test_classifier_is_a_real_priced_model(self):
        m = C.ROLE_MODEL["classifier"]
        self.assertIn(m, C.PRICES, "vai classifier phải dùng model có giá thật")
        self.assertNotIn("jev", m.lower())

    def test_jev_constants_removed(self):
        self.assertFalse(hasattr(C, "JEV_PRICE"))
        self.assertFalse(hasattr(C, "JEV_CLASSIFIER_TOKENS"))
        self.assertTrue(hasattr(C, "CLASSIFIER_TOKENS"))

    def test_classifier_cost_is_positive(self):
        self.assertGreater(classifier_cost(C.CLASSIFIER_TOKENS), 0.0)

    def test_no_jev_symbol_anywhere(self):
        import r0.pipeline as P
        self.assertFalse(hasattr(P, "jev_cost"))


if __name__ == "__main__":
    unittest.main()
