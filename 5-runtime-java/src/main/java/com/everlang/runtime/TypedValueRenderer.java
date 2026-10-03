package com.everlang.runtime;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Pure re-derivation of a typed transpilation row, mirroring the Python source of truth:
 *
 * {@code everlang_standalone/everlang/transpiler/typed.py :: render_typed, escape_string}
 *
 * <p>A typed row ({@code value_kind} set) stores the value's canonical DPL literal in
 * {@code val}: {@code 85.5}, {@code -7}, {@code true}, or a list such as
 * {@code ["tcp", "udp"]}. {@link #parse} reads that literal back into items; {@link #render}
 * renders them with each built-in language's native type and literal syntax:
 *
 * <pre>
 *            Str          Int        Float     Bool      (literal suffix)
 * KOTLIN     String       Long       Double    Boolean   Int: L
 * RUST       String       i64        f64       bool      Str: "...".to_string()
 * C_CLANG    char*        long long  double    bool
 * GO         string       int64      float64   bool
 * GROOVY     String       Long       Double    Boolean   Int: L, Float: d
 * </pre>
 *
 * Scalars: {@code val n: T? = lit} (Kotlin), {@code let n: Option<T> = Some(lit);} (Rust),
 * {@code const T n = lit;} (C), {@code var n T = lit} (Go), {@code T n = lit // confidence(c)}
 * (Groovy). Lists: {@code listOf(..)}, {@code Some(vec![..])}, {@code const T n[len] = {..};},
 * {@code []T{..}}, {@code List<T> n = [..]}. DPL: {@code particle n : E<type_spec> = literal
 * @ confidence(c)}. Plain string scalars are never typed rows.
 *
 * <p>Literal syntax is checked (an Int must be canonical and within ±(2^63-1), a Float must
 * contain '.' or an exponent and be finite, a Bool is {@code true}/{@code false}), but a Float's
 * digits are emitted exactly as stored rather than re-derived from Python's {@code repr}.
 */
final class TypedValueRenderer {

    static final List<String> KINDS = List.of(
            "Int", "Float", "Bool", "List<Str>", "List<Int>", "List<Float>", "List<Bool>");

    private static final Pattern INT_TEXT = Pattern.compile("-?[0-9]+");
    private static final Pattern FLOAT_TEXT = Pattern.compile("-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?");

    private static final Map<String, Map<String, String>> NATIVE_TYPES = Map.of(
            "KOTLIN", Map.of("Str", "String", "Int", "Long", "Float", "Double", "Bool", "Boolean"),
            "RUST", Map.of("Str", "String", "Int", "i64", "Float", "f64", "Bool", "bool"),
            "C_CLANG", Map.of("Str", "char*", "Int", "long long", "Float", "double", "Bool", "bool"),
            "GO", Map.of("Str", "string", "Int", "int64", "Float", "float64", "Bool", "bool"),
            "GROOVY", Map.of("Str", "String", "Int", "Long", "Float", "Double", "Bool", "Boolean"));

    private TypedValueRenderer() {
    }

    static boolean isList(String kind) {
        return kind.startsWith("List<");
    }

    static String elementKind(String kind) {
        return isList(kind) ? kind.substring(5, kind.length() - 1) : kind;
    }

    /**
     * Parses a canonical DPL literal of the given kind into its items (raw strings for
     * {@code Str}, literal text otherwise). Throws IllegalArgumentException if the text is
     * not a well-formed literal of that kind.
     */
    static List<String> parse(String kind, String literal) {
        if (!KINDS.contains(kind)) {
            throw new IllegalArgumentException("unknown value kind " + kind);
        }
        String element = elementKind(kind);
        List<String> items = new ArrayList<>();
        if (!isList(kind)) {
            items.add(checkScalar(element, literal));
            return items;
        }
        int n = literal.length();
        if (n < 2 || literal.charAt(0) != '[' || literal.charAt(n - 1) != ']') {
            throw new IllegalArgumentException("a list literal is written [a, b, ...]");
        }
        int i = 1;
        while (true) {
            int end;
            if (element.equals("Str")) {
                StringBuilder raw = new StringBuilder();
                end = readString(literal, i, raw);
                items.add(raw.toString());
            } else {
                end = i;
                while (end < n - 1 && literal.charAt(end) != ',') {
                    end++;
                }
                items.add(checkScalar(element, literal.substring(i, end)));
            }
            if (end == n - 1) {
                return items;
            }
            if (!literal.startsWith(", ", end)) {
                throw new IllegalArgumentException("list items are separated by \", \"");
            }
            i = end + 2;
        }
    }

    /** Reads a DPL string literal starting at {@code start}; returns the index after its closing quote. */
    private static int readString(String text, int start, StringBuilder raw) {
        if (start >= text.length() || text.charAt(start) != '"') {
            throw new IllegalArgumentException("expected a quoted string at offset " + start);
        }
        int i = start + 1;
        while (i < text.length()) {
            char c = text.charAt(i);
            if (c == '"') {
                return i + 1;
            }
            if (c == '\n') {
                break;
            }
            if (c == '\\') {
                if (i + 1 >= text.length()) {
                    break;
                }
                switch (text.charAt(i + 1)) {
                    case '"' -> raw.append('"');
                    case '\\' -> raw.append('\\');
                    case 'n' -> raw.append('\n');
                    case 'r' -> raw.append('\r');
                    default -> throw new IllegalArgumentException("unknown escape \\" + text.charAt(i + 1));
                }
                i += 2;
                continue;
            }
            raw.append(c);
            i++;
        }
        throw new IllegalArgumentException("unterminated string");
    }

    private static String checkScalar(String kind, String text) {
        switch (kind) {
            case "Int" -> {
                if (!INT_TEXT.matcher(text).matches()) {
                    throw new IllegalArgumentException("not an Int literal: " + text);
                }
                long value;
                try {
                    value = Long.parseLong(text);
                } catch (NumberFormatException e) {
                    throw new IllegalArgumentException("Int outside the 64-bit range: " + text);
                }
                if (value == Long.MIN_VALUE || !Long.toString(value).equals(text)) {
                    throw new IllegalArgumentException("not a canonical Int literal: " + text);
                }
            }
            case "Float" -> {
                boolean marked = text.indexOf('.') >= 0 || text.indexOf('e') >= 0 || text.indexOf('E') >= 0;
                if (!FLOAT_TEXT.matcher(text).matches() || !marked || !Double.isFinite(Double.parseDouble(text))) {
                    throw new IllegalArgumentException("not a finite Float literal: " + text);
                }
            }
            case "Bool" -> {
                if (!text.equals("true") && !text.equals("false")) {
                    throw new IllegalArgumentException("not true or false: " + text);
                }
            }
            default -> throw new IllegalArgumentException("unknown scalar kind " + kind);
        }
        return text;
    }

    /**
     * Mirrors {@code typed.py :: escape_string}: backslash, double quote, newline and carriage
     * return everywhere; {@code $} for Kotlin and Groovy; every other control character except
     * tab as {@code \ooo} (C), {@code \xhh} (Rust, Go) or {@code \\uhhhh} (Kotlin, Groovy); and in C
     * each {@code ?} that follows a {@code ?}. DPL leaves other control characters raw.
     */
    static String escapeString(String language, String text) {
        StringBuilder out = new StringBuilder(text.length() + 8);
        char prev = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '\\') {
                out.append("\\\\");
            } else if (c == '"') {
                out.append("\\\"");
            } else if (c == '\n') {
                out.append("\\n");
            } else if (c == '\r') {
                out.append("\\r");
            } else if (c == '$' && (language.equals("KOTLIN") || language.equals("GROOVY"))) {
                out.append("\\$");
            } else if (c == '?' && prev == '?' && language.equals("C_CLANG")) {
                out.append("\\?");
            } else if (c < ' ' && c != '\t' && !language.equals("DPL")) {
                switch (language) {
                    case "C_CLANG" -> out.append(String.format("\\%03o", (int) c));
                    case "RUST", "GO" -> out.append(String.format("\\x%02x", (int) c));
                    default -> out.append(String.format("\\u%04x", (int) c));
                }
            } else {
                out.append(c);
            }
            prev = c;
        }
        return out.toString();
    }

    private static String literal(String language, String kind, String item) {
        return switch (kind) {
            case "Str" -> {
                String quoted = "\"" + escapeString(language, item) + "\"";
                yield language.equals("RUST") ? quoted + ".to_string()" : quoted;
            }
            case "Int" -> language.equals("KOTLIN") || language.equals("GROOVY") ? item + "L" : item;
            case "Float" -> language.equals("GROOVY") ? item + "d" : item;
            default -> item;
        };
    }

    /** Canonical DPL literal of the items (what Python stores as {@code val}). */
    static String dplLiteral(String kind, List<String> items) {
        if (!isList(kind)) {
            return items.get(0);
        }
        List<String> parts = new ArrayList<>();
        for (String item : items) {
            parts.add(elementKind(kind).equals("Str") ? "\"" + escapeString("DPL", item) + "\"" : item);
        }
        return "[" + String.join(", ", parts) + "]";
    }

    /** Expected rendering, or null if {@code language} is not a built-in language. */
    static String render(String language, String name, String kind, List<String> items, String typeSpec, int conf) {
        if (language.equals("DPL")) {
            return "particle " + name + " : E<" + typeSpec + "> = " + dplLiteral(kind, items)
                    + " @ confidence(" + conf + ")";
        }
        Map<String, String> types = NATIVE_TYPES.get(language);
        if (types == null) {
            return null;
        }
        String element = elementKind(kind);
        String nativeType = types.get(element);
        List<String> literals = new ArrayList<>();
        for (String item : items) {
            literals.add(literal(language, element, item));
        }
        if (!isList(kind)) {
            String lit = literals.get(0);
            return switch (language) {
                case "KOTLIN" -> "val " + name + ": " + nativeType + "? = " + lit;
                case "RUST" -> "let " + name + ": Option<" + nativeType + "> = Some(" + lit + ");";
                case "C_CLANG" -> "const " + nativeType + " " + name + " = " + lit + ";";
                case "GO" -> "var " + name + " " + nativeType + " = " + lit;
                default -> nativeType + " " + name + " = " + lit + " // confidence(" + conf + ")";
            };
        }
        String joined = String.join(", ", literals);
        return switch (language) {
            case "KOTLIN" -> "val " + name + ": List<" + nativeType + ">? = listOf(" + joined + ")";
            case "RUST" -> "let " + name + ": Option<Vec<" + nativeType + ">> = Some(vec![" + joined + "]);";
            case "C_CLANG" -> "const " + nativeType + " " + name + "[" + literals.size() + "] = {" + joined + "};";
            case "GO" -> "var " + name + " []" + nativeType + " = []" + nativeType + "{" + joined + "}";
            default -> "List<" + nativeType + "> " + name + " = [" + joined + "] // confidence(" + conf + ")";
        };
    }
}
