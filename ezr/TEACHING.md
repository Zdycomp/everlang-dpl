# Ever — Code for Dummies

**Same engine. Same numbers. Different words.**

Codric Enterprise · Ricky (Dreid) · 2026

---

## The one thing that had to change

Ever's core mechanic was **withholding**. Below 128 it refused. A
beginner pastes their first attempt, sees `withheld: 18/256`, and closes
the laptop.

Every other design choice was already beginner-friendly. That one was
beginner-hostile, and it was load-bearing.

**HTML won because it never punishes you.** Write broken HTML and the
page still renders. Forget a closing tag and the browser guesses. You are
never blocked. That is the property worth copying, and it does not
require giving up anything Ever already does.

### Learn mode and Ship mode

The confidence number *is* the feedback. The floor is a separate concern
— a production-safety feature that had been welded onto the learning
experience.

| | Behaviour |
|---|---|
| **Learn** | never blocks. Always computes, always shows a result. The number says how much to lean on it. |
| **Ship** | the floor is enforced, exactly as before. |

Same engine, same math, same archive. One flag. Learn mode is arguably
*more* faithful to Ever's philosophy than the hard floor was: the whole
premise is that confidence is a scale rather than pass/fail, and a
pass/fail gate had been bolted on top of the scale.

---

## Three rules the teaching layer keeps

### 1. One thing at a time

Twelve problems at once is how people quit. Ever finds all of them,
archives all of them, and shows **one** — with a quiet count of what
remains.

```
ONE THING AT A TIME   (2 more after this)
```

### 2. Show the change

"Add a semicolon" is advice. This is an answer:

```
  you wrote:
    return x + y
  change to:
    return x + y;
```

They decide whether to type it or take it. Typing it is how it sticks;
taking it is how they stay unblocked. Both are legitimate and the choice
is theirs.

### 3. Never a wall

A Z is *"I couldn't work this out yet"*, never a refusal — and the
wording takes the blame rather than assigning it:

> I couldn't work out part of this one. That's on me as much as you —
> start with the fix below.

---

## Before and after

Ever used to say:

```
CONFIDENT @ 18/256
3 errors · defects: unbounded, misbound
line 4: statement missing semicolon before closing brace
```

Now it says:

```
  C   ██████░░░░░░░░░░░░░░  34%
  Early days — This needs work, but the shape of it is there.

  ONE THING AT A TIME

  A line needs a semicolon at the end
  around line 1

    In this language every instruction ends with a semicolon. One of
    yours doesn't, so it runs into the next line and confuses the
    computer.

    Why it matters:
    The semicolon is a full stop. It's how the language knows one
    instruction finished and the next one began.

    What to do: Put a ; at the end of that line.

      you wrote:
        return x + y
      change to:
        return x + y;

  Fix that one, then check again. The rest can wait.
```

---

## Danger is ranked above untidiness

A beginner should be pointed at the thing that would actually hurt them
before the thing that is merely messy. Safety findings sort first and are
marked:

```
  ⚠ This one matters more than the others.

  This would delete everything
```

Ten of the thirty-two lessons are safety lessons: unbounded DELETE, SQL
injection, `gets()` overflow, unguarded null, `eval`, memory leaks,
missing `noopener`, and the rest.

---

## What's already working gets said

Every review leads with what the person did right, in words they'd use
themselves:

| Ever's internal pattern | What the beginner reads |
|---|---|
| `parameters typed` | you said what goes in — that helps a lot |
| `RAII ownership` | cleanup is handled for you here — good choice |
| `semantic structure` | your page structure is meaningful, not just boxes |
| `aria attributes` | you're thinking about accessibility |
| `optional over null` | you're avoiding null — good instinct |

And clean code is **recognised**, not met with silence:

> **Nothing to fix here.** This one holds up. Try changing something and
> check again to see what happens — breaking things on purpose is a good
> way to learn.

---

## The archive is "View Source"

"View Source" turned the entire web into a tutorial: you learned by
looking at other people's work.

Ever's archive is the same mechanism. Every fix taught is available to
everyone who hits the same error. It is the teaching engine and the moat
in one piece — and it was already built.

---

## Zero install

`ever-start.html` is a single file. No framework, no CDN, no build step,
no account. Open it from a USB stick on a library computer with no
internet and it works.

The browser was already there. That was always HTML's real advantage.

---

## Verified

| Component | Assertions |
|---|---|

This table used to be transcribed here by hand, and it had drifted: it
carried the same Python-interpreter row as three other documents and
`FINDINGS.md`, and `FINDINGS.md` said 81 while these said 83. Counts now
live in exactly one place, generated from a real run:

    python3 tests/assertion_counts.py

`FINDINGS.md` §5 carries the output and `--check` fails the gate when it
goes stale. See §5 there for why the 81 survived as long as it did.

The teaching tests check things unit tests normally don't: that no
fraction ever reaches the screen, that no internal defect word leaks,
that exactly one fix is shown at a time, that danger sorts first, and
that **every** sample produces a concrete next step rather than a dead
end.

---

## What did not change

The engine. The E-thread still threads into all seven languages. The
A-atom is untouched. The I-O-U loop still runs. Ever is still a language
that sits alongside C and SQL and can be threaded into either.

Only the words changed.
