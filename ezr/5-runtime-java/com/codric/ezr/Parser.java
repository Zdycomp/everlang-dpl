package com.codric.ezr;

import java.util.ArrayList;
import java.util.List;

import com.codric.ezr.Lexer.Kind;
import com.codric.ezr.Lexer.Tok;

/**
 * Recursive descent over 7-forge/GRAMMAR.ebnf.
 *
 * <p>The grammar's {@code additive} and {@code multiplicative} are written
 * left-recursively, which recursive descent cannot take directly; both become
 * loops here, which is the standard elimination and preserves left
 * associativity. That the associativity survives is not assumed — the
 * differential harness checks {@code 10 - 3 - 2} against the Python front
 * ends, where a right-associative slip would give 9 instead of 5.
 *
 * <p>Three forge rulings are enforced, not re-litigated:
 * <ul>
 *   <li>{@code a < b < c} does not parse. The published rule is
 *       {@code comparison = additive compare-op additive}, optional-once,
 *       not repeated.</li>
 *   <li>An argument or parameter list may not end with a comma.
 *       16 of 16 independent witnesses agreed.</li>
 *   <li>A run of definitions may <em>not</em> be followed by an expression.
 *       That grammar is ambiguous — {@code def f(n) = 1 - 1} has two
 *       derivations — and only the chart parser could see it.</li>
 * </ul>
 *
 * <p>Running out of input is {@code Z(unbounded)}; a token that cannot start
 * what the grammar needs is {@code Z(misbound)}. Never an exception.
 */
public final class Parser {

    public record Out(Ast ast, Particle error) {
        public boolean ok() { return error == null; }
    }

    private final List<Tok> toks;
    private int p = 0;

    private Parser(List<Tok> toks) { this.toks = toks; }

    /** Lex then parse. The whole front end in one call. */
    public static Out parse(String source) {
        Lexer.Out lexed = Lexer.lex(source);
        if (!lexed.ok()) return new Out(null, lexed.error());
        return new Parser(lexed.tokens()).program();
    }

    /* ── program = definitions | expression ─────────────────────────── */

    private Out program() {
        try {
            if (atKeyword("def")) {
                List<Ast.Def> defs = new ArrayList<>();
                while (atKeyword("def")) defs.add(definition());
                expect(Kind.EOF, "end of input after the definitions");
                return new Out(new Ast.Prog(defs, null), null);
            }
            if (at(Kind.EOF)) {
                return new Out(null, Particle.z(Particle.Defect.UNBOUNDED,
                    "empty program"));
            }
            Ast e = expression();
            expect(Kind.EOF, "end of input");
            return new Out(new Ast.Prog(List.of(), e), null);
        } catch (Refusal r) {
            return new Out(null, r.z);
        }
    }

    /* ── definition = "def" name "(" [parameters] ")" "=" expression ── */

    private Ast.Def definition() {
        eat();                                          // def
        Tok name = expect(Kind.NAME, "a function name after 'def'");
        expect(Kind.LPAR, "'(' after the function name");
        List<String> params = new ArrayList<>();
        if (!at(Kind.RPAR)) {
            params.add(expect(Kind.NAME, "a parameter name").text());
            while (at(Kind.COMMA)) {
                eat();
                // settled: no trailing comma
                params.add(expect(Kind.NAME, "a parameter name after ','").text());
            }
        }
        expect(Kind.RPAR, "')' to close the parameter list");
        expect(Kind.EQ, "'=' after the parameter list");
        return new Ast.Def(name.text(), params, expression());
    }

    /* ── expression = conditional | binding | comparison ────────────── */

    private Ast expression() {
        if (atKeyword("if"))  return conditional();
        if (atKeyword("let")) return binding();
        return comparison();
    }

    private Ast conditional() {
        eat();                                          // if
        Ast c = expression();
        expectKeyword("then");
        Ast a = expression();
        expectKeyword("else");
        return new Ast.If(c, a, expression());
    }

    private Ast binding() {
        eat();                                          // let
        Tok name = expect(Kind.NAME, "a name after 'let'");
        expect(Kind.EQ, "'=' after the bound name");
        Ast v = expression();
        expectKeyword("in");
        return new Ast.Let(name.text(), v, expression());
    }

    /** comparison = additive [ compare-op additive ] — optional ONCE. */
    private Ast comparison() {
        Ast left = additive();
        if (at(Kind.CMP)) {
            String op = eat().text();
            Ast right = additive();
            if (at(Kind.CMP)) {                         // a < b < c
                throw refuse(Particle.Defect.MISBOUND,
                    "chained comparison is outside the grammar at line "
                    + peek().line());
            }
            return new Ast.Bin(op, left, right);
        }
        return left;
    }

