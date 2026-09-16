"""Curva de largada: os PRIMEIROS 6 meses de venda da capinha, nao os ultimos."""
import unittest
from unittest import mock

from mithrandir import store
from mithrandir.collectors import case_sales

# Recorte real do site, com os dois casos que importam: SKU duplicado do mesmo
# aparelho (iPhone 15 Pro Max vem em duas linhas) e produto que nao e celular.
ROWS = [
    {"name": "iPhone 16", "primeiro_mes": "2024-09-01",
     "serie": [122, 659, 1412, 1183, 905, 703]},
    {"name": "iPhone 15 Pro Max", "primeiro_mes": "2023-09-01",
     "serie": [1064, 2857, 4422, 3542, 3303, 3778]},
    {"name": "iPhone 15 Pro Max", "primeiro_mes": "2023-09-01",
     "serie": [269, 298, 373, 236, 149, 148]},
    {"name": "Ecobag Duocolor", "primeiro_mes": "2026-03-01", "serie": [10, 5]},
]


class TestParse(unittest.TestCase):
    def test_serie_de_largada_por_modelo(self):
        out = case_sales.parse_rows(ROWS)
        self.assertEqual(out["APPLE 16"]["serie"], [122, 659, 1412, 1183, 905, 703])
        self.assertEqual(out["APPLE 16"]["m0"], "2024-09-01")

    def test_skus_do_mesmo_aparelho_e_mesmo_mes_somam(self):
        out = case_sales.parse_rows(ROWS)
        self.assertEqual(out["APPLE 15 PRO MAX"]["serie"],
                         [1333, 3155, 4795, 3778, 3452, 3926])

    def test_janelas_diferentes_nao_somam_fica_a_maior(self):
        # somar series que comecam em meses diferentes inventaria uma curva
        rows = [{"name": "iPhone 16", "primeiro_mes": "2024-09-01", "serie": [100, 200]},
                {"name": "iPhone 16", "primeiro_mes": "2025-01-01", "serie": [10, 20]}]
        out = case_sales.parse_rows(rows)
        self.assertEqual(out["APPLE 16"]["serie"], [100, 200])
        self.assertEqual(out["APPLE 16"]["m0"], "2024-09-01")

    def test_corta_em_6_meses(self):
        rows = [{"name": "iPhone 16", "primeiro_mes": "2024-09-01",
                 "serie": [1, 2, 3, 4, 5, 6, 7, 8]}]
        self.assertEqual(len(case_sales.parse_rows(rows)["APPLE 16"]["serie"]),
                         case_sales.MESES)

    def test_o_que_nao_e_celular_fica_de_fora(self):
        fora = []
        out = case_sales.parse_rows(ROWS, descartados=fora)
        self.assertNotIn("ECOBAG DUOCOLOR", out)
        self.assertEqual(len(fora), 1)

    def test_entrada_invalida_nao_quebra(self):
        self.assertEqual(case_sales.parse_rows([]), {})
        self.assertEqual(case_sales.parse_rows(None), {})
        self.assertEqual(case_sales.parse_rows([{"name": "iPhone 16"}]), {})   # sem serie


class TestUsoNaViabilidade(unittest.TestCase):
    """A serie de largada tem que chegar ao breakeven; sem ela, cai nos ultimos 6."""

    def setUp(self):
        self.mem = {}
        for nome, fn in (("get_cached", self.mem.get),
                         ("set_cached", lambda k, v: self.mem.__setitem__(k, v))):
            p = mock.patch.object(store, nome, fn)
            p.start()
            self.addCleanup(p.stop)

    def _similar(self):
        from mithrandir.internal_bi import find_similar
        from mithrandir.normalize import canonicalize
        recs = [{"canonical_model": "APPLE 16", "brand": "APPLE", "family": "APPLE #",
                 "generation": 16, "units": 1000, "revenue": 0.0, "margin_pct": 0.0,
                 "sell_through_pct": 0.0, "device": "iPhone 16"}]
        with mock.patch("mithrandir.internal_bi.load_monthly_sales",
                        return_value={"APPLE 16": [9, 9, 9, 9, 9, 9]}):
            return find_similar(canonicalize("iPhone 17"), recs)

    def test_usa_a_largada_quando_existe(self):
        case_sales.ingest(ROWS)
        s = self._similar()
        self.assertEqual(s.monthly_sales, [122, 659, 1412, 1183, 905, 703])
        self.assertTrue(s.monthly_from_launch)

    def test_sem_largada_cai_nos_ultimos_6_meses(self):
        s = self._similar()
        self.assertEqual(s.monthly_sales, [9, 9, 9, 9, 9, 9])
        self.assertFalse(s.monthly_from_launch)

    def test_ingest_vazio_e_recusado(self):
        with self.assertRaises(ValueError):
            case_sales.ingest([])


if __name__ == "__main__":
    unittest.main()
