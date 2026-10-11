#!/usr/bin/env python3
"""
translate.py — Ever Language, Layer 2 (Python)

The translator. Every language becomes E-particles here.

Python owns this layer because parsing is pattern work, and Python is the
best pattern-matching glue in the stack. It speaks to Layer 0 through the
serialized particle line format, so C, C++, Java and SQL all read exactly
what Python writes.

Ever accepts:  C · C++ · Python · Ruby · SQL · Java · HTML

Codric Enterprise · Ricky (Dreid) · 2026
Theory of Relative E:  E = MC²
"""

import re
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


# ─────────────────────────────────────────────
# Constants — must match 0-core-c/ever.h exactly
# ─────────────────────────────────────────────

E_ZERO               = 0
E_CERTAIN            = 256
E_PI_WIDTH_WARN      = 81      # int(256 / pi)
E_PI_WIDTH_ENUMERATE = 25      # int(256 / pi^2)
E_EMULATE_CEILING    = 3       # int(pi)
E_PHI                = 1.6180339887


class EState(IntEnum):
    Z         = 0
    CONFIDENT = 1
    CERTAIN   = 2
    EQUIV     = 3
    EXPRESS   = 4
    EMULATING = 5
    EVOLVED   = 6
    ABSENT    = 7
    ERROR     = 8


class ELang(IntEnum):
    C      = 0
    CPP    = 1
    PYTHON = 2
    RUBY   = 3
    SQL    = 4
    JAVA   = 5
    HTML   = 6
    EVER   = 7


# ─────────────────────────────────────────────
# The particle — same shape as the C struct
# ─────────────────────────────────────────────

@dataclass
class EParticle:
    state: EState = EState.Z
    phase: int = 0
    lang: ELang = ELang.EVER
    confidence: int = 0
    lo: int = 0
    hi: int = 0
    error_distance: int = 0
    generation: int = 0
    archive_id: int = -1
    born_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    ident: str = ""
    reason: str = ""

    # ── predicates ──

    @property
    def is_z(self) -> bool:
        return self.state == EState.Z

    @property
    def is_cleared(self) -> bool:
        if self.state in (EState.Z, EState.ERROR, EState.ABSENT):
            return False
        return self.confidence > E_ZERO

    @property
    def can_execute(self) -> bool:
        return self.is_cleared and self.confidence >= 128

    @property
    def width(self) -> int:
        return self.hi - self.lo

    def pi_status(self) -> str:
        w = self.width
        if w > E_PI_WIDTH_WARN:
            return "APPROACHING_Z"
        if w > E_PI_WIDTH_ENUMERATE:
            return "ENUMERATE"
        return "ACCEPTABLE"

    # ── the line format Layer 0 reads ──

    def serialize(self) -> str:
        return "|".join(str(x) for x in (
            int(self.state), self.phase, int(self.lang),
            self.confidence, self.lo, self.hi,
            self.error_distance, self.generation,
            self.archive_id, self.born_ms,
            self.ident, self.reason,
        ))

    @staticmethod
    def deserialize(line: str) -> "EParticle":
        p = line.split("|")
        if len(p) < 12:
            return EParticle(state=EState.Z, reason="malformed particle line")
        return EParticle(
            state=EState(int(p[0])), phase=int(p[1]), lang=ELang(int(p[2])),
            confidence=int(p[3]), lo=int(p[4]), hi=int(p[5]),
            error_distance=int(p[6]), generation=int(p[7]),
            archive_id=int(p[8]), born_ms=int(p[9]),
            ident=p[10], reason=p[11],
        )

    def __repr__(self) -> str:
        return (f"E<{EState(self.state).name}>({self.ident} "
                f"@ {self.confidence}/256 · {ELang(self.lang).name})")


# ── constructors ──

def e_z(ident: str, reason: str = "unverified") -> EParticle:
    return EParticle(state=EState.Z, ident=ident, reason=reason)

def e_certain(ident: str, lang: ELang) -> EParticle:
    return EParticle(state=EState.CERTAIN, lang=lang, ident=ident,
                     confidence=E_CERTAIN, lo=E_CERTAIN, hi=E_CERTAIN)

def e_confident(ident: str, degree: int, lang: ELang) -> EParticle:
    if degree <= E_ZERO:
        return e_z(ident, "confidence collapsed to zero")
    if degree >= E_CERTAIN:
        return e_certain(ident, lang)
    return EParticle(state=EState.CONFIDENT, lang=lang, ident=ident,
                     confidence=degree, lo=degree, hi=degree)

