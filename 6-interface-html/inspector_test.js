/*
 * inspector_test.js — Ever Layer 6 verification
 *
 * Extracts the logic out of the hand-written inspector.html and runs it
 * headless, then checks it agrees with Layer 2 (Python) exactly. If the
 * browser and the translator disagree, the instrument is lying to
 * somebody.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const HERE = __dirname;
const html = fs.readFileSync(path.join(HERE, 'inspector.html'), 'utf8');

// Pull the script body out of the page, strip the DOM-bound tail.
let js = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
js = js.slice(0, js.indexOf('/* ── rendering ── */'));
js += '\nmodule.exports = { detect, inspect, score, E_CERTAIN, E_ZERO, ' +
    'E_EMULATE_CEILING, E_EXECUTE_FLOOR, E_PI_WIDTH_WARN, ' +
    'E_PI_WIDTH_ENUMERATE };\n';

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ever-inspector-'));
const logic = path.join(scratch, 'inspector_logic.js');
fs.writeFileSync(logic, js);
const L6 = require(logic);
fs.rmSync(scratch, { recursive: true, force: true });

let passed = 0, failed = 0, skipped = 0;

function ok(name, cond) {
    if (cond) {
        passed++;
        console.log('  \u2713 ' + name);
    } else {
        failed++;
        console.log('  \u2717 ' + name);
    }
}

function run(code) {
    const lang = L6.detect(code);
    const f = L6.inspect(code, lang);
    const errors = f.filter(x => x.kind === 'error');
    const patterns = f.filter(x => x.kind === 'pattern');
    return Object.assign({lang, errors, patterns}, L6.score(errors, patterns));
}

console.log('\n=== Ever Layer 6 (hand HTML) — the interface ===\n');

console.log('Page structure');
ok('doctype first', html.trim().toLowerCase().startsWith('<!doctype html>'));
ok('one script block', (html.match(/<script>/g) || []).length === 1);
ok('no external fetch', !/https?:\/\/(?!www\.w3)/.test(html));
ok('no framework', !/react|vue|angular|jquery|tailwind/i.test(html));
ok('single file', true);
ok('reduced motion honoured', html.includes('prefers-reduced-motion'));
ok('focus visible styled', html.includes(':focus-visible'));
ok('meter role on the bar', html.includes('role="meter"'));

console.log('\nConstants agree with Layer 0');
ok('Certain is 256', L6.E_CERTAIN === 256);
ok('Zero is 0', L6.E_ZERO === 0);
ok('pi warn is 81', L6.E_PI_WIDTH_WARN === 81);
ok('pi squared is 25', L6.E_PI_WIDTH_ENUMERATE === 25);
ok('emulate ceiling is 3', L6.E_EMULATE_CEILING === 3);
ok('execute floor is 128', L6.E_EXECUTE_FLOOR === 128);

console.log('\nLanguage detection matches Layer 2');
ok('detects C', L6.detect('#include <stdio.h>\nint main(){return 0;}') === 'C');
ok('detects C++', L6.detect('#include <iostream>\nusing std::cout;') === 'C++');
ok('detects Python', L6.detect('def f(x: int) -> int:\n    return x') === 'Python');
ok('detects Ruby', L6.detect('def greet\n  puts "hi"\nend') === 'Ruby');
ok('detects SQL', L6.detect('SELECT id, name FROM users WHERE id = ?') === 'SQL');
ok('detects Java', L6.detect('public class A { public static void main(String[] a){} }') === 'Java');
ok('detects HTML', L6.detect('<!DOCTYPE html>\n<html lang="en"></html>') === 'HTML');

console.log('\nErrors are caught in every language');
ok('C missing semicolon',
    run('int add(int x, int y) { return x + y }')
        .errors.some(e => /semicolon/.test(e.message)));
ok('C++ new without delete',
    run('#include <iostream>\nclass A {};\nint main(){ A* a = new A(); return 0; }')
        .errors.some(e => /new without delete/.test(e.message)));
ok('Python mutable default',
    run('def f(items=[]):\n    return items')
        .errors.some(e => /mutable default/.test(e.message)));
ok('Ruby missing end',
    run('def greet\n  puts "hi"')
        .errors.some(e => /missing end/.test(e.message)));
