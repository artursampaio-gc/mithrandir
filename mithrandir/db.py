"""Persistencia em SQLite (biblioteca padrao).

Guarda o historico de execucoes/scores para auditoria e para calcular momentum
em versoes futuras (RNF-04). O banco fica em data/mithrandir.db.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH
from .models import Candidate

SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ts TEXT NOT NULL,
    mock_mode INTEGER NOT NULL,
    n_candidates INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_snapshot (
    run_id INTEGER NOT NULL,
    canonical_model TEXT NOT NULL,
    phase TEXT,
    score REAL,
    review_count INTEGER,
    marketplace_rank INTEGER,
    payload TEXT,
    FOREIGN KEY (run_id) REFERENCES run(id)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_model ON candidate_snapshot(canonical_model);
"""


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_run(candidates: list[Candidate], mock_mode: bool, path: Path = DB_PATH) -> int:
    conn = _connect(path)
    try:
        run_ts = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO run (run_ts, mock_mode, n_candidates) VALUES (?, ?, ?)",
            (run_ts, 1 if mock_mode else 0, len(candidates)),
        )
        run_id = cur.lastrowid
        for c in candidates:
            mk = c.marketplace
            conn.execute(
                "INSERT INTO candidate_snapshot "
                "(run_id, canonical_model, phase, score, review_count, marketplace_rank, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, c.canonical_model, c.phase, c.score,
                    mk.review_count if mk else None,
                    mk.rank if mk else None,
                    json.dumps(c.to_dict(), ensure_ascii=False),
                ),
            )
        conn.commit()
        return run_id
    finally:
        conn.close()


def previous_review_count(canonical_model: str, path: Path = DB_PATH) -> int | None:
    """Ultima contagem de avaliacoes registrada para o modelo (para momentum)."""
    if not path.exists():
        return None
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT review_count FROM candidate_snapshot "
            "WHERE canonical_model = ? AND review_count IS NOT NULL "
            "ORDER BY run_id DESC LIMIT 1",
            (canonical_model,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()