def e_equivalence(ident: str, lo: int, hi: int, lang: ELang) -> EParticle:
    if lo > hi:
        lo, hi = hi, lo
    return EParticle(state=EState.EQUIV, lang=lang, ident=ident,
                     lo=lo, hi=hi, confidence=(lo + hi) // 2)

def e_error(ident: str, reason: str, at: int = 0) -> EParticle:
    return EParticle(state=EState.ERROR, ident=ident, reason=reason,
                     confidence=E_ZERO, lo=at, hi=at)


# ─────────────────────────────────────────────
# A finding — one thing the parser noticed
# ─────────────────────────────────────────────

# The five ways a binding fails. Every structurally checkable error in
# every language reduces to one of these.
DEFECT_UNBOUND   = "unbound"
DEFECT_MISBOUND  = "misbound"
DEFECT_UNBOUNDED = "unbounded"
DEFECT_OVERBOUND = "overbound"
DEFECT_ORPHANED  = "orphaned"


def classify(message: str) -> str:
    """Map a finding to its binding defect.

    This is the universality claim made operational: the inspectors were
    written per-language, but every one of their findings lands in the
    same five buckets.
    """
    m = message.lower()
    if any(k in m for k in ("null", "nil", "none", "without a guard",
                            "never bound", "undefined")):
        return DEFECT_UNBOUND
    if any(k in m for k in ("missing semicolon", "missing end",
                            "missing colon", "unclosed", "unterminated",
                            "unbalanced", "without where", "select *",
                            "overflow", "gets is unsafe", "without if exists")):
        return DEFECT_UNBOUNDED
    if any(k in m for k in ("compared with ==", "type", "cartesian",
                            "concatenation into sql", "eval",
                            "empty catch", "bare except", "bare rescue")):
        return DEFECT_MISBOUND
    if any(k in m for k in ("mutable default", "global variable",
                            "namespace std", "shared")):
        return DEFECT_OVERBOUND
    if any(k in m for k in ("without delete", "without matching free",
                            "virtual destructor", "leak")):
        return DEFECT_ORPHANED
    return DEFECT_MISBOUND


@dataclass
class Finding:
    kind: str              # "error" | "pattern"
    message: str
    line: int
    weight: int            # how much confidence this costs or earns
    fix_hint: str = ""     # what Layer 4 archives as the teaching template

    @property
    def defect(self) -> str:
        return classify(self.message) if self.kind == "error" else "none"


# ─────────────────────────────────────────────
# Language detection
# ─────────────────────────────────────────────

def detect(code: str) -> ELang:
    """Order matters. Most distinctive markers first."""
    s = code.strip()

    if re.search(r'^\s*<(!DOCTYPE|html|div|form|body|head|p|a|span|img)\b',
                 s, re.I | re.M):
        return ELang.HTML

    if re.search(r'\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|CREATE TABLE|'
                 r'ALTER TABLE|DROP TABLE)\b', s, re.I):
        return ELang.SQL

    if "#include" in s:
        cpp_markers = ("iostream", "std::", "namespace", "template<",
                       "class ", "vector<", "cout")
        return ELang.CPP if any(m in s for m in cpp_markers) else ELang.C

    if re.search(r'\b(public|private|protected)\s+(static\s+)?'
                 r'(class|void|int|String)\b', s):
        return ELang.JAVA

    if re.search(r'^\s*def\s+\w+.*\|.*\|', s, re.M):     # ruby block params
        return ELang.RUBY
    if re.search(r'\b(end|puts|require|attr_accessor|do\s*\|)\b', s):
        return ELang.RUBY

    # A bare C function with no include directive. Found by cross-checking
    # Layer 2 against Layer 6: both agreed on 'Ever', and both were wrong.
    if re.search(r'^\s*(?:static\s+|const\s+|unsigned\s+)*'
                 r'(int|char|float|double|long|short|void|size_t)\s*\*?\s*'
                 r'\w+\s*\([^;]*\)\s*\{', s, re.M):
        return ELang.C

    if re.search(r'^\s*def\s+\w+\s*\(.*\)\s*(->.*)?:', s, re.M):
        return ELang.PYTHON
    if re.search(r'^\s*(import|from)\s+\w+', s, re.M) and ":" in s:
        return ELang.PYTHON

    return ELang.EVER


# ─────────────────────────────────────────────
# Per-language inspectors
#
# Each returns Findings. Errors cost confidence.
# Recognised good patterns earn it.
# ─────────────────────────────────────────────

class Inspector:
    lang: ELang = ELang.EVER

    def inspect(self, code: str) -> List[Finding]:
        raise NotImplementedError

    @staticmethod
    def _lines(code: str):
        return list(enumerate(code.split("\n"), start=1))


class CInspector(Inspector):
    lang = ELang.C

    def inspect(self, code):
        out = []
        for n, line in self._lines(code):
            t = line.strip()
            if not t or t.startswith(("//", "/*", "*", "#")):
                continue
            if re.match(r'^\s*(int|char|float|double|long|short|void|'
                        r'unsigned|size_t)\b.*[^;{}\s]$', t) and \
               not t.endswith((",", "\\", ")")):
                out.append(Finding("error", "statement missing semicolon",
                                   n, 40, "append ;"))
            # a statement running straight into a closing brace, e.g.
            #   int add(int x, int y) { return x + y }
            if re.search(r'(?:\breturn\b[^;{}]*[^;{}\s]|[\w\]\)]\s*='
                         r'[^;{}]*[^;{}\s])\s*\}', t):
                out.append(Finding("error", "statement missing semicolon "
                                   "before closing brace", n, 40, "append ;"))
            # Per-line paren counting is wrong for C: multi-line calls
            # and declarations are normal and balance across lines.
            # Found by running this inspector against Tapestry's own C
            # atom, which gcc -Wall compiles clean while this rule
            # reported 54 errors. Balance is now checked file-wide below.
            if re.search(r'\bmalloc\s*\(', t) and "free" not in code:
                out.append(Finding("error", "malloc without matching free",
                                   n, 60, "pair every malloc with free"))
            if re.search(r'\bgets\s*\(', t):
                out.append(Finding("error", "gets is unsafe, buffer overflow",
                                   n, 90, "use fgets with a bound"))

        stripped = re.sub(r'"(\\.|[^"\\])*"', '""', code)
        stripped = re.sub(r"'(\\.|[^'\\])*'", "''", stripped)
        stripped = re.sub(r'//[^\n]*', '', stripped)
        stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.S)
        if stripped.count("(") != stripped.count(")"):
            out.append(Finding("error", "unbalanced parentheses in file",
                               1, 50, "match ( with )"))
        if stripped.count("{") != stripped.count("}"):
            out.append(Finding("error", "unbalanced braces in file",
                               1, 50, "match { with }"))

        if "#include" in code:
            out.append(Finding("pattern", "header inclusion", 1, 20))
        if re.search(r'\bint\s+main\s*\(', code):
            out.append(Finding("pattern", "entry point declared", 1, 25))
            if "return" not in code:
                out.append(Finding("error", "main does not return", 1, 30,
                                   "add return 0;"))
        return out


