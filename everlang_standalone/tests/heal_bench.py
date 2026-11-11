#!/usr/bin/env python3
"""Benchmark EArchive.heal against real code, judged by each language's own parser.

Part A  heals untouched real files. A valid file must come back unchanged;
        one that is refused, broken or changed in meaning is a false positive.
Part B  injects one common error into a real file, heals it, and asks the
        parser whether the result is valid and equal to the original.

Corpora: the Python stdlib, GOROOT, the global npm modules, commons-lang3
sources (Maven Central), a few crates (crates.io), this repo's Java, Kotlin
and Ever files. Downloads go to --cache. A language whose toolchain or corpus
is missing is skipped. Kotlin has no parser oracle here, so its results say
only whether heal refused or edited.

    python3 everlang_standalone/tests/heal_bench.py [language ...]
        [--files N] [--mutants N] [--seed N] [--cache DIR] [--json FILE]

Not part of run_all.py: it needs the network and takes minutes. Exits 1 when
heal breaks, refuses or changes the meaning of a valid file, or leaves an
edited file still broken.
"""
import argparse
import ast
import glob
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tokenize
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from everlang.core.archive import EArchive          # noqa: E402
from everlang.core import heal as heal_engine       # noqa: E402

EXT = {"ever": ".ever", "python": ".py", "javascript": ".js", "go": ".go",
       "rust": ".rs", "java": ".java", "kotlin": ".kt"}
TOOL = {"javascript": "node", "go": "gofmt", "rust": "rustc", "java": "java"}
CRATES = ("itoa/1.0.11", "semver/1.0.23", "anyhow/1.0.86", "log/0.4.22",
          "cfg-if/1.0.0", "bitflags/2.6.0")
JAVA_SOURCES = ("https://repo1.maven.org/maven2/org/apache/commons/commons-lang3/"
                "3.14.0/commons-lang3-3.14.0-sources.jar")
POOL = ThreadPoolExecutor(8)
FALSE_POSITIVES = ("BROKE_valid_file", "refused_valid_file", "edited_CHANGED_program")


# ---------------------------------------------------------------- oracles
def _ok(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, env=env).returncode == 0


def oracle(lang, texts, tmp):
    """Per text: True if the language's parser accepts it, None if no oracle."""
    if lang == "python":
        out = []
        for t in texts:
            try:
                compile(t, "<bench>", "exec", dont_inherit=True)
                out.append(True)
            except (SyntaxError, ValueError, RecursionError):
                out.append(False)
        return out
    if lang == "ever":
        import syntax                      # ezr's strict parser, on sys.path via heal
        return [syntax.parse(t)[1] is None for t in texts]
    if lang == "kotlin":
        return [None] * len(texts)
    if not texts:
        return []
    d = tempfile.mkdtemp(dir=tmp)
    paths = []
    for i, t in enumerate(texts):
        sub = os.path.join(d, str(i))
        os.mkdir(sub)
        name = "M" + EXT[lang]
        if lang == "java":                 # a public type must match its file name
            m = re.search(r"^public\s+(?:\w+\s+)*?(?:class|interface|enum|record|@interface)"
                          r"\s+(\w+)", t, re.M)
            name = (m.group(1) if m else "M") + ".java"
        p = os.path.join(sub, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        paths.append(p)
    if lang == "java":
        lst = os.path.join(d, "files.txt")
        with open(lst, "w") as f:
            f.write("\n".join(paths) + "\n")
        r = subprocess.run(["java", os.path.join(HERE, "ParseCheck.java"), lst],
                           capture_output=True, text=True)
        res = r.stdout.split()
        if len(res) != len(paths):
            raise RuntimeError("ParseCheck failed: " + r.stderr[-400:])
        return [x == "OK" for x in res]
    if lang == "javascript":
        return list(POOL.map(lambda p: _ok(["node", "--check", p]), paths))
    if lang == "go":
        return list(POOL.map(lambda p: _ok(["gofmt", "-e", "-l", p]), paths))
    env = dict(os.environ, RUSTC_BOOTSTRAP="1")     # -Zunpretty parses without resolving
    return list(POOL.map(lambda p: _ok(
        ["rustc", "--edition", "2021", "-Zunpretty=normal", p], env), paths))


# ---------------------------------------------------------------- corpora
def _fetch(url, dest):
    if not os.path.exists(dest):
        with urllib.request.urlopen(url, timeout=60) as r, open(dest + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(dest + ".part", dest)
    return dest


def _sources(lang, cache):
    if lang == "python":
        std = sysconfig.get_paths()["stdlib"]
        return [p for p in glob.glob(std + "/**/*.py", recursive=True)
                if "/test" not in p and "site-packages" not in p and "lib2to3" not in p]
    if lang == "go":
        root = subprocess.run(["go", "env", "GOROOT"], capture_output=True, text=True).stdout.strip()
        return [p for p in glob.glob(root + "/src/**/*.go", recursive=True)
                if "testdata" not in p and not p.endswith("_test.go")]
    if lang == "javascript":
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.realpath(shutil.which("node")))), "lib", "node_modules")
        return [p for p in glob.glob(root + "/**/*.js", recursive=True) if ".min." not in p]
    if lang == "rust":
        d = os.path.join(cache, "crates")
        os.makedirs(d, exist_ok=True)
        for c in CRATES:
            name, ver = c.split("/")
            if not os.path.isdir(os.path.join(d, f"{name}-{ver}")):
                tgz = _fetch(f"https://static.crates.io/crates/{name}/{name}-{ver}.crate",
                             os.path.join(d, f"{name}-{ver}.crate"))
                with tarfile.open(tgz) as t:
                    t.extractall(d, filter="data")
        return glob.glob(d + "/**/*.rs", recursive=True)
    if lang == "java":
        d = os.path.join(cache, "java")
        if not os.path.isdir(d):
            jar = _fetch(JAVA_SOURCES, os.path.join(cache, "commons-lang3-sources.jar"))
            with zipfile.ZipFile(jar) as z:
                z.extractall(d, [n for n in z.namelist() if n.endswith(".java")])
        return glob.glob(d + "/**/*.java", recursive=True) + \
            glob.glob(REPO + "/5-runtime-java/**/*.java", recursive=True)
    if lang == "kotlin":
        return glob.glob(REPO + "/6-android-kotlin/**/*.kt", recursive=True)
    return glob.glob(REPO + "/ezr/**/*.ever", recursive=True)


