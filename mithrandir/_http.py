"""Helper HTTP resiliente.

Usa `requests` quando disponivel (robusto no ambiente serverless do Vercel, onde
o `urllib` pode falhar com [Errno 16] Device or resource busy). Cai para `urllib`
no ambiente local (sem dependencia extra).
"""
from __future__ import annotations

import json as _json
import urllib.request

try:
    import requests as _requests  # disponivel no Vercel (requirements.txt)
except Exception:  # pragma: no cover
    _requests = None


def request_text(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """GET simples que devolve o corpo como texto (RSS/HTML, nao JSON)."""
    headers = dict(headers or {})
    if _requests is not None:
        resp = _requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def request_json(method: str, url: str, headers: dict | None = None,
                 json_body=None, timeout: int = 30):
    """Faz a requisicao e retorna o JSON (ou None se corpo vazio)."""
    headers = dict(headers or {})
    if _requests is not None:
        resp = _requests.request(method, url, headers=headers, json=json_body,
                                 timeout=timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    data = None
    if json_body is not None:
        data = _json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8")
    return _json.loads(body) if body else None
