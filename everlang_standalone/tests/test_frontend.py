import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from everlang.core.reinforced_archive import ReinforcedArchive
from everlang.frontend import (
    BaselineExecutor, BaselineLexer, BaselineParser, Collision, Declaration, MegaExecuter,
    QuantificationUltraParser, Supercodalexer, compile_and_run,
)
from everlang.frontend.bench import make_program, measure
from everlang.frontend.mega_executer import compile_renderer
from everlang.transpiler import SuperTranspiler

REPO_ROOT = Path(__file__).resolve().parents[2]
CPP_BINARY = REPO_ROOT / "1-phase-cpp" / "bin" / "verify_particle"


def kinds(tokens):
    return [t[0] for t in tokens]


class TestSupercodalexer(unittest.TestCase):
    def lex(self, src):
        return Supercodalexer().lex(src)

    def test_canonical_declaration_tokens_and_columns(self):
        toks, diags = self.lex('particle p : E<T> = "v" @ confidence(5)\n')
        self.assertEqual(diags, [])
        self.assertEqual([(t[0], t[1], t[3]) for t in toks], [
            ("KW_PARTICLE", "particle", 1), ("IDENT", "p", 10), ("COLON", ":", 12), ("IDENT", "E", 14),
            ("LT", "<", 15), ("IDENT", "T", 16), ("GT", ">", 17), ("EQ", "=", 19), ("STRING", "v", 21),
            ("AT", "@", 25), ("KW_CONFIDENCE", "confidence", 27), ("LPAREN", "(", 37), ("INT", "5", 38),
            ("RPAREN", ")", 39), ("NEWLINE", "\n", 40), ("EOF", "", 1),
        ])

    def test_loose_spacing_and_comment(self):
        toks, diags = self.lex('  particle  rate:E< float >="0.5"@confidence ( 200 )  # note')
        self.assertEqual(diags, [])
        self.assertEqual(toks[0][3], 3)
        self.assertEqual([t[1] for t in toks if t[0] in ("IDENT", "STRING", "INT")], ["rate", "E", "float", "0.5", "200"])

    def test_string_escapes_are_decoded(self):
        toks, _ = self.lex('particle x : E<T> = "a\\"b\\\\" @ confidence(1)')
        self.assertEqual(toks[8][1], 'a"b\\')

    def test_keyword_as_name_is_lexed_as_keyword(self):
        toks, _ = self.lex('particle collide : E<T> = "v" @ confidence(1)')
        self.assertEqual(toks[1][0], "KW_COLLIDE")

    def test_every_bad_character_is_reported(self):
        _, diags = self.lex("$ é\n%")
        self.assertEqual([(d.line, d.col, d.message) for d in diags], [
            (1, 1, "unexpected character '$'"), (1, 3, "unexpected character 'é'"),
            (2, 1, "unexpected character '%'"),
        ])

    def test_unterminated_string_and_unknown_escape(self):
        _, diags = self.lex('"open\n"bad\\q"')
        self.assertEqual([d.message for d in diags], ["unterminated string", "unknown escape sequence in string"])

    def test_dash_hint_suggests_arrow(self):
        _, diags = self.lex("collide a b - c")
        self.assertEqual(diags[0].hint, "did you mean '->'?")

    def test_crlf_and_trailing_whitespace(self):
        toks, diags = self.lex("collide a b\r\ncollide c d  ")
        self.assertEqual(diags, [])
        self.assertEqual(toks[-1], ("EOF", "", 2, 14))

    def test_token_stream_records_verified_declarations(self):
        toks, _ = self.lex('collide a b\nparticle p : E<T> = "v" @ confidence(5)\n')
        self.assertEqual(toks.declaration_starts, (4,))


class TestQuantificationUltraParser(unittest.TestCase):
    def parse(self, src):
        return QuantificationUltraParser().parse(Supercodalexer().lex(src)[0])

    def test_declaration_and_collisions(self):
        result = self.parse('particle a : E<T> = "v" @ confidence(90)\ncollide a b\ncollide a b -> c\n')
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(result.statements, [
            Declaration("a", "T", "v", 90, 1), Collision("a", "b", None, 2), Collision("a", "b", "c", 3),
        ])

    def test_error_has_hint_and_parsing_resumes(self):
        result = self.parse('particle a : E<T> = "v" confidence(9)\nparticle b : E<T> = "w" @ confidence(8)')
        self.assertEqual(len(result.diagnostics), 1)
        diag = result.diagnostics[0]
        self.assertEqual((diag.line, diag.col, diag.message), (1, 25, "expected '@', found 'confidence'"))
        self.assertIn("@ confidence(N)", diag.hint)
        self.assertEqual([s.name for s in result.statements], ["b"])

    def test_every_bad_line_is_reported(self):
        result = self.parse("hello\ncollide a\nparticle\ncollide a b c")
        self.assertEqual([d.line for d in result.diagnostics], [1, 2, 3, 4])
        self.assertEqual(result.diagnostics[3].message, "expected end of line, found 'c'")

    def test_lexer_errors_are_not_reported_twice(self):
        tokens, lex_diags = Supercodalexer().lex("collide a $ b")
        result = QuantificationUltraParser().parse(tokens)
        self.assertEqual(len(lex_diags), 1)
        self.assertEqual(result.diagnostics, [])

    def test_plain_token_list_parses_identically(self):
        tokens, _ = Supercodalexer().lex(make_program(50))
        self.assertEqual(QuantificationUltraParser().parse(list(tokens)), QuantificationUltraParser().parse(tokens))


