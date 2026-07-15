import tempfile
import unittest
from pathlib import Path

from mithrandir import settings as st


class TestSettings(unittest.TestCase):
    def test_defaults_quando_vazio(self):
        with tempfile.TemporaryDirectory() as d:
            s = st.load_settings(Path(d) / "s.json")
            self.assertEqual(s["case_price"], 99.90)
            self.assertEqual(s["scouting_frequency"], "diaria")

    def test_save_merge_e_ignora_chaves_invalidas(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            saved = st.save_settings({"case_price": 120, "mold_cost": 30000,
                                      "hack": "x"}, p)
            self.assertEqual(saved["case_price"], 120.0)
            self.assertEqual(saved["mold_cost"], 30000.0)
            self.assertNotIn("hack", saved)
            self.assertEqual(saved["unit_cost"], 3.16)  # default preservado
            self.assertEqual(st.load_settings(p)["case_price"], 120.0)

    def test_coercao_numerica(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            saved = st.save_settings({"unit_cost": "5.5", "history_months": "6"}, p)
            self.assertEqual(saved["unit_cost"], 5.5)
            self.assertEqual(saved["history_months"], 6)


if __name__ == "__main__":
    unittest.main()
