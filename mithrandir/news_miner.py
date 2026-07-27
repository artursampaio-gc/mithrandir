"""Mineracao de noticias: expande o corpus em UM sinal por aparelho citado.

Problema que resolve: uma noticia costuma citar varios aparelhos com datas
diferentes ("Pro e Pro Max em setembro de 2026; o base e o 18e so em 2027").
O estimador trabalha por device, entao sem esta etapa o Pro Max era ignorado e
o modelo de 2027 nunca entrava no calendario.

Aqui a IA le cada noticia e devolve, para CADA aparelho citado, a frase que se
aplica a ele. O resultado tem o mesmo formato do cache de noticias, entao o
restante do pipeline nao muda.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .normalize import canonicalize

_MINE_CACHE: dict = {}


def clear_cache() -> None:
    _MINE_CACHE.clear()


_SYSTEM = "Voce extrai aparelhos e datas de lancamento de noticias de tecnologia."


def _prompt(device_hint: str, signals: list[dict]) -> str:
    corpus = "\n".join(f"- {s.get('text','')}" for s in signals)
    return (
        f"Noticias sobre lancamento (contexto: {device_hint}):\n{corpus}\n\n"
        "Liste TODOS os aparelhos citados, um por um. Se a noticia citar varios "
        "modelos com datas diferentes (ex.: 'Pro e Pro Max em setembro; o base "
        "so em 2027'), crie uma entrada SEPARADA para cada modelo, com a data "
        "que se aplica aquele modelo especifico.\n"
        "Regras: use o nome comercial completo (ex.: 'Apple iPhone 18 Pro Max'); "
        "nao invente modelos que nao foram citados; a frase deve mencionar a data "
        "ou a situacao daquele modelo.\n"
        'Responda SOMENTE JSON: {"devices":[{"device":"...","text":"frase com a '
        'data/situacao desse modelo"}]}'
    )


def _mine_entry(ai, canon: str, entry: dict) -> list[tuple[str, dict]]:
    """Retorna [(canonical, signal)] extraidos de uma entrada de noticia."""
    signals = entry.get("signals") or []
    if not signals:
        return []
    prompt = _prompt(entry.get("device", canon), signals)
    if prompt in _MINE_CACHE:
        found = _MINE_CACHE[prompt]
    else:
        try:
            data = ai.complete_json(prompt, system=_SYSTEM)
            found = [d for d in (data.get("devices") or [])
                     if isinstance(d, dict) and str(d.get("device", "")).strip()]
            _MINE_CACHE[prompt] = found
        except Exception:
            return []  # falhou -> o chamador mantem a entrada original

    # Herdamos fonte/url do primeiro sinal (a noticia de origem)
    src, url = signals[0].get("source", ""), signals[0].get("url", "")
    out = []
    for d in found:
        name = str(d["device"]).strip()
        text = str(d.get("text", "")).strip()
        if not text:
            continue
        out.append((canonicalize(name).canonical,
                    {"source": src, "url": url, "text": text, "device": name}))
    return out


def expand_signals(ai, cache: dict) -> dict:
    """Expande o cache de noticias em uma entrada por aparelho citado.

    Sem IA (ou se a mineracao falhar), devolve o cache original inalterado.
    """
    if not cache or not getattr(ai, "available", False):
        return cache

    items = [(k, v) for k, v in cache.items() if isinstance(v, dict)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        mined = list(ex.map(lambda it: _mine_entry(ai, it[0], it[1]), items))

    out: dict = {}

    def add(canon: str, device: str, signal: dict) -> None:
        e = out.setdefault(canon, {"device": device, "signals": []})
        if not any(s.get("text") == signal.get("text") for s in e["signals"]):
            e["signals"].append({k: v for k, v in signal.items() if k != "device"})

    for (canon, entry), extracted in zip(items, mined):
        if not extracted:
            # mineracao nao rendeu nada -> preserva a entrada original
            out.setdefault(canon, {"device": entry.get("device", canon),
                                   "signals": list(entry.get("signals") or [])})
            continue
        for c, sig in extracted:
            add(c, sig.get("device", c), sig)
    return out
