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

from . import store
from .config import SAMPLE_DIR
from .models import InternalPerformance
from .normalize import ParsedModel, canonicalize


def load_monthly_sales(path: Optional[Path] = None) -> dict:
    """Vendas mensais por modelo. Prioriza os dados reais da planilha (store);
    cai no exemplo (monthly_sales.json) quando nao houver."""
    cached = store.get_cached("monthly_sales")
    if cached:
        return cached
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
    """Base interna de vendas por modelo. Prioriza os dados reais da planilha
    (store); cai no CSV de exemplo quando nao houver."""
    cached = store.get_cached("internal_records")
    if cached:
        return cached
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


def load_catalog(path: Optional[Path] = None,
                 records: Optional[list[dict]] = None) -> set[str]:
    """Modelos para os quais a Gocase JA tem capinha (gera penalidade).

    Duas fontes, unidas:

    1) **A base interna de vendas.** Se vendemos capinha do modelo, temos capinha
       dele — e essa e a fonte que vale: 158 modelos reais da planilha contra as
       4 linhas do CSV de exemplo. Enquanto so o CSV valia, a penalidade era
       inerte e o app recomendava iPhone 16 (41 mil capinhas vendidas) como se
       fosse novidade.
    2) **O CSV de catalogo**, para o caso de uma capinha existir mas ainda nao ter
       venda registrada (lancamento recente).

    Passe `records` para reaproveitar a base ja carregada pelo chamador.
    """
    catalog: set[str] = set()

    recs = load_internal_records() if records is None else records
    for r in recs:
        key = (r.get("canonical_model") or "").strip()
        if key:
            catalog.add(key)   # ja vem canonicalizado de load_internal_records

    path = path or (SAMPLE_DIR / "catalog_sample.csv")
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                # Canonicaliza para casar com a chave dos candidatos
                catalog.add(canonicalize(row["canonical_model"].strip()).canonical)
    return catalog


def cases_started_selling(min_units: int = 100, today=None) -> dict[str, str]:
    """Capinhas que ESTREARAM na janela da serie: canonical -> "AAAA-MM-01".

    Sinal: a serie mensal comeca em zero e depois engrena. A planilha nao tem
    data de lancamento da capinha, entao esse "primeiro mes com venda" e o que
    da para inferir.

    Os dois filtros existem porque o primeiro mes com venda, sozinho, confunde
    lancamento com cauda longa: o `APPLE 7/8 +` (aparelho de 2016) aparece como
    [0,0,0,10,0,0] — 10 unidades avulsas, nao um lancamento. Exigimos volume
    minimo E venda no ultimo mes, o que separa limpo os casos reais
    (`SAMSUNG A57` = [0,0,21,548,1388,1273]) do ruido.

    ⚠️ So enxerga a janela da serie (hoje 6 meses, e do ANO CORRENTE — a planilha
    nao guarda o ano anterior). Capinha lancada antes disso nao aparece aqui.
    """
    from datetime import date as _date

    from .collectors.sheets import _completed_months

    today = today or _date.today()
    out: dict[str, str] = {}
    for canon, serie in load_monthly_sales().items():
        if not serie or not any(serie):
            continue
        primeiro = next(i for i, v in enumerate(serie) if v > 0)
        if primeiro == 0:
            continue                      # ja vendia quando a janela comecou
        if sum(serie) < min_units or serie[-1] <= 0:
            continue                      # venda avulsa de modelo antigo
        meses = _completed_months(today.month, len(serie))
        if len(meses) != len(serie):
            continue                      # serie fora de sincronia com o calendario
        out[canon] = f"{today.year:04d}-{meses[primeiro]:02d}-01"
    return out


def _perf_score(rec: dict, all_units: list[int]) -> float:
    """Desempenho do similar em 0-100, pelo PERCENTIL de unidades no catalogo.

    Percentil (e nao normalizacao linear pelo maximo) porque a distribuicao real
    e de cauda longa: um modelo dominante (ex.: iPhone 13/14, ~100k) esmagaria
    todos os outros para perto de zero. Assim, 80 = "vendeu mais que 80% dos
    modelos da nossa base".
    """
    units = rec.get("units", 0) or 0
    if not all_units or units <= 0:
        return 0.0
    pct = sum(1 for u in all_units if u <= units) / len(all_units) * 100.0
    sell_through = rec.get("sell_through_pct", 0.0) or 0.0    # ja 0-100
    margin_norm = min(rec.get("margin_pct", 0.0) or 0.0, 100.0)
    # Sem margem/sell-through (ex.: planilha so tem unidades) -> usa so o percentil
    if sell_through <= 0 and margin_norm <= 0:
        return round(pct, 2)
    score = 0.5 * pct + 0.35 * sell_through + 0.15 * margin_norm
    return round(max(0.0, min(100.0, score)), 2)


def find_similar(parsed: ParsedModel, records: list[dict]) -> Optional[InternalPerformance]:
    """Encontra o modelo similar (tipicamente a geracao anterior) na base interna.

    Estrategia por regras: mesma familia + geracao imediatamente anterior.
    Ex.: candidato 'GALAXY S26 FE' casa com 'GALAXY S25 FE'.
    """
    if not records:
        return None
    all_units = [r.get("units", 0) or 0 for r in records if (r.get("units", 0) or 0) > 0]

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
        perf_score=_perf_score(match, all_units),
        monthly_sales=monthly,
    )
