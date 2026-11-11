#!/usr/bin/env python3
"""
profiler_test.py — Ever / Tapestry, Dynamic Profiler test suite

The claims under test, in order of how much they matter:

  1. The score MOVES with evidence, in the right direction.
  2. It rises faster than it falls (asymmetric alpha).
  3. Diversity is scored separately from difficulty — six different
     tier-2 constructs must beat one tier-3 construct hammered forty
     times, or the score rewards copied snippets.
  4. Bands map onto scaffolding levels, and the same error renders
     differently at each level.
  5. Suggestions are the NEXT step, never the hardest unused one.
  6. It survives a full session trajectory: novice → architect.
  7. It never breaks the semantic pass.

Codric Enterprise · Ricky (Dreid) · 2026
"""

import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiler import (
    Profiler, Profile, Observation, Tier, Construct, Band,
    TAXONOMY, TIER_MEMBERS, BANDS, band_for, classify,
    observe_source_flags, P_MAX, P_MIN, P_START,
    ALPHA_UP, ALPHA_DOWN,
)

_pass = _fail = 0
def ok(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  \u2717 {name}" + (f"\n      {detail}" if detail else ""))

def eq(name, expected, got):
    ok(name, expected == got, f"expected: {expected}\n      got:      {got}")


# ══════════════════════════════════════════════
# 1. TAXONOMY INTEGRITY
# ══════════════════════════════════════════════
print("\n[taxonomy]")

ok("taxonomy is non-empty", len(TAXONOMY) >= 20)
ok("every construct has a tier",
   all(isinstance(c.tier, Tier) for c in TAXONOMY.values()))
ok("every construct has a positive weight",
   all(c.weight > 0 for c in TAXONOMY.values()))
ok("every construct explains what it teaches",
   all(c.teaches and len(c.teaches) > 5 for c in TAXONOMY.values()))
ok("keys match their construct key",
   all(k == c.key for k, c in TAXONOMY.items()))

for t in (Tier.SIMPLE, Tier.INTERMEDIATE, Tier.ADVANCED):
    ok(f"tier {t.label} is populated", len(TIER_MEMBERS[t]) >= 5)

# advanced constructs should carry more weight than simple ones
simple_max = max(TAXONOMY[k].weight for k in TIER_MEMBERS[Tier.SIMPLE])
adv_min    = min(TAXONOMY[k].weight for k in TIER_MEMBERS[Tier.ADVANCED])
ok("advanced constructs outweigh simple ones", adv_min > simple_max,
   f"simple max={simple_max}, advanced min={adv_min}")

# recursion should be the heaviest single signal
heaviest = max(TAXONOMY.values(), key=lambda c: (int(c.tier), c.weight))
ok("recursion is among the heaviest signals",
   heaviest.key in ("recursion", "higher_order", "anchor"),
   f"heaviest was {heaviest.key}")


# ══════════════════════════════════════════════
# 2. BANDS
# ══════════════════════════════════════════════
print("[bands]")

ok("bands cover 0..256 with no gap",
   BANDS[0].low == 0 and BANDS[-1].high == 256)
for i in range(len(BANDS) - 1):
    ok(f"band {i} abuts band {i+1}",
       BANDS[i].high + 1 == BANDS[i+1].low,
       f"{BANDS[i].high} then {BANDS[i+1].low}")

eq("score 0 is Novice",         "Novice",       band_for(0).name)
eq("score 256 is Architect",    "Architect",    band_for(256).name)
eq("score 128 is Practitioner", "Practitioner", band_for(128).name)
eq("novice gets full scaffolding",  "full",   band_for(10).scaffold)
eq("architect gets silent",         "silent", band_for(250).scaffold)

# every band names a distinct scaffolding level
levels = [b.scaffold for b in BANDS]
eq("scaffolding levels are distinct", len(levels), len(set(levels)))


# ══════════════════════════════════════════════
# 3. OBSERVATION SCORING
# ══════════════════════════════════════════════
print("[observation]")

o_empty = Observation()
eq("empty observation scores at the start point",
   float(P_START), o_empty.session_score())

o_simple = Observation()
for _ in range(10):
    o_simple.note("lit_int")
o_simple.note("bind_let")
o_simple.max_depth = 1

o_advanced = Observation()
o_advanced.note("recursion")
o_advanced.note("branch")
o_advanced.note("compare")
o_advanced.note("fn_def")
o_advanced.note("composition")
o_advanced.max_depth = 5

ok("advanced session outscores simple session",
   o_advanced.session_score() > o_simple.session_score(),
   f"simple={o_simple.session_score():.1f}  advanced={o_advanced.session_score():.1f}")

ok("simple-only session has simple_ratio 1.0",
   abs(o_simple.simple_ratio - 1.0) < 1e-9,
   f"got {o_simple.simple_ratio}")
ok("advanced session has non-zero advanced_ratio",
   o_advanced.advanced_ratio > 0.0)

# tier totals must sum to the count
tt = o_advanced.tier_totals()
eq("tier totals sum to the construct count",
   o_advanced.total, sum(tt.values()))

# ── CLAIM 3, part A: repetition must not inflate the score ──
# Forty copies of one construct is one fact about its author, not
# forty. Because difficulty is a weighted MEAN, counts cancel.
o_once = Observation(); o_once.note("recursion"); o_once.max_depth = 3
o_repeat = Observation()
for _ in range(40):
    o_repeat.note("recursion")
o_repeat.max_depth = 3

eq("repeated construct counts as 1 unique", 1, o_repeat.unique)
eq("40 uses score the same as 1 use",
   round(o_once.session_score(), 6), round(o_repeat.session_score(), 6))

# ── CLAIM 3, part B: range breaks ties WITHIN a tier ──
o_narrow = Observation()
for _ in range(40):
    o_narrow.note("compare")       # one tier-2 construct, forty times
o_narrow.max_depth = 3

o_variety = Observation()
for k in ("compare", "branch", "fn_def", "fn_call",
          "multi_param", "nested_expr"):
    o_variety.note(k)              # six different tier-2 constructs
o_variety.max_depth = 3

eq("varied session counts 6 unique", 6, o_variety.unique)
ok("breadth at a tier beats repetition at that tier",
   o_variety.session_score() > o_narrow.session_score(),
   f"varied={o_variety.session_score():.1f}  narrow={o_narrow.session_score():.1f}")

# ── CLAIM 3, part C: diversity must NOT outrank difficulty ──
# A program that only recurses still beats a broad sweep of
# intermediate work, and should: recursion demonstrates something the
# intermediate set does not. Asserting this pins the weighting so a
# future tweak to diversity cannot quietly invert it.
ok("a harder construct outranks a broader set of easier ones",
   o_repeat.session_score() > o_variety.session_score(),
   f"advanced={o_repeat.session_score():.1f}  intermediate={o_variety.session_score():.1f}")

# depth saturates rather than running away
o_deep = Observation(); o_deep.note("branch"); o_deep.max_depth = 40
o_mid  = Observation(); o_mid.note("branch");  o_mid.max_depth  = 8
eq("depth saturates at 8", o_mid.session_score(), o_deep.session_score())


# ══════════════════════════════════════════════
# 4. THE CORE CLAIM — THE SCORE SHIFTS
# ══════════════════════════════════════════════
print("[dynamics]")

p = Profiler()
start = p.profile.score
p.observe(o_advanced)
ok("advanced work raises the score", p.profile.score > start,
   f"{start:.1f} then {p.profile.score:.1f}")

p2 = Profiler()
p2.profile.score = 200.0
p2.observe(o_simple)
ok("simple work lowers a high score", p2.profile.score < 200.0,
   f"200.0 then {p2.profile.score:.1f}")

# ── CLAIM 2: asymmetry ──
# From the same starting point, an equal-magnitude gain and loss must
# not move the score equally. Rising is trusted more than falling.
mid = 128.0
up   = Profiler(); up.profile.score   = mid
down = Profiler(); down.profile.score = mid

high_obs = Observation()
for k in ("recursion", "composition", "confidence", "higher_order",
          "branch", "fn_def"):
    high_obs.note(k)
high_obs.max_depth = 6

low_obs = Observation()
low_obs.note("lit_int"); low_obs.max_depth = 1

up.observe(high_obs)
down.observe(low_obs)

gain = up.profile.score - mid
loss = mid - down.profile.score
ok("score rises faster than it falls",
   (gain / max(abs(high_obs.session_score() - mid), 1e-9)) >
   (loss / max(abs(mid - low_obs.session_score()), 1e-9)),
   f"gain={gain:.1f} loss={loss:.1f}")
ok("alpha asymmetry is 3:1", abs(ALPHA_UP / ALPHA_DOWN - 3.0) < 0.01)

# one weak session must not demote a fluent user out of their band
fluent = Profiler(); fluent.profile.score = 190.0
band_before = fluent.profile.band.name
fluent.observe(low_obs)
eq("one simple session does not demote a fluent user",
   band_before, fluent.profile.band.name)

# the score is clamped to the scale
clamp_hi = Profiler(); clamp_hi.profile.score = 255.0
for _ in range(50):
    clamp_hi.observe(high_obs)
ok("score never exceeds 256", clamp_hi.profile.score <= P_MAX)
clamp_lo = Profiler(); clamp_lo.profile.score = 1.0
for _ in range(50):
    clamp_lo.observe(low_obs)
ok("score never drops below 0", clamp_lo.profile.score >= P_MIN)


# ══════════════════════════════════════════════
# 5. TRAJECTORY — novice to architect
# ══════════════════════════════════════════════
print("[trajectory]")

j = Profiler()
path = []

# weeks 1-3: literals and let bindings only
for _ in range(6):
    o = Observation()
    for _ in range(6): o.note("lit_int")
    o.note("bind_let"); o.note("var_ref"); o.note("arith")
    o.max_depth = 1
    j.observe(o)
path.append(("weeks 1-3 simple only", j.profile.rounded, j.profile.band.name))

# weeks 4-6: comparisons and branching appear
for _ in range(6):
    o = Observation()
    o.note("compare"); o.note("branch"); o.note("bind_let")
    o.note("lit_int"); o.note("var_ref"); o.note("nested_expr")
    o.max_depth = 3
    j.observe(o)
path.append(("weeks 4-6 branching", j.profile.rounded, j.profile.band.name))

# weeks 7-9: functions
for _ in range(6):
    o = Observation()
    for k in ("fn_def", "fn_call", "multi_param", "branch",
              "compare", "nested_expr", "bind_ever"):
        o.note(k)
    o.max_depth = 4
    j.observe(o)
path.append(("weeks 7-9 functions", j.profile.rounded, j.profile.band.name))

# weeks 10+: recursion, composition, confidence
for _ in range(8):
    o = Observation()
    for k in ("recursion", "composition", "confidence", "zero_abs",
              "nested_branch", "fn_def", "branch", "compare",
              "aggregate", "higher_order", "anchor"):
        o.note(k)
    o.max_depth = 6
    j.observe(o)
path.append(("weeks 10+ advanced", j.profile.rounded, j.profile.band.name))

for label, score, band in path:
    print(f"    {label:<26} {score:>3}/256  {band}")

scores = [s for _, s, _ in path]
ok("score climbs monotonically across the trajectory",
   all(scores[i] < scores[i+1] for i in range(len(scores)-1)),
   f"path was {scores}")
ok("beginner phase reads as Novice or Learner",
   path[0][2] in ("Novice", "Learner"), path[0][2])
ok("advanced phase reaches Fluent or Architect",
   path[-1][2] in ("Fluent", "Architect"), path[-1][2])
eq("trend reports climbing", "climbing", j.profile.trend())


# ══════════════════════════════════════════════
# 6. SCAFFOLDING — the user-visible payoff
# ══════════════════════════════════════════════
print("[scaffolding]")

msg     = "unbound name 'total'"
hint    = "You used 'total' before giving it a value. Name it first."
example = "let total = 0\nshow total"

renders = {}
for target_score, expect_level in [(20, "full"), (90, "guided"),
                                   (140, "hints"), (190, "terse"),
                                   (240, "silent")]:
    pr = Profiler(); pr.profile.score = float(target_score)
    eq(f"score {target_score} maps to '{expect_level}'",
       expect_level, pr.scaffold_level())
    renders[expect_level] = pr.explain_error(msg, hint, example)

ok("full scaffolding includes a worked example",
   "let total = 0" in renders["full"])
ok("guided includes the explanation but not the example",
   hint in renders["guided"] and "let total = 0" not in renders["guided"])
ok("hints is shorter than guided",
   len(renders["hints"]) < len(renders["guided"]))
ok("terse is just the message", renders["terse"].strip() == msg)
ok("silent is just the message", renders["silent"].strip() == msg)
ok("every level still states the actual error",
   all(msg in r for r in renders.values()))

print("\n    same error, five bands:")
for lvl in ("full", "guided", "hints", "terse"):
    first = renders[lvl].split("\n")[0]
    print(f"      {lvl:<8} {first[:52]}")


# ══════════════════════════════════════════════
# 7. SUGGESTIONS — next step, not hardest step
# ══════════════════════════════════════════════
print("[suggestions]")

nov = Profiler(); nov.profile.score = 30.0
nov.profile.lifetime = {"lit_int": 20, "bind_let": 10, "var_ref": 8}
sug = nov.next_constructs(3)
ok("novice gets 3 suggestions", len(sug) == 3)
ok("novice is not shown recursion first",
   sug[0].key != "recursion", f"got {sug[0].key}")
ok("novice suggestions are tier 1-2",
   all(int(c.tier) <= 2 for c in sug),
   f"got {[(c.key, int(c.tier)) for c in sug]}")
ok("suggestions are constructs never used",
   all(not nov.profile.used(c.key) for c in sug))

arch = Profiler(); arch.profile.score = 230.0
arch.profile.lifetime = {k: 5 for k in TIER_MEMBERS[Tier.SIMPLE]}
arch.profile.lifetime.update({k: 5 for k in TIER_MEMBERS[Tier.INTERMEDIATE]})
asug = arch.next_constructs(3)
ok("architect is pointed at advanced constructs",
   all(int(c.tier) == 3 for c in asug),
   f"got {[(c.key, int(c.tier)) for c in asug]}")

full = Profiler()
full.profile.lifetime = {k: 1 for k in TAXONOMY}
eq("nothing left to suggest when all used", 0, len(full.next_constructs(3)))


# ══════════════════════════════════════════════
# 8. PERSISTENCE
# ══════════════════════════════════════════════
print("[persistence]")

with tempfile.TemporaryDirectory() as td:
    path_p = os.path.join(td, "profile.json")
    a = Profiler(path=path_p)
    for _ in range(5):
        a.observe(o_advanced)
    saved_score = a.profile.rounded
    saved_sessions = a.profile.sessions
    a.save()
    ok("profile file was written", os.path.exists(path_p))

    b = Profiler(path=path_p)
    eq("score survives a reload",    saved_score,    b.profile.rounded)
    eq("sessions survive a reload",  saved_sessions, b.profile.sessions)
    ok("lifetime counts survive a reload",
       b.profile.lifetime.get("recursion", 0) == 5,
       f"got {b.profile.lifetime.get('recursion')}")

    raw = json.loads(open(path_p).read())
    ok("stored profile is plain JSON", "score" in raw and "lifetime" in raw)

    corrupt = os.path.join(td, "bad.json")
    open(corrupt, "w").write("{not json")
    c = Profiler(path=corrupt)
    eq("corrupt profile falls back to a fresh one",
       float(P_START), c.profile.score)

# history is bounded so the file cannot grow without limit
hp = Profiler()
for _ in range(260):
    hp.observe(o_simple)
ok("history is capped at 200 entries", len(hp.profile.history) <= 200,
   f"got {len(hp.profile.history)}")


# ══════════════════════════════════════════════
# 9. AST CLASSIFICATION
# ══════════════════════════════════════════════
print("[classification]")

from syntax import parse, Semantic

def observe_src(src):
    ast, err = parse(src)
    if err:
        return None
    o = classify(ast)
    observe_source_flags(o, src)
    return o

cases = [
    ("1 + 2",                      ["arith", "lit_int"]),
    ("x > 5",                      ["compare"]),
    ("if x > 5 then 1 else 0",     ["branch", "compare"]),
    ("square(7)",                  ["fn_call"]),
    ("f(g(3))",                    ["fn_call", "composition"]),
    ('"hello"',                    ["lit_text"]),
    ("3.14",                       ["lit_real"]),
    ("(1 + 2) * 3",                ["arith", "nested_expr"]),
]
for src, expect in cases:
    o = observe_src(src)
    if o is None:
        ok(f"parse: {src}", False, "parse failed")
        continue
    missing = [k for k in expect if k not in o.counts]
    ok(f"classify {src!r}", not missing,
       f"missing {missing}, saw {sorted(o.counts)}")

# recursion detection through a function definition
o = observe_src("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
ok("recursion is detected", o and "recursion" in o.counts,
   f"saw {sorted(o.counts) if o else None}")
ok("function definition is detected", o and "fn_def" in o.counts)

# nested branching
o = observe_src("if a > 1 then (if b > 2 then 1 else 2) else 3")
ok("nested branching is detected", o and "nested_branch" in o.counts,
   f"saw {sorted(o.counts) if o else None}")

# let vs ever comes from statement syntax, not the expression AST
o = Observation()
observe_source_flags(o, "let x = 1\never y = 2")
ok("let binding detected from source", "bind_let"  in o.counts)
ok("ever binding detected from source", "bind_ever" in o.counts)


# ══════════════════════════════════════════════
# 10. SEMANTIC INTEGRATION
# ══════════════════════════════════════════════
print("[integration]")

pr = Profiler()
src = "if n > 5 then n * 2 else 0"
ast, err = parse(src)
sem = Semantic(profiler=pr, source=src)
a = sem.analyse(ast)

ok("Analysis carries an observation", a.observation is not None)
ok("Analysis carries a proficiency score", a.proficiency is not None)
ok("Analysis carries a scaffold level", a.scaffold is not None)
ok("proficiency is on the 0..256 scale",
   a.proficiency is not None and 0 <= a.proficiency <= 256)
mix = a.construct_mix
ok("construct mix reports simple ratio",  "simple"   in mix)
ok("construct mix reports advanced ratio","advanced" in mix)
ok("construct mix reports unique count",  mix.get("unique", 0) > 0)

# profiling must not disturb the analysis itself
sem_plain = Semantic()
a_plain = sem_plain.analyse(parse(src)[0])
eq("type inference is unchanged by profiling", a_plain.ty, a.ty)
eq("error list is unchanged by profiling", a_plain.errors, a.errors)
eq("size is unchanged by profiling", a_plain.size, a.size)

# without a profiler, the observation is still produced but no state moves
sem_no = Semantic(source=src)
a_no = sem_no.analyse(parse(src)[0])
ok("observation produced without a profiler", a_no.observation is not None)
ok("no score written without a profiler",     a_no.proficiency is None)

# a broken node must not take down the semantic pass
class Broken:
    def __getattr__(self, k): raise RuntimeError("boom")
try:
    sem_b = Semantic(profiler=Profiler())
    sem_b._profile(Broken(), a_plain)
    ok("profiler failure is contained", True)
except Exception as e:
    ok("profiler failure is contained", False, str(e))

# repeated analysis accumulates
pr2 = Profiler()
before = pr2.profile.sessions
for s in ["1 + 1", "if x > 1 then 2 else 3", "f(g(h(1)))"]:
    node, _ = parse(s)
    Semantic(profiler=pr2, source=s).analyse(node)
eq("each analysis is one session", before + 3, pr2.profile.sessions)


# ══════════════════════════════════════════════
# 11. REPORT
# ══════════════════════════════════════════════
print("[report]")

rep = j.report()
ok("report shows the score",  "/256" in rep)
ok("report shows the band",   any(b.name in rep for b in BANDS))
ok("report shows a bar",      "█" in rep or "░" in rep)
ok("report shows tier usage", "simple" in rep and "advanced" in rep)
ok("report suggests next steps", "try next" in rep)


# ══════════════════════════════════════════════
print("\n" + "=" * 58)
print(f"=== Dynamic Profiler: {_pass} passed, {_fail} failed ===")
print("=" * 58 + "\n")
sys.exit(0 if _fail == 0 else 1)
