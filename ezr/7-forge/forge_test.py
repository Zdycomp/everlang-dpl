#!/usr/bin/env python3
"""forge_test.py — EZR / Tapestry, layer 7 verification.

Checks the forge itself, and then checks the core the forge settled on:
every lexer paired with every parser, over the whole conformance
corpus, under every law. A regression in any one of the sixteen front
ends fails this file.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contract import (Bin, Call, Def, If, Num, Prog, Var, skeleton,   # noqa
                      unparse)
from corpus import ACCEPT, GOLDEN, PROBES, REFUSE_LEX, REFUSE_PARSE, Fuzzer
from forge import (DOCTRINE, FINDINGS, REPAIRS, Forge, all_parsers,
                   build_pairs)
from grammar_doc import render, token_table
from laws import (law_agreement, law_position, law_roundtrip,
                  law_token_stream, law_total, law_unambiguous)
from lexers import LEXERS, keywords
import repair as repair_mod
import selfgen
from parsers import PARSERS
from spec import SPEC

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


print("\n=== EZR — layer 7, the forge ===\n")

forge = Forge(budget=0, verbose=False)
pairs = build_pairs()

print("1. THE MATRIX")
ok("four lexers",                 len(LEXERS) == 4)
ok("four hand-written parsers",   len(PARSERS) == 4)
ok("plus one the grammar emits",  len(all_parsers()) == 5)
ok("twenty front ends",           len(pairs) == 20)
ok("every pair is lexer x parser",
   all(" x " in p.name for p in pairs))

print("\n2. EVERY QUESTION IS SETTLED")
ok("nothing left open",           not SPEC.open_questions)
ok("seven questions settled",     len(SPEC.settled_questions) == 7)
ok("a bare '<' is CMP",           SPEC.get("cmp_kind", None) == "CMP")
ok("an unclosed string is unbounded",
   SPEC.get("unterminated_string_defect", None) == "unbounded")
ok("eight reserved words, not nineteen",
   len(SPEC.get("reserved_words", [])) == 8)
ok("several definitions per text", SPEC.get("multi_definition", None) is True)
ok("no chained comparison",       SPEC.get("chained_comparison", None) is False)
ok("no trailing comma",           SPEC.get("trailing_comma", None) is False)
ok("no trailing expression",      SPEC.get("trailing_expression", None) is False)
ok("every ruling carries its reason",
   all(q.rationale for q in SPEC.settled_questions))

print("\n3. THE SCANNERS AGREE")
for text, kind in token_table():
    if text in ("<", ">"):
        ok(f"'{text}' is CMP everywhere", kind == "CMP")
ok("no disputed token kind",
   all(k != "DISPUTED" for _t, k in token_table()))
ok("'to' is a name again",
   all(f("to").toks[0].kind == "NAME" for f in LEXERS.values()))
ok("'def' is still a keyword",
   all(f("def").toks[0].kind == "KW" for f in LEXERS.values()))
ok("the reserved set is the words the grammar reaches",
   keywords() == {"def", "else", "false", "if", "in", "let", "then",
                  "true"})

print("\n4. THE GOLDEN CORPUS, ON ALL SIXTEEN")
bad_outcome = bad_tree = 0
for case in GOLDEN:
    for p in pairs:
        r = forge.run_one(p, case.src)
        if case.outcome and forge.outcome_of(r) != case.outcome:
            bad_outcome += 1
        if case.sexp and r.parse_ok and r.verdict != case.sexp:
            bad_tree += 1
ok(f"{len(GOLDEN)} cases x 16 front ends reach the required outcome",
   bad_outcome == 0)
ok("and build the required tree",  bad_tree == 0)

print("\n5. THE LAWS")
sample = [c.src for c in GOLDEN] + [c.src for c in PROBES] + \
         [c.src for c in Fuzzer(seed=20260906).batch(600)]
counts = {"total": 0, "agreement": 0, "unambiguous": 0,
          "position": 0, "token-stream": 0, "roundtrip": 0}
for src in sample:
    runs = {p.name: forge.run_one(p, src) for p in pairs}
    for law, key in ((law_total, "total"),
                     (law_agreement, "agreement"),
                     (law_unambiguous, "unambiguous"),
                     (law_position, "position"),
                     (law_token_stream, "token-stream")):
        counts[key] += len(law(src, runs))
    counts["roundtrip"] += len(law_roundtrip(src, runs, forge.canon_of))
ok(f"total — nothing raised over {len(sample)} texts", counts["total"] == 0)
ok("agreement — all sixteen reach one verdict", counts["agreement"] == 0)
ok("unambiguous — no text has two trees", counts["unambiguous"] == 0)
ok("position — every refusal lands inside the text", counts["position"] == 0)
ok("token-stream — one EOF, positions forward",
   counts["token-stream"] == 0)
ok("roundtrip — printing and reading back is the identity",
   counts["roundtrip"] == 0)

print("\n6. WHAT THE FORGE SETTLED, RE-CHECKED DIRECTLY")
def verdicts(src):
    return {forge.run_one(p, src).verdict for p in pairs}

ok("the SEMANTICS.md worked example parses",
   verdicts("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)") ==
   {"(prog (def fact (n) (if (<= n 1) 1 (* n (call fact (- n 1))))))"})
ok("two definitions in one text",
   verdicts("def f(n) = n\ndef g(n) = n + 1") ==
   {"(prog (def f (n) n) (def g (n) (+ n 1)))"})
ok("a definition followed by an expression is refused",
   verdicts("def d(n) = n * 2\nd(21)") == {"FAIL[parse/unbounded]"})
ok("the ambiguous text now has one tree",
   verdicts("def f(n) = 1 - 1") == {"(prog (def f (n) (- 1 1)))"})
ok("a conditional is not an operand",
   verdicts("1 + if a then 2 else 3") == {"FAIL[parse/unbounded]"})
ok("parentheses make it one",
   verdicts("(if a then 1 else 2) != 3") ==
   {"(prog (!= (if a 1 2) 3))"})
ok("the else branch is a whole expression",
   verdicts("if a then 1 else 2 != 3") == {"(prog (if a 1 (!= 2 3)))"})
ok("chained comparison is refused",
   verdicts("1 < 2 < 3") == {"FAIL[parse/unbounded]"})
ok("a trailing comma is refused",
   verdicts("f(1,)") == {"FAIL[parse/unbounded]"})
ok("an unclosed string is unbounded everywhere",
   verdicts('"oops') == {"FAIL[lex/unbounded]"})
ok("an illegal character is misbound everywhere",
   verdicts("a $ b") == {"FAIL[lex/misbound]"})
ok("'to' is usable as a parameter",
   verdicts("def area(to) = to * 2") ==
   {"(prog (def area (to) (* to 2)))"})

print("\n7. ASSOCIATIVITY AND PRECEDENCE")
ok("subtraction is left-associative",
   verdicts("1 - 2 - 3") == {"(prog (- (- 1 2) 3))"})
ok("division is left-associative",
   verdicts("8 / 4 / 2") == {"(prog (/ (/ 8 4) 2))"})
ok("multiplication binds tighter than addition",
   verdicts("1 + 2 * 3") == {"(prog (+ 1 (* 2 3)))"})
ok("comparison binds loosest",
   verdicts("1 + 2 < 3 + 4") == {"(prog (< (+ 1 2) (+ 3 4)))"})
ok("prefix minus binds tighter than multiplication",
   verdicts("-2 * 3") == {"(prog (* (- 0 2) 3))"})
ok("prefix minus nests",
   verdicts("- -2") == {"(prog (- 0 (- 0 2)))"})

print("\n8. THE EMITTED GRAMMAR")
ebnf = render()
ok("carries every rule name",
   all(k in ebnf for k in ("program", "definitions", "definition",
                           "expression", "conditional", "comparison",
                           "additive", "multiplicative", "unary",
                           "atom", "arguments")))
ok("states left recursion, so associativity is written down",
   "additive , \"+\" , multiplicative" in ebnf)
ok("carries the token kinds", "CMP" in ebnf and "OP" in ebnf)
ok("carries every settled question",
   all(q.key in ebnf for q in SPEC.settled_questions))
ok("names the section of SEMANTICS.md it closes", "section 7" in ebnf)

print("\n9. ARBITRATION")
ok("four rulings rest on a published document", len(DOCTRINE) == 4)
ok("every doctrine ruling cites its source",
   all(d.source and d.quote for d in DOCTRINE.values()))
ok("one ruling rests on a law the forge checks",
   len(FINDINGS) == 1 and "trailing_expression" in FINDINGS)
ok("the coverage gap is recorded against the runtime",
   "Lambda.globals" in
   SPEC.questions["multi_definition"].rationale)
ok("consensus needed pi=3 and two thirds",
   "pi=3" in SPEC.questions["trailing_comma"].rationale)

print("\n10. SELF-GENERATION")
gen_src = open(selfgen.OUT_PATH).read() if os.path.exists(selfgen.OUT_PATH) \
    else ""
ok("a parser was emitted to disk",  len(gen_src) > 0)
ok("it is generated, and says so",  "GENERATED. Do not edit" in gen_src)
ok("left recursion became a loop",
   "_rec_additive_0" in gen_src and "while True:" in gen_src)
ok("it is registered as a witness",  "P5-generated" in all_parsers())
gp = all_parsers()["P5-generated"]
def gen_verdict(s):
    return gp(LEXERS["L2-handrolled"](s).toks).canon()
ok("it agrees on the worked example",
   gen_verdict("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)") ==
   "(prog (def fact (n) (if (<= n 1) 1 (* n (call fact (- n 1))))))")
ok("it agrees on left associativity",
   gen_verdict("1 - 2 - 3") == "(prog (- (- 1 2) 3))")
ok("it agrees on precedence",
   gen_verdict("1 + 2 * 3") == "(prog (+ 1 (* 2 3)))")
ok("it refuses what the others refuse",
   gen_verdict("1 < 2 < 3").startswith("FAIL"))
ok("regenerating is deterministic",
   open(selfgen.generate()).read() == gen_src)

print("\n11. SELF-REPAIR")
def _boom(_s):
    raise KeyError("injected")
_shielded = repair_mod.shield(_boom, "lex", "misbound")
ok("a raise becomes a refusal",
   _shielded("x").fail.defect == "misbound")
ok("the normal path is untouched",
   repair_mod.shield(lambda s: "fine", "lex", "misbound")("x") == "fine")
ok("the original is kept, not replaced",
   _shielded._unshielded is _boom)
ok("shields are recognisable",     repair_mod.is_shielded(_shielded))
ok("consensus needs pi = 3",       repair_mod.PI == 3)

_probe = Forge(budget=0, verbose=False)
_probe.lexers["L4-trie"] = _boom
_probe.pairs = build_pairs(_probe.lexers, _probe.parsers)
_sr = repair_mod.SelfRepair(_probe.lexers, _probe.parsers,
                            _probe.verdict_table, REPAIRS, verbose=False)
_found = _sr.scan(["1 =$= 2"])
ok("it localises the broken component",
   len(_found) == 1 and _found[0].component == "L4-trie")
ok("and takes its target from the survivors",
   _found[0].target == "FAIL[lex/misbound]" and len(_found[0].witnesses) >= 3)
ok("it withholds when there is no failure to copy",
   _sr.synthesize(repair_mod.Defect("L4-trie", "lex", "1 + 1", "raises",
                                    "x", target="(prog (+ 1 1))")) == [])
ok("and when the witnesses do not agree",
   _sr.synthesize(repair_mod.Defect("L4-trie", "lex", "x", "raises",
                                    "x", target=None)) == [])
ok("the repair ledger is on disk",
   REPAIRS.path.endswith("repairs.json"))

print("\n12. CONTRACT")
tree = Prog([Def("f", ["n"], If(Bin("<", Var("n"), Num(1)), Num(1),
                                Bin("*", Var("n"),
                                    Call("f", [Bin("-", Var("n"),
                                                   Num(1))]))))])
ok("a tree prints", unparse(tree).startswith("def f(n) ="))
ok("and reads back the same",
   verdicts(unparse(tree)) == {tree.sexp()})
ok("skeletons erase constants",
   skeleton(Num(1)) == skeleton(Num(99)))
ok("skeletons erase which comparison",
   skeleton(Bin("<", Var("n"), Num(1))) ==
   skeleton(Bin(">=", Var("x"), Num(4))))
ok("skeletons keep which arithmetic",
   skeleton(Bin("+", Var("n"), Num(1))) !=
   skeleton(Bin("*", Var("n"), Num(1))))

print(f"\n=== Forge: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
