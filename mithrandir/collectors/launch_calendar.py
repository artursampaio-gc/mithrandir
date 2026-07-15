"""Previsao sazonal de lancamentos (RF-01).

Le o calendario historico de lancamentos e projeta o proximo modelo de cada
linha para a mesma janela do ano seguinte. Ex.: se o S25 FE lancou em set/2025,
prevê o S26 FE para set/2026.

O calendario historico hoje vem de um CSV de exemplo; futuramente e alimentado
por GSMArena/noticias (spec 03).
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Optional

from ..config import SAMPLE_DIR


def load_launch_history(path: Optional[Path] = None) -> list[dict]:
    path = path or (SAMPLE_DIR / "launches_history_sample.csv")
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                gen = int(float(row.get("generation", "") or 0))
            except ValueError:
                gen = 0
            rows.append({
                "brand": row["brand"].strip().upper(),
                "family": row["family"].strip().upper(),
                "canonical_model": row["canonical_model"].strip().upper(),
                "generation": gen,
                "launch_date": row["launch_date"].strip(),  # ISO do ano anterior
            })
    return rows


def _next_gen_name(canonical: str, gen: int) -> str:
    """Troca o numero de geracao pelo proximo (S25 FE -> S26 FE).

    Usa fronteira de digito (nao de palavra) para pegar numeros colados a
    uma letra, como o '25' em 'S25'.
    """
    if gen and re.search(rf"(?<!\d){gen}(?!\d)", canonical):
        return re.sub(rf"(?<!\d){gen}(?!\d)", str(gen + 1), canonical, count=1)
    return canonical + " (proximo)"


def _confidence(days_to: int, horizon: int) -> float:
    """Confianca da previsao conforme a proximidade da janela prevista."""
    if days_to < 0:
        # janela ja passou ha pouco: lancamento iminente/recente
        return 0.6
    # decai de ~0.9 (no dia previsto) ate ~0.3 (fim do horizonte)
    frac = min(days_to, horizon) / horizon
    return round(max(0.3, 0.9 - 0.6 * frac), 3)


def predict_upcoming(history: list[dict], today: Optional[date] = None,
                     horizon_days: int = 210, lookback_days: int = 60) -> list[dict]:
    """Retorna candidatos pre-lancamento previstos dentro da janela [hoje-lookback, hoje+horizon]."""
    today = today or date.today()
    out: list[dict] = []
    for rec in history:
        try:
            base = date.fromisoformat(rec["launch_date"])
        except ValueError:
            continue
        # mesma data, um ano depois
        try:
            predicted = base.replace(year=base.year + 1)
        except ValueError:
            predicted = base.replace(year=base.year + 1, day=28)
        days_to = (predicted - today).days
        if days_to < -lookback_days or days_to > horizon_days:
            continue
        next_gen = (rec["generation"] + 1) if rec["generation"] else None
        out.append({
            "canonical_model": _next_gen_name(rec["canonical_model"], rec["generation"]),
            "brand": rec["brand"],
            "family": rec["family"],
            "generation": next_gen,
            "predicted_launch": predicted.isoformat(),
            "launch_confidence": _confidence(days_to, horizon_days),
            "source": f"Previsao sazonal (base: {rec['canonical_model']} em {rec['launch_date']})",
        })
    return out
