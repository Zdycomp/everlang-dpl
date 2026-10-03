"""
ReinforcedArchive: an opt-in, drop-in wrapper around EArchive that reinforces
the self-healing Archive with two backend phases, each used through the
CLI/file contract it documents (never by re-implementing its logic here):

  - 1-phase-cpp/bin/verify_particle: a native safety-verification gate.
    Every write is passed through it first; a write it rejects is recorded
    into the SQL archive's `rejected_writes` table instead of being trusted.
  - 4-archive-sql/archive_db.py (SqlArchive): durable SQLite persistence,
    so the Archive's history survives past this process's lifetime (the
    in-process EArchive loses everything on restart).

Both phases are optional at runtime: if the C++ binary isn't built, or the
SQL module can't be imported, ReinforcedArchive falls back to exactly
EArchive's own in-process behavior. Nothing here changes EArchive itself or
its existing callers/tests.

`transpile_and_archive` additionally routes everlang/transpiler's
SuperTranspiler output through the same two backends: each rendered
language's code is gated by the C++ verifier and persisted into the SQL
archive's `transpilations` table, which 5-runtime-java's TranspileAudit
independently re-renders and cross-checks (the same pattern already used
for `emulate_repair` vs. RepairAuditor).
"""
import importlib.util
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from .archive import EArchive
from .particle import EParticle
from ..transpiler import SuperTranspiler, validate_template

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CPP_BINARY = _REPO_ROOT / "1-phase-cpp" / "bin" / "verify_particle"
_DEFAULT_SQL_DIR = _REPO_ROOT / "4-archive-sql"

_VERIFIER_TIMEOUT_SECONDS = 2


