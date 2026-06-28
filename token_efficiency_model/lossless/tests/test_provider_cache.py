"""Tests for Lever 1 — provider-native caching (breakpoint placement + honest savings)."""

from token_efficiency_model.lossless.provider_cache import (
    apply_anthropic_cache,
    count_tokens,
    savings_from_usage,
)


def _long(n_words: int) -> str:
    return " ".join(["lorem"] * n_words)


# --- breakpoint placement honors the >=1024-token guard -------------------- #
def test_no_breakpoint_when_prefix_below_min():
    body = {
        "system": "short system prompt",
        "messages": [{"role": "user", "content": "hi"}],
    }
    plan = apply_anthropic_cache(body)
    assert plan.breakpoints == 0
    # system left as a plain string (not converted) since not cached
    assert isinstance(body["system"], str)


def test_breakpoint_added_when_prefix_large():
    big = _long(2000)  # well over 1024 tokens
    body = {
        "system": big,
        "messages": [
            {"role": "user", "content": "earlier turn " + _long(1500)},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "the new volatile question"},
        ],
    }
    plan = apply_anthropic_cache(body)
    assert plan.breakpoints >= 1
    assert plan.cached_prefix_tokens >= 1024
    # the volatile last user message must NOT be marked
    last = body["messages"][-1]
    assert isinstance(last["content"], str) or "cache_control" not in last["content"][-1]


def test_tools_block_is_cached_when_large():
    body = {
        "tools": [{"name": "f", "description": _long(2000)}],
        "messages": [{"role": "user", "content": "q"}],
    }
    plan = apply_anthropic_cache(body)
    assert "tools" in plan.positions
    assert "cache_control" in body["tools"][-1]


def test_at_most_four_breakpoints():
    body = {
        "system": _long(2000),
        "messages": (
            [{"role": "user", "content": _long(1500)} for _ in range(8)]
            + [{"role": "user", "content": "final"}]
        ),
    }
    plan = apply_anthropic_cache(body)
    assert plan.breakpoints <= 4


# --- honest savings from real usage ---------------------------------------- #
def test_anthropic_savings_from_cache_read():
    # 9000 tokens read from cache, 1000 fresh -> big discount
    usage = {"input_tokens": 1000, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 9000}
    s = savings_from_usage(usage, "anthropic")
    # uncached = 10000; actual = 1000*1 + 9000*0.1 = 1900 -> 81% savings
    assert s.cached_tokens == 9000
    assert abs(s.savings_pct - 81.0) < 0.5


def test_anthropic_cache_write_costs_more_no_phantom_savings():
    usage = {"input_tokens": 0, "cache_creation_input_tokens": 10000,
             "cache_read_input_tokens": 0}
    s = savings_from_usage(usage, "anthropic")
    assert s.savings_pct < 0  # writing the cache costs 1.25x; honest = negative on turn 1


def test_openai_cached_tokens_savings():
    usage = {"prompt_tokens": 10000, "prompt_tokens_details": {"cached_tokens": 8000}}
    s = savings_from_usage(usage, "openai")
    # actual = 2000*1 + 8000*0.5 = 6000; uncached = 10000 -> 40% savings
    assert s.cached_tokens == 8000
    assert abs(s.savings_pct - 40.0) < 0.5


def test_no_cache_means_no_savings():
    assert savings_from_usage({"prompt_tokens": 500, "prompt_tokens_details": {}}, "openai").savings_pct == 0.0


def test_deepseek_uses_90pct_cache_discount_not_openai_50():
    """Regression: DeepSeek caches at ~10% of input price (90% off), not OpenAI's 50%."""
    usage = {"prompt_tokens": 10000, "prompt_tokens_details": {"cached_tokens": 8000}}
    ds = savings_from_usage(usage, "deepseek").savings_pct
    oa = savings_from_usage(usage, "openai").savings_pct
    assert abs(ds - 72.0) < 0.5    # 2000*1 + 8000*0.1 = 2800 -> 72% saved
    assert abs(oa - 40.0) < 0.5    # 2000*1 + 8000*0.5 = 6000 -> 40% saved
    assert ds > oa
