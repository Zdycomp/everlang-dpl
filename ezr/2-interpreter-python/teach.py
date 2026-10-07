#!/usr/bin/env python3
"""
teach.py — Ever / Tapestry, the teaching layer

Same engine. Same numbers. Different words.

Ever's checker says:

    CONFIDENT @ 18/256
    3 errors · defects: unbounded, misbound
    line 4: statement missing semicolon before closing brace

Somebody on their first day reads that and closes the laptop. This layer
says the same thing in words they already know, shows the exact change,
explains the rule behind it, and gives them ONE thing to do next.

Three rules this layer keeps:

  1. ONE FIX AT A TIME. Twelve problems at once is how people quit.
  2. SHOW THE CHANGE. "Add a semicolon" is advice. `return x + y;` is
     an answer, and they can decide whether to type it or take it.
  3. NEVER A WALL. A Z is "I could not work this out yet", never a
     refusal. HTML won because a broken page still renders.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ever import E_CERTAIN, E_EXECUTE_FLOOR
from checker import Translator, ELang, Finding, classify


# ═════════════════════════════════════════════
# How confident, in words
# ═════════════════════════════════════════════

BANDS: List[Tuple[int, str, str]] = [
    (0,   "Just getting started",
     "There's a fair bit to fix here. Everyone starts here."),
    (40,  "Early days",
     "This needs work, but the shape of it is there."),
    (90,  "Getting there",
     "Most of it holds up. A couple of things left."),
    (128, "This will run",
     "Nothing here would stop it working."),
    (180, "Solid",
     "This is in good shape."),
    (230, "Really solid",
     "Hard to fault this."),
    (256, "Verified",
     "Tested and proven, not just written."),
]


def band(confidence: int) -> Tuple[str, str]:
    label, note = BANDS[0][1], BANDS[0][2]
    for floor, l, n in BANDS:
        if confidence >= floor:
            label, note = l, n
    return label, note


def percent(confidence: int) -> int:
    return int(round(100 * confidence / E_CERTAIN))


# ═════════════════════════════════════════════
# The lessons
# ═════════════════════════════════════════════

@dataclass
class Lesson:
    """One thing to fix, explained for somebody who has never seen it."""
    match: str                  # substring of the checker's message
    title: str                  # what it is, in plain words
    what: str                   # what is happening
    why: str                    # why it matters
    fix: str                    # what to do
    example_before: str = ""
    example_after: str = ""
    tone: str = "normal"        # "normal" | "safety"


LESSONS: List[Lesson] = [
    # ── endings and closings ──
    Lesson("missing semicolon",
           "A line needs a semicolon at the end",
           "In this language every instruction ends with a semicolon. One "
           "of yours doesn't, so it runs into the next line and confuses "
           "the computer.",
           "The semicolon is a full stop. It's how the language knows one "
           "instruction finished and the next one began.",
           "Put a ; at the end of that line.",
           "return x + y", "return x + y;"),

    Lesson("missing end",
           "Something was opened and never closed",
           "You started a block with def, do, if or class, and there's no "
           "matching end to close it.",
           "Ruby needs to know where a block stops. Without end it keeps "
           "reading and runs off the bottom of the file.",
           "Add end on its own line, lined up with the word that opened "
           "the block.",
           "def greet\n  puts \"hi\"", "def greet\n  puts \"hi\"\nend"),

    Lesson("missing colon",
           "A line needs a colon at the end",
           "In Python, def, if, for and while all end with a colon before "
           "the indented block underneath.",
           "The colon is what says \"the next indented lines belong to "
           "this\". Without it Python doesn't know the block started.",
           "Add : at the end of that line.",
           "def greet(name)", "def greet(name):"),

    Lesson("unclosed",
           "A tag was opened and never closed",
           "An HTML tag was opened but never closed, so everything after "
           "it gets swallowed into it.",
           "Browsers try to guess what you meant, and they often guess "
           "wrong. Closing it yourself removes the guesswork.",
           "Add the matching closing tag.",
           "<div><p>text</div>", "<div><p>text</p></div>"),

    Lesson("unbalanced",
           "Brackets don't match up",
           "There are more opening brackets than closing ones, or the "
           "other way round.",
           "Every ( needs a ). The computer counts them, and if the count "
           "is off it can't tell where anything starts or stops.",
           "Count the brackets on that line and add the missing one."),

    Lesson("unterminated",
           "A piece of text was never closed",
           "A quote was opened and never closed, so the rest of the file "
           "is being read as text.",
           "Quotes come in pairs. Everything between them is text rather "
           "than instructions.",
           "Add the closing quote.",
           'name = "Codric', 'name = "Codric"'),

    # ── safety ──
    Lesson("without WHERE",
           "This would delete everything",
           "A DELETE or UPDATE with no WHERE line doesn't touch one row. "
           "It touches every row in the table.",
           "This is one of the most common ways real data gets destroyed, "
           "and it usually can't be undone.",
           "Add a WHERE line saying which rows you mean.",
           "DELETE FROM users", "DELETE FROM users WHERE id = 42",
           tone="safety"),

    Lesson("concatenation into SQL",
           "Someone else could rewrite this query",
           "You're gluing text straight into a database command. Whatever "
           "a user types becomes part of the command.",
           "If someone types the right thing in a form, they can read or "
           "delete anything in your database. This has a name — SQL "
           "injection — and it's how a lot of real break-ins happen.",
           "Use a placeholder and pass the value separately.",
           'WHERE name = "' + "' + userName + '" + '"',
           "WHERE name = ?",
           tone="safety"),

    Lesson("gets is unsafe",
           "This function can be used to break in",
           "gets() reads input with no limit on length. Type more than "
           "the space you set aside, and it writes straight past the end.",
           "This is a buffer overflow. It's how a lot of serious security "
           "holes work, and gets() is so unsafe it was removed from the C "
           "standard.",
           "Use fgets, which takes a size limit.",
           "gets(buf);", "fgets(buf, sizeof buf, stdin);",
           tone="safety"),

    Lesson("null used without a guard",
           "This might not exist when you use it",
           "A value here can be null — meaning nothing at all — and it's "
           "being used without checking first.",
           "If it's null when you use it, the program stops immediately. "
           "This is the single most common crash in Java.",
           "Check it isn't null before you use it.",
           "return owner.equals(who);",
           "if (owner == null) return false;\nreturn owner.equals(who);",
           tone="safety"),

    Lesson("eval",
           "This runs whatever text it's given",
           "eval takes text and runs it as code. If that text ever comes "
           "from someone else, they choose what your program does.",
           "It's the most direct way to hand control of your program to a "
           "stranger.",
           "Use a safe parser instead. For data, ast.literal_eval.",
           "eval(line)", "ast.literal_eval(line)",
           tone="safety"),

    Lesson("DROP TABLE without IF EXISTS",
           "This will fail if the table is already gone",
           "DROP TABLE errors out when the table isn't there.",
           "Adding IF EXISTS makes it safe to run twice, which matters "
           "when scripts get re-run.",
           "Write DROP TABLE IF EXISTS instead.",
           "DROP TABLE audit;", "DROP TABLE IF EXISTS audit;"),

    Lesson("cartesian",
           "This joins every row to every other row",
           "A JOIN without an ON line pairs every row in one table with "
           "every row in the other.",
           "Two tables of 1,000 rows become a million rows. It's slow, and "
           "the answer is wrong.",
           "Add ON saying which columns should match.",
           "FROM a JOIN b", "FROM a JOIN b ON a.id = b.a_id"),

    # ── things that surprise people later ──
    Lesson("mutable default",
           "This list is shared between every call",
           "A list written as a default value is created once, not once "
           "per call. Every call adds to the same list.",
           "It's one of Python's genuine traps. The function works the "
           "first time and gets stranger every call after.",
           "Use None as the default and make the list inside.",
           "def collect(items=[]):",
           "def collect(items=None):\n    if items is None:\n        items = []"),

    Lesson("compared with ==",
           "This compares locations, not words",
           "In Java, == on text asks whether they're the same object in "
           "memory, not whether they say the same thing.",
           "Two strings can read identically and still fail ==. It works "
           "in small tests and breaks in real use, which makes it hard to "
           "track down.",
           "Use .equals() to compare what they say.",
           'if (who == "admin")', 'if ("admin".equals(who))'),

    Lesson("bare except",
           "This hides every problem, including ones you'd want to know about",
           "A catch with no error type swallows everything, then carries "
           "on as if nothing happened.",
           "When something does go wrong you get no message and no clue "
           "where it came from.",
           "Name the error you're expecting.",
           "except:", "except ValueError as e:"),

    Lesson("bare rescue",
           "This hides every problem",
           "rescue with no error type catches everything, including "
           "problems you'd want to see.",
           "Silent failure is harder to fix than a loud one.",
           "Name the error you're expecting.",
           "rescue", "rescue StandardError => e"),

    Lesson("empty catch",
           "A problem is being caught and then ignored",
           "The catch block is empty, so when something fails nothing "
           "happens at all.",
           "The program keeps going in a broken state and you never find "
           "out why.",
           "At minimum, print it.",
           "catch (Exception e) {}",
           "catch (Exception e) { e.printStackTrace(); }"),

    Lesson("without alt",
           "This image has no description",
           "An image with no alt text is invisible to screen readers and "
           "shows nothing when the image fails to load.",
           "People using screen readers get nothing at all. In many "
           "places it's also a legal requirement.",
           "Add alt with a short description.",
           '<img src="lock.png">',
           '<img src="lock.png" alt="Secure checkout">'),

    Lesson("input without type",
           "This box doesn't say what goes in it",
           "An input with no type is treated as plain text, so phones "
           "show the wrong keyboard and the browser can't check anything.",
           "Setting the type gets you a number pad for numbers, an email "
           "keyboard for emails, and free validation.",
           "Add type.",
           '<input placeholder="card number">',
           '<input type="tel" inputmode="numeric" placeholder="card number">'),

    Lesson("no label anchor",
           "This box has no label",
           "There's nothing tying this input to a label, so a screen "
           "reader can't say what it's for.",
           "Placeholder text disappears the moment someone starts typing. "
           "A real label doesn't.",
           "Give the input an id and point a label at it.",
           '<input type="text">',
           '<label for="card">Card number</label>\n<input id="card" type="text">'),

    Lesson("noopener",
           "This link gives the new page control of yours",
           "A link with target=\"_blank\" lets the page it opens reach "
           "back and change the page it came from.",
           "It can be used to swap your page for a fake one after "
           "someone clicks away. Two words close it.",
           'Add rel="noopener noreferrer".',
           '<a href="/pay" target="_blank">',
           '<a href="/pay" target="_blank" rel="noopener noreferrer">'),

    Lesson("form without action",
           "This form doesn't say where it sends things",
           "A form with no action posts back to the same page, which is "
           "rarely what's meant.",
           "People fill it in, press the button, and nothing happens.",
           "Add action with the address it should send to.",
           "<form>", '<form action="/checkout" method="post">'),

    Lesson("global variable",
           "This can be changed from anywhere",
           "A variable starting with $ is visible and changeable from "
           "every part of the program.",
           "When it holds the wrong value there's no way to narrow down "
           "which part of the code did it.",
           "Use an instance variable with @ instead.",
           "$cart_total = 0", "@cart_total = 0"),

    Lesson("without delete",
           "Memory is taken and never given back",
           "Something is created with new and never released.",
           "The program uses more memory the longer it runs, until it "
           "runs out. This is a memory leak.",
           "Use a smart pointer that releases it for you.",
           "Shape* s = new Shape();",
           "auto s = std::make_unique<Shape>();"),

    Lesson("malloc without",
           "Memory is taken and never given back",
           "malloc reserves memory and nothing ever frees it.",
           "The program grows until it runs out of memory.",
           "Call free() when you're done with it.",
           "char *p = malloc(64);",
           "char *p = malloc(64);\n/* ... */\nfree(p);"),

    Lesson("virtual destructor",
           "Cleanup might get skipped",
           "A class with virtual methods needs a virtual destructor, or "
           "deleting through a base pointer skips the derived cleanup.",
           "Parts of the object never get tidied up and the memory leaks.",
           "Add a virtual destructor.",
           "class Shape { virtual void draw(); };",
           "class Shape {\n  virtual void draw();\n  virtual ~Shape() = default;\n};"),

    Lesson("SELECT *",
           "This asks for every column, whatever they turn out to be",
           "SELECT * fetches all columns, so the answer changes shape "
           "whenever somebody changes the table.",
           "Code that worked yesterday breaks when a column is added, "
           "and it's slower than asking for what you need.",
           "Name the columns you want.",
           "SELECT * FROM accounts", "SELECT id, name FROM accounts"),

    Lesson("without primary key",
           "This table has no way to tell rows apart",
           "There's no primary key, so two identical rows are "
           "indistinguishable.",
           "You can't reliably update or delete one row without one.",
           "Add a primary key column.",
           "CREATE TABLE t (name TEXT)",
           "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"),

    Lesson("mixed tabs and spaces",
           "Tabs and spaces are mixed together",
           "Some lines are indented with tabs and others with spaces. "
           "They look the same and aren't.",
           "Python decides what belongs to what by indentation, so this "
           "produces errors that are invisible on screen.",
           "Use four spaces everywhere.",),

    Lesson("main does not return",
           "The program never says how it went",
           "main has no return, so it never reports whether it succeeded.",
           "Other programs check that number to decide what to do next.",
           "Add return 0; at the end for success.",
           "int main() { }", "int main() {\n    return 0;\n}"),

    Lesson("namespace std",
           "This pulls in every standard name at once",
           "using namespace std brings in the entire standard library's "
           "names, which can collide with yours.",
           "Two things end up with the same name and the compiler picks "
           "one, sometimes the wrong one.",
           "Write std:: where you need it.",
           "using namespace std;\ncout << x;", "std::cout << x;"),
]


def find_lesson(message: str) -> Optional[Lesson]:
    m = message.lower()
    for lesson in LESSONS:
        if lesson.match.lower() in m:
            return lesson
    return None


# ═════════════════════════════════════════════
# What a beginner sees
# ═════════════════════════════════════════════

FRIENDLY_LANG = {
    ELang.C: "C", ELang.CPP: "C++", ELang.PYTHON: "Python",
    ELang.RUBY: "Ruby", ELang.SQL: "SQL", ELang.JAVA: "Java",
    ELang.HTML: "HTML", ELang.EVER: "Ever",
}


@dataclass
class Step:
    """One thing to do next."""
    lesson: Optional[Lesson]
    finding: Finding
    line: int
    raw_message: str

    @property
    def title(self) -> str:
        return self.lesson.title if self.lesson else self.raw_message

    @property
    def is_safety(self) -> bool:
        return bool(self.lesson and self.lesson.tone == "safety")


@dataclass
class Report:
    language: str
    confidence: int
    label: str
    note: str
    pct: int
    good: List[str]
    steps: List[Step]
    total_issues: int
    unknown: bool = False

    @property
    def next_step(self) -> Optional[Step]:
        return self.steps[0] if self.steps else None

    @property
    def done(self) -> bool:
        return not self.steps


class Teacher:
    """Turns a checker result into something a beginner can act on."""

    def __init__(self):
        self.tr = Translator()

    def review(self, code: str,
               lang: Optional[ELang] = None) -> Report:
        t = self.tr.translate(code, ident="yours", lang=lang)

        steps: List[Step] = []
        for f in t.errors:
            steps.append(Step(find_lesson(f.message), f, f.line, f.message))

        # Safety first, then by how much it costs, then by line. A
        # beginner should be pointed at the thing that would actually
        # hurt them before the thing that is merely untidy.
        steps.sort(key=lambda s: (not s.is_safety, -s.finding.weight, s.line))

        good = [self._praise(p.message) for p in t.patterns]

        conf = t.particle.confidence
        # A Z means the checker gave up, not that the code is worthless.
        # Show the effort, never a zero with no explanation.
        unknown = t.particle.is_z
        if unknown and steps:
            conf = max(1, 128 - 20 * len(steps))

        label, note = band(conf)
        if unknown:
            # A Z means the checker gave up on part of this, which is a
            # different message from "your code is poor". Say which.
            note = ("I couldn't work out part of this one. That's on me "
                    "as much as you — start with the fix below.")
        return Report(
            language=FRIENDLY_LANG.get(t.lang, "code"),
            confidence=conf, label=label, note=note, pct=percent(conf),
            good=good, steps=steps, total_issues=len(steps),
            unknown=unknown)

    @staticmethod
    def _praise(pattern: str) -> str:
        nice = {
            "header inclusion": "you brought in the tools you need",
            "entry point declared": "your program has a clear starting point",
            "function defined": "you're using functions, which keeps things tidy",
            "method defined": "you're using methods, which keeps things tidy",
            "return type annotated": "you said what comes back — that helps",
            "parameters typed": "you said what goes in — that helps a lot",
            "class declared": "you're grouping related things together",
            "public class": "you're grouping related things together",
            "exception handled": "you're handling things that can go wrong",
            "immutability asserted": "you're marking things that shouldn't change",
            "optional over null": "you're avoiding null — good instinct",
            "RAII ownership": "cleanup is handled for you here — good choice",
            "attribute accessor": "clean way to expose values",
            "block with parameters": "nice use of blocks",
            "doctype declared": "you told the browser what this is",
            "language declared": "you set the language — screen readers need that",
            "aria attributes": "you're thinking about accessibility",
            "semantic structure": "your page structure is meaningful, not just boxes",
            "form element": "you're collecting input properly",
            "table defined": "your data has a shape",
            "index declared": "you thought about speed",
            "referential integrity": "your tables know how they relate",
            "transactional boundary": "you're keeping changes together",
        }
        for k, v in nice.items():
            if k in pattern.lower():
                return v
        return pattern

    # ── rendering ──

    def render(self, r: Report, show_fix: bool = True) -> str:
        out: List[str] = []
        bar = "\u2588" * (r.pct // 5) + "\u2591" * (20 - r.pct // 5)

        out.append(f"  {r.language}   {bar}  {r.pct}%")
        out.append(f"  {r.label} \u2014 {r.note}")
        out.append("")

        if r.good:
            out.append("  What's already working:")
            for g in r.good[:3]:
                out.append(f"    \u2713 {g}")
            out.append("")

        if r.done:
            out.append("  Nothing to fix. This is ready.")
            return "\n".join(out)

        left = r.total_issues - 1
        s = r.next_step
        out.append(f"  ONE THING AT A TIME"
                   + (f"   ({left} more after this)" if left else ""))
        out.append("")
        if s.is_safety:
            out.append("  \u26a0 This one matters more than the others.")
            out.append("")
        out.append(f"  {s.title}")
        if s.line:
            out.append(f"  around line {s.line}")
        out.append("")

        if s.lesson:
            out.append(f"    {self._wrap(s.lesson.what)}")
            out.append("")
            out.append("    Why it matters:")
            out.append(f"    {self._wrap(s.lesson.why)}")
            out.append("")
            out.append(f"    What to do: {s.lesson.fix}")
            if show_fix and s.lesson.example_before:
                out.append("")
                out.append("      you wrote:")
                for ln in s.lesson.example_before.split("\n"):
                    out.append(f"        {ln}")
                out.append("      change to:")
                for ln in s.lesson.example_after.split("\n"):
                    out.append(f"        {ln}")
        else:
            out.append(f"    {s.raw_message}")
            if s.finding.fix_hint:
                out.append(f"    Try: {s.finding.fix_hint}")

        out.append("")
        out.append("  Fix that one, then check again. The rest can wait.")
        return "\n".join(out)

    @staticmethod
    def _wrap(text: str, width: int = 66, indent: str = "    ") -> str:
        words, lines, cur = text.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > width:
                lines.append(cur); cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        return ("\n" + indent).join(lines)


# ═════════════════════════════════════════════
# Demonstration
# ═════════════════════════════════════════════

SAMPLES = {
    "C": 'int add(int x, int y) { return x + y }',
    "SQL": "DELETE FROM users",
    "Python": "def collect(items=[]):\n    items.append(1)\n    return items",
    "HTML": '<div><img src="a.jpg"></div>',
    "Java": "public class A {\n  void f() {\n    String s = null;\n    s.length();\n  }\n}",
}

if __name__ == "__main__":
    t = Teacher()
    for name, code in SAMPLES.items():
        print("\n" + "=" * 70)
        print(f"  someone pasted this {name}:")
        for ln in code.split("\n"):
            print(f"      {ln}")
        print("=" * 70)
        print(t.render(t.review(code)))
    print()
