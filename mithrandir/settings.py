"""Parametros configuraveis pelo usuario (persistidos em data/settings.json).

Custos, frequencia de scouting e outros. Sao os defaults do negocio ate serem
ajustados na pagina de Config do app.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULTS = {
    # Financeiro (viabilidade)
    "case_price": 99.90,      # valor de venda da capinha (R$)
    "mold_cost": 22200.0,     # custo do molde (R$)
    "unit_cost": 3.16,        # custo por unidade (R$)
    # Scouting
    "scouting_frequency": "diaria",   # diaria | semanal | manual
    "scouting_time": "08:00",         # horario da coleta
    # Analise
    "history_months": 6,      # meses de historico usados na viabilidade
}

_NUMERIC = {"case_price", "mold_cost", "unit_cost", "history_months"}


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    data = dict(DEFAULTS)
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except json.JSONDecodeError:
            pass
    return data


def save_settings(patch: dict, path: Path = SETTINGS_PATH) -> dict:
    """Aplica as chaves validas de `patch` sobre as atuais e persiste."""
    current = load_settings(path)
    for k, v in (patch or {}).items():
        if k not in DEFAULTS:
            continue
        if k in _NUMERIC:
            try:
                v = float(v)
                if k == "history_months":
                    v = int(v)
            except (TypeError, ValueError):
                continue
        current[k] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