class CppInspector(Inspector):
    lang = ELang.CPP

    def inspect(self, code):
        out = CInspector().inspect(code)
        out = [f for f in out if "malloc" not in f.message]

        if re.search(r'\bnew\b', code) and not re.search(r'\bdelete\b', code) \
           and "unique_ptr" not in code and "shared_ptr" not in code:
            out.append(Finding("error", "new without delete or smart pointer",
                               1, 60, "prefer std::unique_ptr"))
        if "using namespace std" in code:
            out.append(Finding("error", "using namespace std in header scope",
                               1, 25, "qualify with std::"))
        if re.search(r'\bclass\b', code):
            out.append(Finding("pattern", "class declared", 1, 25))
            if re.search(r'\bvirtual\b', code) and \
               not re.search(r'virtual\s+~', code):
                out.append(Finding("error", "virtual method without virtual "
                                   "destructor", 1, 55,
                                   "declare virtual ~Class()"))
        if "unique_ptr" in code or "shared_ptr" in code:
            out.append(Finding("pattern", "RAII ownership", 1, 30))
        return out


class PythonInspector(Inspector):
    lang = ELang.PYTHON

    def inspect(self, code):
        out = []
        for n, line in self._lines(code):
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            if re.match(r'^\s*(def|class|if|elif|else|for|while|try|except|'
                        r'finally|with)\b', line) and not t.endswith(":") \
               and "\\" not in t and not t.endswith((",", "(")):
                out.append(Finding("error", "block header missing colon",
                                   n, 45, "append :"))
            if "\t" in line and "    " in line:
                out.append(Finding("error", "mixed tabs and spaces",
                                   n, 40, "use four spaces"))
            if re.match(r'^\s*except\s*:\s*$', line):
                out.append(Finding("error", "bare except swallows everything",
                                   n, 50, "except SpecificError as e"))
            if re.search(r'\beval\s*\(', t):
                out.append(Finding("error", "eval on untrusted input",
                                   n, 80, "use ast.literal_eval"))
            if re.search(r'\bdef\s+\w+\s*\([^)]*=\s*(\[\]|\{\})', t):
                out.append(Finding("error", "mutable default argument",
                                   n, 55, "default to None"))

        if re.search(r'^\s*def\s+', code, re.M):
            out.append(Finding("pattern", "function defined", 1, 20))
        if re.search(r'->\s*\w+\s*:', code):
            out.append(Finding("pattern", "return type annotated", 1, 30))
        if re.search(r':\s*(int|str|float|bool|List|Dict|Optional)', code):
            out.append(Finding("pattern", "parameters typed", 1, 30))
        return out


