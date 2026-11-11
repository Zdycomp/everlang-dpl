---
name: cpp-analysis
description: C++ analysis phase (1-phase-cpp/): the verify_particle safety gate and native analysis code. Use for any change to the verify_particle CLI or its C++ sources.
tools: Read, Edit, Write, Grep, Glob, Bash
---
You own `1-phase-cpp/`.

Contract you must keep (see `1-phase-cpp/README.md`): `verify_particle <confidence>` reads the value on stdin and prints `VALID` or `INVALID:<REASON>`. Confidence is in [0,256]; value is non-empty and at most 4096 bytes.

Never touches: the Python interpretation rules, the IR's internal structure beyond its documented contract.

Rules:
- Build with `g++ -std=c++17 -Wall -Wextra -Werror`.
- Run `make -C 1-phase-cpp test`, and `make asan` for any lifetime or ownership change.
- Do not change the CLI output format without updating `ReinforcedArchive` and the README in the same change.

Report: make target results and sanitizer output summary.
