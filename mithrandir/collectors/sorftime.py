"""Ingestao da coleta do Sorftime (tracao real de marketplace).

O Sorftime so e acessivel via MCP, dentro de uma sessao do Claude — o app no
Vercel nao consegue chamar a ferramenta. Entao o produtor e uma tarefa agendada
(semanal, segunda-feira) que consulta o MCP e faz POST das linhas CRUAS em
`/api/marketplace/ingest`. Toda a transformacao mora aqui: em codigo testado no
repo, e nao no prompt do agente.

Formato de entrada = a saida do `category_report` do Sorftime, sem retoque.

Um modelo aparece em varios ASINs (cor/armazenamento): o iPhone 16 tinha 7 na
coleta de 2026-08-29. O app raciocina por MODELO, entao a agregacao aqui e a
parte que importa — somar venda e guardar o melhor anuncio de cada modelo.
"""
from __future__ import annotations

from datetime import date

from .. import store
from ..normalize import canonicalize
from . import marketplace

SOURCE = "amazon"          # loja (uma das marketplace.SITES)
HISTORY_KEY = "marketplace_history"
HISTORY_WEEKS = 26         # ~6 meses de coletas semanais
OBS_KEY = "marketplace_observations"


def _int(v) -> int:
    """Sorftime manda numero como string ('6285'); campo ausente vira 0."""
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def _float(v):
    try:
        f = float(str(v).strip())
        return f if f == f else None      # descarta NaN
    except (TypeError, ValueError):
        return None


def parse_products(raw: list, descartados: list | None = None) -> list[dict]:
    """Le as linhas cruas do Sorftime e devolve so o que o app usa.

    Descarta o que nao for celular de marca conhecida. A categoria "Celulares e
    Smartphones" da Amazon BR tem intruso — o Meta Quest 3S (headset de VR) veio
    no top 100 da coleta de 2026-08-29 — e `product_category` do Sorftime vem
    vazio em 72 dos 99 anuncios, entao nao serve de filtro. A marca serve: sem
    marca reconhecida o app nao consegue casar com o BI nem sugerir capinha.

    O custo e uma marca nova (uma TCL da vida) sumir calada; por isso o que cai
    volta em `descartados`, e o resumo da ingestao mostra a contagem.
    """
    rows = []
    for i, p in enumerate(raw or []):
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or "").strip()
        if not title:
            continue
        if not canonicalize(title).brand:
            if descartados is not None:
                descartados.append(title)
            continue
        rows.append({
            "asin": str(p.get("asin") or "").strip(),
            "title": title,
            "brand": str(p.get("brand") or "").strip(),
            "sales": _int(p.get("monthly_sales_volume")),
            "amount": _float(p.get("monthly_sales_amount")) or 0.0,
            "price": _float(p.get("price")),
            "reviews": _int(p.get("review_count")),
            "rating": _float(p.get("star_rating")),
            "online_date": str(p.get("online_date") or "").strip() or None,
            "source_rank": i + 1,          # posicao como veio do Sorftime
            "canonical_model": marketplace.model_from_listing(title),
        })
    return rows


def aggregate_by_model(rows: list[dict]) -> list[dict]:
    """Junta os ASINs do mesmo modelo. Ordena por venda mensal (maior primeiro).

    - venda e faturamento SOMAM (sao variantes do mesmo aparelho);
    - avaliacoes usam o MAIOR, nao a soma: na Amazon as variantes costumam
      compartilhar as reviews do ASIN pai, entao somar contaria duas vezes;
    - preco/nota/titulo vem do ASIN mais bem colocado (o representativo);
    - `online_date` e a MAIS ANTIGA: e quando o modelo apareceu na loja.
    """
    by_model: dict[str, dict] = {}
    for r in rows:
        c = r["canonical_model"]
        if not c:
            continue
        a = by_model.get(c)
        if a is None:
            a = by_model[c] = {
                "canonical_model": c, "device_raw": r["title"], "brand": r["brand"],
                "sales": 0, "amount": 0.0, "reviews": 0, "asins": 0,
                "price": r["price"], "rating": r["rating"],
                "online_date": r["online_date"], "_best": r["source_rank"],
            }
        a["sales"] += r["sales"]
        a["amount"] += r["amount"]
        a["reviews"] = max(a["reviews"], r["reviews"])
        a["asins"] += 1
        if r["source_rank"] < a["_best"]:      # ASIN representativo do modelo
            a["_best"] = r["source_rank"]
            a["device_raw"], a["price"] = r["title"], r["price"]
            a["rating"], a["brand"] = r["rating"], r["brand"] or a["brand"]
        if r["online_date"] and (not a["online_date"] or r["online_date"] < a["online_date"]):
            a["online_date"] = r["online_date"]

    out = sorted(by_model.values(), key=lambda a: -a["sales"])
    for i, a in enumerate(out, 1):
        a["rank"] = i                          # rank do MODELO, nao do anuncio
        a.pop("_best", None)
    return out


