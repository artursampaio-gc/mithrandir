"""Busca web de noticias de lancamento.

Duas responsabilidades:

  1) MONTAR O CRITERIO de busca (`queries_for`): sem palavra-chave de data a
     pesquisa devolve review/preco/ficha tecnica e o sinal de lancamento se perde.
  2) EXECUTAR a busca (`get_search_provider`): hoje via Google Noticias (RSS
     publico, sem chave de API).

Os sinais coletados vao para o cache (`data/news_cache.json`) e alimentam o
Calendario. A base curada (`news_seed.json`) e o fallback quando nao ha busca.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from .. import store
from .._http import request_text
from ..config import DATA_DIR, get_setting as _get_setting

_UA = "Mozilla/5.0 (compatible; Mithrandir/0.1)"

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
#
# SEM ASPAS. Medido no Google News: `S26 FE "release date"` como frase exata
# devolveu 3 resultados (e nenhum do aparelho); sem aspas, 100 resultados —
# incluindo a manchete que crava a data. Aspas restringem, nao qualificam.
_QUERY_TEMPLATES = (
    "{device} " + LAUNCH_KEYWORDS[0],
    "{device} " + LAUNCH_KEYWORDS[1] + " Brasil",
    "{device} lancamento Brasil preco disponibilidade",
)

# Quantas consultas por device quando a varredura e em LOTE (agente na watchlist
# inteira). Com as 3 dava ~48 buscas de uma vez e o Google cortava com 429 no meio
# — devices sumiam da atualizacao. As 2 primeiras cobrem data oficial + Brasil.
BULK_QUERIES = 2


def _ascii_low(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def enrich_query(query: str) -> str:
    """Acrescenta a palavra-chave de data a um criterio de busca ja existente.

    Adiciona so "release date", solto (ver _QUERY_TEMPLATES: aspas restringem).
    Empilhar tambem o termo em PT deixaria a consulta estreita demais — a versao
    brasileira ja tem uma consulta so dela. Idempotente e insensivel a acento.
    """
    query = (query or "").strip()
    if not query or PRIMARY_KEYWORD in _ascii_low(query):
        return query
    return f"{query} {PRIMARY_KEYWORD}"


def build_queries(device: str) -> list[str]:
    """Consultas de busca para descobrir a data de lancamento de UM device."""
    device = (device or "").strip()
    if not device:
        return []
    return [t.format(device=device) for t in _QUERY_TEMPLATES]


def queries_for(device: str, query: str = "", limit: int | None = None) -> list[str]:
    """Criterios de busca de um device, sempre com as palavras-chave de data.

    Se a watchlist trouxer uma query manual, ela vem primeiro (enriquecida);
    as consultas padrao entram em seguida, sem repetir.

    `limit` corta a lista: o agente varre a watchlist inteira de uma vez e o
    Google passa a devolver 429 quando o volume sobe (ver BULK_QUERIES), enquanto
    a pesquisa de UM device pode usar todas.
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
    return out[:limit] if limit else out


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


