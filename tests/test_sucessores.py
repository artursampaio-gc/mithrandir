"""Vigiar o sucessor do aparelho de cada capinha que a GOCASE lancou no ultimo ano.

Regra do negocio: "ano passado lancamos capinha do Galaxy A17 -> pesquise o A18;
se nao houver data esperada, use a data de lancamento do A17 no ano seguinte."
"""
import unittest
from datetime import date
from unittest import mock

from mithrandir import news_agent
from mithrandir.collectors import sorftime
from mithrandir.launch_estimator import predecessor_baseline

HOJE = date(2026, 8, 31)

# Nossa base: modelos para os quais a Gocase vende capinha
RECORDS = [
    {"canonical_model": "SAMSUNG A17", "units": 7455},
    {"canonical_model": "SAMSUNG A57", "units": 3230},
    {"canonical_model": "APPLE 15", "units": 46642},
]
# Serie mensal (6 meses fechados). Quem comeca com zero e engrena = capinha nova.
MENSAIS = {
    "SAMSUNG A57": [0, 0, 21, 548, 1388, 1273],   # estreou na janela
    "SAMSUNG A17": [712, 905, 1219, 1069, 1425, 1338],  # ja vendia antes
    "APPLE 15": [400, 380, 350, 300, 280, 260],   # antigo
    "APPLE 7/8 +": [0, 0, 0, 10, 0, 0],           # venda avulsa, NAO e lancamento
}
# Coleta da Amazon: da a data de estreia do APARELHO
OBS = [
    {"canonical_model": "SAMSUNG A17", "online_date": "2025-09-04", "sold_qty": 7140},
    {"canonical_model": "SAMSUNG A57", "online_date": None, "sold_qty": 3000},
    {"canonical_model": "APPLE 15", "online_date": "2023-12-28", "sold_qty": 1333},
]


def _patch(caso):
    for alvo, nome, valor in (
        ("mithrandir.internal_bi.load_internal_records", None, RECORDS),
        ("mithrandir.internal_bi.load_monthly_sales", None, MENSAIS),
        ("mithrandir.collectors.sorftime.load_observations", None, OBS),
    ):
        p = mock.patch(alvo, return_value=valor)
        p.start()
        caso.addCleanup(p.stop)


class TestDataDoSorftime(unittest.TestCase):
    def test_string_null_nao_vira_data(self):
        # O Sorftime manda a STRING "null" (34 dos 99 anuncios da coleta real).
        # Cru, "null" > "2025-08-31" na comparacao de string e um aparelho SEM
        # data entrava como "lancado no ultimo ano".
        for ruim in ("null", "", None, "2025-13-45"):
            self.assertIsNone(sorftime._date(ruim))
        self.assertEqual(sorftime._date("2025-09-08"), "2025-09-08")


class TestCapinhaQueEstreou(unittest.TestCase):
    def setUp(self):
        _patch(self)

    def test_serie_que_comeca_em_zero_e_engrena(self):
        from mithrandir.internal_bi import cases_started_selling
        saida = cases_started_selling(today=HOJE)
        self.assertIn("SAMSUNG A57", saida)
        self.assertEqual(saida["SAMSUNG A57"], "2026-04-01")   # 3o mes da serie

    def test_venda_avulsa_de_modelo_antigo_nao_conta(self):
        from mithrandir.internal_bi import cases_started_selling
        # iPhone 7/8 e de 2016: [0,0,0,10,0,0] sao 10 unidades soltas
        self.assertNotIn("APPLE 7/8 +", cases_started_selling(today=HOJE))

    def test_quem_ja_vendia_no_inicio_da_janela_nao_conta(self):
        from mithrandir.internal_bi import cases_started_selling
        self.assertNotIn("SAMSUNG A17", cases_started_selling(today=HOJE))


class TestWatchlistDeSucessores(unittest.TestCase):
    def setUp(self):
        _patch(self)
        p = mock.patch.object(news_agent, "watchlist_from_base", return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def _wl(self, catalogo=frozenset()):
        with mock.patch("mithrandir.internal_bi.load_catalog", return_value=set(catalogo)):
            return news_agent.watchlist_from_launches(today=HOJE)

    def test_projeta_o_sucessor_do_que_lancamos(self):
        devices = {w["device"] for w in self._wl()}
        self.assertIn("SAMSUNG A18", devices)   # capinha do A17, aparelho de 09/2025
        self.assertIn("SAMSUNG A58", devices)   # capinha estreou na nossa serie

    def test_modelo_antigo_nao_entra(self):
        # iPhone 15: aparelho de 2023 e capinha que ja vendia — nao e "do ultimo ano"
        self.assertNotIn("APPLE 16", {w["device"] for w in self._wl()})

    def test_ordena_por_venda_da_capinha(self):
        self.assertEqual(self._wl()[0]["predecessor"], "SAMSUNG A17")   # 7455 un

    def test_sucessor_que_ja_temos_nao_entra(self):
        self.assertNotIn("SAMSUNG A18", {w["device"] for w in self._wl({"SAMSUNG A18"})})

    def test_leva_o_predecessor_junto(self):
        w = next(w for w in self._wl() if w["device"] == "SAMSUNG A18")
        self.assertEqual(w["predecessor"], "SAMSUNG A17")


class TestBaselineDoPredecessor(unittest.TestCase):
    def setUp(self):
        _patch(self)

    def test_usa_a_estreia_do_aparelho_quando_existe(self):
        # A17 estreou em 04/09/2025 -> sem noticia, o A18 fica em 04/09/2026
        self.assertEqual(predecessor_baseline("SAMSUNG A18", HOJE), "2026-09-04")

    def test_cai_na_estreia_da_nossa_capinha_quando_falta_a_do_aparelho(self):
        # O A57 nao tem online_date na Amazon (34 dos 99 anuncios vem sem data);
        # sem esta segunda fonte o A58 voltava sem data nenhuma.
        self.assertEqual(predecessor_baseline("SAMSUNG A58", HOJE), "2027-04-01")

    def test_avanca_ate_cair_no_futuro(self):
        # iPhone 15 estreou em 12/2023: o 16 nao pode ser "previsto" para 2024
        base = predecessor_baseline("APPLE 16", HOJE)
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
