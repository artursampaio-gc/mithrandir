"""Orquestracao do pipeline diario (spec 05-arquitetura).

Fluxo: previsao de lancamentos + coleta de marketplace + noticias
-> normalizacao/dedup -> casamento com base interna -> score -> persistencia.
"""
from __future__ import annotations

from .ai.proxy import AIClient
from .config import Config, load_config
from .collectors import mercadolivre, news
from .collectors.launch_calendar import load_launch_history, predict_upcoming
from .db import previous_review_count, save_run
from .internal_bi import find_similar, load_catalog, load_internal_records
from .models import Candidate, MarketplaceSignal
from .normalize import BRANDS, canonicalize
from .scoring import rank_candidates
from .settings import load_settings
from .viability import compute_viability


def _compute_momentum(obs: dict, key: str) -> float:
    """Momentum 0-100: usa o hint do mock, ou calcula pelo crescimento de reviews."""
    if obs.get("momentum") is not None:
        return float(obs["momentum"])
    prev = previous_review_count(key)
    cur = obs.get("review_count", 0) or 0
    if prev and prev > 0:
        growth = (cur - prev) / prev
        return max(0.0, min(100.0, growth * 200.0))
    return 50.0  # sem historico: valor neutro


def _headline_matches(title: str, c: Candidate) -> bool:
    """Heuristica: manchete cita a marca e o token de geracao do candidato."""
    low = title.lower()
    aliases = [tok for tok, b in BRANDS.items() if b == c.brand]
    brand_ok = any(a in low for a in aliases) if aliases else False
    gen_tokens = [t.lower() for t in c.canonical_model.split()
                  if any(ch.isdigit() for ch in t)]
    gen_ok = all(t in low for t in gen_tokens) if gen_tokens else False
    return brand_ok and gen_ok


def run_pipeline(cfg: Config | None = None) -> list[Candidate]:
    cfg = cfg or load_config()
    ai = AIClient(cfg.ai)
    internal = load_internal_records()
    catalog = load_catalog()
    st = load_settings()

    candidates: dict[str, Candidate] = {}

    # 1) Candidatos pre-lancamento (previsao sazonal)
    for p in predict_upcoming(load_launch_history()):
        parsed = canonicalize(p["canonical_model"])  # chave consistente com o marketplace
        key = parsed.canonical
        c = candidates.setdefault(key, Candidate(canonical_model=key))
        c.brand = parsed.brand or p["brand"]
        c.family = parsed.family or p["family"]
        c.phase = "pre_launch"
        c.predicted_launch = p["predicted_launch"]
        c.launch_confidence = p["launch_confidence"]
        if key not in c.raw_names:
            c.raw_names.append(key)
        c.sources.append(p["source"])

    # 2) Candidatos com tracao no marketplace (pos-lancamento)
    # Usa a normalizacao por regras (deterministica e consistente com BI/catalogo).
    for o in mercadolivre.collect(cfg.mercadolivre):
        parsed = canonicalize(o["raw_name"])
        key = parsed.canonical
        c = candidates.setdefault(key, Candidate(canonical_model=key))
        c.brand = c.brand or parsed.brand
        c.family = c.family or parsed.family
        c.phase = "post_launch"  # ja esta a venda
        c.marketplace = MarketplaceSignal(
            source=o["source"], rank=o.get("rank"), sold_qty=o.get("sold_qty"),
            review_count=o.get("review_count", 0) or 0, rating=o.get("rating"),
            price=o.get("price"), offers=o.get("offers", 0) or 0,
        )
        c.momentum = _compute_momentum(o, key)
        c.rankings = o.get("rankings", [])
        if o["raw_name"] not in c.raw_names:
            c.raw_names.append(o["raw_name"])
        c.sources.append(f"{o['source']}: {o['raw_name']}")

    # 3) Enriquecimento com noticias
    headlines = news.collect()
    for c in candidates.values():
        for h in headlines:
            if _headline_matches(h["title"], c):
                c.sources.append(f"noticia: {h['title']}")

    # 4) Casamento com base interna + flag de catalogo + viabilidade
    for key, c in candidates.items():
        parsed = canonicalize(key)
        c.internal = find_similar(parsed, internal)
        c.already_have_case = key in catalog
        if c.internal and c.internal.monthly_sales:
            c.viability = compute_viability(
                c.internal.monthly_sales,
                case_price=st["case_price"], mold_cost=st["mold_cost"],
                unit_cost=st["unit_cost"])

    ranked = rank_candidates(list(candidates.values()))
    save_run(ranked, cfg.mock_mode)
    return ranked
