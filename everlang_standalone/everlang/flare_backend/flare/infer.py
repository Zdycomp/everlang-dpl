"""Whole-program type inference for Flare v0.

Types: i64 f64 bool str range dyn void, plus ("list", T) and ("dict", V)
(string-keyed dict with homogeneous value type V).
Constraint-based with join lattice; iterates to a fixpoint so recursion and
forward references work. Anything unresolved becomes dyn (boxed Value in C).
Every expression node gets .inferred; Assign gets .target_type; For gets .var_type.
"""

from flare import nodes as N

I64, F64, BOOL, STR, RANGE, DYN, VOID = "i64", "f64", "bool", "str", "range", "dyn", "void"


def list_t(t):
    return ("list", t)


def is_list(t):
    return isinstance(t, tuple) and len(t) == 2 and t[0] == "list"


def dict_t(t):
    return ("dict", t)


def is_dict(t):
    return isinstance(t, tuple) and len(t) == 2 and t[0] == "dict"


def is_container(t):
    return is_list(t) or is_dict(t)


def closure_t(qname):
    return ("closure", qname)


def is_class(t):
    return isinstance(t, tuple) and len(t) == 2 and t[0] == "class"


def class_t(cname):
    return ("class", cname)


def is_closure(t):
    return isinstance(t, tuple) and len(t) == 2 and t[0] == "closure"


