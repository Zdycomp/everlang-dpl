# Everlang Semantics Plan

## Current State
- **Exists**: 4-stage pipeline, DNA sequencer, 6-language transpiler, confidence model
- **Missing**: Textual language syntax, parser, IR, execution engine

## Path to Language Viability

### Phase 1: Define Everlang Syntax (SEMANTICS.md)
```
GOAL: Define the textual Everlang language that can be parsed and executed

1. Value types (particles):
   - EParticle{value: str, confidence: 0-256}
   - Literal syntax: particle name : Type = "value" @ confidence(N)
   
2. Operations (phase transitions):
   - Collide: two particles → state transition (Z_CONTAGION, EXCEL, EXPEL, REPEL)
   - Repair: particle with error → auto-heal using formula
   - Swap: entangled particles → restore from anchor
   
3. Control flow:
   - Sequential (pipe operator |)
   - Conditional (if confidence > N)
   - Loops (while valid)
   
4. Built-in functions:
   - confidence(p): get confidence
   - distance(p, q): compute error distance
   - collide(p, q, rule): trigger state transition
   - repair(p, errors): invoke self-healing
   
5. Example program:
   ```everlang
   particle x : String = "hello" @ confidence(200)
   particle y : String = "world" @ confidence(180)
   
   rule fusion = collide(x, y, excel_rule)
   result : String = fusion | repair(errors)
   return result @ confidence(fusion.confidence)
   ```

### Phase 2: Build Parser (2-interpreter-python/everlang_parser.py)
```
Pattern: Follow DnaSequencer's lexer/parser split
- DnaLexer → BaseToken (proven pattern)
- DnaParser → structured output
  
For Everlang:
- EverlangLexer → Token (keyword, identifier, literal, operator)
- EverlangParser → AST (ParticleDecl, Operation, ControlFlow)

Use same error recovery: invalid tokens → ERROR token, continue parsing
```

### Phase 3: Build IR & Lowering (ir.py → tac.c)
```
Convert Everlang AST → Three-Address Code (TAC)

Example:
  particle x = "v" @ 200
  ↓ (ir.py)
  Assign(name=x, value="v", confidence=200)
  ↓ (tac.c)
  x_1 = "v"
  x_confidence = 200
  verify_particle(x_1, x_confidence)
```

### Phase 4: Build Executor (5-runtime-java)
```
Currently: read-only auditors
Needed: TAC interpreter
  - State machine for particles
  - Collision/repair/swap operations
  - Output final result
```

## Effort Estimate
- **SEMANTICS.md**: 1-2 weeks (design, document, examples)
- **Parser (2-interpreter-python/)**: 2-4 weeks (lexer, parser, error recovery)
- **IR/Lowering (ir.py, tac.c)**: 3-4 weeks (optimizer passes)
- **Executor (5-runtime-java)**: 2-3 weeks (TAC interpreter)
- **Integration tests**: 1-2 weeks

**Total: 2-3 months to viable language**

## Alternative: Ship Reusable Tools First
Rather than a full language, ship these now:
1. **DnaSequencer** - standalone DNA analysis tool (pip install everlang-dna)
2. **SuperTranspiler** - multi-language snippet generator (pip install everlang-transpiler)
3. **EParticle + PhaseEngine** - probabilistic state machine framework (pip install everlang-particles)

These are **immediately useful** and **production-ready**.
Then build the language as a layer on top.

## Recommendation
**Ship reusable tools first** (2-4 weeks), then commit to full language (2-3 months).
This gives users value while you build the full vision.
