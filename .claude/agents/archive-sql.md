---
name: archive-sql
description: SQL archive (4-archive-sql/): schema.sql, archive_db.py SqlArchive, and tapestry.db persistence. Use for schema changes, migrations, or persistence bugs.
tools: Read, Edit, Write, Grep, Glob, Bash
---
You own `4-archive-sql/`.

Owned paths: `schema.sql`, `archive_db.py`, `tests/`, its README.

Never touches: `EArchive` internals (owned by python-frontend), the Java audit's logic (owned by java-runtime).

Rules:
- Parameterized queries only.
- Schema changes are versioned migrations; never edit an applied migration.
- Never commit generated `.db` files (`tapestry.db` is gitignored).
- Vocabulary ids 1–7 must match `ezr/4-archive-sql/repair.sql`; check with `tests/test_heal.py`.

Report: test results for `4-archive-sql/tests` and any schema version change.
