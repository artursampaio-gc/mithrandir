"""Coletor da planilha de vendas internas (Google Sheets via API key).

A planilha e uma tabela dinamica: coluna A = "Case ... / <modelo do aparelho>",
colunas de meses (1..N) = quantidade vendida, coluna "Total geral" = total.
Extraimos o modelo do aparelho (apos o ultimo " / "), somamos por modelo e
geramos: registros de desempenho (total) + serie mensal (para a viabilidade).

Requer a planilha compartilhada como "qualquer um com o link -> Leitor" e uma
Google Sheets API key. Sincroniza para o Supabase (app_cache) via sync_to_store.
"""
from __future__ import annotations

import urllib.parse
from datetime import date

from .. import store
from .._http import request_json
from ..config import SheetsConfig, load_config
from ..normalize import canonicalize

_API = "https://sheets.googleapis.com/v4/spreadsheets"


def _num(v) -> int:
    """Converte '5.707' -> 5707; vazio -> 0."""
    s = str(v).strip().replace(".", "").replace(",", "").replace(" ", "")
    return int(s) if s.lstrip("-").isdigit() else 0


def _phone_from_product(product: str) -> str:
    p = (product or "").strip()
    return p.rsplit(" / ", 1)[1].strip() if " / " in p else p


def _resolve_title(cfg: SheetsConfig) -> str:
    """Descobre o nome do tab a partir do gid (ou usa cfg.range se fornecido)."""
    if cfg.range:
        return cfg.range
    meta = request_json("GET", f"{_API}/{cfg.sheet_id}?fields=sheets.properties&key={cfg.api_key}")
    for s in (meta or {}).get("sheets", []):
        props = s.get("properties", {})
        if str(props.get("sheetId")) == str(cfg.gid):
            return props.get("title", "")
    # fallback: primeiro tab
    sheets = (meta or {}).get("sheets", [])
    return sheets[0]["properties"]["title"] if sheets else ""


def fetch_values(cfg: SheetsConfig) -> list[list]:
    title = _resolve_title(cfg)
    rng = urllib.parse.quote(title)
    data = request_json("GET", f"{_API}/{cfg.sheet_id}/values/{rng}?key={cfg.api_key}")
    return (data or {}).get("values", [])


def parse(values: list[list]) -> dict:
    """Agrega as vendas por modelo canonico. Retorna canon -> dados."""
    if len(values) < 3:
        return {}
    header = values[1]  # linha "Produto | 1 | 2 | ... | Total geral"
    month_cols, total_col = [], None
    for i, h in enumerate(header):
        hs = str(h).strip()
        if hs.isdigit():
            month_cols.append((i, int(hs)))
        elif hs.lower().startswith("total"):
            total_col = i

    out: dict = {}
    for row in values[2:]:
        if not row or not str(row[0]).strip():
            continue
        if str(row[0]).strip().lower().startswith("total geral"):
            continue  # linha de rodape da tabela dinamica
        phone = _phone_from_product(row[0])
        if not phone:
            continue
        p = canonicalize(phone)
        canon = p.canonical
        entry = out.setdefault(canon, {
            "device": phone, "brand": p.brand, "family": p.family,
            "generation": p.generation, "months": {}, "total": 0,
        })
        for ci, mnum in month_cols:
            if ci < len(row):
                entry["months"][mnum] = entry["months"].get(mnum, 0) + _num(row[ci])
        if total_col is not None and total_col < len(row):
            entry["total"] += _num(row[total_col])
    # se nao houver coluna de total, usa a soma dos meses
    for e in out.values():
        if e["total"] == 0:
            e["total"] = sum(e["months"].values())
    return out


def _completed_months(current_month: int, n: int = 6) -> list[int]:
    """Ultimos n meses ja fechados (antes do mes atual) dentro do ano."""
    done = list(range(1, max(1, current_month)))  # 1..current-1
    return done[-n:]


def build_records(parsed: dict) -> list[dict]:
    """Registros no formato de internal_bi.load_internal_records."""
    records = []
    for canon, e in parsed.items():
        records.append({
            "canonical_model": canon, "brand": e["brand"],
            "family": e["family"], "generation": e["generation"] or 0,
            "units": e["total"], "revenue": 0.0,
            "margin_pct": 0.0, "sell_through_pct": 0.0,
            # nome comercial como aparece na planilha (para montar buscas legiveis)
            "device": e["device"],
        })
    return records


def build_monthly(parsed: dict, current_month: int) -> dict:
    """Serie dos ultimos meses fechados por modelo (para a viabilidade)."""
    months = _completed_months(current_month)
    return {canon: [e["months"].get(m, 0) for m in months] for canon, e in parsed.items()}


def sync_to_store(cfg: SheetsConfig | None = None, current_month: int | None = None) -> int:
    """Le a planilha e grava internal_records + monthly_sales no store. Retorna nº de modelos."""
    cfg = cfg or load_config().sheets
    if not cfg.is_configured:
        raise RuntimeError("Google Sheets nao configurado (api_key/sheet_id).")
    current_month = current_month or date.today().month
    parsed = parse(fetch_values(cfg))
    if not parsed:
        return 0
    store.set_cached("internal_records", build_records(parsed))
    store.set_cached("monthly_sales", build_monthly(parsed, current_month))
    return len(parsed)
