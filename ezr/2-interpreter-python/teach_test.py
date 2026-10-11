#!/usr/bin/env python3
"""teach_test.py — Ever / Tapestry, teaching layer verification.

The engine is tested elsewhere. What is tested here is whether somebody
on their first day would be helped or discouraged.
"""

import re

from teach import (
    Teacher, Report, Step, Lesson, LESSONS, BANDS,
    band, percent, find_lesson,
)
from checker import ELang
from ever import E_CERTAIN, E_EXECUTE_FLOOR

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


t = Teacher()
print("\n=== Ever \u2014 the teaching layer ===\n")

print("Confidence reads as words, not fractions")
ok("zero has a label",        band(0)[0] != "")
ok("low is encouraging",      "Everyone starts here" in band(0)[1])
ok("the floor reads as runnable", band(128)[0] == "This will run")
ok("high is distinct",        band(230)[0] != band(128)[0])
ok("256 is verified",         band(256)[0] == "Verified")
ok("percent converts",        percent(128) == 50)
ok("percent tops out",        percent(256) == 100)

print("\nNo message is a dead end")
for lesson in LESSONS:
    if not lesson.fix:
        ok(f"{lesson.match} has a fix", False)
ok("every lesson says what to do",  all(l.fix for l in LESSONS))
ok("every lesson says why",         all(l.why for l in LESSONS))
ok("every lesson has a plain title", all(l.title for l in LESSONS))
ok("titles avoid jargon",
   not any(re.search(r'\bnull pointer\b|\bsegfault\b|\bstack trace\b',
                     l.title, re.I) for l in LESSONS))
ok("safety lessons are marked",
   sum(1 for l in LESSONS if l.tone == "safety") >= 5)
ok("most lessons show the change",
   sum(1 for l in LESSONS if l.example_after) >= len(LESSONS) * 0.7)

print("\nLessons match real checker output")
cases = [
    ("int add(int x, int y) { return x + y }", ELang.C, "semicolon"),
    ("DELETE FROM users", ELang.SQL, "delete everything"),
    ("def collect(items=[]):\n    return items", ELang.PYTHON, "shared"),
    ('<div><img src="a.jpg"></div>', ELang.HTML, "no description"),
    ("public class A { void f(){ String s = null; s.length(); } }",
     ELang.JAVA, "might not exist"),
    ('def greet\n  puts "hi"', ELang.RUBY, "never closed"),
]
for code, lang, expect in cases:
    r = t.review(code, lang)
    got = r.next_step.title.lower() if r.next_step else ""
    ok(f"{ELang(lang).name} \u2192 {expect!r}", expect in got)

print("\nOne thing at a time")
messy = """
def f(items=[], raw=None):
    for line in raw.split(","):
        items.append(eval(line))
    try:
        return items
    except:
        pass
"""
r = t.review(messy, ELang.PYTHON)
ok("several problems found",      r.total_issues >= 3)
ok("only one is presented",       r.next_step is not None)
rendered = t.render(r)
ok("the count is mentioned, not the list", "more after this" in rendered)
ok("exactly one title shown",
   sum(1 for l in rendered.split("\n") if l.strip() == r.next_step.title) == 1)

print("\nDanger is ranked above untidiness")
dangerous = 'SELECT * FROM a;\nDELETE FROM sessions;'
r2 = t.review(dangerous, ELang.SQL)
ok("the destructive one comes first", r2.next_step.is_safety)
ok("it is flagged as such",
   "matters more" in t.render(r2))

print("\nNothing is ever a wall")
r3 = t.review("SELECT * FROM a JOIN b;\nDELETE FROM c;\nDROP TABLE d;\n"
              "UPDATE e SET x=1;", ELang.SQL)
ok("the checker gave up",         r3.unknown)
ok("but confidence is never zero", r3.confidence > 0)
ok("the wording takes the blame",  "on me" in r3.note)
ok("a next step is still offered", r3.next_step is not None)
out3 = t.render(r3)
ok("no bare refusal shown",       "withheld" not in out3.lower())
ok("no raw defect words shown",
   not any(w in out3.lower() for w in ("misbound", "unbounded", "overbound")))

print("\nWhat is already working gets said")
good = ("public class C {\n  private final int v;\n"
        "  public void go(){ try { work(); } catch (Exception e) { log(e); } }\n}")
r4 = t.review(good, ELang.JAVA)
ok("praise is collected",         len(r4.good) > 0)
ok("praise is in plain words",
   all(not any(c in g for c in "_<>") for g in r4.good))
ok("praise appears in the output", "Already" in t.render(r4)
                                   or "working" in t.render(r4))

print("\nClean code is recognised, not just tolerated")
clean = "def add(x: int, y: int) -> int:\n    return x + y"
r5 = t.review(clean, ELang.PYTHON)
ok("nothing to fix",              r5.done)
ok("it clears the floor",         r5.confidence >= E_EXECUTE_FLOOR)
ok("it is told it will run",      r5.label in ("This will run", "Solid",
                                               "Really solid"))
ok("the output says so",          "ready" in t.render(r5).lower())

print("\nThe render never leaks internals")
for code, lang in [(c, l) for c, l, _ in cases]:
    out = t.render(t.review(code, lang))
    if "/256" in out or "particle" in out.lower() or "Z(" in out:
        ok("no internals leaked", False)
        break
else:
    ok("no internals leaked in any sample", True)

ok("no fraction shown anywhere",
   all("/256" not in t.render(t.review(c, l)) for c, l, _ in cases))

print("\nEvery sample produces something actionable")
for code, lang, _ in cases:
    r = t.review(code, lang)
    s = r.next_step
    if not s or not (s.lesson or s.finding.fix_hint):
        ok(f"{ELang(lang).name} actionable", False)
        break
else:
    ok("every sample gives a concrete next step", True)

print(f"\n=== Teaching layer: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
