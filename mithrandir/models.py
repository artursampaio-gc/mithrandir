"""Estruturas de dados do dominio (dataclasses)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class MarketplaceSignal:
    """Sinal de tracao coletado de um marketplace (ex.: Mercado Livre)."""
    source: str                    # "mercadolivre", "amazon", ...
    rank: Optional[int] = None     # posicao no ranking de mais vendidos (1 = topo)
    sold_qty: Optional[int] = None # quantidade vendida (quando disponivel)
    review_count: int = 0          # nro de avaliacoes (proxy de volume)
    rating: Optional[float] = None # nota media (0-5)
    price: Optional[float] = None
    offers: int = 0                # nro de anuncios/vendedores


@dataclass
class InternalPerformance:
    """Desempenho de capinha do modelo SIMILAR na base interna (BI)."""
    similar_model: str             # modelo similar encontrado (ex.: "S25 FE")
    units: int = 0                 # unidades vendidas do similar
    revenue: float = 0.0
    margin_pct: Optional[float] = None
    sell_through_pct: Optional[float] = None  # % do estoque vendido
    perf_score: float = 0.0        # 0-100, desempenho normalizado do similar
    monthly_sales: list = field(default_factory=list)  # vendas dos ultimos 6 meses [int]


@dataclass
class Candidate:
    """Um modelo de celular candidato a desenvolvimento de capinha."""
    canonical_model: str           # chave canonica (ex.: "SAMSUNG GALAXY S26 FE")
    brand: str = ""
    family: str = ""               # linha (ex.: "Galaxy S FE", "Moto G")
    raw_names: list[str] = field(default_factory=list)  # variacoes de nome vistas

    phase: str = "pre_launch"      # "pre_launch" | "post_launch"
    predicted_launch: str = ""     # data prevista (ISO) ou ""
    launch_confidence: float = 0.0 # 0-1

    marketplace: Optional[MarketplaceSignal] = None
    internal: Optional[InternalPerformance] = None

    # Sinais de momentum (variacao no tempo) ja normalizados 0-100
    momentum: float = 0.0

    # Flags que geram penalidade
    already_have_case: bool = False
    similar_sold_poorly: bool = False

    # Fontes/noticias que sustentam o candidato (para o drill-down)
    sources: list[str] = field(default_factory=list)

    # Rankings por loja (para a analise de viabilidade)
    rankings: list = field(default_factory=list)  # [{store,position,criterio,value,reviews}]

    # Preenchido pelo motor de score
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    # Preenchido pelo modulo de viabilidade
    viability: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
