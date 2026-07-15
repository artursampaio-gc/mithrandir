"""Provedor de busca de noticias de lancamento.

Hoje le sinais de um cache semeado por busca manual (data/news_cache.json).
Em producao, `refresh` deve rodar diariamente: buscar noticias online (API de
busca) e/ou usar o proxy de IA com navegacao, gravando os sinais no cache no
mesmo formato. O restante do sistema nao muda.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import store
from ..config import DATA_DIR

NEWS_CACHE_PATH = DATA_DIR / "news_cache.json"


def _load_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_news_cache_raw(path: Path = NEWS_CACHE_PATH) -> dict:
    """Le o cache completo, incluindo a chave _meta.

    No Supabase, usa o cache gravado; se ainda vazio, cai no arquivo semeado
    (empacotado no deploy) como base inicial.
    """
    if store.is_supabase():
        cached = store.get_cached("news_cache")
        return cached if cached else _load_file(path)
    return _load_file(path)


def save_news_cache(cache: dict, path: Path = NEWS_CACHE_PATH) -> None:
    if store.is_supabase():
        store.set_cached("news_cache", cache)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def load_news_cache(path: Path = NEWS_CACHE_PATH) -> dict:
    data = load_news_cache_raw(path)
    data.pop("_meta", None)
    return data


def get_search_provider(cfg=None):
    """Retorna uma funcao de busca web (query -> list[{title,url,snippet}]) ou None.

    Hoje retorna None (sem API de busca configurada): o agente cai no modo
    'conhecimento do modelo'. Quando a empresa liberar uma API de busca, implemente
    aqui (lendo credenciais do cfg/env) para o agente passar a vasculhar a web.
    """
    return None


def signals_for(canonical: str, cache: dict | None = None) -> list[dict]:
    cache = cache if cache is not None else load_news_cache()
    entry = cache.get(canonical)
    return entry.get("signals", []) if entry else []


def known_devices(cache: dict | None = None) -> dict:
    """Mapa canonical -> nome de exibicao dos devices com noticias."""
    cache = cache if cache is not None else load_news_cache()
    return {k: v.get("device", k) for k, v in cache.items()}
