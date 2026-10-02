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

CREATE TABLE IF NOT EXISTS kmer_indices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id TEXT NOT NULL UNIQUE,
    kmer_size INTEGER NOT NULL CHECK (kmer_size = 11),
    unique_kmers INTEGER NOT NULL CHECK (unique_kmers > 0),
    total_kmers INTEGER NOT NULL CHECK (total_kmers >= unique_kmers),
    genome_length INTEGER NOT NULL,
    shard_id INTEGER NOT NULL DEFAULT 0,
    shard_count INTEGER NOT NULL DEFAULT 1,
    verified_by_cpp INTEGER NOT NULL CHECK (verified_by_cpp IN (0,1)) DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CONSTRAINT shard_valid CHECK (shard_id < shard_count)
);

CREATE TABLE IF NOT EXISTS sequence_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id TEXT NOT NULL,
    query_sequence TEXT NOT NULL,
    query_length INTEGER NOT NULL,
    top_k INTEGER NOT NULL,
    min_coverage REAL NOT NULL,
    match_count INTEGER NOT NULL,
    total_time_ms REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY(index_id) REFERENCES kmer_indices(index_id)
);

CREATE TABLE IF NOT EXISTS sequence_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    reference_position INTEGER NOT NULL,
    kmer_matches INTEGER NOT NULL,
    coverage REAL NOT NULL CHECK (coverage BETWEEN 0.0 AND 1.0),
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 256),
    match_strength TEXT NOT NULL CHECK (match_strength IN ('exact', 'high', 'medium', 'low')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY(query_id) REFERENCES sequence_queries(id)
);

CREATE INDEX IF NOT EXISTS idx_kmer_indices_shard ON kmer_indices(shard_id, shard_count);
CREATE INDEX IF NOT EXISTS idx_sequence_queries_index ON sequence_queries(index_id);
CREATE INDEX IF NOT EXISTS idx_sequence_matches_query ON sequence_matches(query_id);
