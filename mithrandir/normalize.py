"""Normalizacao e deduplicacao de nomes de modelo de celular.

Resolve variacoes como "Galaxy S26 FE", "Samsung S26FE", "S26 Fan Edition"
para uma mesma chave canonica. Usa regras determinísticas; o proxy de IA pode
ser plugado para os casos ambiguos (ver `canonicalize_with_ai`).
"""
from __future__ import annotations

import re
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


def _clean(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[®™]", "", t)
    for pat, rep in REPLACEMENTS:
        t = re.sub(pat, rep.lower(), t)
    # Remove ruido comum de anuncios: armazenamento, rede, dual sim
    t = re.sub(r"\b\d{1,4}\s?(gb|tb)\b", " ", t)
    t = re.sub(r"\b[2345]g\b", " ", t)
    t = re.sub(r"\bdual\b|\bsim\b|\bnfc\b", " ", t)
    # Separa sufixo colado ao numero de geracao: "s26fe" -> "s26 fe"
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def detect_brand(text: str) -> str:
    low = text.lower()
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
