"""Coletor de tracao do Mercado Livre (RF-03).

Com credencial configurada, consulta a API oficial. Sem credencial, retorna a
amostra de mock (collectors.mock_seed) para o pipeline rodar hoje.

API oficial: https://developers.mercadolivre.com.br  (search por categoria de
celulares no site MLB). Ajuste `_search` conforme o contrato/escopo do token.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ..config import MercadoLivreConfig
from . import mock_seed

# Categoria "Celulares e Smartphones" no Mercado Livre Brasil
CATEGORY_SMARTPHONES = "MLB1055"


def _search(cfg: MercadoLivreConfig, limit: int = 50, timeout: int = 30) -> list[dict]:
    base = f"https://api.mercadolibre.com/sites/{cfg.site_id}/search"
    params = {
        "category": CATEGORY_SMARTPHONES,
        "sort": "sold_quantity_desc",
        "limit": limit,
    }
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {cfg.access_token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("results", [])


def _map_result(idx: int, r: dict) -> dict:
    """Converte um resultado da API para o formato interno de observacao."""
    reviews = (r.get("reviews") or {})
    return {
        "raw_name": r.get("title", ""),
        "brand": "",  # detectado depois pela normalizacao
        "source": "mercadolivre",
        "rank": idx + 1,
        "sold_qty": r.get("sold_quantity"),
        "review_count": reviews.get("total", 0) or 0,
        "rating": reviews.get("rating_average"),
        "price": r.get("price"),
        "offers": 1,
    }


def collect(cfg: MercadoLivreConfig) -> list[dict]:
    """Retorna observacoes de tracao (reais ou mock)."""
    if not cfg.is_configured:
        return mock_seed.marketplace_observations()
    try:
        results = _search(cfg)
        return [_map_result(i, r) for i, r in enumerate(results)]
    except Exception as e:  # falha de rede/token nao derruba o pipeline (RNF-02)
        print(f"[mercadolivre] falha na API ({e}); usando mock.")
        return mock_seed.marketplace_observations()
