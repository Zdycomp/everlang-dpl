#!/usr/bin/env python3
"""
emit.py — Ever / Tapestry, transpiler backends.

Ever compiles to Go, Rust, R, and Kotlin. Not four rewrites of the
language — one traversal, four emitters, because the IR is structural
rather than syntactic. Every backend matches the same small set of
shapes; only the spelling differs.

This is the payoff the generic IR was built for. Adding a fifth target
is one class, not a fork.

WHAT CROSSES THE BOUNDARY

Ever's premise is that every value carries a trust level, and that z
(the honest unknown) poisons whatever it touches instead of quietly
becoming a plausible number. None of the target languages have that.
So each backend emits a small runtime shim implementing:

    Val    — a tagged value carrying (kind, number/text/bool, conf)
    z      — the unknown, confidence 0
    binops — that return z whenever either side is z

Without the shim you would get Go that computes 88 where Ever says z,
which is precisely the failure the language exists to prevent. The
shim is small and self-contained; the emitted program is a single
file with no dependencies.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from typing import List, Optional

from syntax import (parse, Program, Let, Show, FnDef, Num, Str, Bool,
                    Var, BinOp, If, Call, ZLit, ListLit, RecordLit,
                    Semantic, Extern)

# Ever's operator set, shared by every backend that spells them the same.
_OPS = {"+": "+", "-": "-", "*": "*", "/": "/",
        "<": "<", ">": ">", "<=": "<=", ">=": ">=",
        "==": "==", "!=": "!="}

_CMP = {"<", ">", "<=", ">=", "==", "!="}


class Emitter:
    """Base: walks the AST, dispatches on shape. Subclasses supply
    spelling. Anything not overridden is a hard error rather than a
    silent omission — a backend that quietly skips a construct is
    worse than one that refuses to compile."""

    ext = "txt"
    name = "base"

    # ── required of every backend ──
    def preamble(self, fns: List[FnDef]) -> str: raise NotImplementedError
    def postamble(self) -> str: raise NotImplementedError
    def fn(self, f: FnDef) -> str: raise NotImplementedError
    _declared: set = None

    def _first_binding(self, name: str) -> bool:
        """True the first time this emit() run binds `name`."""
        if self._declared is None:
            self._declared = set()
        if name in self._declared:
            return False
        self._declared.add(name)
        return True

    def let(self, name: str, expr: str, tracked: bool) -> str: raise NotImplementedError
    def show(self, name: str) -> str: raise NotImplementedError

    def num(self, v) -> str: raise NotImplementedError
    def text(self, v: str) -> str: raise NotImplementedError

    @staticmethod
    def _cstr(v: str, dollar: bool = False) -> str:
        """A double-quoted string literal valid in Go, Rust, JS, Kotlin
        and R.

        Every backend used to interpolate the raw text straight between
        quotes — `f'txt("{v}")'` — so a quote, a backslash or a newline
        in an Ever string emitted code that would not compile. Go was
        worse: it built the literal with `repr()` and then replaced
        every apostrophe with a double quote, so "it's fine" came out
        as "it"s fine".

        `dollar=True` also escapes '$', which Kotlin reads as the start
        of a template expression.
        """
        out = []
        for ch in v:
            if   ch == "\\": out.append("\\\\")
            elif ch == '"':    out.append('\\"')
            elif ch == "\n":  out.append("\\n")
            elif ch == "\r":  out.append("\\r")
            elif ch == "\t":  out.append("\\t")
            elif dollar and ch == "$": out.append("\\$")
            else: out.append(ch)
        return '"' + "".join(out) + '"'
    def boolean(self, v: bool) -> str: raise NotImplementedError
    def zval(self) -> str: raise NotImplementedError
    def var(self, n: str) -> str: raise NotImplementedError
    def binop(self, op: str, l: str, r: str) -> str: raise NotImplementedError
    def cond(self, c: str, t: str, e: str) -> str: raise NotImplementedError
    def call(self, n: str, args: List[str]) -> str: raise NotImplementedError
    def listlit(self, items: List[str]) -> str: raise NotImplementedError
    def reclit(self, keys: List[str], vals: List[str]) -> str: raise NotImplementedError
    def unaryop(self, op: str, operand: str) -> str: raise NotImplementedError
    def logic(self, op: str, left, right) -> str: raise NotImplementedError
    def index(self, target: str, key: str) -> str: raise NotImplementedError
    def field(self, target: str, name: str) -> str: raise NotImplementedError
    def forrange(self, var: str, start: str, end: str,
                step: Optional[str], body) -> str: raise NotImplementedError
    def forin(self, var: str, seq: str, body) -> str: raise NotImplementedError
    def whileloop(self, cond, body) -> str: raise NotImplementedError

    # ── the one traversal ──
    def expr(self, n) -> str:
        t = type(n).__name__
        if t == "Num":   return self.num(n.value)
        if t == "Str":   return self.text(n.value)
        if t == "Bool":  return self.boolean(n.value)
        if t == "ZLit":  return self.zval()
        if t == "Var":   return self.var(n.name)
        if t == "BinOp":
            if n.op in ("and", "or"):
                # Short-circuit, matching the Python evaluator exactly:
                # confidence when short-circuited is the LEFT operand's
                # confidence alone, not min(left,right) — the right
                # side was never actually consulted. Routing "and"/"or"
                # through the generic op() runtime helper (which only
                # ever sees two ALREADY-evaluated values) cannot
                # express that: it silently fell through to a default
                # case and returned z for every and/or expression,
                # with no error at parse, compile, or run time. Fixed
                # by emitting real short-circuiting code instead of a
                # runtime call.
                return self.logic(n.op, n.left, n.right)
            return self.binop(n.op, self.expr(n.left), self.expr(n.right))
        if t == "If":    return self.cond(self.expr(n.cond),
                                          self.expr(n.then),
                                          self.expr(n.els))
        if t == "Call":  return self.call(n.name,
                                          [self.expr(a) for a in n.args])
        if t == "ListLit":
            return self.listlit([self.expr(i) for i in n.items])
        if t == "RecordLit":
            return self.reclit(list(n.keys),
                               [self.expr(v) for v in n.values])
        if t == "UnaryOp":
            return self.unaryop(n.op, self.expr(n.operand))
        if t == "Index":
            return self.index(self.expr(n.target), self.expr(n.key))
        if t == "Field":
            return self.field(self.expr(n.target), n.name)
        if t == "ForRange":
            step = self.expr(n.step) if n.step else None
            return self.forrange(n.var, self.expr(n.start),
                                 self.expr(n.end), step, n.body)
        if t == "ForIn":
            return self.forin(n.var, self.expr(n.seq), n.body)
        if t == "While":
            return self.whileloop(n.cond, n.body)
        raise NotImplementedError(
            f"{self.name} backend cannot emit {t}")

    def emit(self, src: str) -> str:
        node, err = parse(src)
        if err is not None:
            raise ValueError(f"parse error: {err}")
        prog = node if isinstance(node, Program) else Program([node])

        # FFI is a Python-runtime capability (ctypes calling a real
        # loaded C library) with no equivalent wired into any of the
        # four transpiler targets. Silently dropping an `extern`
        # statement here is worse than refusing: the CALL to that
        # name survives into the emitted code, and for a name that
        # happens to already exist as a builtin in the target
        # language (R's own sqrt(), for one) it can appear to work by
        # coincidence — while any other extern fails outright. An
        # explicit refusal here is the only version of this that
        # can't quietly mislead.
        if any(isinstance(s, Extern) for s in prog.statements):
            raise NotImplementedError(
                f"{self.name} backend cannot emit extern/FFI "
                f"declarations — FFI runs through Python's ctypes and "
                f"has no equivalent wired into this target")

        # Ever lets a name be re-bound; Go's `:=`, JS's `const` and
        # Kotlin's `val` each allow it exactly once. Emitting a fresh
        # declaration every time produced code that would not compile
        # ("no new variables on left side of :=",
        # "Identifier 'x' has already been declared"). Backends consult
        # this set to declare once and assign thereafter.
        self._declared = set()

        fns  = [s for s in prog.statements if isinstance(s, FnDef)]
        body: List[str] = []
        for s in prog.statements:
            if isinstance(s, FnDef):
                continue
            if isinstance(s, Let):
                body.append(self.let(s.name, self.expr(s.value), s.tracked))
            elif isinstance(s, Show):
                body.append(self.show(s.name))
        return (self.preamble(fns) + "\n".join(body) + self.postamble())


# ═══════════════════════════════════════════════
# GO
# ═══════════════════════════════════════════════

class GoEmitter(Emitter):
    ext, name = "go", "go"

    def preamble(self, fns):
        f = "\n".join(self.fn(x) for x in fns)
        return '''package main

import (
	"fmt"
	"math"
	"strings"
)

// Ever value: carries a trust level, and z poisons what it touches.
type Val struct {
	Kind string // "num","txt","bool","z","list","rec"
	N    float64
	S    string
	B    bool
	L    []Val
	K    []string
	Conf int
}

func num(f float64) Val  { return Val{Kind: "num", N: f, Conf: 256} }
func txt(s string) Val   { return Val{Kind: "txt", S: s, Conf: 256} }
func bl(b bool) Val      { return Val{Kind: "bool", B: b, Conf: 256} }
func z() Val             { return Val{Kind: "z", Conf: 0} }
func lst(v ...Val) Val {
	c := 256
	for _, x := range v {
		if x.Conf < c { c = x.Conf }
	}
	return Val{Kind: "list", L: v, Conf: c}
}
func rec(k []string, v []Val) Val {
	c := 256
	for _, x := range v {
		if x.Conf < c { c = x.Conf }
	}
	return Val{Kind: "rec", K: k, L: v, Conf: c}
}

func op(o string, a, b Val) Val {
	if a.Kind == "z" || b.Kind == "z" { return z() }
	c := a.Conf
	if b.Conf < c { c = b.Conf }
	// TEXT has exactly one defined operator in the reference: `+`,
	// which concatenates. Everything else used to fall through to the
	// numeric path, where a txt Val's N is 0 — so "ab" + "cd" came out
	// as the number 0, and "ab" == "ab" answered true at full
	// confidence where Ever answers z. Certainty invented out of a
	// type the operator was never defined for.
	bothTxt := a.Kind == "txt" && b.Kind == "txt"
	anyTxt := a.Kind == "txt" || b.Kind == "txt"
	if o == "+" && bothTxt { return Val{Kind: "txt", S: a.S + b.S, Conf: c} }
	if anyTxt { return z() }
	switch o {
	case "+": return Val{Kind: "num", N: a.N + b.N, Conf: c}
	case "-": return Val{Kind: "num", N: a.N - b.N, Conf: c}
	case "*": return Val{Kind: "num", N: a.N * b.N, Conf: c}
	case "/":
		if b.N == 0 { return z() }
		return Val{Kind: "num", N: a.N / b.N, Conf: c}
	case "<":  return Val{Kind: "bool", B: a.N < b.N, Conf: c}
	case ">":  return Val{Kind: "bool", B: a.N > b.N, Conf: c}
	case "<=": return Val{Kind: "bool", B: a.N <= b.N, Conf: c}
	case ">=": return Val{Kind: "bool", B: a.N >= b.N, Conf: c}
	case "==": return Val{Kind: "bool", B: a.N == b.N, Conf: c}
	case "!=": return Val{Kind: "bool", B: a.N != b.N, Conf: c}
	}
	return z()
}

func truthy(v Val) bool { return v.Kind == "bool" && v.B }

// A branch result can never be more certain than the condition that chose it. cond() returned the taken branch untouched, so `if z then 1 else 2` came back 2 at 256/256 where the reference says 2 at 0/256 — confidence manufactured out of an unknown.
func condv(c Val, v Val) Val {
	if v.Kind == "z" { return v }
	cc := c.Conf
	if v.Conf < cc { cc = v.Conf }
	v.Conf = cc
	return v
}

func vexp(a Val) Val {
	if a.Kind == "z" { return z() }
	return Val{Kind: "num", N: math.Exp(a.N), Conf: a.Conf}
}
func vsigmoid(a Val) Val {
	if a.Kind == "z" { return z() }
	return Val{Kind: "num", N: 1.0 / (1.0 + math.Exp(-a.N)), Conf: a.Conf}
}
func vdot(a, b Val) Val {
	if a.Kind != "list" || b.Kind != "list" ||
		len(a.L) != len(b.L) || len(a.L) == 0 {
		return z()
	}
	sum, minc := 0.0, 256
	for i := range a.L {
		if a.L[i].Kind == "z" || b.L[i].Kind == "z" { return z() }
		sum += a.L[i].N * b.L[i].N
		c := a.L[i].Conf
		if b.L[i].Conf < c { c = b.L[i].Conf }
		if c < minc { minc = c }
	}
	return Val{Kind: "num", N: sum, Conf: minc}
}
func vnot(a Val) Val {
	if a.Kind != "bool" { return z() }
	return bl(!a.B)
}
func vindex(lst, idx Val) Val {
	if lst.Kind != "list" || idx.Kind != "num" { return z() }
	i := int(idx.N)
	if i < 0 || i >= len(lst.L) { return z() }
	return lst.L[i]
}
func vfield(rec Val, name string) Val {
	if rec.Kind != "rec" { return z() }
	for i, k := range rec.K {
		if k == name { return rec.L[i] }
	}
	return z()
}
func vmse(p, act Val) Val {
	if p.Kind != "list" || act.Kind != "list" ||
		len(p.L) != len(act.L) || len(p.L) == 0 {
		return z()
	}
	sum, minc := 0.0, 256
	for i := range p.L {
		if p.L[i].Kind == "z" || act.L[i].Kind == "z" { return z() }
		d := p.L[i].N - act.L[i].N
		sum += d * d
		c := p.L[i].Conf
		if act.L[i].Conf < c { c = act.L[i].Conf }
		if c < minc { minc = c }
	}
	return Val{Kind: "num", N: sum / float64(len(p.L)), Conf: minc}
}

func fmtNum(f float64) string {
	if f == float64(int64(f)) { return fmt.Sprintf("%d", int64(f)) }
	return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%.10f", f), "0"), ".")
}

func show(name string, v Val) {
	switch v.Kind {
	case "z":    fmt.Printf("%s = z [0/256]\\n", name)
	case "num":  fmt.Printf("%s = %s [%d/256]\\n", name, fmtNum(v.N), v.Conf)
	case "txt":  fmt.Printf("%s = %q [%d/256]\\n", name, v.S, v.Conf)
	case "bool": fmt.Printf("%s = %t [%d/256]\\n", name, v.B, v.Conf)
	case "list": fmt.Printf("%s = <list %d items> [%d/256]\\n", name, len(v.L), v.Conf)
	case "rec":  fmt.Printf("%s = {%s} [%d/256]\\n", name, strings.Join(v.K, ", "), v.Conf)
	}
}

''' + f + "\nfunc main() {\n"

    def postamble(self): return "}\n"

    def fn(self, f):
        ps = ", ".join(f"{p} Val" for p in f.params)
        return f"func {f.name}({ps}) Val {{\n\treturn {self.expr(f.body)}\n}}\n"

    def let(self, name, expr, tracked):
        if self._first_binding(name):
            return f"\t{name} := {expr}\n\t_ = {name}"
        return f"\t{name} = {expr}\n\t_ = {name}"

    def show(self, name): return f'\tshow("{name}", {name})'
    def num(self, v):     return f"num({float(v)})"
    def text(self, v):    return f"txt({self._cstr(v)})"
    def boolean(self, v): return f"bl({'true' if v else 'false'})"
    def zval(self):       return "z()"
    def var(self, n):     return n
    def binop(self, o, l, r): return f'op("{o}", {l}, {r})'
    def cond(self, c, t, e):
        return (f"func() Val {{ cv := {c}; if truthy(cv) "
                f"{{ return condv(cv, {t}) }}; return condv(cv, {e}) }}()")
    def unaryop(self, op, operand):
        return f"vnot({operand})"
    def logic(self, op, left, right):
        l = self.expr(left); r = self.expr(right)
        want = "false" if op == "and" else "true"
        return (f"func() Val {{ l := {l}; if l.Kind != \"bool\" {{ "
               f"return z() }}; if l.B == {want} {{ return l }}; "
               f"return {r} }}()")
    def index(self, target, key):
        return f"vindex({target}, {key})"
    def field(self, target, name):
        return f'vfield({target}, "{name}")'
    def forrange(self, var, start, end, step, body):
        step_expr = step if step else "num(1.0)"
        has_step = "true" if step else "false"
        body_code = self.expr(body)
        return f'''func() Val {{
		startV := {start}; endV := {end}; stepV := {step_expr}
		if startV.Kind != "num" || endV.Kind != "num" {{ return z() }}
		st := 1.0
		if {has_step} {{
			if stepV.Kind != "num" {{ return z() }}
			st = stepV.N
		}}
		if st == 0 {{ return z() }}
		result := z()
		iv := startV.N
		guard := 0
		for (st > 0 && iv <= endV.N) || (st < 0 && iv >= endV.N) {{
			guard++
			if guard > 1000000 {{ return z() }}
			{var} := num(iv)
			result = {body_code}
			iv += st
		}}
		return result
	}}()'''
    def forin(self, var, seq, body):
        body_code = self.expr(body)
        return f'''func() Val {{
		seqV := {seq}
		if seqV.Kind != "list" {{ return z() }}
		result := z()
		for _, {var} := range seqV.L {{
			result = {body_code}
		}}
		return result
	}}()'''
    def whileloop(self, cond, body):
        cond_code = self.expr(cond)
        body_code = self.expr(body)
        return f'''func() Val {{
		result := z()
		guard := 0
		for {{
			guard++
			if guard > 1000000 {{ return z() }}
			c := {cond_code}
			if c.Kind != "bool" || !c.B {{ break }}
			result = {body_code}
		}}
		return result
	}}()'''
    _ML_BUILTINS = {"sigmoid": "vsigmoid", "exp": "vexp", "dot": "vdot", "mse": "vmse"}
    def call(self, n, a):
        native = self._ML_BUILTINS.get(n)
        if native: return f"{native}({', '.join(a)})"
        return f"{n}({', '.join(a)})"
    def listlit(self, items): return f"lst({', '.join(items)})"
    def reclit(self, keys, vals):
        ks = ", ".join(f'"{k}"' for k in keys)
        return f"rec([]string{{{ks}}}, []Val{{{', '.join(vals)}}})"


# ═══════════════════════════════════════════════
# RUST
# ═══════════════════════════════════════════════

class RustEmitter(Emitter):
    ext, name = "rs", "rust"

    def preamble(self, fns):
        f = "\n".join(self.fn(x) for x in fns)
        return '''#[derive(Clone, Debug)]
pub enum Val {
    Num(f64, i32),
    Txt(String, i32),
    Bool(bool, i32),
    List(Vec<Val>, i32),
    Rec(Vec<String>, Vec<Val>, i32),
    Z,
}

fn conf(v: &Val) -> i32 {
    match v {
        Val::Num(_, c) | Val::Txt(_, c) | Val::Bool(_, c)
        | Val::List(_, c) | Val::Rec(_, _, c) => *c,
        Val::Z => 0,
    }
}

fn numof(v: &Val) -> f64 {
    match v { Val::Num(n, _) => *n, Val::Bool(b, _) => if *b {1.0} else {0.0}, _ => 0.0 }
}

fn lst(items: Vec<Val>) -> Val {
    let c = items.iter().map(conf).min().unwrap_or(256);
    Val::List(items, c)
}

fn rec(k: Vec<String>, v: Vec<Val>) -> Val {
    let c = v.iter().map(conf).min().unwrap_or(256);
    Val::Rec(k, v, c)
}

fn op(o: &str, a: Val, b: Val) -> Val {
    if matches!(a, Val::Z) || matches!(b, Val::Z) { return Val::Z; }
    let c = conf(&a).min(conf(&b));
    // TEXT's only defined operator is `+` (concatenation); every other
    // one used to read numof() == 0.0 and answer with false certainty.
    let both_txt = matches!(a, Val::Txt(..)) && matches!(b, Val::Txt(..));
    let any_txt = matches!(a, Val::Txt(..)) || matches!(b, Val::Txt(..));
    if o == "+" && both_txt {
        if let (Val::Txt(p, _), Val::Txt(q, _)) = (&a, &b) {
            return Val::Txt(format!("{}{}", p, q), c);
        }
    }
    if any_txt { return Val::Z; }
    let (x, y) = (numof(&a), numof(&b));
    match o {
        "+" => Val::Num(x + y, c),
        "-" => Val::Num(x - y, c),
        "*" => Val::Num(x * y, c),
        "/" => if y == 0.0 { Val::Z } else { Val::Num(x / y, c) },
        "<"  => Val::Bool(x <  y, c),
        ">"  => Val::Bool(x >  y, c),
        "<=" => Val::Bool(x <= y, c),
        ">=" => Val::Bool(x >= y, c),
        "==" => Val::Bool(x == y, c),
        "!=" => Val::Bool(x != y, c),
        _ => Val::Z,
    }
}

fn truthy(v: &Val) -> bool { matches!(v, Val::Bool(true, _)) }

// A branch result can never be more certain than the condition that chose it. cond() returned the taken branch untouched, so `if z then 1 else 2` came back 2 at 256/256 where the reference says 2 at 0/256 — confidence manufactured out of an unknown.
fn condv(cc: i32, v: Val) -> Val {
    match v {
        Val::Num(n, c)     => Val::Num(n, c.min(cc)),
        Val::Txt(s, c)     => Val::Txt(s, c.min(cc)),
        Val::Bool(b, c)    => Val::Bool(b, c.min(cc)),
        Val::List(l, c)    => Val::List(l, c.min(cc)),
        Val::Rec(k, w, c)  => Val::Rec(k, w, c.min(cc)),
        Val::Z             => Val::Z,
    }
}

fn vexp(a: Val) -> Val {
    if matches!(a, Val::Z) { return Val::Z; }
    let c = conf(&a);
    Val::Num(numof(&a).exp(), c)
}
fn vsigmoid(a: Val) -> Val {
    if matches!(a, Val::Z) { return Val::Z; }
    let c = conf(&a);
    Val::Num(1.0 / (1.0 + (-numof(&a)).exp()), c)
}
fn vdot(a: Val, b: Val) -> Val {
    match (&a, &b) {
        (Val::List(la, _), Val::List(lb, _))
            if la.len() == lb.len() && !la.is_empty() => {
            let mut sum = 0.0; let mut minc = 256;
            for (x, y) in la.iter().zip(lb.iter()) {
                if matches!(x, Val::Z) || matches!(y, Val::Z) { return Val::Z; }
                sum += numof(x) * numof(y);
                minc = minc.min(conf(x).min(conf(y)));
            }
            Val::Num(sum, minc)
        }
        _ => Val::Z,
    }
}
fn vnot(a: Val) -> Val {
    match a {
        Val::Bool(b, c) => Val::Bool(!b, c),
        _ => Val::Z,
    }
}
fn vindex(lst: Val, idx: Val) -> Val {
    match (&lst, &idx) {
        (Val::List(l, _), Val::Num(n, _)) => {
            let i = *n as i64;
            if i < 0 || i as usize >= l.len() { Val::Z }
            else { l[i as usize].clone() }
        }
        _ => Val::Z,
    }
}
fn vfield(rec: Val, name: &str) -> Val {
    match &rec {
        Val::Rec(k, v, _) => {
            for (i, key) in k.iter().enumerate() {
                if key == name { return v[i].clone(); }
            }
            Val::Z
        }
        _ => Val::Z,
    }
}
fn vmse(p: Val, act: Val) -> Val {
    match (&p, &act) {
        (Val::List(lp, _), Val::List(la, _))
            if lp.len() == la.len() && !lp.is_empty() => {
            let mut sum = 0.0; let mut minc = 256;
            for (x, y) in lp.iter().zip(la.iter()) {
                if matches!(x, Val::Z) || matches!(y, Val::Z) { return Val::Z; }
                let d = numof(x) - numof(y);
                sum += d * d;
                minc = minc.min(conf(x).min(conf(y)));
            }
            Val::Num(sum / (lp.len() as f64), minc)
        }
        _ => Val::Z,
    }
}

fn fmt_num(f: f64) -> String {
    if f == f.trunc() { format!("{}", f as i64) } else { format!("{}", f) }
}

fn show(name: &str, v: &Val) {
    match v {
        Val::Z => println!("{} = z [0/256]", name),
        Val::Num(n, c) => println!("{} = {} [{}/256]", name, fmt_num(*n), c),
        Val::Txt(s, c) => println!("{} = \\"{}\\" [{}/256]", name, s, c),
        Val::Bool(b, c) => println!("{} = {} [{}/256]", name, b, c),
        Val::List(items, c) =>
            println!("{} = <list {} items> [{}/256]", name, items.len(), c),
        Val::Rec(k, _, c) =>
            println!("{} = {{{}}} [{}/256]", name, k.join(", "), c),
    }
}

''' + f + "\nfn main() {\n"

    def postamble(self): return "}\n"

    def fn(self, f):
        ps = ", ".join(f"{p}: Val" for p in f.params)
        return f"fn {f.name}({ps}) -> Val {{\n    {self.expr(f.body)}\n}}\n"

    def let(self, name, expr, tracked):
        return f"    let {name} = {expr};"

    def show(self, name): return f'    show("{name}", &{name});'
    def num(self, v):     return f"Val::Num({float(v)}, 256)"
    def text(self, v):    return f"Val::Txt({self._cstr(v)}.to_string(), 256)"
    def boolean(self, v): return f"Val::Bool({'true' if v else 'false'}, 256)"
    def zval(self):       return "Val::Z"
    def var(self, n):     return f"{n}.clone()"
    def binop(self, o, l, r): return f'op("{o}", {l}, {r})'
    def cond(self, c, t, e):
        return (f"{{ let cv = {c}; let cc = conf(&cv); "
                f"if truthy(&cv) {{ condv(cc, {t}) }} else {{ condv(cc, {e}) }} }}")
    def unaryop(self, op, operand):
        return f"vnot({operand})"
    def logic(self, op, left, right):
        l = self.expr(left); r = self.expr(right)
        want = "false" if op == "and" else "true"
        return (f"{{ let l = {l}; match &l {{ "
               f"Val::Bool({want}, _) => l, "
               f"Val::Bool(_, _) => {r}, "
               f"_ => Val::Z }} }}")
    def index(self, target, key):
        return f"vindex({target}, {key})"
    def field(self, target, name):
        return f'vfield({target}, "{name}")'
    def forrange(self, var, start, end, step, body):
        step_expr = step if step else "Val::Num(1.0, 256)"
        body_code = self.expr(body)
        return f'''{{
        let start_v = {start}; let end_v = {end}; let step_v = {step_expr};
        if !matches!(start_v, Val::Num(_,_)) || !matches!(end_v, Val::Num(_,_))
            || !matches!(step_v, Val::Num(_,_)) {{ Val::Z }}
        else {{
            let sv = numof(&start_v); let ev = numof(&end_v); let st = numof(&step_v);
            if st == 0.0 {{ Val::Z }} else {{
                let mut result = Val::Z;
                let mut iv = sv;
                let mut guard = 0;
                loop {{
                    if !((st > 0.0 && iv <= ev) || (st < 0.0 && iv >= ev)) {{ break; }}
                    guard += 1;
                    if guard > 1_000_000 {{ result = Val::Z; break; }}
                    let {var} = Val::Num(iv, 256);
                    result = {body_code};
                    iv += st;
                }}
                result
            }}
        }}
    }}'''
    def forin(self, var, seq, body):
        body_code = self.expr(body)
        return f'''{{
        let seq_v = {seq};
        match &seq_v {{
            Val::List(items, _) => {{
                let mut result = Val::Z;
                for it in items.iter() {{
                    let {var} = it.clone();
                    result = {body_code};
                }}
                result
            }}
            _ => Val::Z,
        }}
    }}'''
    def whileloop(self, cond, body):
        cond_code = self.expr(cond)
        body_code = self.expr(body)
        return f'''{{
        let mut result = Val::Z;
        let mut guard = 0;
        loop {{
            guard += 1;
            if guard > 1_000_000 {{ result = Val::Z; break; }}
            let c = {cond_code};
            if !matches!(c, Val::Bool(true, _)) {{ break; }}
            result = {body_code};
        }}
        result
    }}'''
    _ML_BUILTINS = {"sigmoid": "vsigmoid", "exp": "vexp", "dot": "vdot", "mse": "vmse"}
    def call(self, n, a):
        native = self._ML_BUILTINS.get(n)
        if native: return f"{native}({', '.join(a)})"
        return f"{n}({', '.join(a)})"
    def listlit(self, items): return f"lst(vec![{', '.join(items)}])"
    def reclit(self, keys, vals):
        ks = ", ".join(f'"{k}".to_string()' for k in keys)
        return f"rec(vec![{ks}], vec![{', '.join(vals)}])"


# ═══════════════════════════════════════════════
# R
# ═══════════════════════════════════════════════

class REmitter(Emitter):
    ext, name = "R", "r"

    def preamble(self, fns):
        f = "\n".join(self.fn(x) for x in fns)
        return '''# Ever -> R
mkval <- function(kind, n=0, s="", b=FALSE, items=list(), keys=character(0), conf=256)
  list(kind=kind, n=n, s=s, b=b, items=items, keys=keys, conf=conf)

num <- function(x) mkval("num", n=x)
txt <- function(x) mkval("txt", s=x)
bl  <- function(x) mkval("bool", b=x)
zz  <- function()  mkval("z", conf=0)

lst <- function(...) {
  it <- list(...)
  c0 <- if (length(it) == 0) 256 else min(sapply(it, function(v) v$conf))
  mkval("list", items=it, conf=c0)
}

recv <- function(keys, ...) {
  it <- list(...)
  c0 <- if (length(it) == 0) 256 else min(sapply(it, function(v) v$conf))
  mkval("rec", items=it, keys=keys, conf=c0)
}

op <- function(o, a, b) {
  if (a$kind == "z" || b$kind == "z") return(zz())
  cf <- min(a$conf, b$conf)
  # TEXT's only defined operator is `+`; every other one read a$n,
  # which is 0 for a txt, and answered with invented certainty.
  if (o == "+" && a$kind == "txt" && b$kind == "txt")
    return(mkval("txt", s=paste0(a$s, b$s), conf=cf))
  if (a$kind == "txt" || b$kind == "txt") return(zz())
  x <- a$n; y <- b$n
  if (o == "+") return(mkval("num", n=x+y, conf=cf))
  if (o == "-") return(mkval("num", n=x-y, conf=cf))
  if (o == "*") return(mkval("num", n=x*y, conf=cf))
  if (o == "/") { if (y == 0) return(zz()); return(mkval("num", n=x/y, conf=cf)) }
  if (o == "<")  return(mkval("bool", b=(x <  y), conf=cf))
  if (o == ">")  return(mkval("bool", b=(x >  y), conf=cf))
  if (o == "<=") return(mkval("bool", b=(x <= y), conf=cf))
  if (o == ">=") return(mkval("bool", b=(x >= y), conf=cf))
  if (o == "==") return(mkval("bool", b=(x==y), conf=cf))
  if (o == "!=") return(mkval("bool", b=(x!=y), conf=cf))
  zz()
}

truthy <- function(v) v$kind == "bool" && v$b

# A branch result can never be more certain than the condition that chose it.
condv <- function(cv, v) {
  if (v$kind == "z") return(v)
  v$conf <- min(cv$conf, v$conf)
  v
}

vexp <- function(a) {
  if (a$kind == "z") return(zz())
  mkval("num", n=exp(a$n), conf=a$conf)
}
vsigmoid <- function(a) {
  if (a$kind == "z") return(zz())
  mkval("num", n=1/(1+exp(-a$n)), conf=a$conf)
}
vdot <- function(a, b) {
  if (a$kind != "list" || b$kind != "list" ||
      length(a$items) != length(b$items) || length(a$items) == 0) return(zz())
  s <- 0; mc <- 256
  for (i in seq_along(a$items)) {
    if (a$items[[i]]$kind == "z" || b$items[[i]]$kind == "z") return(zz())
    s <- s + a$items[[i]]$n * b$items[[i]]$n
    mc <- min(mc, a$items[[i]]$conf, b$items[[i]]$conf)
  }
  mkval("num", n=s, conf=mc)
}
vnot <- function(a) {
  if (a$kind != "bool") return(zz())
  bl(!a$b)
}
vindex <- function(lst, idx) {
  if (lst$kind != "list" || idx$kind != "num") return(zz())
  i <- as.integer(idx$n)
  # R lists are 1-indexed; Ever's are 0-indexed
  if (i < 0 || i >= length(lst$items)) return(zz())
  lst$items[[i + 1]]
}
vfield <- function(rec, name) {
  if (rec$kind != "rec") return(zz())
  for (i in seq_along(rec$keys)) {
    if (rec$keys[i] == name) return(rec$items[[i]])
  }
  zz()
}
vmse <- function(p, act) {
  if (p$kind != "list" || act$kind != "list" ||
      length(p$items) != length(act$items) || length(p$items) == 0) return(zz())
  s <- 0; mc <- 256
  for (i in seq_along(p$items)) {
    if (p$items[[i]]$kind == "z" || act$items[[i]]$kind == "z") return(zz())
    d <- p$items[[i]]$n - act$items[[i]]$n
    s <- s + d * d
    mc <- min(mc, p$items[[i]]$conf, act$items[[i]]$conf)
  }
  mkval("num", n=s/length(p$items), conf=mc)
}

fmtnum <- function(x) if (x == round(x)) format(as.integer(x)) else format(x)

show_val <- function(name, v) {
  if (v$kind == "z")    cat(sprintf("%s = z [0/256]\\n", name))
  else if (v$kind == "num")  cat(sprintf("%s = %s [%d/256]\\n", name, fmtnum(v$n), v$conf))
  else if (v$kind == "txt")  cat(sprintf('%s = "%s" [%d/256]\\n', name, v$s, v$conf))
  else if (v$kind == "bool") cat(sprintf("%s = %s [%d/256]\\n", name,
                                   if (v$b) "true" else "false", v$conf))
  else if (v$kind == "list") cat(sprintf("%s = <list %d items> [%d/256]\\n", name,
                                   length(v$items), v$conf))
  else if (v$kind == "rec")  cat(sprintf("%s = {%s} [%d/256]\\n", name,
                                   paste(v$keys, collapse=", "), v$conf))
}

''' + f + "\n"

    def postamble(self): return "\n"

    def fn(self, f):
        ps = ", ".join(f.params)
        return f"{f.name} <- function({ps}) {{\n  {self.expr(f.body)}\n}}\n"

    def let(self, name, expr, tracked): return f"{name} <- {expr}"
    def show(self, name):  return f'show_val("{name}", {name})'
    def num(self, v):      return f"num({float(v)})"
    def text(self, v):     return f"txt({self._cstr(v)})"
    def boolean(self, v):  return f"bl({'TRUE' if v else 'FALSE'})"
    def zval(self):        return "zz()"
    def var(self, n):      return n
    def binop(self, o, l, r): return f'op("{o}", {l}, {r})'
    def cond(self, c, t, e):
        return (f"(function() {{ cv <- {c}; "
                f"if (truthy(cv)) condv(cv, {t}) else condv(cv, {e}) }})()")
    def unaryop(self, op, operand):
        return f"vnot({operand})"
    def logic(self, op, left, right):
        l = self.expr(left); r = self.expr(right)
        want = "FALSE" if op == "and" else "TRUE"
        return (f'(function() {{ l <- {l}; '
               f'if (l$kind != "bool") return(zz()); '
               f'if (l$b == {want}) return(l); '
               f'{r} }})()')
    def index(self, target, key):
        return f"vindex({target}, {key})"
    def field(self, target, name):
        return f'vfield({target}, "{name}")'
    def forrange(self, var, start, end, step, body):
        step_expr = step if step else "num(1.0)"
        body_code = self.expr(body)
        return f'''(function() {{
  start_v <- {start}; end_v <- {end}; step_v <- {step_expr}
  if (start_v$kind != "num" || end_v$kind != "num" || step_v$kind != "num")
    return(zz())
  st <- step_v$n
  if (st == 0) return(zz())
  result <- zz()
  iv <- start_v$n
  guard <- 0
  while ((st > 0 && iv <= end_v$n) || (st < 0 && iv >= end_v$n)) {{
    guard <- guard + 1
    if (guard > 1000000) return(zz())
    {var} <- num(iv)
    result <- {body_code}
    iv <- iv + st
  }}
  result
}})()'''
    def forin(self, var, seq, body):
        body_code = self.expr(body)
        return f'''(function() {{
  seq_v <- {seq}
  if (seq_v$kind != "list") return(zz())
  result <- zz()
  for ({var} in seq_v$items) {{
    result <- {body_code}
  }}
  result
}})()'''
    def whileloop(self, cond, body):
        cond_code = self.expr(cond)
        body_code = self.expr(body)
        return f'''(function() {{
  result <- zz()
  guard <- 0
  repeat {{
    guard <- guard + 1
    if (guard > 1000000) return(zz())
    c <- {cond_code}
    if (c$kind != "bool" || !c$b) break
    result <- {body_code}
  }}
  result
}})()'''
    _ML_BUILTINS = {"sigmoid": "vsigmoid", "exp": "vexp", "dot": "vdot", "mse": "vmse"}
    def call(self, n, a):
        native = self._ML_BUILTINS.get(n)
        if native: return f"{native}({', '.join(a)})"
        return f"{n}({', '.join(a)})"
    def listlit(self, items): return f"lst({', '.join(items)})"
    def reclit(self, keys, vals):
        ks = ", ".join(f'"{k}"' for k in keys)
        return f"recv(c({ks}), {', '.join(vals)})" if vals else "recv(character(0))"


# ═══════════════════════════════════════════════
# KOTLIN
# ═══════════════════════════════════════════════

class KotlinEmitter(Emitter):
    ext, name = "kt", "kotlin"

    def preamble(self, fns):
        f = "\n".join(self.fn(x) for x in fns)
        return '''sealed class Val {
    abstract val conf: Int
    data class Num(val n: Double, override val conf: Int = 256) : Val()
    data class Txt(val s: String, override val conf: Int = 256) : Val()
    data class Bool(val b: Boolean, override val conf: Int = 256) : Val()
    data class Lst(val items: List<Val>, override val conf: Int = 256) : Val()
    data class Rec(val keys: List<String>, val vals: List<Val>,
                   override val conf: Int = 256) : Val()
    object Z : Val() { override val conf: Int = 0 }
}

fun num(x: Double) = Val.Num(x)
fun txt(x: String) = Val.Txt(x)
fun bl(x: Boolean) = Val.Bool(x)
fun z(): Val = Val.Z

fun lst(vararg v: Val): Val =
    Val.Lst(v.toList(), v.minOfOrNull { it.conf } ?: 256)

fun rec(keys: List<String>, vararg v: Val): Val =
    Val.Rec(keys, v.toList(), v.minOfOrNull { it.conf } ?: 256)

fun numOf(v: Val): Double = when (v) {
    is Val.Num -> v.n
    is Val.Bool -> if (v.b) 1.0 else 0.0
    else -> 0.0
}

fun op(o: String, a: Val, b: Val): Val {
    if (a is Val.Z || b is Val.Z) return Val.Z
    val c = minOf(a.conf, b.conf)
    // TEXT's only defined operator is `+`; the rest read numOf() == 0.0
    // and answered with certainty Ever never granted.
    if (o == "+" && a is Val.Txt && b is Val.Txt) return Val.Txt(a.s + b.s, c)
    if (a is Val.Txt || b is Val.Txt) return Val.Z
    val x = numOf(a); val y = numOf(b)
    return when (o) {
        "+" -> Val.Num(x + y, c)
        "-" -> Val.Num(x - y, c)
        "*" -> Val.Num(x * y, c)
        "/" -> if (y == 0.0) Val.Z else Val.Num(x / y, c)
        "<"  -> Val.Bool(x <  y, c)
        ">"  -> Val.Bool(x >  y, c)
        "<=" -> Val.Bool(x <= y, c)
        ">=" -> Val.Bool(x >= y, c)
        "==" -> Val.Bool(x == y, c)
        "!=" -> Val.Bool(x != y, c)
        else -> Val.Z
    }
}

fun truthy(v: Val): Boolean = v is Val.Bool && v.b

// A branch result can never be more certain than the condition that chose it.
fun condv(cc: Int, v: Val): Val = when (v) {
    is Val.Num  -> Val.Num(v.n, minOf(v.conf, cc))
    is Val.Txt  -> Val.Txt(v.s, minOf(v.conf, cc))
    is Val.Bool -> Val.Bool(v.b, minOf(v.conf, cc))
    is Val.Lst  -> Val.Lst(v.items, minOf(v.conf, cc))
    is Val.Rec  -> Val.Rec(v.keys, v.vals, minOf(v.conf, cc))
    is Val.Z    -> Val.Z
}

fun vexp(a: Val): Val {
    if (a is Val.Z) return Val.Z
    return Val.Num(Math.exp(numOf(a)), a.conf)
}
fun vsigmoid(a: Val): Val {
    if (a is Val.Z) return Val.Z
    return Val.Num(1.0 / (1.0 + Math.exp(-numOf(a))), a.conf)
}
fun vdot(a: Val, b: Val): Val {
    if (a !is Val.Lst || b !is Val.Lst ||
        a.items.size != b.items.size || a.items.isEmpty()) return Val.Z
    var sum = 0.0; var minc = 256
    for (i in a.items.indices) {
        val x = a.items[i]; val y = b.items[i]
        if (x is Val.Z || y is Val.Z) return Val.Z
        sum += numOf(x) * numOf(y)
        minc = minOf(minc, x.conf, y.conf)
    }
    return Val.Num(sum, minc)
}
fun vnot(a: Val): Val {
    if (a !is Val.Bool) return Val.Z
    return Val.Bool(!a.b)
}
fun vindex(lst: Val, idx: Val): Val {
    if (lst !is Val.Lst || idx !is Val.Num) return Val.Z
    val i = idx.n.toInt()
    if (i < 0 || i >= lst.items.size) return Val.Z
    return lst.items[i]
}
fun vfield(rec: Val, name: String): Val {
    if (rec !is Val.Rec) return Val.Z
    val i = rec.keys.indexOf(name)
    if (i < 0) return Val.Z
    return rec.vals[i]
}
fun vmse(p: Val, act: Val): Val {
    if (p !is Val.Lst || act !is Val.Lst ||
        p.items.size != act.items.size || p.items.isEmpty()) return Val.Z
    var sum = 0.0; var minc = 256
    for (i in p.items.indices) {
        val x = p.items[i]; val y = act.items[i]
        if (x is Val.Z || y is Val.Z) return Val.Z
        val d = numOf(x) - numOf(y)
        sum += d * d
        minc = minOf(minc, x.conf, y.conf)
    }
    return Val.Num(sum / p.items.size, minc)
}

fun fmtNum(d: Double): String =
    if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString() else d.toString()

fun show(name: String, v: Val) {
    when (v) {
        is Val.Z -> println("$name = z [0/256]")
        is Val.Num -> println("$name = ${fmtNum(v.n)} [${v.conf}/256]")
        is Val.Txt -> println("$name = \\"${v.s}\\" [${v.conf}/256]")
        is Val.Bool -> println("$name = ${v.b} [${v.conf}/256]")
        is Val.Lst -> println("$name = <list ${v.items.size} items> [${v.conf}/256]")
        is Val.Rec -> println("$name = {${v.keys.joinToString(", ")}} [${v.conf}/256]")
    }
}

''' + f + "\nfun main() {\n"

    def postamble(self): return "}\n"

    def fn(self, f):
        ps = ", ".join(f"{p}: Val" for p in f.params)
        return f"fun {f.name}({ps}): Val =\n    {self.expr(f.body)}\n"

    def let(self, name, expr, tracked):
        if self._first_binding(name):
            return f"    var {name} = {expr}"
        return f"    {name} = {expr}"
    def show(self, name):  return f'    show("{name}", {name})'
    def num(self, v):      return f"num({float(v)})"
    def text(self, v):     return f"txt({self._cstr(v, dollar=True)})"
    def boolean(self, v):  return f"bl({'true' if v else 'false'})"
    def zval(self):        return "z()"
    def var(self, n):      return n
    def binop(self, o, l, r): return f'op("{o}", {l}, {r})'
    def cond(self, c, t, e):
        return (f"run {{ val cv = {c}; val cc = cv.conf; "
                f"if (truthy(cv)) condv(cc, {t}) else condv(cc, {e}) }}")
    def unaryop(self, op, operand):
        return f"vnot({operand})"
    def logic(self, op, left, right):
        l = self.expr(left); r = self.expr(right)
        want = "false" if op == "and" else "true"
        return (f"run {{ val l = {l}; "
               f"if (l !is Val.Bool) Val.Z "
               f"else if (l.b == {want}) l "
               f"else {r} }}")
    def index(self, target, key):
        return f"vindex({target}, {key})"
    def field(self, target, name):
        return f'vfield({target}, "{name}")'
    def forrange(self, var, start, end, step, body):
        step_expr = step if step else "num(1.0)"
        body_code = self.expr(body)
        return f'''run {{
        val startV = {start}; val endV = {end}; val stepV = {step_expr}
        if (startV !is Val.Num || endV !is Val.Num || stepV !is Val.Num) Val.Z
        else {{
            val st = stepV.n
            if (st == 0.0) Val.Z else {{
                var result: Val = Val.Z
                var iv = startV.n
                var guard = 0
                while ((st > 0.0 && iv <= endV.n) || (st < 0.0 && iv >= endV.n)) {{
                    guard++
                    if (guard > 1_000_000) {{ result = Val.Z; break }}
                    val {var} = Val.Num(iv)
                    result = {body_code}
                    iv += st
                }}
                result
            }}
        }}
    }}'''
    def forin(self, var, seq, body):
        body_code = self.expr(body)
        return f'''run {{
        val seqV = {seq}
        if (seqV !is Val.Lst) Val.Z
        else {{
            var result: Val = Val.Z
            for ({var} in seqV.items) {{
                result = {body_code}
            }}
            result
        }}
    }}'''
    def whileloop(self, cond, body):
        cond_code = self.expr(cond)
        body_code = self.expr(body)
        return f'''run {{
        var result: Val = Val.Z
        var guard = 0
        while (true) {{
            guard++
            if (guard > 1_000_000) {{ result = Val.Z; break }}
            val c = {cond_code}
            if (c !is Val.Bool || !c.b) break
            result = {body_code}
        }}
        result
    }}'''
    _ML_BUILTINS = {"sigmoid": "vsigmoid", "exp": "vexp", "dot": "vdot", "mse": "vmse"}
    def call(self, n, a):
        native = self._ML_BUILTINS.get(n)
        if native: return f"{native}({', '.join(a)})"
        return f"{n}({', '.join(a)})"
    def listlit(self, items): return f"lst({', '.join(items)})"
    def reclit(self, keys, vals):
        ks = ", ".join(f'"{k}"' for k in keys)
        return f"rec(listOf({ks}){', ' + ', '.join(vals) if vals else ''})"


# ═══════════════════════════════════════════════
# JAVASCRIPT
# ═══════════════════════════════════════════════

class JSEmitter(Emitter):
    ext, name = "js", "javascript"

    def preamble(self, fns):
        f = "\n".join(self.fn(x) for x in fns)
        return '''// Ever value: carries a trust level, and z poisons what it touches.
function num(n) { return {kind: "num", n: n, conf: 256}; }
function txt(s)  { return {kind: "txt", s: s, conf: 256}; }
function bl(b)   { return {kind: "bool", b: b, conf: 256}; }
function z()     { return {kind: "z", conf: 0}; }
function lst(...items) {
    let c = 256;
    for (const x of items) if (x.conf < c) c = x.conf;
    return {kind: "list", items: items, conf: c};
}
function rec(keys, vals) {
    let c = 256;
    for (const x of vals) if (x.conf < c) c = x.conf;
    return {kind: "rec", keys: keys, items: vals, conf: c};
}

function op(o, a, b) {
    if (a.kind === "z" || b.kind === "z") return z();
    // text has no defined operator but '+', and comparing two txt
    // values answered true/false where the reference answers z
    if (o !== "+" && (a.kind === "txt" || b.kind === "txt")) return z();
    const c = Math.min(a.conf, b.conf);
    switch (o) {
        case "+":
            // TEXT's only defined operator. Falling through to the
            // numeric path gave "ab" + "cd" === NaN at 256/256.
            if (a.kind === "txt" && b.kind === "txt")
                return {kind: "txt", s: a.s + b.s, conf: c};
            return {kind: "num", n: a.n + b.n, conf: c};
        case "-": return {kind: "num", n: a.n - b.n, conf: c};
        case "*": return {kind: "num", n: a.n * b.n, conf: c};
        case "/":
            if (b.n === 0) return z();
            return {kind: "num", n: a.n / b.n, conf: c};
        case "<":  return {kind: "bool", b: a.n <  b.n, conf: c};
        case ">":  return {kind: "bool", b: a.n >  b.n, conf: c};
        case "<=": return {kind: "bool", b: a.n <= b.n, conf: c};
        case ">=": return {kind: "bool", b: a.n >= b.n, conf: c};
        case "==": return {kind: "bool", b: a.n === b.n, conf: c};
        case "!=": return {kind: "bool", b: a.n !== b.n, conf: c};
    }
    return z();
}

function truthy(v) { return v.kind === "bool" && v.b; }

// A branch result can never be more certain than the condition that chose it. cond() returned the taken branch untouched, so `if z then 1 else 2` came back 2 at 256/256 where the reference says 2 at 0/256 — confidence manufactured out of an unknown.
function condv(c, v) {
    if (v.kind === "z") return v;
    return Object.assign({}, v, {conf: Math.min(c.conf, v.conf)});
}

function vexp(a) {
    if (a.kind === "z") return z();
    return {kind: "num", n: Math.exp(a.n), conf: a.conf};
}
function vsigmoid(a) {
    if (a.kind === "z") return z();
    return {kind: "num", n: 1 / (1 + Math.exp(-a.n)), conf: a.conf};
}
function vdot(a, b) {
    if (a.kind !== "list" || b.kind !== "list" ||
        a.items.length !== b.items.length || a.items.length === 0) return z();
    let sum = 0, minc = 256;
    for (let i = 0; i < a.items.length; i++) {
        if (a.items[i].kind === "z" || b.items[i].kind === "z") return z();
        sum += a.items[i].n * b.items[i].n;
        minc = Math.min(minc, a.items[i].conf, b.items[i].conf);
    }
    return {kind: "num", n: sum, conf: minc};
}
function vmse(p, act) {
    if (p.kind !== "list" || act.kind !== "list" ||
        p.items.length !== act.items.length || p.items.length === 0) return z();
    let sum = 0, minc = 256;
    for (let i = 0; i < p.items.length; i++) {
        if (p.items[i].kind === "z" || act.items[i].kind === "z") return z();
        const d = p.items[i].n - act.items[i].n;
        sum += d * d;
        minc = Math.min(minc, p.items[i].conf, act.items[i].conf);
    }
    return {kind: "num", n: sum / p.items.length, conf: minc};
}
function vnot(a) {
    if (a.kind !== "bool") return z();
    return {kind: "bool", b: !a.b, conf: a.conf};
}
function vindex(lst, idx) {
    if (lst.kind !== "list" || idx.kind !== "num") return z();
    const i = Math.trunc(idx.n);
    if (i < 0 || i >= lst.items.length) return z();
    return lst.items[i];
}
function vfield(rec, name) {
    if (rec.kind !== "rec") return z();
    const i = rec.keys.indexOf(name);
    if (i < 0) return z();
    return rec.items[i];
}

function show(name, v) {
    if (v.kind === "z")    console.log(`${name} = z [0/256]`);
    else if (v.kind === "num")  console.log(`${name} = ${v.n} [${v.conf}/256]`);
    else if (v.kind === "txt")  console.log(`${name} = "${v.s}" [${v.conf}/256]`);
    else if (v.kind === "bool") console.log(`${name} = ${v.b} [${v.conf}/256]`);
    else if (v.kind === "list") console.log(`${name} = <list ${v.items.length} items> [${v.conf}/256]`);
    else if (v.kind === "rec")  console.log(`${name} = {${v.keys.join(", ")}} [${v.conf}/256]`);
}

''' + f + "\n"

    def postamble(self): return "\n"

    def fn(self, f):
        ps = ", ".join(f.params)
        return f"function {f.name}({ps}) {{\n  return {self.expr(f.body)};\n}}\n"

    def let(self, name, expr, tracked):
        if self._first_binding(name):
            return f"let {name} = {expr};"
        return f"{name} = {expr};"

    def show(self, name): return f'show("{name}", {name});'
    def num(self, v):     return f"num({float(v)})"
    def text(self, v):    return f"txt({self._cstr(v)})"
    def boolean(self, v): return f"bl({'true' if v else 'false'})"
    def zval(self):       return "z()"
    def var(self, n):     return n
    def binop(self, o, l, r): return f'op("{o}", {l}, {r})'
    def cond(self, c, t, e):
        return (f"(function() {{ const cv = {c}; "
                f"return truthy(cv) ? condv(cv, {t}) : condv(cv, {e}); }})()")
    def unaryop(self, op, operand):
        return f"vnot({operand})"
    def logic(self, op, left, right):
        l = self.expr(left); r = self.expr(right)
        want = "false" if op == "and" else "true"
        return (f'(function() {{ const l = {l}; '
               f'if (l.kind !== "bool") return z(); '
               f'if (l.b === {want}) return l; '
               f'return {r}; }})()')
    def index(self, target, key):
        return f"vindex({target}, {key})"
    def field(self, target, name):
        return f'vfield({target}, "{name}")'
    def forrange(self, var, start, end, step, body):
        step_expr = step if step else "num(1.0)"
        body_code = self.expr(body)
        return f'''(function() {{
    const startV = {start}, endV = {end}, stepV = {step_expr};
    if (startV.kind !== "num" || endV.kind !== "num" || stepV.kind !== "num") return z();
    const st = stepV.n;
    if (st === 0) return z();
    let result = z();
    let iv = startV.n;
    let guard = 0;
    while ((st > 0 && iv <= endV.n) || (st < 0 && iv >= endV.n)) {{
        guard++;
        if (guard > 1000000) return z();
        const {var} = num(iv);
        result = {body_code};
        iv += st;
    }}
    return result;
}})()'''
    def forin(self, var, seq, body):
        body_code = self.expr(body)
        return f'''(function() {{
    const seqV = {seq};
    if (seqV.kind !== "list") return z();
    let result = z();
    for (const {var} of seqV.items) {{
        result = {body_code};
    }}
    return result;
}})()'''
    def whileloop(self, cond, body):
        cond_code = self.expr(cond)
        body_code = self.expr(body)
        return f'''(function() {{
    let result = z();
    let guard = 0;
    while (true) {{
        guard++;
        if (guard > 1000000) return z();
        const c = {cond_code};
        if (c.kind !== "bool" || !c.b) break;
        result = {body_code};
    }}
    return result;
}})()'''
    _ML_BUILTINS = {"sigmoid": "vsigmoid", "exp": "vexp", "dot": "vdot", "mse": "vmse"}
    def call(self, n, a):
        native = self._ML_BUILTINS.get(n)
        if native: return f"{native}({', '.join(a)})"
        return f"{n}({', '.join(a)})"
    def listlit(self, items): return f"lst({', '.join(items)})"
    def reclit(self, keys, vals):
        ks = ", ".join(f'"{k}"' for k in keys)
        return f"rec([{ks}], [{', '.join(vals)}])"


BACKENDS = {
    "go":     GoEmitter,
    "rust":   RustEmitter,
    "r":      REmitter,
    "kotlin": KotlinEmitter,
    "js":     JSEmitter,
}


def emit(source: str, target: str) -> str:
    if target not in BACKENDS:
        raise ValueError(f"unknown target {target!r}; "
                         f"have {', '.join(sorted(BACKENDS))}")
    return BACKENDS[target]().emit(source)
