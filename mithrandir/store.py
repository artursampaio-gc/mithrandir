"""Camada de persistencia: Supabase (nuvem) ou arquivos locais.

Ponto unico de I/O de dados que mudam (intel, settings, news cache, cache do app).
Se SUPABASE_URL + SUPABASE_SERVICE_KEY estiverem no ambiente, usa o Supabase (REST);
caso contrario, usa arquivos locais (dev). Assim o mesmo codigo roda local e no Vercel.

Dados de referencia empacotados (CSVs de exemplo) continuam sendo lidos do disco.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

_APP_CACHE_FILE = DATA_DIR / "app_cache.json"


def is_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------- Supabase REST (baixo nivel) ----------------

def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mithrandir/0.1",
    }
    if extra:
        h.update(extra)
    return h


def _req(method: str, table: str, params: dict | None = None, body=None,
         headers: dict | None = None, timeout: int = 30):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(headers))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8")
        return json.loads(txt) if txt else []


def sb_select(table: str, params: dict | None = None) -> list:
    return _req("GET", table, params={"select": "*", **(params or {})})


def sb_insert(table: str, row) -> list:
    body = row if isinstance(row, list) else [row]
    return _req("POST", table, body=body, headers={"Prefer": "return=representation"})


def sb_upsert(table: str, row, on_conflict: str) -> list:
    body = row if isinstance(row, list) else [row]
    return _req("POST", table, params={"on_conflict": on_conflict},
                body=body, headers={"Prefer": "resolution=merge-duplicates,return=representation"})


def sb_delete(table: str, params: dict) -> None:
    _req("DELETE", table, params=params, headers={"Prefer": "return=minimal"})


# ---------------- Cache do app (candidates / calendar / news) ----------------
# No Supabase: tabela app_cache(key text pk, value jsonb, updated_at timestamptz).
# Local: arquivo data/app_cache.json.

def get_cached(key: str):
    if is_supabase():
        rows = sb_select("app_cache", {"key": f"eq.{key}", "limit": 1})
        return rows[0]["value"] if rows else None
    if _APP_CACHE_FILE.exists():
        try:
            return json.loads(_APP_CACHE_FILE.read_text(encoding="utf-8")).get(key)
        except json.JSONDecodeError:
            return None
    return None


def set_cached(key: str, value) -> None:
    if is_supabase():
        sb_upsert("app_cache", {"key": key, "value": value, "updated_at": _now()},
                  on_conflict="key")
        return
    data = {}
    if _APP_CACHE_FILE.exists():
        try:
            data = json.loads(_APP_CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data[key] = value
    _APP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _APP_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
