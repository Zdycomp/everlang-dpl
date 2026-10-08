# Ever Gold Standard Suite

Each .ever file is a source program. Each .expected file is the
canonical output — identical text, identical numbers, identical exit
code — that BOTH execution backends must produce.

Backend A: Python tree-walk interpreter (ever.py)
Backend B: Parser → TAC IR → C interpreter (tac.c ev_interp_*)

If A and B diverge, the harness reports which lines differ and which
backend is wrong.
