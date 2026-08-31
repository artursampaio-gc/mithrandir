"""Normalizacao e deduplicacao de nomes de modelo de celular.

Resolve variacoes como "Galaxy S26 FE", "Samsung S26FE", "S26 Fan Edition"
para uma mesma chave canonica. Usa regras determinísticas; o proxy de IA pode
ser plugado para os casos ambiguos (ver `canonicalize_with_ai`).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

BRANDS = {
    "samsung": "SAMSUNG",
    "galaxy": "SAMSUNG",   # "Galaxy" implica Samsung (linha removida do corpo)
    "motorola": "MOTOROLA",
    "moto": "MOTOROLA",
    "xiaomi": "XIAOMI",
    "redmi": "XIAOMI",
    "poco": "XIAOMI",
    "apple": "APPLE",
    "iphone": "APPLE",
    "realme": "REALME",
    "asus": "ASUS",
    "infinix": "INFINIX",
    # Marcas que apareceram no top 100 da Amazon BR e nao estavam mapeadas: sem
    # marca reconhecida o aparelho e descartado na ingestao e some do scouting.
    "oppo": "OPPO",
    "tcl": "TCL",
    "honor": "HONOR",
    "nokia": "NOKIA",
    "zte": "ZTE",
    "multilaser": "MULTILASER",
    "philco": "PHILCO",
}

# Substituicoes que normalizam sinonimos de sufixos/linhas
REPLACEMENTS = [
    (r"\bfan edition\b", "FE"),
    (r"\bpro plus\b", "PRO+"),
    (r"\bplus\b", "+"),
    (r"\bultra\b", "ULTRA"),
]


@dataclass
class ParsedModel:
    canonical: str
    brand: str
    family: str          # linha sem o numero de geracao (ex.: "GALAXY S FE")
    generation: Optional[int]  # numero da geracao (ex.: 26 em "S26 FE")


def _unglue_brand(text: str) -> str:
    """Separa a marca colada ao numero: 'iPhone12Mini' -> 'iPhone 12Mini'."""
    tokens = "|".join(sorted(BRANDS, key=len, reverse=True))
    return re.sub(rf"({tokens})(\d)", r"\1 \2", text, flags=re.IGNORECASE)


# Ruido tipico de titulo de anuncio de marketplace
_CATEGORIA = r"smartphone|celular|aparelho|telefone"
_CONECTOR = r"de|com|para|e"
_COR = (r"preto|preta|branco|branca|azul|verde|roxo|roxa|violeta|cinza|prata|"
        r"prateado|dourado|dourada|titanio|grafite|rosa|amarelo|vermelho|bege|"
        r"black|blue|white|purple|midnight|silver|gold|green|pink|"
        r"intenso|escuro|claro|natural|deserto|"
        # Vistos em anuncios reais da Amazon BR — inclui espanhol e o typo do
        # lojista: "POCO C85 4G Negro", "Note 14 Pro Coral Green", "Note 14
        # Ocean Blue", "Redmi 15C Mint Green", "Moonlight Blue", "Pro Titanuim"
        r"negro|negra|blanco|coral|ocean|mint|moonlight|lavanda|lavender|"
        r"titanium|titanuim")
_SPEC = r"ram|rom|boost|nfc|global|camera|cam|tela|memoria|polegadas|selfie|tripla"


def _strip_accents(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def _clean(text: str) -> str:
    t = _strip_accents(_unglue_brand(text)).lower().strip()
    t = re.sub(r"[®™]", "", t)
    for pat, rep in REPLACEMENTS:
        t = re.sub(pat, rep.lower(), t)
    # Titulos de marketplace: corta o que vem depois de "|" e o que esta em ()
    t = re.sub(r"\|.*$", " ", t)
    t = re.sub(r"\([^)]*\)", " ", t)
    # Remove ruido comum de anuncios: armazenamento, rede, dual sim
    t = re.sub(r"\b\d{1,4}\s?(gb|tb)\b", " ", t)
    t = re.sub(r"\b[2345]g\b", " ", t)
    # Armazenamento escrito so com "G" ("Note 15 4G 256G/8Gb Ram"): exige 2+
    # digitos para nao comer a rede (4G/5G), tratada na linha acima.
    t = re.sub(r"\b\d{2,4}\s?g\b", " ", t)
    t = re.sub(r"\bdual\b|\bsim\b|\bnfc\b", " ", t)
    t = re.sub(rf"\bip\d{{2}}\b|\b\d+\s?mp\b|\b\d+(\.\d+)?\"", " ", t)
    # Palavras de anuncio: categoria, conectores, cores e specs
    t = re.sub(rf"\b({_CATEGORIA})\b", " ", t)
    t = re.sub(rf"\b({_COR})\b", " ", t)
    t = re.sub(rf"\b({_SPEC})\b", " ", t)
    t = re.sub(rf"\b({_CONECTOR})\b", " ", t)
    # Separa sufixo colado ao numero de geracao: "s26fe" -> "s26 fe"
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    # Pontuacao solta ("Galaxy S25." / "g86 - 256GB" -> "g86")
    t = re.sub(r"[.,;:]+(\s|$)", r"\1", t)
    t = re.sub(r"[-–—/]+(\s|$)", r"\1", t)  # "g06-" (de "g06-128GB") e "256G/" -> limpa
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def detect_brand(text: str) -> str:
    low = _unglue_brand(text).lower()   # pega tambem "iPhone12Mini"
    for token, brand in BRANDS.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            return brand
    return ""


def _extract_generation(text: str) -> Optional[int]:
    """Pega o numero de geracao mais provavel (ex.: 26 em 'S26 FE', 86 em 'G86')."""
    m = re.search(r"\b[A-Za-z]?(\d{1,3})\b", text)
    return int(m.group(1)) if m else None


def canonicalize(raw: str) -> ParsedModel:
    """Gera a chave canonica de um nome de modelo por regras."""
    brand = detect_brand(raw)
    cleaned = _clean(raw)

    # Remove o nome da marca do corpo para nao duplicar
    for token in BRANDS:
        cleaned = re.sub(rf"\b{re.escape(token)}\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().upper()

    generation = _extract_generation(cleaned)
    # family = corpo com o numero trocado por '#'
    family = cleaned
    if generation is not None:
        family = re.sub(rf"\b([A-Z]?){generation}\b", r"\1#", cleaned, count=1)
    family = re.sub(r"\s+", " ", family).strip()

    canonical = f"{brand} {cleaned}".strip()
    canonical = re.sub(r"\s+", " ", canonical)
    return ParsedModel(
        canonical=canonical,
        brand=brand,
        family=(f"{brand} {family}".strip() if brand else family),
        generation=generation,
    )


def canonicalize_with_ai(raw: str, ai_client) -> ParsedModel:
    """Fallback opcional via proxy de IA para nomes ambiguos.

    Cai de volta nas regras se o proxy nao estiver disponivel ou falhar.
    """
    rule_based = canonicalize(raw)
    if not ai_client or not getattr(ai_client, "available", False):
        return rule_based
    try:
        prompt = (
            "Normalize o nome de celular abaixo. Responda SOMENTE um JSON com as "
            'chaves: brand, canonical, family, generation.\n'
            f'Nome: "{raw}"'
        )
        data = ai_client.complete_json(prompt, system="Voce normaliza nomes de smartphones.")
        return ParsedModel(
            canonical=str(data.get("canonical", rule_based.canonical)).upper(),
            brand=str(data.get("brand", rule_based.brand)).upper(),
            family=str(data.get("family", rule_based.family)).upper(),
            generation=data.get("generation", rule_based.generation),
        )
    except Exception:
        return rule_based
