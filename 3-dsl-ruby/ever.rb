#!/usr/bin/env ruby
# frozen_string_literal: true

# ever.rb — Ever Language, Layer 3 (Ruby)
#
# The DSL. This is where Ever stops being a library and becomes a language
# you write.
#
# Ruby owns this layer because Ruby was built for people writing languages
# inside it. Blocks, method_missing and open classes let Ever's eight
# constructs read as syntax rather than as function calls.
#
#   Codric Enterprise · Ricky (Dreid) · 2026
#   Theory of Relative E:  E = MC²
#
# The eight constructs:
#   Z · Expression · Equivalence · Expect · Example
#   Enumerate/Estimate · Emulate · Evolve
#
# Written:
#
#   result = Ever.examine("invoice_total") do
#     express     :parsed_amount
#     equivalence :severity, 100..115
#     expect      :parsed_amount, min_confidence: 128, or_z: true
#     emulate     :broken_parse, from: :working_parse, distance: 1
#     evolve      :parser
#   end

module Ever
  # ── constants, identical to 0-core-c/ever.h ──
  ZERO               = 0
  CERTAIN            = 256
  PI_WIDTH_WARN      = 81    # int(256 / pi)
  PI_WIDTH_ENUMERATE = 25    # int(256 / pi**2)
  EMULATE_CEILING    = 3     # int(pi)
  PHI                = 1.6180339887

  STATES = %i[z confident certain equivalence expression
              emulating evolved absent eerror].freeze

  LANGS = %i[c cpp python ruby sql java html ever].freeze

  # ─────────────────────────────────────────────
  # Particle
  # ─────────────────────────────────────────────

  class Particle
    attr_reader :ident, :state, :lang, :confidence, :lo, :hi,
                :reason, :error_distance, :generation

    def initialize(ident:, state: :z, confidence: ZERO, lo: nil, hi: nil,
                   lang: :ever, reason: '', error_distance: 0, generation: 0)
      @ident          = ident.to_s
      @state          = state
      @lang           = lang
      @confidence     = confidence
      @lo             = lo || confidence
      @hi             = hi || confidence
      @reason         = reason
      @error_distance = error_distance
      @generation     = generation
      freeze
    end

    # ── constructors ──

    def self.z(ident, reason = 'unverified')
      new(ident: ident, state: :z, confidence: ZERO, reason: reason)
    end

    def self.certain(ident, lang: :ever)
      new(ident: ident, state: :certain, confidence: CERTAIN, lang: lang)
    end

    def self.confident(ident, degree, lang: :ever)
      return z(ident, 'confidence collapsed to zero') if degree <= ZERO
      return certain(ident, lang: lang)              if degree >= CERTAIN

      new(ident: ident, state: :confident, confidence: degree, lang: lang)
    end

    def self.equivalence(ident, range, lang: :ever)
      lo, hi = range.min, range.max
      new(ident: ident, state: :equivalence, lo: lo, hi: hi,
          confidence: (lo + hi) / 2, lang: lang)
    end

    def self.expression(ident, lang: :ever)
      new(ident: ident, state: :expression, confidence: ZERO, lang: lang,
          reason: 'shape known, value pending')
    end

    def self.eerror(ident, reason, at: 0)
      new(ident: ident, state: :eerror, confidence: ZERO,
          lo: at, hi: at, reason: reason)
    end

    # ── predicates ──

    def z?        = state == :z
    def cleared?  = !%i[z eerror absent].include?(state) && confidence > ZERO
    def execute?  = cleared? && confidence >= 128
    def width     = hi - lo

    def pi_status
      return :approaching_z if width > PI_WIDTH_WARN
      return :enumerate     if width > PI_WIDTH_ENUMERATE

      :acceptable
    end

    # ── propagation: Z is contagious ──

    def carry(new_ident)
      return Particle.z(new_ident, reason)              if z?
      return Particle.z(new_ident, 'upstream error')    if state == :eerror
      return Particle.z(new_ident, 'upstream absent')   if state == :absent

      Particle.new(ident: new_ident, state: state, confidence: confidence,
                   lo: lo, hi: hi, lang: lang, reason: reason,
                   error_distance: error_distance, generation: generation)
    end

    def cap(ceiling)
      return Particle.z(ident, 'capped to zero') if ceiling <= ZERO
      return self                                 if confidence <= ceiling

      # Certain demoted honestly to Confident when capped
      new_state = state == :certain ? :confident : state
      Particle.new(ident: ident, state: new_state, confidence: ceiling,
                   lo: [lo, ceiling].min, hi: [hi, ceiling].min,
                   lang: lang, reason: reason, generation: generation)
    end

    # ── the line format Layer 0 reads ──

    def serialize
      [STATES.index(state), 0, LANGS.index(lang), confidence, lo, hi,
       error_distance, generation, -1, (Time.now.to_f * 1000).to_i,
       ident, reason].join('|')
    end

    def self.deserialize(line)
      f = line.split('|', 12)
      return z('malformed', 'malformed particle line') if f.size < 12

      new(ident: f[10], state: STATES[f[0].to_i], lang: LANGS[f[2].to_i],
          confidence: f[3].to_i, lo: f[4].to_i, hi: f[5].to_i,
          error_distance: f[6].to_i, generation: f[7].to_i, reason: f[11])
    end

    def to_s = "E<#{state}>(#{ident} @ #{confidence}/256 · #{lang})"
    def inspect = to_s
  end

  # ─────────────────────────────────────────────
  # Expect — the gate. Nothing executes past a failed Expect.
  # ─────────────────────────────────────────────

  class ExpectFailure < StandardError; end

  class Gate
    def initialize(particle, min_confidence: nil, not_z: false,
                   pi_acceptable: false, cleared: false)
      @p             = particle
      @min           = min_confidence
      @not_z         = not_z
      @pi_acceptable = pi_acceptable
      @cleared       = cleared
      @failures      = []
      evaluate
    end

    attr_reader :failures

    def pass? = @failures.empty?

    def or_z
      pass? ? @p : Particle.z(@p.ident, @failures.join('; '))
    end

    def or_throw
      raise ExpectFailure, "#{@p.ident}: #{@failures.join('; ')}" unless pass?

      @p
    end

    def or_archive(archive)
      unless pass?
        archive << Particle.eerror(@p.ident, @failures.join('; '),
                                   at: @p.confidence)
      end
      pass? ? @p : Particle.z(@p.ident, @failures.join('; '))
    end

    private

    def evaluate
      @failures << 'is Z' if @not_z && @p.z?
      @failures << 'not cleared' if @cleared && !@p.cleared?
      if @min && @p.confidence < @min
        @failures << "confidence #{@p.confidence} below #{@min}"
      end
      if @pi_acceptable && @p.pi_status != :acceptable
        @failures << "range #{@p.pi_status} (width #{@p.width})"
      end
    end
  end

  # ─────────────────────────────────────────────
  # Emulate — borrow a working neighbour's pattern
  # ─────────────────────────────────────────────

  def self.emulate(broken, working, distance)
    if distance > EMULATE_CEILING
      return Particle.z(broken.ident,
                        "error distance #{distance} exceeds emulate " \
                        "ceiling #{EMULATE_CEILING}")
    end
    unless working.cleared?
      return Particle.z(broken.ident, 'no cleared neighbour to emulate')
    end

    borrowed = [working.confidence - (30 * distance), 1].max
    Particle.new(ident: broken.ident, state: :emulating,
                 confidence: borrowed, lang: broken.lang,
                 error_distance: distance,
                 reason: "emulating #{working.ident} at distance #{distance}")
  end

  # ─────────────────────────────────────────────
  # Evolve — the three-point force loop
  #
  # Action = Reaction / Force. A construct that survives three aligned
  # applications has earned the right to advance its own state.
  # Downward evolution is legitimate: learning you were overconfident
  # is learning.
  # ─────────────────────────────────────────────

  class ForceLoop
    def initialize(ident)
      @ident  = ident
      @points = []
    end

    attr_reader :points

    def <<(particle)
      @points << particle
      @points.shift while @points.size > 3
      self
    end

    def closed? = @points.size == 3

    def evolve
      return nil unless closed?

      mean = @points.sum(&:confidence) / 3
      spread = @points.map(&:confidence).max - @points.map(&:confidence).min

      # Aligned means the three points agree within the pi-squared band.
      return nil if spread > PI_WIDTH_ENUMERATE

      generation = @points.map(&:generation).max + 1
      Particle.new(ident: @ident, state: :evolved, confidence: mean,
                   lang: @points.last.lang, generation: generation,
                   reason: "evolved from 3 aligned points, spread #{spread}")
    end
  end

  # ─────────────────────────────────────────────
  # phi equalizer, applied at the end of Execute
  # ─────────────────────────────────────────────

  def self.phi_equalize(particles)
    return { balanced: [], flagged: [] } if particles.empty?

    mean = particles.sum(&:confidence) / particles.size
    hi_bound = (mean * PHI).to_i
    lo_bound = (mean / PHI).to_i

    particles.partition { |p| p.confidence.between?(lo_bound, hi_bound) }
             .then { |bal, flag| { balanced: bal, flagged: flag } }
  end

  # ─────────────────────────────────────────────
  # The DSL — Examine, Evaluate, Execute
  # ─────────────────────────────────────────────

  class Examination
    attr_reader :name, :particles, :archive, :loops

    def initialize(name)
      @name      = name
      @particles = {}
      @archive   = []
      @loops     = Hash.new { |h, k| h[k] = ForceLoop.new(k) }
    end

    # ── the eight constructs, as syntax ──

    def z(ident, reason = 'unverified')
      @particles[ident] = Particle.z(ident, reason)
    end

    def express(ident, lang: :ever)
      @particles[ident] = Particle.expression(ident, lang: lang)
    end

    def confident(ident, degree, lang: :ever)
      @particles[ident] = Particle.confident(ident, degree, lang: lang)
    end

    def certain(ident, lang: :ever)
      @particles[ident] = Particle.certain(ident, lang: lang)
    end

    def equivalence(ident, range, lang: :ever)
      @particles[ident] = Particle.equivalence(ident, range, lang: lang)
    end

    def expect(ident, **opts)
      p = @particles[ident] or return Particle.z(ident, 'never declared')
      gate = Gate.new(p, **opts.slice(:min_confidence, :not_z,
                                      :pi_acceptable, :cleared))
      @particles[ident] =
        if opts[:or_throw] then gate.or_throw
        elsif opts[:or_archive] then gate.or_archive(@archive)
        else gate.or_z
        end
    end

    def example(ident, cases)
      # Examples are evidence. Each passing case earns confidence,
      # each failing case spends it.
      passing = cases.count { |c| c }
      degree  = ((passing.to_f / cases.size) * (CERTAIN - 1)).to_i
      @particles[ident] = Particle.confident(ident, degree)
    end

    def enumerate(ident, values)
      # Enumerate collapses a too-wide Equivalence into named points.
      values.each_with_index do |v, i|
        @particles["#{ident}[#{i}]"] = Particle.confident("#{ident}[#{i}]", v)
      end
      @particles[ident]
    end

    def estimate(ident, range)
      # Estimate is the inverse: named points widen back into a range.
      equivalence(ident, range)
    end

    def emulate(ident, from:, distance:)
      broken  = @particles[ident] || Particle.z(ident, 'undeclared')
      working = @particles[from]  || Particle.z(from, 'undeclared')
      @particles[ident] = Ever.emulate(broken, working, distance)
    end

    def evolve(ident)
      p = @particles[ident] or return nil
      @loops[ident] << p
      evolved = @loops[ident].evolve
      @particles[ident] = evolved if evolved
      evolved
    end

    # ── interoperability ──

    def assimilate(ident, to:)
      source = @particles[ident] || Particle.z(ident, 'undeclared')
      @particles[ident] = Particle.new(
        ident: source.ident, state: source.state,
        confidence: source.confidence, lo: source.lo, hi: source.hi,
        lang: to, reason: "Ruby DSL assimilated #{source.lang} to #{to}"
      )
    end

    def serialize(ident)
      (@particles[ident] || Particle.z(ident, 'undeclared')).serialize
    end

    def import(line, ident: nil)
      particle = Particle.deserialize(line)
      @particles[ident || particle.ident] = particle
    end


    def execute
      cleared = @particles.values.select(&:cleared?)
      blocked = @particles.values.reject(&:cleared?)
      @archive.concat(blocked.reject { |p| p.state == :expression })

      Result.new(name: @name,
                 cleared: cleared,
                 blocked: blocked,
                 equalized: Ever.phi_equalize(cleared),
                 archive: @archive)
    end
  end

  class Result
    attr_reader :name, :cleared, :blocked, :equalized, :archive

    def initialize(name:, cleared:, blocked:, equalized:, archive:)
      @name      = name
      @cleared   = cleared
      @blocked   = blocked
      @equalized = equalized
      @archive   = archive
    end

    def executable? = blocked.empty? && cleared.all?(&:execute?)

    def report
      out = []
      out << "\nExamination: #{name}"
      out << ('-' * 52)
      out << "  cleared : #{cleared.size}"
      cleared.each { |p| out << "      #{p}" }
      out << "  blocked : #{blocked.size}"
      blocked.each { |p| out << "      #{p}  <- #{p.reason}" }
      out << "  flagged by phi : #{equalized[:flagged].size}"
      equalized[:flagged].each { |p| out << "      #{p}" }
      out << "  archived : #{archive.size}"
      out << ''
      out << (executable? ? '  CLEARED FOR EXECUTION' : '  BLOCKED')
      out.join("\n")
    end
  end

  def self.examine(name, &block)
    ex = Examination.new(name)
    ex.instance_eval(&block)
    ex
  end
