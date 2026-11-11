# 4-archive-sql

## What this phase owns

This is the standalone SQL archive phase of the Everlang/4Ever pipeline. It
provides a persistent, durable backing store (SQLite) for the self-healing
Archive concept implemented in-process by `EArchive`
(`everlang_standalone/everlang/core/archive.py`). `EArchive` keeps its
`boundary_markers`, repair emulations, and `evolved_vectors` only in memory
and loses that history on process restart. This module (`SqlArchive`)
reinforces `EArchive` by giving the same categories of events a durable,
queryable home in a SQLite database (`tapestry.db`).

This phase does not import or depend on `everlang_standalone/`. It is a
standalone persistence layer; any bridge code that wires `EArchive` events
into `SqlArchive` writes belongs to a different phase/agent.

`tapestry.db` itself must never be committed. The repo's root `.gitignore`
already has a blanket `*.db` rule, so no additional ignore entry was needed
(verified).

## Schema

See `schema.sql` (all DDL uses `CREATE TABLE IF NOT EXISTS`, safe to run
against an existing database):

```sql
CREATE TABLE IF NOT EXISTS boundary_markers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context TEXT NOT NULL,
    value TEXT,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 256),
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failing_signature TEXT NOT NULL,
    error_distance INTEGER NOT NULL,
    repaired_value TEXT,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 256),
    quarantined INTEGER NOT NULL CHECK (quarantined IN (0,1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS evolved_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector REAL NOT NULL,
    action_success REAL NOT NULL,
    reaction_data REAL NOT NULL,
    force REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS rejected_writes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS transpilations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    val TEXT NOT NULL,
    type_spec TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 256),
    target_language TEXT NOT NULL,
    rendered_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    template_version INTEGER CHECK (template_version IS NULL OR template_version >= 1),
    -- NULL: rendered by a string template. Otherwise a typed rendering (built-in
    -- languages only) whose val is the value's canonical DPL literal.
    value_kind TEXT CHECK (value_kind IS NULL OR (value_kind IN ('Int', 'Float', 'Bool', 'List<Str>', 'List<Int>', 'List<Float>', 'List<Bool>') AND template_version IS NULL))
);

CREATE TABLE IF NOT EXISTS custom_template_versions (
    language TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    template TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0,1)) DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (language, version)
);
-- plus a partial unique index: at most one active version per language
```

`transpilations` persists each language the SuperTranspiler
(`everlang_standalone/everlang/transpiler/`) renders for a given value. It is
reinforced the same way `boundary_markers`/`repairs` are — every write is
gated by the C++ verifier first — and independently audited by
`5-runtime-java`'s `TranspileAudit`.

`custom_template_versions` is the append-only history of user-registered
languages. Editing a template adds a version; retiring one clears `active`
but never deletes the row. A custom-language `transpilations` row records the
`template_version` that rendered it (`NULL` for built-in languages), so the
auditor can re-render old rows after a template changes. `SqlArchive` adds
`template_version` and `value_kind` to a `transpilations` table created by an
older schema when it opens the database.

`value_kind` marks a typed rendering (`SuperTranspiler.transpile_typed`): a
number, boolean or list rendered with each built-in language's native type and
literal syntax rather than through the string templates. Such a row's `val` is
the value's canonical DPL literal (`85.5`, `true`, `["tcp", "udp"]`), which the
auditor parses to re-render it. The CHECK limits `value_kind` to the seven kinds
`everlang/transpiler/typed.py` defines and forbids it on custom-template rows.

## `SqlArchive` public API (`archive_db.py`)

This is the contract other phases (e.g. a future Python bridge) rely on
verbatim:

```python
class SqlArchive:
    def __init__(self, db_path: str = None):
        """If db_path is None, defaults to <this file's dir>/tapestry.db.
        Ensures schema.sql has been applied (idempotent)."""

    def record_boundary_marker(self, context: str, value, confidence: int, reason: str) -> int:
        """Inserts a row into boundary_markers, returns the new row id."""

    def record_repair(self, failing_signature: str, error_distance: int, repaired_value,
                       confidence: int, quarantined: bool) -> int:
        """Inserts a row into repairs, returns the new row id."""

    def record_evolved_vector(self, vector: float, action_success: float,
                               reaction_data: float, force: float) -> int:
        """Inserts a row into evolved_vectors, returns the new row id."""

    def record_rejected_write(self, table_name: str, reason: str, payload: str) -> int:
        """Inserts a row into rejected_writes, returns the new row id."""

    def record_transpilation(self, name: str, val: str, type_spec: str, confidence: int,
                              target_language: str, rendered_code: str,
                              template_version: int = None, value_kind: str = None) -> int:
        """Inserts a row into transpilations, returns the new row id."""

    def save_custom_template(self, language: str, template: str) -> int:
        """Makes `template` the active version and returns its version number;
        re-saving the active template returns the existing version."""

    def retire_custom_template(self, language: str) -> bool:
        """Retires the active version (history kept); True if one was active."""

    def load_custom_templates(self) -> dict:
        """Active templates as {language: (version, template)}."""

    def load_template_history(self, language: str) -> list:
        """Every version as [(version, template, active)], oldest first."""

    def close(self):
        """Closes the underlying sqlite3 connection."""
```

Notes on behavior:

- `value`, `repaired_value`, and `payload` are coerced to `str(...)` before
  insertion, since `EParticle` values and other archive payloads can be
  arbitrary Python objects, while the DB columns are `TEXT`. Likewise,
  `record_transpilation`'s `name`, `val`, `type_spec`, `target_language`,
  and `rendered_code` arguments are all coerced to `str(...)`.
- Confidence values are **not** pre-validated by `SqlArchive`; the
  `CHECK (confidence BETWEEN 0 AND 256)` constraint in the schema is the
  sole gate, and an out-of-range value raises `sqlite3.IntegrityError`
  naturally. Range validation is the responsibility of an upstream phase
  (e.g. the C++ analysis phase); this layer only persists and trusts its
  own constraints.
- All write methods acquire an internal `threading.Lock()` before touching
  the connection, mirroring `EArchive`'s own locking pattern, so concurrent
  callers from multiple threads do not corrupt the database or lose writes.

## Running the tests

```bash
cd /home/user/everlang-dpl && python3 -m unittest discover -s 4-archive-sql/tests -t .
```

Tests use `tempfile.mkdtemp()` for every database path; they never touch the
real `tapestry.db`.
