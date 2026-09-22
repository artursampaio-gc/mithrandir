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


class TestFiltroDePrecoDoAparelho(unittest.TestCase):
    """Celular de entrada tem comprador que nao compra capinha de ~R$100 —
    abaixo do minimo o candidato so polui a lista."""

    def _cand(self, nome, preco=None, fase="post_launch"):
        from mithrandir.models import Candidate, MarketplaceSignal
        c = Candidate(canonical_model=nome, phase=fase)
        if preco is not None:
            c.marketplace = MarketplaceSignal(source="amazon", price=preco)
        return c

    def test_corta_abaixo_do_minimo(self):
        from mithrandir.pipeline import _filtra_por_preco
        cands = [self._cand("CARO", 2999.0), self._cand("BARATO", 699.0)]
        fica = {c.canonical_model for c in _filtra_por_preco(cands, 1200)}
        self.assertEqual(fica, {"CARO"})

    def test_mantem_quem_esta_exatamente_no_minimo(self):
        from mithrandir.pipeline import _filtra_por_preco
        cands = [self._cand("NOLIMITE", 1200.0)]
        self.assertEqual(len(_filtra_por_preco(cands, 1200)), 1)

    def test_pre_lancamento_sem_preco_nao_e_cortado(self):
        # e justamente o que mais interessa vigiar: ainda nao esta a venda
        from mithrandir.pipeline import _filtra_por_preco
        cands = [self._cand("SAMSUNG S26 FE", None, "pre_launch")]
        self.assertEqual(len(_filtra_por_preco(cands, 1200)), 1)

    def test_zero_ou_invalido_desliga_o_filtro(self):
        from mithrandir.pipeline import _filtra_por_preco
        cands = [self._cand("BARATO", 699.0)]
        for valor in (0, None, "", "abc"):
            with self.subTest(valor=valor):
                self.assertEqual(len(_filtra_por_preco(cands, valor)), 1)

    def test_setting_persiste(self):
        from mithrandir.settings import DEFAULTS
        self.assertEqual(DEFAULTS["min_device_price"], 1200.0)


class TestCandidatoComCapinhaSaiDaLista(unittest.TestCase):
    """Aparelho para o qual ja temos capinha nao e candidato a desenvolvimento.
    Antes so levava penalidade e caia para o fim — 31 dos 50 seguiam na lista."""

    def _cand(self, nome, tem_capinha=False, preco=2000.0):
        from mithrandir.models import Candidate, MarketplaceSignal
        c = Candidate(canonical_model=nome)
        c.already_have_case = tem_capinha
        c.marketplace = MarketplaceSignal(source="amazon", price=preco)
        return c

    def test_remove_quem_ja_tem_capinha(self):
        from mithrandir.pipeline import _filtra_candidatos
        cands = [self._cand("APPLE 13", True), self._cand("MOTOROLA EDGE 70")]
        fica = {c.canonical_model for c in _filtra_candidatos(cands, {})}
        self.assertEqual(fica, {"MOTOROLA EDGE 70"})

    def test_os_dois_filtros_valem_juntos(self):
        from mithrandir.pipeline import _filtra_candidatos
        cands = [self._cand("TEM CAPINHA CARO", True, 3000.0),
                 self._cand("SEM CAPINHA BARATO", False, 500.0),
                 self._cand("SEM CAPINHA CARO", False, 3000.0)]
        fica = {c.canonical_model
                for c in _filtra_candidatos(cands, {"min_device_price": 1200})}
        self.assertEqual(fica, {"SEM CAPINHA CARO"})
