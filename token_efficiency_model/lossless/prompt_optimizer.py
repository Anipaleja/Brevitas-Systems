"""Single-prompt token optimization — shrink ONE prompt's token count.

This is a different lever from caching/dedup/delta (which avoid re-sending repeated context).
Here we reduce the tokens of a single, one-shot prompt. Two layers:

1. LOSSLESS normalization (always on, safe): collapse redundant whitespace / blank lines and
   trim trailing space *outside* fenced code blocks. Meaning-preserving; small but free savings.

2. LLMLingua-2 compression (opt-in, LOSSY, paper-backed): faithful prompt compression via the
   published `llmlingua` library — LLMLingua-2 (Pan et al., ACL'24, arXiv:2403.12968), a token
   classifier (keep/discard) distilled from GPT-4. Gives 2-5x compression with strong
   answer-retention, but it DOES drop tokens, so it is lossy and opt-in via `rate < 1.0`.
   Requires the `[promptopt]` extra (`pip install brevitas-systems[promptopt]`); if unavailable,
   we fail safe to lossless-only and say so.

Token counts are measured with the real tokenizer (tiktoken cl100k_base).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .provider_cache import count_tokens

_FENCE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)


@dataclass
class PromptOptimization:
    original: str
    optimized: str
    tokens_before: int
    tokens_after: int
    saved_pct: float
    method: str          # "lossless" | "llmlingua2" | "llmlingua2+lossless"
    lossy: bool
    note: str = ""


def normalize_prompt(text: str) -> str:
    """Lossless whitespace/format normalization. Code fences are left byte-identical so
    indentation-significant content (Python, YAML, etc.) is never altered."""
    if not text:
        return text
    parts = _FENCE.split(text)
    out = []
    for i, seg in enumerate(parts):
        if i % 2 == 1:                      # odd indices are the captured code fences
            out.append(seg)
            continue
        # prose segment: safe, meaning-preserving cleanups
        seg = re.sub(r"[ \t]+", " ", seg)          # runs of spaces/tabs -> single space
        seg = re.sub(r" *\n", "\n", seg)           # trailing spaces before newlines
        seg = re.sub(r"\n{3,}", "\n\n", seg)        # 3+ blank lines -> one blank line
        out.append(seg)
    return "".join(out).strip()


# --- optional LLMLingua-2 (lazy, fail-safe) -------------------------------- #
_LLMLINGUA = None
_LLMLINGUA_TRIED = False


def _get_llmlingua():
    global _LLMLINGUA, _LLMLINGUA_TRIED
    if _LLMLINGUA_TRIED:
        return _LLMLINGUA
    _LLMLINGUA_TRIED = True
    try:
        from llmlingua import PromptCompressor
        _LLMLINGUA = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
        )
    except Exception:
        _LLMLINGUA = None
    return _LLMLINGUA


def optimize_prompt(text: str, rate: float = 1.0,
                    force_tokens: Optional[list] = None) -> PromptOptimization:
    """Optimize a single prompt's token count.

    Args:
        text: the prompt to shrink.
        rate: target keep-ratio. 1.0 = lossless normalization only (safe, default). A value
            < 1.0 (e.g. 0.5 keeps ~half) enables LLMLingua-2 compression (LOSSY). Requires the
            `[promptopt]` extra; falls back to lossless-only with a note if unavailable.
        force_tokens: tokens LLMLingua-2 must never drop (e.g. ["\n", ".", "?"]).

    Returns a PromptOptimization with before/after token counts measured by tiktoken.
    """
    before = count_tokens(text)
    normalized = normalize_prompt(text)

    if rate >= 1.0:
        after = count_tokens(normalized)
        return PromptOptimization(
            original=text, optimized=normalized, tokens_before=before, tokens_after=after,
            saved_pct=round(100 * (1 - after / max(1, before)), 2),
            method="lossless", lossy=False,
        )

    # rate < 1.0 -> LLMLingua-2 (lossy, opt-in)
    comp = _get_llmlingua()
    if comp is None:
        after = count_tokens(normalized)
        return PromptOptimization(
            original=text, optimized=normalized, tokens_before=before, tokens_after=after,
            saved_pct=round(100 * (1 - after / max(1, before)), 2),
            method="lossless", lossy=False,
            note="LLMLingua-2 unavailable (install brevitas-systems[promptopt]); used lossless only.",
        )
    try:
        result = comp.compress_prompt(
            normalized, rate=rate,
            force_tokens=force_tokens or ["\n", ".", "!", "?", ",", ":"],
        )
        compressed = result.get("compressed_prompt", normalized)
    except Exception as e:
        after = count_tokens(normalized)
        return PromptOptimization(
            original=text, optimized=normalized, tokens_before=before, tokens_after=after,
            saved_pct=round(100 * (1 - after / max(1, before)), 2),
            method="lossless", lossy=False,
            note=f"LLMLingua-2 failed ({type(e).__name__}); used lossless only.",
        )

    after = count_tokens(compressed)
    return PromptOptimization(
        original=text, optimized=compressed, tokens_before=before, tokens_after=after,
        saved_pct=round(100 * (1 - after / max(1, before)), 2),
        method="llmlingua2+lossless", lossy=True,
        note="LLMLingua-2 (arXiv:2403.12968) — lossy compression; verify output on critical prompts.",
    )
