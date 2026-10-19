# ADR-001: One JDK or two for the JVM phases

**Status:** Proposed
**Date:** 2026-10-19
**Deciders:** repository owner

## Context

Two phases run on the JVM, and they currently need different JDKs.

- **`5-runtime-java`** compiles with `--release 25`. Java 25 was an explicit goal: the plan in `.github/modernize/java-upgrade/` lists "Java 25 (latest LTS target requested)", and commit `b086478` (#5) applied it.
- **`6-android-kotlin`** builds with Gradle 8.14.3 and Kotlin Gradle plugin 2.2.0, and targets JVM 17.

Measured on 2026-10-19 in an Ubuntu 24.04 container with OpenJDK 21.0.12 and 25.0.4.1:

| Experiment | Result |
|---|---|
| Java phase, `--release 25`, JDK 25 | 9/9 tests pass |
| Java phase, `--release 25`, JDK 21 | Fails: `release version 25 not supported` |
| Java phase, `--release 21`, JDK 21 | 9/9 tests pass. The code uses nothing from Java 22–25. |
| Kotlin build, Gradle 8.14.3, JDK 21 | 114 tests pass |
| Kotlin build, Gradle 8.14.3, JDK 25 | Fails during configuration. The only error text is the version string `25.0.4.1`. Whether Gradle or the Kotlin plugin rejects it was not established. |
| `run_all.py`, JDK 21 as default, JDK 25 for Maven | All six phases pass |

So no single JDK builds both phases today. Three more facts shape the options:

- `run_all.py` (commit `3d9c804`) finds the pom's JDK under `/usr/lib/jvm`. That's the Debian/Ubuntu layout. The modernization plan shows the owner's machine is macOS, with JDKs under `/Library/Java/JavaVirtualMachines`, where this lookup finds nothing.
- Installing JDK 25 with apt made it the system default, which breaks the Kotlin build until the default is set back to 21. The two-JDK setup is easy to break by accident.
- Android Studio runs Gradle on its own bundled JDK. Which version that is depends on the Studio release, and it wasn't checked.

## Decision

Keep Java 25 as the target for `5-runtime-java`.

- **Now:** keep two JDKs (Option A). It's the only configuration verified green.
- **Next:** try to reach a single JDK 25 by upgrading the Kotlin build's Gradle and Kotlin plugin (Option C). Adopt it only if the JVM suites pass on JDK 25 and Android Studio syncs `:app`.
- **Not chosen:** retargeting the Java phase to 21 (Option B). It works, but it reverses a goal the owner asked for. Take it only if the owner drops the Java 25 goal.

## Options Considered

### Option A: Two JDKs, 21 as default (current)

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Every environment installs two JDKs and keeps 21 as the default |
| Scalability | Each new JVM phase has to pick a JDK |
| Team familiarity | Common on Linux; less so on macOS |

**Pros:** verified green; no build-file changes; keeps Java 25.

**Cons:**
- Depends on the environment, and the `run_all.py` lookup only works on Linux.
- On a machine whose default JDK is 25, the Kotlin build fails unless `JAVA_HOME` points to 17 or 21.
- One package install can silently change the default.

### Option B: Retarget `5-runtime-java` to Java 21

| Dimension | Assessment |
|---|---|
| Complexity | Low (one property in `pom.xml`) |
| Cost | Minimal |
| Scalability | One JDK 21 for every JVM phase |
| Team familiarity | High |

**Pros:** verified (9/9 tests pass with `--release 21`); one JDK everywhere; `run_all.py` needs no JDK lookup.

**Cons:** reverses the requested Java 25 upgrade; rules out Java 22–25 language and API features until it's raised again.

### Option C: Upgrade Gradle and the Kotlin plugin so the build runs on JDK 25

| Dimension | Assessment |
|---|---|
| Complexity | Medium to high |
| Cost | Wrapper and plugin version changes; the Android Gradle Plugin must also support the new Gradle |
| Scalability | One JDK 25 for every JVM phase |
| Team familiarity | Medium (Gradle 9 has breaking changes) |

**Pros:** keeps Java 25; ends with one JDK; removes the JDK lookup from `run_all.py`; matches the owner's macOS setup.

**Cons:**
- Unverified. Which Gradle 9.x and Kotlin plugin versions support running on JDK 25 still has to be checked, not assumed.
- Android Gradle Plugin compatibility can't be checked in the cloud environment, because `dl.google.com` is blocked.
- It changes the untested Android build path.

### Option D: Maven toolchains

Maven runs on any JDK. The pom requests JDK 25 through `maven-toolchains-plugin`, and each machine maps it in `~/.m2/toolchains.xml`.

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | A pom change, plus `toolchains.xml` on every machine |
| Scalability | Same as A |
| Team familiarity | Low to medium |

**Pros:** works on macOS and Linux alike, unlike the `run_all.py` lookup; it's the Maven-native way to pin a JDK.

**Cons:** still two JDKs; one more per-machine file to keep correct.

## Trade-off Analysis

- **B** is the cheapest option, and it's verified. It contradicts the owner's stated goal, though, and only the owner can make that call.
- **A** works today but is fragile across machines, and it's Linux-only as implemented.
- **C** is the only option that keeps Java 25 and ends with one JDK. Its cost stays unknown until it's tested.
- **D** fixes A's portability, but not its complexity. It's the fallback if C fails.

## Consequences

- **Easier:** with A, all six phases pass in the cloud environment today. With C, any machine with one JDK 25 builds everything.
- **Harder:** A requires every environment, including CI and new contributors' machines, to install two JDKs and keep 21 as the default.
- **To revisit:** the macOS gap in A, and Android Studio's bundled JDK version, which decides what Gradle runs on there.

## Action Items

1. [ ] The owner confirms Java 25 stays the target. If not, take Option B.
2. [ ] Add JDK 25 to the cloud environment's setup script and keep JDK 21 as the default (`update-alternatives --set java` and `--set javac` to the JDK 21 binaries).
3. [ ] Test Option C on a scratch branch: move to a Gradle 9.x wrapper and a Kotlin plugin version that both support JDK 25, then run `6-android-kotlin/tools/determinism_check.sh` on JDK 25. Open the project in Android Studio and sync `:app`.
4. [ ] If C passes: make JDK 25 the only JDK, remove `jdk_for_pom` from `run_all.py`, update `CLAUDE.md`, and mark this ADR Accepted with C.
5. [ ] If C fails or is deferred: make the JDK lookup work on macOS (`/usr/libexec/java_home -v 25`) or adopt Option D, and mark this ADR Accepted with A.
