// Brevitas Systems — shared UI components
// Exposes: Nav, Footer, Overline, Button, StatCard, TechniqueCard,
// BenchmarkBadge, CodeBlock, SectionShell, WaitlistInput, LogoMark, ArrowRight

const { useState, useEffect, useRef, useCallback } = React;

// --- utility hooks ---
function useInView(opts = { threshold: 0.2 }) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setInView(true);
        io.disconnect();
      }
    }, opts);
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  return [ref, inView];
}

function useReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setR(mq.matches);
    const h = (e) => setR(e.matches);
    mq.addEventListener('change', h);
    return () => mq.removeEventListener('change', h);
  }, []);
  return r;
}

function useCountUp(target, { duration = 800, start = 0, trigger = true } = {}) {
  const [val, setVal] = useState(start);
  useEffect(() => {
    if (!trigger) return;
    let raf;
    const t0 = performance.now();
    const ease = (t) => t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t+2, 2)/2;
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      setVal(start + (target - start) * ease(p));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, trigger]);
  return val;
}

// --- atoms ---
function LogoMark({ size = 28, color }) {
  const s = size;
  const style = { color: color || 'currentColor' };
  return (
    <svg width={s} height={s} viewBox="0 0 28 28" style={style} aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.5"/>
      <line x1="14" y1="4" x2="14" y2="24" stroke="currentColor" strokeWidth="1.5"/>
      <line x1="4" y1="14" x2="24" y2="14" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  );
}

function ArrowRight({ size = 14 }) {
  return <span className="arrow" aria-hidden="true">→</span>;
}

function Overline({ children, dot = false, className = '' }) {
  return (
    <div className={`overline t-overline ${className}`}>
      {dot && <span className="overline-dot" />}
      <span>{children}</span>
    </div>
  );
}

function Button({ variant = 'primary', href, onClick, children, arrow = true, className = '' }) {
  const cls = `btn btn-${variant} ${className}`;
  const content = (
    <>
      <span>{children}</span>
      {arrow && <span className="arrow" aria-hidden="true">→</span>}
    </>
  );
  if (href) return <a href={href} className={cls} onClick={onClick}>{content}</a>;
  return <button className={cls} onClick={onClick} type="button">{content}</button>;
}

function SectionShell({ overline, overlineDot, rule = false, children, className = '', id, tight = false }) {
  return (
    <section id={id} className={`section ${tight ? 'section--tight' : ''} ${className}`}>
      <div className="container">
        {rule && <hr className="rule" style={{ marginBottom: 48 }} />}
        {overline && <Overline dot={overlineDot}>{overline}</Overline>}
        <div style={{ marginTop: overline ? 32 : 0 }}>
          {children}
        </div>
      </div>
    </section>
  );
}

