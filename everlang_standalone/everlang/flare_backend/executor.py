"""Flare-backed execution for everlang-dpl.

Flare (vendored v0.2.0, see FLARE_VERSION) compiles Python-shaped source to
a native binary via gcc and runs it. This module is the adapter between that
engine and DPL's confidence model: a program's stdout becomes the value of an
EParticle, and its confidence is earned only by completing cleanly under
Flare's execution anchor.

Confidence mapping (conservative, no silent fallback to CPython):
  exit 0                 -> EParticle(stdout, 256)   # CERTAIN
  compile error          -> EParticle("Quarantined(Z)", 0)
  runtime non-zero exit  -> EParticle("Quarantined(Z)", 0)  # clean Flare error
  death by signal        -> EParticle("Quarantined(Z)", 0)  # anchor breached
  timeout                -> EParticle("Quarantined(Z)", 0)

A snippet Flare cannot compile is Z, per DPL semantics ("refused, never
emulated"). Flare is a Python-shaped *subset* (lowercase true/false, no
break/continue, no raise, no inheritance, string-keyed dicts only); those
limits surface here as compile errors, never as silent rewrites.
"""

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..core.particle import EParticle

_BACKEND_DIR = Path(__file__).resolve().parent
_FLARE_PKG = _BACKEND_DIR / "flare"
_RT_DIR = _BACKEND_DIR / "rt"

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_OPT = "2"


@dataclass
class FlareResult:
    """One Flare execution, with its DPL confidence attached."""
    stdout: str
    stderr: str
    returncode: Optional[int]
    error: Optional[str]   # human-readable reason when confidence is 0
    particle: EParticle
    elapsed_s: float
    executed: bool = True  # False only when the caller skipped execution

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _z(error: str, elapsed_s: float, executed: bool = True) -> FlareResult:
    return FlareResult(
        stdout="", stderr="", returncode=None, error=error,
        particle=EParticle("Quarantined(Z)", 0),
        elapsed_s=elapsed_s, executed=executed)


class FlareExecutor:
    """Run Flare-shaped source through the vendored Flare compiler."""

    def __init__(self, backend_dir: Optional[Path] = None):
        self.backend_dir = Path(backend_dir) if backend_dir else _BACKEND_DIR
        if not (self.backend_dir / "flare" / "cli.py").is_file():
            raise FileNotFoundError(
                "vendored Flare not found at %s (expected flare/cli.py)"
                % self.backend_dir)
        if not (self.backend_dir / "rt" / "flare_rt.h").is_file():
            raise FileNotFoundError(
                "vendored Flare runtime header not found at %s"
                % (self.backend_dir / "rt" / "flare_rt.h"))

    @staticmethod
    def available() -> bool:
        return (_FLARE_PKG / "cli.py").is_file() and (_RT_DIR / "flare_rt.h").is_file()

    def _load_cli(self):
        # The vendored flare/ package has no __init__.py (namespace package);
        # its parent dir must be on sys.path, exactly as flare-bin does.
        backend = str(self.backend_dir)
        if backend not in sys.path:
            sys.path.insert(0, backend)
        import flare.cli as cli  # noqa: E402  (import after path setup)
        return cli

    def run(self, source: str, *, opt: str = DEFAULT_OPT,
            timeout: float = DEFAULT_TIMEOUT_S,
            prog_args: Optional[List[str]] = None,
            extra_files: Optional[dict] = None) -> FlareResult:
        """Compile `source` with Flare and run the resulting binary.

        Returns a FlareResult whose particle carries stdout at confidence 256
        on clean exit, or Quarantined(Z) at 0 on any failure.

        `extra_files`: {filename: content} written next to the snippet, so
        multi-file programs (`import name` resolves sibling `<name>.fl`)
        work through the snippet API.
        """
        t0 = time.perf_counter()
        try:
            cli = self._load_cli()
        except Exception as exc:  # vendored copy unimportable: refuse, don't guess
            return _z("flare backend unavailable: %s" % exc, time.perf_counter() - t0)
        try:
            with tempfile.TemporaryDirectory(prefix="everlang-flare-") as tmp:
                src_path = os.path.join(tmp, "snippet.fl")
                with open(src_path, "w") as fh:
                    fh.write(source)
                for name, content in (extra_files or {}).items():
                    with open(os.path.join(tmp, name), "w") as fh:
                        fh.write(content)
                exe = cli.cached_build(source, tmp, opt)
                r = subprocess.run(
                    [exe] + list(prog_args or []),
                    capture_output=True, text=True, timeout=timeout)
        except Exception as exc:
            # ParseError / CompileError / C compilation failure / timeout:
            # all are refusals, never emulated. TimeoutExpired has no
            # returncode; everything else here is a compile-stage failure.
            elapsed = time.perf_counter() - t0
            if isinstance(exc, subprocess.TimeoutExpired):
                return _z("timed out after %.1fs" % timeout, elapsed)
            return _z("flare compile failed: %s" % exc, elapsed)
        elapsed = time.perf_counter() - t0
        if r.returncode == 0:
            return FlareResult(
                stdout=r.stdout, stderr=r.stderr, returncode=0, error=None,
                particle=EParticle(r.stdout.strip(), 256), elapsed_s=elapsed)
        if r.returncode is not None and r.returncode < 0:
            return FlareResult(
                stdout=r.stdout, stderr=r.stderr, returncode=r.returncode,
                error="anchor breached: died by signal %d" % (-r.returncode),
                particle=EParticle("Quarantined(Z)", 0), elapsed_s=elapsed)
        err = (r.stderr or "").strip() or ("exited %d" % r.returncode)
        return FlareResult(
            stdout=r.stdout, stderr=r.stderr, returncode=r.returncode,
            error=err, particle=EParticle("Quarantined(Z)", 0),
            elapsed_s=elapsed)

    def run_file(self, path, *, opt: str = DEFAULT_OPT,
                 timeout: float = DEFAULT_TIMEOUT_S) -> FlareResult:
        """Run a .fl file in place, so sibling `import` files resolve
        from the file's own directory (unlike run(), which uses a temp dir)."""
        t0 = time.perf_counter()
        try:
            cli = self._load_cli()
            with open(path) as fh:
                source = fh.read()
            base_dir = os.path.dirname(os.path.realpath(path))
            exe = cli.cached_build(source, base_dir, opt)
            r = subprocess.run([exe], capture_output=True, text=True,
                               timeout=timeout)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            if isinstance(exc, subprocess.TimeoutExpired):
                return _z("timed out after %.1fs" % timeout, elapsed)
            return _z("flare compile failed: %s" % exc, elapsed)
        elapsed = time.perf_counter() - t0
        if r.returncode == 0:
            return FlareResult(
                stdout=r.stdout, stderr=r.stderr, returncode=0, error=None,
                particle=EParticle(r.stdout.strip(), 256), elapsed_s=elapsed)
        if r.returncode is not None and r.returncode < 0:
            return FlareResult(
                stdout=r.stdout, stderr=r.stderr, returncode=r.returncode,
                error="anchor breached: died by signal %d" % (-r.returncode),
                particle=EParticle("Quarantined(Z)", 0), elapsed_s=elapsed)
        err = (r.stderr or "").strip() or ("exited %d" % r.returncode)
        return FlareResult(
            stdout=r.stdout, stderr=r.stderr, returncode=r.returncode,
            error=err, particle=EParticle("Quarantined(Z)", 0),
            elapsed_s=elapsed)