class RubyInspector(Inspector):
    lang = ELang.RUBY

    def inspect(self, code):
        out = []
        opens = len(re.findall(r'\b(def|do|class|module|if|unless|case|'
                               r'begin|while)\b', code))
        ends = len(re.findall(r'\bend\b', code))
        inline_if = len(re.findall(r'\S\s+(if|unless)\s+\S', code))
        expected = max(0, opens - inline_if)
        if ends < expected:
            out.append(Finding("error", f"missing end: {expected} opened, "
                               f"{ends} closed", 1, 50, "add end"))

        for n, line in self._lines(code):
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            if re.search(r'\beval\s*\(', t):
                out.append(Finding("error", "eval on untrusted input",
                                   n, 80, "avoid eval"))
            if re.search(r'\brescue\s*$', t):
                out.append(Finding("error", "bare rescue swallows everything",
                                   n, 50, "rescue StandardError => e"))
            # Ruby's own globals are builtins, not smells. Found by
            # running this inspector against Tapestry's Ruby layer.
            if re.search(r'\$\w+', t) and not re.search(
                    r'\$(PROGRAM_NAME|stdout|stderr|stdin|LOAD_PATH|'
                    r'LOADED_FEATURES|ARGV|ERROR_INFO|0|\d)\b', t):
                out.append(Finding("error", "global variable",
                                   n, 30, "prefer an instance variable"))

        if re.search(r'\bdef\s+', code):
            out.append(Finding("pattern", "method defined", 1, 20))
        if "attr_accessor" in code or "attr_reader" in code:
            out.append(Finding("pattern", "attribute accessor", 1, 25))
        if re.search(r'\bdo\s*\|', code) or re.search(r'\{\s*\|', code):
            out.append(Finding("pattern", "block with parameters", 1, 25))
        if "freeze" in code:
            out.append(Finding("pattern", "immutability asserted", 1, 30))
        return out


class SqlInspector(Inspector):
    lang = ELang.SQL

    def inspect(self, code):
        out = []
        up = code.upper()

        if re.search(r'\bSELECT\s+\*', up):
            out.append(Finding("error", "SELECT * hides schema drift",
                               1, 35, "name the columns"))
        # Per statement, not per file. Checking the whole blob let a
        # WHERE in an unrelated SELECT mask an unbounded DELETE, which
        # is the single most destructive thing this inspector exists to
        # catch. Found by cell 4 of the notebook batch.
        for stmt in [x.strip() for x in up.split(";") if x.strip()]:
            if re.search(r'\b(DELETE\s+FROM|UPDATE)\b', stmt) and \
               not re.search(r'\bWHERE\b', stmt):
                out.append(Finding("error", "DELETE or UPDATE without WHERE",
                                   1, 95, "add a WHERE clause"))
        if re.search(r"[\"']\s*\+\s*|\%s\s*[\"']|\|\|\s*'", code):
            out.append(Finding("error", "string concatenation into SQL",
                               1, 90, "use bound parameters"))
        if re.search(r'\bDROP\s+TABLE\b', up) and \
           not re.search(r'\bIF\s+EXISTS\b', up):
            out.append(Finding("error", "DROP TABLE without IF EXISTS",
                               1, 60, "add IF EXISTS"))
        if re.search(r'\bCREATE\s+TABLE\b', up):
            out.append(Finding("pattern", "table defined", 1, 25))
            if not re.search(r'\bPRIMARY\s+KEY\b', up):
                out.append(Finding("error", "table without primary key",
                                   1, 50, "declare a PRIMARY KEY"))
        if re.search(r'\bJOIN\b', up) and not re.search(r'\bON\b', up):
            out.append(Finding("error", "JOIN without ON produces a "
                               "cartesian product", 1, 85, "add ON"))
        if re.search(r'\bINDEX\b', up):
            out.append(Finding("pattern", "index declared", 1, 30))
        if re.search(r'\bFOREIGN\s+KEY\b', up):
            out.append(Finding("pattern", "referential integrity", 1, 30))
        if re.search(r'\bTRANSACTION\b|\bBEGIN\b', up):
            out.append(Finding("pattern", "transactional boundary", 1, 30))
        return out