function StatCard({ value, label, sub, variant = 'default', delta, onInView = true }) {
  const [ref, inView] = useInView();
  const numericTarget = typeof value === 'number' ? value : parseFloat(String(value).replace(/[^-0-9.]/g, ''));
  const suffix = typeof value === 'string' ? (value.match(/%$/) ? '%' : '') : '%';
  const prefix = typeof value === 'string' && value.startsWith('–') ? '–' : '';
  const count = useCountUp(numericTarget, { duration: 900, trigger: inView });
  const display = isNaN(numericTarget) ? value : `${prefix}${count.toFixed(1).replace(/\.0$/, '')}${suffix}`;

  if (variant === 'inline') {
    return (
      <div ref={ref} className="stat-inline" style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 140 }}>
        <div className="serif tabular" style={{ fontSize: 'clamp(32px, 3.6vw, 44px)', fontWeight: 300, lineHeight: 1, color: 'var(--fg)', letterSpacing: '-0.01em' }}>
          {display}
        </div>
        <div className="t-mono" style={{ color: 'var(--stone-2)', marginTop: 6 }}>{label}</div>
      </div>
    );
  }
  const isEmph = variant === 'emphasis';
  return (
    <div ref={ref} className="card" style={{ padding: isEmph ? '40px 32px' : 28 }}>
      <div className="serif tabular" style={{
        fontSize: isEmph ? 'clamp(64px, 7vw, 96px)' : 'clamp(40px, 4.5vw, 56px)',
        fontWeight: 300,
        lineHeight: 1,
        letterSpacing: '-0.02em',
        color: 'var(--fg)',
      }}>
        {display}
      </div>
      <hr className="rule" style={{ margin: '20px 0 16px', width: 40, borderColor: 'var(--line)' }} />
      <div className="t-mono" style={{ color: 'var(--fg-dim)' }}>{label}</div>
      {sub && <div className="t-mono" style={{ color: 'var(--stone)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function TechniqueCard({ index, title, body, demoLink }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16, minHeight: 260 }}>
      <div className="t-mono" style={{ color: 'var(--stone)' }}>{String(index).padStart(2, '0')}</div>
      <div className="serif" style={{ fontSize: 24, fontWeight: 400, lineHeight: 1.22, letterSpacing: '-0.01em' }}>
        {title}
      </div>
      <div className="t-body" style={{ color: 'var(--bone-dim)', flex: 1 }}>{body}</div>
      {demoLink && (
        <a href={demoLink} className="t-mono link" style={{ color: 'var(--bronze)', marginTop: 8 }}>
          see it →
        </a>
      )}
    </div>
  );
}

function BenchmarkBadge({ letter, name, venue }) {
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '20px 24px', minWidth: 220 }}>
      <div style={{
        width: 44, height: 44,
        border: '1.5px solid var(--stone-2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'Newsreader, serif', fontWeight: 400, fontSize: 22,
        color: 'var(--fg)',
      }}>
        {letter}
      </div>
      <div>
        <div style={{ fontWeight: 500, fontSize: 15, color: 'var(--fg)' }}>{name}</div>
        <div className="t-mono" style={{ color: 'var(--stone-2)', fontSize: 12 }}>{venue}</div>
      </div>
    </div>
  );
}

