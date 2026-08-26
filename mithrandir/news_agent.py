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
from .collectors.websearch import (BULK_QUERIES, NEWS_CACHE_PATH,
                                   get_search_provider, load_news_cache_raw,
                                   queries_for, save_news_cache, search_all)
from .config import DATA_DIR, load_config
from .normalize import canonicalize

WATCHLIST_PATH = DATA_DIR / "watchlist.json"

# Distingue "nao passei search_fn" (usa o provedor) de "passei None" (sem busca).
_AUTO = object()

_AI_TIMEOUT = 35   # s por device (o Vercel corta a funcao inteira em 60s)

# Sem "query" fixa: quem monta o criterio de busca e `queries_for`, que sempre
# injeta as palavras-chave de data ("release date", "data de lancamento").
DEFAULT_WATCHLIST = [
    {"device": "Samsung Galaxy S26 FE"},
    {"device": "Apple iPhone 18 Pro"},
]


def watchlist_from_base(top_n: int = 16, recent_months: int = 3,
                        per_brand: int = 4) -> list[dict]:
    """Deriva o que pesquisar dos modelos que mais vendem HOJE na nossa base.

    Ranqueia por vendas RECENTES (ultimos meses), nao pelo total historico: a
    numeracao nao indica atualidade (o Galaxy A73 e mais antigo que o A56) e
    linhas descontinuadas acumulam volume passado. Para cada modelo do topo,
    projeta a proxima geracao (A56 -> A57, iPhone 17 Pro Max -> 18 Pro Max).

    Ha uma cota por marca (`per_brand`): so por volume, Apple/Samsung tomariam
    todas as vagas e marcas menores nunca seriam vigiadas — foi exatamente assim
    que a Motorola ficou fora do radar ate o G86 virar sucesso.
    """
    from .collectors.launch_calendar import _next_gen_name
    from .internal_bi import load_catalog, load_internal_records, load_monthly_sales

    monthly = load_monthly_sales()
    records = load_internal_records()
    # Ja conhecidos: nao adianta "descobrir" um modelo que ja esta na base/catalogo
    known = {r["canonical_model"] for r in records} | load_catalog()

    ranked = []
    for r in records:
        gen, name = r.get("generation") or 0, r.get("device") or r.get("canonical_model", "")
        if not gen or not name:
            continue
        if "/" in name:
            continue  # capa combinada ("iPhone 13/14") nao tem "proxima geracao"
        if not r.get("brand"):
            continue  # sem marca a busca fica ambigua ("A33 5G" de quem?)
        series = monthly.get(r["canonical_model"]) or []
        recent = sum(series[-recent_months:]) if series else 0
        if series and recent <= 0:
            continue  # linha sem venda recente = descontinuada
        ranked.append((recent or r.get("units", 0), r, gen, name))

    out, seen, by_brand = [], set(), {}
    for recent, r, gen, name in sorted(ranked, key=lambda t: -t[0]):
        nxt = _next_gen_name(name, gen)
        if not nxt or "(proximo)" in nxt:
            continue
        key = canonicalize(nxt).canonical
        if key in seen or key in known:
            continue  # a "proxima geracao" ja existe na base -> nao e novidade
        brand = r.get("brand") or "?"
        if by_brand.get(brand, 0) >= per_brand:
            continue  # cota da marca cheia: da vez para marcas menores
        seen.add(key)
        by_brand[brand] = by_brand.get(brand, 0) + 1
        out.append({
            "device": nxt,
            "brand": brand,
            "base_device": name,
            "base_recent_units": recent,
        })
        if len(out) >= top_n:
            break
    return out


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    """Watchlist = fixadas manualmente (watchlist.json) + derivadas da base.

    A base manda no que pesquisar; o arquivo serve para fixar casos extras.
    """
    manual: list[dict] = []
    if path.exists():
        try:
            manual = json.loads(path.read_text(encoding="utf-8")) or []
        except json.JSONDecodeError:
            manual = []

    merged, seen = [], set()
    for item in list(manual) + watchlist_from_base():
        key = canonicalize(item.get("device", "")).canonical
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged or DEFAULT_WATCHLIST


