"""Interpreta a intel em texto livre digitada no 'chat' e a estrutura.

Com o proxy de IA, extrai device/data/confianca do texto. Sem IA, faz um parse
por regex (data + marca/modelo) como melhor esforco. Se nao conseguir o device,
retorna needs_device=True para a UI pedir o campo explicitamente.
"""
from __future__ import annotations

import re

from .ai.proxy import AIClient
from .launch_estimator import extract_dates
from .normalize import BRANDS


_SUFFIX = r"(?:\s+(?:fe|pro\+?|ultra|plus|max|lite|neo|se|fan\s+edition))?"


def _regex_device(text: str) -> str | None:
    low = text.lower()
    for token, _ in BRANDS.items():
        m = re.search(rf"\b{re.escape(token)}\b[\w\s\+]*?\d{{1,3}}[a-z+]*{_SUFFIX}", low)
        if m:
            return text[m.start():m.end()].strip()
    return None


def parse_intel(text: str, ai: AIClient) -> dict:
    """Retorna {device, date, confidence, note, needs_device, via}."""
    if ai.available:
        try:
            data = ai.complete_json(
                "Extraia informacao de lancamento desta nota de analista. Responda SOMENTE "
                'um JSON: {"device":"...","date":"YYYY-MM-DD ou YYYY-MM ou null",'
                '"confidence":0..1,"note":"resumo"}\n'
                f'Nota: "{text}"',
                system="Voce estrutura notas sobre lancamento de smartphones.")
            date = data.get("date")
            if date and len(date) == 7:
                date = date + "-01"
            device = (data.get("device") or "").strip()
            return {
                "device": device,
                "date": date,
                "confidence": float(data.get("confidence", 0.85)),
                "note": data.get("note") or text,
                "needs_device": not bool(device),
                "via": "ia",
            }
        except Exception:
            pass  # cai para o regex

    dates = extract_dates(text)
    device = _regex_device(text)
    return {
        "device": device or "",
        "date": dates[0]["iso"] if dates else None,
        "confidence": 0.85,
        "note": text,
        "needs_device": device is None,
        "via": "regex",
    }