end

# ─────────────────────────────────────────────
# Demonstration
# ─────────────────────────────────────────────

if __FILE__ == $PROGRAM_NAME
  puts "\n=== Ever Layer 3 (Ruby) — the DSL ===\n"

  exam = Ever.examine('invoice_scan') do
    z           :ocr_text, 'OCR not yet run'
    confident   :parsed_amount, 180, lang: :python
    confident   :working_parse, 200, lang: :c
    confident   :broken_parse,   40, lang: :c
    equivalence :severity, 100..115, lang: :ruby
    certain     :schema_version, lang: :sql

    expect :parsed_amount, min_confidence: 128, not_z: true
    expect :severity,      pi_acceptable: true
    expect :ocr_text,      not_z: true, or_archive: true

    emulate :broken_parse, from: :working_parse, distance: 1
  end

  result = exam.execute
  puts result.report

  puts "\nForce loop (Evolve)"
  loop_exam = Ever.examine('parser_evolution') do
    confident :parser, 170
    evolve    :parser
    confident :parser, 175
    evolve    :parser
    confident :parser, 180
  end
  evolved = loop_exam.evolve(:parser)
  puts evolved ? "  evolved -> #{evolved}" : '  loop not yet closed'
  puts "  reason  : #{evolved&.reason}"

  puts "\nSerialization to Layer 0 format"
  p1 = Ever::Particle.confident('parsed_amount', 180, lang: :python)
  line = p1.serialize
  puts "  #{line}"
  back = Ever::Particle.deserialize(line)
  puts "  round trip -> #{back}"
  raise 'round trip lost the particle' unless back.to_s == p1.to_s && back.reason == p1.reason
  piped = Ever::Particle.z('piped', 'reason a|b')
  raise 'a reason containing | was cut' unless Ever::Particle.deserialize(piped.serialize).reason == 'reason a|b'
  puts
end
