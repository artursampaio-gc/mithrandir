"""Parametros configuraveis (custos, frequencia de scouting, etc.).

Persistido no Supabase (tabela `settings` chave/valor) quando configurado, ou em
data/settings.json no modo local.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import store
from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULTS = {
    # Financeiro (viabilidade)
    "case_price": 99.90,
    "mold_cost": 22200.0,
    "unit_cost": 3.16,
    # Scouting
    "scouting_frequency": "diaria",   # diaria | semanal | manual
    "scouting_time": "08:00",
    # Analise
    "history_months": 6,
}

_NUMERIC = {"case_price", "mold_cost", "unit_cost", "history_months"}


def _coerce(k, v):
    if k in _NUMERIC:
        try:
            v = float(v)
            if k == "history_months":
                v = int(v)
        except (TypeError, ValueError):
            return None
    return v


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    data = dict(DEFAULTS)
    if store.is_supabase():
        for r in store.sb_select("settings"):
            k = r.get("key")
            if k in DEFAULTS:
                data[k] = r.get("value")
        return data
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except json.JSONDecodeError:
            pass
    return data


def save_settings(patch: dict, path: Path = SETTINGS_PATH) -> dict:
    current = load_settings(path)
    changed = {}
    for k, v in (patch or {}).items():
        if k not in DEFAULTS:
            continue
        cv = _coerce(k, v)
        if cv is None:
            continue
        current[k] = cv
        changed[k] = cv
    if store.is_supabase():
        if changed:
            store.sb_upsert("settings", [{"key": k, "value": v} for k, v in changed.items()],
                            on_conflict="key")
        return current
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
