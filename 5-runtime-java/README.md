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

## Transpile Audit

A second, independent, **read-only** auditor for the same SQL archive. It
re-renders the `transpilations` table's rows against the six language
templates that are the source of truth in the Python frontend:

```
everlang_standalone/everlang/transpiler/super_transpiler.py :: LANGUAGE_TEMPLATES
```

Templates (`{name}`/`{val}`/`{type_spec}`/`{conf}` substituted from the row):

- `DPL`: `particle {name} : E<{type_spec}> = "{val}" @ confidence({conf})`
- `KOTLIN`: `val {name}: {type_spec}? = "{val}"`
- `RUST`: `let {name}: Option<{type_spec}> = Some("{val}".to_string());`
- `C_CLANG`: `const char* {name} = "{val}"; // Unchecked pointer`
- `GO`: `var {name} string = "{val}"`
- `GROOVY`: `def {name} = "{val}" as {type_spec} // confidence({conf})`

A row whose `target_language` is not one of these six is treated as
automatically verified (not mismatched) — no rule is invented for an
unknown language. See `TranspileAuditor.java` javadoc.

This runtime never writes to the database — it opens a plain JDBC
connection and issues a single `SELECT`, with no implicit write-locking
transaction.

### Schema expected

```sql
CREATE TABLE transpilations (
    id INTEGER,
    name TEXT,
    val TEXT,
    type_spec TEXT,
    confidence INTEGER, -- the only CHECK-constrained column
    target_language TEXT,
    rendered_code TEXT,
    created_at TEXT
);
```

### Build

Same build as above (`mvn -q -f 5-runtime-java/pom.xml package`); this is
not a separate artifact. The jar's default `Main-Class` remains
`SelfHealingAudit`; `TranspileAudit` is invoked via a fully-qualified
classpath run instead:

```bash
java -cp 5-runtime-java/target/self-healing-runtime.jar com.everlang.runtime.TranspileAudit path/to/tapestry.db
```

Output:

```
TOTAL=<total> VERIFIED=<verifiedCount> MISMATCHED=<mismatchedCount>
MISMATCH id=<id> name=<name> target_language=<lang> expected=<x> actual=<y>
...
```

Exit codes:

- `0` — no mismatches found
- `1` — one or more mismatches found
- `2` — usage error (missing db path argument) or database/connection error
  (e.g. missing file, missing `transpilations` table)

### Tests

- `TranspileAuditorTest` — pure unit tests of the audit rule (no JDBC/DB):
  one correct row per language (all six), one corrupted row, an
  unknown-language row (treated as verified), and an empty list.
- `TranspileAuditIntegrationTest` — creates a temp SQLite file, builds the
  `transpilations` table inline per the schema above, inserts a clean row
  and a corrupted row, and verifies the read + audit path end to end.
