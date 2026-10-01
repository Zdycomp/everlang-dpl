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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