def to_snapshot_rows(agg: list[dict]) -> list[dict]:
    """Formato que `marketplace.merge_into_snapshot` consome."""
    return [{"rank": a["rank"], "title": a["device_raw"], "price": a["price"],
             "reviews": a["reviews"], "canonical_model": a["canonical_model"]}
            for a in agg]


def to_observations(agg: list[dict]) -> list[dict]:
    """Formato de observacao de tracao que o pipeline consome.

    `sold_qty` aqui e venda mensal ESTIMADA de verdade — ate agora esse campo so
    existia no mock.
    """
    return [{
        "raw_name": a["device_raw"],
        "brand": a["brand"],
        "source": SOURCE,
        "rank": a["rank"],
        "sold_qty": a["sales"],
        "review_count": a["reviews"],
        "rating": a["rating"],
        "price": a["price"],
        "offers": a["asins"],
        "revenue": a["amount"],
        "online_date": a["online_date"],
        "canonical_model": a["canonical_model"],
    } for a in agg]


def load_observations() -> list[dict]:
    """Observacoes da ultima coleta (vazio enquanto nao houver ingestao)."""
    return store.get_cached(OBS_KEY) or []


def load_history() -> list[dict]:
    return store.get_cached(HISTORY_KEY) or []


def sales_by_model(entry: dict | None = None) -> dict:
    """canonical -> venda mensal, de uma entrada do historico."""
    return {r["canonical_model"]: r["sales"] for r in (entry or {}).get("rows", [])}


def previous_sales(collected_at: str | None = None) -> dict:
    """Venda por modelo na coleta ANTERIOR (para momentum semana a semana).

    Ignora entradas da mesma data para o reprocessamento de uma coleta nao virar
    comparacao consigo mesma (momentum zero).
    """
    hist = [h for h in load_history() if h.get("collected_at") != collected_at]
    return sales_by_model(hist[-1]) if hist else {}


def momentum_from_sales(current: int, previous: int | None) -> float | None:
    """Momentum 0-100 pela variacao de venda entre coletas. None sem base.

    Crescer 25% em uma semana ja e um sinal forte, por isso a escala satura
    rapido; 50 = estavel, para nao mexer no significado que a metrica ja tinha.
    """
    if not previous or previous <= 0:
        return None
    growth = (current - previous) / previous
    return round(max(0.0, min(100.0, 50.0 + growth * 200.0)), 1)


def ingest(raw_products: list, collected_at: str | None = None,
           source: str = SOURCE) -> dict:
    """Aplica uma coleta: agrega, grava snapshot, observacoes e historico."""
    collected_at = collected_at or date.today().isoformat()
    descartados: list[str] = []
    rows = parse_products(raw_products, descartados)
    if not rows:
        raise ValueError("coleta vazia: nenhum produto com titulo utilizavel.")
    agg = aggregate_by_model(rows)

    prev = previous_sales(collected_at)
    obs = to_observations(agg)
    for o in obs:
        m = momentum_from_sales(o["sold_qty"], prev.get(o["canonical_model"]))
        if m is not None:
            o["momentum"] = m

    snap = marketplace.merge_into_snapshot(
        source, to_snapshot_rows(agg), marketplace.load_snapshot())
    marketplace.save_snapshot(snap)
    store.set_cached(OBS_KEY, obs)

    # historico semanal: alimenta o momentum da proxima coleta e a curva de tracao
    hist = [h for h in load_history() if h.get("collected_at") != collected_at]
    hist.append({"collected_at": collected_at, "source": source,
                 "rows": [{"canonical_model": a["canonical_model"], "rank": a["rank"],
                           "sales": a["sales"], "price": a["price"]} for a in agg]})
    store.set_cached(HISTORY_KEY, hist[-HISTORY_WEEKS:])

    if descartados:
        print(f"[sorftime] {len(descartados)} anuncio(s) sem marca conhecida, "
              f"fora da ingestao: {'; '.join(t[:60] for t in descartados[:3])}")
    return {"collected_at": collected_at, "source": source,
            "products": len(rows), "models": len(agg),
            "top": [{"model": a["canonical_model"], "sales": a["sales"]} for a in agg[:5]],
            "with_momentum": sum(1 for o in obs if "momentum" in o),
            "descartados": len(descartados),
            "descartados_exemplos": [t[:80] for t in descartados[:5]]}
