import unittest

from mithrandir.models import Candidate, InternalPerformance, MarketplaceSignal
from mithrandir.scoring import score_candidate


def _post_launch(model, rank, reviews, rating, momentum, perf):
    return Candidate(
        canonical_model=model, brand="X", phase="post_launch",
        marketplace=MarketplaceSignal(source="ml", rank=rank, review_count=reviews, rating=rating),
        internal=InternalPerformance(similar_model="prev", units=1000, perf_score=perf),
        momentum=momentum,
    )


class TestScoring(unittest.TestCase):
    def test_sucesso_pos_lancamento_pontua_mais_que_fraco(self):
        forte = score_candidate(_post_launch("FORTE", 2, 1600, 4.7, 92, 60))
        fraco = score_candidate(_post_launch("FRACO", 40, 120, 4.0, 15, 20))
        self.assertGreater(forte.score, fraco.score)

    def test_penalidade_ja_temos_capinha(self):
        base = _post_launch("M", 1, 2000, 5.0, 90, 90)
        sem = score_candidate(_post_launch("M", 1, 2000, 5.0, 90, 90))
        base.already_have_case = True
        com = score_candidate(base)
        self.assertLess(com.score, sem.score)

    def test_similar_fraco_marca_flag_automatica(self):
        c = _post_launch("M", 5, 500, 4.5, 50, 10)  # perf 10 < limiar 30
        score_candidate(c)
        self.assertTrue(c.similar_sold_poorly)

    def test_breakdown_explicavel(self):
        c = score_candidate(_post_launch("M", 3, 800, 4.5, 60, 55))
        self.assertIn("components_0_100", c.score_breakdown)
        self.assertIn("weighted_contribution", c.score_breakdown)
        self.assertEqual(c.score_breakdown["final"], c.score)


if __name__ == "__main__":
    unittest.main()