class ReinforcedArchive:
    """Drop-in reinforcement of EArchive: same public methods/return values,
    plus optional native safety verification and durable SQL persistence."""

    def __init__(
        self,
        cpp_binary_path: Optional[str] = None,
        sql_module_dir: Optional[str] = None,
        sql_db_path: Optional[str] = None,
    ) -> None:
        self._archive = EArchive()
        self._log_lock = threading.Lock()
        self._transpiler = SuperTranspiler()
        self._template_versions: Dict[str, int] = {}
        # Guards the transpiler's templates together with _template_versions, so a
        # rendering is always stamped with the version that produced it (taken before
        # _log_lock, never after, to keep a single lock order).
        self._languages_lock = threading.Lock()

        self._cpp_binary = Path(cpp_binary_path) if cpp_binary_path else _DEFAULT_CPP_BINARY
        self.cpp_verifier_available = self._cpp_binary.is_file()

        self._sql = None
        self.sql_available = False
        sql_dir = Path(sql_module_dir) if sql_module_dir else _DEFAULT_SQL_DIR
        try:
            # Import by file path under a dedicated module name, rather than
            # a bare `import archive_db` after a sys.path.insert: the latter
            # is silently defeated whenever anything else has already put a
            # module named "archive_db" into sys.modules (import looks there
            # first, before consulting sys.path at all).
            module_file = sql_dir / "archive_db.py"
            spec = importlib.util.spec_from_file_location("everlang_sql_archive_db", module_file)
            archive_db = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(archive_db)

            self._sql = archive_db.SqlArchive(db_path=sql_db_path)
            self.sql_available = True
            self._load_custom_templates()
        except Exception as exc:  # native/SQL reinforcement is best-effort
            print(f"ReinforcedArchive: SQL archive unavailable ({exc})", file=sys.stderr)
            self._sql = None
            self.sql_available = False

    # -- verification -----------------------------------------------------

    def _verify_with_cpp(self, value, confidence: int) -> Tuple[Optional[bool], str]:
        """Returns (verdict, reason). verdict is True/False per the
        verify_particle CLI contract, or None if the verifier is unavailable
        or errors (never blocks the caller). The reason is returned alongside
        the verdict rather than stashed on self, so concurrent callers never
        read back another thread's result (see memory-safety audit finding A)."""
        if not self.cpp_verifier_available:
            return None, ""
        try:
            result = subprocess.run(
                [str(self._cpp_binary), str(confidence)],
                input=str(value),
                capture_output=True,
                text=True,
                timeout=_VERIFIER_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            print(f"ReinforcedArchive: verify_particle failed to run ({exc})", file=sys.stderr)
            self.cpp_verifier_available = False
            return None, ""
        stdout = result.stdout.strip()
        if stdout == "VALID":
            return True, ""
        # Any INVALID:<REASON> (or unexpected output) is treated as rejected.
        return False, stdout or f"exit={result.returncode}"

    # -- EArchive-compatible API -------------------------------------------

    def _sql_write(self, fn, *args, **kwargs):
        """Runs one SqlArchive write and returns its result (None on failure),
        never letting a sqlite3 error escape to the caller (see memory-safety
        audit finding B): a locked/closed/unreachable database must not crash
        a self-healing write that already succeeded in-memory, nor leave the
        caller unaware the SQL leg failed."""
        try:
            with self._log_lock:
                return fn(*args, **kwargs)
        except sqlite3.Error as exc:
            print(f"ReinforcedArchive: SQL write failed, disabling SQL reinforcement ({exc})", file=sys.stderr)
            self.sql_available = False
            return None

    def log_boundary_marker(self, context: str, particle: EParticle, reason: str) -> None:
        # Never regress existing in-process behavior.
        self._archive.log_boundary_marker(context, particle, reason)

        verdict, verifier_reason = self._verify_with_cpp(particle.value, particle.confidence)
        if not self.sql_available:
            return
        if verdict is False:
            self._sql_write(
                self._sql.record_rejected_write,
                table_name="boundary_markers",
                reason=verifier_reason or "INVALID",
                payload=f"context={context!r} value={particle.value!r} confidence={particle.confidence}",
            )
        else:
            # verdict True, or None (verifier unavailable) -> persist as-is.
            self._sql_write(
                self._sql.record_boundary_marker,
                context=context,
                value=particle.value,
                confidence=particle.confidence,
                reason=reason,
            )

    def emulate_repair(self, failing_signature: str, error_distance: int) -> EParticle:
        # Identical logic/return value as EArchive; this call is the source of truth.
        particle = self._archive.emulate_repair(failing_signature, error_distance)

        if self.sql_available:
            self._sql_write(
                self._sql.record_repair,
                failing_signature=failing_signature,
                error_distance=error_distance,
                repaired_value=particle.value,
                confidence=particle.confidence,
                quarantined=particle.is_z(),
            )
        return particle

    def calculate_evolve_vector(self, action_success: float, reaction_data: float, force: float) -> float:
        vector = self._archive.calculate_evolve_vector(action_success, reaction_data, force)

        # EArchive returns 0.0 both for its "no-op" bail-out (reaction_data==0
        # or force==0) and for a real vector that happens to equal 0.0 exactly
        # -- these are indistinguishable from the return value alone. We log
        # every call's result as telemetry regardless; this is a known
        # limitation, not a correctness issue (the SQL archive is a record of
        # attempts, not a re-derivation of EArchive's internal state).
        if self.sql_available:
            self._sql_write(
                self._sql.record_evolved_vector,
                vector=vector,
                action_success=action_success,
                reaction_data=reaction_data,
                force=force,
            )
        return vector

    def transpile_and_archive(self, name: str, val: str, type_spec: str, conf: int) -> Dict[str, str]:
        """Renders `val` into every SuperTranspiler-configured language,
        gates each rendering through the C++ verifier, and persists each
        one into the SQL archive's `transpilations` table. Always returns
        the rendered dict (the transpiler itself never depends on either
        backend being available -- same fallback philosophy as the rest of
        this class)."""
        with self._languages_lock:
            rendered = self._transpiler.transpile(name, val, type_spec, conf)
            versions = dict(self._template_versions)

        if not self.sql_available:
            return rendered

        for target_language, code in rendered.items():
            verdict, verifier_reason = self._verify_with_cpp(code, conf)
            if verdict is False:
                self._sql_write(
                    self._sql.record_rejected_write,
                    table_name="transpilations",
                    reason=verifier_reason or "INVALID",
                    payload=f"name={name!r} target_language={target_language!r} code={code!r}",
                )
                continue
            # verdict True, or None (verifier unavailable) -> persist as-is.
            self._sql_write(
                self._sql.record_transpilation,
                name=name,
                val=val,
                type_spec=type_spec,
                confidence=conf,
                target_language=target_language,
                rendered_code=code,
                template_version=versions.get(target_language),
            )
        return rendered

    # -- custom language management ----------------------------------------

    def _load_custom_templates(self) -> None:
        """Load custom templates from SQL on init and register them with the transpiler."""
        if not self.sql_available:
            return
        try:
            templates = self._sql.load_custom_templates()
        except sqlite3.Error as exc:
            print(f"ReinforcedArchive: could not load custom templates ({exc})", file=sys.stderr)
            return
        for language, (version, template) in templates.items():
            try:
                self._transpiler.register_language(language, template)
            except ValueError as exc:
                print(f"ReinforcedArchive: skipping stored template {language} v{version} ({exc})", file=sys.stderr)
                continue
            self._template_versions[language] = version

    def register_language(self, language: str, template: str) -> Optional[int]:
        """Register a custom language target. With SQL available, the template
        is stored as a new version and that version number is returned and
        stamped on every rendering archived from then on; otherwise None."""
        validate_template(template)
        lang_upper = language.upper()
        with self._languages_lock:
            self._transpiler.register_language(language, template)
            self._template_versions.pop(lang_upper, None)
            if not self.sql_available:
                return None
            version = self._sql_write(
                self._sql.save_custom_template,
                language=lang_upper,
                template=template,
            )
            if version is not None:
                self._template_versions[lang_upper] = version
            return version

    def unregister_language(self, language: str) -> bool:
        """Remove a custom language. Returns True if removed. Its stored
        versions are retired, not deleted, so archived rows stay auditable."""
        lang_upper = language.upper()
        with self._languages_lock:
            if not self._transpiler.unregister_language(language):
                return False
            self._template_versions.pop(lang_upper, None)
            if self.sql_available:
                self._sql_write(self._sql.retire_custom_template, language=lang_upper)
            return True

    @property
    def template_versions(self) -> Dict[str, int]:
        with self._languages_lock:
            return dict(self._template_versions)

    @property
    def custom_languages(self) -> Dict[str, str]:
        return self._transpiler.custom_languages

    def close(self) -> None:
        if self._sql is not None:
            self._sql.close()

    # -- pass-through accessors matching EArchive's public attributes -----

    @property
    def boundary_markers(self):
        return self._archive.boundary_markers

    @property
    def evolved_vectors(self):
        return self._archive.evolved_vectors
