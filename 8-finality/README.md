# Layer 8 — Rust/Go finality drive

Python is the semantic reference and fast orchestration layer. Rust and Go
are release targets. The finality drive emits both targets, compiles them,
runs them, and compares output against Python.

A target that compiles but disagrees with Python is a failure. An unavailable
toolchain is reported as unavailable, never as a pass.
