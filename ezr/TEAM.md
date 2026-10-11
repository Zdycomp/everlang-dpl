# Running the Ever dev team

## One-time setup

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
cd tapestry
claude
```

Needs Claude Code v2.1.32 or later. Agent Teams is experimental and off
by default, which is what that env var turns on.

## The split

| Agent | Owns | Never touches |
|---|---|---|
| `c-runtime` | tapestry.c, evalue.c, ir.c, scope.c | tac/form, Python |
| `tac-optimizer` | form.c, form_lower.c, tac.c | atom/value layer |
| `python-frontend` | syntax.py, ir.py, scope.py, runtime.py, ever_cli.py | all C |
| `test-engineer` | all test suites, integration programs | source outside tests |
| `memory-safety` | ASAN/UBSan sweeps | library fixes (reports them) |
| `reviewer` | verification only | writes no code |
| `docs-examples` | README, CLAUDE.md, examples/*.ever | source |

Seven agents, no two owning the same file. That's deliberate — parallel
agents editing one file is where multi-agent work falls apart.

## Launching

Just describe the job. The lead splits it.

```
Add list and record literals to the language: [a,b] and {k:v}.
Use the team.
```

Expected flow: `python-frontend` does the grammar, `tac-optimizer` does
the lowering (AGGREGATE and ACCESS forms already exist, so no new form
kinds), `test-engineer` adds coverage, `memory-safety` sweeps,
`reviewer` signs off.

To be explicit about parallelism, say the number:

```
Use three agents in parallel: one per layer.
```

## Worktrees

For agents that would otherwise collide on the same files:

```bash
git worktree add ../ever-frontend -b feat/frontend
git worktree add ../ever-runtime  -b feat/runtime
```

Each agent gets its own checkout. Merge when green.

## Definition of done

No task is complete until `reviewer` confirms:

- `python3 tests/run_all.py` → 25 passed, 0 failed
- `python3 tests/ev_integrate.py` → 11/11 GOLD, both backends
- three C suites → 1082 assertions, 0 failed
- ASAN → zero errors, zero leaks

Partial work reported as complete is the one failure mode that costs
more than the bug it hid.
