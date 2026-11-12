---
name: ReEstablish
description: Re-establishes and reinforces any user-defined project scope through baseline measurement, contract auditing, focused hardening, regression coverage, and full verification.
---

# ReEstablish

Use this skill whenever the user asks to re-establish, reinforce, harden, strengthen, accelerate, stabilize, or comprehensively verify a defined scope.

The scope is always supplied by the user. It may be a file, subsystem, language layer, service, repository section, build pipeline, archive, integration boundary, or the entire project. Never assume the scope is C, Docker, ReFix, or any other subsystem unless the user defines it.

## Scope rule

At the start of every run, identify and preserve the user-defined scope exactly.

- If the user names files, operate only on those files and their required dependencies.
- If the user names a subsystem, inspect its entrypoints, dependencies, tests, and integration boundaries.
- If the user names the whole project, inspect the project structure and all relevant layers.
- Do not expand the scope silently.
- If a required dependency lies outside the named scope, read it for compatibility, but modify it only when necessary and report it.
- Do not overwrite unrelated user changes.

## Required workflow

1. Explore the defined scope.
   - Inspect the relevant files, directories, entrypoints, dependencies, configuration, and tests.
   - Read project-local instructions before editing.
   - Check `git status --short`.
   - Map inputs, outputs, ownership, persistence, APIs, and external boundaries.

2. Establish a hard baseline.
   - Run the narrowest relevant tests first.
   - Run the project’s broader verification command when available.
   - Record every failure, warning, skipped check, timing, and environmental limitation.
   - Never call a baseline green if a failure was hidden by a skip or substring check.

3. Audit the contracts.
   - Identify invariants, error handling, resource ownership, data formats, concurrency assumptions, security boundaries, and compatibility promises.
   - Check malformed input, empty input, maximum values, missing dependencies, timeouts, retries, partial failure, and recovery paths.
   - Compare implementations across languages, backends, storage layers, or services when the scope crosses them.

4. Build instrumentation and safety baselines.
   - Use the strongest applicable compiler warnings, linters, type checks, sanitizers, static analysis, tracing, profiling, or schema validation.
   - Measure performance before optimization.
   - Treat memory errors, undefined behavior, data corruption, race conditions, leaked resources, and silent fallback as correctness failures.

5. Reinforce the implementation.
   - Make focused edits to functional files.
   - Preserve public interfaces and data compatibility unless migration is explicitly requested.
   - Add validation at boundaries.
   - Make cleanup and failure behavior explicit.
   - Bound retries, recursion, allocation, input size, and execution time where appropriate.
   - Optimize only after correctness is established and measure the result.
   - Never remove tests, assertions, checks, error records, or integration paths to make a build pass.
   - Never replace real execution with mocks when verifying a production path.

6. Add regression coverage.
   - Add a test for every discovered defect.
   - Cover normal paths, boundary paths, malformed inputs, partial failures, repeated execution, and recovery.
   - Add compatibility tests for every affected integration boundary.
   - Preserve exact failure evidence where the system is an archive, repair engine, or audit trail.

7. Verify in layers.
   - Run focused tests after each logical change.
   - Re-run instrumentation, sanitizer, lint, type, schema, and performance checks.
   - Run integration and cross-layer tests.
   - Run the full regression suite last.
   - Build or deploy the relevant artifact when the request includes build or deployment verification.
   - Retry failed commands with corrected arguments; do not pivot to documentation.

8. Report precisely.
   - State the exact scope used.
   - State files changed and behavior reinforced.
   - Separate baseline failures, introduced failures, fixed failures, skips, and environmental limits.
   - Include exact commands and pass/fail counts.
   - Include before/after performance only when measured.
   - Never claim production readiness, compatibility, safety, or repair success without evidence.

## Mandatory behavior

- Follow the user’s requested scope, not a predefined technology.
- Preserve unrelated changes.
- Fix functional artifacts directly when asked to reinforce or stabilize them.
- Do not create guides or summary files unless explicitly requested.
- Do not weaken tests.
- Do not conceal failures as skips.
- Keep error records, rejection records, rollback data, and audit history intact.
- Apply cross-language compatibility checks whenever the defined scope crosses languages.

## Completion criteria

Do not report completion unless the applicable criteria are satisfied:

- The defined scope builds, loads, or starts as applicable.
- Focused tests pass.
- Relevant instrumentation reports no unresolved correctness failures.
- Regression coverage exists for discovered defects.
- Integration boundaries remain compatible.
- The full relevant regression suite passes.
- Performance claims have measurements.
- No unrelated user changes were overwritten.

## Report template

Use this structure in the final summary:

- Scope: exact user-defined scope.
- Reinforced: concise behavior and files changed.
- Verification: exact commands and results.
- Remaining: only measured failures, skips, limitations, or unverified claims.
- Next steps: two or three concrete actions appropriate to the same scope.
