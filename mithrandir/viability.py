"""Analise de viabilidade de um novo device (mesma logica da planilha Gocase).

Calcula, a partir das vendas do device de estudo (similar) e das constantes
financeiras, a receita/mes, a margem por unidade e o ponto de breakeven.

As constantes sao defaults do negocio (ajustaveis). Quando o BI/custos reais
forem conectados, sobrescreva CASE_PRICE/MOLD_COST/UNIT_COST ou passe por device.
"""
from __future__ import annotations

from datetime import date

# Constantes de negocio (defaults — vindos da planilha de referencia)
CASE_PRICE = 99.90        # valor de venda da capinha
MOLD_COST = 22200.0       # custo do molde (fixo)
UNIT_COST = 3.16          # custo por unidade
WEEKS_PER_MONTH = 4.3
DAYS_PER_MONTH = 30

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def month_labels(n: int = 6, today: date | None = None) -> list[str]:
    """Nomes dos ultimos n meses completos (anteriores ao mes atual)."""
    today = today or date.today()
    base = today.year * 12 + (today.month - 1)
    return [MESES[(base - k) % 12] for k in range(n, 0, -1)]


def _mom(units: list[int]) -> list:
    """Variacao mes-a-mes (%). None no 1o mes; 'div0' quando o mes anterior e 0."""
    out = [None]
    for i in range(1, len(units)):
        prev = units[i - 1]
        out.append(round((units[i] - prev) / prev * 100) if prev else "div0")
    return out


def compute_viability(monthly_units: list[int], today: date | None = None,
                      case_price: float = CASE_PRICE, mold_cost: float = MOLD_COST,
                      unit_cost: float = UNIT_COST) -> dict:
    """Retorna o dicionario de viabilidade (vazio se nao houver vendas)."""
    if not monthly_units:
        return {}
    n = len(monthly_units)
    labels = month_labels(n, today)
    total = sum(monthly_units)
    avg_month = total / n
    avg_week = avg_month / WEEKS_PER_MONTH
    per_day = total / (n * DAYS_PER_MONTH)
    receita_mes = avg_month * case_price
    unit_margin = case_price - unit_cost
    qtd_breakeven = round(mold_cost / unit_margin) if unit_margin > 0 else None
    breakeven_weeks = (qtd_breakeven / avg_week) if (qtd_breakeven and avg_week) else None

    moms = _mom(monthly_units)
    months = [{"label": labels[i], "units": monthly_units[i], "mom": moms[i]}
              for i in range(n)]

    return {
        "months": months,
        "total": total,
        "avg_month": round(avg_month),
        "avg_week": round(avg_week, 1),
        "per_day": round(per_day, 1),
        "case_price": case_price,
        "receita_mes": round(receita_mes, 2),
        "mold_cost": mold_cost,
        "unit_cost": unit_cost,
        "unit_margin": round(unit_margin, 2),
        "qtd_breakeven": qtd_breakeven,
        "breakeven_weeks": round(breakeven_weeks, 2) if breakeven_weeks else None,
    }
