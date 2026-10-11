#!/usr/bin/env ruby
# frozen_string_literal: true

# ever.rb — Ever / Tapestry, Layer 3 (Ruby)
#
# The DSL. The writable surface of the weave.
#
# Ruby owns this layer because Ruby was built for building languages
# inside it. Blocks and instance_eval let EZR's constructs read as
# syntax rather than as method calls.
#
#   weave = EZR.weave("invoice") do
#     anchor :total, 500
#     let    :rate, 0.08
#     ever   :tax, from: [:total, :rate], op: :*
#     ascend :tax, by: 130
#     assimilate :total, to: :rust
#     show   :tax
#   end
#
# Codric Enterprise · Ricky (Dreid) · 2026

module EZR
  # constants, identical to 0-atom-c/tapestry.h
  ZERO               = 0
  CERTAIN            = 256
  EXECUTE_FLOOR      = 128
  PI_WIDTH_WARN      = 81
  PI_WIDTH_ENUMERATE = 25
  EMULATE_CEILING    = 3
  ASCEND_POINTS      = 3
  INTAKE             = 120
  PHI                = 1.6180339887

  STATES  = %i[z confident certain equivalence expression
               emulating evolved anchored absent eerror].freeze
  DEFECTS = %i[none unbound misbound unbounded overbound orphaned].freeze
  LANGS   = %i[c cpp python ruby sql java html rust go ts swift ever].freeze

  # ═══════════════════════════════════════════
  # The thread
  # ═══════════════════════════════════════════

  class Thread
    attr_reader :ident, :value, :state, :defect, :confidence, :lo, :hi,
                :lang, :anchor_id, :generation, :ascend_points,
                :error_distance, :reason

    def initialize(ident:, value: nil, state: :z, defect: :none,
                   confidence: ZERO, lo: nil, hi: nil, lang: :ever,
                   anchor_id: 0, generation: 0, ascend_points: 0,
                   error_distance: 0, reason: '')
      @ident          = ident.to_s
      @value          = value
      @state          = state
      @defect         = defect
      @confidence     = confidence
      @lo             = lo || confidence
      @hi             = hi || confidence
      @lang           = lang
      @anchor_id      = anchor_id
      @generation     = generation
      @ascend_points  = ascend_points
      @error_distance = error_distance
      @reason         = reason
      freeze
    end

    # ── constructors ──

    def self.z(ident, reason = 'unverified', defect = :unbound)
      new(ident: ident, state: :z, defect: defect, reason: reason)
    end

    def self.val(ident, value, conf, lang: :ever)
      return z(ident, 'confidence collapsed to zero') if conf <= ZERO

      st = conf >= CERTAIN ? :certain : :confident
      c  = [conf, CERTAIN].min
      new(ident: ident, value: value, state: st, confidence: c, lang: lang)
    end

    def self.equivalence(ident, range, lang: :ever)
      lo, hi = range.min, range.max
      new(ident: ident, value: (lo + hi) / 2, state: :equivalence,
          lo: lo, hi: hi, confidence: (lo + hi) / 2, lang: lang)
    end

    def self.expression(ident, lang: :ever)
      new(ident: ident, state: :expression, lang: lang,
          reason: 'shape bound, value pending')
    end

    def self.eerror(ident, reason, defect: :misbound, at: 0)
      new(ident: ident, state: :eerror, defect: defect,
          lo: at, hi: at, reason: reason)
    end

    # ── predicates ──

    def z?        = state == :z
    def cleared?  = !%i[z eerror absent].include?(state) && confidence > ZERO
    def execute?  = cleared? && confidence >= EXECUTE_FLOOR
    def anchored? = anchor_id.positive?
    def width     = hi - lo

    def pi_status
      return :approaching_z if width > PI_WIDTH_WARN
      return :enumerate     if width > PI_WIDTH_ENUMERATE

      :acceptable
    end

    def type_name
      case value
      when nil            then 'void'
      when true, false    then 'bool'
      when Integer        then 'int'
      when Float          then 'real'
      when String         then 'text'
      when Array          then 'list'
      else 'foreign'
      end
    end

    # ── derivation ──

    def with(**changes)
      Thread.new(
        ident:          changes.fetch(:ident, ident),
        value:          changes.fetch(:value, value),
        state:          changes.fetch(:state, state),
        defect:         changes.fetch(:defect, defect),
        confidence:     changes.fetch(:confidence, confidence),
        lo:             changes.fetch(:lo, lo),
        hi:             changes.fetch(:hi, hi),
        lang:           changes.fetch(:lang, lang),
        anchor_id:      changes.fetch(:anchor_id, anchor_id),
        generation:     changes.fetch(:generation, generation),
        ascend_points:  changes.fetch(:ascend_points, ascend_points),
        error_distance: changes.fetch(:error_distance, error_distance),
        reason:         changes.fetch(:reason, reason)
      )
    end

    # Z is contagious. Enforced here as in every other layer.
    def carry(new_ident)
      return Thread.z(new_ident, reason, defect)          if z?
      return Thread.z(new_ident, 'upstream error', :misbound) if state == :eerror
      return Thread.z(new_ident, 'upstream absent', :unbound) if state == :absent

      with(ident: new_ident)
    end

    def cap(ceiling)
      return Thread.z(ident, 'capped to zero') if ceiling <= ZERO
      return self if confidence <= ceiling

      with(confidence: ceiling,
           state: state == :certain ? :confident : state,
           lo: [lo, ceiling].min, hi: [hi, ceiling].min)
    end

    def serialize
      [STATES.index(state), type_name, LANGS.index(lang),
       DEFECTS.index(defect), confidence, lo, hi, error_distance,
       generation, ascend_points, anchor_id, -1,
       (Time.now.to_f * 1000).to_i, ident, value, reason].join('|')
    end

    def to_s
      return "E<Z>(#{ident} \u2014 #{reason})" if z?

      mark = anchored? ? "\u2693" : ''
      "E<#{state}>#{mark}(#{ident} = #{value.inspect} @ #{confidence}/256)"
    end
    alias inspect to_s
  end

  # ═══════════════════════════════════════════
  # The six A-operators
  # ═══════════════════════════════════════════

  NOTHING = %w[null nil None NULL undefined nullptr Z].freeze

  module_function

  # ANY — lift any language's literal into a thread
  def any(ident, literal, from: :ever)
    s = literal.to_s.strip
    return Thread.z(ident, 'no literal to lift') if s.empty?
    return Thread.z(ident, "#{from} expressed nothing", :unbound) if NOTHING.include?(s)

    return Thread.val(ident, true,  INTAKE, lang: from) if %w[true True TRUE].include?(s)
    return Thread.val(ident, false, INTAKE, lang: from) if %w[false False FALSE].include?(s)

    if s.length >= 2 && ['"', "'"].include?(s[0])
      return Thread.val(ident, s[1..-2], INTAKE, lang: from) if s[-1] == s[0]

      return Thread.z(ident, 'unterminated string literal', :unbounded)
    end

    return Thread.val(ident, Integer(s), INTAKE, lang: from) if s.match?(/\A-?\d+\z/)
    return Thread.val(ident, Float(s), INTAKE, lang: from) if s.match?(/\A-?\d*\.\d+\z/)

    Thread.val(ident, s, 100, lang: from)
          .with(reason: 'lifted as foreign, shape unresolved')
  end

  # ASSIMILATE — carry a thread into another language.
  # Anchored crosses free; unanchored pays one, so drift stays visible.
  def assimilate(thread, to:)
    return Thread.z(thread.ident, 'Z does not translate', thread.defect) if thread.z?

    if thread.state == :eerror
      return Thread.z(thread.ident, 'misbound thread does not translate', :misbound)
    end
    return thread if thread.lang == to

    if thread.anchored?
      thread.with(lang: to,
                  reason: "assimilated #{thread.lang} to #{to}, " \
                          "anchor #{thread.anchor_id} held")
    else
      c = [thread.confidence - 1, 1].max
      # Certain means exactly 256. A thread that paid for a crossing is
      # no longer Certain and must say so.
      st = thread.state == :certain ? :confident : thread.state
      thread.with(lang: to, confidence: c, lo: c, hi: c, state: st,
                  reason: "assimilated #{thread.lang} to #{to}, " \
                          'unanchored, -1 confidence')
    end
  end

  @anchor_seq = 1000

  def anchor(thread, anchor_id = nil)
    unless thread.cleared?
      return Thread.z(thread.ident, 'cannot anchor an uncleared binding',
                      thread.defect == :none ? :unbound : thread.defect)
    end

    anchor_id ||= (@anchor_seq += 1)
    return Thread.z(thread.ident, 'anchor id zero is reserved') if anchor_id.zero?

    thread.with(anchor_id: anchor_id, state: :anchored,
                reason: "anchored #{anchor_id} at confidence #{thread.confidence}")
  end

  # Multiplicative uncertainty: u_result = u_a * u_b. A product of
  # non-zero ignorances is never zero, so combination approaches Certain
  # without attaining it. Capping one short keeps Certain earned.
  def excel(a, b)
    return CERTAIN if a >= CERTAIN && b >= CERTAIN

    [[a + b - (a * b / CERTAIN), CERTAIN - 1].min, ZERO].max
  end

  # [EXAMPLE], SEMANTICS.md 4.2 — evidence earns confidence.
  #
  #   u_f = ((CERTAIN - INTAKE)/CERTAIN) ** p
  #   c_f = floor(CERTAIN * (1 - u_f) * p/t), capped one short of CERTAIN
  #
  # Each passing Example is an INDEPENDENT witness at intake strength, so
  # Examples corroborate rather than chain: 1/1 is 120 and still under the
  # execute floor, 2/2 clears at 183, 3/3 is 217. A failure scales the
  # result by the share that held, so 2 of 3 is 122 and back under.
  def from_examples(passing, total)
    return ZERO if total <= 0

    passing = 0 if passing.negative?
    unit = (CERTAIN - INTAKE).to_f / CERTAIN
    u    = passing.zero? ? 1.0 : unit**passing
    c    = (CERTAIN * (1.0 - u) * (passing.to_f / total)).floor
    [[c, CERTAIN - 1].min, ZERO].max
  end

  # [EXAMPLE] solved for the evidence still owed, rather than the score.
  #
  # The least k further PASSING witnesses that reach `target`, or nil when
  # it is out of reach within `cap`. Walked rather than inverted: the
  # forward rule is monotone in k and saturates one short of CERTAIN, so
  # walking up from 0 finds the least sufficient k or proves there is
  # none. A failure already recorded cannot be withdrawn, so the answer
  # accounts for it — 1 of 9 needs eight more, not one.
  #
  # A refusal that says only "below the execute floor" has deleted the
  # half a person can act on. This is that half.
  def witnesses_needed(passing, total, target = EXECUTE_FLOOR, cap = 64)
    (0..cap).each { |k| return k if from_examples(passing + k, total + k) >= target }
    nil
  end

  # ASCEND — the only path upward. Three aligned points.
  def ascend(thread, evidence)
    return Thread.z(thread.ident, 'Z cannot ascend; it must be resolved', thread.defect) if thread.z?
    return thread unless evidence.cleared?

    gap = (evidence.confidence - thread.confidence).abs
    if gap > PI_WIDTH_ENUMERATE
      return thread.with(ascend_points: 0,
                         reason: "evidence disagreed by #{gap}, ascent reset")
    end

    points = thread.ascend_points + 1
    if points < ASCEND_POINTS
      return thread.with(ascend_points: points,
                         reason: "ascending: #{points} of #{ASCEND_POINTS} points")
    end

    c = excel(thread.confidence, evidence.confidence)
    thread.with(confidence: c, lo: c, hi: c, ascend_points: 0,
                generation: thread.generation + 1,
                state: c >= CERTAIN ? :certain : :evolved,
                reason: "ascended on #{ASCEND_POINTS} aligned points to #{c}, " \
                        "generation #{thread.generation + 1}")
  end

  # APPLY2ALL — broadcast, halting at the first Z
  def apply2all(threads)
    out = []
    threads.each_with_index do |t, i|
      return [out + threads[i..], i] if t.z?

      out << yield(t)
    end
    [out, -1]
  end

  # AUTO-DIDACT — derive a rule from the corpus's own history
  def autodidact(history, about)
    return Thread.z(about, 'history too short to derive a rule') if history.size < ASCEND_POINTS

    defects = history.reject(&:cleared?).map(&:defect).reject { |d| d == :none }
    unless defects.empty?
      common = defects.group_by(&:itself).max_by { |_, v| v.size }
      if common[1].size >= ASCEND_POINTS
        return Thread.val(about, common[0].to_s, 180)
                     .with(reason: "derived: #{common[0]} recurs #{common[1].size} times")
      end
    end

    cleared = history.select(&:cleared?)
    return Thread.z(about, 'too few cleared observations to derive') if cleared.size < ASCEND_POINTS

    confs  = cleared.map(&:confidence)
    mean   = confs.sum / confs.size
    spread = confs.max - confs.min
    return Thread.z(about, 'history too scattered to derive a rule', :unbounded) if spread > PI_WIDTH_WARN

    Thread.val(about, mean, spread <= PI_WIDTH_ENUMERATE ? 200 : 150)
          .with(lo: confs.min, hi: confs.max,
                reason: "derived from #{cleared.size} observations, " \
                        "mean #{mean}, spread #{spread}")
  end

  # Arithmetic: the result is worth the weaker input. You cannot become
  # more certain by combining things you were less certain about.
  def combine(a, b, op, ident)
    return Thread.z(ident, "operand #{a.ident} is Z", a.defect) if a.z?
    return Thread.z(ident, "operand #{b.ident} is Z", b.defect) if b.z?

    begin
      return Thread.z(ident, 'division by zero', :misbound) if op == :/ && b.value.zero?

      v = a.value.public_send(op, b.value)
    rescue NoMethodError, TypeError, ZeroDivisionError
      return Thread.z(ident,
                      "cannot #{op} #{a.type_name} with #{b.type_name}", :misbound)
    end

    Thread.val(ident, v, [a.confidence, b.confidence].min)
          .with(reason: "#{a.ident} #{op} #{b.ident}, worth the weaker input")
  end

  def phi_equalize(threads)
    return { balanced: [], flagged: [] } if threads.empty?

    mean = threads.sum(&:confidence) / threads.size
    hi_b = (mean * PHI).to_i
    lo_b = (mean / PHI).to_i
    bal, flag = threads.partition { |t| t.confidence.between?(lo_b, hi_b) }
    { balanced: bal, flagged: flag }
  end

  # ═══════════════════════════════════════════
  # The DSL
  # ═══════════════════════════════════════════

  class Weave
    attr_reader :name, :threads, :archive, :history, :output, :blocked

    def initialize(name)
      @name    = name
      @threads = {}
      @archive = []
      @history = Hash.new { |h, k| h[k] = [] }
      @output  = []
      @blocked = 0
    end

    def record(t)
      @threads[t.ident.to_sym] = t
      @history[t.ident.to_sym] << t
      @archive << t unless t.cleared?
      t
    end

    def fetch(sym)
      @threads[sym.to_sym] || Thread.z(sym.to_s, 'never bound')
    end

    # ── constructs ──

    def z(ident, reason = 'declared unknown')
      record(Thread.z(ident.to_s, reason))
    end

    def let(ident, value, conf: INTAKE, lang: :ever)
      record(Thread.val(ident.to_s, value, conf, lang: lang))
    end

    def anchor(ident, value = nil, conf: INTAKE)
      t = value.nil? ? fetch(ident) : Thread.val(ident.to_s, value, conf)
      record(EZR.anchor(t))
    end

    def equiv(ident, range)
      record(Thread.equivalence(ident.to_s, range))
    end

    def express(ident)
      record(Thread.expression(ident.to_s))
    end

    def ever(ident, from:, op:)
      a = fetch(from[0])
      b = fetch(from[1])
      record(EZR.combine(a, b, op, ident.to_s))
    end

    def ascend(ident, by:)
      t  = fetch(ident)
      ev = Thread.val("#{ident}_evidence", t.value, by)
      record(EZR.ascend(t, ev))
    end

    def assimilate(ident, to:)
      record(EZR.assimilate(fetch(ident), to: to))
    end

    def expect(ident, at_least:)
      t = fetch(ident)
      return t if t.confidence >= at_least

      @blocked += 1
      @output << "  BLOCKED #{ident}: expected >= #{at_least}, had #{t.confidence}"
      record(Thread.z(ident.to_s,
                      "expected >= #{at_least}, had #{t.confidence}"))
    end

    def learn(ident)
      rule = EZR.autodidact(@history[ident.to_sym], "#{ident}_rule")
      @output << "  LEARNED #{rule}"
      record(rule)
    end

    def show(ident)
      t = fetch(ident)
      @output << if t.z?
                   "  #{ident} = Z  (#{t.reason})"
                 elsif !t.execute?
                   "  #{ident} withheld: #{t.confidence}/256 is below the " \
                   "execute floor of #{EXECUTE_FLOOR}"
                 else
                   mark = t.anchored? ? " \u2693" : ''
                   "  #{ident} = #{t.value.inspect}  " \
                   "[#{t.confidence}/256 #{t.state}#{mark}]"
                 end
      t
    end

    def report
      out = ["\n  weave: #{name}", '  ' + ("\u2500" * 54)]
      @threads.each_value do |t|
        next if t.ident.end_with?('_evidence')

        out << "    #{t}"
      end
      out << ''
      out << "  threads #{@threads.size}   archived #{@archive.size}   " \
             "blocked #{@blocked}"
      out.join("\n")
    end
  end

  def weave(name, &block)
    w = Weave.new(name)
    w.instance_eval(&block)
    w
  end
