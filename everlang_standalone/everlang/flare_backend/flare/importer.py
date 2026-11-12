"""Flare multi-file importer: `import name` merges a sibling .fl file's AST.

Only top-level `import name` statements are supported (no `from`/`as`,
no relative imports). The imported file is resolved as `<name>.fl` in the
same directory as the file containing the import. Its top-level statements
are prepended (in dependency order) so its definitions and globals are
available; the Import nodes themselves are removed.

Cycles are a compile error. Name conflicts (two files defining the same
top-level function/class) are a compile error.
"""

import os

from flare import nodes as N
from flare.parser import parse
from flare.infer import CompileError


def resolve_imports(program, base_dir, _visited=None):
    """Return (new Program with imports resolved, list of files read).
    base_dir is the directory containing the top-level .fl file."""
    if _visited is None:
        _visited = set()
    files = []
    stmts = []
    for s in program.stmts:
        if isinstance(s, N.Import):
            imp_stmts, imp_files = _load_import(s, base_dir, _visited)
            stmts.extend(imp_stmts)
            files.extend(imp_files)
        else:
            stmts.append(s)
    # check for duplicate top-level definitions after merging
    seen = set()
    for s in stmts:
        if isinstance(s, N.FuncDef):
            key = ("func", s.name)
        elif isinstance(s, N.ClassDef):
            key = ("class", s.name)
        else:
            continue
        if key in seen:
            raise CompileError("line %d: duplicate %s '%s' (from import)"
                               % (s.line, key[0], s.name))
        seen.add(key)
    return N.Program(stmts), files


def _load_import(node, base_dir, visited):
    path = os.path.join(base_dir, node.name + ".fl")
    real = os.path.realpath(path)
    if not os.path.isfile(path):
        raise CompileError("line %d: cannot find module '%s' (%s)"
                           % (node.line, node.name, path))
    if real in visited:
        raise CompileError("line %d: circular import of '%s'"
                           % (node.line, node.name))
    visited.add(real)
    try:
        with open(path) as f:
            source = f.read()
        try:
            prog = parse(source)
        except Exception as ex:
            raise CompileError("in imported file '%s': %s" % (path, ex))
        # imports inside functions are not supported; top-level imports
        # in the imported file are fine (resolved recursively)
        for s in prog.stmts:
            if not isinstance(s, N.Import):
                _check_no_nested_import(s, path)
        merged, files = resolve_imports(prog, os.path.dirname(real), visited)
        return merged.stmts, [real] + files
    finally:
        visited.remove(real)


def _check_no_nested_import(node, path):
    # Import must be top-level; walk function/class bodies to enforce it
    if isinstance(node, N.Import):
        raise CompileError("in imported file '%s': import must be top-level"
                           % path)
    for v in vars(node).values():
        _check_no_nested_value(v, path)


def _check_no_nested_value(v, path):
    if isinstance(v, N.Node):
        _check_no_nested_import(v, path)
    elif isinstance(v, (list, tuple)):
        for item in v:
            _check_no_nested_value(item, path)