class TestMegaExecuter(unittest.TestCase):
    def run_src(self, src, **kwargs):
        return compile_and_run(src, **kwargs)

    def test_declaration_produces_particle_and_every_rendering(self):
        result = self.run_src('particle rate : E<float> = "0.5" @ confidence(200)')
        decl = result.execution.declarations[0]
        self.assertEqual(result.execution.particles["rate"].confidence, 200)
        self.assertEqual(decl.renderings, SuperTranspiler().transpile("rate", "0.5", "float", 200))

    def test_dpl_rendering_round_trips(self):
        source = 'particle rate : E<float> = "0.5" @ confidence(200)'
        result = self.run_src(source)
        self.assertEqual(result.execution.declarations[0].renderings["DPL"], source)

    def test_dpl_renderings_of_a_whole_program_read_back_identically(self):
        first = self.run_src(make_program(200))
        dpl = "\n".join(d.renderings["DPL"] for d in first.execution.declarations)
        second = self.run_src(dpl)
        self.assertEqual(second.diagnostics, [])
        self.assertEqual([d[:4] for d in second.execution.declarations],
                         [d[:4] for d in first.execution.declarations])

    def test_dpl_rendering_with_quotes_and_backslashes_reads_back_identically(self):
        rng = random.Random(99)
        alphabet = 'ab "\\\\#@()<>:= \t\n\r'
        for _ in range(300):
            value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
            dpl = SuperTranspiler().transpile("q", value, "T", 7)["DPL"]
            back = self.run_src(dpl)
            self.assertEqual(back.diagnostics, [], repr(value))
            self.assertEqual(back.execution.declarations[0].value, value)
            self.assertEqual(back.execution.declarations[0].renderings["DPL"], dpl)

    def test_newline_and_carriage_return_escapes_decode(self):
        result = self.run_src('particle q : E<T> = "a\\nb\\rc\\\\n" @ confidence(1)')
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(result.execution.declarations[0].value, "a\nb\rc\\n")

    def test_v2_dpl_output_reads_back_at_every_confidence_tier(self):
        from everlang.transpiler.super_transpiler_v2 import SuperTranspilerV2
        value = 'say "hi"\\path\nnext'
        for conf in (10, 120, 230):
            dpl = SuperTranspilerV2().transpile("q", value, "str", conf)["DPL"]
            back = self.run_src(dpl)
            self.assertEqual(back.diagnostics, [], (conf, dpl))
            self.assertEqual(back.execution.declarations[0].value, value)

    def test_custom_language_renderings_included(self):
        transpiler = SuperTranspiler()
        transpiler.register_language("TOML", '{name} = "{val}"  # {type_spec}/{conf}')
        result = self.run_src('particle k : E<T> = "v" @ confidence(7)', transpiler=transpiler)
        self.assertEqual(result.execution.declarations[0].renderings["TOML"], 'k = "v"  # T/7')

    def test_confidence_above_256_is_clamped_with_warning(self):
        result = self.run_src('particle k : E<T> = "v" @ confidence(300)')
        self.assertEqual(result.execution.particles["k"].confidence, 256)
        self.assertEqual(result.diagnostics[0].severity, "warning")

    def test_collision_outcomes_and_chaining(self):
        result = self.run_src(
            'particle a : E<T> = "x" @ confidence(200)\n'
            'particle b : E<T> = "y" @ confidence(180)\n'
            'particle c : E<T> = "z" @ confidence(40)\n'
            'particle d : E<T> = "w" @ confidence(0)\n'
            'collide a b -> ab\n'
            'collide ab c\n'
            'collide a d\n'
        )
        self.assertEqual(result.diagnostics, [])
        self.assertEqual([c.outcome for c in result.execution.collisions], ["EXCEL", "EXPEL", "Z_CONTAGION"])
        self.assertIn("ab", result.execution.particles)

    def test_unbound_and_rebound_names_are_errors_execution_continues(self):
        result = self.run_src(
            'particle a : E<T> = "x" @ confidence(10)\n'
            'particle a : E<T> = "y" @ confidence(20)\n'
            'collide a ghost\n'
            'collide a a -> a\n'
            'particle z : E<T> = "ok" @ confidence(30)\n'
        )
        self.assertEqual([d.message for d in result.diagnostics], [
            "'a' is already bound", "'ghost' is not bound", "'a' is already bound",
        ])
        self.assertEqual(result.execution.particles["a"].value, "x")
        self.assertIn("z", result.execution.particles)

    def test_compiled_renderer_matches_str_format_for_hostile_literals(self):
        templates = {
            "Q": "'''\"\"\" {name} \\n {{x}} {val}",
            "SPEC": "{name:>5} {val}",
            "WEIRD'KEY": "{name}={val}",
        }
        render = compile_renderer(templates)
        expected = {k: v.format(name="n", val="v", type_spec="t", conf=1) for k, v in templates.items()}
        self.assertEqual(render("n", "v", "t", 1), expected)

    def test_renderer_cache_is_bounded(self):
        from everlang.frontend import mega_executer
        for i in range(mega_executer._COMPILED_MAX + 10):
            compile_renderer({"L": f"{i} {{name}} {{val}}"})
        self.assertLessEqual(len(mega_executer._COMPILED), mega_executer._COMPILED_MAX)

    @unittest.skipUnless(CPP_BINARY.is_file(), "1-phase-cpp not built (run `make -C 1-phase-cpp`)")
    def test_archive_receives_renderings_and_collisions(self):
        db_path = str(Path(tempfile.mkdtemp()) / "frontend.db")
        archive = ReinforcedArchive(sql_db_path=db_path)
        self.addCleanup(archive.close)
        self.run_src('particle a : E<T> = "x" @ confidence(200)\n'
                     'particle b : E<T> = "y" @ confidence(180)\n'
                     'collide a b\n', archive=archive)
        conn = sqlite3.connect(db_path)
        try:
            transpilations = conn.execute("SELECT COUNT(*) FROM transpilations").fetchone()[0]
            markers = conn.execute("SELECT context FROM boundary_markers").fetchall()
        finally:
            conn.close()
        self.assertEqual(transpilations, 2 * len(SuperTranspiler().templates))
        self.assertEqual(markers, [("collide a b",)])