# --- Provedor de busca: Google News RSS --------------------------------------
# Nao precisa de API key nem contrato: e o feed publico de busca do Google
# Noticias. Devolve manchete + veiculo + DATA DE PUBLICACAO, que e exatamente o
# material de que o estimador precisa (e o pubDate ainda permite priorizar a
# noticia mais recente sobre o rumor antigo).
_GNEWS_URL = "https://news.google.com/rss/search"
_LOCALE_BR = {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
_LOCALE_US = {"hl": "en-US", "gl": "US", "ceid": "US:en"}
# Marcas de que a consulta esta em portugues -> vale procurar no Google BR
_PT_MARKERS = ("lancamento", "preco", "disponibilidade", "brasil", "data de")

_TAG_RE = re.compile(r"<[^>]+>")
_SEARCH_CACHE: dict[str, list[dict]] = {}

# Rate limit global: sem isso o Google devolve 429 no meio da rodada do agente.
_RATE_LOCK = threading.Lock()
_MIN_INTERVAL = 0.35   # segundos entre buscas (qualquer thread)
_RETRY_SLEEP = 2.0     # espera antes da unica retentativa no 429
_last_call = [0.0]


def clear_search_cache() -> None:
    _SEARCH_CACHE.clear()


def _locale_for(query: str) -> dict:
    """Consulta em PT vai para o Google BR; em EN, para o americano.

    Sem isso a consulta em ingles cai no indice brasileiro e volta pobre — e e a
    consulta em ingles ("release date") que traz a data oficial cravada.
    """
    low = _ascii_low(query)
    return _LOCALE_BR if any(m in low for m in _PT_MARKERS) else _LOCALE_US


def _pub_iso(pub_date: str) -> str:
    """'Thu, 20 Aug 2026 12:00:00 GMT' -> '2026-08-20' (ou '' se nao parsear)."""
    try:
        return parsedate_to_datetime(pub_date).date().isoformat()
    except Exception:
        return ""


def _throttled_get(url: str, timeout: int) -> str:
    """GET com passo minimo entre chamadas e 1 retentativa no 429.

    O agente dispara ~48 buscas de uma vez (16 devices x 3 consultas) e o Google
    devolvia 429 no meio da rodada — devices sumiam da atualizacao em silencio.
    O espacamento e global (todas as threads passam por este lock).
    """
    for tentativa in (1, 2):
        with _RATE_LOCK:
            espera = _MIN_INTERVAL - (time.monotonic() - _last_call[0])
            if espera > 0:
                time.sleep(espera)
            _last_call[0] = time.monotonic()
        try:
            return request_text(url, headers={"User-Agent": _UA}, timeout=timeout)
        except Exception as e:
            if tentativa == 1 and "429" in str(e):
                time.sleep(_RETRY_SLEEP)
                continue
            raise
    return ""


def google_news_search(query: str, limit: int = 8, timeout: int = 20) -> list[dict]:
    """Busca no Google Noticias. Retorna [{title,url,snippet,published}]."""
    if query in _SEARCH_CACHE:
        return _SEARCH_CACHE[query]
    url = f"{_GNEWS_URL}?" + urllib.parse.urlencode({"q": query, **_locale_for(query)})
    body = _throttled_get(url, timeout)
    root = ET.fromstring(body.encode("utf-8"))
    out: list[dict] = []
    for item in list(root.iter("item"))[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        published = _pub_iso((item.findtext("pubDate") or "").strip())
        snippet = _TAG_RE.sub(" ", item.findtext("description") or "")
        out.append({
            "title": title,
            "url": (item.findtext("link") or "").strip(),
            # o veiculo vem no fim do titulo ("... - Tecnoblog")
            "source": (item.findtext("source") or title.rsplit(" - ", 1)[-1]).strip(),
            "snippet": " ".join(snippet.split())[:300],
            "published": published,
        })
    _SEARCH_CACHE[query] = out
    return out


def get_search_provider(cfg=None):
    """Retorna uma funcao de busca web (query -> list[{title,url,snippet}]) ou None.

    A funcao recebe a query pronta (montada por `queries_for`, ja com as palavras-
    chave de data) — nao precisa montar criterio nenhum, so consultar e devolver.

    Hoje usa o Google Noticias (RSS publico, sem chave). Desligue com
    MITHRANDIR_WEBSEARCH=off; troque aqui por uma API paga se a empresa liberar.
    """
    if str(_get_setting("websearch", "on")).lower() in ("off", "0", "false", "no"):
        return None
    return google_news_search


def signals_for(canonical: str, cache: dict | None = None) -> list[dict]:
    cache = cache if cache is not None else load_news_cache()
    entry = cache.get(canonical)
    return entry.get("signals", []) if entry else []


def known_devices(cache: dict | None = None) -> dict:
    """Mapa canonical -> nome de exibicao dos devices com noticias."""
    cache = cache if cache is not None else load_news_cache()
    return {k: v.get("device", k) for k, v in cache.items()}
