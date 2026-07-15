"""Motor de priorizacao (spec 06-modelo-priorizacao).

Score = w1*SinalLancamento + w2*DesempenhoSimilarInterno
      + w3*TracaoMarketplace + w4*MomentumNoticias - Penalidades

Cada componente e normalizado 0-100. Os pesos variam por fase do ciclo
(pre-lancamento vs pos-lancamento) e sao ajustaveis (loop de feedback).
"""
from __future__ import annotations

from .models import Candidate

# Pesos por fase (somam 1.0). Calibraveis com o time (spec 04, conversa 6).
WEIGHTS = {
    "pre_launch": {"launch": 0.45, "internal": 0.40, "traction": 0.05, "momentum": 0.10},
    "post_launch": {"launch": 0.10, "internal": 0.25, "traction": 0.40, "momentum": 0.25},
}

# Penalidades (subtraidas do score final, 0-100)
PENALTY_ALREADY_HAVE_CASE = 60.0
PENALTY_SIMILAR_SOLD_POORLY = 35.0

# Limiar abaixo do qual o desempenho do similar conta como "vendeu mal"
POOR_PERF_THRESHOLD = 30.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def launch_component(c: Candidate) -> float:
    """Sinal de lancamento: confianca da previsao sazonal (0-100)."""
    return _clamp(c.launch_confidence * 100.0)


def internal_component(c: Candidate) -> float:
    """Desempenho do modelo similar na base interna (0-100)."""
    if not c.internal:
        return 0.0
    return _clamp(c.internal.perf_score)


def traction_component(c: Candidate) -> float:
    """Tracao no marketplace (0-100), combinando ranking, avaliacoes e nota."""
    m = c.marketplace
    if not m:
        return 0.0
    # Ranking: 1 -> ~100, cai suavemente. Sem ranking, contribui 0.
    rank_score = 0.0
    if m.rank:
        rank_score = _clamp(100.0 * (1.0 - (m.rank - 1) / 100.0))
    # Avaliacoes: proxy de volume (escala log-ish simplificada). 2000+ ~ 100.
    reviews_score = _clamp(min(m.review_count, 2000) / 2000.0 * 100.0)
    # Nota media (0-5 -> 0-100)
    rating_score = _clamp((m.rating or 0.0) / 5.0 * 100.0)
    return _clamp(0.5 * rank_score + 0.35 * reviews_score + 0.15 * rating_score)


def momentum_component(c: Candidate) -> float:
    """Momentum ja vem normalizado 0-100 (velocidade de crescimento)."""
    return _clamp(c.momentum)


def penalties(c: Candidate) -> float:
    total = 0.0
    if c.already_have_case:
        total += PENALTY_ALREADY_HAVE_CASE
    if c.similar_sold_poorly:
        total += PENALTY_SIMILAR_SOLD_POORLY
    return total


def score_candidate(c: Candidate) -> Candidate:
    """Calcula o score e preenche a decomposicao (explicabilidade - RNF-07)."""
    # Marca "vendeu mal" a partir do desempenho do similar
    if c.internal and c.internal.perf_score < POOR_PERF_THRESHOLD:
        c.similar_sold_poorly = True

    w = WEIGHTS.get(c.phase, WEIGHTS["pre_launch"])
    comp = {
        "launch": launch_component(c),
        "internal": internal_component(c),
        "traction": traction_component(c),
        "momentum": momentum_component(c),
    }
    weighted = {k: round(comp[k] * w[k], 2) for k in comp}
    base = sum(weighted.values())
    pen = penalties(c)
    final = _clamp(base - pen)

    c.score = round(final, 2)
    c.score_breakdown = {
        "phase": c.phase,
        "weights": w,
        "components_0_100": {k: round(v, 2) for k, v in comp.items()},
        "weighted_contribution": weighted,
        "base": round(base, 2),
        "penalties": {
            "already_have_case": PENALTY_ALREADY_HAVE_CASE if c.already_have_case else 0.0,
            "similar_sold_poorly": PENALTY_SIMILAR_SOLD_POORLY if c.similar_sold_poorly else 0.0,
            "total": pen,
        },
        "final": c.score,
    }
    return c


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        score_candidate(c)
    return sorted(candidates, key=lambda x: x.score, reverse=True)
