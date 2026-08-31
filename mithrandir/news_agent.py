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
import time
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

# Teto da watchlist: cada device custa buscas no Google + 1 chamada ao proxy.
# Com 16 a rodada ja levava ~45s dos 60s disponiveis.
MAX_WATCHLIST = 20

# Teto de tempo da rodada. O cron do Vercel tem 60s para o agente MAIS o
# recalculo do calendario, medido em 26,5s (e que cresce junto com a watchlist).
# Com 35s aqui o total dava 61,5s e a funcao era cortada ANTES do save.
# O que nao couber fica para a proxima rodada: como cada rodada parte do cache
# anterior, rodando diariamente a watchlist inteira e coberta em poucos dias.
BUDGET_SECONDS = 22.0

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


def gocase_recent_models(months: int = 12, today=None) -> dict:
    """Modelos para os quais a GOCASE passou a vender capinha no ultimo ano.

    canonical -> unidades vendidas. Duas fontes, porque nenhuma sozinha cobre a
    janela de 12 meses:

    A) **estreia na nossa serie de vendas** (`cases_started_selling`): capinha que
       comecou a vender dentro da janela da planilha. Preciso, mas a planilha so
       guarda o ANO CORRENTE — hoje, ~6 meses;
    B) **capinha nossa de aparelho recente**: temos o modelo na base E o aparelho
       estreou na loja ha menos de `months` (`online_date` da coleta da Amazon).
       Cobre o pedaco que (A) nao alcanca. E o caso do Galaxy A17: a capinha
       saiu em 09/2025, fora da janela da planilha, mas o aparelho estreou nessa
       data e nos temos capinha dele.

    ⚠️ (B) e aproximacao: assume que a capinha saiu perto do lancamento do
    aparelho. O jeito certo e uma data de lancamento de capinha vinda do
    e-commerce — ver DEV.md §9.
    """
    from .collectors.sorftime import recent_launches
    from .internal_bi import cases_started_selling, load_internal_records

    nossos = {r["canonical_model"]: (r.get("units") or 0) for r in load_internal_records()}
    saida = {c: nossos.get(c, 0) for c in cases_started_selling()}          # (A)
    for o in recent_launches(months, today):                                # (B)
        canon = o.get("canonical_model") or ""
        if canon in nossos:
            saida[canon] = nossos[canon]
    return saida


def watchlist_from_launches(months: int = 12, top_n: int = 12,
                            today=None) -> list[dict]:
    """Sucessor do aparelho de cada capinha que a Gocase lancou no ultimo ano.

    Ex.: lancamos capinha do Galaxy A17 -> vigiamos o A18. E o criterio que o
    negocio pediu, e e diferente de `watchlist_from_base` (que ranqueia por
    volume de venda, sem olhar quando a capinha entrou).

    Leva junto `predecessor` e `predecessor_date`: sem noticia de data, o
    estimador usa a data de lancamento do PREDECESSOR no ano seguinte (ver
    `launch_estimator.predecessor_baseline`).

    A ordem e por VENDA da capinha: quando ha mais candidatos que vagas, vigiar
    o sucessor do que mais vende rende mais.
    """
    from .collectors.launch_calendar import _next_gen_name
    from .internal_bi import load_catalog

    conhecidos = load_catalog()
    saida, vistos = [], set()
    for canon, unidades in sorted(gocase_recent_models(months, today).items(),
                                  key=lambda kv: -kv[1]):
        parsed = canonicalize(canon)
        if not parsed.generation or not parsed.brand:
            continue                      # sem geracao nao da para projetar sucessor
        nxt = _next_gen_name(canon, parsed.generation)
        if not nxt or "(proximo)" in nxt:
            continue
        chave = canonicalize(nxt).canonical
        if chave in vistos or chave in conhecidos:
            continue                      # ja temos capinha do sucessor
        vistos.add(chave)
        saida.append({
            "device": nxt,
            "brand": parsed.brand,
            "predecessor": canon,
            "predecessor_units": unidades,
        })
        if len(saida) >= top_n:
            break
    return saida


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    """Watchlist = fixadas no arquivo + sucessores de lancamento recente + top de venda.

    Tres fontes, nessa ordem de prioridade (a primeira que traz um device manda):

    1. `watchlist.json` — casos que o analista quis fixar;
    2. **lancamento recente** (`watchlist_from_launches`) — estreou na loja nos
       ultimos 12 meses, entao a proxima geracao esta a caminho;
    3. **venda** (`watchlist_from_base`) — os que mais vendem capinha hoje.

    O total e limitado por `MAX_WATCHLIST`: cada device custa buscas + uma
    chamada ao proxy, e a rodada inteira do agente tem os 60s do Vercel.
    """
    manual: list[dict] = []
    if path.exists():
        try:
            manual = json.loads(path.read_text(encoding="utf-8")) or []
        except json.JSONDecodeError:
            manual = []

    merged, seen = [], set()
    for item in list(manual) + watchlist_from_launches() + watchlist_from_base():
        key = canonicalize(item.get("device", "")).canonical
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= MAX_WATCHLIST:
            break
    return merged or DEFAULT_WATCHLIST


