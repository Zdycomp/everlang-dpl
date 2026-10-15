# ReFix v2

Zero-dependency Node CLI. Matches Gradle build errors against a signature
corpus, archives every accepted repair as a `(Failure, Fixture)` pair, and
synthesizes new rules only when the same fixture recurs across distinct
sources and replays against the entire archive without changing any prior
outcome.

The mechanism ports from Ever/Tapestry `SEMANTICS.md` §9 and
`4-archive-sql/repair.sql`. Constants live in one file (`src/constants.js`)
and derive from `E_CERTAIN = 256`.

## What's in and what's not

**In, tonight:**
- 14 hand-authored Gradle signatures drawn from documented AGP/Gradle errors
- Failure/Fixture archive as append-only JSONL
- Recurrence detection at `E_ASCEND_POINTS = 3` distinct sources
- Rule proposal with replay-against-archive gate
- Admission at `E_EXECUTE_FLOOR = 128`; rejected rules preserved forever
  with the reason
- 21 tests, zero deps

**Not in, and not pretending to be:**
- No trained corpus. The archive starts empty. Users build the moat.
- No `apply` command. v0 archives fixtures; it does not edit your files.
  When apply ships, revert lives in the same record. (Codric rule: every
  repair carries its own revert.)
- No hosted / team archive. Local JSONL only.

## Usage

```
refix scan <build.log>              — what signatures match?
refix accept <build.log> <src-id>   — archive matches as accepted repairs
refix candidates                    — fixtures that cleared the threshold
refix propose                       — attempt admission; replay-gated
refix rules                         — admitted & rejected rules
refix archive                       — raw JSONL to stdout
refix errors                        — unresolved and matched error catches
refix finality <program.ever>       — signature count and archive summary for a program
```

Archive lives at `$REFIX_HOME` or `~/.refix`.

## Tests

```
node tests/test_all.js
```

## Two bugs the mechanism caught during its own construction

Kept here because the project's discipline says gaps are documented, not
swept.

1. The `unresolved_dependency` regex used capturing alternation
   `(resolve|find)` — the first capture slot became `"resolve"` instead
   of the group id. The recurrence engine would have detected divergent
   `fixture_form` values across identical failures. Fixed to
   `(?:resolve|find)`.

2. The `agp_too_old` regex used `[\d\.]+`, which swallowed the sentence-
   final period into the version string, producing `8.5.2.` instead of
   `8.5.2`. Test caught it. Fixed to `\d+(?:\.\d+)*`.

Both are the failure mode ReFix exists to prevent in Gradle output —
regex overreach — appearing in ReFix's own regex file. Noted because
the tool is not exempt from its own claims.
