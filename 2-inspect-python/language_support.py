"""Language catalog and conservative pattern rules for unsupported front ends."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import re


class ExtendedLanguage(IntEnum):
    CSHARP = 8
    CLOJURE = 9
    CSS = 10
    DART = 11
    DOCKERFILE = 12
    ELIXIR = 13
    EMACS_LISP = 14
    HASKELL = 15
    JAVASCRIPT = 16
    JULIA = 17
    JUPYTER = 18
    KOTLIN = 19
    LUA = 20
    MATLAB = 21
    OBJECTIVE_C = 22
    PERL = 23
    PHP = 24
    POWERSHELL = 25
    R = 26
    SCALA = 27
    SHELL = 28
    SWIFT = 29
    TEX = 30
    TYPESCRIPT = 31
    VUE = 32


LANGUAGE_NAMES = {
    ExtendedLanguage.CSHARP: "C#", ExtendedLanguage.CLOJURE: "Clojure",
    ExtendedLanguage.CSS: "CSS", ExtendedLanguage.DART: "Dart",
    ExtendedLanguage.DOCKERFILE: "Dockerfile", ExtendedLanguage.ELIXIR: "Elixir",
    ExtendedLanguage.EMACS_LISP: "Emacs Lisp", ExtendedLanguage.HASKELL: "Haskell",
    ExtendedLanguage.JAVASCRIPT: "JavaScript", ExtendedLanguage.JULIA: "Julia",
    ExtendedLanguage.JUPYTER: "Jupyter Notebook", ExtendedLanguage.KOTLIN: "Kotlin",
    ExtendedLanguage.LUA: "Lua", ExtendedLanguage.MATLAB: "MATLAB",
    ExtendedLanguage.OBJECTIVE_C: "Objective-C", ExtendedLanguage.PERL: "Perl",
    ExtendedLanguage.PHP: "PHP", ExtendedLanguage.POWERSHELL: "PowerShell",
    ExtendedLanguage.R: "R", ExtendedLanguage.SCALA: "Scala",
    ExtendedLanguage.SHELL: "Shell", ExtendedLanguage.SWIFT: "Swift",
    ExtendedLanguage.TEX: "TeX", ExtendedLanguage.TYPESCRIPT: "TypeScript",
    ExtendedLanguage.VUE: "Vue",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    message: str
    line: int
    weight: int
    fix_hint: str = ""


RULES = {
    ExtendedLanguage.CSHARP: [(r"\bunsafe\b", "unsafe block requires review", 35, "prefer safe APIs")],
    ExtendedLanguage.CLOJURE: [(r"\beval\b", "dynamic eval requires review", 45, "prefer data-driven dispatch")],
    ExtendedLanguage.CSS: [(r"!important", "important override reduces cascade clarity", 20, "prefer selector specificity")],
    ExtendedLanguage.DART: [(r"\bdynamic\b", "dynamic value bypasses static checks", 25, "use a concrete type")],
    ExtendedLanguage.DOCKERFILE: [(r"^\s*ADD\s+", "ADD has implicit extraction/network behavior", 25, "prefer COPY for local files")],
    ExtendedLanguage.ELIXIR: [(r"\bspawn\s*\(", "unbounded process creation requires supervision", 35, "use a supervisor")],
    ExtendedLanguage.EMACS_LISP: [(r"\beval\b", "dynamic evaluation requires review", 40, "prefer quoted forms")],
    ExtendedLanguage.HASKELL: [(r"\bunsafePerformIO\b", "unsafe IO bypasses effect tracking", 60, "keep effects explicit")],
    ExtendedLanguage.JAVASCRIPT: [
        (r"\beval\s*\(", "dynamic evaluation is unsafe", 60, "remove eval"),
        (r"\bdocument\.write\s*\(", "document.write can inject unescaped markup", 40, "use DOM APIs"),
        (r"\.innerHTML\s*=", "innerHTML assignment can inject markup", 45, "assign textContent or sanitize"),
    ],
    ExtendedLanguage.JULIA: [(r"\beval\b", "dynamic evaluation requires review", 40, "prefer functions")],
    ExtendedLanguage.JUPYTER: [(r"get_ipython\s*\(", "notebook shell escape requires review", 50, "avoid shell escapes")],
    ExtendedLanguage.KOTLIN: [(r"\b!!", "non-null assertion can crash at runtime", 45, "use safe calls")],
    ExtendedLanguage.LUA: [(r"\bloadstring\b", "dynamic code loading requires review", 50, "validate code before loading")],
    ExtendedLanguage.MATLAB: [(r"\beval\s*\(", "dynamic evaluation requires review", 45, "prefer function handles")],
    ExtendedLanguage.OBJECTIVE_C: [(r"\bmalloc\s*\(", "manual allocation requires ownership review", 30, "use managed ownership where possible")],
    ExtendedLanguage.PERL: [(r"\beval\s*[$\"'(]", "runtime eval requires error handling", 40, "check $@ explicitly")],
    ExtendedLanguage.PHP: [(r"\beval\s*\(", "dynamic evaluation is unsafe", 70, "remove eval")],
    ExtendedLanguage.POWERSHELL: [(r"\bInvoke-Expression\b|\biex\b", "dynamic command execution is unsafe", 70, "use parameterized commands")],
    ExtendedLanguage.R: [(r"\beval\s*\(", "dynamic evaluation requires review", 40, "prefer explicit calls")],
    ExtendedLanguage.SCALA: [(r"\basInstanceOf\b", "unchecked cast can fail at runtime", 35, "use pattern matching")],
    ExtendedLanguage.SHELL: [(r"\beval\s+", "shell eval expands untrusted text", 70, "use arrays and quoted variables")],
    ExtendedLanguage.SWIFT: [(r"\btry!", "forced try can trap at runtime", 45, "handle the error")],
    ExtendedLanguage.TEX: [(r"\\write18", "shell escape executes external commands", 70, "disable unrestricted shell escape")],
    ExtendedLanguage.TYPESCRIPT: [(r":\s*any\b", "any bypasses static checks", 30, "use an explicit type")],
    ExtendedLanguage.VUE: [(r"v-html\s*=", "raw HTML binding can inject markup", 60, "sanitize the value")],
}


def inspect(code: str, language: ExtendedLanguage):
    findings = []
    for pattern, message, weight, hint in RULES.get(language, []):
        for match in re.finditer(pattern, code, re.I | re.M):
            findings.append(Finding("error", message, code.count("\n", 0, match.start()) + 1, weight, hint))
    return findings
