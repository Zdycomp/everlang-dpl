"""Flare codegen: typed AST -> C99.

Concrete numeric types compile to raw C (int64_t / double) — this is the
10x. Anything the inferrer could not pin down becomes a boxed Value.
"""

from flare import nodes as N
from flare.infer import (
    I64, F64, BOOL, STR, RANGE, DYN, VOID, is_list, is_dict, is_container,
    is_closure, is_class, CompileError,
)


def _has_call(node):
    """True if the expression tree contains a Call anywhere."""
    if isinstance(node, (N.Call, N.CallObj)):
        return True
    for v in vars(node).values():
        if _has_call_value(v):
            return True
    return False


def _has_call_value(v):
    if isinstance(v, N.Node):
        return _has_call(v)
    if isinstance(v, (list, tuple)):
        return any(_has_call_value(item) for item in v)
    if isinstance(v, dict):
        return any(_has_call_value(item) for item in v.values())
    return False


class Codegen:
    def __init__(self, program, funcs, globals_, classes=None):
        self.program = program
        self.guarded = False
        self.funcs = funcs
        self.globals = globals_
        self.classes = classes or {}
        self.out = []
        self.declared = set()
        self.cur_func = None
        self._tmp = 0
        self.try_stack = []
        self._try_id = 0
        self.comp_vars = []  # comprehension loop vars currently in scope
        self.cell_vars = set()   # function locals/params held in heap cells
        self.capture_map = {}    # names captured from enclosing scope -> True

    # -- helpers ----------------------------------------------------------
    def w(self, s):
        self.out.append(s)

    def tmp(self):
        self._tmp += 1
        return "_t%d" % self._tmp

    def ctype(self, t):
        if t == I64:
            return "int64_t"
        if t == F64:
            return "double"
        if t == BOOL:
            return "bool"
        if t == STR:
            return "char*"
        if t == DYN:
            return "Value"
        if t == VOID:
            return "void"
        if t == RANGE:
            return "FlRange"
        if is_closure(t):
            return "FlClosure"
        if is_class(t):
            return "Class_%s*" % t[1]
        if is_list(t):
            return {"I64": "FlListI64*", "F64": "FlListF64*",
                    "Str": "FlListStr*", "Dyn": "FlListDyn*",
                    "Pair": "FlListListDyn*"}[self._list_storage(t)]
        if is_dict(t):
            e = t[1]
            if e == I64:
                return "FlDict_I64*"
            if e == F64:
                return "FlDict_F64*"
            if e == STR:
                return "FlDict_Str*"
            return "FlDict_Dyn*"
        raise CompileError("no C type for %r" % (t,))

    def _list_storage(self, t):
        """Storage class for ("list", E): I64/F64/Str/Dyn/Pair.

        Pair is the enumerate()/zip() list-of-pairs representation, used
        only for the exact element type ("list", DYN). Any other container
        element type (nested lists/dicts) is stored boxed in a plain
        FlListDyn, with each element a tag-carrying Value.
        """
        e = t[1] if is_list(t) else DYN
        if e == I64:
            return "I64"
        if e == F64:
            return "F64"
        if e == STR:
            return "Str"
        if e == ("list", DYN):
            return "Pair"
        return "Dyn"

    def _box_fn(self, t):
        """C constructor boxing a typed container pointer into a Value."""
        if is_list(t):
            e = t[1]
            if e == I64:
                return "v_list_I64"
            if e == F64:
                return "v_list_F64"
            if e == STR:
                return "v_list_Str"
            if e == ("list", DYN):
                return "v_list_PAIR"
            # DYN, BOOL and any nested container element type: Dyn storage
            return "v_list_DYN"
        elif is_dict(t):
            e = t[1]
            if e == I64:
                return "v_dict_I64"
            if e == F64:
                return "v_dict_F64"
            if e == STR:
                return "v_dict_Str"
            return "v_dict_DYN"
        raise CompileError("cannot box %r" % (t,))

    def _unbox_fn(self, t):
        """C function unboxing a Value to a typed container pointer
        (checked; raises a clean TypeError on tag mismatch)."""
        if is_list(t):
            e = t[1]
            if e == I64:
                return "v_unbox_list_I64"
            if e == F64:
                return "v_unbox_list_F64"
            if e == STR:
                return "v_unbox_list_Str"
            if e == ("list", DYN):
                return "v_unbox_list_PAIR"
            # DYN, BOOL and any nested container element type: Dyn storage
            return "v_unbox_list_DYN"
        elif is_dict(t):
            e = t[1]
            if e == I64:
                return "v_unbox_dict_I64"
            if e == F64:
                return "v_unbox_dict_F64"
            if e == STR:
                return "v_unbox_dict_Str"
            return "v_unbox_dict_DYN"
        raise CompileError("cannot unbox %r" % (t,))

    def _list_converter(self, from_t, to_t):
        """C function converting between list storage classes.
        Only widening to Dyn storage is supported."""
        fs = self._list_storage(from_t)
        if self._list_storage(to_t) != "Dyn":
            raise CompileError("cannot convert %r to %r" % (from_t, to_t))
        return {"I64": "fl_list_I64_to_Dyn", "F64": "fl_list_F64_to_Dyn",
                "Str": "fl_list_Str_to_Dyn",
                "Pair": "fl_list_PAIR_to_Dyn"}[fs]

    def _dict_converter(self, from_t, to_t):
        """C function converting between dict storage classes.
        Only widening to Dyn storage is supported."""
        fs = self.dict_suffix(from_t)
        if self.dict_suffix(to_t) != "Dyn":
            raise CompileError("cannot convert %r to %r" % (from_t, to_t))
        return {"I64": "fl_dict_I64_to_Dyn", "F64": "fl_dict_F64_to_Dyn",
                "Str": "fl_dict_Str_to_Dyn"}[fs]

    def list_new(self, t):
        return {"I64": "list_I64_new()", "F64": "list_F64_new()",
                "Str": "list_Str_new()", "Dyn": "list_Dyn_new()",
                "Pair": "list_ListDyn_new()"}[self._list_storage(t)]

    def to_value(self, code, t):
        if t == I64:
            return "v_i64(%s)" % code
        if t == F64:
            return "v_f64(%s)" % code
        if t == BOOL:
            return "v_bool(%s)" % code
        if t == STR:
            return "v_str(%s)" % code
        if t == DYN:
            return code
        if is_container(t):
            return "%s(%s)" % (self._box_fn(t), code)
        raise CompileError("cannot box %r" % (t,))

    def from_value(self, code, t):
        if t == I64:
            return "v_to_i64(%s)" % code
        if t == F64:
            return "v_to_f64(%s)" % code
        if t == BOOL:
            return "v_to_bool(%s)" % code
        if t == STR:
            return "v_to_str(%s)" % code
        if is_container(t):
            return "%s(%s)" % (self._unbox_fn(t), code)
        return code

    def convert(self, code, from_t, to_t):
        if from_t == to_t or from_t is None or to_t is None:
            return code
        if to_t == DYN:
            return self.to_value(code, from_t)
        if from_t == DYN:
            return self.from_value(code, to_t)
        if is_list(from_t) and is_list(to_t):
            # same storage class -> identical C representation
            if self._list_storage(from_t) == self._list_storage(to_t):
                return code
            return "%s(%s)" % (self._list_converter(from_t, to_t), code)
        if is_dict(from_t) and is_dict(to_t):
            # e.g. ("dict", ("list", I64)) and ("dict", DYN) are both
            # FlDict_Dyn*; only typed->Dyn storage changes need a copy
            if self.dict_suffix(from_t) == self.dict_suffix(to_t):
                return code
            return "%s(%s)" % (self._dict_converter(from_t, to_t), code)
        if from_t == I64 and to_t == F64:
            return "((double)(%s))" % code
        if from_t == F64 and to_t == I64:
            return "((int64_t)(%s))" % code
        if from_t == BOOL and to_t in (I64, F64):
            return "(%s(%s))" % ("(int64_t)" if to_t == I64 else "(double)", code)
        raise CompileError("cannot convert %r to %r" % (from_t, to_t))

    def truthy(self, code, t):
        if t == BOOL:
            return "(%s)" % code
        if t == I64:
            return "((%s) != 0)" % code
        if t == F64:
            return "((%s) != 0.0)" % code
        if t == STR:
            return "((%s)[0] != '\\0')" % code
        if t == DYN:
            return "value_truthy(%s)" % code
        if is_list(t):
            return "((%s)->len != 0)" % code
        if is_dict(t):
            return "((%s)->len != 0)" % code
        raise CompileError("cannot test truthiness of %r" % (t,))

    def var_ref(self, name, finfo, is_global):
        """C code to read/write a variable, honoring comprehension scopes,
        closure captures, heap cells, and param/local-over-global shadowing.
        A top-level function named by itself is a first-class closure value."""
        if name in self.comp_vars:
            return name
        if not is_global and finfo is not None:
            if name in self.capture_map:
                return "(*_fl_env->%s)" % name
            if name in self.cell_vars:
                return "(*_cell_%s)" % name
            if name in finfo["params"] or name in finfo["locals"]:
                return name
        if name in self.globals:
            return "_g_" + name
        if name in self.funcs and not self.funcs[name].get("nested"):
            return "(FlClosure){ %s, 0 }" % self.funcs[name]["cname"]
        return name

    def var_type(self, name, finfo, is_global):
        if not is_global and finfo is not None:
            if name in finfo["params"]:
                return finfo["param_types"][finfo["params"].index(name)]
            if name in self.capture_map:
                return self.capture_type(self.capture_map[name], name)
            if name in finfo["locals"]:
                return finfo["locals"][name]
        if name in self.globals:
            return self.globals[name]
        raise CompileError("no type for variable '%s'" % name)

    def capture_type(self, qn, name):
        f = self.funcs[qn]
        if name in f["params"]:
            return f["param_types"][f["params"].index(name)]
        return f["locals"][name]

    # -- entry --------------------------------------------------------------
    def gen(self):
        self.w('#include "flare_rt.h"')
        self.w("")
        self.w("static FlListStr *_flare_argv;")
        # class structs (before globals and methods that use them)
        for cname, cls in self.classes.items():
            self.w("typedef struct {")
            for aname, atype in cls["attrs"].items():
                self.w("    %s %s;" % (self.ctype(atype), aname))
            self.w("} Class_%s;" % cname)
            self.w("")
        for name, t in self.globals.items():
            self.w("static %s _g_%s;" % (self.ctype(t), name))
        if self.globals:
            self.w("")
        # closure environments (before forward declarations)
        for qn, f in self.funcs.items():
            if not f["nested"]:
                continue
            self.w("typedef struct {")
            for (cname, defining_qn) in f["captures"]:
                vt = self.capture_type(defining_qn, cname)
                self.w("    %s *%s;" % (self.ctype(vt), cname))
            self.w("} Env_%s;" % qn)
            self.w("")
        for qn, f in self.funcs.items():
            params = ", ".join(
                "%s %s" % (self.ctype(pt), pn)
                for pn, pt in zip(f["params"], f["param_types"]))
            if f["nested"]:
                envp = "Env_%s *_fl_env" % f["qname"]
                params = envp + (", " + params if params else "")
            self.w("static %s %s(%s);" % (self.ctype(f["ret"]), f["cname"], params or "void"))
        if self.funcs:
            self.w("")
        for qn, f in self.funcs.items():
            self.gen_func(qn, f)
        self.w("int main(int argc, char **argv) {")
        self.w("    _flare_anchor();")
        self.w("    _flare_argv = list_Str_new();")
        self.w("    for (int _ai = 0; _ai < argc; _ai++)")
        self.w("        list_Str_append(_flare_argv, argv[_ai]);")
        for s in self.program.stmts:
            if not isinstance(s, (N.FuncDef, N.ClassDef)):
                self.gen_stmt(s, None, True)
        self.w("    return 0;")
        self.w("}")
        return "\n".join(self.out) + "\n"

    def gen_func(self, name, f):
        cname = f["cname"]
        params = ", ".join(
            "%s %s" % (self.ctype(pt), pn)
            for pn, pt in zip(f["params"], f["param_types"]))
        if f["nested"]:
            envp = "Env_%s *_fl_env" % f["qname"]
            params = envp + (", " + params if params else "")
        self.w("static %s %s(%s) {" % (self.ctype(f["ret"]), cname, params or "void"))
        self.guarded = bool(f.get("recursive"))
        if self.guarded:
            self.w("    _flare_enter();")
        self.declared = set(f["params"])
        self.try_stack = []
        self.cell_vars = set(f["cell_vars"])
        self.capture_map = {cn: dq for (cn, dq) in f["captures"]}
        self.w("    bool _fl_did_return_ = false;")
        if f["ret"] != VOID:
            self.w("    %s _fl_retval_;" % self.ctype(f["ret"]))
        # Hoist every local to function top (zero-initialized) so that
        # assignments inside if/while/for/try bodies stay visible after
        # the block, matching Python's function scoping. Variables captured
        # by nested functions become heap cells shared via environments.
        for lname, lt in f["locals"].items():
            if lname in f["params"]:
                continue
            ct = self.ctype(lt)
            if lname in self.cell_vars:
                self.w("    %s *_cell_%s = (%s *)malloc(sizeof(%s));"
                       % (ct, lname, ct, ct))
                self.w("    *_cell_%s = %s;" % (lname, self.zero_init(lt)))
            else:
                self.w("    %s %s = %s;" % (ct, lname, self.zero_init(lt)))
            self.declared.add(lname)
        for pn, pt in zip(f["params"], f["param_types"]):
            if pn in self.cell_vars:
                ct = self.ctype(pt)
                self.w("    %s *_cell_%s = (%s *)malloc(sizeof(%s));"
                       % (ct, pn, ct, ct))
                self.w("    *_cell_%s = %s;" % (pn, pn))
        self.cur_func = f
        for s in f["node"].body:
            self.gen_stmt(s, f, False)
        self.cur_func = None
        self.cell_vars = set()
        self.capture_map = {}
        self.w("}")
        self.w("")

    def zero_init(self, t):
        if t == I64:
            return "0"
        if t == F64:
            return "0.0"
        if t == BOOL:
            return "false"
        if t == STR:
            return 'flare_strdup("")'
        if t == DYN:
            return "(Value){0}"
        if t == RANGE:
            return "(FlRange){0, 0, 1}"
        if is_closure(t):
            return "(FlClosure){0}"
        if is_list(t):
            return self.list_new(t)
        if is_dict(t):
            return self.dict_new(t)
        raise CompileError("no zero value for %r" % (t,))

    # -- statements -----------------------------------------------------------
    def gen_stmt(self, s, finfo, is_global):
        if isinstance(s, N.Assign):
            # Store into the variable's declared (possibly widened) type, not
            # the RHS expression's type: the fixed point may widen the variable
            # (e.g. `total = 0` later combined with a boxed Value) while the RHS
            # keeps its narrow type. convert() boxes/widens to match storage.
            t = self.var_type(s.target, finfo, is_global)
            val = self.convert(self.gen_expr(s.value, finfo, is_global),
                               s.value.inferred, t)
            cname = self.var_ref(s.target, finfo, is_global)
            if is_global or s.target in self.declared or s.target in self.capture_map:
                self.w("    %s = %s;" % (cname, val))
            else:
                self.w("    %s %s = %s;" % (self.ctype(t), cname, val))
                self.declared.add(s.target)
        elif isinstance(s, N.SetItem):
            dt = self.var_type(s.target, finfo, is_global)
            cname = self.var_ref(s.target, finfo, is_global)
            if is_list(dt):
                elt = dt[1]
                kc = self.convert(self.gen_expr(s.key, finfo, is_global),
                                  s.key.inferred, I64)
                if self._list_storage(dt) == "Pair":
                    vc = self.convert(self.gen_expr(s.value, finfo, is_global),
                                      s.value.inferred, ("list", DYN))
                    self.w("    fl_set_ListDyn(%s, %s, %s);" % (cname, kc, vc))
                else:
                    suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
                    vc = self.convert(self.gen_expr(s.value, finfo, is_global),
                                      s.value.inferred, elt)
                    if elt == BOOL or is_container(elt):
                        vc = self.to_value(vc, elt)
                    self.w("    fl_set_%s(%s, %s, %s);" % (suf, cname, kc, vc))
            elif is_dict(dt):
                suf = self.dict_suffix(dt)
                vt = dt[1]
                kc = self.gen_expr(s.key, finfo, is_global)
                if s.key.inferred == DYN:
                    kc = "v_to_str(%s)" % kc
                vc = self.convert(self.gen_expr(s.value, finfo, is_global),
                                  s.value.inferred, vt)
                if vt == BOOL or is_container(vt):
                    vc = self.to_value(vc, vt)
                self.w("    dict_%s_set(%s, %s, %s);" % (suf, cname, kc, vc))
            elif dt == DYN:
                # fully dynamic target: dispatch at runtime
                kt = s.key.inferred
                kc = self.gen_expr(s.key, finfo, is_global)
                vc = self.to_value(self.gen_expr(s.value, finfo, is_global),
                                   s.value.inferred)
                if kt == STR:
                    self.w("    value_dict_set(%s, %s, %s);" % (cname, kc, vc))
                elif kt == I64 or kt == BOOL:
                    kc = self.convert(kc, kt, I64)
                    self.w("    value_list_set(%s, %s, %s);" % (cname, kc, vc))
                else:
                    if kt is not None:
                        kc = self.to_value(kc, kt)
                    self.w("    value_setitem(%s, %s, %s);" % (cname, kc, vc))
            else:
                raise CompileError("line %d: cannot set item on %r"
                                   % (s.line, dt))
        elif isinstance(s, N.SetAttr):
            obj = self.gen_expr(s.obj, finfo, is_global)
            ot = s.obj.inferred
            atype = None
            if is_class(ot):
                atype = self.classes[ot[1]]["attrs"].get(s.attr)
            vc = self.gen_expr(s.value, finfo, is_global)
            if atype is not None:
                vc = self.convert(vc, s.value.inferred, atype)
            self.w("    (%s)->%s = %s;" % (obj, s.attr, vc))
        elif isinstance(s, N.Return):
            if self.try_stack:
                self.gen_try_return(s, finfo, is_global)
                return
            rt = finfo["ret"]
            leave = "    _flare_leave();\n" if self.guarded else ""
            if s.value is None:
                self.w(leave + "    return;")
            elif self.guarded and _has_call(s.value):
                # evaluate BEFORE _flare_leave so the guard nests around
                # recursive calls (and defeats tail-call frame reuse)
                val = self.gen_expr(s.value, finfo, is_global)
                tmp = self.tmp()
                self.w("    %s %s = %s;" % (
                    self.ctype(rt), tmp,
                    self.convert(val, s.value.inferred, rt)))
                self.w(leave + "    return %s;" % tmp)
            else:
                val = self.convert(self.gen_expr(s.value, finfo, is_global),
                                   s.value.inferred, rt)
                self.w(leave + "    return %s;" % val)
        elif isinstance(s, N.If):
            first = True
            for cond, body in s.branches:
                kw = "if" if first else "else if"
                first = False
                c = self.truthy(self.gen_expr(cond, finfo, is_global), cond.inferred)
                self.w("    %s (%s) {" % (kw, c))
                for b in body:
                    self.gen_stmt(b, finfo, is_global)
                self.w("    }", )
            if s.else_body:
                self.w("    else {")
                for b in s.else_body:
                    self.gen_stmt(b, finfo, is_global)
                self.w("    }")
        elif isinstance(s, N.While):
            c = self.truthy(self.gen_expr(s.cond, finfo, is_global), s.cond.inferred)
            self.w("    while (%s) {" % c)
            for b in s.body:
                self.gen_stmt(b, finfo, is_global)
            self.w("    }")
        elif isinstance(s, N.For):
            self.gen_for(s, finfo, is_global)
        elif isinstance(s, N.Try):
            self.gen_try(s, finfo, is_global)
        elif isinstance(s, N.FuncDef):
            self.gen_nested_def(s, finfo, is_global)
        elif isinstance(s, N.ExprStmt):
            self.w("    %s;" % self.gen_expr(s.expr, finfo, is_global))
        else:
            raise CompileError("cannot generate %r" % s)

    def gen_nested_def(self, s, finfo, is_global):
        # `def inner(...): ...` inside a function: allocate the environment,
        # wire captured cells into it, and bind the closure value.
        f = self.funcs[s.qualname]
        if not f["nested"]:
            # top-level function defined inside top-level control flow: the
            # definition lives at file scope; the name already resolves to
            # the function value, so there is nothing to do at runtime.
            return
        qn = f["qname"]
        env_tmp = self.tmp()
        self.w("    Env_%s *%s = (Env_%s *)malloc(sizeof(Env_%s));"
               % (qn, env_tmp, qn, qn))
        for (cname, defining_qn) in f["captures"]:
            if defining_qn == finfo["qname"]:
                cell = "_cell_%s" % cname
            else:
                # forwarded through our own environment
                cell = "_fl_env->%s" % cname
            self.w("    %s->%s = %s;" % (env_tmp, cname, cell))
        closure = "(FlClosure){ %s, %s }" % (f["cname"], env_tmp)
        lv = self.var_ref(s.name, finfo, is_global)
        self.w("    %s = %s;" % (lv, closure))

    def gen_indirect_call(self, e, finfo, is_global):
        # call through a closure-typed variable
        cl = self.var_ref(e.func, finfo, is_global)
        return self.gen_closure_call(e.indirect, cl, e, finfo, is_global)

    def gen_instantiation(self, e, finfo, is_global):
        # Point(...) -> malloc the struct, run __init__, yield the pointer
        cname = e.inst_class
        cls = self.classes[cname]
        tmp = self.tmp()
        parts = ["Class_%s *%s = (Class_%s *)malloc(sizeof(Class_%s));"
                 % (cname, tmp, cname, cname)]
        if "__init__" in cls["methods"]:
            mf = cls["methods"]["__init__"]
            eargs = getattr(e, "effective_args", e.args)
            args = [self.convert(self.gen_expr(a, finfo, is_global), a.inferred, pt)
                    for a, pt in zip(eargs, mf["param_types"][1:])]
            argstr = ", ".join([tmp] + args)
            parts.append("%s(%s);" % (mf["cname"], argstr))
        parts.append(tmp + ";")
        return "({ %s })" % " ".join(parts)

    def gen_method_call(self, e, finfo, is_global):
        # obj.method(args) -> Class_method(obj, args...)
        cname = e.method_class
        mname = e.method_name
        mf = self.classes[cname]["methods"][mname]
        eargs = getattr(e, "effective_args", e.args)
        self_arg = self.gen_expr(eargs[0], finfo, is_global)
        args = [self.convert(self.gen_expr(a, finfo, is_global), a.inferred, pt)
                for a, pt in zip(eargs[1:], mf["param_types"][1:])]
        argstr = ", ".join([self_arg] + args)
        call = "%s(%s)" % (mf["cname"], argstr)
        if mf["ret"] == VOID:
            return "(%s, 0)" % call
        return call

    def gen_callobj(self, e, finfo, is_global):
        # call through a closure-valued expression: funcs[0](), f()()
        cl = self.gen_expr(e.func, finfo, is_global)
        return self.gen_closure_call(e.indirect, cl, e, finfo, is_global)

    def gen_closure_call(self, qn, cl, e, finfo, is_global):
        f = self.funcs[qn]
        eargs = getattr(e, "effective_args", e.args)
        cargs = [self.convert(self.gen_expr(a, finfo, is_global), a.inferred, pt)
                 for a, pt in zip(eargs, f["param_types"])]
        argstr = ", ".join(cargs)
        if not f["nested"]:
            # top-level function value: direct call, no environment
            call = "%s(%s)" % (f["cname"], argstr)
            if f["ret"] == VOID:
                return "(%s, 0)" % call
            return call
        params = ", ".join(self.ctype(pt) for pt in f["param_types"])
        sig = "%s(*)(Env_%s *_fl_env%s)" % (
            self.ctype(f["ret"]), qn, ", " + params if params else "")
        call = "((%s)(%s).fn)((%s).env%s)" % (sig, cl, cl, ", " + argstr if argstr else "")
        if f["ret"] == VOID:
            return "(%s, 0)" % call
        return call

    # -- try/except/finally -------------------------------------------------
    def gen_try(self, s, finfo, is_global):
        n = self._try_id
        self._try_id += 1
        has_finally = bool(s.finally_body)
        lbl = "__fl_tryfin_%d" % n
        ctx = {"has_finally": has_finally, "label": lbl,
               "saved": "_fl_sv_%d" % n}
        self.w("    {")
        self.w("    FlHandler _fl_h_%d;" % n)
        self.w("    _fl_h_%d.prev = _flare_top;" % n)
        self.w("    _fl_h_%d.saved_depth = _flare_depth;" % n)
        self.w("    _flare_top = &_fl_h_%d;" % n)
        self.w("    FlHandler *%s = _fl_h_%d.prev;" % (ctx["saved"], n))
        self.w("    const char *_fl_et_%d = 0;" % n)
        self.w("    const char *_fl_em_%d = 0;" % n)
        self.w("    if (setjmp(_fl_h_%d.jb) == 0) {" % n)
        self.try_stack.append(ctx)
        for b in s.body:
            self.gen_stmt(b, finfo, is_global)
        self.try_stack.pop()
        self.w("    _flare_top = _fl_h_%d.prev;" % n)
        self.w("    } else {")
        self.w("    _fl_et_%d = _flare_errtype;" % n)
        self.w("    _fl_em_%d = _flare_errmsg;" % n)
        if s.handlers:
            first = True
            for (exc, var, hbody) in s.handlers:
                kw = "if" if first else "else if"
                first = False
                self.w("    %s (%s) {" % (kw, self.except_cond(exc, n)))
                if var is not None:
                    # the handler variable binds the error message (a string)
                    cvar = ("_g_" + var) if is_global else var
                    self.w("    %s = flare_strdup(_fl_em_%d);" % (cvar, n))
                self.try_stack.append(ctx)
                for b in hbody:
                    self.gen_stmt(b, finfo, is_global)
                self.try_stack.pop()
                self.w("    }")
            self.w("    else {")
            self.gen_finally(s, finfo, is_global)
            self.w("    fl_reraise();")
            self.w("    }")
        else:
            self.gen_finally(s, finfo, is_global)
            self.w("    fl_reraise();")
        self.w("    }")
        self.w("    %s:;" % lbl)
        self.gen_finally(s, finfo, is_global)
        if finfo is not None:
            # propagate an in-flight return from the try body outward
            target = None
            for oc in reversed(self.try_stack):
                if oc["has_finally"]:
                    target = oc["label"]
                    break
            if target is not None:
                self.w("    if (_fl_did_return_) goto %s;" % target)
            elif finfo["ret"] == VOID:
                self.w("    if (_fl_did_return_) return;")
            else:
                self.w("    if (_fl_did_return_) return _fl_retval_;")
        self.w("    }")

    def gen_finally(self, s, finfo, is_global):
        # NOTE: the current try is not on try_stack here, so a `return`
        # inside finally targets enclosing trys (never loops to itself).
        for b in s.finally_body:
            self.gen_stmt(b, finfo, is_global)

    def except_cond(self, exc, n):
        if exc is None or exc in ("Exception", "BaseException"):
            return "1"
        return '(strcmp(_fl_et_%d, "%s") == 0)' % (n, exc)

    def gen_try_return(self, s, finfo, is_global):
        # `return` inside a try: pop handlers, run enclosing finally blocks
        # (via goto), then return. The return value is evaluated BEFORE
        # _flare_leave so recursive calls still nest the depth guard.
        rt = finfo["ret"]
        n = self._try_id
        self._try_id += 1
        if s.value is not None:
            v = self.convert(self.gen_expr(s.value, finfo, is_global),
                             s.value.inferred, rt)
            self.w("    %s _fl_rv_%d = %s;" % (self.ctype(rt), n, v))
        self.w("    _flare_top = %s;" % self.try_stack[0]["saved"])
        if self.guarded:
            self.w("    _flare_leave();")
        if s.value is not None:
            self.w("    _fl_retval_ = _fl_rv_%d;" % n)
        self.w("    _fl_did_return_ = true;")
        target = None
        for ctx in reversed(self.try_stack):
            if ctx["has_finally"]:
                target = ctx["label"]
                break
        if target is not None:
            self.w("    goto %s;" % target)
        elif rt == VOID:
            self.w("    return;")
        else:
            self.w("    return _fl_retval_;")

    def gen_for(self, s, finfo, is_global):
        it = s.iter_expr
        var = s.var
        lv = self.var_ref(var, finfo, is_global)
        # The loop variable reuses its hoisted local (or global) so the
        # last value leaks after the loop, like Python.
        it_t = it.inferred
        if (isinstance(it, N.Call) and it.func == "range") or it_t == RANGE:
            # range loop: use the FlRange value (handles 1-3 args and step)
            if isinstance(it, N.Call) and it.func == "range":
                rng = self.gen_expr(it, finfo, is_global)
            else:
                rng = self.gen_expr(it, finfo, is_global)
            rtmp = self.tmp()
            self.w("    FlRange %s = %s;" % (rtmp, rng))
            # handle step (positive or negative)
            if is_global or var in self.declared:
                self.w("    for (%s = %s.lo; %s.step > 0 ? %s < %s.hi : %s > %s.hi; %s += %s.step) {"
                       % (lv, rtmp, rtmp, lv, rtmp, lv, rtmp, lv, rtmp))
            else:
                self.declared.add(var)
                self.w("    for (int64_t %s = %s.lo; %s.step > 0 ? %s < %s.hi : %s > %s.hi; %s += %s.step) {"
                       % (lv, rtmp, rtmp, lv, rtmp, lv, rtmp, lv, rtmp))
            for b in s.body:
                self.gen_stmt(b, finfo, is_global)
            self.w("    }")
            return
        lt = it.inferred
        if lt == DYN:
            # Fully dynamic iterable (e.g. a nested container read through a
            # variable the fixpoint left dynamic): dispatch on the boxed
            # list at runtime. Clean TypeError if it isn't a list.
            return self.gen_for_dyn(s, var, lv, finfo, is_global)
        if not is_list(lt):
            raise CompileError("line %d: for loop needs range() or a list" % s.line)
        elt_t = lt[1]
        lc = self.gen_expr(it, finfo, is_global)
        idx = self.tmp()
        self.w("    for (int64_t %s = 0; %s < (%s)->len; %s++) {" % (idx, idx, lc, idx))
        elem = "(%s)->data[%s]" % (lc, idx)
        if self._list_storage(lt) == "Dyn" and is_container(elt_t):
            # FlListDyn stores Values; unbox to the static element type
            elem = "%s(%s)" % (self._unbox_fn(elt_t), elem)
        elif elt_t == BOOL:
            elem = "v_to_bool(%s)" % elem
        # Convert to the variable's declared (storage) type: the fixpoint may
        # have widened it (e.g. to DYN) after s.var_type was last set, and the
        # function-local hoist declares it with that widened type.
        try:
            vt = self.var_type(var, finfo, is_global)
        except CompileError:
            vt = s.var_type
        elem = self.convert(elem, elt_t, vt)
        if is_global or var in self.declared:
            self.w("        %s = %s;" % (lv, elem))
        else:
            self.declared.add(var)
            self.w("        %s %s = %s;" % (self.ctype(vt), lv, elem))
        for b in s.body:
            self.gen_stmt(b, finfo, is_global)
        self.w("    }")

    def gen_for_dyn(self, s, var, lv, finfo, is_global):
        # `for v in <dyn>:` — the iterable is a boxed Value; its list
        # storage is only known at runtime.
        it = s.iter_expr
        lc = self.gen_expr(it, finfo, is_global)
        idx = self.tmp()
        ltmp = self.tmp()
        ntmp = self.tmp()
        self.w("    Value %s = %s;" % (ltmp, lc))
        self.w("    int64_t %s = fl_dyn_iter_len(%s);" % (ntmp, ltmp))
        self.w("    for (int64_t %s = 0; %s < %s; %s++) {"
               % (idx, idx, ntmp, idx))
        elem = "fl_dyn_iter_elem(%s, %s)" % (ltmp, idx)
        try:
            vt = self.var_type(var, finfo, is_global)
        except CompileError:
            vt = s.var_type
        elem = self.convert(elem, DYN, vt)
        if is_global or var in self.declared:
            self.w("        %s = %s;" % (lv, elem))
        else:
            self.declared.add(var)
            self.w("        %s %s = %s;" % (self.ctype(vt), lv, elem))
        for b in s.body:
            self.gen_stmt(b, finfo, is_global)
        self.w("    }")

    def global_names_set(self):
        return set(self.globals.keys())

    # -- expressions ------------------------------------------------------------
    def gen_expr(self, e, finfo, is_global):
        if isinstance(e, N.IntLit):
            return "(int64_t)%d" % e.value
        if isinstance(e, N.FloatLit):
            return "(%r)" % e.value
        if isinstance(e, N.StrLit):
            return "flare_strdup(%s)" % self.c_str(e.value)
        if isinstance(e, N.BoolLit):
            return "true" if e.value else "false"
        if isinstance(e, N.Name):
            if e.id == "PI":
                return "FL_PI"
            if e.id == "E":
                return "FL_E"
            return self.var_ref(e.id, finfo, is_global)
        if isinstance(e, N.ListLit):
            return self.gen_list(e, finfo, is_global)
        if isinstance(e, N.DictLit):
            return self.gen_dict(e, finfo, is_global)
        if isinstance(e, N.FStr):
            return self.gen_fstr(e, finfo, is_global)
        if isinstance(e, N.ListComp):
            return self.gen_listcomp(e, finfo, is_global)
        if isinstance(e, N.DictComp):
            return self.gen_dictcomp(e, finfo, is_global)
        if isinstance(e, N.Index):
            return self.gen_index(e, finfo, is_global)
        if isinstance(e, N.Slice):
            return self.gen_slice(e, finfo, is_global)
        if isinstance(e, N.UnaryOp):
            return self.gen_unary(e, finfo, is_global)
        if isinstance(e, N.BinOp):
            return self.gen_binop(e, finfo, is_global)
        if isinstance(e, N.ChainCompare):
            return self.gen_chain(e, finfo, is_global)
        if isinstance(e, N.Call):
            return self.gen_call(e, finfo, is_global)
        if isinstance(e, N.CallObj):
            return self.gen_callobj(e, finfo, is_global)
        if isinstance(e, N.GetAttr):
            obj = self.gen_expr(e.obj, finfo, is_global)
            return "(%s)->%s" % (obj, e.attr)
        raise CompileError("cannot generate %r" % e)

    def c_str(self, s):
        return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def gen_list(self, e, finfo, is_global):
        t = e.inferred
        new = self.list_new(t)
        tmp = self.tmp()
        self.w("    %s %s = %s;" % (self.ctype(t), tmp, new))
        if self._list_storage(t) == "Pair":
            # list of enumerate()/zip() pairs: inner lists are FlListDyn*
            for x in e.elts:
                xc = self.convert(self.gen_expr(x, finfo, is_global),
                                  x.inferred, ("list", DYN))
                self.w("    list_ListDyn_append(%s, %s);" % (tmp, xc))
            return tmp
        elt_t = t[1] if is_list(t) else DYN
        for x in e.elts:
            xc = self.convert(self.gen_expr(x, finfo, is_global), x.inferred, elt_t)
            app = {I64: "list_I64_append", F64: "list_F64_append",
                   STR: "list_Str_append"}.get(elt_t, "list_Dyn_append")
            if elt_t == BOOL or is_container(elt_t):
                # FlListDyn stores Values: box bools and nested containers
                # (convert() already boxed scalars when elt_t is DYN)
                xc = self.to_value(xc, elt_t)
            self.w("    %s(%s, %s);" % (app, tmp, xc))
        # NOTE: emitted as statements; wrap via statement-expression below
        return tmp

    def gen_fstr(self, e, finfo, is_global):
        # build the interpolated string via str_concat pieces
        tmp = self.tmp()
        self.w("    char *%s = flare_strdup(\"\");" % tmp)
        for kind, p in e.parts:
            if kind == "lit":
                if not p:
                    continue
                self.w("    %s = str_concat(%s, %s);" % (tmp, tmp, self.c_str(p)))
            else:
                t = p.inferred
                c = self.gen_expr(p, finfo, is_global)
                piece = self.tmp()
                self.w("    char *%s = %s;" % (piece, self.fstr_piece(c, t, p.line)))
                self.w("    %s = str_concat(%s, %s);" % (tmp, tmp, piece))
        return tmp

    def fstr_piece(self, c, t, line):
        if t == I64:
            return "fl_str_i64(%s)" % c
        if t == F64:
            return "fl_str_f64(%s)" % c
        if t == BOOL:
            return "fl_str_bool(%s)" % c
        if t == STR:
            return "(%s)" % c
        if t == DYN:
            return "fl_str_value(%s)" % c
        if t == RANGE:
            return "fl_str_range(%s)" % c
        if is_closure(t):
            return 'flare_strdup("<function>")'
        if is_class(t):
            return 'fl_str_class("%s", (void*)(%s))' % (t[1], c)
        if is_list(t):
            if self._list_storage(t) == "Pair":
                return "fl_str_list_PAIR(%s)" % c
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(t[1], "Dyn")
            return "fl_str_list_%s(%s)" % (suf, c)
        if is_dict(t):
            return "fl_str_dict_%s(%s)" % (self.dict_suffix(t), c)
        raise CompileError("line %d: cannot interpolate %r in f-string" % (line, t))

    def gen_comp_for(self, var, it, finfo, is_global):
        # emit one comprehension loop; the loop variable is declared in the
        # comprehension's own C block so it never leaks (unlike for loops)
        if isinstance(it, N.Call) and it.func == "range":
            args = it.args
            if len(args) == 1:
                lo = "0"
                hi = self.gen_expr(args[0], finfo, is_global)
            else:
                lo = self.gen_expr(args[0], finfo, is_global)
                hi = self.gen_expr(args[1], finfo, is_global)
            self.w("    for (int64_t %s = %s; %s < %s; %s++) {" % (var, lo, var, hi, var))
            return
        itt = it.inferred
        if not is_list(itt):
            raise CompileError("line %d: comprehension needs range() or a list" % it.line)
        elt_t = itt[1]
        itc = self.gen_expr(it, finfo, is_global)
        ltmp = self.tmp()
        self.w("    %s %s = %s;" % (self.ctype(itt), ltmp, itc))
        idx = self.tmp()
        self.w("    for (int64_t %s = 0; %s < (%s)->len; %s++) {" % (idx, idx, ltmp, idx))
        elem = "(%s)->data[%s]" % (ltmp, idx)
        if self._list_storage(itt) == "Dyn" and is_container(elt_t):
            elem = "%s(%s)" % (self._unbox_fn(elt_t), elem)
        elif elt_t == BOOL and self._list_storage(itt) == "Dyn":
            elem = "v_to_bool(%s)" % elem
        self.w("    %s %s = %s;" % (self.ctype(elt_t), var, elem))

    def gen_comp_clauses(self, clauses, finfo, is_global):
        for cl in clauses:
            if cl[0] == "for":
                _kind, var, it = cl
                self.gen_comp_for(var, it, finfo, is_global)
                self.comp_vars.append(var)
            else:
                cond = cl[1]
                c = self.truthy(self.gen_expr(cond, finfo, is_global), cond.inferred)
                self.w("    if (%s) {" % c)
        # closings are emitted by the caller (after the element), then it
        # must pop comp_vars for the "for" clauses in reverse order
        return [cl[1] for cl in clauses if cl[0] == "for"]

    def gen_listcomp(self, e, finfo, is_global):
        t = e.inferred
        tmp = self.tmp()
        self.w("    %s %s;" % (self.ctype(t), tmp))
        self.w("    {")
        self.w("    %s = %s;" % (tmp, self.list_new(t)))
        bound = self.gen_comp_clauses(e.clauses, finfo, is_global)
        elt_t = t[1] if is_list(t) else DYN
        if self._list_storage(t) == "Pair":
            xc = self.convert(self.gen_expr(e.elt, finfo, is_global),
                              e.elt.inferred, ("list", DYN))
            self.w("    list_ListDyn_append(%s, %s);" % (tmp, xc))
        else:
            xc = self.convert(self.gen_expr(e.elt, finfo, is_global),
                              e.elt.inferred, elt_t)
            app = {I64: "list_I64_append", F64: "list_F64_append",
                   STR: "list_Str_append"}.get(elt_t, "list_Dyn_append")
            if elt_t == BOOL or is_container(elt_t):
                xc = self.to_value(xc, elt_t)
            self.w("    %s(%s, %s);" % (app, tmp, xc))
        for _cl in e.clauses:
            self.w("    }")
        for _v in bound:
            self.comp_vars.pop()
        self.w("    }")
        return tmp

    def gen_dictcomp(self, e, finfo, is_global):
        t = e.inferred
        tmp = self.tmp()
        suf = self.dict_suffix(t)
        self.w("    %s %s;" % (self.ctype(t), tmp))
        self.w("    {")
        self.w("    %s = %s;" % (tmp, self.dict_new(t)))
        bound = self.gen_comp_clauses(e.clauses, finfo, is_global)
        vt = t[1] if is_dict(t) else DYN
        kc = self.gen_expr(e.key, finfo, is_global)
        vc = self.convert(self.gen_expr(e.value, finfo, is_global),
                          e.value.inferred, vt)
        if vt == BOOL or is_container(vt):
            vc = self.to_value(vc, vt)
        self.w("    dict_%s_set(%s, %s, %s);" % (suf, tmp, kc, vc))
        for _cl in e.clauses:
            self.w("    }")
        for _v in bound:
            self.comp_vars.pop()
        self.w("    }")
        return tmp

    def dict_new(self, t):
        e = t[1] if is_dict(t) else DYN
        if e == I64:
            return "dict_I64_new()"
        if e == F64:
            return "dict_F64_new()"
        if e == STR:
            return "dict_Str_new()"
        return "dict_Dyn_new()"

    def dict_suffix(self, t):
        e = t[1] if is_dict(t) else DYN
        return {I64: "I64", F64: "F64", STR: "Str"}.get(e, "Dyn")

    def gen_dict(self, e, finfo, is_global):
        t = e.inferred
        tmp = self.tmp()
        vt = t[1] if is_dict(t) else DYN
        suf = self.dict_suffix(t)
        self.w("    %s %s = %s;" % (self.ctype(t), tmp, self.dict_new(t)))
        for k, v in zip(e.keys, e.values):
            kc = self.gen_expr(k, finfo, is_global)
            vc = self.convert(self.gen_expr(v, finfo, is_global), v.inferred, vt)
            if vt == BOOL or is_container(vt):
                # dict_Dyn_set takes a Value; box bools and nested containers
                # (convert() already boxed scalars when vt is DYN)
                vc = self.to_value(vc, vt)
            self.w("    dict_%s_set(%s, %s, %s);" % (suf, tmp, kc, vc))
        return tmp

    def gen_index(self, e, finfo, is_global):
        obj = self.gen_expr(e.obj, finfo, is_global)
        ot = e.obj.inferred
        if is_dict(ot):
            suf = self.dict_suffix(ot)
            it = e.index.inferred
            key = self.gen_expr(e.index, finfo, is_global)
            if it == DYN:
                key = "v_to_str(%s)" % key
            code = "dict_%s_get(%s, %s)" % (suf, obj, key)
            vt = ot[1]
            if suf == "Dyn" and is_container(vt):
                # dict_Dyn_get returns a Value; unbox to the static value type
                code = "%s(%s)" % (self._unbox_fn(vt), code)
            elif vt == BOOL:
                code = "v_to_bool(%s)" % code
            return code
        if ot == STR:
            idx = self.convert(self.gen_expr(e.index, finfo, is_global),
                               e.index.inferred, I64)
            return "fl_str_index(%s, %s)" % (obj, idx)
        if is_list(ot):
            idx = self.convert(self.gen_expr(e.index, finfo, is_global),
                               e.index.inferred, I64)
            if self._list_storage(ot) == "Pair":
                # list of lists (enumerate/zip): return the inner list
                return "fl_index_ListDyn(%s, %s)" % (obj, idx)
            elt = ot[1]
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
            code = "fl_index_%s(%s, %s)" % (suf, obj, idx)
            if elt == BOOL:
                return "v_to_bool(%s)" % code
            if is_container(elt):
                # fl_index_Dyn returns a Value; unbox to the static elt type
                return "%s(%s)" % (self._unbox_fn(elt), code)
            return code
        if ot == DYN:
            it = e.index.inferred
            if it == STR:
                return "value_dict_get(%s, %s)" % (
                    obj, self.gen_expr(e.index, finfo, is_global))
            if it == I64 or it == BOOL:
                idx = self.convert(self.gen_expr(e.index, finfo, is_global),
                                   it, I64)
                return "value_index(%s, %s)" % (obj, idx)
            key = self.gen_expr(e.index, finfo, is_global)
            if it is not None:
                key = self.to_value(key, it)
            return "value_subscript(%s, %s)" % (obj, key)
        raise CompileError("line %d: cannot index %r" % (e.line, ot))

    def gen_slice(self, e, finfo, is_global):
        obj = self.gen_expr(e.obj, finfo, is_global)
        ot = e.obj.inferred

        def part(node, default):
            if node is None:
                return default, "0"
            c = self.convert(self.gen_expr(node, finfo, is_global),
                             node.inferred, I64)
            return c, "1"

        lo, has_lo = part(e.lo, "0")
        hi, has_hi = part(e.hi, "0")
        st, has_st = part(e.step, "1")
        if ot == STR:
            return "fl_str_slice(%s, %s, %s, %s, %s, %s, %s)" % (
                obj, lo, hi, st, has_lo, has_hi, has_st)
        if is_list(ot):
            if self._list_storage(ot) == "Pair":
                raise CompileError("line %d: cannot slice a list of pairs (v0)"
                                   % e.line)
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(ot[1], "Dyn")
            return "fl_slice_%s(%s, %s, %s, %s, %s, %s, %s)" % (
                suf, obj, lo, hi, st, has_lo, has_hi, has_st)
        raise CompileError("line %d: cannot slice %r" % (e.line, ot))

    def gen_unary(self, e, finfo, is_global):
        x = self.gen_expr(e.operand, finfo, is_global)
        t = e.operand.inferred
        if e.op == "not":
            return "(!%s)" % self.truthy(x, t)
        if t == DYN:
            return "value_neg(%s)" % x
        return "(-(%s))" % x

    def gen_binop(self, e, finfo, is_global):
        op = e.op
        lt, rt = e.left.inferred, e.right.inferred
        if op in ("and", "or"):
            # Python semantics: yield the deciding operand
            jt = e.inferred
            l = self.gen_expr(e.left, finfo, is_global)
            r = self.gen_expr(e.right, finfo, is_global)
            lc = self.convert(l, lt, jt)
            rc = self.convert(r, rt, jt)
            t = self.truthy(l, lt)
            if op == "or":
                return "((%s) ? (%s) : (%s))" % (t, lc, rc)
            return "((%s) ? (%s) : (%s))" % (t, rc, lc)
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return self.gen_compare(e, lt, rt, finfo, is_global)
        if op == "%":
            return self.gen_mod(e, lt, rt, finfo, is_global)
        if op == "in":
            return self.gen_in(e, lt, rt, finfo, is_global)
        res_t = e.inferred
        l = self.gen_expr(e.left, finfo, is_global)
        r = self.gen_expr(e.right, finfo, is_global)
        if res_t == STR and op == "+":
            return "str_concat(%s, %s)" % (l, r)
        if res_t == DYN or lt == DYN or rt == DYN:
            fn = {"+": "value_add", "-": "value_sub", "*": "value_mul",
                  "/": "value_div", "%": "value_mod"}[op]
            return "%s(%s, %s)" % (fn, self.to_value(l, lt), self.to_value(r, rt))
        l = self.convert(l, lt, res_t)
        r = self.convert(r, rt, res_t)
        if op == "/":
            return "fl_div_f64(%s, %s)" % (l, r)
        return "((%s) %s (%s))" % (l, op, r)

    def gen_mod(self, e, lt, rt, finfo, is_global):
        # Python-floored modulo (C's % truncates toward zero)
        l = self.gen_expr(e.left, finfo, is_global)
        r = self.gen_expr(e.right, finfo, is_global)
        res_t = e.inferred
        if res_t == DYN or lt == DYN or rt == DYN:
            return "value_mod(%s, %s)" % (self.to_value(l, lt), self.to_value(r, rt))
        l = self.convert(l, lt, res_t)
        r = self.convert(r, rt, res_t)
        if res_t == F64:
            return "fl_mod_f64(%s, %s)" % (l, r)
        return "fl_mod_i64(%s, %s)" % (l, r)

    def gen_in(self, e, lt, rt, finfo, is_global):
        # needle in haystack
        needle = self.gen_expr(e.left, finfo, is_global)
        hay = self.gen_expr(e.right, finfo, is_global)
        if is_dict(rt):
            return "dict_%s_has(%s, %s)" % (self.dict_suffix(rt), hay, needle)
        if rt == STR:
            return "(strstr(%s, %s) != NULL)" % (hay, needle)
        if is_list(rt):
            elt = rt[1]
            if self._list_storage(rt) == "Pair":
                return "fl_contains_ListDyn(%s, %s)" % (
                    hay, self.to_value(needle, lt))
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
            if suf == "Dyn":
                needle = self.to_value(needle, lt)
            else:
                needle = self.convert(needle, lt, elt)
            return "fl_contains_%s(%s, %s)" % (suf, hay, needle)
        if rt == RANGE:
            ndl = self.convert(needle, lt, I64)
            return "fl_range_contains(%s, %s)" % (hay, ndl)
        if rt == DYN or lt == DYN:
            return "value_contains(%s, %s)" % (
                self.to_value(hay, rt), self.to_value(needle, lt))
        raise CompileError("line %d: cannot use 'in' on %r" % (e.line, rt))

    def gen_compare(self, e, lt, rt, finfo, is_global):
        op = e.op
        l = self.gen_expr(e.left, finfo, is_global)
        r = self.gen_expr(e.right, finfo, is_global)
        return self.compare_codes(l, lt, op, r, rt, e.line)

    def compare_codes(self, l, lt, op, r, rt, line):
        if is_container(lt) or is_container(rt):
            # structural equality for nested containers; ordering
            # comparisons raise a clean TypeError at runtime (v0)
            fn = {"==": "value_eq", "!=": "value_ne", "<": "value_lt",
                  ">": "value_gt", "<=": "value_le", ">=": "value_ge"}[op]
            return "%s(%s, %s)" % (fn, self.to_value(l, lt),
                                   self.to_value(r, rt))
        if lt == DYN or rt == DYN:
            fn = {"==": "value_eq", "!=": "value_ne", "<": "value_lt",
                  ">": "value_gt", "<=": "value_le", ">=": "value_ge"}[op]
            return "%s(%s, %s)" % (fn, self.to_value(l, lt), self.to_value(r, rt))
        if lt == STR or rt == STR:
            c = "strcmp(%s, %s)" % (l, r)
            return {"==": "(%s == 0)" % c, "!=": "(%s != 0)" % c,
                    "<": "(%s < 0)" % c, ">": "(%s > 0)" % c,
                    "<=": "(%s <= 0)" % c, ">=": "(%s >= 0)" % c}[op]
        ct = F64 if F64 in (lt, rt) else I64
        l = self.convert(l, lt, ct)
        r = self.convert(r, rt, ct)
        return "((%s) %s (%s))" % (l, op, r)

    def gen_chain(self, e, finfo, is_global):
        # a < b < c  ->  ({ T _t = b; (a < _t) && (_t < c); })
        # middle operands evaluated once, left to right
        temps = []
        setup = []
        for x in e.exprs[1:-1]:
            tmp = self.tmp()
            temps.append((tmp, x.inferred))
            setup.append("%s %s = %s;" % (
                self.ctype(x.inferred), tmp, self.gen_expr(x, finfo, is_global)))
        codes = []
        for i, op in enumerate(e.ops):
            if i == 0:
                l, lt = self.gen_expr(e.exprs[0], finfo, is_global), e.exprs[0].inferred
            else:
                l, lt = temps[i - 1][0], temps[i - 1][1]
            if i < len(temps):
                r, rt = temps[i][0], temps[i][1]
            else:
                r, rt = self.gen_expr(e.exprs[-1], finfo, is_global), e.exprs[-1].inferred
            codes.append(self.compare_codes(l, lt, op, r, rt, e.line))
        return "({ %s (%s); })" % (" ".join(setup), " && ".join(codes))

    def gen_any_all(self, e, c, t, is_any, finfo, is_global):
        # any()/all() over a list or range: eager loop
        tmp = self.tmp()
        init = "false" if is_any else "true"
        setval = "true" if is_any else "false"
        if t == RANGE:
            # iterate the range directly
            if is_any:
                cond = "(_v != 0)"
            else:
                cond = "!(_v != 0)"
            return ("({ bool %s = %s; FlRange _r = %s; int64_t _n = fl_range_len(_r); "
                    "for (int64_t _i = 0; _i < _n; _i++) { "
                    "int64_t _v = _r.lo + _i * _r.step; "
                    "if (%s) { %s = %s; break; } } "
                    "%s; })" % (tmp, init, c, cond, tmp, setval, tmp))
        # list case
        elt = t[1] if is_list(t) else DYN
        suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
        if elt == I64:
            check = "(_v != 0)"
        elif elt == F64:
            check = "(_v != 0.0)"
        elif elt == STR:
            check = "((_v)[0] != '\\0')"
        elif elt == BOOL:
            # bools are stored boxed in FlListDyn
            check = "(value_truthy(_v))"
        else:
            check = "(value_truthy(_v))"
        if not is_any:
            check = "!(%s)" % check
        vctype = self.ctype(elt) if elt in (I64, F64, STR) else "Value"
        return ("({ bool %s = %s; FlList%s *_l = %s; "
                "for (int64_t _i = 0; _i < _l->len; _i++) { "
                "%s _v = _l->data[_i]; "
                "if (%s) { %s = %s; break; } } "
                "%s; })" % (tmp, init, suf, c,
                            vctype, check, tmp, setval, tmp))

    def gen_enumerate(self, e, c, t, finfo, is_global):
        # enumerate(xs) -> FlListListDyn of [index, value] pairs
        tmp = self.tmp()
        if t == RANGE:
            return ("({ FlListListDyn *%s = list_ListDyn_new(); FlRange _r = %s; "
                    "int64_t _n = fl_range_len(_r); "
                    "for (int64_t _i = 0; _i < _n; _i++) { "
                    "FlListDyn *_p = list_Dyn_new(); "
                    "list_Dyn_append(_p, v_i64(_i)); "
                    "list_Dyn_append(_p, v_i64(_r.lo + _i * _r.step)); "
                    "list_ListDyn_append(%s, _p); } "
                    "%s; })" % (tmp, c, tmp, tmp))
        # list case
        elt = t[1] if is_list(t) else DYN
        in_suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
        # box the element as a Value
        if elt == I64:
            box = "v_i64(_v)"
        elif elt == F64:
            box = "v_f64(_v)"
        elif elt == STR:
            box = "v_str(_v)"
        elif elt == BOOL:
            box = "v_bool(_v)"
        else:
            box = "_v"
        return ("({ FlListListDyn *%s = list_ListDyn_new(); "
                "FlList%s *_l = %s; "
                "for (int64_t _i = 0; _i < _l->len; _i++) { "
                "%s _v = _l->data[_i]; "
                "FlListDyn *_p = list_Dyn_new(); "
                "list_Dyn_append(_p, v_i64(_i)); "
                "list_Dyn_append(_p, %s); "
                "list_ListDyn_append(%s, _p); } "
                "%s; })" % (tmp, in_suf, c, self.ctype(elt), box, tmp, tmp))

    def gen_zip(self, e, c1, t1, c2, t2, finfo, is_global):
        # zip(a, b) -> FlListListDyn of [a_i, b_i] pairs (stops at shorter)
        tmp = self.tmp()
        # get element types and suffixes
        def suf_of(t):
            if t == RANGE:
                return "I64"
            elt = t[1] if is_list(t) else DYN
            return {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
        def elt_of(t):
            if t == RANGE:
                return I64
            return t[1] if is_list(t) else DYN
        s1, s2 = suf_of(t1), suf_of(t2)
        e1, e2 = elt_of(t1), elt_of(t2)
        # convert ranges to lists for uniform iteration
        if t1 == RANGE:
            c1 = "fl_range_to_list(%s)" % c1
        if t2 == RANGE:
            c2 = "fl_range_to_list(%s)" % c2
        # box functions
        def box(v, elt):
            if elt == I64:
                return "v_i64(%s)" % v
            if elt == F64:
                return "v_f64(%s)" % v
            if elt == STR:
                return "v_str(%s)" % v
            if elt == BOOL:
                return "v_bool(%s)" % v
            return v
        t1_tmp, t2_tmp = self.tmp(), self.tmp()
        return ("({ FlListListDyn *%s = list_ListDyn_new(); "
                "FlList%s *%s = %s; FlList%s *%s = %s; "
                "int64_t _n = %s->len < %s->len ? %s->len : %s->len; "
                "for (int64_t _i = 0; _i < _n; _i++) { "
                "FlListDyn *_p = list_Dyn_new(); "
                "list_Dyn_append(_p, %s); "
                "list_Dyn_append(_p, %s); "
                "list_ListDyn_append(%s, _p); } "
                "%s; })" % (tmp, s1, t1_tmp, c1, s2, t2_tmp, c2,
                            t1_tmp, t2_tmp, t1_tmp, t2_tmp,
                            box("%s->data[_i]" % t1_tmp, e1),
                            box("%s->data[_i]" % t2_tmp, e2),
                            tmp, tmp))

    def gen_map_filter(self, e, name, finfo, is_global):
        # map(f, xs): eager list of f(x); filter(f, xs): eager list of x where f(x).
        # v0: f must be a top-level function name taking 1 argument.
        func_expr = e.args[0]
        if not isinstance(func_expr, N.Name) or func_expr.id not in self.funcs:
            raise CompileError("line %d: %s() function must be a top-level function name (v0)"
                               % (e.line, name))
        f = self.funcs[func_expr.id]
        if f.get("nested"):
            raise CompileError("line %d: %s() function must be a top-level function (v0)"
                               % (e.line, name))
        if len(f["params"]) != 1:
            raise CompileError("line %d: %s() function must take 1 argument"
                               % (e.line, name))
        xs_expr = e.args[1]
        xs_c = self.gen_expr(xs_expr, finfo, is_global)
        xs_t = xs_expr.inferred
        if xs_t == RANGE:
            in_suf, xs_list = "I64", "fl_range_to_list(%s)" % xs_c
            in_elt = I64
        elif is_list(xs_t):
            in_elt = xs_t[1]
            in_suf = {I64: "I64", F64: "F64", STR: "Str"}.get(in_elt, "Dyn")
            xs_list = xs_c
        else:
            raise CompileError("line %d: %s() needs a list" % (e.line, name))
        if name == "map":
            out_elt = f["ret"] if f["ret"] not in (None, VOID) else DYN
        else:
            out_elt = in_elt
        out_suf = {I64: "I64", F64: "F64", STR: "Str"}.get(out_elt, "Dyn")
        # function param type for conversion
        f_in_t = f["param_types"][0] if f["param_types"] else DYN
        tmp = self.tmp()
        in_tmp = self.tmp()
        # convert input element to function's param type
        arg_code = "(%s->data[_i])" % in_tmp
        if in_elt != f_in_t:
            # box/unbox as needed; for v0, assume compatible or use convert
            # (convert needs the code string; we'll do a simple version)
            if f_in_t == DYN:
                # elements are already Values when in_elt is DYN or a
                # (boxed) container; only box raw scalars
                if in_elt != DYN and not is_container(in_elt):
                    arg_code = self.to_value(arg_code, in_elt)
            elif in_elt == DYN or is_container(in_elt):
                # a Value is in hand; unbox (checked) to the param type
                arg_code = self.from_value(arg_code, f_in_t)
        call = "%s(%s)" % (f["cname"], arg_code)
        # convert result to output element type if needed
        f_ret = f["ret"] if f["ret"] not in (None, VOID) else DYN
        if name == "map":
            if f_ret != out_elt:
                if out_elt == DYN:
                    call = self.to_value(call, f_ret)
                elif f_ret == DYN:
                    call = self.from_value(call, out_elt)
            body = "list_%s_append(%s, %s);" % (out_suf, tmp, call)
        else:
            truthy = self.truthy(call, f_ret)
            body = "if (%s) list_%s_append(%s, %s->data[_i]);" % (
                truthy, out_suf, tmp, in_tmp)
        return ("({ FlList%s *%s = list_%s_new(); "
                "FlList%s *%s = %s; "
                "for (int64_t _i = 0; _i < %s->len; _i++) { %s } "
                "%s; })" % (out_suf, tmp, out_suf, in_suf, in_tmp, xs_list,
                            in_tmp, body, tmp))

    def _resolve_map_func(self, func_expr, finfo, is_global, line):
        # Returns (call_template, ret_type) for map/filter function.
        # call_template is a format string with one %s for the argument.
        if isinstance(func_expr, N.Name):
            fname = func_expr.id
            if fname in self.funcs and not self.funcs[fname].get("nested"):
                f = self.funcs[fname]
                # direct call: f(arg)
                return ("%s(%%s)" % f["cname"], f["ret"])
            # try closure variable
            # (for simplicity, require it to be a Name; full expr not supported in v0)
        raise CompileError("line %d: map/filter function must be a simple function name (v0)" % line)

    def gen_call(self, e, finfo, is_global):
        name = e.func
        if getattr(e, "indirect", None):
            return self.gen_indirect_call(e, finfo, is_global)
        if getattr(e, "inst_class", None):
            return self.gen_instantiation(e, finfo, is_global)
        if getattr(e, "method_class", None):
            return self.gen_method_call(e, finfo, is_global)
        if name == "print":
            parts = []
            for i, a in enumerate(e.args):
                c = self.gen_expr(a, finfo, is_global)
                t = a.inferred
                parts.append(self._print_one(c, t))
                if i < len(e.args) - 1:
                    parts.append('putchar(\' \');')
            parts.append("putchar('\\n');")
            return "({ %s })" % " ".join(parts)
        if name == "len":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            if is_list(t):
                return "((int64_t)((%s)->len))" % c
            if is_dict(t):
                return "((int64_t)((%s)->len))" % c
            if t == STR:
                return "((int64_t)strlen(%s))" % c
            if t == RANGE:
                return "fl_range_len(%s)" % c
            if t == DYN:
                return "value_len(%s)" % c
            raise CompileError("line %d: len() of %r" % (e.line, t))
        if name == "range":
            args = [self.convert(self.gen_expr(a, finfo, is_global), a.inferred, I64)
                    for a in e.args]
            if len(args) == 1:
                return "fl_make_range(0, %s, 1)" % args[0]
            elif len(args) == 2:
                return "fl_make_range(%s, %s, 1)" % (args[0], args[1])
            else:
                return "fl_make_range(%s, %s, %s)" % (args[0], args[1], args[2])
        if name == "list":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            if t == RANGE:
                return "fl_range_to_list(%s)" % c
            if is_list(t):
                return c
            raise CompileError("line %d: list() of %r" % (e.line, t))
        if name == "sorted":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            elt = t[1] if is_list(t) else DYN
            if is_container(elt) or self._list_storage(t) == "Pair":
                raise CompileError("line %d: sorted() of nested containers is not supported (v0)"
                                   % e.line)
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
            tmp = self.tmp()
            return ("({ FlList%s *%s = list_%s_copy(%s); "
                    "list_%s_sort(%s); %s; })" % (suf, tmp, suf, c, suf, tmp, tmp))
        if name == "reversed":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            if t == RANGE:
                return "fl_range_to_rev_list(%s)" % c
            elt = t[1] if is_list(t) else DYN
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt, "Dyn")
            tmp = self.tmp()
            return ("({ FlList%s *%s = list_%s_copy(%s); "
                    "list_%s_reverse(%s); %s; })" % (suf, tmp, suf, c, suf, tmp, tmp))
        if name in ("any", "all"):
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            return self.gen_any_all(e, c, t, name == "any", finfo, is_global)
        if name == "enumerate":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            return self.gen_enumerate(e, c, t, finfo, is_global)
        if name == "zip":
            c1 = self.gen_expr(e.args[0], finfo, is_global)
            c2 = self.gen_expr(e.args[1], finfo, is_global)
            t1 = e.args[0].inferred
            t2 = e.args[1].inferred
            return self.gen_zip(e, c1, t1, c2, t2, finfo, is_global)
        if name in ("map", "filter"):
            return self.gen_map_filter(e, name, finfo, is_global)
        if name == "append":
            lc = self.gen_expr(e.args[0], finfo, is_global)
            lt = e.args[0].inferred
            vt = e.args[1].inferred
            if is_closure(vt):
                raise CompileError("line %d: cannot store a function in a list" % e.line)
            if lt == DYN or lt is None:
                # dynamic receiver (a boxed Value): dispatch at runtime
                vc = self.gen_expr(e.args[1], finfo, is_global)
                if vt is not None:
                    vc = self.to_value(vc, vt)
                return "value_list_append(%s, %s)" % (lc, vc)
            elt_t = lt[1] if is_list(lt) else DYN
            vc = self.gen_expr(e.args[1], finfo, is_global)
            if is_list(lt) and self._list_storage(lt) == "Pair":
                vc = self.convert(vc, vt, ("list", DYN))
                return "list_ListDyn_append(%s, %s)" % (lc, vc)
            vc = self.convert(vc, vt, elt_t)
            app = {I64: "list_I64_append", F64: "list_F64_append",
                   STR: "list_Str_append"}.get(elt_t, "list_Dyn_append")
            if elt_t == BOOL or is_container(elt_t):
                # list_Dyn_append takes a Value; box bools and nested
                # containers (convert() already boxed scalars for DYN)
                vc = self.to_value(vc, elt_t)
            elif elt_t != DYN and elt_t not in (I64, F64, STR):
                # typed appends (I64/F64/STR) need no boxing; anything else
                # is unrepresentable
                raise CompileError("line %d: cannot append %r to list" % (e.line, elt_t))
            return "%s(%s, %s)" % (app, lc, vc)
        if name == "keys":
            c = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            if is_dict(t):
                return "dict_%s_keys(%s)" % (self.dict_suffix(t), c)
            raise CompileError("line %d: keys() of %r" % (e.line, t))
        # ---- stdlib: math ----
        if name in ("sqrt", "sin", "cos", "tan", "exp", "log"):
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, F64)
            return "%s(%s)" % (name, x)
        if name == "pow":
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, F64)
            y = self.convert(self.gen_expr(e.args[1], finfo, is_global),
                             e.args[1].inferred, F64)
            return "pow(%s, %s)" % (x, y)
        if name == "abs":
            x = self.gen_expr(e.args[0], finfo, is_global)
            t = e.args[0].inferred
            if t == I64:
                return "llabs(%s)" % x
            if t == F64:
                return "fabs(%s)" % x
            return "value_abs(%s)" % self.to_value(x, t)
        if name in ("floor", "ceil"):
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, F64)
            return "((int64_t)%s(%s))" % (name, x)
        # ---- stdlib: strings ----
        if name == "split":
            s = self.gen_expr(e.args[0], finfo, is_global)
            d = self.gen_expr(e.args[1], finfo, is_global)
            return "str_split(%s, %s)" % (s, d)
        if name == "join":
            d = self.gen_expr(e.args[0], finfo, is_global)
            l = self.gen_expr(e.args[1], finfo, is_global)
            return "str_join(%s, %s)" % (d, l)
        if name in ("upper", "lower", "strip"):
            s = self.gen_expr(e.args[0], finfo, is_global)
            return "str_%s(%s)" % (name, s)
        if name == "replace":
            s = self.gen_expr(e.args[0], finfo, is_global)
            o = self.gen_expr(e.args[1], finfo, is_global)
            n = self.gen_expr(e.args[2], finfo, is_global)
            return "str_replace(%s, %s, %s)" % (s, o, n)
        if name == "find":
            s = self.gen_expr(e.args[0], finfo, is_global)
            sub = self.gen_expr(e.args[1], finfo, is_global)
            return "str_find(%s, %s)" % (s, sub)
        if name in ("startswith", "endswith"):
            s = self.gen_expr(e.args[0], finfo, is_global)
            sub = self.gen_expr(e.args[1], finfo, is_global)
            return "str_%s(%s, %s)" % (name, s, sub)
        # ---- stdlib: lists ----
        if name in ("sort", "reverse"):
            l = self.gen_expr(e.args[0], finfo, is_global)
            elt = e.args[0].inferred[1] if is_list(e.args[0].inferred) else DYN
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt)
            if suf is None:
                raise CompileError("line %d: %s() needs a typed list (v0)" % (e.line, name))
            return "list_%s_%s(%s)" % (suf, name, l)
        if name == "sum":
            l = self.gen_expr(e.args[0], finfo, is_global)
            at = e.args[0].inferred
            if at == RANGE:
                return "fl_range_sum(%s)" % l
            elt = at[1] if is_list(at) else DYN
            suf = {I64: "I64", F64: "F64"}.get(elt)
            if suf is None:
                raise CompileError("line %d: sum() needs a numeric list (v0)" % e.line)
            return "list_%s_sum(%s)" % (suf, l)
        if name in ("min", "max"):
            l = self.gen_expr(e.args[0], finfo, is_global)
            elt = e.args[0].inferred[1] if is_list(e.args[0].inferred) else DYN
            suf = {I64: "I64", F64: "F64", STR: "Str"}.get(elt)
            if suf is None:
                raise CompileError("line %d: %s() needs a typed list (v0)" % (e.line, name))
            return "list_%s_%s(%s)" % (suf, name, l)
        # ---- stdlib: files ----
        if name == "read_file":
            p = self.gen_expr(e.args[0], finfo, is_global)
            return "file_read_all(%s)" % p
        if name == "write_file":
            p = self.gen_expr(e.args[0], finfo, is_global)
            c = self.gen_expr(e.args[1], finfo, is_global)
            return "file_write_all(%s, %s)" % (p, c)
        if name == "file_lines":
            p = self.gen_expr(e.args[0], finfo, is_global)
            return "file_read_lines(%s)" % p
        # ---- stdlib: time & random & sys ----
        if name == "now":
            return "time_now()"
        if name == "sleep":
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, F64)
            return "time_sleep(%s)" % x
        if name == "rand":
            return "rand01()"
        if name == "randint":
            a = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, I64)
            b = self.convert(self.gen_expr(e.args[1], finfo, is_global),
                             e.args[1].inferred, I64)
            return "randint_ab(%s, %s)" % (a, b)
        if name == "seed":
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, I64)
            return "srand((unsigned)(%s))" % x
        if name == "argv":
            return "_flare_argv"
        if name == "exit":
            x = self.convert(self.gen_expr(e.args[0], finfo, is_global),
                             e.args[0].inferred, I64)
            return "exit((int)(%s))" % x
        # user function
        f = self.funcs[name]
        eargs = getattr(e, "effective_args", e.args)
        args = [self.convert(self.gen_expr(a, finfo, is_global), a.inferred, pt)
                for a, pt in zip(eargs, f["param_types"])]
        if f["nested"]:
            # direct call to a nested function: only valid for recursion,
            # where the current environment is the right one
            if finfo is not None and finfo["qname"] == name:
                call = "%s(_fl_env%s)" % (f["cname"], ", " + ", ".join(args) if args else "")
            else:
                raise CompileError("line %d: cannot call nested function '%s' directly"
                                   % (e.line, name))
        else:
            call = "%s(%s)" % (f["cname"], ", ".join(args))
        if f["ret"] == VOID:
            return "(%s, 0)" % call  # ExprStmt context only; value unused
        return call

    def _print_one(self, c, t):
        if t == I64:
            return 'printf("%%" PRId64, (int64_t)(%s));' % c
        if t == F64:
            return 'fl_print_f64((double)(%s));' % c
        if t == BOOL:
            return 'fputs((%s) ? "True" : "False", stdout);' % c
        if t == STR:
            return 'fputs(%s, stdout);' % c
        if t == RANGE:
            return 'fputs(fl_str_range(%s), stdout);' % c
        if is_closure(t):
            return 'fputs("<function>", stdout);'
        if is_class(t):
            return 'printf("<%%s object at %%p>", "%s", (void*)(%s));' % (t[1], c)
        if t == DYN:
            return 'print_value(%s);' % c
        if is_list(t):
            if self._list_storage(t) == "Pair":
                return 'print_list_ListDyn(%s);' % c
            e = t[1]
            fn = {I64: "print_list_I64", F64: "print_list_F64",
                  STR: "print_list_Str"}.get(e, "print_list_Dyn")
            return '%s(%s);' % (fn, c)
        if is_dict(t):
            return 'dict_%s_print(%s);' % (self.dict_suffix(t), c)
        raise CompileError("cannot print %r" % (t,))
