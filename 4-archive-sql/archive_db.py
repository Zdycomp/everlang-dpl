"""SqlArchive: durable SQLite-backed store for the self-healing Archive.

This module is the standalone SQL phase (4-archive-sql/). It persists the
same events the in-process `EArchive` (everlang_standalone/everlang/core/archive.py)
tracks in memory, so that boundary markers, repairs, and evolved vectors
survive process restarts.
"""

import sqlite3
import threading
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "tapestry.db"


class SqlArchive:
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path) if db_path is not None else str(_DEFAULT_DB_PATH)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys=ON")
        with open(_SCHEMA_PATH, "r") as f:
            schema_sql = f.read()
        self._conn.executescript(schema_sql)
        self._conn.commit()

    def record_boundary_marker(self, context: str, value, confidence: int, reason: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO boundary_markers (context, value, confidence, reason) "
                "VALUES (?, ?, ?, ?)",
                (context, str(value), confidence, reason),
            )
            self._conn.commit()
            return cur.lastrowid

    def record_repair(self, failing_signature: str, error_distance: int, repaired_value,
                       confidence: int, quarantined: bool) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO repairs (failing_signature, error_distance, repaired_value, "
                "confidence, quarantined) VALUES (?, ?, ?, ?, ?)",
                (failing_signature, error_distance, str(repaired_value), confidence,
                 int(quarantined)),
            )
            self._conn.commit()
            return cur.lastrowid

    def record_evolved_vector(self, vector: float, action_success: float,
                               reaction_data: float, force: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO evolved_vectors (vector, action_success, reaction_data, force) "
                "VALUES (?, ?, ?, ?)",
                (vector, action_success, reaction_data, force),
            )
            self._conn.commit()
            return cur.lastrowid

    def record_rejected_write(self, table_name: str, reason: str, payload: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO rejected_writes (table_name, reason, payload) VALUES (?, ?, ?)",
                (table_name, reason, str(payload)),
            )
            self._conn.commit()
            return cur.lastrowid

    def close(self):
        self._conn.close()
