package com.codric.ezr;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * The scanner. Written from the token-kind table in 7-forge/GRAMMAR.ebnf.
 *
 * <p>Two of its rulings were open questions the forge had to settle, and both
 * are honoured here rather than guessed at again:
 *
 * <ul>
 *   <li><strong>A bare {@code <} is CMP, not OP.</strong> The four Python
 *       scanners split 2-2 on this, so consensus withheld and doctrine
 *       decided it — PIPELINE.md names CMP as the class of the comparison
 *       operator.</li>
 *   <li><strong>A string with no closing quote is {@code unbounded}</strong>,
 *       not misbound. Running out of input is unbounded; an illegal character
 *       is misbound.</li>
 * </ul>
 *
 * <p>A lexing failure is not an exception. It is a Z carrying a defect class
 * and a source position, because evaluation being total is a property of the
 * whole pipeline or it is not a property at all.
 */
public final class Lexer {

    /** Token kinds, exactly the set GRAMMAR.ebnf lists. */
    public enum Kind { NUM, STR, NAME, KW, OP, CMP, EQ, LPAR, RPAR,
                       LBRACK, RBRACK, COMMA, EOF }

    /** The eight reserved words. Not nineteen — the other eleven reserved
     *  names against a syntax that did not exist. */
    public static final Set<String> KEYWORDS =
        Set.of("def", "else", "false", "if", "in", "let", "then", "true");

    public record Tok(Kind kind, String text, int line, int col) {
        @Override public String toString() { return kind + "(" + text + ")"; }
    }

    /** Either a token list or the Z that says why there isn't one. */
    public record Out(List<Tok> tokens, Particle error) {
        public boolean ok() { return error == null; }
    }

    private final String src;
    private int i = 0, line = 1, col = 1;

    private Lexer(String src) { this.src = src; }

    public static Out lex(String source) {
        return new Lexer(source).run();
    }

    private Out run() {
        List<Tok> out = new ArrayList<>();
        while (true) {
            skipBlanksAndComments();
            if (i >= src.length()) {
                out.add(new Tok(Kind.EOF, "", line, col));
                return new Out(out, null);
            }
            int startLine = line, startCol = col;
            char c = src.charAt(i);

            if (Character.isDigit(c)) {
                out.add(number(startLine, startCol));
            } else if (c == '"') {
                Tok t = string(startLine, startCol);
                if (t == null) {
                    return new Out(null, Particle.z(Particle.Defect.UNBOUNDED,
                        "unterminated string at line " + startLine));
                }
                out.add(t);
            } else if (Character.isLetter(c) || c == '_') {
                out.add(word(startLine, startCol));
            } else {
                Tok t = punctuation(startLine, startCol);
                if (t == null) {
                    return new Out(null, Particle.z(Particle.Defect.MISBOUND,
                        "unexpected character '" + c + "' at line " + startLine
                        + " column " + startCol));
                }
                out.add(t);
            }
        }
    }

    /* ── pieces ─────────────────────────────────────────────────────── */

    private void skipBlanksAndComments() {
        while (i < src.length()) {
            char c = src.charAt(i);
            if (c == '#') {                       // comment to end of line
                while (i < src.length() && src.charAt(i) != '\n') advance();
            } else if (Character.isWhitespace(c)) {
                advance();
            } else {
                return;
            }
        }
    }

    private Tok number(int l, int c0) {
        StringBuilder sb = new StringBuilder();
        while (i < src.length() && Character.isDigit(src.charAt(i))) {
            sb.append(src.charAt(i)); advance();
        }
        // one optional fractional part; a second '.' ends the number
        if (i + 1 < src.length() && src.charAt(i) == '.'
                && Character.isDigit(src.charAt(i + 1))) {
            sb.append('.'); advance();
            while (i < src.length() && Character.isDigit(src.charAt(i))) {
                sb.append(src.charAt(i)); advance();
            }
        }
        return new Tok(Kind.NUM, sb.toString(), l, c0);
    }

    /** Returns null when the quote never closes — the caller makes that a Z. */
    private Tok string(int l, int c0) {
        advance();                                // past the opening quote
        StringBuilder sb = new StringBuilder();
        while (i < src.length()) {
            char c = src.charAt(i);
            if (c == '"') { advance(); return new Tok(Kind.STR, sb.toString(), l, c0); }
            if (c == '\n') return null;           // a string does not span lines
            sb.append(c); advance();
        }
        return null;
    }

    private Tok word(int l, int c0) {
        StringBuilder sb = new StringBuilder();
        while (i < src.length()) {
            char c = src.charAt(i);
            if (!Character.isLetterOrDigit(c) && c != '_') break;
            sb.append(c); advance();
        }
        String w = sb.toString();
        return new Tok(KEYWORDS.contains(w) ? Kind.KW : Kind.NAME, w, l, c0);
    }

    /** Returns null on a character that is not in the language. */
    private Tok punctuation(int l, int c0) {
        char c = src.charAt(i);
        char n = (i + 1 < src.length()) ? src.charAt(i + 1) : '\0';

        // two-character comparisons first, or '<' would eat the '=' of '<='
        if ((c == '<' || c == '>' || c == '=' || c == '!') && n == '=') {
            advance(); advance();
            return new Tok(Kind.CMP, "" + c + n, l, c0);
        }
        advance();
        return switch (c) {
            // settled: a bare '<' or '>' is CMP, by doctrine
            case '<', '>'           -> new Tok(Kind.CMP,    String.valueOf(c), l, c0);
            case '+', '-', '*', '/' -> new Tok(Kind.OP,     String.valueOf(c), l, c0);
            case '='                -> new Tok(Kind.EQ,     "=",  l, c0);
            case '('                -> new Tok(Kind.LPAR,   "(",  l, c0);
            case ')'                -> new Tok(Kind.RPAR,   ")",  l, c0);
            case '['                -> new Tok(Kind.LBRACK, "[",  l, c0);
            case ']'                -> new Tok(Kind.RBRACK, "]",  l, c0);
            case ','                -> new Tok(Kind.COMMA,  ",",  l, c0);
            default                 -> null;
        };
    }

    private void advance() {
        if (src.charAt(i) == '\n') { line++; col = 1; } else { col++; }
        i++;
    }
}
