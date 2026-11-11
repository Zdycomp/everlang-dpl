"""SqlArchive: durable SQLite-backed store for the self-healing Archive.

This module is the standalone SQL phase (4-archive-sql/). It persists the
same events the in-process `EArchive` (everlang_standalone/everlang/core/archive.py)
tracks in memory, so that boundary markers, repairs, and evolved vectors
survive process restarts.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "tapestry.db"
# Same definition as schema.sql, for tables created before the column existed.
_VALUE_KIND_COLUMN = (
    "value_kind TEXT CHECK (value_kind IS NULL OR (value_kind IN "
    "('Int', 'Float', 'Bool', 'List<Str>', 'List<Int>', 'List<Float>', 'List<Bool>') AND template_version IS NULL))"
)


class SqlArchive:
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path) if db_path is not None else str(_DEFAULT_DB_PATH)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys=ON")
        with open(_SCHEMA_PATH, "r") as f:
            schema_sql = f.read()
        self._conn.executescript(schema_sql)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        # CREATE TABLE IF NOT EXISTS never alters a table an older schema already created.
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(transpilations)")}
        if "template_version" not in cols:
            self._conn.execute(
                "ALTER TABLE transpilations ADD COLUMN template_version INTEGER "
                "CHECK (template_version IS NULL OR template_version >= 1)"
            )
        if "value_kind" not in cols:
            self._conn.execute("ALTER TABLE transpilations ADD COLUMN " + _VALUE_KIND_COLUMN)
        # The pre-versioning custom_templates table (one row per language) becomes
        # version 1 of each language not already versioned; the old table is left as-is.
        legacy = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='custom_templates'"
        ).fetchone()
        if legacy:
            self._conn.execute(
                "INSERT INTO custom_template_versions (language, version, template, active) "
                "SELECT language, 1, template, 1 FROM custom_templates "
                "WHERE language NOT IN (SELECT language FROM custom_template_versions)"
            )

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
                              target_language: str, rendered_code: str,
                              template_version: int = None, value_kind: str = None) -> int:
        """Inserts a row into transpilations, returns the new row id.
        template_version is None for built-in languages. value_kind is None for
        string-template renderings; for a typed rendering it is the value's kind
        and val is its canonical DPL literal."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO transpilations (name, val, type_spec, confidence, "
                "target_language, rendered_code, template_version, value_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(name), str(val), str(type_spec), confidence, str(target_language),
                 str(rendered_code), template_version, value_kind),
            )
            self._conn.commit()
            return cur.lastrowid

    def save_custom_template(self, language: str, template: str) -> int:
        """Makes `template` the active version for `language` and returns its
        version number. Re-saving the current active template is a no-op that
        returns the existing version; prior versions are kept, never overwritten."""
        language, template = str(language), str(template)
        with self._lock, self._write_transaction():
            active = self._conn.execute(
                "SELECT version, template FROM custom_template_versions "
                "WHERE language=? AND active=1",
                (language,),
            ).fetchone()
            if active is not None and active[1] == template:
                return active[0]
            next_version = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM custom_template_versions "
                "WHERE language=?",
                (language,),
            ).fetchone()[0]
            self._conn.execute(
                "UPDATE custom_template_versions SET active=0 WHERE language=? AND active=1",
                (language,),
            )
            self._conn.execute(
                "INSERT INTO custom_template_versions (language, version, template, active) "
                "VALUES (?, ?, ?, 1)",
                (language, next_version, template),
            )
            return next_version

    def retire_custom_template(self, language: str) -> bool:
        """Retires the active version (history is kept so archived rows stay
        auditable). Returns True if an active version was retired."""
        with self._lock, self._write_transaction():
            cur = self._conn.execute(
                "UPDATE custom_template_versions SET active=0 WHERE language=? AND active=1",
                (str(language),),
            )
            return cur.rowcount > 0

    @contextmanager
    def _write_transaction(self):
        # BEGIN IMMEDIATE takes SQLite's RESERVED lock before the version is read,
        # so two processes can't both compute the same next version. (Python's
        # implicit BEGIN only arrives at the first write, after the read.)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        self._conn.commit()

    def load_custom_templates(self):
        """Returns active templates as {language: (version, template)}."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT language, version, template FROM custom_template_versions WHERE active=1"
            )
            return {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    def load_template_history(self, language: str):
        """Returns every version of `language` as [(version, template, active)], oldest first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT version, template, active FROM custom_template_versions "
                "WHERE language=? ORDER BY version",
                (str(language),),
            )
            return [(row[0], row[1], bool(row[2])) for row in cur.fetchall()]

    def close(self):
        self._conn.close()


def _insert(db_conn, sql, params):
    """Runs one INSERT and commits it. A sqlite3.Error (e.g. a CHECK or foreign-key
    violation) rolls back and propagates, so a caller never receives a bogus id."""
    try:
        cursor = db_conn.execute(sql, params)
        db_conn.commit()
        return cursor.lastrowid
    except sqlite3.Error:
        db_conn.rollback()
        raise


def record_kmer_index(db_conn, index_id, kmer_size, unique_kmers, total_kmers,
                      genome_length, shard_id=0, shard_count=1, verified_cpp=False):
    """Record k-mer index metadata in SQL audit log."""
    return _insert(db_conn, """
        INSERT INTO kmer_indices
        (index_id, kmer_size, unique_kmers, total_kmers, genome_length,
         shard_id, shard_count, verified_by_cpp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (index_id, kmer_size, unique_kmers, total_kmers, genome_length,
          shard_id, shard_count, 1 if verified_cpp else 0))


def record_sequence_query(db_conn, index_id, query_sequence, top_k, min_coverage,
                          match_count, elapsed_ms):
    """Record sequence query execution."""
    return _insert(db_conn, """
        INSERT INTO sequence_queries
        (index_id, query_sequence, query_length, top_k, min_coverage,
         match_count, total_time_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (index_id, query_sequence, len(query_sequence), top_k, min_coverage,
          match_count, elapsed_ms))


def record_sequence_match(db_conn, query_id, reference_position, kmer_matches,
                          coverage, confidence, match_strength):
    """Record individual sequence match result."""
    return _insert(db_conn, """
        INSERT INTO sequence_matches
        (query_id, reference_position, kmer_matches, coverage, confidence, match_strength)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (query_id, reference_position, kmer_matches, coverage, confidence, match_strength))