def _signals_from_search(ai: AIClient, device: str, results: list[dict]) -> list[dict]:
    evidence = "\n".join(
        f"- [publicado em {r.get('published') or '?'}] {r.get('title','')} "
        f"({r.get('url','')}): {r.get('snippet','')}" for r in results
    ) or "(sem resultados)"
    prompt = (
        f"Resultados de busca sobre o lancamento do {device}:\n" + evidence + "\n\n"
        "Extraia ate 4 sinais objetivos sobre a data de lancamento.\n"
        "Regras:\n"
        "1) Prefira resultados com DATA explicita (dia/mes/ano ou mes/ano); descarte "
        "review, preco e ficha tecnica sem data.\n"
        "2) Copie a data como ela aparece no resultado — nao arredonde nem deduza "
        "pela geracao anterior. Complete o ano pela data de publicacao da noticia.\n"
        "3) Diga SEMPRE de que data se trata, com estas palavras:\n"
        "   - 'anuncio oficial' = evento/apresentacao (ex.: 'Galaxy Event em 27/08');\n"
        "   - 'disponibilidade no Brasil' = quando chega as lojas brasileiras.\n"
        "   Sao coisas diferentes e as duas interessam — nao troque uma pela outra.\n"
        "4) Noticia mais RECENTE (veja a data de publicacao) vence rumor antigo; se "
        "houver confirmacao oficial, marque com 'confirmado'.\n"
        "5) Se nenhum resultado trouxer data, devolva uma lista vazia.\n"
        "Responda SOMENTE JSON: "
        '{"signals":[{"source":"veiculo","text":"frase com a data/situacao","url":"link"}]}'
    )
    # timeout curto: a rodada inteira do agente tem que caber nos 60s do Vercel,
    # e um device lento nao pode derrubar a gravacao dos outros (o save e no fim)
    return ai.complete_json(prompt, timeout=_AI_TIMEOUT,
                            system="Voce coleta sinais de lancamento de smartphones.").get("signals", [])


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
            # varias consultas por device, todas com palavra-chave de data
            results = search_all(search_fn, queries_for(
                item["device"], item.get("query", ""), limit=BULK_QUERIES))
            return _signals_from_search(ai, item["device"], results)
        return _signals_from_knowledge(ai, item["device"])
    except Exception as e:
        print(f"[agent] falha em {item['device']}: {e}")
        return []


def refresh_news_cache(ai: AIClient | None = None, search_fn=_AUTO,
                       watchlist: list[dict] | None = None,
                       path: Path = NEWS_CACHE_PATH) -> list[str]:
    """Atualiza o news_cache para toda a watchlist. Retorna os devices atualizados.

    `search_fn` omitido = usa o provedor configurado; `search_fn=None` = sem busca
    (o agente vira no-op). Sao situacoes diferentes, por isso o sentinela.
    """
    cfg = load_config()
    ai = ai or AIClient(cfg.ai)
    if not ai.available:
        raise RuntimeError("Proxy de IA nao configurado — o agente precisa do proxy.")
    if search_fn is _AUTO:
        search_fn = get_search_provider(cfg)
    if search_fn is None:
        # Sem API de busca web, o modo-conhecimento nao conhece datas novas e so
        # degradaria a base curada. Nao faz nada ate uma busca real ser ligada.
        print("[agent] sem API de busca web — mantendo a base curada (news_seed.json).")
        return []
    watchlist = watchlist or load_watchlist()

    # Chamadas em paralelo. Cada device custa ~25s (3 buscas + 1 chamada ao proxy,
    # que e a parte lenta), e o Vercel corta em 60s: com 6 workers a watchlist de
    # 16 daria 3 rodadas e estouraria. Uma rodada so, todos de uma vez.
    with ThreadPoolExecutor(max_workers=max(1, min(16, len(watchlist)))) as ex:
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