def corpus(lang, rng, n_files, cache, tmp):
    files = sorted(_sources(lang, cache))
    rng.shuffle(files)
    lo = 3 if lang in ("ever", "kotlin") else 25
    out = []
    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                t = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        if "\r" in t or lang == "python" and "\t" in t:
            continue
        if lo <= t.count("\n") <= 400:
            out.append((p, t))
        if len(out) >= n_files * 2:
            break
    ok = oracle(lang, [t for _, t in out], tmp)
    return [pt for pt, k in zip(out, ok) if k is not False][:n_files]


# ---------------------------------------------------------------- mutations
KEYWORDS = {"javascript": ["function", "return", "const"], "java": ["public", "return", "class"],
            "go": ["func", "return", "package"], "rust": ["let", "return", "struct"],
            "kotlin": ["fun", "val", "return"],
            "python": ["def", "return", "import", "else", "while"],
            "ever": ["let", "then", "show", "else"]}


def _swap(w):
    i = len(w) - 2 if len(w) > 3 else 1
    return w[:i] + w[i + 1] + w[i] + w[i + 2:]


def _py_string_lines(text):
    """(lines holding any string or comment, lines holding a one-line "..." string)."""
    any_, single = set(), set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        name = tokenize.tok_name[tok.type]
        if name in ("STRING", "COMMENT") or name.startswith("FSTRING"):
            any_.update(range(tok.start[0] - 1, tok.end[0]))
        if name == "STRING" and tok.start[0] == tok.end[0] and \
                tok.string.startswith('"') and not tok.string.startswith('"""'):
            single.add(tok.start[0] - 1)
    return any_, single


def code_lines(lang, text):
    """(lines, indices of lines that hold code only: no string, no comment)."""
    lines = text.split("\n")
    if lang == "python":
        try:
            bad, _ = _py_string_lines(text)
        except (tokenize.TokenError, SyntaxError):
            return lines, []
        return lines, [i for i, l in enumerate(lines) if i not in bad and l.strip()]
    ok, in_block = [], False
    for i, l in enumerate(lines):
        s = l.strip()
        if in_block:
            in_block = "*/" not in l
            continue
        if "/*" in l and lang != "ever":
            in_block = "*/" not in l
            continue
        if not s or any(c in l for c in "\"'`") or "//" in l or s.startswith("*") \
                or lang == "ever" and "#" in l or lang == "rust" and "#[" in l:
            continue
        ok.append(i)
    return lines, ok


def _sub_line(lines, i, new):
    out = list(lines)
    out[i] = new
    return "\n".join(out)


