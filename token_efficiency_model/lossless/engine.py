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
                     session_id: str, optimize_prompts: bool = True) -> dict:
    """Apply the lossless strategy to `body` in place and return decision meta.

    Two complementary levers run here:
      1. CONTEXT lever (caching / retrieval): saves on LARGE, repeating context. Needs a
         prefix above the provider's cacheable minimum, so it does nothing for small tasks.
      2. PROMPT lever (`optimize_prompts`): shrinks the volatile last user message itself —
         lossless whitespace normalization always, plus task-aware LLMLingua-2 when the
         [promptopt] extra is installed. This is what saves on SMALL / one-shot tasks.

    The stable prefix is always left byte-identical (only the last message is touched), so
    provider prefix-caching is never disturbed.
    """
    messages = body.get("messages", []) or []
    if not messages:
        return {"strategy": "passthrough", "reason": "no messages"}

    system = body.get("system")
    stable = _stable_context(messages, system)
    query = _msg_text(messages[-1].get("content", ""))

    decision = router.decide(session_id, stable, query)
    meta: Dict[str, Any] = {"strategy": decision.strategy, "reason": decision.reason}

    # --- 1. CONTEXT lever -----------------------------------------------------
    strategy = decision.strategy
    handled = False
    if strategy == "retrieve":
        # reduce the prior context to the relevant chunks (fail-safe to full inside)
        sel = retrieval_select(query[:200], stable, k=8)
        if not sel["fallback_applied"] and sel["selected_context"]:
            keep = set(sel["selected_context"])
            new_msgs = [m for m in messages[:-1] if _msg_text(m.get("content", "")) in keep]
            new_msgs.append(messages[-1])
            body["messages"] = new_msgs
            meta.update({"strategy": "retrieve", "kept": len(new_msgs), "of": len(messages),
                         "baseline_tokens": sel["baseline_tokens"],
                         "optimized_tokens": sel["optimized_tokens"]})
            handled = True
        else:
            # retrieval bailed (e.g. encoder unavailable). DON'T force a cache write —
            # only fall through to caching if the router has authorised a write.
            strategy = "cache_only" if decision.write_cache else "passthrough"
            meta["strategy"] = strategy

    if not handled:
        # Anthropic cache WRITES cost ~1.25x input and only pay off once a read follows.
        # Only inject cache_control after the prefix has proven to repeat (write_cache),
        # so a one-off / non-repeating call is never made MORE expensive than baseline.
        if provider == "anthropic" and strategy == "cache_only" and decision.write_cache:
            plan = apply_anthropic_cache(body)   # inject cache_control breakpoints
            meta.update({"strategy": "cache_only", "cache_breakpoints": plan.breakpoints,
                         "cached_prefix_tokens": plan.cached_prefix_tokens})
        elif provider == "anthropic" and not decision.write_cache:
            # Anthropic without a proven repeat: leave the prefix untouched (baseline cost).
            meta["strategy"] = "passthrough"
        # OpenAI/DeepSeek: caching is automatic on byte-identical prefixes — we DON'T mutate it.

    # --- 2. PROMPT lever (any task size, incl. small/one-shot) ----------------
    if optimize_prompts:
        meta.update(_optimize_last_message(body))

    return meta


# Reused across calls; the heavy LLMLingua-2 model (if any) is loaded once, lazily.
_TASK_ROUTER = None


def _get_task_router():
    global _TASK_ROUTER
    if _TASK_ROUTER is None:
        from .task_router import TaskCompressionRouter
        _TASK_ROUTER = TaskCompressionRouter()
    return _TASK_ROUTER


def _optimize_text(text: str) -> Tuple[str, int, int]:
    """Return (optimized_text, tokens_before, tokens_after). Never expands tokens."""
    if not text or not text.strip():
        return text, 0, 0
    opt = _get_task_router().route(text).optimization
    if opt.optimized.strip() and opt.tokens_after < opt.tokens_before:
        return opt.optimized, opt.tokens_before, opt.tokens_after
    return text, opt.tokens_before, opt.tokens_before


def _optimize_last_message(body: dict) -> dict:
    """Shrink ONLY the last user message (the volatile prompt). Preserves message role and
    any non-text content blocks (images, tool calls); never touches the stable prefix."""
    messages = body.get("messages") or []
    idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], dict) and messages[i].get("role") == "user":
            idx = i
            break
    if idx < 0:
        return {"prompt_optimized": False}

    msg = messages[idx]
    content = msg.get("content")
    before = after = 0
    changed = False

    if isinstance(content, str):
        new_text, before, after = _optimize_text(content)
        if new_text != content:
            new_msg = dict(msg)
            new_msg["content"] = new_text
            messages[idx] = new_msg
            changed = True
    elif isinstance(content, list):
        new_blocks = []
        for blk in content:
            if (isinstance(blk, dict) and blk.get("type") == "text"
                    and isinstance(blk.get("text"), str)):
                nt, b, a = _optimize_text(blk["text"])
                before += b
                after += a
                if nt != blk["text"]:
                    nb = dict(blk)
                    nb["text"] = nt
                    new_blocks.append(nb)
                    changed = True
                else:
                    new_blocks.append(blk)
            else:
                new_blocks.append(blk)
        if changed:
            new_msg = dict(msg)
            new_msg["content"] = new_blocks
            messages[idx] = new_msg
    else:
        return {"prompt_optimized": False}

    return {"prompt_optimized": changed,
            "prompt_tokens_before": before, "prompt_tokens_after": after}


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
