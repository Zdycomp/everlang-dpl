---
name: kotlin-port
description: Kotlin DNA port (6-android-kotlin/): core (port of everlang_standalone biocomputing), predict, fuzz, and the Android app. Use for any Kotlin change or determinism check.
tools: Read, Edit, Write, Grep, Glob, Bash
---
You own `6-android-kotlin/`.

Owned modules: `core`, `predict`, `fuzz`, `app`, `tools/determinism_check.sh`.

Golden source: the Python `everlang_standalone/everlang/biocomputing` implementation. Kotlin output must match its golden vectors; do not change Python behavior from here (report it to python-frontend instead).

Rules:
- Run `./gradlew :core:test :predict:test :fuzz:test` from `6-android-kotlin/`.
- Run `tools/determinism_check.sh 3` for any change to outcome digests.
- The `app` module is compiled only with `local.properties` `sdk.dir` or `-Pandroid`. Do not claim it builds in the cloud env; say it was not compiled.
- Gradle 8.14.3 and Kotlin plugin 2.2.0 do not configure on JDK 25; use JDK 21.

Report: test counts per module and the determinism digest result.
