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

    def record_transpilation(self, name: str, val: str, type_spec: str, confidence: int,
                              target_language: str, rendered_code: str) -> int:
        """Inserts a row into transpilations, returns the new row id."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO transpilations (name, val, type_spec, confidence, "
                "target_language, rendered_code) VALUES (?, ?, ?, ?, ?, ?)",
                (str(name), str(val), str(type_spec), confidence, str(target_language),
                 str(rendered_code)),
            )
            self._conn.commit()
            return cur.lastrowid

    def save_custom_template(self, language: str, template: str) -> None:
        """Upsert a custom language template."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO custom_templates (language, template) VALUES (?, ?) "
                "ON CONFLICT(language) DO UPDATE SET template=excluded.template",
                (str(language), str(template)),
            )
            self._conn.commit()

    def delete_custom_template(self, language: str) -> bool:
        """Remove a custom template. Returns True if a row was deleted."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM custom_templates WHERE language=?",
                (str(language),),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def load_custom_templates(self):
        """Returns all custom templates as a dict {language: template}."""
        with self._lock:
            cur = self._conn.execute("SELECT language, template FROM custom_templates")
            return {row[0]: row[1] for row in cur.fetchall()}

    def close(self):
        self._conn.close()


def record_kmer_index(db_conn, index_id, kmer_size, unique_kmers, total_kmers, 
                      genome_length, shard_id=0, shard_count=1, verified_cpp=False):
    """Record k-mer index metadata in SQL audit log."""
    try:
        cursor = db_conn.cursor()
        cursor.execute("""
            INSERT INTO kmer_indices 
            (index_id, kmer_size, unique_kmers, total_kmers, genome_length, 
             shard_id, shard_count, verified_by_cpp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (index_id, kmer_size, unique_kmers, total_kmers, genome_length,
              shard_id, shard_count, 1 if verified_cpp else 0))
        db_conn.commit()
        return cursor.lastrowid
    except Exception as e:
        return None


def record_sequence_query(db_conn, index_id, query_sequence, top_k, min_coverage, 
                         match_count, elapsed_ms):
    """Record sequence query execution."""
    try:
        cursor = db_conn.cursor()
        cursor.execute("""
            INSERT INTO sequence_queries 
            (index_id, query_sequence, query_length, top_k, min_coverage, 
             match_count, total_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (index_id, query_sequence, len(query_sequence), top_k, min_coverage,
              match_count, elapsed_ms))
        db_conn.commit()
        return cursor.lastrowid
    except Exception as e:
        return None


def record_sequence_match(db_conn, query_id, reference_position, kmer_matches, 
                         coverage, confidence, match_strength):
    """Record individual sequence match result."""
    try:
        cursor = db_conn.cursor()
        cursor.execute("""
            INSERT INTO sequence_matches 
            (query_id, reference_position, kmer_matches, coverage, confidence, match_strength)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (query_id, reference_position, kmer_matches, coverage, confidence, match_strength))
        db_conn.commit()
        return cursor.lastrowid
    except Exception as e:
        return None
