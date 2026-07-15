"""Acesso a base interna da Gocase (desempenho de capinhas por modelo).

Hoje le de um CSV de exemplo (data/sample/internal_bi_sample.csv), que simula
uma exportacao do BI. Quando o acesso ao BI for liberado (spec 04), troque
`load_internal_performance` por uma consulta a API/dataset do BI mantendo o
mesmo formato de saida.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from .config import SAMPLE_DIR
from .models import InternalPerformance
from .normalize import ParsedModel, canonicalize


def load_monthly_sales(path: Optional[Path] = None) -> dict:
    """Vendas mensais (6 meses) por modelo de estudo. Exemplo ate o BI real."""
    path = path or (SAMPLE_DIR / "monthly_sales.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    data.pop("_meta", None)
    return {k: v for k, v in data.items() if isinstance(v, list)}


def _to_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _to_int(v: str) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def load_internal_records(path: Optional[Path] = None) -> list[dict]:
    """Le a base interna de vendas de capinhas por modelo de aparelho."""
    path = path or (SAMPLE_DIR / "internal_bi_sample.csv")
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            canonical = row["canonical_model"].strip()
            # Deriva marca/familia/geracao pela mesma normalizacao dos candidatos,
            # garantindo casamento consistente (independe de colunas do CSV).
            parsed = canonicalize(canonical)
            records.append({
                "canonical_model": parsed.canonical,
                "brand": parsed.brand,
                "family": parsed.family,
                "generation": parsed.generation if parsed.generation is not None else 0,
                "units": _to_int(row.get("units", "")),
                "revenue": _to_float(row.get("revenue", "")),
                "margin_pct": _to_float(row.get("margin_pct", "")),
                "sell_through_pct": _to_float(row.get("sell_through_pct", "")),
            })
    return records


def load_catalog(path: Optional[Path] = None) -> set[str]:
    """Modelos para os quais a Gocase JA tem capinha (gera penalidade)."""
    path = path or (SAMPLE_DIR / "catalog_sample.csv")
    catalog: set[str] = set()
    if not path.exists():
        return catalog
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            # Canonicaliza para casar com a chave dos candidatos
            catalog.add(canonicalize(row["canonical_model"].strip()).canonical)
    return catalog


def _perf_score(rec: dict, max_units: int) -> float:
    """Normaliza o desempenho do similar em 0-100."""
    units_norm = (rec["units"] / max_units * 100.0) if max_units else 0.0
    sell_through = rec.get("sell_through_pct", 0.0)          # ja 0-100
    margin_norm = min(rec.get("margin_pct", 0.0), 100.0)    # ja 0-100
    score = 0.5 * units_norm + 0.35 * sell_through + 0.15 * margin_norm
    return round(max(0.0, min(100.0, score)), 2)


def find_similar(parsed: ParsedModel, records: list[dict]) -> Optional[InternalPerformance]:
    """Encontra o modelo similar (tipicamente a geracao anterior) na base interna.

    Estrategia por regras: mesma familia + geracao imediatamente anterior.
    Ex.: candidato 'GALAXY S26 FE' casa com 'GALAXY S25 FE'.
    """
    if not records:
        return None
    max_units = max((r["units"] for r in records), default=0)

    same_family = [r for r in records if r["family"] and r["family"] == parsed.family]
    pool = same_family or [r for r in records if r["brand"] == parsed.brand]
    if not pool:
        return None

    match = None
    if parsed.generation is not None:
        # geracao anterior exata
        prev = [r for r in pool if r["generation"] == parsed.generation - 1]
        if prev:
            match = max(prev, key=lambda r: r["units"])
    if match is None:
        # cai para a geracao mais recente disponivel na familia
        match = max(pool, key=lambda r: (r["generation"], r["units"]))

    monthly = load_monthly_sales().get(match["canonical_model"], [])
    return InternalPerformance(
        similar_model=match["canonical_model"],
        units=match["units"],
        revenue=match["revenue"],
        margin_pct=match["margin_pct"],
        sell_through_pct=match["sell_through_pct"],
        perf_score=_perf_score(match, max_units),
        monthly_sales=monthly,
    )
