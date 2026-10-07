package com.codric.ezr;

import java.util.List;

/**
 * The abstract syntax tree, matching the node set that 7-forge/contract.py
 * fixes for every front end: Num, Str, Bool, Var, Bin, If, Call, Def, Prog,
 * Lst, Let. Nothing outside that set is a node, because nothing outside
 * GRAMMAR.ebnf is EZR.
 *
 * <p>Written as a sealed interface over records. That is not decoration: the
 * exhaustiveness check on a switch over a sealed type is what makes
 * <strong>G1 (evaluation is total)</strong> a compile-time property here
 * rather than a convention. If a node kind is ever added and the evaluator
 * does not handle it, this layer stops compiling. The Python interpreter
 * cannot make that check; it is the kind of thing a second implementation in
 * a different language is <em>for</em>.
 */
public sealed interface Ast {

    /** A number literal. Held as double; EZR has no integer type yet. */
    record Num(double value) implements Ast { }

    /** A string literal. */
    record Str(String value) implements Ast { }

    /** true or false. */
    record Bool(boolean value) implements Ast { }

    /** A name in reference position. */
    record Var(String name) implements Ast { }

    /** A binary operator: + - * / and the six comparisons. */
    record Bin(String op, Ast left, Ast right) implements Ast { }

    /** if c then a else b. Lazy under a known condition; see Eval. */
    record If(Ast cond, Ast then, Ast otherwise) implements Ast { }

    /** A call: name(args). */
    record Call(String name, List<Ast> args) implements Ast { }

    /** def name(params) = body. */
    record Def(String name, List<String> params, Ast body) implements Ast { }

    /** let name = value in body. */
    record Let(String name, Ast value, Ast body) implements Ast { }

    /** A list literal. */
    record Lst(List<Ast> items) implements Ast { }

    /**
     * A whole program: a run of definitions, or a single expression.
     * Never both — "trailing_expression = False" was settled by the forge,
     * because {@code def f(n) = 1 - 1} would otherwise have two derivations.
     */
    record Prog(List<Def> defs, Ast expr) implements Ast { }

    /**
     * How many nodes this subtree holds. The AST measures structure, which is
     * the whole reason PIPELINE.md gives for having one: {@code n * 1} is
     * three nodes and {@code n} is one, and {@code ((n))} is one.
     */
    static int size(Ast n) {
        return switch (n) {
            case Num  x -> 1;
            case Str  x -> 1;
            case Bool x -> 1;
            case Var  x -> 1;
            case Bin  x -> 1 + size(x.left()) + size(x.right());
            case If   x -> 1 + size(x.cond()) + size(x.then()) + size(x.otherwise());
            case Call x -> 1 + x.args().stream().mapToInt(Ast::size).sum();
            case Def  x -> 1 + size(x.body());
            case Let  x -> 1 + size(x.value()) + size(x.body());
            case Lst  x -> 1 + x.items().stream().mapToInt(Ast::size).sum();
            case Prog x -> x.defs().stream().mapToInt(Ast::size).sum()
                           + (x.expr() == null ? 0 : size(x.expr()));
        };
    }

    /**
     * The shape with constants and operators collapsed — what PIPELINE.md
     * calls the skeleton. Two candidate solutions with the same skeleton are
     * one idea in different hats, and one idea cannot corroborate itself.
     */
    /**
     * A faithful, canonical re-rendering of a node — unlike
     * {@link #skeleton}, which deliberately erases literal values.
     *
     * <p>Used to tell one Example's witness from another. `f(1,2)` and
     * `f( 1 , 2 )` must render the same (they are one witness stated
     * twice) and `f(1)` and `f(2)` must not (they are two witnesses),
     * which is exactly the distinction skeleton throws away: under it
     * both are {@code CALL(K, K)}.
     *
     * <p>Numbers go through {@link Particle#renderValue} so a whole
     * double renders as {@code 1} rather than {@code 1.0}, matching how
     * every other surface in this runtime prints one.
     */
    static String render(Ast n) {
        return switch (n) {
            case Num  x -> Particle.renderValue(x.value());
            case Str  x -> "\"" + x.value() + "\"";
            case Bool x -> x.value() ? "true" : "false";
            case Var  x -> x.name();
            case Bin  x -> "(" + render(x.left()) + " " + x.op() + " "
                           + render(x.right()) + ")";
            case If   x -> "if " + render(x.cond()) + " then " + render(x.then())
                           + " else " + render(x.otherwise());
            case Call x -> x.name() + "(" + joinRenders(x.args()) + ")";
            case Def  x -> "def " + x.name() + "(" + String.join(", ", x.params())
                           + ") = " + render(x.body());
            case Let  x -> "let " + x.name() + " = " + render(x.value())
                           + " in " + render(x.body());
            case Lst  x -> "[" + joinRenders(x.items()) + "]";
            case Prog x -> x.expr() == null ? joinRenders(x.defs())
                                            : render(x.expr());
        };
    }

    private static String joinRenders(List<? extends Ast> xs) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < xs.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append(render(xs.get(i)));
        }
        return sb.toString();
    }

    static String skeleton(Ast n) {
        return switch (n) {
            case Num  x -> "K";
            case Str  x -> "K";
            case Bool x -> "K";
            case Var  x -> "V";
            case Bin  x -> "(" + skeleton(x.left())
                           + (isCompare(x.op()) ? " CMP " : " OP ")
                           + skeleton(x.right()) + ")";
            case If   x -> "if " + skeleton(x.cond()) + " then " + skeleton(x.then())
                           + " else " + skeleton(x.otherwise());
            case Call x -> "CALL(" + joinSkeletons(x.args()) + ")";
            case Def  x -> "def(" + skeleton(x.body()) + ")";
            case Let  x -> "let " + skeleton(x.value()) + " in " + skeleton(x.body());
            case Lst  x -> "[" + joinSkeletons(x.items()) + "]";
            case Prog x -> x.expr() == null ? joinSkeletons(x.defs())
                                            : skeleton(x.expr());
        };
    }

    private static String joinSkeletons(List<? extends Ast> xs) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < xs.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append(skeleton(xs.get(i)));
        }
        return sb.toString();
    }

    static boolean isCompare(String op) {
        return switch (op) {
            case "<", ">", "<=", ">=", "==", "!=" -> true;
            default -> false;
        };
    }
}
