// Brevitas — three signature animations
// A: Compression Sequence · B: Pipeline Reduction · C: Thesis Sequence

const { useState: useStateA, useEffect: useEffectA, useRef: useRefA, useCallback: useCallbackA } = React;

// ============================================================
// A — Compression Sequence
// ============================================================
// Natural paragraph → compressed form. Kept words highlight; dropped words ghost out.

const COMPRESSION_WORDS = [
  // [word, kept]
  ['The', false], ['architecture', true], ['should', false], ['follow', false], ['a', false],
  ['three-layer', true], ['pattern', true], ['comprising', false], ['a', false],
  ['presentation', true], ['layer,', false], ['a', false], ['business', true], ['logic', true],
  ['layer,', false], ['and', false], ['a', false], ['persistence', true], ['layer.', false],
  ['The', false], ['presentation', true], ['layer', false], ['handles', false], ['user-facing', true],
  ['concerns', false], ['and', false], ['renders', false], ['the', false], ['UI', true],
  ['based', false], ['on', false], ['props', false], ['passed', false], ['down', false],
  ['from', false], ['the', false], ['business', true], ['logic', true], ['layer.', false],
  ['The', false], ['business', false], ['logic', false], ['layer', false], ['encapsulates', false],
  ['domain', true], ['operations', true], ['and', false], ['should', false], ['be', false],
  ['written', false], ['in', false], ['pure', true], ['functions', true], ['where', false],
  ['possible.', false], ['The', false], ['persistence', true], ['layer', false],
  ['mediates', false], ['reads', true], ['and', false], ['writes', true], ['against', false],
  ['the', false], ['database.', true],
];