end

# ─────────────────────────────────────────────
# Self-verification
# ─────────────────────────────────────────────

if __FILE__ == $PROGRAM_NAME
  passed = 0
  failed = 0
  ok = lambda { |name, cond|
    if cond
      passed += 1
      puts "  \u2713 #{name}"
    else
      failed += 1
      puts "  \u2717 #{name}"
    end
  }

  puts "\n=== Tapestry Layer 3 (Ruby) — the DSL ===\n\n"

  puts 'Constants agree with the C atom'
  ok.call('Certain 256',       EZR::CERTAIN == 256)
  ok.call('execute floor 128', EZR::EXECUTE_FLOOR == 128)
  ok.call('pi warn 81',        EZR::PI_WIDTH_WARN == 81)
  ok.call('pi squared 25',     EZR::PI_WIDTH_ENUMERATE == 25)
  ok.call('emulate ceiling 3', EZR::EMULATE_CEILING == 3)
  ok.call('ascend points 3',   EZR::ASCEND_POINTS == 3)

  puts "\nThe thread carries T"
  n = EZR::Thread.val('count', 42, 180)
  ok.call('holds its value',  n.value == 42)
  ok.call('knows its type',   n.type_name == 'int')
  ok.call('carries confidence', n.confidence == 180)
  ok.call('text type',  EZR::Thread.val('s', 'hi', 150).type_name == 'text')
  ok.call('real type',  EZR::Thread.val('r', 1.5, 150).type_name == 'real')
  ok.call('bool type',  EZR::Thread.val('b', true, 150).type_name == 'bool')
  ok.call('Z holds nothing', EZR::Thread.z('x').value.nil?)

  puts "\nA1 ANY"
  ok.call('lifts int',   EZR.any('x', '42').value == 42)
  ok.call('lifts real',  EZR.any('y', '3.14').type_name == 'real')
  ok.call('lifts text',  EZR.any('s', '"hello"').value == 'hello')
  ok.call('lifts bool',  EZR.any('b', 'true').value == true)
  %w[null nil None undefined nullptr].each do |w|
    ok.call("#{w} lifts to Z", EZR.any('n', w).z?)
  end
  ok.call('unterminated is unbounded',
          EZR.any('s', '"oops').defect == :unbounded)
  ok.call('intake below floor',
          EZR.any('x', '42').confidence < EZR::EXECUTE_FLOOR)

  puts "\nA2 ASSIMILATE"
  py = EZR::Thread.val('total', 99, 200, lang: :python)
  rs = EZR.assimilate(py, to: :rust)
  ok.call('payload survives', rs.value == 99)
  ok.call('language changed', rs.lang == :rust)
  ok.call('unanchored pays 1', rs.confidence == 199)
  ok.call('Z does not translate', EZR.assimilate(EZR::Thread.z('u'), to: :go).z?)

  puts "\nA3 ANCHOR"
  anc = EZR.anchor(py, 7001)
  ok.call('anchor set', anc.anchored?)
  ok.call('state anchored', anc.state == :anchored)
  h = anc
  %i[rust swift java go ts].each { |l| h = EZR.assimilate(h, to: l) }
  ok.call('five hops no loss', h.confidence == 200)
  ok.call('anchor held', h.anchor_id == 7001)
  ok.call('payload held', h.value == 99)
  d = py
  %i[rust swift java go ts].each { |l| d = EZR.assimilate(d, to: l) }
  ok.call('unanchored drifts 5', d.confidence == 195)
  ok.call('anchoring is the difference', h.confidence > d.confidence)
  ok.call('cannot anchor a Z', EZR.anchor(EZR::Thread.z('u')).z?)

  puts "\nA4 ASCEND"
  base = EZR::Thread.val('parse', 1, 150)
  ev   = EZR::Thread.val('e', 1, 160)
  s1 = EZR.ascend(base, ev)
  ok.call('one point no lift', s1.confidence == 150)
  s3 = EZR.ascend(EZR.ascend(s1, ev), ev)
  ok.call('three points lift', s3.confidence > 150)
  ok.call('matches excel', s3.confidence == EZR.excel(150, 160))
  ok.call('generation advanced', s3.generation == 1)
  ok.call('disagreement resets',
          EZR.ascend(s1, EZR::Thread.val('f', 1, 40)).ascend_points.zero?)
  ok.call('Z cannot ascend', EZR.ascend(EZR::Thread.z('u'), ev).z?)

  puts "\nA5 APPLY2ALL"
  res, halt = EZR.apply2all([EZR::Thread.val('a', 1, 200),
                              EZR::Thread.val('b', 2, 180)]) do |t|
    t.with(confidence: t.confidence / 2)
  end
  ok.call('all transformed', halt == -1 && res[0].confidence == 100)
  res, halt = EZR.apply2all([EZR::Thread.val('a', 1, 200),
                              EZR::Thread.z('b'),
                              EZR::Thread.val('c', 3, 160)]) do |t|
    t.with(confidence: t.confidence / 2)
  end
  ok.call('halts at Z', halt == 1)
  ok.call('past halt untouched', res[2].confidence == 160)

  puts "\nA6 AUTO-DIDACT"
  hist = [170, 175, 180, 178].map { |c| EZR::Thread.val('o', 1, c) }
  rule = EZR.autodidact(hist, 'conf')
  ok.call('rule derived', rule.cleared?)
  ok.call('rule holds mean', rule.value == 175)
  ok.call('rule records spread', rule.lo == 170 && rule.hi == 180)
  ok.call('under three refuses', EZR.autodidact(hist[0, 2], 'x').z?)
  ok.call('scattered refuses',
          EZR.autodidact([20, 240, 60, 200].map { |c| EZR::Thread.val('o', 1, c) },
                          's').z?)

  puts "\nArithmetic propagates confidence"
  a = EZR::Thread.val('a', 10, 200)
  b = EZR::Thread.val('b', 3, 150)
  ok.call('result is weaker input', EZR.combine(a, b, :*, 'c').confidence == 150)
  ok.call('value computed', EZR.combine(a, b, :*, 'c').value == 30)
  ok.call('Z operand yields Z', EZR.combine(a, EZR::Thread.z('u'), :+, 'c').z?)
  ok.call('div by zero is Z',
          EZR.combine(a, EZR::Thread.val('z', 0, 200), :/, 'c').z?)

  puts "\nEquivalence and pi"
  ok.call('width computed', EZR::Thread.equivalence('s', 100..115).width == 15)
  ok.call('15 acceptable',
          EZR::Thread.equivalence('s', 100..115).pi_status == :acceptable)
  ok.call('26 enumerate',
          EZR::Thread.equivalence('s', 100..126).pi_status == :enumerate)
  ok.call('150 approaching Z',
          EZR::Thread.equivalence('s', 50..200).pi_status == :approaching_z)

  puts "\nZ contagion"
  zz = EZR::Thread.z('unknown', 'not set')
  ok.call('Z carried stays Z', zz.carry('downstream').z?)
  ok.call('defect carried', zz.carry('downstream').defect == :unbound)

  puts "\nThe DSL weaves"
  w = EZR.weave('invoice') do
    anchor :total, 500
    let    :rate, 0.08
    ever   :tax, from: %i[total rate], op: :*
    ascend :total, by: 130
    ascend :total, by: 135
    ascend :total, by: 132
    assimilate :total, to: :rust
    assimilate :total, to: :swift
    show   :total
    z      :ocr, 'OCR not run'
    ever   :parsed, from: %i[ocr total], op: :+
    show   :parsed
    equiv  :severity, 100..115
    expect :tax, at_least: 200
    learn  :total
  end
  ok.call('weave produced output', !w.output.empty?)
  ok.call('anchored total held across two hops',
          w.fetch(:total).confidence == 191)
  ok.call('anchor survived the weave', w.fetch(:total).anchored?)
  ok.call('Z contagion in the weave', w.fetch(:parsed).z?)
  ok.call('expect blocked', w.blocked.positive?)
  ok.call('archive kept the failures', !w.archive.empty?)

  puts "\nSerialization"
  line = EZR.anchor(EZR::Thread.val('t', 99, 200), 7001).serialize
  ok.call('sixteen fields', line.split('|').size == 16)
  ok.call('carries the payload', line.include?('99'))
  ok.call('carries the anchor', line.include?('7001'))

  puts "\n=== Layer 3: #{passed} passed, #{failed} failed ===\n\n"
  exit(failed.zero? ? 0 : 1)
end
