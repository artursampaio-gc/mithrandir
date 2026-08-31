"""Normalizacao de titulo de anuncio com o proxy de IA.

Por que existe: as regras de `normalize.py` sao enxuga-gelo. Cada coleta nova
traz cor/edicao que ninguem previu — "Awesome Lavender", "Pantone Greener
Pastures", "Sandstone Beige", "Negro", "Ocean Blue" — e cada uma dessas vira um
candidato duplicado com a venda fatiada. A IA generaliza; a regra so conhece a
lista que alguem lembrou de escrever.

Medido na coleta de 2026-08-29 com ruido inedito: a regra errou 7 de 8, a IA
acertou 8 de 8, e ainda descartou corretamente um `Galaxy Tab S10 FE` — que o
filtro por marca NAO pega, porque a marca (Samsung) e legitima.

Desenho defensivo, nesta ordem:
  1. a regra (`model_from_listing`) sempre roda e e o piso;
  2. a IA so SUBSTITUI a regra quando concorda nos dois campos que sustentam o
     join com o BI: marca e numero de geracao. Discordou -> fica a regra;
  3. sem proxy, falha ou JSON torto -> tudo cai na regra e a ingestao segue.

A IA nunca inventa uma chave sozinha: ela so limpa o que a regra ja identificou.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from .collectors.marketplace import model_from_listing
from .normalize import canonicalize

BATCH = 40          # titulos por chamada (99 anuncios = 3 chamadas)
CACHE_KEY = "title_keys"

_SYSTEM = "Voce normaliza nomes de celular para uma chave de catalogo."

_PROMPT = """Normalize titulos de anuncio de celular para a CHAVE CANONICA do nosso catalogo.

Formato: MARCA + MODELO, em maiusculas, sem acento.
Regras:
- Remova cor, edicao, armazenamento, RAM, rede (4G/5G), camera, tela, bateria e
  codigo de fabricante. Cor pode vir em ingles ou espanhol e com nome de fantasia
  ("Awesome Lavender", "Pantone Greener Pastures", "Negro") — tudo isso sai.
- Sub-marca vira a marca dona: Redmi/Poco -> XIAOMI; iPhone -> APPLE;
  Galaxy -> SAMSUNG; Moto -> MOTOROLA.
- NAO repita a sub-marca na chave: "Redmi Note 15" -> "XIAOMI NOTE 15".
- MANTENHA o sufixo que distingue um APARELHO de outro, porque a capinha muda:
  PRO, PRO MAX, ULTRA, FE, MINI, E, e PLUS escrito como "+".
- Se NAO for um celular (fone, tablet, smartwatch, headset, carregador, capa),
  devolva chave vazia "".

Exemplos do catalogo: APPLE 16, APPLE 16 PRO MAX, APPLE 12 MINI, SAMSUNG S24 ULTRA,
SAMSUNG S23 +, SAMSUNG A55, MOTOROLA G84, XIAOMI NOTE 11, XIAOMI X6.

Titulos:
{lista}

Responda SOMENTE JSON: {{"itens":[{{"n":1,"chave":"..."}}]}}"""


def _formatar(chave: str) -> str:
    """Poe a chave da IA no formato da casa: digito nunca colado em letra.

    `canonicalize` desmembra "s26fe" -> "S26 FE", entao TODA chave do BI e dos
    candidatos respeita esse invariante. A IA devolvia "XIAOMI 15C" onde a regra
    devolve "XIAOMI 15 C" — mesmo aparelho, chaves diferentes, join quebrado.

    Nao da para simplesmente passar a chave da IA por `canonicalize`: ela nao e
    idempotente e transformaria "APPLE 16 E" em "APPLE 16", fundindo o iPhone
    16e no 16 de novo (ver DEV.md §8). Entao aplicamos so este desmembramento.
    """
    return re.sub(r"\s+", " ", re.sub(r"(\d)([A-Za-z])", r"\1 \2", chave)).strip()


def _compativel(chave_ia: str, titulo: str) -> bool:
    """A IA so vale se nao contradisser a regra nos campos que sustentam o join.

    - **Marca**: tem que bater sempre. Se a IA disser SAMSUNG onde a regra viu
      Motorola, e alucinacao.
    - **Geracao**: so cobrada quando a regra realmente achou uma. Quando a regra
      falha em achar (aconteceu com "Smartphone TCL 256GB ... mAh TCL 605", em
      que o modelo esta no fim do titulo e a regra devolveu so "TCL"), exigir
      igualdade jogaria fora justamente a resposta certa. Nesse caso a defesa e
      outra: o numero que a IA usou precisa APARECER no titulo.
    """
    regra = canonicalize(model_from_listing(titulo))
    ia = canonicalize(chave_ia)
    if not ia.canonical or ia.brand != regra.brand:
        return False
    if regra.generation is not None:
        return ia.generation == regra.generation
    if ia.generation is None:
        return True
    return re.search(rf"\b{ia.generation}\b", titulo) is not None


def clean_titles(ai, titles: list[str], cache: dict | None = None) -> dict:
    """titulo -> chave canonica; "" marca 'nao e celular'.

    Titulos ja resolvidos antes vem do `cache` (a coleta semanal repete quase
    tudo, entao da segunda rodada em diante quase nao ha chamada).
    """
    cache = cache if cache is not None else {}
    out = {t: cache[t] for t in titles if t in cache}
    faltam = [t for t in titles if t not in out]
    if not faltam or not getattr(ai, "available", False):
        return out

    lotes = [faltam[i:i + BATCH] for i in range(0, len(faltam), BATCH)]
    # Em paralelo: em serie, 99 titulos levavam 53s e a ingestao inteira tem os
    # 60s do Vercel. Um lote que falha nao derruba os outros.
    with ThreadPoolExecutor(max_workers=min(4, len(lotes))) as ex:
        for lote, itens in zip(lotes, ex.map(lambda l: _pedir_lote(ai, l), lotes)):
            for item in itens:
                try:
                    titulo = lote[int(item["n"]) - 1]
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
                chave = _formatar(str(item.get("chave", "")).strip().upper())
                if chave and not _compativel(chave, titulo):
                    print(f"[normalize_ai] descartada (incompativel com a regra): "
                          f"{chave!r} <- {titulo[:60]!r}")
                    continue
                out[titulo] = chave      # "" = nao e celular
    return out


def _pedir_lote(ai, lote: list[str]) -> list[dict]:
    lista = "\n".join(f"{n}. {t}" for n, t in enumerate(lote, 1))
    try:
        data = ai.complete_json(_PROMPT.format(lista=lista), system=_SYSTEM, timeout=90)
        return data.get("itens") or []
    except Exception as e:
        print(f"[normalize_ai] lote falhou ({e}); usando as regras nele.")
        return []
