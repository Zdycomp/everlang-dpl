# 5-runtime-java — Self-Healing Archive Auditor

## What this is

An independent, **read-only** Java auditor for the SQL archive
(`tapestry.db`, owned by the `archive-sql` phase). It does not trust the
writer blindly: it re-derives the expected outcome of every persisted
repair record from the documented repair formula and flags any row whose
stored `confidence` / `quarantined` values have drifted from what the
formula says they should be.

The formula mirrored here is the source of truth in the Python frontend:

```
everlang_standalone/everlang/core/archive.py :: EArchive.emulate_repair
```

Rule: for a repair row with a given `error_distance`,

- if `1 <= error_distance <= 3`: `expected_confidence = 250 - error_distance * 30`, `expected_quarantined = false`
- otherwise: `expected_confidence = 0`, `expected_quarantined = true`

No other rule is invented; see `RepairAuditor.java` javadoc.

This runtime never writes to the database — it opens a plain JDBC
connection and issues a single `SELECT`, with no implicit write-locking
transaction.

## Schema expected

```sql
CREATE TABLE repairs (
    id INTEGER,
    failing_signature TEXT,
    error_distance INTEGER,
    repaired_value TEXT,
    confidence INTEGER,
    quarantined INTEGER, -- 0 or 1
    created_at TEXT
);
```

## Build

```bash
mvn -q -f 5-runtime-java/pom.xml package
```

This produces an executable fat jar (sqlite-jdbc bundled) at
`5-runtime-java/target/self-healing-runtime.jar`.

## Run

```bash
java -jar 5-runtime-java/target/self-healing-runtime.jar path/to/tapestry.db
```

Output:

```
TOTAL=<total> VERIFIED=<verifiedCount> MISMATCHED=<mismatchedCount>
MISMATCH id=<id> signature=<failingSignature> expected_confidence=<x> actual_confidence=<y> expected_quarantined=<a> actual_quarantined=<b>
...
```

Exit codes:

- `0` — no mismatches found
- `1` — one or more mismatches found
- `2` — usage error (missing db path argument) or database/connection error
  (e.g. missing file, missing `repairs` table)

## Tests

```bash
mvn -q -f 5-runtime-java/pom.xml test
```

- `RepairAuditorTest` — pure unit tests of the audit formula (no JDBC/DB).
- `SelfHealingAuditIntegrationTest` — creates a temp SQLite file, builds the
  `repairs` table inline (does not depend on the archive-sql phase's
  `schema.sql` existing), inserts a clean row and a corrupted row, and
  verifies the read + audit path end to end.