class JavaInspector(Inspector):
    lang = ELang.JAVA

    def inspect(self, code):
        out = []
        for n, line in self._lines(code):
            t = line.strip()
            if not t or t.startswith(("//", "*", "/*")):
                continue
            if re.match(r'^[\w\s\.\<\>\[\]]+=[^=].*[^;{}\s]$', t) and \
               not t.endswith((",", "(", "+")):
                out.append(Finding("error", "statement missing semicolon",
                                   n, 40, "append ;"))
            if re.search(r'\bcatch\s*\([^)]*\)\s*\{\s*\}', t):
                out.append(Finding("error", "empty catch block",
                                   n, 55, "log or rethrow"))
            if re.search(r'==\s*"', t) or re.search(r'"\s*==', t):
                out.append(Finding("error", "string compared with ==",
                                   n, 60, "use .equals()"))

        if re.search(r'\bnull\b', code) and \
           not re.search(r'!=\s*null|==\s*null|Optional|@Nullable', code):
            out.append(Finding("error", "null used without a guard",
                               1, 65, "check != null or use Optional"))
        if re.search(r'\bthrows\b|\bthrow\s+new\b', code) and \
           "try" not in code:
            out.append(Finding("error", "throw without any try boundary",
                               1, 45, "wrap in try/catch"))
        if re.search(r'\bpublic\s+class\b', code):
            out.append(Finding("pattern", "public class", 1, 25))
        if "try" in code and "catch" in code:
            out.append(Finding("pattern", "exception handled", 1, 30))
        if "final " in code:
            out.append(Finding("pattern", "immutability asserted", 1, 25))
        if "Optional" in code:
            out.append(Finding("pattern", "optional over null", 1, 30))
        return out


class HtmlInspector(Inspector):
    """Hand HTML. Written by a person, so inspected like a person wrote it."""
    lang = ELang.HTML

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    @staticmethod
    def _markup_only(code: str) -> str:
        """Script, style and comment bodies are not markup.

        Found by running Ever against its own interface: a <img> inside a
        JavaScript string is sample data, not an image, and flagging it
        drove a sound file to Z. A false positive that reaches Z is worse
        than a missed finding, because it teaches the corpus a lie.
        """
        code = re.sub(r'<!--.*?-->', '', code, flags=re.S)
        code = re.sub(r'<script\b[^>]*>.*?</script\s*>', '<script></script>',
                      code, flags=re.S | re.I)
        code = re.sub(r'<style\b[^>]*>.*?</style\s*>', '<style></style>',
                      code, flags=re.S | re.I)
        return code

    def inspect(self, code):
        code = self._markup_only(code)
        out = []

        for m in re.finditer(r'<img\b[^>]*>', code, re.I):
            if not re.search(r'\balt\s*=', m.group(0), re.I):
                out.append(Finding("error", "img without alt text",
                                   1, 55, 'add alt=""'))

        for m in re.finditer(r'<input\b[^>]*>', code, re.I):
            tag = m.group(0)
            if not re.search(r'\btype\s*=', tag, re.I):
                out.append(Finding("error", "input without type",
                                   1, 45, 'add type="text"'))
            if not re.search(r'\b(id|name|aria-label)\s*=', tag, re.I):
                out.append(Finding("error", "input with no label anchor",
                                   1, 40, "add id and a matching label"))

        for m in re.finditer(r'<a\b[^>]*target\s*=\s*["\']_blank["\'][^>]*>',
                             code, re.I):
            if "noopener" not in m.group(0):
                out.append(Finding("error", "target=_blank without noopener",
                                   1, 50, 'add rel="noopener noreferrer"'))

        if re.search(r'<form\b', code, re.I):
            out.append(Finding("pattern", "form element", 1, 20))
            if not re.search(r'\baction\s*=', code, re.I):
                out.append(Finding("error", "form without action",
                                   1, 40, "add action="))

        # unclosed non-void tags
        opened = re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)\b[^>/]*>', code)
        closed = re.findall(r'</([a-zA-Z][a-zA-Z0-9]*)\s*>', code)
        for tag in set(opened):
            low = tag.lower()
            if low in self.VOID:
                continue
            if opened.count(tag) > closed.count(tag):
                out.append(Finding("error", f"unclosed <{low}>",
                                   1, 50, f"add </{low}>"))

        if re.search(r'<!DOCTYPE', code, re.I):
            out.append(Finding("pattern", "doctype declared", 1, 25))
        if re.search(r'\blang\s*=', code, re.I):
            out.append(Finding("pattern", "language declared", 1, 25))
        if re.search(r'\baria-\w+\s*=', code, re.I):
            out.append(Finding("pattern", "aria attributes", 1, 30))
        if re.search(r'<(header|nav|main|footer|article|section)\b', code, re.I):
            out.append(Finding("pattern", "semantic structure", 1, 30))
        return out


