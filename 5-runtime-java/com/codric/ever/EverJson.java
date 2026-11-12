package com.codric.ever;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * EverJson.java — the JSON the repair store reads and writes.
 *
 * Zero dependencies, because this layer goes into other people's builds.
 * It reads any RFC 8259 value and writes objects, arrays, strings, numbers,
 * booleans and null. The files it touches are the ReFix archive's
 * (repairs.jsonl, errors.jsonl) and the Python registry's, so a record it
 * writes must still be a record they can read.
 *
 * Codric Enterprise · Ricky (Dreid) · 2026
 */
public final class EverJson {

    private final String src;
    private int pos;

    private EverJson(String src) { this.src = src; }

    /** Parse one JSON value. The whole input must be consumed. */
    public static Object parse(String text) {
        EverJson p = new EverJson(text);
        p.skipWs();
        Object v = p.value();
        p.skipWs();
        if (p.pos != text.length())
            throw new IllegalArgumentException("trailing text at " + p.pos);
        return v;
    }

    /** Parse one line that must be a JSON object. */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(String line) {
        Object v = parse(line);
        if (!(v instanceof Map))
            throw new IllegalArgumentException("not a JSON object");
        return (Map<String, Object>) v;
    }

    private Object value() {
        if (pos >= src.length()) throw error("unexpected end");
        char c = src.charAt(pos);
        switch (c) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case 't': return literal("true", Boolean.TRUE);
            case 'f': return literal("false", Boolean.FALSE);
            case 'n': return literal("null", null);
            default:
                if (c == '-' || (c >= '0' && c <= '9')) return number();
                throw error("unexpected character '" + c + "'");
        }
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        pos++;                                   // {
        skipWs();
        if (peek('}')) { pos++; return m; }
        while (true) {
            skipWs();
            if (!peek('"')) throw error("expected a key");
            String k = string();
            skipWs();
            expect(':');
            skipWs();
            m.put(k, value());
            skipWs();
            if (peek(',')) { pos++; continue; }
            expect('}');
            return m;
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        pos++;                                   // [
        skipWs();
        if (peek(']')) { pos++; return a; }
        while (true) {
            skipWs();
            a.add(value());
            skipWs();
            if (peek(',')) { pos++; continue; }
            expect(']');
            return a;
        }
    }

    private String string() {
        pos++;                                   // opening quote
        StringBuilder b = new StringBuilder();
        while (true) {
            if (pos >= src.length()) throw error("unterminated string");
            char c = src.charAt(pos++);
            if (c == '"') return b.toString();
            if (c != '\\') { b.append(c); continue; }
            if (pos >= src.length()) throw error("unterminated escape");
            char e = src.charAt(pos++);
            switch (e) {
                case '"': b.append('"'); break;
                case '\\': b.append('\\'); break;
                case '/': b.append('/'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'n': b.append('\n'); break;
                case 'r': b.append('\r'); break;
                case 't': b.append('\t'); break;
                case 'u':
                    if (pos + 4 > src.length()) throw error("short \\u escape");
                    b.append((char) Integer.parseInt(src.substring(pos, pos + 4), 16));
                    pos += 4;
                    break;
                default: throw error("bad escape \\" + e);
            }
        }
    }

    private Object number() {
        int start = pos;
        if (peek('-')) pos++;
        while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
        boolean real = false;
        if (peek('.')) {
            real = true; pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
        }
        if (peek('e') || peek('E')) {
            real = true; pos++;
            if (peek('+') || peek('-')) pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
        }
        String t = src.substring(start, pos);
        try {
            return real ? (Object) Double.valueOf(t) : (Object) Long.valueOf(t);
        } catch (NumberFormatException ex) {
            throw error("bad number " + t);
        }
    }

    private Object literal(String word, Object v) {
        if (!src.startsWith(word, pos)) throw error("expected " + word);
        pos += word.length();
        return v;
    }

    private void skipWs() {
        while (pos < src.length()) {
            char c = src.charAt(pos);
            if (c == ' ' || c == '\t' || c == '\r' || c == '\n') pos++;
            else break;
        }
    }

    private boolean peek(char c) { return pos < src.length() && src.charAt(pos) == c; }

    private void expect(char c) {
        if (!peek(c)) throw error("expected '" + c + "'");
        pos++;
    }

    private IllegalArgumentException error(String what) {
        return new IllegalArgumentException(what + " at " + pos);
    }

    /* ── writing ── */

    /** A JSON string literal, escaped. */
    public static String quote(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n");  break;
                case '\r': b.append("\\r");  break;
                case '\t': b.append("\\t");  break;
                case '\b': b.append("\\b");  break;
                case '\f': b.append("\\f");  break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append('"').toString();
    }

    /** One object as a single line, keys in insertion order. Null values are written. */
    public static String write(Map<String, Object> m) {
        StringBuilder b = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> e : m.entrySet()) {
            if (!first) b.append(", ");
            first = false;
            b.append(quote(e.getKey())).append(": ").append(value(e.getValue()));
        }
        return b.append('}').toString();
    }

    private static String value(Object v) {
        if (v == null) return "null";
        if (v instanceof String) return quote((String) v);
        if (v instanceof Boolean || v instanceof Long || v instanceof Integer) return v.toString();
        if (v instanceof Double) {
            double d = (Double) v;
            if (Double.isNaN(d) || Double.isInfinite(d))
                throw new IllegalArgumentException("JSON has no NaN or infinity");
            return v.toString();
        }
        if (v instanceof Map) {
            StringBuilder b = new StringBuilder("{");
            boolean first = true;
            for (Object o : ((Map<?, ?>) v).entrySet()) {
                Map.Entry<?, ?> e = (Map.Entry<?, ?>) o;
                if (!first) b.append(", ");
                first = false;
                b.append(quote(String.valueOf(e.getKey()))).append(": ").append(value(e.getValue()));
            }
            return b.append('}').toString();
        }
        if (v instanceof List) {
            StringBuilder b = new StringBuilder("[");
            boolean first = true;
            for (Object o : (List<?>) v) {
                if (!first) b.append(", ");
                first = false;
                b.append(value(o));
            }
            return b.append(']').toString();
        }
        throw new IllegalArgumentException("cannot write " + v.getClass().getSimpleName());
    }
}
