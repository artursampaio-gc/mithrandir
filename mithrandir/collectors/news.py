"""Coletor de noticias/rumores de lancamento (RF-02).

Le feeds RSS de portais de tecnologia (stdlib: urllib + xml). Sem rede, ou em
caso de falha, retorna a amostra de mock. A extracao de modelo a partir do texto
pode ser reforcada pelo proxy de IA (passado pelo pipeline).
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET

from . import mock_seed

# Feeds RSS de portais BR (ajustaveis). Usados no modo real.
FEEDS = [
    "https://tecnoblog.net/feed/",
    "https://www.tudocelular.com/rss/noticias.xml",
]


def _fetch_feed(url: str, timeout: int = 20) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mithrandir/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "link": link, "source": url})
    return items


def collect(enabled: bool = False) -> list[dict]:
    """Retorna manchetes relevantes. `enabled=False` mantem o modo mock."""
    if not enabled:
        return mock_seed.news_headlines()
    headlines: list[dict] = []
    for url in FEEDS:
        try:
            headlines.extend(_fetch_feed(url))
        except Exception as e:
            print(f"[news] falha no feed {url} ({e}); ignorando.")
    return headlines or mock_seed.news_headlines()
