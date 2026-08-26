"""Provedor de busca de noticias de lancamento.

Hoje le sinais de um cache semeado por busca manual (data/news_cache.json).
Em producao, `refresh` deve rodar diariamente: buscar noticias online (API de
busca) e/ou usar o proxy de IA com navegacao, gravando os sinais no cache no
mesmo formato. O restante do sistema nao muda.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from .. import store
from ..config import DATA_DIR

NEWS_CACHE_PATH = DATA_DIR / "news_cache.json"   # runtime (busca web real)
NEWS_SEED_PATH = DATA_DIR / "news_seed.json"     # base curada (somente leitura)


def _load_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _is_web(cache: dict) -> bool:
    """True se o cache veio de busca web real (nao do modo-conhecimento)."""
    return str((cache or {}).get("_meta", {}).get("mode", "")).startswith("busca web")


def load_news_cache_raw(path: Path = NEWS_CACHE_PATH) -> dict:
    """Retorna a base de sinais.

    Prioriza resultados de BUSCA WEB real (quando houver); caso contrario usa a
    BASE CURADA (news_seed.json). O modo-conhecimento do agente NAO e usado como
    fonte (ele nao conhece datas novas e so degradaria os dados).
    """
    stored = store.get_cached("news_cache") if store.is_supabase() else _load_file(path)
    if _is_web(stored):
        return stored
    return _load_file(NEWS_SEED_PATH)


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


# --- Criterio de busca -------------------------------------------------------
# O que muda a precisao da pesquisa nao e o provedor, e a QUERY. Sem palavra-chave
# de data, a busca devolve review/preco/ficha tecnica e o sinal de lancamento se
# perde no meio. "release date" e o termo que os veiculos (inclusive os BR) usam
# no titulo quando cravam a data; os termos em PT-BR trazem a data do Brasil, que
# e a que interessa aqui.
LAUNCH_KEYWORDS = ("release date", "data de lancamento")
PRIMARY_KEYWORD = LAUNCH_KEYWORDS[0]

# Consultas complementares aplicadas a cada device (a 1a busca a data oficial,
# a 2a a data brasileira, a 3a o "ja esta a venda?").
_QUERY_TEMPLATES = (
    '{device} "' + LAUNCH_KEYWORDS[0] + '"',
    "{device} " + LAUNCH_KEYWORDS[1] + " Brasil",
    "{device} lancamento Brasil preco disponibilidade",
)


def _ascii_low(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def enrich_query(query: str) -> str:
    """Acrescenta a palavra-chave de data a um criterio de busca ja existente.

    Adiciona so "release date" (entre aspas, como frase exata). Empilhar tambem o
    termo em PT deixaria a consulta restrita demais — a versao brasileira ja tem
    uma consulta so dela em `_QUERY_TEMPLATES`. Idempotente e insensivel a acento.
    """
    query = (query or "").strip()
    if not query or PRIMARY_KEYWORD in _ascii_low(query):
        return query
    return f'{query} "{PRIMARY_KEYWORD}"'


def build_queries(device: str) -> list[str]:
    """Consultas de busca para descobrir a data de lancamento de UM device."""
    device = (device or "").strip()
    if not device:
        return []
    return [t.format(device=device) for t in _QUERY_TEMPLATES]


def queries_for(device: str, query: str = "") -> list[str]:
    """Criterios de busca de um device, sempre com as palavras-chave de data.

    Se a watchlist trouxer uma query manual, ela vem primeiro (enriquecida);
    as consultas padrao entram em seguida, sem repetir.
    """
    out: list[str] = []
    seen: set[str] = set()
    for q in [enrich_query(query)] + build_queries(device):
        q = (q or "").strip()
        key = _ascii_low(q)
        if not q or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def search_all(search_fn, queries: list[str], per_query: int = 8) -> list[dict]:
    """Roda varias consultas e junta os resultados, deduplicados por URL/titulo."""
    results: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        try:
            found = search_fn(q) or []
        except Exception as e:  # uma query ruim nao pode derrubar as outras
            print(f"[websearch] falha na busca '{q}': {e}")
            continue
        for r in found[:per_query]:
            key = _ascii_low(str(r.get("url") or "") or str(r.get("title") or ""))
            if not key or key in seen:
                continue
            seen.add(key)
            results.append({**r, "query": q})
    return results


def get_search_provider(cfg=None):
    """Retorna uma funcao de busca web (query -> list[{title,url,snippet}]) ou None.

    A funcao recebe a query pronta (montada por `queries_for`, ja com as palavras-
    chave de data) — nao precisa montar criterio nenhum, so consultar e devolver.

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