def _signals_from_search(ai: AIClient, device: str, results: list[dict],
                         timeout: float = _AI_TIMEOUT) -> list[dict]:
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
    return ai.complete_json(prompt, timeout=max(5, int(timeout)),
                            system="Voce coleta sinais de lancamento de smartphones.").get("signals", [])


def _signals_from_knowledge(ai: AIClient, device: str) -> list[dict]:
    prompt = (
        f"Com base no seu conhecimento, descreva a situacao de lancamento NO BRASIL do {device}: "
        "data confirmada ou mais provavel, e se ja foi lancado. Cite datas concretas quando souber. "
        'Responda SOMENTE JSON: {"signals":[{"source":"conhecimento do modelo",'
        '"text":"frase com a data/situacao","url":""}]} com 1 ou 2 itens.'
    )
    return ai.complete_json(prompt, system="Voce e um analista de lancamentos de smartphones no Brasil.").get("signals", [])


def _collect_for(ai: AIClient, item: dict, search_fn, deadline: float | None = None) -> list[dict]:
    if deadline is not None and time.monotonic() > deadline:
        # Estourou o orcamento: devolve vazio e o device MANTEM o sinal anterior.
        # Melhor perder alguns devices desta rodada do que a funcao ser cortada
        # pelo Vercel antes do save (que e no fim) e perder a rodada inteira.
        return []
    try:
        if search_fn:
            # varias consultas por device, todas com palavra-chave de data
            results = search_all(search_fn, queries_for(
                item["device"], item.get("query", ""), limit=BULK_QUERIES))
            # o proxy nao pode passar do orcamento da rodada
            restante = _AI_TIMEOUT if deadline is None else deadline - time.monotonic()
            return _signals_from_search(ai, item["device"], results, restante)
        return _signals_from_knowledge(ai, item["device"])
    except Exception as e:
        print(f"[agent] falha em {item['device']}: {e}")
        return []


def refresh_news_cache(ai: AIClient | None = None, search_fn=_AUTO,
                       watchlist: list[dict] | None = None,
                       path: Path = NEWS_CACHE_PATH,
                       budget_seconds: float = BUDGET_SECONDS) -> list[str]:
    """Atualiza o news_cache para toda a watchlist. Retorna os devices atualizados.

    `search_fn` omitido = usa o provedor configurado; `search_fn=None` = sem busca
    (o agente vira no-op). Sao situacoes diferentes, por isso o sentinela.

    `budget_seconds` limita a rodada. O que nao coube fica para a proxima: como
    cada rodada parte do cache anterior, a cobertura se acumula. Sem isso, com a
    watchlist em 20 devices (~50s) mais o recalculo, o cron do Vercel era cortado
    aos 60s ANTES do save e a rodada inteira se perdia.
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
    deadline = time.monotonic() + budget_seconds
    with ThreadPoolExecutor(max_workers=max(1, min(16, len(watchlist)))) as ex:
        results = list(ex.map(
            lambda it: (it, _collect_for(ai, it, search_fn, deadline)), watchlist))
    if any(not sig for _, sig in results) and time.monotonic() > deadline:
        print(f"[agent] orcamento de {budget_seconds:.0f}s estourado; "
              "os devices restantes ficam para a proxima rodada.")

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
