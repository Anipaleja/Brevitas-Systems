"""Auto-router — picks the cheapest lossless strategy per request, automatically.

The benchmarks showed the right strategy depends on (a) whether the bulk context REPEATS
across calls and (b) the provider's prompt-cache discount. This router detects both at
runtime and chooses, per request, between:

  * "cache_only" : keep the full context, rely on provider prefix caching (best when the
                   context repeats AND the provider caches strongly, e.g. DeepSeek/Anthropic).
  * "retrieve"   : send only the relevant retrieved subset (best when the context is large
                   and varies per call, OR the provider caches weakly, e.g. OpenAI).
  * "passthrough": context too small to bother.

Decision is by estimated amortized input cost — no guessing. Lossless either way: cache_only
sends everything; retrieve fails safe to full context on low confidence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .provider_cache import count_tokens

# cached-token price as a fraction of fresh input price (from provider docs)
CACHE_DISCOUNT = {
    "anthropic": 0.10,   # cache read ~10% of input
    "deepseek": 0.10,    # disk cache ~10%
    "openai": 0.50,      # cached input ~50%
    "groq": 1.00,        # no caching
    "default": 0.50,
}
MIN_CACHEABLE = 1024     # provider minimum cacheable prefix (tokens)


@dataclass
class RouteDecision:
    strategy: str                 # cache_only | retrieve | passthrough
    reason: str
    est_cost_cache_only: float
    est_cost_retrieve: float
    repeat_rate: float            # 0..1 how often this session's context has repeated
    provider_cache_discount: float
    write_cache: bool = False     # safe to pay a cache WRITE? only once a prefix repeats


@dataclass
class _SessionState:
    last_prefix_hash: str = ""
    calls: int = 0
    repeats: int = 0
    # observed REAL cache performance from provider usage: EWMA of cached/prompt fraction
    obs_hit: float = -1.0          # -1 = no observation yet
    obs_count: int = 0


@dataclass
class BrevitasRouter:
    provider: str = "openai"
    # fraction of a large context that retrieval typically keeps (from benchmarks ~0.6)
    retrieve_keep_frac: float = 0.6

    _sessions: Dict[str, _SessionState] = field(default_factory=dict)

    def _discount(self) -> float:
        return CACHE_DISCOUNT.get(self.provider.lower(), CACHE_DISCOUNT["default"])

    def observe_usage(self, session_id: str, prompt_tokens: int, cached_tokens: int) -> None:
        """Feed back REAL provider usage so the router learns the provider's actual cache
        hit rate (advertised discounts don't always activate). Call after each cache_only
        request with the response's usage. EWMA of cached/prompt fraction."""
        if prompt_tokens <= 0:
            return
        st = self._sessions.setdefault(session_id, _SessionState())
        hit = max(0.0, min(1.0, cached_tokens / prompt_tokens))
        st.obs_hit = hit if st.obs_hit < 0 else 0.5 * st.obs_hit + 0.5 * hit
        st.obs_count += 1

    def _observe(self, session_id: str, stable_context: Sequence[str]) -> tuple[float, bool]:
        """Update repeat tracking; return (running repeat rate, did-this-prefix-just-repeat)."""
        st = self._sessions.setdefault(session_id, _SessionState())
        h = hashlib.sha256("".join(stable_context).encode("utf-8")).hexdigest()
        repeated_now = bool(st.last_prefix_hash) and h == st.last_prefix_hash
        st.calls += 1
        if repeated_now:
            st.repeats += 1
        st.last_prefix_hash = h
        rate = st.repeats / max(1, st.calls - 1) if st.calls > 1 else 0.0
        return rate, repeated_now

    def decide(self, session_id: str, stable_context: Sequence[str],
               volatile_query: str = "") -> RouteDecision:
        """Choose the cheapest strategy for this request."""
        ctx_tokens = sum(count_tokens(c) for c in stable_context)
        q_tokens = count_tokens(volatile_query)
        repeat_rate, _ = self._observe(session_id, stable_context)
        disc = self._discount()

        # A cache WRITE only pays off if a read follows. Only authorise writes once
        # this session's prefix has actually repeated, so a one-off / test-project
        # call never eats a (write-premium) cache write for context that never recurs.
        write_cache = self._sessions[session_id].repeats > 0

        if ctx_tokens < MIN_CACHEABLE:
            return RouteDecision("passthrough", "context below cacheable minimum",
                                 0.0, 0.0, repeat_rate, disc, write_cache=write_cache)

        st = self._sessions[session_id]
        # Effective cache multiplier for cache_only. If we have REAL observations of how much
        # the provider actually caches (obs_hit), use them — advertised discounts don't always
        # activate (e.g. OpenAI underdelivered in tests). Else fall back to repeat_rate model.
        if st.obs_hit >= 0.0 and st.obs_count >= 2:
            eff_mult = (1 - st.obs_hit) * 1.0 + st.obs_hit * disc
            why_basis = f"observed cache hit {st.obs_hit:.0%}"
        else:
            eff_mult = repeat_rate * disc + (1 - repeat_rate) * 1.0
            why_basis = f"repeat {repeat_rate:.0%} x discount {disc:.0%}"

        cache_only = ctx_tokens * eff_mult + q_tokens
        retrieve = ctx_tokens * self.retrieve_keep_frac * 1.0 + q_tokens

        if retrieve < cache_only:
            strat, why = "retrieve", f"retrieval cheaper ({why_basis})"
        else:
            strat, why = "cache_only", f"caching cheaper ({why_basis})"
        return RouteDecision(strat, why, round(cache_only, 1), round(retrieve, 1),
                             round(repeat_rate, 3), disc, write_cache=write_cache)
