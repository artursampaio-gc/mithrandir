"""Catalogo de capinhas da Gocase (tabela `spree_devices` do site).

Responde as duas perguntas que o app errava:

  1. **"ja temos capinha do X?"** — antes vinha de um CSV de exemplo com 4 linhas
     e de inferencia pela planilha de vendas. Errava feio: o iPhone 16e era o
     candidato numero 1 e tem capinha desde 25/02/2025.
  2. **"que capinhas lancamos no ultimo ano?"** — `created_at` e a data em que o
     aparelho entrou no site, ou seja, quando a capinha saiu. Antes era
     aproximado pela data do aparelho na Amazon.

O banco do site so e alcancavel por MCP/proxy, que o app no Vercel nao chama —
mesmo desenho do Sorftime: produtor externo -> `POST /api/catalog/ingest`, e a
transformacao mora aqui.

⚠️ A ingestao vem PAGINADA de proposito. Sao 735 registros e normalizar tudo de
uma vez levou 92s, contra os 60s do Vercel. Cada pagina cabe no limite; o cache
de titulos (`normalize_ai`) faz as rodadas seguintes saírem quase de graca.
"""
from __future__ import annotations

from .. import store
from ..normalize import canonicalize
from .marketplace import model_from_listing

CATALOG_KEY = "gocase_catalog"     # canonical -> "AAAA-MM-DD" (lancamento da capinha)
CACHE_TITULOS = "catalog_title_keys"   # cache da IA, separado do de marketplace


def parse_devices(rows: list, chaves: dict | None = None,
                  descartados: list | None = None) -> dict:
    """Linhas cruas do site -> {canonical: data de lancamento da capinha}.

    Quando o mesmo modelo aparece em varios registros (o site tem "Case Infinite
    Xiaomi Redmi Note 15 Pro 5G" alem do proprio aparelho), fica a data MAIS
    ANTIGA: e quando a primeira capinha daquele modelo saiu.

    O que nao normaliza para um celular fica de fora — o catalogo tem bolsa,
    garrafa, ecobag e entrada de waitlist misturadas (231 dos 735 registros).
    """
    chaves = chaves or {}
    out: dict[str, str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nome = str(r.get("name") or "").strip()
        data = str(r.get("created_at") or "").strip()[:10]
        if not nome or len(data) != 10:
            continue
        canon = chaves.get(nome)
        if canon is None:                  # a IA nao opinou -> regra
            canon = model_from_listing(nome) if canonicalize(nome).brand else ""
        if not canon:
            if descartados is not None:
                descartados.append(nome)
            continue
        out[canon] = min(out[canon], data) if canon in out else data
    return out


def load_catalog() -> dict:
    """{canonical: data de lancamento da capinha}. Vazio se nunca houve ingestao."""
    return store.get_cached(CATALOG_KEY) or {}


def _chaves_da_ia(rows: list, ai=None) -> dict:
    """Nome do site -> chave limpa pela IA. Mesmo cache da ingestao de marketplace.

    Os nomes do site sao sujos de um jeito proprio: "Case Infinite Xiaomi Redmi
    Note 15 Pro 5G", "Xiaomi Redmi 14 Pro / X7 5G", e ate typo de cadastro
    ("Morotola G10"). Qualquer falha volta {} e a ingestao segue nas regras.

    Usa cache PROPRIO (`CACHE_TITULOS`), separado do cache da ingestao de
    marketplace: a mesma string tem resposta diferente nos dois contextos, porque
    a regra de descarte e oposta — la uma capa e ruido, aqui e o produto.
    """
    from ..normalize_ai import DESCARTE_CATALOGO, clean_titles

    try:
        if ai is None:
            from ..ai.proxy import AIClient
            from ..config import load_config
            ai = AIClient(load_config().ai)
        if not getattr(ai, "available", False):
            return {}
        nomes = [str(r.get("name") or "").strip()
                 for r in (rows or []) if isinstance(r, dict)]
        cache = store.get_cached(CACHE_TITULOS) or {}
        chaves = clean_titles(ai, [n for n in nomes if n], cache,
                              descarte=DESCARTE_CATALOGO)
        store.set_cached(CACHE_TITULOS, {**cache, **chaves})
        return chaves
    except Exception as e:
        print(f"[catalog] limpeza por IA indisponivel ({e}); seguindo nas regras.")
        return {}


def ingest(rows: list, reset: bool = False, ai=None) -> dict:
    """Aplica uma pagina do catalogo. `reset` comeca do zero (1a pagina)."""
    descartados: list[str] = []
    pagina = parse_devices(rows, _chaves_da_ia(rows, ai), descartados)
    if not pagina and not reset:
        raise ValueError("pagina vazia: nenhum device utilizavel.")

    atual = {} if reset else load_catalog()
    for canon, data in pagina.items():
        atual[canon] = min(atual[canon], data) if canon in atual else data
    store.set_cached(CATALOG_KEY, atual)

    if descartados:
        print(f"[catalog] {len(descartados)} registro(s) fora (nao sao celular): "
              f"{'; '.join(d[:40] for d in descartados[:3])}")
    return {"recebidos": len(rows or []), "modelos_na_pagina": len(pagina),
            "modelos_no_catalogo": len(atual), "descartados": len(descartados),
            "reset": bool(reset)}
