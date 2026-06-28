"""Lever 1 — provider-native prompt caching, measured honestly.

This finishes the native-caching lever from REVAMP_PLAN.md:

1. apply_anthropic_cache(): place cache_control breakpoints ONLY where the cached prefix
   is >= the provider minimum (1024 tokens), on stable blocks (tools/system/prior turns),
   never on the volatile last user message, using up to 4 breakpoints. (The existing
   optimizers/provider_cache/anthropic.py never actually counted tokens.)

2. savings_from_usage(): read the REAL cache fields from the provider response and compute
   honest savings = (what uncached would cost) vs (actual billed cost with cache discount):
     * Anthropic: cache_read_input_tokens (~0.1x), cache_creation_input_tokens (~1.25x)
     * OpenAI/DeepSeek: usage.prompt_tokens_details.cached_tokens (~0.5x)

Provider facts (docs): Anthropic min cacheable 1024 tok, cache read ~10% of input price;
OpenAI automatic >=1024 tok, cached input ~50% off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# token counting
# --------------------------------------------------------------------------- #
try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text or "", disallowed_special=()))
except Exception:  # pragma: no cover
    def count_tokens(text: str) -> int:
        return max(1, int(len((text or "").split()) * 1.3))


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return block.get("text", "") or block.get("content", "") if isinstance(
            block.get("text", ""), str) else ""
    return ""


def _content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return count_tokens(content)
    if isinstance(content, list):
        return sum(count_tokens(_block_text(b)) for b in content)
    return 0


# --------------------------------------------------------------------------- #
# 1. Anthropic cache_control placement (with real 1024-token guard)
# --------------------------------------------------------------------------- #
def _mark(obj_holder: dict, key: str) -> bool:
    """Attach cache_control to the last text block of body[key] (system) or a message
    content. Converts a string to a one-element block list. Returns True if marked."""
    val = obj_holder.get(key)
    if isinstance(val, str):
        obj_holder[key] = [{"type": "text", "text": val, "cache_control": {"type": "ephemeral"}}]
        return True
    if isinstance(val, list) and val:
        if isinstance(val[-1], dict) and "cache_control" not in val[-1]:
            val[-1]["cache_control"] = {"type": "ephemeral"}
            return True
    return False


def _mark_content(msg: dict) -> bool:
    content = msg.get("content")
    if isinstance(content, str):
        msg["content"] = [{"type": "text", "text": content,
                           "cache_control": {"type": "ephemeral"}}]
        return True
    if isinstance(content, list) and content:
        if isinstance(content[-1], dict) and "cache_control" not in content[-1]:
            content[-1]["cache_control"] = {"type": "ephemeral"}
            return True
    return False


@dataclass
class CachePlan:
    breakpoints: int
    cached_prefix_tokens: int
    positions: List[str]


def apply_anthropic_cache(body: dict, min_tokens: int = 1024,
                          max_breakpoints: int = 4) -> CachePlan:
    """Insert cache_control breakpoints on the stable prefix in-place; return a CachePlan.

    A breakpoint is only placed where the cumulative prefix (tools + system + prior turns,
    up to that block) is >= min_tokens, so the provider will actually cache it. The volatile
    last user message is never marked. Up to `max_breakpoints` are placed, preferring the
    blocks closest to the tail (maximum cached coverage)."""
    if not isinstance(body, dict):
        return CachePlan(0, 0, [])
    messages = body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return CachePlan(0, 0, [])

    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], dict) and messages[i].get("role") == "user":
            last_user_idx = i
            break

    # ordered stable segments with a (marker-fn, token-count, label)
    segments: List[tuple] = []
    if body.get("tools"):
        tt = sum(count_tokens(str(t)) for t in body["tools"])
        segments.append((lambda: _mark_tools(body), tt, "tools"))
    if body.get("system"):
        segments.append((lambda: _mark(body, "system"), _content_tokens(body["system"]), "system"))
    stable_end = last_user_idx if last_user_idx >= 0 else len(messages)
    for i in range(stable_end):
        msg = messages[i]
        segments.append((lambda m=msg: _mark_content(m), _content_tokens(msg.get("content")),
                         f"message[{i}]"))

    # cumulative tokens; candidate breakpoints are segments whose prefix >= min_tokens
    cum = 0
    candidates = []  # (index_in_segments, cum_after, label)
    for idx, (_, tok, label) in enumerate(segments):
        cum += tok
        if cum >= min_tokens:
            candidates.append((idx, cum, label))

    if not candidates:
        return CachePlan(0, cum, [])

    chosen = candidates[-max_breakpoints:]  # closest to the tail = most coverage
    placed = []
    for idx, cum_after, label in chosen:
        if segments[idx][0]():
            placed.append(label)
    return CachePlan(len(placed), chosen[-1][1] if chosen else 0, placed)


def _mark_tools(body: dict) -> bool:
    tools = body.get("tools")
    if isinstance(tools, list) and tools and isinstance(tools[-1], dict) \
            and "cache_control" not in tools[-1]:
        tools[-1]["cache_control"] = {"type": "ephemeral"}
        return True
    return False


# --------------------------------------------------------------------------- #
# 2. Honest savings from real provider usage
# --------------------------------------------------------------------------- #
# relative input-token prices (cost units); output excluded (savings is input-side)
_ANTHROPIC = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.10}
_OPENAI = {"input": 1.0, "cache_read": 0.50}
# cached-token discount as a fraction of fresh input price, per provider (from provider docs).
# DeepSeek caches at ~10% of input price (90% off); OpenAI ~50%.
_CACHE_READ = {"openai": 0.50, "deepseek": 0.10, "groq": 1.00}


@dataclass
class Savings:
    uncached_cost: float
    actual_cost: float
    savings_pct: float
    cached_tokens: int
    detail: Dict[str, Any]


def savings_from_usage(usage: dict, provider: str) -> Savings:
    """Compute honest input-side savings from a provider response `usage` object."""
    provider = provider.lower()
    if provider == "anthropic":
        fresh = int(usage.get("input_tokens", 0))
        write = int(usage.get("cache_creation_input_tokens", 0))
        read = int(usage.get("cache_read_input_tokens", 0))
        total_in = fresh + write + read
        uncached = total_in * _ANTHROPIC["input"]
        actual = (fresh * _ANTHROPIC["input"] + write * _ANTHROPIC["cache_write"]
                  + read * _ANTHROPIC["cache_read"])
        cached = read
        detail = {"input": fresh, "cache_write": write, "cache_read": read}
    else:  # openai / deepseek style — use the PROVIDER'S real cache discount
        prompt = int(usage.get("prompt_tokens", 0))
        details = usage.get("prompt_tokens_details", {}) or {}
        cached = int(details.get("cached_tokens", 0) or usage.get("prompt_cache_hit_tokens", 0))
        fresh = prompt - cached
        cache_read = _CACHE_READ.get(provider.lower(), 0.50)
        uncached = prompt * 1.0
        actual = fresh * 1.0 + cached * cache_read
        detail = {"prompt": prompt, "cached": cached, "cache_read_rate": cache_read}
    savings_pct = round(100 * (1 - actual / uncached), 2) if uncached > 0 else 0.0
    return Savings(round(uncached, 2), round(actual, 2), savings_pct, cached, detail)
