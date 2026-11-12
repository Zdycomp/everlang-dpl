"""Flare backend for everlang-dpl (vendored Flare v0.2.0).

Flare compiles Python-shaped source to a native binary via gcc. This package
adapts it to DPL: execution results come back as EParticles with confidence
earned only by a clean run (see executor.py for the mapping).
"""

from pathlib import Path

from .executor import FlareExecutor, FlareResult


def _flare_version() -> str:
    try:
        return (Path(__file__).resolve().parent / "FLARE_VERSION").read_text().splitlines()[0]
    except OSError:
        return "unknown"


FLARE_VERSION = _flare_version()

__all__ = ["FlareExecutor", "FlareResult", "FLARE_VERSION"]
