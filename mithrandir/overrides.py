"""Intel manual do analista (overrides).

Dados que o usuario sabe (ex.: contato em fabrica) e que SOBREPOEM o scouting
online. Persistido em data/overrides.json. Cada override casa com um device pela
chave canonica e vence a estimativa automatica.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR
from .normalize import canonicalize

OVERRIDES_PATH = DATA_DIR / "overrides.json"


def load_overrides(path: Path = OVERRIDES_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save(items: list[dict], path: Path = OVERRIDES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_override(device: str, date: str | None, confidence: float,
                 note: str = "", source_label: str = "Intel do analista",
                 path: Path = OVERRIDES_PATH) -> dict:
    items = load_overrides(path)
    new_id = (max((it.get("id", 0) for it in items), default=0)) + 1
    entry = {
        "id": new_id,
        "device": device,
        "canonical": canonicalize(device).canonical,
        "date": date,                    # "YYYY-MM-DD" | "YYYY-MM" | None
        "confidence": float(confidence),
        "note": note,
        "source_label": source_label,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    items.append(entry)
    _save(items, path)
    return entry


def delete_override(override_id: int, path: Path = OVERRIDES_PATH) -> bool:
    items = load_overrides(path)
    remaining = [it for it in items if it.get("id") != override_id]
    if len(remaining) == len(items):
        return False
    _save(remaining, path)
    return True


def override_for(canonical: str, path: Path = OVERRIDES_PATH) -> dict | None:
    """Override mais recente para um device (o ultimo cadastrado vence)."""
    matches = [it for it in load_overrides(path) if it.get("canonical") == canonical]
    return matches[-1] if matches else None
