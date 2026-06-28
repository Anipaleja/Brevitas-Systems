"""Tests for the shared lossless optimization engine.

Regression focus: the engine must never make an Anthropic request MORE expensive
than baseline. Anthropic cache writes cost ~1.25x input, so cache_control is only
injected after a prefix has proven to repeat in the session.
"""

from token_efficiency_model.lossless.engine import optimize_request
from token_efficiency_model.lossless.router import BrevitasRouter


def _big_system(n=300):
    return "You are a helpful assistant. " * n  # comfortably over the 1024-token min


def _cache_injected(body) -> bool:
    sysv = body.get("system")
    if isinstance(sysv, list) and any("cache_control" in b for b in sysv):
        return True
    return any(
        isinstance(m.get("content"), list)
        and any("cache_control" in b for b in m["content"])
        for m in body.get("messages", [])
    )


def _fresh_body():
    return {
        "model": "claude-sonnet-4-6",
        "system": _big_system(),
        "messages": [{"role": "user", "content": "What is 2+2?"}],
    }


def test_first_anthropic_call_is_not_mutated():
    """A one-off call must pass through untouched — no speculative cache write."""
    r = BrevitasRouter(provider="anthropic")
    body = _fresh_body()
    dec = optimize_request(body, "anthropic", r, "s")
    assert dec["strategy"] == "passthrough"
    assert _cache_injected(body) is False
    assert isinstance(body["system"], str)  # unchanged


def test_anthropic_cache_injected_after_repeat():
    """Once the prefix repeats, the engine injects cache_control (now worthwhile)."""
    r = BrevitasRouter(provider="anthropic")
    optimize_request(_fresh_body(), "anthropic", r, "s")      # first sight -> passthrough
    body = _fresh_body()
    dec = optimize_request(body, "anthropic", r, "s")         # repeat -> cache
    assert dec["strategy"] == "cache_only"
    assert _cache_injected(body) is True


def test_varying_prefix_never_mutated():
    """Context that changes each call must never be mutated into a cache write."""
    r = BrevitasRouter(provider="anthropic")
    for i in range(4):
        body = _fresh_body()
        body["system"] = _big_system() + f" variant {i}"
        dec = optimize_request(body, "anthropic", r, "s")
        assert dec["strategy"] == "passthrough"
        assert _cache_injected(body) is False


def test_openai_body_never_mutated():
    """OpenAI caching is server-side; the engine must not touch the request body."""
    r = BrevitasRouter(provider="openai")
    body = _fresh_body()
    body.pop("system")
    body["messages"] = [{"role": "user", "content": _big_system()}]
    before = [dict(m) for m in body["messages"]]
    optimize_request(body, "openai", r, "s")
    assert body["messages"] == before