function CompressionSequence() {
  const [phase, setPhase] = useStateA('idle'); // idle, typing, hold, dropout, done
  const [visibleCount, setVisibleCount] = useStateA(0);
  const [tokens, setTokens] = useStateA(1000);
  const [key, setKey] = useStateA(0);
  const [ref, inView] = useInView({ threshold: 0.35 });
  const reduced = useReducedMotion();

  useEffectA(() => {
    if (!inView) return;
    if (reduced) { setPhase('done'); setVisibleCount(COMPRESSION_WORDS.length); setTokens(300); return; }
    let timers = [];
    setPhase('typing');
    // Type all words in quickly (800ms total)
    const total = COMPRESSION_WORDS.length;
    for (let i = 1; i <= total; i++) {
      timers.push(setTimeout(() => setVisibleCount(i), (i / total) * 900 + 100));
    }
    timers.push(setTimeout(() => setPhase('hold'), 1200));
    timers.push(setTimeout(() => setPhase('dropout'), 2000));
    // Animate token counter down
    timers.push(setTimeout(() => {
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 1400);
        const eased = p < 0.5 ? 2*p*p : 1 - Math.pow(-2*p+2,2)/2;
        setTokens(Math.round(1000 - 700 * eased));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, 2000));
    timers.push(setTimeout(() => setPhase('done'), 3500));
    return () => timers.forEach(clearTimeout);
  }, [inView, key, reduced]);

  const replay = () => { setVisibleCount(0); setTokens(1000); setPhase('idle'); setKey(k => k+1); };

  const isAfter = phase === 'dropout' || phase === 'done';

  return (
    <div ref={ref} className="card" style={{ padding: 0, overflow: 'hidden', background: 'var(--ink-2)' }}>
      <div style={{
        padding: '18px 24px',
        borderBottom: '1px solid var(--line)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        gap: 16, flexWrap: 'wrap',
      }}>
        <div className="t-overline" style={{ color: 'var(--stone-2)' }}>
          {isAfter ? 'COMPRESSED' : 'AGENT 1 OUTPUT'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="t-mono tabular" style={{ color: isAfter ? 'var(--signal)' : 'var(--oxblood)' }}>
            {tokens.toLocaleString()} tokens
          </div>
          {isAfter && (
            <div className="t-mono" style={{
              color: 'var(--signal)',
              padding: '2px 8px',
              border: '1px solid var(--signal)',
              borderRadius: 2,
              fontSize: 11,
            }}>
              −70%
            </div>
          )}
        </div>
      </div>
      <div style={{
        padding: '28px 28px 24px',
        minHeight: 260,
        fontFamily: 'JetBrains Mono, ui-monospace, monospace',
        fontSize: 14,
        lineHeight: 1.85,
        color: 'var(--bone-dim)',
      }}>
        {COMPRESSION_WORDS.map(([w, kept], i) => {
          const visible = i < visibleCount;
          const dropout = isAfter && !kept;
          const highlight = isAfter && kept;
          return (
            <span
              key={i}
              style={{
                opacity: visible ? (dropout ? 0.12 : 1) : 0,
                color: highlight ? 'var(--signal)' : (dropout ? 'var(--stone)' : 'var(--bone-dim)'),
                transition: `opacity 280ms var(--ease-out-soft) ${i * 18}ms, color 300ms var(--ease-out-soft) ${i * 18}ms`,
                textDecoration: dropout ? 'line-through' : 'none',
                textDecorationColor: 'var(--stone)',
                textDecorationThickness: '1px',
                marginRight: 6,
                display: 'inline-block',
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      <div style={{
        padding: '12px 24px',
        borderTop: '1px solid var(--line)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        background: 'rgba(0,0,0,0.15)',
      }}>
        <div className="t-mono" style={{ color: 'var(--stone)', fontSize: 12 }}>
          inter-agent.compress()
        </div>
        <button onClick={replay} className="t-mono" style={{
          background: 'transparent', border: '1px solid var(--line)',
          color: 'var(--fg-dim)', padding: '4px 10px', borderRadius: 2,
          cursor: 'pointer', fontSize: 12,
        }}>
          Replay ↻
        </button>
      </div>
    </div>
  );
}

// ============================================================
// B — Pipeline Reduction  (THE hero animation)
// ============================================================

function PipelineReduction({ compact = false, loop = true }) {
  const [ref, inView] = useInView({ threshold: 0.25 });
  const reduced = useReducedMotion();
  const [stage, setStage] = useStateA(0);
  // stages: 0 idle, 1 A1 active, 2 after A1 arrows, 3 A2 active + arrows, 4 A3 active, 5 totals, 6 resolution
  const [baselineTokens, setBaselineTokens] = useStateA(0);
  const [optimizedTokens, setOptimizedTokens] = useStateA(0);
  const [resolveIn, setResolveIn] = useStateA(false);
  const [statA, setStatA] = useStateA(0);
  const [statB, setStatB] = useStateA(0);
  const [statC, setStatC] = useStateA(0);
  const [cycle, setCycle] = useStateA(0);

  useEffectA(() => {
    if (!inView) return;
    if (reduced) {
      setStage(5); setBaselineTokens(2924); setOptimizedTokens(1188);
      setResolveIn(true); setStatA(59.4); setStatB(46.9); setStatC(99);
      return;
    }
    let timers = [];
    setStage(0); setBaselineTokens(0); setOptimizedTokens(0); setResolveIn(false);
    setStatA(0); setStatB(0); setStatC(0);
    timers.push(setTimeout(() => setStage(1), 500));
    timers.push(setTimeout(() => {
      setStage(2);
      // tick tokens
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 900);
        setBaselineTokens(Math.round(1000 * p));
        setOptimizedTokens(Math.round(300 * p));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, 900));
    timers.push(setTimeout(() => {
      setStage(3);
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 900);
        setBaselineTokens(Math.round(1000 + 500 * p));
        setOptimizedTokens(Math.round(300 + 450 * p));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, 1800));
    timers.push(setTimeout(() => {
      setStage(4);
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 900);
        setBaselineTokens(Math.round(1500 + 1424 * p));
        setOptimizedTokens(Math.round(750 + 438 * p));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, 2700));
    timers.push(setTimeout(() => setStage(5), 3600));
    timers.push(setTimeout(() => {
      setResolveIn(true);
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 900);
        const e = p < 0.5 ? 2*p*p : 1 - Math.pow(-2*p+2,2)/2;
        setStatA(+(59.4 * e).toFixed(1));
        setStatB(+(46.9 * e).toFixed(1));
        setStatC(Math.round(99 * e));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, 4400));
    if (loop) {
      timers.push(setTimeout(() => setCycle(c => c+1), 12000));
    }
    return () => timers.forEach(clearTimeout);
  }, [inView, cycle, reduced, loop]);

  const stageActive = (n) => stage >= n;

  const AgentBox = ({ label, sublabel, active, side }) => (
    <div style={{
      border: `1.5px solid ${active ? 'var(--fg)' : 'var(--line)'}`,
      background: active ? 'var(--ink-3)' : 'var(--ink-2)',
      padding: '14px 18px',
      minWidth: 160,
      textAlign: 'center',
      borderRadius: 2,
      transition: 'border-color 400ms var(--ease-out-standard), background 400ms var(--ease-out-standard)',
    }}>
      <div className="t-mono" style={{ color: 'var(--stone-2)', fontSize: 11 }}>{sublabel}</div>
      <div className="serif" style={{ fontSize: 18, fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--fg)', marginTop: 4 }}>{label}</div>
    </div>
  );

  const BrevitasBox = ({ visible, active }) => (
    <div style={{
      border: '1.5px double var(--signal)',
      background: 'var(--ink-2)',
      padding: '10px 16px',
      minWidth: 180,
      textAlign: 'center',
      borderRadius: 2,
      opacity: visible ? 1 : 0,
      boxShadow: active ? '0 0 24px var(--signal-glow)' : 'none',
      transition: 'opacity 400ms, box-shadow 400ms',
    }}>
      <div className="t-mono" style={{ color: 'var(--signal)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase' }}>
        BREVITAS LAYER
      </div>
      <div className="t-mono" style={{ color: 'var(--stone-2)', fontSize: 10, marginTop: 2 }}>
        compress · reference · delta
      </div>
    </div>
  );

  // Arrow: side 'left' is oxblood/thick, 'right' is signal/thin
  const Arrow = ({ side, thick = false, visible, label }) => {
    const color = side === 'left' ? 'var(--oxblood)' : 'var(--signal)';
    const width = side === 'left' ? (thick ? 6 : 3) : 2;
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
        opacity: visible ? 1 : 0,
        transition: 'opacity 300ms, transform 600ms var(--ease-out-soft)',
      }}>
        <div style={{
          width,
          height: 36,
          background: color,
          opacity: side === 'left' ? 0.55 : 0.85,
          transition: 'width 600ms var(--ease-out-soft)',
        }}/>
        <div style={{ color, opacity: 0.85, fontSize: 10, lineHeight: 1 }}>▼</div>
        {label && (
          <div className="t-mono tabular" style={{ color: side === 'left' ? 'var(--oxblood)' : 'var(--signal)', fontSize: 11 }}>
            {label}
          </div>
        )}
      </div>
    );
  };

  return (
    <div ref={ref} style={{
      border: '1px solid var(--line)',
      background: 'var(--ink-2)',
      borderRadius: 4,
      padding: compact ? 24 : 'clamp(28px, 4vw, 56px)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Main split */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1px 1fr',
        gap: 0,
        opacity: resolveIn ? 0.2 : 1,
        transition: 'opacity 800ms var(--ease-out-soft)',
      }}>
        {/* LEFT: baseline */}
        <div style={{ padding: '0 clamp(12px, 2vw, 32px)' }}>
          <div className="t-overline" style={{ color: 'var(--stone-2)', marginBottom: 6 }}>BASELINE PIPELINE</div>
          <div className="t-mono" style={{ color: 'var(--stone)', marginBottom: 28, fontSize: 12 }}>how every team builds this today</div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
            <AgentBox label="Architect" sublabel="AGENT 1 · DeepSeek" active={stage === 1 || (stage >= 1 && stage <= 2)} />
            <Arrow side="left" thick={stage >= 2} visible={stage >= 2} label={stage >= 2 ? '1,000 tok' : ''} />
            <AgentBox label="Builder" sublabel="AGENT 2 · Groq" active={stage === 3} />
            <Arrow side="left" thick={stage >= 3} visible={stage >= 3} label={stage >= 3 ? '1,500 tok' : ''} />
            <AgentBox label="Reviewer" sublabel="AGENT 3 · OpenAI" active={stage === 4} />
          </div>
          <div style={{ marginTop: 32, textAlign: 'center' }}>
            <div className="t-mono" style={{ color: 'var(--stone-2)', fontSize: 11 }}>CUMULATIVE</div>
            <div className="serif tabular" style={{ fontSize: 36, fontWeight: 300, color: 'var(--oxblood)', letterSpacing: '-0.02em', marginTop: 4 }}>
              ▶ {baselineTokens.toLocaleString()} <span style={{ fontSize: 16, color: 'var(--stone-2)' }}>tokens</span>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div style={{ background: 'var(--line)', width: 1, height: '100%' }} />

        {/* RIGHT: with brevitas */}
        <div style={{ padding: '0 clamp(12px, 2vw, 32px)' }}>
          <div className="t-overline" style={{ color: 'var(--signal)', marginBottom: 6 }}>
            <span className="overline-dot" style={{ background: 'var(--signal)' }}/> WITH BREVITAS
          </div>
          <div className="t-mono" style={{ color: 'var(--stone)', marginBottom: 28, fontSize: 12 }}>the same task, optimized</div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
            <AgentBox label="Architect" sublabel="AGENT 1 · DeepSeek" active={stage === 1} />
            <Arrow side="right" visible={stage >= 2} label={stage >= 2 ? '300 tok · compressed' : ''} />
            <BrevitasBox visible={stage >= 2} active={stage === 2} />
            <Arrow side="right" visible={stage >= 2} />
            <AgentBox label="Builder" sublabel="AGENT 2 · Groq" active={stage === 3} />
            <Arrow side="right" visible={stage >= 3} label={stage >= 3 ? '450 tok · delta' : ''} />
            <BrevitasBox visible={stage >= 3} active={stage === 3} />
            <Arrow side="right" visible={stage >= 3} />
            <AgentBox label="Reviewer" sublabel="AGENT 3 · OpenAI" active={stage === 4} />
          </div>
          <div style={{ marginTop: 32, textAlign: 'center' }}>
            <div className="t-mono" style={{ color: 'var(--stone-2)', fontSize: 11 }}>CUMULATIVE</div>
            <div className="serif tabular" style={{ fontSize: 36, fontWeight: 300, color: 'var(--signal)', letterSpacing: '-0.02em', marginTop: 4 }}>
              ▶ {optimizedTokens.toLocaleString()} <span style={{ fontSize: 16, color: 'var(--stone-2)' }}>tokens</span>
            </div>
          </div>
        </div>
      </div>

      {/* Resolution frame */}
      {resolveIn && !compact && (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          background: 'rgba(15,20,16,0.86)',
          backdropFilter: 'blur(6px)',
          padding: 24,
          animation: 'fadeIn 700ms var(--ease-out-soft)',
        }}>
          <div style={{ display: 'flex', gap: 'clamp(24px, 6vw, 80px)', alignItems: 'baseline', flexWrap: 'wrap', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div className="serif tabular" style={{ fontSize: 'clamp(52px, 7vw, 88px)', fontWeight: 300, color: 'var(--signal)', letterSpacing: '-0.02em', lineHeight: 1 }}>
                –{statA.toFixed(1)}%
              </div>
              <div className="t-mono" style={{ color: 'var(--stone-2)', marginTop: 8 }}>tokens saved</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="serif tabular" style={{ fontSize: 'clamp(52px, 7vw, 88px)', fontWeight: 300, color: 'var(--signal)', letterSpacing: '-0.02em', lineHeight: 1 }}>
                –{statB.toFixed(1)}%
              </div>
              <div className="t-mono" style={{ color: 'var(--stone-2)', marginTop: 8 }}>cost saved</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="serif tabular" style={{ fontSize: 'clamp(52px, 7vw, 88px)', fontWeight: 300, color: 'var(--fg)', letterSpacing: '-0.02em', lineHeight: 1 }}>
                {statC}%
              </div>
              <div className="t-mono" style={{ color: 'var(--stone-2)', marginTop: 8 }}>quality parity</div>
            </div>
          </div>
          <div className="t-mono" style={{ color: 'var(--stone)', marginTop: 32, textAlign: 'center' }}>
            AgentBench task · real API calls · real token counts
          </div>
        </div>
      )}

      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}

// ============================================================
// C — Thesis Sequence
// ============================================================

function ThesisSequence() {
  const [ref, inView] = useInView({ threshold: 0.3 });
  const reduced = useReducedMotion();
  const [s, setS] = useStateA(0); // 0..5

  useEffectA(() => {
    if (!inView) return;
    if (reduced) { setS(5); return; }
    const ts = [
      setTimeout(() => setS(1), 500),
      setTimeout(() => setS(2), 1400),
      setTimeout(() => setS(3), 2500),
      setTimeout(() => setS(4), 3600),
      setTimeout(() => setS(5), 4200),
    ];
    return () => ts.forEach(clearTimeout);
  }, [inView, reduced]);

  const Line = ({ visible, children, caption, captionVisible, emphasis = false }) => (
    <div style={{ marginBottom: 'clamp(40px, 6vh, 72px)' }}>
      <div
        className={emphasis ? 't-display' : 't-h2'}
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(16px)',
          transition: 'opacity 700ms var(--ease-out-soft), transform 700ms var(--ease-out-soft)',
          color: emphasis ? 'var(--fg)' : 'var(--bone-dim)',
          textWrap: 'balance',
        }}
      >
        {children}
      </div>
      {caption && (
        <div
          className="t-mono"
          style={{
            color: 'var(--stone)',
            marginTop: 14,
            opacity: captionVisible ? 1 : 0,
            transition: 'opacity 400ms 200ms var(--ease-out-soft)',
          }}
        >
          {caption}
        </div>
      )}
    </div>
  );

  return (
    <div ref={ref}>
      <div style={{
        opacity: s >= 1 ? 1 : 0,
        transition: 'opacity 400ms',
        marginBottom: 'clamp(48px, 7vh, 80px)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
      }}>
        <div className="t-overline">THE STATE OF THE STACK — 2026</div>
        <hr className="rule" style={{ width: 64, marginTop: 18, borderColor: 'var(--line)' }}/>
      </div>

      <Line visible={s >= 1} captionVisible={s >= 1} caption="// gpt-4.turbo · one model · one call">
        The 2023 default was a single prompt.
      </Line>

      <Line visible={s >= 2} captionVisible={s >= 2} caption="// orchestrators · 5 to 50 inter-agent calls per task">
        The 2026 default is a pipeline of agents.
      </Line>

      <div style={{ marginBottom: 'clamp(40px, 6vh, 72px)' }}>
        <div
          className="t-mono"
          style={{
            color: 'var(--stone-2)',
            letterSpacing: '0.05em',
            opacity: s >= 3 ? 1 : 0,
            transition: 'opacity 400ms',
            marginBottom: 22,
            fontSize: 13,
          }}
        >
          ────────── and no one optimized ──────────
        </div>
        <div
          className="t-h2"
          style={{
            opacity: s >= 4 ? 1 : 0,
            transform: s >= 4 ? 'translateY(0)' : 'translateY(16px)',
            transition: 'opacity 900ms var(--ease-out-soft), transform 900ms var(--ease-out-soft)',
            color: 'var(--fg)',
            textWrap: 'balance',
          }}
        >
          what flows <em style={{ fontStyle: 'italic', color: 'var(--bronze)' }}>between</em> them.
        </div>
        <div
          className="t-mono"
          style={{
            color: 'var(--stone)',
            marginTop: 16,
            opacity: s >= 4 ? 1 : 0,
            transition: 'opacity 400ms 400ms',
          }}
        >
          // until now
        </div>
      </div>

      <div style={{
        opacity: s >= 5 ? 1 : 0,
        transition: 'opacity 500ms',
        marginTop: 24,
      }}>
        <a href="/how-it-works" className="btn btn-secondary">
          See how <span className="arrow">→</span>
        </a>
      </div>
    </div>
  );
}

Object.assign(window, {
  CompressionSequence, PipelineReduction, ThesisSequence,
});
