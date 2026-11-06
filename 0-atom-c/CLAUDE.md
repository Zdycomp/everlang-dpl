# C runtime landmines (0-atom-c)

**Arena ownership is asymmetric.**

- `ev_module_new(name, arena)` — TAKES the arena. `ev_module_free`
  frees it. Never free it yourself.
- `ev_lower_module(...)` / `ev_lower_form_module(...)` — MINT their own. Your arena still holds the tree and is yours to
  free.

**Pool composites are BY REFERENCE.** INT/REAL/BOOL/TEXT/VOID are inline (by value). BLOB/LIST/RECORD hold a `pool_ref`
index — copying the EValue copies the handle. Use `ev_pool_clear()` for bulk teardown.

**C99 only.** No `strnlen`. No `&ev_int(3)` (not an lvalue) — use named temporaries. `E_INTAKE` needs a local `#ifndef`
guard.
