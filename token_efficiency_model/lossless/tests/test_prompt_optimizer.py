"""Tests for single-prompt token optimization (lossless layer + fail-safe)."""

from token_efficiency_model.lossless.prompt_optimizer import (
    PromptOptimization,
    normalize_prompt,
    optimize_prompt,
)


# --- lossless normalization ------------------------------------------------ #
def test_collapses_redundant_whitespace():
    messy = "Summarize    this   text.\n\n\n\nBe concise.   \n  Use bullets.  "
    out = normalize_prompt(messy)
    assert "    " not in out                      # no runs of spaces
    assert "\n\n\n" not in out                    # no 3+ newlines
    assert out == "Summarize this text.\n\nBe concise.\n Use bullets."


def test_preserves_code_fences_byte_for_byte():
    p = "Run this:\n```python\ndef f(x):\n        return  x  +  1\n```\nThanks."
    out = normalize_prompt(p)
    # the code fence (incl. its odd indentation + double spaces) must be untouched
    assert "def f(x):\n        return  x  +  1" in out
    # prose around it still normalized
    assert out.startswith("Run this:")


def test_normalization_is_meaning_preserving_wordwise():
    p = "  Please   write   a    poem   about   the   sea.  "
    out = normalize_prompt(p)
    assert out.split() == ["Please", "write", "a", "poem", "about", "the", "sea."]


def test_empty_prompt():
    assert normalize_prompt("") == ""
    r = optimize_prompt("")
    assert r.tokens_before == 0 and r.tokens_after == 0


# --- optimize_prompt API --------------------------------------------------- #
def test_lossless_default_saves_on_messy_prompt():
    messy = "Hello   world.\n\n\n\nThis    is     a    very    spaced    out    prompt."
    r = optimize_prompt(messy)            # rate defaults to 1.0 -> lossless
    assert isinstance(r, PromptOptimization)
    assert r.method == "lossless"
    assert r.lossy is False
    assert r.tokens_after <= r.tokens_before
    assert r.saved_pct >= 0


def test_clean_prompt_yields_little_or_no_savings():
    clean = "Write a haiku about autumn leaves."
    r = optimize_prompt(clean)
    assert r.lossy is False
    assert r.tokens_after <= r.tokens_before     # never increases


def test_lossy_rate_failsafe_when_llmlingua_absent():
    """rate<1.0 requests LLMLingua-2; if the [promptopt] extra isn't installed, it must
    fail safe to lossless (never crash) and say so."""
    r = optimize_prompt("Compress    this    prompt please.", rate=0.5)
    # in CI without the heavy extra, method falls back to lossless with a note
    if r.method == "lossless":
        assert r.lossy is False
        assert "LLMLingua" in r.note
    else:
        assert r.method == "llmlingua2+lossless" and r.lossy is True


def test_token_counts_use_real_tokenizer_and_are_consistent():
    from token_efficiency_model.lossless.provider_cache import count_tokens
    p = "Explain   quantum   entanglement   simply."
    r = optimize_prompt(p)
    assert r.tokens_before == count_tokens(p)
    assert r.tokens_after == count_tokens(r.optimized)