def mutators(lang):
    """name -> f(text, rng) returning the text with one error injected, or None."""
    def by_regex(pattern, repl, pre=None):
        rx = re.compile(pattern)

        def f(text, rng):
            lines, ok = code_lines(lang, text)
            c = [i for i in ok if rx.search(lines[i]) and (pre is None or pre(lines[i]))]
            if not c:
                return None
            i = rng.choice(c)
            return _sub_line(lines, i, rx.sub(repl, lines[i], count=1))
        return f

    def unterminated(text, rng):           # delete the closing quote of a one-string line
        lines = text.split("\n")
        c = [i for i, l in enumerate(lines)
             if l.count('"') == 2 and not any(x in l for x in "'`\\#") and "//" not in l
             and "/*" not in l and not l.strip().startswith("*")]
        if lang == "python":
            try:
                _, single = _py_string_lines(text)
            except (tokenize.TokenError, SyntaxError):
                return None
            c = [i for i in c if i in single]
        if not c:
            return None
        i = rng.choice(c)
        k = lines[i].rindex('"')
        return _sub_line(lines, i, lines[i][:k] + lines[i][k + 1:])

    def dedent(text, rng):
        lines, ok = code_lines(lang, text)
        c = [i for i in ok if i > 0 and lines[i - 1].rstrip().endswith(":")
             and lines[i].startswith("    ")]
        if not c:
            return None
        i = rng.choice(c)
        return _sub_line(lines, i, lines[i].lstrip())

    M = {
        "drop_closing_bracket": by_regex(r"[)\]}](?=[^)\]}]*$)", ""),
        "extra_closing_bracket": by_regex(r"\)(?=[^)]*$)", "))"),
        "wrong_bracket_kind": by_regex(r"\)(?=[^)]*$)", "]"),
        "unterminated_string": unterminated,
        "keyword_typo": by_regex(r"^(\s*)(%s)\b" % "|".join(KEYWORDS[lang]),
                                 lambda m: m.group(1) + _swap(m.group(2))),
        "drop_comma": by_regex(r"(\w), (\w)", r"\1 \2", pre=lambda l: "(" in l or "[" in l),
    }
    if lang == "python":
        M["drop_colon"] = by_regex(r":\s*$", "", pre=lambda l: re.match(
            r"\s*(if|elif|else|for|while|def|class|try|except|finally|with)\b", l))
        M["eq_for_compare"] = by_regex(r" == ", " = ", pre=lambda l: re.match(
            r"\s*(if|elif|while)\b.*:\s*$", l))
        M["missing_indent"] = dedent
    elif lang == "ever":
        M["eq_for_compare"] = by_regex(r" == ", " = ")
        M["stray_semicolon"] = by_regex(r"(\S)\s*$", r"\1;")
        M["colon_for_equals"] = by_regex(r"^(\s*(?:let|ever)\s+\w+)\s*=", r"\1:")
        M["equals_for_colon"] = by_regex(r"(\{\s*\w+): ", r"\1 = ")
        M["trailing_comma"] = by_regex(r"(\w)\]", r"\1,]")
        M["keyword_case"] = by_regex(r"^(\s*)(let|ever|show|if)\b",
                                     lambda m: m.group(1) + m.group(2).capitalize())
        M["missing_comma_in_list"] = by_regex(r"(\[[^\]]*?\w), (\w)", r"\1 \2")
    else:
        if lang in ("javascript", "java", "rust"):
            M["drop_semicolon"] = by_regex(r";\s*$", "", pre=lambda l: not re.match(
                r"\s*(for|use|import|package|pub use|mod|pub mod)\b", l))
        M["eq_for_compare"] = by_regex(r" ===? ", " = ", pre=lambda l: re.match(
            r"\s*(\}\s*else\s+)?(if|while)\b", l))
        M["drop_open_brace"] = by_regex(r"\s*\{\s*$", "",
                                        pre=lambda l: re.search(r"\)\s*\{\s*$", l))
    return M


# ---------------------------------------------------------------- judging
def same_program(lang, original, h):
    if lang == "ever":
        import syntax
        return repr(h.program) == repr(syntax.parse(original)[0])
    if h.code == original:
        return True
    if lang == "python":
        try:
            return ast.dump(ast.parse(h.code)) == ast.dump(ast.parse(original))
        except SyntaxError:
            return False
    return re.sub(r"\s+", "", h.code) == re.sub(r"\s+", "", original)


def judge_valid(lang, text, h, parses):
    if h.refused:
        return "refused_valid_file"
    if not h.repairs:
        return "untouched"
    if parses is False:
        return "BROKE_valid_file"
    if same_program(lang, text, h):
        return "edited_same_program"
    if parses is None:
        return "edited_unverified"
    # Only Python can prove a meaning change (AST). Elsewhere the edit still
    # parses; for JavaScript that is a ';' ASI would have supplied anyway.
    return "edited_CHANGED_program" if lang == "python" else "edited_still_parses"


