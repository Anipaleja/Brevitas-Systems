"""Tests for the auto-router — strategy choice by estimated cost + repeat detection."""

from token_efficiency_model.lossless.router import BrevitasRouter, MIN_CACHEABLE


def _big(tokens=2000):
    return " ".join(["brand"] * tokens)


def test_small_context_passthrough():
    r = BrevitasRouter(provider="openai")
    d = r.decide("s1", ["short brand note"], "write a tweet")
    assert d.strategy == "passthrough"


def test_deepseek_repeating_context_prefers_cache():
    """Strong cache (DeepSeek) + repeated context -> cache_only is cheaper."""
    r = BrevitasRouter(provider="deepseek")
    ctx = [_big()]
    # repeat the SAME stable context several times (marketing-agent pattern)
    for _ in range(5):
        d = r.decide("sess", ctx, "write campaign brief variant")
    assert d.repeat_rate > 0.5
    assert d.strategy == "cache_only"


def test_deepseek_unique_context_prefers_retrieve():
    """Strong cache but context changes every call -> retrieval cheaper."""
    r = BrevitasRouter(provider="deepseek")
    last = None
    for i in range(5):
        last = r.decide("sess", [_big() + f" unique-{i}"], "question")
    assert last.repeat_rate == 0.0
    assert last.strategy == "retrieve"


def test_openai_partial_repeat_prefers_retrieve():
    """OpenAI (50% cached): when context only sometimes repeats, retrieval (0.6x) beats the
    blended cache_only cost. (For FULLY-repeating context, cache_only wins even on OpenAI,
    since 0.5x < 0.6x — assuming the provider cache actually activates.)"""
    r = BrevitasRouter(provider="openai")
    # alternate context so repeat_rate stays low/partial
    for i in range(6):
        d = r.decide("sess", [_big() + f" v{i % 2}"], "q")
    assert d.repeat_rate < 0.6
    assert d.strategy == "retrieve"


def test_cache_feedback_flips_decision_when_provider_underdelivers():
    """If observed real cache hit is low (provider not actually caching), the router should
    switch a repeating-context session from cache_only to retrieve — avoiding money loss."""
    r = BrevitasRouter(provider="openai")
    ctx = [_big()]
    for _ in range(5):
        r.decide("sess", ctx, "q")
        r.observe_usage("sess", prompt_tokens=3000, cached_tokens=150)  # 5% hit
    d = r.decide("sess", ctx, "q")
    assert "observed" in d.reason
    assert d.strategy == "retrieve"


def test_cache_feedback_keeps_cache_when_provider_delivers():
    """High observed cache hit (90%) on a strong-cache provider -> stay cache_only."""
    r = BrevitasRouter(provider="deepseek")
    ctx = [_big()]
    for _ in range(5):
        r.decide("sess", ctx, "q")
        r.observe_usage("sess", prompt_tokens=3000, cached_tokens=2700)  # 90% hit
    d = r.decide("sess", ctx, "q")
    assert d.strategy == "cache_only"


def test_no_speculative_cache_write_on_first_sight():
    """A prefix seen for the first time must NOT authorise a cache write — otherwise
    a one-off / test-project Anthropic call pays the ~1.25x write premium for nothing."""
    r = BrevitasRouter(provider="anthropic")
    d = r.decide("sess", [_big()], "q")
    assert d.write_cache is False


def test_cache_write_authorised_only_after_repeat():
    """Once the same prefix repeats, writing the cache is worthwhile (reads will follow)."""
    r = BrevitasRouter(provider="anthropic")
    ctx = [_big()]
    assert r.decide("sess", ctx, "q").write_cache is False   # first sight
    assert r.decide("sess", ctx, "q").write_cache is True    # proven repeat


def test_varying_prefix_never_authorises_write():
    """Context that changes every call must never trigger a (premium) cache write."""
    r = BrevitasRouter(provider="anthropic")
    for i in range(5):
        d = r.decide("sess", [_big() + f" unique-{i}"], "q")
        assert d.write_cache is False


def test_cost_estimates_present_and_ordered():
    r = BrevitasRouter(provider="deepseek")
    ctx = [_big()]
    for _ in range(4):
        d = r.decide("sess", ctx, "q")
    assert d.est_cost_cache_only > 0 and d.est_cost_retrieve > 0
    chosen = min(d.est_cost_cache_only, d.est_cost_retrieve)
    assert (chosen == d.est_cost_cache_only) == (d.strategy == "cache_only")
