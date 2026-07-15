"""Intel manual do analista (overrides) — sobrepoe o scouting.

Persistido no Supabase (tabela `intel`) quando configurado, ou em
data/overrides.json no modo local. Cada override casa com um device pela chave
canonica e vence a estimativa automatica.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .config import DATA_DIR
from .normalize import canonicalize

OVERRIDES_PATH = DATA_DIR / "overrides.json"


def _map_row(r: dict) -> dict:
    """Converte uma linha da tabela `intel` para o formato usado no app."""
    return {
        "id": r.get("id"),
        "device": r.get("device"),
        "canonical": r.get("canonical_model"),
        "date": r.get("launch_date"),
        "confidence": r.get("confidence"),
        "note": r.get("note"),
        "source_label": r.get("source_label"),
        "created_at": r.get("created_at"),
    }


# ---------------- Local (arquivo) ----------------

def _load_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_file(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- API publica ----------------

def load_overrides(path: Path = OVERRIDES_PATH) -> list[dict]:
    if store.is_supabase():
        return [_map_row(r) for r in store.sb_select("intel", {"order": "id.asc"})]
    return _load_file(path)


def add_override(device: str, date: str | None, confidence: float,
                 note: str = "", source_label: str = "Intel do analista",
                 path: Path = OVERRIDES_PATH) -> dict:
    canonical = canonicalize(device).canonical
    if store.is_supabase():
        rows = store.sb_insert("intel", {
            "device": device, "canonical_model": canonical,
            "launch_date": date, "confidence": float(confidence),
            "note": note, "source_label": source_label,
        })
        return _map_row(rows[0]) if rows else {}
    items = _load_file(path)
    new_id = (max((it.get("id", 0) for it in items), default=0)) + 1
    entry = {
        "id": new_id, "device": device, "canonical": canonical,
        "date": date, "confidence": float(confidence), "note": note,
        "source_label": source_label,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    items.append(entry)
    _save_file(items, path)
    return entry


def delete_override(override_id: int, path: Path = OVERRIDES_PATH) -> bool:
    if store.is_supabase():
        store.sb_delete("intel", {"id": f"eq.{override_id}"})
        return True
    items = _load_file(path)
    remaining = [it for it in items if it.get("id") != override_id]
    if len(remaining) == len(items):
        return False
    _save_file(remaining, path)
    return True


def override_for(canonical: str, path: Path = OVERRIDES_PATH) -> dict | None:
    matches = [it for it in load_overrides(path) if it.get("canonical") == canonical]
    return matches[-1] if matches else None