def judge_mutant(lang, text, h, mutant_valid, parses):
    if mutant_valid is True:           # the injected change was not an error here
        return "not_an_error/" + ("refused" if h.refused else
                                  "edited" if h.repairs else "left_alone")
    if h.refused:
        return "refused"
    if lang == "ever":
        return "REPAIRED_exact" if same_program(lang, text, h) else "repaired_different_program"
    if not h.repairs:
        return "missed"
    if parses is None:
        return "edited_unverified"
    if not parses:
        return "edited_still_broken"
    return "REPAIRED_exact" if same_program(lang, text, h) else "repaired_different_program"


def _first_diff(a, b):
    return next((j for j, (x, y) in enumerate(zip(a.split("\n"), b.split("\n"))) if x != y), 0)


def bench(lang, args, archive, tmp):
    rng = random.Random(args.seed)
    files = corpus(lang, rng, args.files, args.cache, tmp)
    rep = {"files": len(files), "valid": Counter(), "valid_examples": [],
           "mutants": defaultdict(Counter), "mutant_examples": defaultdict(list)}

    healed = [archive.heal(t, lang, "valid:" + p) for p, t in files]
    edited = [i for i, h in enumerate(healed) if h.repairs and not h.refused and h.code is not None]
    parses = dict(zip(edited, oracle(lang, [healed[i].code for i in edited], tmp)))
    base = []
    for i, ((p, t), h) in enumerate(zip(files, healed)):
        k = judge_valid(lang, t, h, parses.get(i, True if lang == "ever" else None))
        rep["valid"][k] += 1
        if k == "untouched":
            base.append((p, t))
        elif len(rep["valid_examples"]) < 40:
            ex = {"file": os.path.relpath(p, REPO), "kind": k, "fixes": len(h.repairs)}
            if h.repairs:
                r = h.repairs[0]
                ex.update(line=r["line_no"], fix=r["name"], before=r["line_text"].strip()[:110])
            if h.refusals:
                ex["refusal"] = h.refusals[0][:110]
            rep["valid_examples"].append(ex)

    for name, mutate in mutators(lang).items() if base else ():
        cases, tries = [], 0
        while len(cases) < args.mutants and tries < args.mutants * 12:
            tries += 1
            p, t = rng.choice(base)
            m = mutate(t, rng)
            if m is not None and m != t:
                cases.append((p, t, m))
        if not cases:
            continue
        mutant_valid = oracle(lang, [m for _, _, m in cases], tmp)
        hs = [archive.heal(m, lang, f"{name}:{i}:{p}") for i, (p, _, m) in enumerate(cases)]
        need = [i for i, h in enumerate(hs) if not h.refused and h.code is not None]
        parses = dict(zip(need, oracle(lang, [hs[i].code for i in need], tmp)))
        for i, ((p, t, m), h) in enumerate(zip(cases, hs)):
            k = judge_mutant(lang, t, h, mutant_valid[i], parses.get(i))
            rep["mutants"][name][k] += 1
            ex = rep["mutant_examples"][name + "|" + k]
            if len(ex) < 2:
                di = _first_diff(t, m)
                ex.append({"original": t.split("\n")[di].strip()[:100],
                           "mutant": m.split("\n")[di].strip()[:100],
                           "healed": h.code.split("\n")[di].strip()[:100] if h.code else None,
                           "confidence": h.confidence,
                           "refusal": h.refusals[0][:120] if h.refusals else None})
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("languages", nargs="*", choices=[[], *EXT], default=[])
    ap.add_argument("--files", type=int, default=150, help="real files per language")
    ap.add_argument("--mutants", type=int, default=80, help="injected errors per class")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "heal_bench_cache"))
    ap.add_argument("--json", help="write full results, with examples, to this file")
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    if not heal_engine._load():
        sys.exit("heal_bench: ezr/ repair engines not found")

    archive, report, failed = EArchive(), {}, False
    with tempfile.TemporaryDirectory(prefix="heal_bench_") as tmp:
        for lang in args.languages or list(EXT):
            if lang in TOOL and not shutil.which(TOOL[lang]):
                print(f"\n=== {lang}: skipped, {TOOL[lang]} not installed")
                continue
            try:
                rep = report[lang] = bench(lang, args, archive, tmp)
            except OSError as e:           # corpus download failed
                print(f"\n=== {lang}: skipped, {e}")
                continue
            print(f"\n=== {lang}: {rep['files']} real files", flush=True)
            print("  valid code:", dict(rep["valid"]))
            for name, c in rep["mutants"].items():
                print(f"  {name:24s}", dict(c))
            if any(rep["valid"][k] for k in FALSE_POSITIVES) or \
                    any(c["edited_still_broken"] for c in rep["mutants"].values()):
                failed = True
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    print("\nheal_bench:", "FAIL: heal damaged valid code or left an edit broken"
          if failed else "OK")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
