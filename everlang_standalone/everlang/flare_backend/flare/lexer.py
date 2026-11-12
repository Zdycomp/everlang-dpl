"""Flare lexer: Python-style indentation tokens."""


class Token:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind = kind
        self.value = value
        self.line = line

    def __repr__(self):
        return "Token(%s, %r, line=%d)" % (self.kind, self.value, self.line)


KEYWORDS = {
    "def", "return", "if", "else", "elif", "while", "for", "in",
    "true", "false", "and", "or", "not",
    "try", "except", "finally", "as",
    "class", "import",
}

_MULTI_OPS = ["==", "!=", "<=", ">=", "+=", "-=", "*=", "/=", "%="]
_SINGLE_OPS = "+-*/%=<>()[]{}:,."


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
            '"': '"', "'": "'", "0": "\0"}


def decode_escapes(s):
    """Process backslash escapes in a string's inner text."""
    out = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _strip_comment(code):
    """Remove a # comment, respecting string literals."""
    out = []
    i, n = 0, len(code)
    quote = None
    while i < n:
        ch = code[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _tokenize_line(code, lineno):
    toks = []
    i, n = 0, len(code)
    while i < n:
        ch = code[i]
        if ch in " \t":
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and code[j].isdigit():
                j += 1
            if j < n and code[j] == "." and j + 1 < n and code[j + 1].isdigit():
                j += 1
                while j < n and code[j].isdigit():
                    j += 1
                toks.append(Token("FLOAT", code[i:j], lineno))
            else:
                toks.append(Token("INT", code[i:j], lineno))
            i = j
            continue
        if ch in "\"'":
            j = i + 1
            start = j
            while j < n and code[j] != ch:
                if code[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            if j >= n:
                raise SyntaxError("unterminated string at line %d" % lineno)
            toks.append(Token("STRING", decode_escapes(code[start:j]), lineno))
            i = j + 1
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (code[j].isalnum() or code[j] == "_"):
                j += 1
            word = code[i:j]
            if word in ("f", "F") and j < n and code[j] in "\"'":
                # f-string: capture the raw inner text; the parser splits
                # it into literal parts and {expr} interpolations.
                # Brace-aware scan so nested same-quote f-strings work.
                q = code[j]
                k = j + 1
                depth = 0
                while k < n:
                    c = code[k]
                    if c == "\\" and k + 1 < n:
                        k += 2
                        continue
                    if depth == 0:
                        if c == q:
                            break
                        if c == "{":
                            if k + 1 < n and code[k + 1] == "{":
                                k += 2
                                continue
                            depth = 1
                    else:
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                        elif c in "\"'":
                            qq = c
                            k += 1
                            while k < n and code[k] != qq:
                                if code[k] == "\\" and k + 1 < n:
                                    k += 2
                                else:
                                    k += 1
                    k += 1
                if k >= n:
                    raise SyntaxError("unterminated string at line %d" % lineno)
                toks.append(Token("FSTRING", code[j + 1:k], lineno))
                i = k + 1
                continue
            kind = "KW" if word in KEYWORDS else "NAME"
            toks.append(Token(kind, word, lineno))
            i = j
            continue
        two = code[i:i + 2]
        if two in _MULTI_OPS:
            toks.append(Token("OP", two, lineno))
            i += 2
            continue
        if ch in _SINGLE_OPS:
            toks.append(Token("OP", ch, lineno))
            i += 1
            continue
        raise SyntaxError("unexpected character %r at line %d" % (ch, lineno))
    return toks


def lex(source):
    tokens = []
    indent_stack = [0]
    lineno = 0
    for lineno, raw in enumerate(source.split("\n"), 1):
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip(" ")
        if "\t" in line[:len(line) - len(stripped)]:
            raise SyntaxError("tabs are not allowed for indentation (line %d)" % lineno)
        indent = len(line) - len(stripped)
        code = _strip_comment(stripped)
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token("INDENT", "", lineno))
        else:
            while indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token("DEDENT", "", lineno))
            if indent != indent_stack[-1]:
                raise SyntaxError("inconsistent indentation at line %d" % lineno)
        if code:
            tokens.extend(_tokenize_line(code, lineno))
            tokens.append(Token("NEWLINE", "", lineno))
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", "", lineno or 1))
    tokens.append(Token("EOF", "", lineno or 1))
    return tokens
