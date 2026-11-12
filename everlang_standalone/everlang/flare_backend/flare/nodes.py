"""Flare AST nodes."""


class Node:
    pass


class Program(Node):
    def __init__(self, stmts):
        self.stmts = stmts

    def __repr__(self):
        return "Program(%r)" % (self.stmts,)


class FuncDef(Node):
    def __init__(self, name, params, body, line, defaults=None):
        self.name = name
        self.params = params
        self.body = body
        self.line = line
        self.defaults = defaults or {}  # param name -> default expr
        self.qualname = None  # filled by inference (qualified for nested)

    def __repr__(self):
        return "FuncDef(%s, %r, %r)" % (self.name, self.params, self.body)


class ClassDef(Node):
    def __init__(self, name, methods, line):
        self.name = name
        self.methods = methods  # list of FuncDef
        self.line = line

    def __repr__(self):
        return "ClassDef(%s, %r)" % (self.name, self.methods)


class Import(Node):
    def __init__(self, name, line):
        self.name = name
        self.line = line

    def __repr__(self):
        return "Import(%s)" % self.name


class GetAttr(Node):
    def __init__(self, obj, attr, line):
        self.obj = obj
        self.attr = attr
        self.line = line

    def __repr__(self):
        return "GetAttr(%r, %s)" % (self.obj, self.attr)


class SetAttr(Node):
    def __init__(self, obj, attr, value, line):
        self.obj = obj
        self.attr = attr
        self.value = value
        self.line = line

    def __repr__(self):
        return "SetAttr(%r, %s, %r)" % (self.obj, self.attr, self.value)


class Assign(Node):
    def __init__(self, target, value, line):
        self.target = target
        self.value = value
        self.line = line

    def __repr__(self):
        return "Assign(%s, %r)" % (self.target, self.value)


class SetItem(Node):
    def __init__(self, target, key, value, line):
        self.target = target  # variable name holding the dict
        self.key = key
        self.value = value
        self.line = line

    def __repr__(self):
        return "SetItem(%s, %r, %r)" % (self.target, self.key, self.value)


class Return(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return "Return(%r)" % (self.value,)


class If(Node):
    def __init__(self, branches, else_body, line):
        # branches: [(cond, body), ...]  (elif folds in here)
        self.branches = branches
        self.else_body = else_body
        self.line = line

    def __repr__(self):
        return "If(%r, else=%r)" % (self.branches, self.else_body)


class While(Node):
    def __init__(self, cond, body, line):
        self.cond = cond
        self.body = body
        self.line = line

    def __repr__(self):
        return "While(%r, %r)" % (self.cond, self.body)


class For(Node):
    def __init__(self, var, iter_expr, body, line):
        self.var = var
        self.iter_expr = iter_expr
        self.body = body
        self.line = line

    def __repr__(self):
        return "For(%s, %r, %r)" % (self.var, self.iter_expr, self.body)


class ExprStmt(Node):
    def __init__(self, expr, line):
        self.expr = expr
        self.line = line

    def __repr__(self):
        return "ExprStmt(%r)" % (self.expr,)


class BinOp(Node):
    def __init__(self, op, left, right, line):
        self.op = op
        self.left = left
        self.right = right
        self.line = line

    def __repr__(self):
        return "BinOp(%r, %r, %r)" % (self.op, self.left, self.right)


class UnaryOp(Node):
    def __init__(self, op, operand, line):
        self.op = op
        self.operand = operand
        self.line = line

    def __repr__(self):
        return "UnaryOp(%r, %r)" % (self.op, self.operand)


class Call(Node):
    def __init__(self, func, args, line):
        self.func = func  # str (only direct named calls in v0)
        self.args = args
        self.line = line

    def __repr__(self):
        return "Call(%s, %r)" % (self.func, self.args)


class CallObj(Node):
    def __init__(self, func, args, line):
        self.func = func  # expression evaluating to a closure
        self.args = args
        self.line = line

    def __repr__(self):
        return "CallObj(%r, %r)" % (self.func, self.args)


class Index(Node):
    def __init__(self, obj, index, line):
        self.obj = obj
        self.index = index
        self.line = line

    def __repr__(self):
        return "Index(%r, %r)" % (self.obj, self.index)


class Slice(Node):
    def __init__(self, obj, lo, hi, step, line):
        self.obj = obj
        self.lo = lo    # expr | None
        self.hi = hi    # expr | None
        self.step = step  # expr | None
        self.line = line

    def __repr__(self):
        return "Slice(%r, %r, %r, %r)" % (self.obj, self.lo, self.hi, self.step)


class Name(Node):
    def __init__(self, id, line):
        self.id = id
        self.line = line

    def __repr__(self):
        return "Name(%s)" % self.id


class IntLit(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return "Int(%d)" % self.value


class FloatLit(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return "Float(%r)" % self.value


class StrLit(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return "Str(%r)" % self.value


class BoolLit(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def __repr__(self):
        return "Bool(%r)" % self.value


class ChainCompare(Node):
    def __init__(self, exprs, ops, line):
        self.exprs = exprs  # [a, b, c, ...]
        self.ops = ops      # [op1, op2, ...]  len(ops) == len(exprs) - 1
        self.line = line

    def __repr__(self):
        return "ChainCompare(%r, %r)" % (self.ops, self.exprs)


class ListLit(Node):
    def __init__(self, elts, line):
        self.elts = elts
        self.line = line

    def __repr__(self):
        return "List(%r)" % (self.elts,)


class DictLit(Node):
    def __init__(self, keys, values, line):
        self.keys = keys
        self.values = values
        self.line = line

    def __repr__(self):
        return "Dict(%r, %r)" % (self.keys, self.values)


class ListComp(Node):
    def __init__(self, elt, clauses, line):
        # clauses: [("for", var, iter) | ("if", cond), ...]
        self.elt = elt
        self.clauses = clauses
        self.line = line

    def __repr__(self):
        return "ListComp(%r, %r)" % (self.elt, self.clauses)


class DictComp(Node):
    def __init__(self, key, value, clauses, line):
        self.key = key
        self.value = value
        self.clauses = clauses
        self.line = line

    def __repr__(self):
        return "DictComp(%r, %r, %r)" % (self.key, self.value, self.clauses)


class FStr(Node):
    def __init__(self, parts, line):
        # parts: [("lit", str) | ("expr", Node), ...]
        self.parts = parts
        self.line = line

    def __repr__(self):
        return "FStr(%r)" % (self.parts,)


class Try(Node):
    def __init__(self, body, handlers, finally_body, line):
        # handlers: [(exc_name|None, var|None, body), ...]
        self.body = body
        self.handlers = handlers
        self.finally_body = finally_body
        self.line = line

    def __repr__(self):
        return "Try(%r, %r)" % (self.body, self.handlers)
