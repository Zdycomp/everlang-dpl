# DPL Frontend: Supercodalexer → Quantification Ultra Parser → MegaExecuter

A lexer, parser and executor for DPL source text — the syntax `SuperTranspiler`'s
own `DPL` template already emits — so a program can be read, run through the
confidence model, and fanned out to every transpiler target.

## Grammar

```
program     := { line } EOF
line        := [ statement ] ( NEWLINE | EOF )
statement   := declaration | collision
declaration := "particle" IDENT ":" "E" "<" IDENT ">" "=" STRING "@" "confidence" "(" INT ")"
collision   := "collide" IDENT IDENT [ "->" IDENT ]

IDENT    := [A-Za-z_][A-Za-z0-9_]*        (except the keywords particle, collide, confidence)
INT      := [0-9]+
STRING   := '"' { any char except '"', '\', newline  |  '\"'  |  '\\' } '"'
comment  := '#' to end of line            (ignored)
```

Spaces and tabs separate tokens; `\r\n` is read as `\n`. A declaration line has
the same shape as `SuperTranspiler`'s `DPL` rendering, and `SuperTranspiler`
escapes `\` and `"` in DPL values (`escape_dpl_value`), so any DPL rendering
reads back to the same value and renders identically again.

## Semantics

- **declaration** creates `EParticle(value, confidence)` bound to `IDENT`. A
  confidence above 256 is clamped by `EParticle` and reported as a warning.
- **collision** runs `PhaseEngine.collide(a, b)` on two bound particles and records
  the outcome (`Z_CONTAGION`, `EXCEL`, `EXPEL`, `REPEL`). With `-> name`, the
  resulting particle is bound to `name` and can be collided again.
- Binding a name twice, or colliding an unbound name, is an error for that
  statement only; execution continues.

## Outputs

| Stage | Output |
|---|---|
| `Supercodalexer` | Tokens `(kind, text, line, col)`, and one diagnostic for **every** bad character, unterminated string, or unknown escape — not just the first. |
| `QuantificationUltraParser` | The program's statements, plus every syntax error in the file. Each error carries a fix hint. Parsing resumes at the next line after an error. |
| `MegaExecuter` | Per declaration: the particle and its rendering in every transpiler language (built-in and custom). Per collision: a trace entry (operands, outcome, reason, result). Runtime diagnostics. With a `ReinforcedArchive`, renderings go through `transpile_and_archive` and collisions through `log_boundary_marker`, so they are C++-gated and persisted. |

## Speed

`baseline.py` is a textbook reference implementation of the same language: a
character-by-character lexer, a recursive-descent parser, and a visitor-dispatch
executor. The Mega stages produce identical tokens, statements, diagnostics and
results (`tests/test_frontend.py` checks this on random input), so the only
difference is speed:

| Stage | How it's faster | Measured vs baseline (10k lines) |
|---|---|---|
| Supercodalexer | Whole well-formed lines matched by one regex; token tuples built in C via `zip`/`map`; per-token master regex only for other lines | 4.2–4.9× |
| Quantification Ultra Parser | Declarations the lexer already verified (`TokenStream.declaration_starts`) are built from known offsets; otherwise a 14-kind list comparison; recursive descent only for the rest | 1.5–2.4× |
| MegaExecuter | All active templates compiled into one generated f-string function; direct type dispatch | 2.1–2.4× |
| **End to end** | | **2.9–3.6×** |

End to end does not reach 4×. The parser and executor are dominated by work any
implementation must do — building `Declaration` nodes, constructing `EParticle`s,
rendering every language, building result records — which is about two thirds
of MegaExecuter's time. Getting past ~3.7× needs native code or giving up
byte-identical eager output.

`python3 -m everlang.frontend.bench [lines]` prints current ratios. The unit
test enforces regression floors with headroom for timing noise: lexer ≥3×,
end to end ≥2×.

The DPL benchmark lives in this package rather than `benchmarks/`, because
`.claude/settings.json` denies edits under `everlang_standalone/benchmarks/`.
