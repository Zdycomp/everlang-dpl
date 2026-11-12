"""Flare parser: recursive descent over lexer tokens -> AST."""


from flare.lexer import lex, _tokenize_line, Token, decode_escapes
from flare import nodes as N


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0

    # -- cursor ---------------------------------------------------------
    def peek(self):
        return self.toks[self.pos]

    def next(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        return t.kind == kind and (value is None or t.value == value)

    def expect(self, kind, value=None):
        t = self.peek()
        if t.kind != kind or (value is not None and t.value != value):
            raise ParseError("expected %s%r, got %s at line %d"
                             % (kind, value or "", t.kind, t.line))
        return self.next()

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.next()

    # -- entry ----------------------------------------------------------
    def parse(self):
        stmts = []
        self.skip_newlines()
        while not self.at("EOF"):
            stmts.append(self.parse_stmt())
            self.skip_newlines()
        return N.Program(stmts)

    # -- statements ------------------------------------------------------
    def parse_stmt(self):
        t = self.peek()
        if t.kind == "KW":
            if t.value == "def":
                return self.parse_def()
            if t.value == "class":
                return self.parse_class()
            if t.value == "import":
                return self.parse_import()
            if t.value == "if":
                return self.parse_if()
            if t.value == "while":
                return self.parse_while()
            if t.value == "for":
                return self.parse_for()
            if t.value == "return":
                return self.parse_return()
            if t.value == "try":
                return self.parse_try()
        if t.kind == "NAME" and self._assign_op():
            return self.parse_assign()
        return self.parse_expr_stmt()

    def _assign_op(self):
        # NAME (= | += | ...) ...  or  NAME[...] (= | += | ...) ...
        # or  NAME.NAME (= | += | ...) ...
        if self.pos + 1 >= len(self.toks):
            return None
        t2 = self.toks[self.pos + 1]
        if t2.kind == "OP" and t2.value in ("=", "+=", "-=", "*=", "/=", "%="):
            return t2.value
        if t2.kind == "OP" and t2.value == ".":
            # obj.attr (= | += | ...)
            if self.pos + 3 < len(self.toks):
                t3 = self.toks[self.pos + 2]
                t4 = self.toks[self.pos + 3]
                if t3.kind == "NAME" and t4.kind == "OP" and \
                        t4.value in ("=", "+=", "-=", "*=", "/=", "%="):
                    return "setattr"
            return None
        if t2.kind == "OP" and t2.value == "[":
            # look ahead for matching ] followed by an assign op
            depth = 0
            i = self.pos + 1
            while i < len(self.toks):
                ti = self.toks[i]
                if ti.kind == "NEWLINE":
                    return None
                if ti.kind == "OP" and ti.value == "[":
                    depth += 1
                elif ti.kind == "OP" and ti.value == "]":
                    depth -= 1
                    if depth == 0:
                        nxt = self.toks[i + 1] if i + 1 < len(self.toks) else None
                        if nxt is not None and nxt.kind == "OP" and \
                                nxt.value in ("=", "+=", "-=", "*=", "/=", "%="):
                            return "setitem"
                        return None
                i += 1
            return None
        return None

    def parse_suite(self):
        self.expect("OP", ":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        stmts = []
        self.skip_newlines()
        while not self.at("DEDENT") and not self.at("EOF"):
            stmts.append(self.parse_stmt())
            self.skip_newlines()
        self.expect("DEDENT")
        if not stmts:
            raise ParseError("empty block at line %d" % self.peek().line)
        return stmts

    def parse_def(self):
        t = self.expect("KW", "def")
        name = self.expect("NAME").value
        self.expect("OP", "(")
        params = []
        defaults = {}
        if not self.at("OP", ")"):
            while True:
                pname = self.expect("NAME").value
                if self.at("OP", "="):
                    self.next()
                    defaults[pname] = self.parse_expr()
                elif defaults:
                    raise ParseError(
                        "line %d: non-default argument follows default argument"
                        % self.peek().line)
                params.append(pname)
                if not self.at("OP", ","):
                    break
                self.next()
        self.expect("OP", ")")
        body = self.parse_suite()
        return N.FuncDef(name, params, body, t.line, defaults)

    def parse_import(self):
        t = self.expect("KW", "import")
        name = self.expect("NAME").value
        # only `import name` (no `from` / `as`) in v0
        return N.Import(name, t.line)

    def parse_class(self):
        t = self.expect("KW", "class")
        name = self.expect("NAME").value
        if self.at("OP", "("):
            raise ParseError("line %d: inheritance is not supported" % t.line)
        body = self.parse_suite()
        methods = []
        for s in body:
            if not isinstance(s, N.FuncDef):
                raise ParseError("line %d: class body must contain only methods"
                                 % s.line)
            methods.append(s)
        return N.ClassDef(name, methods, t.line)

    def parse_if(self):
        t = self.expect("KW", "if")
        cond = self.parse_expr()
        body = self.parse_suite()
        branches = [(cond, body)]
        else_body = []
        while self.at("KW", "elif"):
            self.next()
            branches.append((self.parse_expr(), self.parse_suite()))
        if self.at("KW", "else"):
            self.next()
            else_body = self.parse_suite()
        return N.If(branches, else_body, t.line)

    def parse_while(self):
        t = self.expect("KW", "while")
        cond = self.parse_expr()
        body = self.parse_suite()
        return N.While(cond, body, t.line)

    def parse_for(self):
        t = self.expect("KW", "for")
        var = self.expect("NAME").value
        self.expect("KW", "in")
        it = self.parse_expr()
        body = self.parse_suite()
        return N.For(var, it, body, t.line)

    def parse_return(self):
        t = self.expect("KW", "return")
        if self.at("NEWLINE"):
            return N.Return(None, t.line)
        return N.Return(self.parse_expr(), t.line)

    def parse_try(self):
        t = self.expect("KW", "try")
        body = self.parse_suite()
        handlers = []
        while self.at("KW", "except"):
            self.next()
            exc, var = None, None
            if not self.at("OP", ":"):
                exc = self.expect("NAME").value
                if self.at("KW", "as"):
                    self.next()
                    var = self.expect("NAME").value
            hbody = self.parse_suite()
            handlers.append((exc, var, hbody))
        finally_body = []
        if self.at("KW", "finally"):
            self.next()
            finally_body = self.parse_suite()
        if not handlers and not finally_body:
            raise ParseError("try needs except or finally at line %d" % t.line)
        for i, (exc, _var, _b) in enumerate(handlers):
            if exc is None and i != len(handlers) - 1:
                raise ParseError("default 'except:' must be last at line %d" % t.line)
        return N.Try(body, handlers, finally_body, t.line)

    def parse_assign(self):
        target = self.expect("NAME").value
        tline = self.toks[self.pos - 1].line
        if self.at("OP", "."):
            # obj.attr = v  /  obj.attr += v  ->  SetAttr
            self.next()
            attr = self.expect("NAME").value
            t = self.expect("OP")
            op = t.value
            rhs = self.parse_expr()
            obj = N.Name(target, tline)
            if op != "=":
                # obj.attr += e  ->  obj.attr = obj.attr + e
                rhs = N.BinOp(op[0], N.GetAttr(obj, attr, t.line), rhs, t.line)
            return N.SetAttr(obj, attr, rhs, t.line)
        if self.at("OP", "["):
            # d[k] = v  /  d[k] += v  ->  SetItem
            self.next()
            key = self.parse_expr()
            self.expect("OP", "]")
            t = self.expect("OP")
            op = t.value
            rhs = self.parse_expr()
            if op != "=":
                # d[k] += e  ->  d[k] = d[k] + e
                rhs = N.BinOp(op[0], N.Index(N.Name(target, t.line), key, t.line),
                              rhs, t.line)
            return N.SetItem(target, key, rhs, t.line)
        t = self.expect("OP")
        op = t.value
        rhs = self.parse_expr()
        if op != "=":
            # x += e  ->  x = x + e
            rhs = N.BinOp(op[0], N.Name(target, t.line), rhs, t.line)
        return N.Assign(target, rhs, t.line)

    def parse_expr_stmt(self):
        e = self.parse_expr()
        t = e.line
        return N.ExprStmt(e, t)

    # -- expressions (precedence climbing) --------------------------------
    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at("KW", "or"):
            t = self.next()
            left = N.BinOp("or", left, self.parse_and(), t.line)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.at("KW", "and"):
            t = self.next()
            left = N.BinOp("and", left, self.parse_not(), t.line)
        return left

    def parse_not(self):
        if self.at("KW", "not"):
            t = self.next()
            return N.UnaryOp("not", self.parse_not(), t.line)
        return self.parse_comparison()

    def parse_comparison(self):
        first = self.parse_arith()
        # `x not in y`  ->  not (x in y)
        if self.at("KW", "not") and self.pos + 1 < len(self.toks) and \
                self.toks[self.pos + 1].kind == "KW" and \
                self.toks[self.pos + 1].value == "in":
            t = self.next()
            self.next()
            right = self.parse_arith()
            return N.UnaryOp("not", N.BinOp("in", first, right, t.line), t.line)
        # `x in y`
        if self.at("KW", "in"):
            t = self.next()
            return N.BinOp("in", first, self.parse_arith(), t.line)
        if not (self.at("OP") and self.peek().value in ("==", "!=", "<", ">", "<=", ">=")):
            return first
        exprs = [first]
        ops = []
        t = None
        while self.at("OP") and self.peek().value in ("==", "!=", "<", ">", "<=", ">="):
            t = self.next()
            ops.append(t.value)
            exprs.append(self.parse_arith())
        if len(ops) == 1:
            return N.BinOp(ops[0], exprs[0], exprs[1], t.line)
        return N.ChainCompare(exprs, ops, t.line)

    def parse_arith(self):
        left = self.parse_term()
        while self.at("OP") and self.peek().value in ("+", "-"):
            t = self.next()
            left = N.BinOp(t.value, left, self.parse_term(), t.line)
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.at("OP") and self.peek().value in ("*", "/", "%"):
            t = self.next()
            left = N.BinOp(t.value, left, self.parse_factor(), t.line)
        return left

    def parse_factor(self):
        if self.at("OP") and self.peek().value in ("-", "+"):
            t = self.next()
            return N.UnaryOp(t.value, self.parse_factor(), t.line)
        return self.parse_atom()

    def parse_atom(self):
        t = self.peek()
        if t.kind == "INT":
            self.next()
            node = N.IntLit(int(t.value), t.line)
        elif t.kind == "FLOAT":
            self.next()
            node = N.FloatLit(float(t.value), t.line)
        elif t.kind == "STRING":
            self.next()
            node = N.StrLit(t.value, t.line)
        elif t.kind == "FSTRING":
            self.next()
            node = self.parse_fstring(t.value, t.line)
        elif t.kind == "KW" and t.value in ("true", "false"):
            self.next()
            node = N.BoolLit(t.value == "true", t.line)
        elif t.kind == "NAME":
            self.next()
            if self.at("OP", "("):
                self.next()
                args = []
                if not self.at("OP", ")"):
                    args.append(self.parse_expr())
                    while self.at("OP", ","):
                        self.next()
                        args.append(self.parse_expr())
                self.expect("OP", ")")
                node = N.Call(t.value, args, t.line)
            else:
                node = N.Name(t.value, t.line)
        elif t.kind == "OP" and t.value == "(":
            self.next()
            node = self.parse_expr()
            self.expect("OP", ")")
        elif t.kind == "OP" and t.value == "[":
            self.next()
            elts = []
            if not self.at("OP", "]"):
                first = self.parse_expr()
                if self.at("KW", "for"):
                    node = N.ListComp(first, self.parse_comp_clauses(t.line), t.line)
                    self.expect("OP", "]")
                else:
                    elts.append(first)
                    while self.at("OP", ","):
                        self.next()
                        elts.append(self.parse_expr())
                    self.expect("OP", "]")
                    node = N.ListLit(elts, t.line)
            else:
                self.next()
                node = N.ListLit(elts, t.line)
        elif t.kind == "OP" and t.value == "{":
            self.next()
            keys, values = [], []
            if not self.at("OP", "}"):
                first = self.parse_expr()
                if self.at("OP", ":"):
                    self.next()
                    second = self.parse_expr()
                    if self.at("KW", "for"):
                        node = N.DictComp(first, second,
                                          self.parse_comp_clauses(t.line), t.line)
                        self.expect("OP", "}")
                    else:
                        keys.append(first)
                        values.append(second)
                        while self.at("OP", ","):
                            self.next()
                            if self.at("OP", "}"):
                                break
                            keys.append(self.parse_expr())
                            self.expect("OP", ":")
                            values.append(self.parse_expr())
                        self.expect("OP", "}")
                        node = N.DictLit(keys, values, t.line)
                elif self.at("KW", "for"):
                    raise ParseError(
                        "set comprehensions are not supported (v0) at line %d" % t.line)
                else:
                    raise ParseError("unexpected %s %r at line %d"
                                     % (self.peek().kind, self.peek().value, t.line))
            else:
                self.next()
                node = N.DictLit(keys, values, t.line)
        else:
            raise ParseError("unexpected %s %r at line %d" % (t.kind, t.value, t.line))
        # postfix: indexing, slicing, method calls, and calls on the
        # result of an expression (f()(), funcs[0]()), on any primary
        while True:
            if self.at("OP", "["):
                self.next()
                node = self.parse_subscript(node, t.line)
            elif self.at("OP", "("):
                self.next()
                args = []
                if not self.at("OP", ")"):
                    args.append(self.parse_expr())
                    while self.at("OP", ","):
                        self.next()
                        args.append(self.parse_expr())
                self.expect("OP", ")")
                node = N.CallObj(node, args, t.line)
            elif self.at("OP", "."):
                self.next()
                attr = self.expect("NAME").value
                if self.at("OP", "("):
                    # method call: obj.method(args) -> Call("method", [obj] + args)
                    self.next()
                    args = []
                    if not self.at("OP", ")"):
                        args.append(self.parse_expr())
                        while self.at("OP", ","):
                            self.next()
                            args.append(self.parse_expr())
                    self.expect("OP", ")")
                    node = N.Call(attr, [node] + args, t.line)
                else:
                    # attribute access: obj.attr -> GetAttr
                    node = N.GetAttr(node, attr, t.line)
            else:
                break
        return node

    def parse_subscript(self, obj, line):
        # obj[expr] | obj[lo:hi:step]  (any part of the slice may be empty)
        lo = hi = step = None
        is_slice = False
        if not self.at("OP", ":"):
            lo = self.parse_expr()
        if self.at("OP", ":"):
            is_slice = True
            self.next()
            if not self.at("OP", ":") and not self.at("OP", "]"):
                hi = self.parse_expr()
            if self.at("OP", ":"):
                self.next()
                if not self.at("OP", "]"):
                    step = self.parse_expr()
        self.expect("OP", "]")
        if is_slice:
            return N.Slice(obj, lo, hi, step, line)
        return N.Index(obj, lo, line)

    # -- f-strings ------------------------------------------------------
    def parse_comp_clauses(self, line):
        clauses = []
        while True:
            if self.at("KW", "for"):
                self.next()
                var = self.expect("NAME").value
                self.expect("KW", "in")
                it = self.parse_expr()
                clauses.append(("for", var, it))
            elif self.at("KW", "if"):
                self.next()
                clauses.append(("if", self.parse_expr()))
            else:
                break
        if not clauses:
            raise ParseError("expected for/if in comprehension at line %d" % line)
        return clauses

    def parse_fstring(self, raw, line):
        """Split raw f-string text into literal parts and {expr} parts."""
        parts = []
        lit = []

        def flush_lit():
            if lit:
                parts.append(("lit", decode_escapes("".join(lit))))
                del lit[:]

        i, n = 0, len(raw)
        while i < n:
            ch = raw[i]
            if ch == "\\" and i + 1 < n:
                lit.append(ch)
                lit.append(raw[i + 1])
                i += 2
                continue
            if ch == "{" and i + 1 < n and raw[i + 1] == "{":
                lit.append("{")
                i += 2
                continue
            if ch == "}" and i + 1 < n and raw[i + 1] == "}":
                lit.append("}")
                i += 2
                continue
            if ch == "{":
                j = i + 1
                depth = 1
                quote = None
                while j < n and depth > 0:
                    c = raw[j]
                    if c == "\\" and j + 1 < n:
                        j += 2
                        continue
                    if quote:
                        if c == quote:
                            quote = None
                    elif c in "\"'":
                        quote = c
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                    j += 1
                if depth != 0:
                    raise ParseError("unmatched '{' in f-string at line %d" % line)
                inner = raw[i + 1:j - 1]
                if not inner.strip():
                    raise ParseError("empty {} in f-string at line %d" % line)
                if _has_format_spec(inner):
                    raise ParseError(
                        "f-string format specs are not supported (v0) at line %d" % line)
                flush_lit()
                toks = _tokenize_line(inner, line)
                toks.append(Token("EOF", "", line))
                sub = Parser(toks)
                expr = sub.parse_expr()
                if not sub.at("EOF"):
                    raise ParseError(
                        "bad expression in f-string at line %d" % line)
                parts.append(("expr", expr))
                i = j
                continue
            if ch == "}":
                raise ParseError("unmatched '}' in f-string at line %d" % line)
            lit.append(ch)
            i += 1
        flush_lit()
        return N.FStr(parts, line)


def _has_format_spec(s):
    """True if the interpolation has a ':' format spec at brace depth 0."""
    depth = 0
    quote = None
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ":" and depth == 0:
            return True
        i += 1
    return False


def parse(source):
    return Parser(lex(source)).parse()
