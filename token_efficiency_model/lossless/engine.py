"""Shared lossless optimization engine — used by the SDK wrapper, the drop-in client, and
the proxy so the router + caching + retrieval logic lives in ONE place.

optimize_request(): given a chat request body, asks the router whether to cache_only, retrieve,
or passthrough for this call, applies the chosen LOSSLESS strategy in-place, and returns the
decision. record_usage(): computes honest savings from the provider response and feeds the
real cache-hit rate back to the router so it adapts per provider/session.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .api_adapter import retrieval_select
from .provider_cache import apply_anthropic_cache, savings_from_usage
from .router import BrevitasRouter


def _msg_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _stable_context(messages: List[dict], system: Any = None) -> List[str]:
    """The repeatable prefix: system + all but the last (volatile) message."""
    ctx: List[str] = []
    if system:
        ctx.append(_msg_text(system) if not isinstance(system, str) else system)
    for m in messages[:-1]:
        t = _msg_text(m.get("content", ""))
        if t:
            ctx.append(t)
    return ctx


def optimize_request(body: dict, provider: str, router: BrevitasRouter,
                     session_id: str) -> dict:
    """Apply the router-chosen lossless strategy to `body` in place. Returns decision meta."""
    messages = body.get("messages", []) or []
    if not messages:
        return {"strategy": "passthrough", "reason": "no messages"}

    system = body.get("system")
    stable = _stable_context(messages, system)
    query = _msg_text(messages[-1].get("content", "")) if messages else ""

    decision = router.decide(session_id, stable, query)

    strategy = decision.strategy
    if strategy == "retrieve":
        # reduce the prior context to the relevant chunks (fail-safe to full inside)
        sel = retrieval_select(query[:200], stable, k=8)
        if not sel["fallback_applied"] and sel["selected_context"]:
            keep = set(sel["selected_context"])
            new_msgs = [m for m in messages[:-1] if _msg_text(m.get("content", "")) in keep]
            new_msgs.append(messages[-1])
            body["messages"] = new_msgs
            return {"strategy": "retrieve", "reason": decision.reason,
                    "kept": len(new_msgs), "of": len(messages),
                    "baseline_tokens": sel["baseline_tokens"],
                    "optimized_tokens": sel["optimized_tokens"]}
        # retrieval bailed (e.g. encoder unavailable). DON'T force a cache write —
        # only fall through to caching if the router has authorised a write.
        strategy = "cache_only" if decision.write_cache else "passthrough"

    # cache_only / passthrough.
    # Anthropic cache WRITES cost ~1.25x input and only pay off once a read follows.
    # Only inject cache_control after the prefix has proven to repeat (write_cache),
    # so a one-off / non-repeating call is never made MORE expensive than baseline.
    if provider == "anthropic" and strategy == "cache_only" and decision.write_cache:
        plan = apply_anthropic_cache(body)   # inject cache_control breakpoints
        return {"strategy": "cache_only", "reason": decision.reason,
                "cache_breakpoints": plan.breakpoints,
                "cached_prefix_tokens": plan.cached_prefix_tokens}
    # OpenAI/DeepSeek: caching is automatic if prefix is byte-identical — we DON'T mutate it.
    # Anthropic without a proven repeat: passthrough (body untouched = baseline cost).
    if provider == "anthropic" and not decision.write_cache:
        return {"strategy": "passthrough", "reason": decision.reason}
    return {"strategy": strategy, "reason": decision.reason}


def record_usage(usage: dict, provider: str, router: BrevitasRouter, session_id: str):
    """Honest savings from real usage + feed cache-hit feedback to the router."""
    s = savings_from_usage(usage, provider)
    if provider == "anthropic":
        prompt = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) \
                 + usage.get("cache_read_input_tokens", 0)
    else:
        prompt = usage.get("prompt_tokens", 0)
    router.observe_usage(session_id, prompt, s.cached_tokens)
    return s