INSPECTORS = {
    ELang.C:      CInspector(),
    ELang.CPP:    CppInspector(),
    ELang.PYTHON: PythonInspector(),
    ELang.RUBY:   RubyInspector(),
    ELang.SQL:    SqlInspector(),
    ELang.JAVA:   JavaInspector(),
    ELang.HTML:   HtmlInspector(),
}


# ─────────────────────────────────────────────
# The translator
# ─────────────────────────────────────────────

@dataclass
class Translation:
    particle: EParticle
    lang: ELang
    errors: List[Finding]
    patterns: List[Finding]
    source: str

    @property
    def error_distance(self) -> int:
        return len(self.errors)

    @property
    def emulatable(self) -> bool:
        return 0 < self.error_distance <= E_EMULATE_CEILING

    def report(self) -> str:
        L = []
        L.append(f"  language   : {ELang(self.lang).name}")
        L.append(f"  confidence : {self.particle.confidence}/256")
        L.append(f"  state      : {EState(self.particle.state).name}")
        L.append(f"  errors     : {len(self.errors)}")
        for e in self.errors:
            L.append(f"      line {e.line}: {e.message}"
                     + (f"  →  {e.fix_hint}" if e.fix_hint else ""))
        L.append(f"  patterns   : {len(self.patterns)}")
        for p in self.patterns:
            L.append(f"      {p.message}")
        if self.emulatable:
            L.append(f"  emulatable : yes (distance {self.error_distance})")
        elif self.error_distance > E_EMULATE_CEILING:
            L.append(f"  emulatable : no — distance {self.error_distance} "
                     f"exceeds ceiling {E_EMULATE_CEILING}, returns to Z")
        return "\n".join(L)


class Translator:
    """Any language in. E-particles out."""

    def translate(self, code: str, ident: str = "unnamed",
                  lang: Optional[ELang] = None) -> Translation:
        lang = lang if lang is not None else detect(code)
        inspector = INSPECTORS.get(lang)

        if inspector is None:
            p = e_z(ident, f"no inspector for {ELang(lang).name}")
            return Translation(p, lang, [], [], code)

        findings = inspector.inspect(code)
        errors   = [f for f in findings if f.kind == "error"]
        patterns = [f for f in findings if f.kind == "pattern"]

        particle = self._score(ident, lang, errors, patterns)
        return Translation(particle, lang, errors, patterns, code)

    def _score(self, ident, lang, errors, patterns) -> EParticle:
        """Confidence is earned by patterns and spent by errors.

        Beyond the Emulate ceiling the particle is not merely low —
        it is Z. Too far from working to borrow a neighbour's behaviour.
        """
        if len(errors) > E_EMULATE_CEILING:
            return e_z(ident,
                       f"{len(errors)} errors exceeds emulate ceiling "
                       f"{E_EMULATE_CEILING}")

        base = 128
        for p in patterns:
            base += p.weight
        for e in errors:
            base -= e.weight

        if base <= E_ZERO:
            return e_z(ident, "confidence spent below zero by errors")
        if base >= E_CERTAIN:
            # Nothing reaches Certain from static inspection alone.
            # Certain is earned at runtime, not guessed at parse time.
            base = E_CERTAIN - 1

        return e_confident(ident, base, lang)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    t = Translator()

    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            with open(path) as fh:
                src = fh.read()
            tr = t.translate(src, ident=path)
            print(f"\n{path}")
            print(tr.report())
            print(f"\n  particle   : {tr.particle.serialize()}")
    else:
        print(__doc__)
        print("usage: python3 translate.py <file> [file...]")