    /** Left-recursive in the grammar; a loop here, still left-associative. */
    private Ast additive() {
        Ast node = multiplicative();
        while (at(Kind.OP) && (peek().text().equals("+") || peek().text().equals("-"))) {
            String op = eat().text();
            node = new Ast.Bin(op, node, multiplicative());
        }
        return node;
    }

    private Ast multiplicative() {
        Ast node = unary();
        while (at(Kind.OP) && (peek().text().equals("*") || peek().text().equals("/"))) {
            String op = eat().text();
            node = new Ast.Bin(op, node, unary());
        }
        return node;
    }

    /** unary = "-" unary | atom. Negation is 0 - x, so the evaluator has
     *  one subtraction rule rather than two. */
    private Ast unary() {
        if (at(Kind.OP) && peek().text().equals("-")) {
            eat();
            return new Ast.Bin("-", new Ast.Num(0), unary());
        }
        return atom();
    }

    private Ast atom() {
        Tok t = peek();
        switch (t.kind()) {
            case NUM -> { eat(); return new Ast.Num(Double.parseDouble(t.text())); }
            case STR -> { eat(); return new Ast.Str(t.text()); }
            case KW  -> {
                if (t.text().equals("true"))  { eat(); return new Ast.Bool(true);  }
                if (t.text().equals("false")) { eat(); return new Ast.Bool(false); }
                throw refuse(Particle.Defect.MISBOUND,
                    "'" + t.text() + "' is a reserved word and cannot start an "
                    + "expression, at line " + t.line());
            }
            case LPAR -> {
                eat();
                Ast inner = expression();
                expect(Kind.RPAR, "')' to close the group");
                return inner;                           // ((n)) is one node
            }
            case LBRACK -> {
                eat();
                List<Ast> items = new ArrayList<>();
                if (!at(Kind.RBRACK)) {
                    items.add(expression());
                    while (at(Kind.COMMA)) { eat(); items.add(expression()); }
                }
                expect(Kind.RBRACK, "']' to close the list");
                return new Ast.Lst(items);
            }
            case NAME -> {
                eat();
                if (at(Kind.LPAR)) {                    // a call
                    eat();
                    List<Ast> args = new ArrayList<>();
                    if (!at(Kind.RPAR)) {
                        args.add(expression());
                        while (at(Kind.COMMA)) { eat(); args.add(expression()); }
                    }
                    expect(Kind.RPAR, "')' to close the argument list");
                    return new Ast.Call(t.text(), args);
                }
                return new Ast.Var(t.text());
            }
            case EOF -> throw refuse(Particle.Defect.UNBOUNDED,
                                     "unexpected end of input at line " + t.line());
            default -> throw refuse(Particle.Defect.MISBOUND,
                            "unexpected " + t.kind() + " '" + t.text()
                            + "' at line " + t.line());
        }
    }

    /* ── cursor ─────────────────────────────────────────────────────── */

    private Tok peek()  { return toks.get(p); }
    private Tok eat()   { return toks.get(p++); }
    private boolean at(Kind k) { return peek().kind() == k; }
    private boolean atKeyword(String w) {
        return peek().kind() == Kind.KW && peek().text().equals(w);
    }

    private Tok expect(Kind k, String what) {
        if (!at(k)) {
            if (at(Kind.EOF)) {
                throw refuse(Particle.Defect.UNBOUNDED,
                    "unexpected end of input at line " + peek().line());
            }
            throw refuse(Particle.Defect.MISBOUND,
                "expected " + what + ", found '" + peek().text()
                + "' at line " + peek().line());
        }
        return eat();
    }

    private void expectKeyword(String w) {
        if (!atKeyword(w)) {
            if (at(Kind.EOF)) {
                throw refuse(Particle.Defect.UNBOUNDED,
                    "unexpected end of input at line " + peek().line());
            }
            throw refuse(Particle.Defect.MISBOUND,
                "expected '" + w + "', found '" + peek().text()
                + "' at line " + peek().line());
        }
        eat();
    }

    /**
     * Internal only. A parse refusal unwinds to {@link #program()}, which
     * turns it back into a Z. Nothing throws across this class's boundary,
     * so the front end is total from the outside.
     */
    private static final class Refusal extends RuntimeException {
        private static final long serialVersionUID = 1L;
        final transient Particle z;
        Refusal(Particle z) { super(z.reason, null, false, false); this.z = z; }
    }

    private static Refusal refuse(Particle.Defect d, String why) {
        return new Refusal(Particle.z(d, why));
    }
}