function CodeBlock({ children, copyable = false, language = 'python', filename }) {
  const [copied, setCopied] = useState(false);
  const doCopy = () => {
    try {
      const text = typeof children === 'string' ? children : (children?.props?.children ?? '');
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {}
  };
  return (
    <div style={{
      background: 'var(--ink-2)',
      border: '1px solid var(--line)',
      borderRadius: 4,
      position: 'relative',
      overflow: 'hidden',
    }}>
      {filename && (
        <div className="t-mono" style={{
          padding: '10px 20px',
          borderBottom: '1px solid var(--line)',
          color: 'var(--stone-2)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{filename}</span>
          {copyable && (
            <button onClick={doCopy} className="t-mono" style={{ background: 'transparent', border: 0, color: copied ? 'var(--signal)' : 'var(--stone-2)', cursor: 'pointer', padding: 0 }}>
              {copied ? '✓ copied' : '⧉ copy'}
            </button>
          )}
        </div>
      )}
      <pre style={{
        margin: 0,
        padding: 20,
        fontFamily: 'JetBrains Mono, ui-monospace, monospace',
        fontSize: 14,
        lineHeight: 1.6,
        color: 'var(--bone-dim)',
        overflowX: 'auto',
      }}>
        <code>{children}</code>
      </pre>
    </div>
  );
}

// Tiny syntax highlighter — minimalist 4-color theme
function syntaxPython(src) {
  const lines = src.split('\n');
  return lines.map((line, i) => {
    // split comment off
    let codePart = line, commentPart = '';
    const hashIdx = (() => {
      let inStr = null;
      for (let j = 0; j < line.length; j++) {
        const c = line[j];
        if (inStr) { if (c === inStr && line[j-1] !== '\\') inStr = null; }
        else if (c === '"' || c === "'") inStr = c;
        else if (c === '#') return j;
      }
      return -1;
    })();
    if (hashIdx >= 0) { codePart = line.slice(0, hashIdx); commentPart = line.slice(hashIdx); }

    const parts = [];
    const re = /(\s+)|("[^"]*"|'[^']*')|\b(import|from|def|return|class|if|else|for|in|as|with|pass|None|True|False|await|async)\b|(\b\d[\d_.]*\b)|([A-Za-z_][A-Za-z0-9_]*)|(.)/g;
    let m, idx = 0;
    while ((m = re.exec(codePart)) !== null) {
      if (m[1]) parts.push(<span key={idx++}>{m[1]}</span>);
      else if (m[2]) parts.push(<span key={idx++} style={{ color: 'var(--signal)' }}>{m[2]}</span>);
      else if (m[3]) parts.push(<span key={idx++} style={{ color: 'var(--bone)', fontWeight: 500 }}>{m[3]}</span>);
      else if (m[4]) parts.push(<span key={idx++} style={{ color: 'var(--stone-2)' }}>{m[4]}</span>);
      else if (m[5]) parts.push(<span key={idx++} style={{ color: 'var(--bone-dim)' }}>{m[5]}</span>);
      else if (m[6]) parts.push(<span key={idx++}>{m[6]}</span>);
    }
    if (commentPart) parts.push(<span key={'c'+i} style={{ color: 'var(--stone)' }}>{commentPart}</span>);
    return <div key={i}>{parts.length ? parts : '\u00A0'}</div>;
  });
}

function CodeBlockPy({ source, filename, copyable = true }) {
  return (
    <CodeBlock filename={filename} copyable={copyable}>
      <>{syntaxPython(source)}</>
    </CodeBlock>
  );
}

// --- Waitlist ---
function WaitlistInput({ variant = 'inline', source = 'unknown' }) {
  const [email, setEmail] = useState('');
  const [expanded, setExpanded] = useState(variant === 'full');
  const [state, setState] = useState('idle'); // idle | submitting | success | error
  const [err, setErr] = useState('');
  const [form, setForm] = useState({ name: '', company: '', role: '', building: '' });

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  const submitEmail = (e) => {
    e?.preventDefault?.();
    if (!emailValid) { setErr("Hmm, that email doesn't look right."); return; }
    setErr('');
    setExpanded(true);
  };

  const submitAll = async (e) => {
    e?.preventDefault?.();
    if (!emailValid) { setErr("Hmm, that email doesn't look right."); return; }
    if (form.name.trim().length < 2) { setErr('Need your name to say hello.'); return; }
    if (form.company.trim().length < 2) { setErr('What company is this for?'); return; }
    if (!form.role) { setErr('Pick a role so we can triage.'); return; }
    if (form.building.trim().length < 20) { setErr('A sentence or two helps us triage — what\'s the multi-agent use case?'); return; }
    setErr('');
    setState('submitting');

    try {
      // Call the backend API
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          name: form.name.trim(),
          company: form.company.trim(),
          role: form.role,
          use_case: form.building.trim(),
          source: source || 'website',
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setState('success');
      } else {
        setErr(data.error || 'Failed to join waitlist. Please try again.');
        setState('idle');
      }
    } catch (error) {
      console.error('Waitlist submission error:', error);
      setErr('Connection error. Please try again.');
      setState('idle');
    }
  };

  if (state === 'success') {
    return (
      <div style={{
        border: '1px solid var(--line)',
        padding: variant === 'full' ? '40px 32px' : '28px 24px',
        borderRadius: 4,
        background: 'var(--ink-2)',
        maxWidth: variant === 'full' ? 720 : 560,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <span style={{ color: 'var(--signal)', fontSize: 24 }}>✓</span>
          <div className="serif" style={{ fontSize: 28, fontWeight: 300, letterSpacing: '-0.01em' }}>You're on the list.</div>
        </div>
        <div className="t-body">
          We'll email at <span className="mono" style={{ color: 'var(--fg)' }}>{email.split('@')[1]}</span> when we have room to talk. In the meantime, watch for a monthly note — no more, usually less.
        </div>
      </div>
    );
  }

  if (variant === 'footer-small') {
    return (
      <form onSubmit={submitEmail} style={{ display: 'flex', gap: 6, alignItems: 'stretch' }}>
        <input
          type="email"
          className="input"
          placeholder="name@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ padding: '10px 14px', fontSize: 14 }}
        />
        <button type="submit" className="btn btn-primary" style={{ padding: '10px 16px', fontSize: 14 }}>
          Join <span className="arrow">→</span>
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={expanded ? submitAll : submitEmail} style={{ maxWidth: variant === 'full' ? 720 : 560 }}>
      {!expanded && (
        <>
          <div className="waitlist-row">
            <input
              type="email"
              className="input"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-label="Work email"
            />
            <button type="submit" className="btn btn-primary">
              Join the waitlist <span className="arrow">→</span>
            </button>
          </div>
          {err && <div className="t-small" style={{ marginTop: 10, color: 'var(--bone-dim)' }}>! {err}</div>}
        </>
      )}
      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="waitlist-row">
            <input
              type="email"
              className="input"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-label="Work email"
            />
            <span style={{
              display: 'inline-flex', alignItems: 'center', padding: '0 14px',
              border: '1px solid var(--line)', borderRadius: 2,
              color: emailValid ? 'var(--signal)' : 'var(--stone)',
            }}>{emailValid ? '✓' : ''}</span>
          </div>
          <input
            className="input"
            placeholder="Your name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="input"
            placeholder="Company"
            value={form.company}
            onChange={(e) => setForm({ ...form, company: e.target.value })}
          />
          <select
            className="input"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            style={{ color: form.role ? 'var(--fg)' : 'var(--stone)' }}
          >
            <option value="">Role</option>
            <option value="Founder / CEO">Founder / CEO</option>
            <option value="CTO / Head of Engineering">CTO / Head of Engineering</option>
            <option value="Engineering IC">Engineering IC</option>
            <option value="Product / Platform Lead">Product / Platform Lead</option>
            <option value="Investor">Investor</option>
            <option value="Researcher">Researcher</option>
            <option value="Other">Other</option>
          </select>
          <textarea
            className="input"
            placeholder={'e.g., "Three-agent research pipeline on GPT-4o and Claude 4.6 — ~10M tokens/month, cost the main constraint."'}
            value={form.building}
            onChange={(e) => setForm({ ...form, building: e.target.value })}
            rows={3}
            style={{ resize: 'vertical', minHeight: 90, fontFamily: 'inherit' }}
            maxLength={300}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, gap: 16 }}>
            <div className="t-mono" style={{ color: 'var(--stone)' }}>
              {form.building.length}/300
            </div>
            <button type="submit" className="btn btn-primary" disabled={state === 'submitting'}>
              {state === 'submitting' ? 'Joining…' : 'Confirm and join'} <span className="arrow">→</span>
            </button>
          </div>
          {err && <div className="t-small" style={{ color: 'var(--bone-dim)' }}>! {err}</div>}
        </div>
      )}
    </form>
  );
}

// --- Theme Toggle ---
function ThemeToggle() {
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    // Check localStorage and system preference on mount
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');

    setTheme(initialTheme);
    document.documentElement.setAttribute('data-theme', initialTheme);
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  return (
    <button
      onClick={toggleTheme}
      className="theme-toggle"
      aria-label="Toggle theme"
      style={{
        background: 'transparent',
        border: '1px solid var(--line)',
        borderRadius: '8px',
        padding: '8px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '36px',
        height: '36px',
        transition: 'all 300ms cubic-bezier(0.16, 1, 0.3, 1)',
        color: 'var(--stone-2)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--bronze)';
        e.currentTarget.style.color = 'var(--bronze)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--line)';
        e.currentTarget.style.color = 'var(--stone-2)';
      }}
    >
      {theme === 'dark' ? (
        // Sun icon for light mode
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
      ) : (
        // Moon icon for dark mode
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      )}
    </button>
  );
}

// --- Nav / Footer ---
function Nav({ current }) {
  const [scrolled, setScrolled] = useState(false);
  const [sheet, setSheet] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 20);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);

  const links = [
    { href: '/product', label: 'Product', k: 'product' },
    { href: '/how-it-works', label: 'How it works', k: 'how' },
    { href: '/benchmarks', label: 'Benchmarks', k: 'benchmarks' },
    { href: '/docs', label: 'Docs', k: 'docs' },
    { href: '/blog', label: 'Blog', k: 'blog' },
  ];
  return (
    <>
      <nav className={`nav ${scrolled ? 'scrolled' : ''}`} aria-label="Primary">
        <div className="nav-inner">
          <a href="/" style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--fg)' }}>
            <span className="serif" style={{ fontSize: 18, letterSpacing: '-0.01em' }}>Brevitas</span>
          </a>
          <div className="nav-links desktop">
            {links.map(l => (
              <a key={l.k} href={l.href} className={`nav-link ${current === l.k ? 'active' : ''}`}>{l.label}</a>
            ))}
          </div>
          <ThemeToggle />
          <Button variant="primary" href="/waitlist" className="nav-cta">Join waitlist</Button>
          <button className="nav-hamburger" onClick={() => setSheet(true)} aria-label="Menu">
            <span/><span/><span/>
          </button>
        </div>
      </nav>
      {sheet && (
        <div className="nav-sheet open" role="dialog" aria-modal="true">
          <button className="nav-sheet-close" onClick={() => setSheet(false)} aria-label="Close">×</button>
          <div className="nav-sheet-links">
            {links.map(l => <a key={l.k} href={l.href}>{l.label}</a>)}
            <a href="/waitlist" style={{ color: 'var(--bronze)' }}>Join waitlist →</a>
          </div>
        </div>
      )}
    </>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <span className="serif" style={{ fontSize: 22, fontWeight: 400, letterSpacing: '-0.01em' }}>Brevitas Systems</span>
            </div>
            <div className="t-body" style={{ maxWidth: 320, fontSize: 14, color: 'var(--stone-2)' }}>
              <span className="mono" style={{ color: 'var(--fg-dim)' }}>brevitas</span> (Latin) — shortness, concision. A rhetorical virtue: saying more with less.
            </div>
          </div>
          <div>
            <h4>Product</h4>
            <ul>
              <li><a href="/product">Product</a></li>
              <li><a href="/how-it-works">How it works</a></li>
              <li><a href="/benchmarks">Benchmarks</a></li>
              <li><a href="/docs">Docs</a></li>
              <li><a href="/docs">Changelog</a></li>
            </ul>
          </div>
          <div>
            <h4>Company</h4>
            <ul>
              <li><a href="/blog">Blog</a></li>
              <li><a href="mailto:james@brevitas.systems">Contact</a></li>
              <li><a href="/waitlist">Waitlist</a></li>
            </ul>
          </div>
          <div>
            <h4>Stay in the loop</h4>
            <WaitlistInput variant="footer-small" source="footer" />
            <div className="t-mono" style={{ marginTop: 14, color: 'var(--stone)', fontSize: 12 }}>
              A monthly note. No marketing.
            </div>
          </div>
        </div>
        <div className="footer-bottom">
          <div>©2026 Brevitas Systems. All rights reserved.</div>
          <div className="legal">
            <a href="#">Privacy</a>
            <a href="#">Terms</a>
            <span className="status-dot">status: operational</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

// Scroll-reveal controller — adds .in class to .fade-up when in view
function useFadeUpReveal() {
  useEffect(() => {
    const els = document.querySelectorAll('.fade-up:not(.in)');
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -5% 0px' });
    els.forEach(el => io.observe(el));
    return () => io.disconnect();
  }, []);
}

Object.assign(window, {
  useInView, useReducedMotion, useCountUp, useFadeUpReveal,
  LogoMark, ArrowRight, Overline, Button, SectionShell,
  StatCard, TechniqueCard, BenchmarkBadge,
  CodeBlock, CodeBlockPy, syntaxPython,
  WaitlistInput, ThemeToggle, Nav, Footer,
});
