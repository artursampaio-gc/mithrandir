"""Agente de scouting de noticias (RF-02).

Para cada device da watchlist, busca sinais de data de lancamento e os grava no
news_cache.json (que alimenta o Calendario). Dois modos:

  - COM API de busca (search_fn): vasculha a web e o proxy de IA extrai os sinais.
  - SEM API de busca (fallback atual): usa o conhecimento do proxy (gpt-5.5) para
    descrever a situacao de lancamento. Rotulado como '(conhecimento do modelo)'
    para deixar claro que nao e noticia ao vivo.

Rode manualmente com `python -m mithrandir agent` ou agende para rodar diariamente.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .ai.proxy import AIClient
from .collectors.websearch import (NEWS_CACHE_PATH, get_search_provider,
                                   load_news_cache_raw, save_news_cache)
from .config import DATA_DIR, load_config
from .normalize import canonicalize

WATCHLIST_PATH = DATA_DIR / "watchlist.json"

DEFAULT_WATCHLIST = [
    {"device": "Samsung Galaxy S26 FE", "query": "Samsung Galaxy S26 FE lancamento Brasil"},
    {"device": "Apple iPhone 18 Pro", "query": "iPhone 18 Pro lancamento data 2026"},
]


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return DEFAULT_WATCHLIST


def _signals_from_search(ai: AIClient, query: str, results: list[dict]) -> list[dict]:
    evidence = "\n".join(
        f"- {r.get('title','')} ({r.get('url','')}): {r.get('snippet','')}" for r in results
    ) or "(sem resultados)"
    prompt = (
        "Resultados de busca sobre lancamento de celular:\n" + evidence + "\n\n"
        "Extraia ate 3 sinais objetivos sobre a data de lancamento NO BRASIL. "
        "Responda SOMENTE JSON: "
        '{"signals":[{"source":"veiculo","text":"frase com a data/situacao","url":"link"}]}'
    )
    return ai.complete_json(prompt, system="Voce coleta sinais de lancamento de smartphones.").get("signals", [])


def _signals_from_knowledge(ai: AIClient, device: str) -> list[dict]:
    prompt = (
        f"Com base no seu conhecimento, descreva a situacao de lancamento NO BRASIL do {device}: "
        "data confirmada ou mais provavel, e se ja foi lancado. Cite datas concretas quando souber. "
        'Responda SOMENTE JSON: {"signals":[{"source":"conhecimento do modelo",'
        '"text":"frase com a data/situacao","url":""}]} com 1 ou 2 itens.'
    )
    return ai.complete_json(prompt, system="Voce e um analista de lancamentos de smartphones no Brasil.").get("signals", [])


def _collect_for(ai: AIClient, item: dict, search_fn) -> list[dict]:
    try:
        if search_fn:
            results = search_fn(item.get("query", item["device"]))
            return _signals_from_search(ai, item.get("query", item["device"]), results)
        return _signals_from_knowledge(ai, item["device"])
    except Exception as e:
        print(f"[agent] falha em {item['device']}: {e}")
        return []


def refresh_news_cache(ai: AIClient | None = None, search_fn=None,
                       watchlist: list[dict] | None = None,
                       path: Path = NEWS_CACHE_PATH) -> list[str]:
    """Atualiza o news_cache para toda a watchlist. Retorna os devices atualizados."""
    cfg = load_config()
    ai = ai or AIClient(cfg.ai)
    if not ai.available:
        raise RuntimeError("Proxy de IA nao configurado — o agente precisa do proxy.")
    search_fn = search_fn if search_fn is not None else get_search_provider(cfg)
    watchlist = watchlist or load_watchlist()

    # Chamadas em paralelo (o proxy e lento)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda it: (it, _collect_for(ai, it, search_fn)), watchlist))

    raw = load_news_cache_raw(path)
    meta = raw.get("_meta", {})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated: list[str] = []
    for item, signals in results:
        if not signals:
            continue
        canon = canonicalize(item["device"]).canonical
        raw[canon] = {"device": item["device"], "signals": signals, "updated_at": now}
        updated.append(item["device"])

    meta["last_agent_run"] = now
    meta["mode"] = "busca web + IA" if search_fn else "conhecimento do modelo (sem API de busca)"
    raw["_meta"] = meta
    save_news_cache(raw, path)
    return updated