class TestBaselineEquivalence(unittest.TestCase):
    """Mega stages must agree with the textbook baseline on any input."""

    ATOMS = ["particle", "collide", "confidence", "E", "p1", "_x9", ":", "<", ">", "=", "@", "(", ")", "->",
             "-", '"v"', '"a\\"b"', '"bad\\q"', '"open', "12", "300", "#c", " ", "\t", "\r", "é", "$", "\\"]
    GOOD = ['particle p : E<T> = "v" @ confidence(5)', 'particle  rate:E< float >="0.5"@confidence ( 200 )  # c',
            "collide a b", "collide a b -> c", 'particle collide : E<T> = "v" @ confidence(1)',
            'particle a : E<T> = "v" @ confidence(90)', 'particle b : E<T> = "w" @ confidence(300)']

    def assert_equivalent(self, src):
        bt, bd = BaselineLexer().lex(src)
        mt, md = Supercodalexer().lex(src)
        self.assertEqual((list(mt), md), (bt, bd), repr(src))
        bp, mp = BaselineParser().parse(bt), QuantificationUltraParser().parse(mt)
        self.assertEqual(mp, bp, repr(src))
        be, me = BaselineExecutor().execute(bp.statements), MegaExecuter().execute(mp.statements)
        self.assertEqual((me.declarations, me.collisions, me.diagnostics),
                         (be.declarations, be.collisions, be.diagnostics), repr(src))

    def test_generated_program(self):
        self.assert_equivalent(make_program(300))

    def test_random_programs(self):
        rng = random.Random(1234)
        for _ in range(400):
            lines = [rng.choice(self.GOOD) if rng.random() < 0.5 else
                     "".join(rng.choice(self.ATOMS) + rng.choice(["", " "]) for _ in range(rng.randint(0, 9)))
                     for _ in range(rng.randint(1, 5))]
            self.assert_equivalent(rng.choice(["\n", "\r\n"]).join(lines) + rng.choice(["", "\n", "  "]))


class TestSpeed(unittest.TestCase):
    """Regression floors with headroom for timing noise; `python3 -m
    everlang.frontend.bench` reports the actual ratios (see frontend/README.md)."""

    def test_mega_pipeline_is_faster_than_baseline(self):
        t = measure(lines=2000, repeats=3)
        lex_ratio = t["baseline"]["lex"] / t["mega"]["lex"]
        total_ratio = t["baseline"]["total"] / t["mega"]["total"]
        self.assertGreaterEqual(lex_ratio, 3.0, f"Supercodalexer only {lex_ratio:.2f}x baseline")
        self.assertGreaterEqual(total_ratio, 2.0, f"Mega pipeline only {total_ratio:.2f}x baseline")


if __name__ == "__main__":
    unittest.main()