def join(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    if is_list(a) and is_list(b):
        return ("list", join(a[1], b[1]))
    if is_dict(a) and is_dict(b):
        return ("dict", join(a[1], b[1]))
    if a in (I64, F64) and b in (I64, F64):
        return F64
    return DYN


BUILTINS = {
    "print", "len", "range", "append", "list",
    # stdlib: math
    "sqrt", "pow", "abs", "floor", "ceil", "sin", "cos", "tan", "exp", "log",
    # stdlib: strings
    "split", "join", "upper", "lower", "strip", "replace", "find",
    "startswith", "endswith",
    # stdlib: lists
    "sort", "reverse", "sum", "min", "max",
    "enumerate", "zip", "map", "filter", "any", "all", "sorted", "reversed",
    # stdlib: files
    "read_file", "write_file", "file_lines",
    # stdlib: time & random & sys
    "now", "sleep", "rand", "randint", "seed", "argv", "exit",
}

# builtin constants
CONSTANTS = {"PI": F64, "E": F64}

# exception types catchable by `except Name`
KNOWN_EXCEPTIONS = {
    "Exception", "BaseException",
    "ZeroDivisionError", "IndexError", "KeyError", "ValueError",
    "TypeError", "RuntimeError", "RecursionError", "OSError",
}


class CompileError(Exception):
    pass


class Inferer:
    def __init__(self, program):
        self.program = program
        self.funcs = {}
        self.classes = {}  # cname -> {"methods": {mname: finfo}, "attrs": {}}
        self.global_names = set()
        self.globals = {}
        for s in program.stmts:
            if not isinstance(s, (N.FuncDef, N.ClassDef)):
                self._collect_global_names(s)
        self._collect_defs(program.stmts, None)
        self.changed = False

    def _collect_defs(self, stmts, func_parent_qn):
        # func_parent_qn: qname of the enclosing function, or None at top
        # level. A def inside top-level control flow is a plain top-level
        # function (it can only see globals); a def inside a function body
        # (at any control-flow nesting) is a nested closure.
        for s in stmts:
            if isinstance(s, N.ClassDef):
                if func_parent_qn is not None:
                    raise CompileError("line %d: classes cannot be defined inside functions"
                                       % s.line)
                if s.name in self.classes:
                    raise CompileError("line %d: duplicate class '%s'"
                                       % (s.line, s.name))
                if s.name in BUILTINS:
                    raise CompileError("line %d: cannot redefine builtin '%s'"
                                       % (s.line, s.name))
                self.classes[s.name] = {"methods": {}, "attrs": {}, "node": s}
                for m in s.methods:
                    qn = s.name + "__" + m.name
                    if m.name in self.classes[s.name]["methods"]:
                        raise CompileError("line %d: duplicate method '%s'"
                                           % (m.line, m.name))
                    m.qualname = qn
                    finfo = self._new_finfo(m, None)
                    finfo["is_method"] = True
                    finfo["class"] = s.name
                    self.funcs[qn] = finfo
                    self.classes[s.name]["methods"][m.name] = finfo
                # methods don't nest further for v0 (no classes in methods)
            elif isinstance(s, N.FuncDef):
                if func_parent_qn is None and s.name in BUILTINS:
                    raise CompileError("line %d: cannot redefine builtin '%s'"
                                       % (s.line, s.name))
                nested = func_parent_qn is not None
                qn = (func_parent_qn + "__" + s.name) if nested else s.name
                if qn in self.funcs:
                    raise CompileError("line %d: duplicate function '%s'"
                                       % (s.line, s.name))
                s.qualname = qn
                self.funcs[qn] = self._new_finfo(
                    s, func_parent_qn if nested else None)
                self._collect_defs(s.body, qn)
            elif isinstance(s, (N.For, N.While)):
                self._collect_defs(s.body, func_parent_qn)
            elif isinstance(s, N.If):
                for _, b in s.branches:
                    self._collect_defs(b, func_parent_qn)
                self._collect_defs(s.else_body, func_parent_qn)
            elif isinstance(s, N.Try):
                self._collect_defs(s.body, func_parent_qn)
                for _e, _v, hb in s.handlers:
                    self._collect_defs(hb, func_parent_qn)
                self._collect_defs(s.finally_body, func_parent_qn)

    def _new_finfo(self, node, parent):
        return {
            "node": node,
            "params": list(node.params),
            "param_types": [None] * len(node.params),
            "defaults": dict(node.defaults),
            "ret": None,
            "has_return": False,
            "locals": {},
            "nested": parent is not None,
            "parent": parent,
            "qname": node.qualname,
            "cname": node.qualname,  # valid C identifier (__ separators)
            "captures": [],      # [(name, defining_qname), ...] filled post-fixpoint
            "cell_vars": set(),  # locals/params needing heap cells (filled post-fixpoint)
        }

    def _collect_global_names(self, s):
        # Every name bound at top level (even inside loop/if bodies)
        # becomes a global; without this, codegen can't type uses after
        # the block ("no type for variable").
        if isinstance(s, N.Assign):
            self.global_names.add(s.target)
        elif isinstance(s, N.For):
            self.global_names.add(s.var)
            for b in s.body:
                self._collect_global_names(b)
        elif isinstance(s, N.Try):
            for b in s.body:
                self._collect_global_names(b)
            for _exc, var, hbody in s.handlers:
                if var is not None:
                    self.global_names.add(var)
                for b in hbody:
                    self._collect_global_names(b)
            for b in s.finally_body:
                self._collect_global_names(b)
        elif isinstance(s, N.While):
            for b in s.body:
                self._collect_global_names(b)
        elif isinstance(s, N.If):
            for _, body in s.branches:
                for b in body:
                    self._collect_global_names(b)
            for b in s.else_body:
                self._collect_global_names(b)
        # FuncDef / SetItem / ExprStmt / Return bind nothing new here

    # -- driver -----------------------------------------------------------
    def infer(self):
        for _ in range(30):
            self.changed = False
            for qn, finfo in self.funcs.items():
                if finfo["nested"]:
                    continue
                self.infer_func(finfo, {})
            # Seed the per-pass environment with the accumulated global types
            # so reads in this pass see each global's widened (converged-so-far)
            # type. Without this, a global widened to dyn by an earlier pass is
            # still read as its narrow per-pass type, and the final pass
            # annotates every use with a stale type that disagrees with the
            # variable's actual storage type (declared from self.globals).
            env = dict(self.globals)
            for s in self.program.stmts:
                if not isinstance(s, (N.FuncDef, N.ClassDef)):
                    self.infer_stmt(s, env, None, True)
            for name in self.global_names:
                self._merge_dict(self.globals, name, env.get(name))
            if not self.changed:
                break
        # finalize: unresolved -> dyn; functions without return -> void
        for finfo in self.funcs.values():
            finfo["param_types"] = [pt or DYN for pt in finfo["param_types"]]
            if not finfo["has_return"]:
                finfo["ret"] = VOID
            elif finfo["ret"] is None:
                finfo["ret"] = DYN
            for k in list(finfo["locals"]):
                if finfo["locals"][k] is None:
                    finfo["locals"][k] = DYN
        for k in list(self.globals):
            if self.globals[k] is None:
                self.globals[k] = DYN
        self._compute_captures()
        self._mark_recursive()
        self._finalize_types(self.program)
        return self.funcs, self.globals

    def infer_func(self, finfo, parent_env):
        # env starts as a copy of the enclosing scope so nested functions
        # see enclosing bindings; writes stay local (CPython scoping:
        # assignment never writes through to an enclosing function scope).
        env = dict(parent_env)
        for p, pt in zip(finfo["params"], finfo["param_types"]):
            # params are always visible (even while their types are still
            # unknown) so nested functions can capture them
            env[p] = pt
        if finfo.get("is_method"):
            # self is the class instance
            cname = finfo["class"]
            if finfo["params"]:
                env[finfo["params"][0]] = class_t(cname)
                finfo["param_types"][0] = class_t(cname)
        for s in finfo["node"].body:
            if isinstance(s, N.FuncDef):
                env[s.name] = closure_t(s.qualname)
        # Seed with this function's accumulated local types (same rationale as
        # the top-level driver: reads must see widened types from earlier
        # passes, otherwise the final pass annotates uses with stale types).
        # setdefault keeps params and nested-function entries intact.
        for k, v in finfo["locals"].items():
            if v is not None:
                env.setdefault(k, v)
        owned = self._owned_names(finfo["node"].body)
        for s in finfo["node"].body:
            if isinstance(s, N.FuncDef):
                continue
            self.infer_stmt(s, env, finfo, False)
        for k, v in env.items():
            if k in finfo["params"] or k in self.global_names:
                continue
            if k in owned:
                self._merge_dict(finfo["locals"], k, v)
        for s in finfo["node"].body:
            if isinstance(s, N.FuncDef):
                self.infer_func(self.funcs[s.qualname], env)

    def _owned_names(self, stmts):
        # names bound by this function scope (not descending into nested defs)
        out = set()
        for s in stmts:
            if isinstance(s, N.Assign):
                out.add(s.target)
            elif isinstance(s, N.For):
                out.add(s.var)
                out |= self._owned_names(s.body)
            elif isinstance(s, N.While):
                out |= self._owned_names(s.body)
            elif isinstance(s, N.If):
                for _, b in s.branches:
                    out |= self._owned_names(b)
                out |= self._owned_names(s.else_body)
            elif isinstance(s, N.Try):
                out |= self._owned_names(s.body)
                for _e, v, hb in s.handlers:
                    if v:
                        out.add(v)
                    out |= self._owned_names(hb)
                out |= self._owned_names(s.finally_body)
            elif isinstance(s, N.FuncDef):
                out.add(s.name)
        return out

    def _mark_recursive(self):
        # Only (transitively) recursive functions can overflow the C stack
        # via input-dependent depth, so only they need the recursion guard.
        calls = {}
        for name, finfo in self.funcs.items():
            found = set()
            self._collect_calls(finfo["node"], found)
            calls[name] = found & set(self.funcs)
        for name in self.funcs:
            seen = set()
            stack = [name]
            recursive = False
            while stack and not recursive:
                cur = stack.pop()
                for callee in calls.get(cur, ()):
                    if callee == name:
                        recursive = True
                        break
                    if callee not in seen:
                        seen.add(callee)
                        stack.append(callee)
            self.funcs[name]["recursive"] = recursive

    def _collect_calls(self, node, out):
        if isinstance(node, (N.Call, N.CallObj)):
            if getattr(node, "indirect", None):
                out.add(node.indirect)
            elif getattr(node, "method_class", None):
                out.add(node.method_class + "__" + node.method_name)
            elif getattr(node, "inst_class", None):
                # __init__ call
                cname = node.inst_class
                if "__init__" in self.classes[cname]["methods"]:
                    out.add(cname + "__" + "__init__")
            elif isinstance(node, N.Call):
                out.add(node.func)
        for v in vars(node).values():
            self._collect_node_calls(v, out)

    def _collect_node_calls(self, v, out):
        if isinstance(v, N.Node):
            self._collect_calls(v, out)
        elif isinstance(v, (list, tuple)):
            for item in v:
                self._collect_node_calls(item, out)
        elif isinstance(v, dict):
            for item in v.values():
                self._collect_node_calls(item, out)

    def _compute_captures(self):
        # Free-variable analysis: for each nested function, find names it
        # reads without assigning that resolve to an enclosing function's
        # scope. Those become heap cells in the defining function and
        # environment slots in the nested function.
        order = []  # nested qnames, innermost first

        def visit(qn):
            for s in self.funcs[qn]["node"].body:
                if isinstance(s, N.FuncDef):
                    visit(s.qualname)
            if self.funcs[qn]["nested"]:
                order.append(qn)

        for qn, fi in self.funcs.items():
            if not fi["nested"]:
                visit(qn)
        for qn in order:
            fi = self.funcs[qn]
            assigned, read = set(), set()
            self._free_vars_body(fi["node"].body, assigned, read)
            assigned |= set(fi["params"])
            for s in fi["node"].body:
                if isinstance(s, N.FuncDef):
                    assigned.add(s.name)
            for name in sorted(read - assigned):
                if name in self.global_names:
                    continue
                if name in BUILTINS or name in CONSTANTS:
                    continue
                cur = fi["parent"]
                while cur is not None:
                    pf = self.funcs[cur]
                    if name in pf["params"] or name in pf["locals"]:
                        fi["captures"].append((name, cur))
                        break
                    cur = pf["parent"]
        # forwarding: a capture from a grandparent passes through the
        # parent's environment
        for qn in order:
            fi = self.funcs[qn]
            pf = self.funcs[fi["parent"]]
            for cap in fi["captures"]:
                if cap[1] != fi["parent"] and cap not in pf["captures"]:
                    pf["captures"].append(cap)
        # defining functions heap-allocate the captured variables
        for qn in order:
            for (name, defining) in self.funcs[qn]["captures"]:
                self.funcs[defining]["cell_vars"].add(name)

    def _free_vars_body(self, stmts, assigned, read):
        for s in stmts:
            if isinstance(s, N.Assign):
                self._free_vars_expr(s.value, assigned, read)
                assigned.add(s.target)
            elif isinstance(s, N.SetItem):
                self._free_vars_expr(s.key, assigned, read)
                self._free_vars_expr(s.value, assigned, read)
                read.add(s.target)
            elif isinstance(s, N.Return):
                if s.value is not None:
                    self._free_vars_expr(s.value, assigned, read)
            elif isinstance(s, N.If):
                for cond, body in s.branches:
                    self._free_vars_expr(cond, assigned, read)
                    self._free_vars_body(body, assigned, read)
                self._free_vars_body(s.else_body, assigned, read)
            elif isinstance(s, N.While):
                self._free_vars_expr(s.cond, assigned, read)
                self._free_vars_body(s.body, assigned, read)
            elif isinstance(s, N.For):
                self._free_vars_expr(s.iter_expr, assigned, read)
                assigned.add(s.var)
                self._free_vars_body(s.body, assigned, read)
            elif isinstance(s, N.ExprStmt):
                self._free_vars_expr(s.expr, assigned, read)
            elif isinstance(s, N.Try):
                self._free_vars_body(s.body, assigned, read)
                for _e, v, hb in s.handlers:
                    if v:
                        assigned.add(v)
                    self._free_vars_body(hb, assigned, read)
                self._free_vars_body(s.finally_body, assigned, read)
            elif isinstance(s, N.FuncDef):
                assigned.add(s.name)  # bound here; body is a separate scope
            elif isinstance(s, N.SetAttr):
                self._free_vars_expr(s.obj, assigned, read)
                self._free_vars_expr(s.value, assigned, read)

    def _free_vars_expr(self, e, assigned, read):
        if isinstance(e, N.Name):
            if e.id not in CONSTANTS:
                read.add(e.id)
            return
        if isinstance(e, N.Call):
            # `adder(5)`: adder is a variable read; builtins and named
            # functions are not.
            if e.func not in BUILTINS and e.func not in self.funcs:
                read.add(e.func)
        if isinstance(e, (N.ListComp, N.DictComp)):
            # comprehension clause variables are bound inside
            sub_a, sub_r = set(), set()
            for cl in e.clauses:
                if cl[0] == "for":
                    self._free_vars_expr(cl[2], sub_a, sub_r)
                    sub_a.add(cl[1])
                else:
                    self._free_vars_expr(cl[1], sub_a, sub_r)
            if isinstance(e, N.ListComp):
                self._free_vars_expr(e.elt, sub_a, sub_r)
            else:
                self._free_vars_expr(e.key, sub_a, sub_r)
                self._free_vars_expr(e.value, sub_a, sub_r)
            read |= (sub_r - sub_a)
            return
        for v in vars(e).values():
            self._free_vars_value(v, assigned, read)

    def _free_vars_value(self, v, assigned, read):
        if isinstance(v, N.Node):
            self._free_vars_expr(v, assigned, read)
        elif isinstance(v, (list, tuple)):
            for item in v:
                self._free_vars_value(item, assigned, read)
        elif isinstance(v, dict):
            for item in v.values():
                self._free_vars_value(item, assigned, read)

    def _finalize_types(self, program):
        for s in program.stmts:
            self._fin_stmt(s)

    def _fin_stmt(self, s):
        if isinstance(s, N.FuncDef):
            for b in s.body:
                self._fin_stmt(b)
        elif isinstance(s, (N.If,)):
            for _, body in s.branches:
                for b in body:
                    self._fin_stmt(b)
            for b in s.else_body:
                self._fin_stmt(b)
        elif isinstance(s, (N.While, N.For)):
            for b in s.body:
                self._fin_stmt(b)
        elif isinstance(s, N.Try):
            for b in s.body:
                self._fin_stmt(b)
            for _exc, _var, hbody in s.handlers:
                for b in hbody:
                    self._fin_stmt(b)
            for b in s.finally_body:
                self._fin_stmt(b)
        self._fin_node(s)
        # also finalize expressions inside the statement
        for v in vars(s).values():
            self._fin_value(v)

    def _fin_value(self, v):
        if isinstance(v, N.Node):
            self._fin_node(v)
            for vv in vars(v).values():
                self._fin_value(vv)
        elif isinstance(v, (list, tuple)):
            for item in v:
                self._fin_value(item)
        elif isinstance(v, dict):
            for item in v.values():
                self._fin_value(item)

    def _fin_node(self, node):
        t = getattr(node, "inferred", None)
        if t is None and isinstance(node, (N.Name, N.Call, N.CallObj, N.BinOp,
                                           N.UnaryOp, N.Index, N.DictLit,
                                           N.GetAttr, N.ListLit)):
            node.inferred = DYN
        for attr in ("target_type", "var_type"):
            if hasattr(node, attr) and getattr(node, attr) is None:
                setattr(node, attr, DYN)

    def _merge_dict(self, d, k, t):
        old = d.get(k)
        new = join(old, t)
        if new != old:
            d[k] = new
            self.changed = True

    # -- variables ----------------------------------------------------------
    def merge_var(self, name, t, env, finfo, is_global):
        if not is_global and finfo is not None and name in finfo["params"]:
            idx = finfo["params"].index(name)
            old = finfo["param_types"][idx]
            new = join(old, t)
            if new != old:
                finfo["param_types"][idx] = new
                self.changed = True
            if env.get(name) != new:
                env[name] = new
            return
        if not is_global and name in self.global_names:
            self._merge_dict(self.globals, name, t)
            return
        self._merge_dict(env, name, t)

    def lookup(self, name, env, finfo, is_global, line):
        if name in env:
            return env[name]
        if not is_global and finfo is not None and name in finfo["params"]:
            return finfo["param_types"][finfo["params"].index(name)]
        if name in self.globals:
            return self.globals[name]
        if name in self.global_names:
            return None
        raise CompileError("line %d: unknown name '%s'" % (line, name))

    # -- statements ----------------------------------------------------------
    def infer_stmt(self, s, env, finfo, is_global):
        if isinstance(s, N.Assign):
            t = self.infer_expr(s.value, env, finfo)
            s.target_type = t
            self.merge_var(s.target, t, env, finfo, is_global)
        elif isinstance(s, N.SetItem):
            # d[k] = v — merge v into the dict's value type (like append)
            ot = self.lookup(s.target, env, finfo, finfo is None, s.line)
            kt = self.infer_expr(s.key, env, finfo)
            vt = self.infer_expr(s.value, env, finfo)
            if is_dict(ot):
                if kt not in (STR, DYN) and kt is not None:
                    raise CompileError("line %d: dict keys must be strings, got %r"
                                       % (s.line, kt))
                new = ("dict", join(ot[1], vt))
                if new != ot:
                    self.merge_var(s.target, new, env, finfo, is_global)
            elif is_list(ot):
                if kt not in (I64, DYN) and kt is not None:
                    raise CompileError("line %d: list indices must be integers, got %r"
                                       % (s.line, kt))
                new = ("list", join(ot[1], vt))
                if new != ot:
                    self.merge_var(s.target, new, env, finfo, is_global)
            elif ot is None or ot == DYN:
                pass  # stays dyn; runtime handles it
            else:
                raise CompileError("line %d: cannot set item on %r" % (s.line, ot))
        elif isinstance(s, N.SetAttr):
            # obj.attr = v — for class instances, merge into the attr type
            ot = self.infer_expr(s.obj, env, finfo)
            vt = self.infer_expr(s.value, env, finfo)
            if is_class(ot):
                cname = ot[1]
                attrs = self.classes[cname]["attrs"]
                old = attrs.get(s.attr)
                new = join(old, vt or DYN)
                if new != old:
                    attrs[s.attr] = new
                    self.changed = True
            elif ot is None or ot == DYN:
                pass  # defer
            else:
                raise CompileError("line %d: cannot set attribute '%s' of %r"
                                   % (s.line, s.attr, ot))
        elif isinstance(s, N.Return):
            if finfo is None:
                raise CompileError("line %d: return outside function" % s.line)
            finfo["has_return"] = True
            if s.value is None:
                if finfo.get("has_valued_return"):
                    raise CompileError(
                        "line %d: bare return in function that returns values" % s.line)
                finfo["has_bare_return"] = True
                t = VOID
            else:
                if finfo.get("has_bare_return"):
                    raise CompileError(
                        "line %d: valued return in function with bare return" % s.line)
                finfo["has_valued_return"] = True
                t = self.infer_expr(s.value, env, finfo)
            old, new = finfo["ret"], join(finfo["ret"], t)
            if new != old:
                finfo["ret"] = new
                self.changed = True
        elif isinstance(s, N.If):
            for cond, body in s.branches:
                self.infer_expr(cond, env, finfo)
                for b in body:
                    self.infer_stmt(b, env, finfo, is_global)
            for b in s.else_body:
                self.infer_stmt(b, env, finfo, is_global)
        elif isinstance(s, N.While):
            self.infer_expr(s.cond, env, finfo)
            for b in s.body:
                self.infer_stmt(b, env, finfo, is_global)
        elif isinstance(s, N.For):
            it = self.infer_expr(s.iter_expr, env, finfo)
            if it == RANGE:
                vt = I64
            elif is_list(it):
                vt = it[1]
            elif it is None or it == DYN:
                vt = DYN
            else:
                raise CompileError("line %d: cannot iterate over %r" % (s.line, it))
            s.var_type = vt
            self.merge_var(s.var, vt, env, finfo, is_global)
            for b in s.body:
                self.infer_stmt(b, env, finfo, is_global)
        elif isinstance(s, N.Try):
            for b in s.body:
                self.infer_stmt(b, env, finfo, is_global)
            for exc, var, hbody in s.handlers:
                if exc is not None and exc not in KNOWN_EXCEPTIONS:
                    raise CompileError("line %d: unknown exception type '%s'"
                                       % (s.line, exc))
                if var is not None:
                    # the handler variable binds the error message (a string)
                    self.merge_var(var, STR, env, finfo, is_global)
                for b in hbody:
                    self.infer_stmt(b, env, finfo, is_global)
            for b in s.finally_body:
                self.infer_stmt(b, env, finfo, is_global)
        elif isinstance(s, N.ExprStmt):
            self.infer_expr(s.expr, env, finfo)
        elif isinstance(s, N.FuncDef):
            pass  # handled in driver
        else:
            raise CompileError("cannot infer statement %r" % s)

    # -- expressions ----------------------------------------------------------
    def infer_expr(self, e, env, finfo):
        t = self._infer_expr(e, env, finfo)
        e.inferred = t
        return t

    def _infer_expr(self, e, env, finfo):
        if isinstance(e, N.IntLit):
            return I64
        if isinstance(e, N.FloatLit):
            return F64
        if isinstance(e, N.StrLit):
            return STR
        if isinstance(e, N.BoolLit):
            return BOOL
        if isinstance(e, N.Name):
            if e.id in CONSTANTS:
                return CONSTANTS[e.id]
            try:
                return self.lookup(e.id, env, finfo, finfo is None, e.line)
            except CompileError:
                # a top-level function referenced by name is a first-class
                # closure value (with no environment)
                if e.id in self.funcs and not self.funcs[e.id].get("nested"):
                    return closure_t(e.id)
                raise
        if isinstance(e, N.ListLit):
            t = None
            for x in e.elts:
                t = join(t, self.infer_expr(x, env, finfo))
            return ("list", t or DYN)
        if isinstance(e, N.DictLit):
            vt = None
            for k in e.keys:
                kt = self.infer_expr(k, env, finfo)
                if kt not in (STR, DYN) and kt is not None:
                    raise CompileError("line %d: dict keys must be strings, got %r"
                                       % (e.line, kt))
            for v in e.values:
                vt = join(vt, self.infer_expr(v, env, finfo))
            return ("dict", vt or DYN)
        if isinstance(e, N.FStr):
            for kind, p in e.parts:
                if kind == "expr":
                    self.infer_expr(p, env, finfo)
            return STR
        if isinstance(e, (N.ListComp, N.DictComp)):
            return self.infer_comp(e, env, finfo)
        if isinstance(e, N.Index):
            ot = self.infer_expr(e.obj, env, finfo)
            it = self.infer_expr(e.index, env, finfo)
            if is_list(ot):
                return ot[1]
            if is_dict(ot):
                if it not in (STR, DYN) and it is not None:
                    raise CompileError("line %d: dict keys must be strings, got %r"
                                       % (e.line, it))
                return ot[1]
            if ot == STR:
                return STR
            if ot is None or ot == DYN:
                return DYN
            raise CompileError("line %d: cannot index %r" % (e.line, ot))
        if isinstance(e, N.Slice):
            ot = self.infer_expr(e.obj, env, finfo)
            for part in (e.lo, e.hi, e.step):
                if part is not None:
                    pt = self.infer_expr(part, env, finfo)
                    if pt not in (I64, None, DYN):
                        raise CompileError("line %d: slice bounds must be integers, got %r"
                                           % (e.line, pt))
            if ot == STR:
                return STR
            if is_list(ot):
                return ot
            if ot is None or ot == DYN:
                return DYN
            raise CompileError("line %d: cannot slice %r" % (e.line, ot))
        if isinstance(e, N.UnaryOp):
            t = self.infer_expr(e.operand, env, finfo)
            if e.op == "not":
                return BOOL
            return t
        if isinstance(e, N.BinOp):
            if e.op in ("and", "or"):
                # Python semantics: return the operand, not a bool
                l = self.infer_expr(e.left, env, finfo)
                r = self.infer_expr(e.right, env, finfo)
                return join(l, r)
            l = self.infer_expr(e.left, env, finfo)
            r = self.infer_expr(e.right, env, finfo)
            if e.op in ("==", "!=", "<", ">", "<=", ">="):
                return BOOL
            if e.op == "in":
                # needle in haystack: list / str / dict / range / dyn
                if is_list(r) or r == STR or is_dict(r) or r == RANGE or r == DYN or r is None:
                    return BOOL
                raise CompileError("line %d: cannot use 'in' on %r" % (e.line, r))
            return self._arith(e.op, l, r, e.line)
        if isinstance(e, N.ChainCompare):
            for x in e.exprs:
                self.infer_expr(x, env, finfo)
            return BOOL
        if isinstance(e, N.Call):
            return self.infer_call(e, env, finfo)
        if isinstance(e, N.CallObj):
            ft = self.infer_expr(e.func, env, finfo)
            if is_closure(ft):
                f = self.funcs[ft[1]]
                e.effective_args = self._apply_defaults(e, f, env, finfo)
                e.indirect = ft[1]
                return f["ret"]
            raise CompileError("line %d: cannot call %r" % (e.line, ft))
        if isinstance(e, N.GetAttr):
            ot = self.infer_expr(e.obj, env, finfo)
            if is_class(ot):
                cname = ot[1]
                attrs = self.classes[cname]["attrs"]
                if e.attr in attrs:
                    return attrs[e.attr]
                # attr not yet seen; defer (fixpoint may discover it)
                return None
            if ot is None or ot == DYN:
                return DYN
            raise CompileError("line %d: cannot get attribute '%s' of %r"
                               % (e.line, e.attr, ot))
        raise CompileError("line %d: cannot infer %r" % (e.line, e))

    def infer_comp(self, e, env, finfo):
        # Clause variables live in a child scope: they must not leak into
        # (or widen) the enclosing environment.
        cenv = dict(env)
        for cl in e.clauses:
            if cl[0] == "for":
                _kind, var, it = cl
                t = self.infer_expr(it, cenv, finfo)
                if t == RANGE:
                    vt = I64
                elif is_list(t):
                    vt = t[1]
                elif t is None or t == DYN:
                    vt = DYN
                else:
                    raise CompileError("line %d: cannot iterate over %r" % (e.line, t))
                cenv[var] = vt
            else:
                self.infer_expr(cl[1], cenv, finfo)
        if isinstance(e, N.ListComp):
            elt_t = self.infer_expr(e.elt, cenv, finfo)
            return ("list", elt_t)
        kt = self.infer_expr(e.key, cenv, finfo)
        if kt not in (STR, None):
            raise CompileError("line %d: dict comprehension keys must be strings, got %r"
                               % (e.line, kt))
        vt = self.infer_expr(e.value, cenv, finfo)
        return ("dict", vt)

    def _arith(self, op, l, r, line):
        if l is None or r is None:
            return None
        if op == "/":
            if l in (I64, F64) and r in (I64, F64):
                return F64
            return DYN
        if l == STR and r == STR and op == "+":
            return STR
        if l in (I64, F64) and r in (I64, F64):
            return I64 if l == I64 and r == I64 and op != "/" else F64
        return DYN

    def infer_indirect_call(self, e, ct, env, finfo):
        # call through a closure-typed variable: f(5) where f holds a closure
        f = self.funcs[ct[1]]
        e.effective_args = self._apply_defaults(e, f, env, finfo)
        e.indirect = ct[1]
        return f["ret"] if f["ret"] is not None else DYN

    def _need_args(self, e, n):
        if len(e.args) != n:
            raise CompileError("line %d: %s() takes %d argument(s)" % (e.line, e.func, n))

    def _need_num(self, e, a, env, finfo):
        t = self.infer_expr(a, env, finfo)
        if t not in (I64, F64, None, DYN):
            raise CompileError("line %d: %s() needs a number" % (e.line, e.func))
        return t

    def _need_str(self, e, a, env, finfo):
        t = self.infer_expr(a, env, finfo)
        if t not in (STR, None, DYN):
            raise CompileError("line %d: %s() needs a string" % (e.line, e.func))
        return t

    def infer_instantiation(self, e, cname, env, finfo):
        # Point(...) -> create instance; args go to __init__ (minus self)
        cls = self.classes[cname]
        e.inst_class = cname
        if "__init__" not in cls["methods"]:
            if e.args:
                raise CompileError("line %d: class '%s' takes no arguments"
                                   % (e.line, cname))
            return class_t(cname)
        mf = cls["methods"]["__init__"]
        # build a synthetic call skipping self
        synth = N.Call("__init__", e.args, e.line)
        synth.effective_args = self._apply_defaults_self(synth, mf, env, finfo)
        e.effective_args = synth.effective_args
        return class_t(cname)

    def _apply_defaults_self(self, e, f, env, finfo):
        # like _apply_defaults but skips the first param (self, already bound)
        nargs = len(e.args)
        nparams = len(f["params"]) - 1  # exclude self
        if nargs > nparams:
            raise CompileError(
                "line %d: takes %d arguments (%d given)"
                % (e.line, nparams, nargs))
        missing = f["params"][1 + nargs:]
        for pname in missing:
            if pname not in f["defaults"]:
                raise CompileError(
                    "line %d: missing required argument '%s'" % (e.line, pname))
        for i, a in enumerate(e.args):
            at = self.infer_expr(a, env, finfo)
            idx = i + 1  # skip self
            old, new = f["param_types"][idx], join(f["param_types"][idx], at)
            if new != old:
                f["param_types"][idx] = new
                self.changed = True
        arg_exprs = list(e.args)
        for j, pname in enumerate(missing):
            dt = self.infer_expr(f["defaults"][pname], env, finfo)
            idx = 1 + nargs + j
            old, new = f["param_types"][idx], join(f["param_types"][idx], dt)
            if new != old:
                f["param_types"][idx] = new
                self.changed = True
            arg_exprs.append(f["defaults"][pname])
        return arg_exprs

    def infer_method_call(self, e, cname, env, finfo):
        # obj.method(args): e.args[0] is the object (self)
        mname = e.func
        cls = self.classes[cname]
        if mname not in cls["methods"]:
            raise CompileError("line %d: class '%s' has no method '%s'"
                               % (e.line, cname, mname))
        mf = cls["methods"][mname]
        # self is e.args[0]; remaining args correspond to params[1:]
        synth = N.Call(mname, e.args[1:], e.line)
        synth.effective_args = self._apply_defaults_self(synth, mf, env, finfo)
        e.effective_args = [e.args[0]] + synth.effective_args
        e.method_class = cname
        e.method_name = mname
        return mf["ret"] if mf["ret"] is not None else DYN

    def infer_call(self, e, env, finfo):
        name = e.func
        is_global = finfo is None
        # method call on a class instance: obj.method(args) parses as
        # Call("method", [obj] + args); only if "method" is actually a
        # method of the class (otherwise it's a builtin/global function
        # taking the instance as an argument, e.g. print(p))
        if e.args:
            ot = self.infer_expr(e.args[0], env, finfo)
            if is_class(ot) and name in self.classes[ot[1]]["methods"]:
                return self.infer_method_call(e, ot[1], env, finfo)
        # class instantiation: Point(...) -> ("class", "Point")
        if name in self.classes:
            return self.infer_instantiation(e, name, env, finfo)
        # a variable holding a closure shadows builtins and named functions
        _unknown = object()
        ct = _unknown
        try:
            ct = self.lookup(name, env, finfo, is_global, e.line)
        except CompileError:
            pass
        if is_closure(ct):
            return self.infer_indirect_call(e, ct, env, finfo)
        if ct is None:
            # a known variable whose type isn't pinned down yet; return None
            # so the fixpoint defers (returning DYN would poison the type)
            return None
        if name == "print":
            for a in e.args:
                self.infer_expr(a, env, finfo)
            return VOID
        if name == "len":
            if len(e.args) != 1:
                raise CompileError("line %d: len() takes 1 argument" % e.line)
            self.infer_expr(e.args[0], env, finfo)
            return I64
        if name == "range":
            if len(e.args) not in (1, 2, 3):
                raise CompileError("line %d: range() takes 1 to 3 arguments" % e.line)
            for a in e.args:
                self.infer_expr(a, env, finfo)
            return RANGE
        if name == "list":
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if t == RANGE:
                return ("list", I64)
            if is_list(t):
                return t
            if t is None or t == DYN:
                return ("list", DYN)
            raise CompileError("line %d: list() of %r" % (e.line, t))
        if name == "sorted":
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if is_list(t):
                return t
            if t is None or t == DYN:
                return ("list", DYN)
            raise CompileError("line %d: sorted() of %r" % (e.line, t))
        if name == "reversed":
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if is_list(t):
                return t
            if t == RANGE:
                return ("list", I64)
            if t is None or t == DYN:
                return ("list", DYN)
            raise CompileError("line %d: reversed() of %r" % (e.line, t))
        if name in ("any", "all"):
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if is_list(t) or t == RANGE or t is None or t == DYN:
                return BOOL
            raise CompileError("line %d: %s() of %r" % (e.line, name, t))
        if name == "enumerate":
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if is_list(t) or t == RANGE or t is None or t == DYN:
                # list of [index, value] pairs (2-elem dyn lists)
                return ("list", ("list", DYN))
            raise CompileError("line %d: enumerate() of %r" % (e.line, t))
        if name == "zip":
            if len(e.args) != 2:
                raise CompileError("line %d: zip() takes 2 arguments" % e.line)
            t1 = self.infer_expr(e.args[0], env, finfo)
            t2 = self.infer_expr(e.args[1], env, finfo)
            # list of [a, b] pairs (2-elem dyn lists)
            return ("list", ("list", DYN))
        if name in ("map", "filter"):
            if len(e.args) != 2:
                raise CompileError("line %d: %s() takes 2 arguments" % (e.line, name))
            # func is args[0], iterable is args[1]
            it = self.infer_expr(e.args[1], env, finfo)
            if it == RANGE:
                elt = I64
            elif is_list(it):
                elt = it[1]
            else:
                elt = DYN
            # resolve the function and join the element type into its param
            func_expr = e.args[0]
            if isinstance(func_expr, N.Name) and func_expr.id in self.funcs:
                f = self.funcs[func_expr.id]
                if len(f["params"]) == 1:
                    old, new = f["param_types"][0], join(f["param_types"][0], elt)
                    if new != old:
                        f["param_types"][0] = new
                        self.changed = True
            fret = self._builtin_func_ret(e.args[0], env, finfo, e.line)
            if name == "map":
                return ("list", fret or DYN)
            else:
                # filter returns same element type as input
                if is_list(it):
                    return it
                if it == RANGE:
                    return ("list", I64)
                return ("list", DYN)
        if name == "append":
            if len(e.args) != 2:
                raise CompileError("line %d: append() takes 2 arguments" % e.line)
            lst, elt = e.args
            et = self.infer_expr(e.args[1], env, finfo)
            lt = self.infer_expr(lst, env, finfo)
            if is_list(lt):
                new_elt = join(lt[1], et)
                if isinstance(lst, N.Name):
                    # merge the widened element type back into the list variable
                    cur = self.lookup(lst.id, env, finfo, is_global, e.line)
                    if is_list(cur):
                        self.merge_var(lst.id, ("list", new_elt), env, finfo, is_global)
                return VOID
            if lt is None or lt == DYN:
                if isinstance(lst, N.Name):
                    self.merge_var(lst.id, ("list", et or DYN), env, finfo, is_global)
                return VOID
            raise CompileError("line %d: append() needs a list" % e.line)
        if name == "keys":
            self._need_args(e, 1)
            t = self.infer_expr(e.args[0], env, finfo)
            if is_dict(t):
                return ("list", STR)
            raise CompileError("line %d: keys() needs a dict" % e.line)
        # ---- stdlib: math ----
        if name in ("sqrt", "sin", "cos", "tan", "exp", "log"):
            self._need_args(e, 1)
            self._need_num(e, e.args[0], env, finfo)
            return F64
        if name == "pow":
            self._need_args(e, 2)
            self._need_num(e, e.args[0], env, finfo)
            self._need_num(e, e.args[1], env, finfo)
            return F64
        if name == "abs":
            self._need_args(e, 1)
            t = self._need_num(e, e.args[0], env, finfo)
            return t if t in (I64, F64) else DYN
        if name in ("floor", "ceil"):
            self._need_args(e, 1)
            self._need_num(e, e.args[0], env, finfo)
            return I64
        # ---- stdlib: strings ----
        if name == "split":
            self._need_args(e, 2)
            self._need_str(e, e.args[0], env, finfo)
            self._need_str(e, e.args[1], env, finfo)
            return ("list", STR)
        if name == "join":
            self._need_args(e, 2)
            self._need_str(e, e.args[0], env, finfo)
            lt = self.infer_expr(e.args[1], env, finfo)
            if lt != ("list", STR) and lt != DYN and lt is not None:
                raise CompileError("line %d: join() needs a list[str]" % e.line)
            return STR
        if name in ("upper", "lower", "strip"):
            self._need_args(e, 1)
            self._need_str(e, e.args[0], env, finfo)
            return STR
        if name == "replace":
            self._need_args(e, 3)
            for a in e.args:
                self._need_str(e, a, env, finfo)
            return STR
        if name == "find":
            self._need_args(e, 2)
            self._need_str(e, e.args[0], env, finfo)
            self._need_str(e, e.args[1], env, finfo)
            return I64
        if name in ("startswith", "endswith"):
            self._need_args(e, 2)
            self._need_str(e, e.args[0], env, finfo)
            self._need_str(e, e.args[1], env, finfo)
            return BOOL
        # ---- stdlib: lists ----
        if name in ("sort", "reverse"):
            self._need_args(e, 1)
            lt = self.infer_expr(e.args[0], env, finfo)
            if not is_list(lt) and lt not in (None, DYN):
                raise CompileError("line %d: %s() needs a list" % (e.line, name))
            return VOID
        if name == "sum":
            self._need_args(e, 1)
            lt = self.infer_expr(e.args[0], env, finfo)
            if lt == ("list", I64):
                return I64
            if lt == ("list", F64):
                return F64
            if lt == RANGE:
                return I64
            if lt is None or lt == DYN:
                return DYN
            raise CompileError("line %d: sum() needs a numeric list" % e.line)
        if name in ("min", "max"):
            self._need_args(e, 1)
            lt = self.infer_expr(e.args[0], env, finfo)
            if is_list(lt):
                return lt[1]
            if lt is None or lt == DYN:
                return DYN
            raise CompileError("line %d: %s() needs a list" % (e.line, name))
        # ---- stdlib: files ----
        if name == "read_file":
            self._need_args(e, 1)
            self._need_str(e, e.args[0], env, finfo)
            return STR
        if name == "write_file":
            self._need_args(e, 2)
            self._need_str(e, e.args[0], env, finfo)
            self._need_str(e, e.args[1], env, finfo)
            return VOID
        if name == "file_lines":
            self._need_args(e, 1)
            self._need_str(e, e.args[0], env, finfo)
            return ("list", STR)
        # ---- stdlib: time & random & sys ----
        if name == "now":
            self._need_args(e, 0)
            return F64
        if name == "sleep":
            self._need_args(e, 1)
            self._need_num(e, e.args[0], env, finfo)
            return VOID
        if name == "rand":
            self._need_args(e, 0)
            return F64
        if name == "randint":
            self._need_args(e, 2)
            self._need_num(e, e.args[0], env, finfo)
            self._need_num(e, e.args[1], env, finfo)
            return I64
        if name == "seed":
            self._need_args(e, 1)
            self._need_num(e, e.args[0], env, finfo)
            return VOID
        if name == "argv":
            self._need_args(e, 0)
            return ("list", STR)
        if name == "exit":
            self._need_args(e, 1)
            self._need_num(e, e.args[0], env, finfo)
            return VOID
        if name in self.funcs:
            f = self.funcs[name]
            e.effective_args = self._apply_defaults(e, f, env, finfo)
            return f["ret"] if f["ret"] is not None else DYN
        # a nested function called by its short name from inside its own
        # scope chain (including direct recursion: boom() inside boom)
        if finfo is not None:
            qn = self._resolve_nested_func(name, finfo)
            if qn is not None:
                e.func = qn  # rewrite to the qualified name
                return self.infer_call(e, env, finfo)
        raise CompileError("line %d: unknown function '%s'" % (e.line, name))

    def _builtin_func_ret(self, func_expr, env, finfo, line):
        # Resolve a function expression (for map/filter) to its return type.
        # Returns the return type, or None if unknown.
        if isinstance(func_expr, N.Name):
            name = func_expr.id
            if name in self.funcs:
                f = self.funcs[name]
                return f["ret"]
            # try variable lookup for closure
            try:
                ct = self.lookup(name, env, finfo, finfo is None, line)
            except CompileError:
                ct = None
            if is_closure(ct):
                f = self.funcs[ct[1]]
                return f["ret"]
        return None

    def _apply_defaults(self, e, f, env, finfo):
        # Fill missing call args with default exprs. Returns the effective
        # arg list (original args + default expr nodes). Infers each default
        # in the caller's context and joins its type into the param type.
        nargs = len(e.args)
        nparams = len(f["params"])
        if nargs > nparams:
            raise CompileError(
                "line %d: takes %d arguments (%d given)"
                % (e.line, nparams, nargs))
        missing = f["params"][nargs:]
        for pname in missing:
            if pname not in f["defaults"]:
                raise CompileError(
                    "line %d: missing required argument '%s'" % (e.line, pname))
        for i, a in enumerate(e.args):
            at = self.infer_expr(a, env, finfo)
            old, new = f["param_types"][i], join(f["param_types"][i], at)
            if new != old:
                f["param_types"][i] = new
                self.changed = True
        arg_exprs = list(e.args)
        for j, pname in enumerate(missing):
            dt = self.infer_expr(f["defaults"][pname], env, finfo)
            idx = nargs + j
            old, new = f["param_types"][idx], join(f["param_types"][idx], dt)
            if new != old:
                f["param_types"][idx] = new
                self.changed = True
            arg_exprs.append(f["defaults"][pname])
        return arg_exprs

    def _resolve_nested_func(self, name, finfo):
        # resolve a short function name visible in the current nested scope:
        # the function itself (for recursion), then outward through parents
        qn = finfo["qname"]
        if qn == name or qn.endswith("__" + name):
            return qn
        p = finfo.get("parent")
        while p is not None:
            cand = p + "__" + name
            if cand in self.funcs:
                return cand
            pf = self.funcs.get(p)
            p = pf.get("parent") if pf else None
        return None
