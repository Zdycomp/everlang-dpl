#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from language_support import ExtendedLanguage, LANGUAGE_NAMES, RULES, inspect

passed = failed = 0

def ok(name, condition):
    global passed, failed
    if condition: passed += 1; print(f"  ✓ {name}")
    else: failed += 1; print(f"  ✗ {name}")

X = ExtendedLanguage

SAMPLES = {
    X.CSHARP: [("unsafe { p = 1; }", "unsafe block requires review")],
    X.CLOJURE: [("(eval form)", "dynamic eval requires review")],
    X.CSS: [("p { color: red !important; }", "important override reduces cascade clarity")],
    X.DART: [("dynamic x = 1;", "dynamic value bypasses static checks")],
    X.DOCKERFILE: [("FROM alpine\nADD app.tar /app", "ADD has implicit extraction/network behavior")],
    X.ELIXIR: [("spawn(fn -> 1 end)", "unbounded process creation requires supervision")],
    X.EMACS_LISP: [("(eval form)", "dynamic evaluation requires review")],
    X.HASKELL: [("x = unsafePerformIO act", "unsafe IO bypasses effect tracking")],
    X.JAVASCRIPT: [
        ("function f(x) { return eval(x); }", "dynamic evaluation is unsafe"),
        ("document.write('<b>' + x)", "document.write can inject unescaped markup"),
        ("el.innerHTML = x;", "innerHTML assignment can inject markup"),
    ],
    X.JULIA: [("eval(expr)", "dynamic evaluation requires review")],
    X.JUPYTER: [("get_ipython().system('ls')", "notebook shell escape requires review")],
    X.KOTLIN: [("val n = s!!.length", "non-null assertion can crash at runtime")],
    X.LUA: [("loadstring(s)()", "dynamic code loading requires review")],
    X.MATLAB: [("eval('x = 1')", "dynamic evaluation requires review")],
    X.OBJECTIVE_C: [("p = malloc(4);", "manual allocation requires ownership review")],
    X.PERL: [("eval $user_code;", "runtime eval requires error handling")],
    X.PHP: [("eval($code);", "dynamic evaluation is unsafe")],
    X.POWERSHELL: [("Invoke-Expression $cmd", "dynamic command execution is unsafe")],
    X.R: [("eval(parse(text = s))", "dynamic evaluation requires review")],
    X.SCALA: [("x.asInstanceOf[Int]", "unchecked cast can fail at runtime")],
    X.SHELL: [("eval $cmd", "shell eval expands untrusted text")],
    X.SWIFT: [("let x = try! f()", "forced try can trap at runtime")],
    X.TEX: [("\\write18{ls}", "shell escape executes external commands")],
    X.TYPESCRIPT: [("let x: any = 1;", "any bypasses static checks")],
    X.VUE: [('<div v-html="x"></div>', "raw HTML binding can inject markup")],
}

CLEAN = "value = 1\n"

print("\nCatalog")
for language, name in LANGUAGE_NAMES.items():
    ok(f"{name} is in the catalog", language in X)
for language in X:
    ok(f"{language.name} has a catalog name", language in LANGUAGE_NAMES)
    ok(f"{language.name} has rules", language in RULES)
    ok(f"{language.name} has samples", language in SAMPLES)

print("\nRules")
for language in X:
    name = LANGUAGE_NAMES[language]
    rule_messages = {message for _, message, _, _ in RULES.get(language, [])}
    sample_messages = {message for _, message in SAMPLES.get(language, [])}
    ok(f"{name} samples cover every rule", rule_messages == sample_messages)
    for sample, message in SAMPLES.get(language, []):
        findings = inspect(sample, language)
        ok(f"{name} reports '{message}'",
           any(f.kind == "error" and f.message == message for f in findings))
        ok(f"{name} findings are errors only", all(f.kind == "error" for f in findings))
    ok(f"{name} clean code is silent", inspect(CLEAN, language) == [])

print("\nBehaviour")
ok("PERL block eval is not flagged",
   inspect("eval { r(); 1 } or die $@;", X.PERL) == [])
ok("PERL string eval is flagged",
   any(f.kind == "error" for f in inspect("eval $user_code;", X.PERL)))

print(f"\n=== Extended languages: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
