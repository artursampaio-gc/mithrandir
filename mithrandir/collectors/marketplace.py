"""Rotina de coleta de ranking dos marketplaces (snapshot, sem historico).

Fluxo: uma coleta (hoje feita no navegador, ver DEV.md) produz linhas no formato
    posicao~titulo do anuncio~preco~reviews
Este modulo normaliza o modelo, monta o snapshot por loja e grava no store
(Supabase quando configurado). O app le esse snapshot e mostra as 3 lojas.

Sem historico por decisao de produto: cada coleta SUBSTITUI a anterior.
"""
from __future__ import annotations

import re
from datetime import date

from .. import store
from ..normalize import canonicalize

SITES = ("amazon", "mercadolivre", "magazineluiza")

# Num titulo de anuncio o modelo vem no inicio; o resto e spec/cor/variante.
_CORTE = re.compile(r"\s[-–—]\s|,|\(|\||/|\bde\s+\d|\b\d{2,4}\s?gb\b", re.IGNORECASE)


def model_from_listing(title: str) -> str:
    """Chave canonica a partir de um titulo de anuncio de marketplace."""
    head = _CORTE.split(title.strip(), maxsplit=1)[0]
    return canonicalize(head or title).canonical


def parse_lines(text: str) -> list[dict]:
    """Le linhas 'posicao~titulo~preco~reviews' de uma coleta."""
    rows = []
    for line in (text or "").strip().splitlines():
        parts = line.split("~")
        if len(parts) < 4 or not parts[0].strip().isdigit():
            continue
        rank, title, price, reviews = (p.strip() for p in parts[:4])
        rows.append({
            "rank": int(rank),
            "title": title,
            "price": float(price) if price else None,
            "reviews": int(reviews) if reviews else None,
            "canonical_model": model_from_listing(title),
        })
    return rows


def best_per_model(rows: list[dict]) -> dict:
    """Mantem, por modelo, o anuncio mais bem posicionado."""
    best: dict = {}
    for r in rows:
        c = r["canonical_model"]
        if c not in best or r["rank"] < best[c]["rank"]:
            best[c] = r
    return best


def merge_into_snapshot(site: str, rows: list[dict], snapshot: dict | None = None) -> dict:
    """Aplica a coleta de uma loja sobre o snapshot (canonical -> dados por loja)."""
    if site not in SITES:
        raise ValueError(f"site invalido: {site} (esperado {SITES})")
    snap = dict(snapshot or {})
    for c, r in best_per_model(rows).items():
        entry = snap.setdefault(c, {"canonical_model": c, "device_raw": r["title"], "sites": {}})
        entry["sites"][site] = {"rank": r["rank"], "price": r["price"], "reviews": r["reviews"]}
        entry.setdefault("device_raw", r["title"])
    return snap


def load_snapshot() -> dict:
    return store.get_cached("marketplace_snapshot") or {}


def save_snapshot(snap: dict) -> None:
    store.set_cached("marketplace_snapshot", snap)
    store.set_cached("marketplace_snapshot_at", date.today().isoformat())


def to_rankings(canonical_model: str, snap: dict | None = None) -> list[dict]:
    """Formato que o app usa na tabela de Rankings (uma linha por loja)."""
    snap = snap if snap is not None else load_snapshot()
    entry = snap.get(canonical_model)
    if not entry:
        return []
    out = []
    for site in SITES:
        d = (entry.get("sites") or {}).get(site)
        if not d:
            continue
        out.append({"store": site,
                    "position": f"Top #{d['rank']}" if d.get("rank") else "-",
                    "value": d.get("price"), "reviews": d.get("reviews")})
    return out
