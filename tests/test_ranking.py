import unittest

from mithrandir.models import Candidate
from mithrandir.scoring import rank_by_breakeven


def cand(name, be=None, have_case=False):
    c = Candidate(canonical_model=name)
    c.already_have_case = have_case
    if be is not None:
        c.viability = {"breakeven_weeks": be}
    return c


class TestRankingPorBreakeven(unittest.TestCase):
    def test_ordem_crescente_de_breakeven(self):
        ranked = rank_by_breakeven([cand("LENTO", 12.7), cand("RAPIDO", 0.5),
                                    cand("MEDIO", 3.0)])
        self.assertEqual([c.canonical_model for c in ranked],
                         ["RAPIDO", "MEDIO", "LENTO"])

    def test_sem_breakeven_vai_para_o_fim(self):
        ranked = rank_by_breakeven([cand("SEM_BASE"), cand("LENTO", 99.0)])
        self.assertEqual([c.canonical_model for c in ranked], ["LENTO", "SEM_BASE"])

    def test_ja_temos_capinha_por_ultimo(self):
        ranked = rank_by_breakeven([cand("JA_TEMOS", 0.1, have_case=True),
                                    cand("SEM_BASE"), cand("BOM", 5.0)])
        self.assertEqual([c.canonical_model for c in ranked],
                         ["BOM", "SEM_BASE", "JA_TEMOS"])

    def test_score_continua_calculado(self):
        ranked = rank_by_breakeven([cand("X", 2.0)])
        self.assertIn("components_0_100", ranked[0].score_breakdown)


if __name__ == "__main__":
    unittest.main()
