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


def test_openai_stable_prefix_never_mutated():
    """OpenAI caching is server-side and prefix-based; the engine must leave the stable
    prefix byte-identical (only the volatile last message may be optimized)."""
    r = BrevitasRouter(provider="openai")
    prefix = [
        {"role": "system", "content": _big_system()},
        {"role": "assistant", "content": "ok"},
    ]
    body = {"model": "gpt-4o", "messages": [dict(m) for m in prefix]
            + [{"role": "user", "content": "hi"}]}
    optimize_request(body, "openai", r, "s")
    assert body["messages"][:2] == prefix  # prefix untouched


def test_small_task_is_optimized_when_enabled():
    """A SMALL, one-shot prompt (below the cacheable minimum) still gets the prompt lever.
    With no [promptopt] extra this is lossless normalization — collapsing redundant
    whitespace — which the caching/retrieval levers would never touch."""
    r = BrevitasRouter(provider="openai")
    messy = "Write    a   haiku   about   the   ocean.\n\n\n\nMake it calm."
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": messy}]}
    meta = optimize_request(body, "openai", r, "s", optimize_prompts=True)
    assert meta["prompt_optimized"] is True
    assert "    " not in body["messages"][0]["content"]   # whitespace collapsed
    assert body["messages"][0]["content"].count("\n\n\n") == 0


def test_prompt_lever_can_be_disabled():
    r = BrevitasRouter(provider="openai")
    messy = "Write    a   haiku   about   the   ocean."
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": messy}]}
    meta = optimize_request(body, "openai", r, "s", optimize_prompts=False)
    assert meta.get("prompt_optimized") in (None, False)
    assert body["messages"][0]["content"] == messy   # untouched


def test_prompt_lever_preserves_non_text_blocks():
    """Image / non-text content blocks must survive prompt optimization."""
    r = BrevitasRouter(provider="openai")
    content = [
        {"type": "text", "text": "Describe    this    image    in    detail please."},
        {"type": "image_url", "image_url": {"url": "data:..."}},
    ]
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": content}]}
    optimize_request(body, "openai", r, "s", optimize_prompts=True)
    blocks = body["messages"][0]["content"]
    assert any(b.get("type") == "image_url" for b in blocks)   # image kept
    assert "    " not in blocks[0]["text"]                      # text optimized
