"""Curva de largada da capinha: os PRIMEIROS 6 meses de venda de cada modelo.

Por que isso e diferente dos "ultimos 6 meses" que o app usava: o breakeven de um
molde NOVO tem que ser comparado com a LARGADA de um similar, nao com a venda
madura ou ja em declinio dele. O iPhone 16 vendeu [122, 659, 1412, 1183, 905,
703] nos seis primeiros meses — a curva de subida. A media dos ultimos seis meses
dele hoje diz outra coisa completamente, e projetar molde em cima disso subestima
o pico e superestima a cauda.

Fonte: `consolidated_line_items` do site (`material_category = 'case'`), que tem
historico desde 2022-08. O `material` e `<tipo>-<slug do aparelho>`, entao o slug
sai do fim e casa com `spree_devices` (que da o nome, para normalizar).

⚠️ O historico comeca em 2022-08: para capinha lancada ANTES disso, o "primeiro
mes com venda" seria so o inicio da janela, nao a largada real. A consulta corta
em 2022-10 justamente por isso — modelo antigo fica de fora em vez de entrar com
numero errado.
"""
from __future__ import annotations

from .. import store
from ..normalize import canonicalize
from .marketplace import model_from_listing

SALES_KEY = "case_first_months"          # canonical -> {"m0": "AAAA-MM-01", "serie": [int]}
CACHE_TITULOS = "catalog_title_keys"     # mesmo contexto do catalogo (nome do site)
MESES = 6


def parse_rows(rows: list, chaves: dict | None = None,
               descartados: list | None = None) -> dict:
    """Linhas do site -> {canonical: {"m0", "serie"}}.

    Um mesmo modelo pode vir em duas linhas (SKUs distintos do site: o iPhone 15
    Pro Max aparece com duas series). Quando o mes inicial bate, as series SOMAM,
    porque sao o mesmo aparelho; quando nao bate, fica a de maior volume — somar
    series desalinhadas no tempo inventaria uma curva que nao existiu.
    """
    chaves = chaves or {}
    out: dict[str, dict] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nome = str(r.get("name") or "").strip()
        m0 = str(r.get("primeiro_mes") or "").strip()[:10]
        serie = [int(v) for v in (r.get("serie") or []) if isinstance(v, (int, float))]
        if not nome or len(m0) != 10 or not serie:
            continue
        canon = chaves.get(nome)
        if canon is None:                        # a IA nao opinou -> regra
            canon = model_from_listing(nome) if canonicalize(nome).brand else ""
        if not canon:
            if descartados is not None:
                descartados.append(nome)
            continue
        serie = serie[:MESES]
        atual = out.get(canon)
        if atual is None:
            out[canon] = {"m0": m0, "serie": serie}
        elif atual["m0"] == m0:                  # mesmo aparelho, outro SKU -> soma
            a, b = atual["serie"], serie
            n = max(len(a), len(b))
            atual["serie"] = [(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0)
                              for i in range(n)]
        elif sum(serie) > sum(atual["serie"]):   # janelas diferentes -> fica a maior
            out[canon] = {"m0": m0, "serie": serie}
    return out


def load_first_months() -> dict:
    """{canonical: {"m0", "serie"}}. Vazio enquanto nao houver ingestao."""
    return store.get_cached(SALES_KEY) or {}


def series_for(canonical: str) -> list:
    """Serie de largada de um modelo, ou [] se nao houver."""
    return (load_first_months().get(canonical) or {}).get("serie") or []


def _chaves_da_ia(rows: list, ai=None) -> dict:
    """Nome do site -> chave limpa pela IA. Compartilha o cache do catalogo:
    e a mesma origem e a mesma regra de descarte."""
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
        print(f"[case_sales] limpeza por IA indisponivel ({e}); seguindo nas regras.")
        return {}


def ingest(rows: list, ai=None) -> dict:
    """Substitui a curva de largada pela coleta recebida."""
    descartados: list[str] = []
    dados = parse_rows(rows, _chaves_da_ia(rows, ai), descartados)
    if not dados:
        raise ValueError("coleta vazia: nenhum modelo utilizavel.")
    store.set_cached(SALES_KEY, dados)
    if descartados:
        print(f"[case_sales] {len(descartados)} registro(s) fora: "
              f"{'; '.join(d[:40] for d in descartados[:3])}")
    return {"recebidos": len(rows or []), "modelos": len(dados),
            "descartados": len(descartados),
            "top": sorted(({"modelo": k, "total6": sum(v["serie"])}
                           for k, v in dados.items()),
                          key=lambda x: -x["total6"])[:5]}
