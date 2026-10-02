# Upgrade Plan: Everlang Java Runtime (20261001235509)

- **Generated**: 2026-10-01
- **HEAD Branch**: main
- **HEAD Commit ID**: N/A (not returned by the version-control status tool)

## Available Tools

**JDKs**
- JDK 17: /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home (current project JDK, used by baseline)
- JDK 25.0.4.1: /Library/Java/JavaVirtualMachines/temurin-25.jdk/Contents/Home (target JDK)

**Build Tools**
- Maven: **<TO_BE_INSTALLED>** (install 3.9.15 in Step 1; no Maven wrapper is present)

## Guidelines

> Note: You can add any specific guidelines or constraints for the upgrade process here if needed, bullet points are preferred.

## Options

- Working branch: appmod/java-upgrade-20261001235509
- Run tests before and after the upgrade: true

## Upgrade Goals

- Java 25 (latest LTS target requested)

## Technology Stack

| Technology/Dependency | Current | Min Compatible Version | Why Incompatible |
| --------------------- | ------- | ---------------------- | ---------------- |
| Java | 17 (`maven.compiler.release`) | 25 | User requested; source and test code must compile against Java 25 |
| Maven | Not installed; no wrapper | 3.9.0+ recommended | Needed to build and verify the module; install Maven 3.9.15 |
| maven-compiler-plugin | Implicit Maven default | 3.11.0+ recommended | Pin a modern plugin so the `maven.compiler.release` setting is applied consistently with Java 25 |
| maven-surefire-plugin | 3.2.5 | 3.0.0+ | Compatible baseline for Java 17+; no upgrade required |
| maven-shade-plugin | 3.5.3 | N/A | No Java 25 incompatibility identified |
| sqlite-jdbc | 3.46.1.0 | N/A | No Java 25 compatibility blocker identified |
| JUnit Jupiter | 5.10.2 | N/A | No Java 25 compatibility blocker identified |

## Derived Upgrades

- Java 25 requires the project compiler release to be set to 25.
- Add an explicit `maven-compiler-plugin` version (3.14.1) to ensure stable support for the compiler release setting.
- Install Maven 3.9.15 because neither a system Maven nor Maven Wrapper is available.

## Impact Analysis

### Dependency Changes

| File | Dependency | Current | Action | Target | Reason |
|------|-----------|---------|--------|--------|--------|
| 5-runtime-java/pom.xml | `maven.compiler.release` | 17 | upgrade | 25 | User-requested Java LTS upgrade |
| 5-runtime-java/pom.xml | `maven-compiler-plugin` | Implicit Maven default | add | 3.14.1 | Explicitly support Java 25 and reliably honor the release property |

### Source Code Changes

No Java source or test changes identified. A targeted scan found no internal JDK API references or reflective access patterns.

### Configuration Changes

No application configuration changes identified.

### CI/CD Changes

No CI/CD files or hardcoded Java-version settings were found in the repository.

### Risks & Warnings

- Maven was not installed and the module has no wrapper. **Mitigation**: Install Maven 3.9.15 in Step 1 and use it for all baseline and target-JDK builds.
- A local Java 17 baseline is available. Changes to the compiler plugin and release value will be kept together so the project remains buildable in the Java 25 upgrade step.
- CVE scanning is part of final verification; dependency versions should only change if a scanner reports a fixable vulnerability.

## Upgrade Steps

- Step 1: Setup Environment
  - **Rationale**: Maven is required for the baseline and Java 25 validation but is not currently installed.
  - **Changes to Make**: Install Maven 3.9.15; no project files change.
  - **Verification**: List installed Maven and JDKs; Maven 3.9.15 and JDK 25 must be available.

- Step 2: Setup Baseline
  - **Rationale**: Establish compilation and test pass rates with the project's current Java 17 target before changing configuration.
  - **Changes to Make**: No project files change.
  - **Verification**: `mvn clean compile test-compile -q && mvn clean test -q`, using JDK 17; expected successful compilation and all existing tests passing.

- Step 3: Upgrade Compiler Target to Java 25
  - **Rationale**: Set the requested LTS target and explicitly pin the compiler plugin so Java 25 compilation is reliable.
  - **Changes to Make**: Apply all Dependency Changes listed in Impact Analysis.
  - **Verification**: `mvn clean test-compile -q`, using JDK 25; expected production and test compilation succeeds.

- Step 4: CVE Validation & Fix
  - **Rationale**: Check direct dependencies for known vulnerabilities after the upgrade.
  - **Changes to Make**: Upgrade only dependencies for which the scanner reports an available compatible fix; re-scan after changes.
  - **Verification**: Scan direct dependencies, compile, and re-scan; expected no reported fixable CVEs.

- Step 5: Final Validation
  - **Rationale**: Confirm the target is active and the complete suite passes on Java 25.
  - **Changes to Make**: Resolve any test or build regressions from the upgrade; no known source changes are anticipated.
  - **Verification**: `mvn clean test -q` and `mvn clean verify -Djacoco.skip=false`, using JDK 25; expected all tests pass and coverage command completes.