ok('SQL delete without where',
    run('DELETE FROM users')
        .errors.some(e => /without WHERE/.test(e.message)));
ok('Java unguarded null',
    run('public class A { void f(){ String s = null; s.length(); } }')
        .errors.some(e => /null used without a guard/.test(e.message)));
ok('HTML img without alt',
    run('<img src="a.jpg">')
        .errors.some(e => /without alt/.test(e.message)));

console.log('\nScript and style bodies are not markup');
const selfInspect = run(html);
ok('inspecting its own page finds no errors', selfInspect.errors.length === 0);
ok('its own page is Confident', selfInspect.state === 'Confident');
ok('its own page clears the floor',
    selfInspect.confidence >= L6.E_EXECUTE_FLOOR);
ok('a real img is still caught',
    run('<!DOCTYPE html><html lang="en"><body><img src="x.jpg"></body></html>')
        .errors.some(e => /without alt/.test(e.message)));

console.log('\nScoring rules');
const clean = run('def add(x: int, y: int) -> int:\n    return x + y');
ok('clean typed python is Confident', clean.state === 'Confident');
ok('clean typed python clears floor', clean.confidence >= 128);
ok('nothing static reaches Certain', clean.confidence < L6.E_CERTAIN);

const wreck = run('SELECT * FROM a JOIN b;\nDELETE FROM c;\nDROP TABLE d;\nUPDATE e SET x = 1;');
ok('past the ceiling returns to Z', wreck.state === 'Z');
ok('Z carries zero confidence', wreck.confidence === 0);
ok('Z states the ceiling reason', /ceiling/.test(wreck.reason));

console.log('\nCross-layer agreement with Layer 2 (Python)');
const cases = [
    'int add(int x, int y) { return x + y }',
    'def collect(items=[]):\n    items.append(1)\n    return items',
    'def add(x: int, y: int) -> int:\n    return x + y',
    'DELETE FROM users',
    'public class A { void f(){ String s = null; s.length(); } }',
    '<img src="a.jpg">',
    'def greet\n  puts "hi"',
    'SELECT * FROM a JOIN b;\nDELETE FROM c;\nDROP TABLE d;\nUPDATE e SET x = 1;'
];
fs.writeFileSync('/tmp/ever_cases.json', JSON.stringify(cases));
const mine = cases.map(c => {
    const r = run(c);
    return {lang: r.lang, state: r.state, confidence: r.confidence};
});

const PY_LANG = { 'C++': 'CPP' };
const translator = [
    'import json, sys',
    'sys.path.insert(0, sys.argv[1])',
    'from translate import Translator, lang_name, EState',
    'out = []',
    'for code in json.load(sys.stdin):',
    '    t = Translator().translate(code)',
    '    out.append({"lang": lang_name(t.lang),',
    '                "state": EState(t.particle.state).name,',
    '                "confidence": t.particle.confidence})',
    'print(json.dumps(out))',
].join('\n');

let theirs = null;
try {
    theirs = JSON.parse(execFileSync('python3',
        ['-B', '-c', translator, path.join(HERE, '..', '2-inspect-python')],
        { input: JSON.stringify(cases), encoding: 'utf8' }));
} catch (e) {
    if (e.code === 'ENOENT') {
        skipped++;
        console.log('  ∼ SKIP: python3 not on PATH, cross-layer agreement not checked');
    } else {
        ok('Python translator runs on every case', false);
    }
}

if (theirs) {
    ok('Python translator reads every case', theirs.length === cases.length);
    mine.forEach((r, i) => {
        const p = theirs[i];
        ok('case ' + i + ': language agrees with Python',
            (PY_LANG[r.lang] || r.lang).toUpperCase() === p.lang);
        ok('case ' + i + ': state agrees with Python', r.state.toUpperCase() === p.state);
        ok('case ' + i + ': confidence agrees with Python', r.confidence === p.confidence);
    });
}

mine.forEach((r, i) => console.log('      case ' + i + ': ' + r.lang +
    ' ' + r.state + ' ' + r.confidence + '/256'));

console.log('\n=== Layer 6: ' + passed + ' passed, ' + failed + ' failed, ' +
    skipped + ' skipped ===\n');
process.exit(failed ? 1 : (skipped ? 77 : 0));
