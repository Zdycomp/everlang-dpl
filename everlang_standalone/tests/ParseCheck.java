import com.sun.source.util.JavacTask;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/**
 * Syntax-only oracle for heal_bench.py: parses each file named in args[0]
 * (one path per line) with javac's own parser and prints OK or ERR per file.
 * Nothing is resolved or compiled, so files need no classpath.
 * Run as a single-file program: java ParseCheck.java files.txt
 */
public class ParseCheck {
    public static void main(String[] a) throws Exception {
        JavaCompiler c = ToolProvider.getSystemJavaCompiler();
        StandardJavaFileManager fm = c.getStandardFileManager(null, null, null);
        for (String f : Files.readAllLines(Path.of(a[0]))) {
            DiagnosticCollector<JavaFileObject> d = new DiagnosticCollector<>();
            boolean ok;
            try {
                JavacTask t = (JavacTask) c.getTask(null, fm, d, List.of("-proc:none"), null,
                        fm.getJavaFileObjects(Path.of(f)));
                t.parse();
                ok = d.getDiagnostics().stream().noneMatch(x -> x.getKind() == Diagnostic.Kind.ERROR);
            } catch (Exception e) {
                ok = false;
            }
            System.out.println(ok ? "OK" : "ERR");
        }
    }
}
