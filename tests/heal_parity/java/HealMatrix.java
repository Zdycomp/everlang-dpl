import com.codric.ever.EParticle;
import com.codric.ever.EverRepair;
import com.codric.ever.RepairStore;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;

/**
 * HealMatrix.java — the Java layer's side of the heal parity matrix.
 *
 * Reads tests/heal_parity/cases.tsv. For each case it copies the prepared
 * archive into a fresh work directory, opens it as a RepairStore, runs the
 * same program the Python and C layers run, and prints one row:
 *
 *   name, value, confidence, action, trace, events, errors
 *
 * The trace, events and errors are joined with " ; "; a null field is "-".
 *
 * usage: HealMatrix <prepared-archives> <cases.tsv> <work-dir>
 */
public final class HealMatrix {

    static String cell(String s) { return s == null ? "-" : s; }

    /** A nested heal, heal/<expr>/<strategy>/<fallback>: the same operator, the
     *  same store and trace, so it is numbered and recorded as Python does it.
     *  Its primary runs first and its fallback only if the plan asks for it. */
    static EParticle nestedHeal(String token, RepairStore store, EverRepair.Trace tr) {
        String[] p = token.split("/", 4);
        EParticle inner = primary(p[1], store, tr);
        EParticle strategyP = EParticle.valued("s", p[2], 256, EParticle.Lang.EVER);
        return EverRepair.heal(inner, "x", () -> strategyP,
                () -> fallback(p[3], store, tr), store, "matrix", tr);
    }

    /** A fallback term: an integer, or a nested heal. */
    static EParticle fallback(String token, RepairStore store, EverRepair.Trace tr) {
        if (token.startsWith("heal/")) return nestedHeal(token, store, tr);
        return EParticle.valued("f", Long.valueOf(token), 256, EParticle.Lang.EVER);
    }

    static EParticle primary(String expr, RepairStore store, EverRepair.Trace tr) {
        if (expr.startsWith("heal/")) return nestedHeal(expr, store, tr);
        if (expr.startsWith("int:"))
            return EParticle.valued("x", Long.valueOf(expr.substring(4)), 256, EParticle.Lang.EVER);
        if (expr.startsWith("div:")) {
            String[] p = expr.split(":");
            return div(Long.parseLong(p[1]), Long.parseLong(p[2]));
        }
        if (expr.startsWith("nested:")) {
            String[] p = expr.split(":");
            return EverRepair.add(div(Long.parseLong(p[1]), Long.parseLong(p[2])),
                    EParticle.valued("one", 1L, 256, EParticle.Lang.EVER));
        }
        if (expr.startsWith("call:")) {
            // Java has no user functions. The callee is f(x) = 10 / x, so a
            // call's failure is that division's z, which is the weaker claim
            // this case makes for Java.
            return div(10, Long.parseLong(expr.substring(5)));
        }
        if (expr.equals("zvar")) return EParticle.z("x", null);
        throw new IllegalArgumentException("unknown expr " + expr);
    }

    static EParticle div(long a, long b) {
        return EverRepair.div(EParticle.valued("a", a, 256, EParticle.Lang.EVER),
                EParticle.valued("b", b, 256, EParticle.Lang.EVER));
    }

    static String value(EParticle p) {
        if (p.isZ()) return "z";
        Object v = p.payload();
        if (v == null) return "z";
        return v.toString();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: HealMatrix <prepared-archives> <cases.tsv> <work-dir>");
            System.exit(2);
        }
        Path prepared = Paths.get(args[0]);
        Path work = Paths.get(args[2]);
        List<String> lines = Files.readAllLines(Paths.get(args[1]), StandardCharsets.UTF_8);
        for (int i = 1; i < lines.size(); i++) {          // skip the header
            String line = lines.get(i);
            if (line.isEmpty()) continue;
            String[] f = line.split("\t", -1);
            if (f.length < 6) { System.out.println("ERROR\tshort row\t-\t-\t-\t-\t-"); continue; }
            String name = f[0], op = f[1], expr = f[2], strategy = f[3], fallback = f[4], variant = f[5];

            Path caseDir = work.resolve(name);
            Files.createDirectories(caseDir);
            Files.copy(prepared.resolve(variant).resolve(RepairStore.REPAIRS),
                    caseDir.resolve(RepairStore.REPAIRS), StandardCopyOption.REPLACE_EXISTING);
            RepairStore store = RepairStore.open(caseDir);

            EverRepair.Trace tr = new EverRepair.Trace();
            EParticle strategyP = EParticle.valued("s", strategy, 256, EParticle.Lang.EVER);
            EParticle out;
            if (op.equals("heal")) {
                out = EverRepair.heal(primary(expr, store, tr), "x", () -> strategyP,
                        () -> fallback(fallback, store, tr), store, "matrix", tr);
            } else {
                EParticle fix = fallback.equals("z") ? EParticle.z("f", "fixture is z")
                        : EParticle.valued("f", Long.valueOf(fallback), 256, EParticle.Lang.EVER);
                out = EverRepair.learn(primary(expr, store, tr), "x", () -> strategyP, fallback, fix,
                        store, "matrix", tr);
            }

            List<String> trace = tr.lines();
            List<String> events = new ArrayList<>();
            String action = "-";
            for (RepairStore.Event e : store.events()) {
                events.add(cell(e.op) + "|" + cell(e.reason) + "|" + cell(e.strategy) + "|"
                        + cell(e.action) + "|" + e.confIn + "|" + e.confOut + "|"
                        + cell(e.fixture) + "|" + e.cost + "|" + cell(e.detail));
                action = e.action;
            }
            List<String> errors = new ArrayList<>();
            for (RepairStore.Error e : store.errors())
                errors.add(cell(e.reason) + "|" + e.confidence);

            System.out.println(name + "\t" + value(out) + "\t" + out.confidence() + "\t" + action
                    + "\t" + String.join(" ; ", trace) + "\t" + String.join(" ; ", events)
                    + "\t" + String.join(" ; ", errors));
        }
    }
}
