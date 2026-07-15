import unittest
from datetime import date

from mithrandir.viability import compute_viability


class TestViability(unittest.TestCase):
    def test_bate_com_a_planilha(self):
        v = compute_viability([131, 111, 0, 226, 230, 140], today=date(2026, 2, 2))
        self.assertEqual(v["total"], 838)
        self.assertEqual(v["per_day"], 4.7)
        self.assertEqual(v["receita_mes"], 13952.70)
        self.assertEqual(v["unit_margin"], 96.74)
        self.assertEqual(v["qtd_breakeven"], 229)
        self.assertAlmostEqual(v["breakeven_weeks"], 7.04, places=1)

    def test_variacao_mensal(self):
        v = compute_viability([131, 111, 0, 226, 230, 140], today=date(2026, 2, 2))
        moms = [m["mom"] for m in v["months"]]
        self.assertEqual(moms, [None, -15, -100, "div0", 2, -39])

    def test_labels_ultimos_6_meses(self):
        v = compute_viability([1, 2, 3, 4, 5, 6], today=date(2026, 7, 9))
        labels = [m["label"] for m in v["months"]]
        self.assertEqual(labels, ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho"])

    def test_vazio(self):
        self.assertEqual(compute_viability([]), {})


if __name__ == "__main__":
    unittest.main()
