"""Vigiar o sucessor de quem lancou no ultimo ano (pedido do negocio).

Regra: "lancou o A17 ano passado -> pesquise o A18; se nao houver data esperada,
use a data do A17 no ano seguinte."
"""
import unittest
from datetime import date
from unittest import mock

from mithrandir import news_agent, store
from mithrandir.collectors import sorftime
from mithrandir.launch_estimator import predecessor_baseline

HOJE = date(2026, 8, 31)

OBS = [
    {"canonical_model": "SAMSUNG A17", "online_date": "2025-09-04", "sold_qty": 7140},
    {"canonical_model": "XIAOMI NOTE 15", "online_date": "2026-01-30", "sold_qty": 2794},
    {"canonical_model": "APPLE 15", "online_date": "2023-12-28", "sold_qty": 1333},   # velho
    {"canonical_model": "APPLE 17", "online_date": None, "sold_qty": 3201},           # sem data
]


class TestDataDoSorftime(unittest.TestCase):
    def test_string_null_nao_vira_data(self):
        # O Sorftime manda a STRING "null" (34 dos 99 anuncios da coleta real).
        # Guardar isso cru fazia "null" > "2025-08-31" e o aparelho sem data
        # entrava como "lancado no ultimo ano".
        self.assertIsNone(sorftime._date("null"))
        self.assertIsNone(sorftime._date(""))
        self.assertIsNone(sorftime._date(None))
        self.assertIsNone(sorftime._date("2025-13-45"))
        self.assertEqual(sorftime._date("2025-09-08"), "2025-09-08")


class TestLancamentosRecentes(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(sorftime, "load_observations", return_value=OBS)
        p.start()
        self.addCleanup(p.stop)

    def test_janela_de_12_meses(self):
        recentes = {o["canonical_model"] for o in sorftime.recent_launches(12, HOJE)}
        self.assertIn("SAMSUNG A17", recentes)      # 09/2025, dentro
        self.assertIn("XIAOMI NOTE 15", recentes)   # 01/2026, dentro
        self.assertNotIn("APPLE 15", recentes)      # 12/2023, fora
        self.assertNotIn("APPLE 17", recentes)      # sem data, fora

    def test_janela_menor(self):
        recentes = {o["canonical_model"] for o in sorftime.recent_launches(3, HOJE)}
        self.assertEqual(recentes, set())           # nada nos ultimos 3 meses


class TestWatchlistDeSucessores(unittest.TestCase):
    def setUp(self):
        for alvo, nome, valor in (
            (sorftime, "load_observations", OBS),
            (news_agent, "watchlist_from_base", []),
        ):
            p = mock.patch.object(alvo, nome, return_value=valor)
            p.start()
            self.addCleanup(p.stop)

    def _wl(self, catalogo=frozenset()):
        with mock.patch("mithrandir.internal_bi.load_catalog", return_value=set(catalogo)):
            return news_agent.watchlist_from_launches(today=HOJE)

    def test_projeta_o_sucessor(self):
        devices = {w["device"] for w in self._wl()}
        self.assertIn("SAMSUNG A18", devices)
        self.assertIn("XIAOMI NOTE 16", devices)

    def test_ordena_por_venda_e_nao_por_data(self):
        # Ordenando por data o A17 (o mais antigo da janela, e #1 em venda)
        # perdia a vaga para um lancamento recente irrelevante.
        self.assertEqual(self._wl()[0]["device"], "SAMSUNG A18")

    def test_sucessor_que_ja_temos_nao_entra(self):
        devices = {w["device"] for w in self._wl(catalogo={"SAMSUNG A18"})}
        self.assertNotIn("SAMSUNG A18", devices)

    def test_leva_o_predecessor_junto(self):
        w = next(w for w in self._wl() if w["device"] == "SAMSUNG A18")
        self.assertEqual(w["predecessor"], "SAMSUNG A17")
        self.assertEqual(w["predecessor_date"], "2025-09-04")


class TestBaselineDoPredecessor(unittest.TestCase):
    def setUp(self):
        p = mock.patch("mithrandir.collectors.sorftime.load_observations", return_value=OBS)
        p.start()
        self.addCleanup(p.stop)

    def test_mesma_data_do_predecessor_no_ano_seguinte(self):
        # A17 estreou em 04/09/2025 -> sem noticia, o A18 fica em 04/09/2026
        self.assertEqual(predecessor_baseline("SAMSUNG A18", HOJE), "2026-09-04")

    def test_avanca_ate_cair_no_futuro(self):
        # APPLE 15 estreou em 12/2023; o 16 nao pode ser "previsto" para 2024
        base = predecessor_baseline("APPLE 16", HOJE)
        self.assertIsNotNone(base)
        self.assertGreaterEqual(base, HOJE.isoformat())

    def test_sem_predecessor_conhecido_devolve_nada(self):
        self.assertIsNone(predecessor_baseline("MOTOROLA G99", HOJE))

    def test_sem_geracao_devolve_nada(self):
        self.assertIsNone(predecessor_baseline("MOTOROLA EDGE", HOJE))


class TestOrcamentoDaRodada(unittest.TestCase):
    def test_estourado_o_device_e_pulado_e_mantem_o_sinal_anterior(self):
        chamou = []
        fn = lambda q: chamou.append(q) or []
        vencido = news_agent.time.monotonic() - 1
        self.assertEqual(
            news_agent._collect_for(mock.Mock(), {"device": "X"}, fn, deadline=vencido), [])
        self.assertEqual(chamou, [])   # nem chega a buscar


if __name__ == "__main__":
    unittest.main()
