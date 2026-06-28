"""Tests for the task-aware compression router (classification + policy + fail-safe)."""

from token_efficiency_model.lossless.task_router import (
    TaskCompressionRouter,
    classify_task,
    _protect_tokens,
    _DEFAULT_RATES,
)


# --- task classification (the user's examples) ----------------------------- #
def test_marketing_reel_is_creative():
    assert classify_task("Make me a marketing reel for our new oak table") == "creative"
    assert classify_task("Write an Instagram caption + tagline for the launch") == "creative"


def test_frontend_code_is_code():
    assert classify_task("Make me a frontend React component for this dashboard") == "code"
    assert classify_task("Build me a web app with an HTML/CSS landing page") == "code"


def test_precise_tasks_classified():
    assert classify_task("Calculate the derivative step by step") == "reasoning"
    assert classify_task("Extract the exact invoice total from this text") == "extraction"
    assert classify_task("Summarize this article in key points") == "summarize"


def test_hint_overrides_classifier():
    assert classify_task("anything at all", hint="code") == "code"
    assert classify_task("ignored", hint="not-a-real-task") == "general"  # invalid hint -> classify


# --- the policy: simple tasks compress harder, precise ones lighter -------- #
def test_creative_rate_more_aggressive_than_reasoning():
    assert _DEFAULT_RATES["creative"] < _DEFAULT_RATES["reasoning"]
    assert _DEFAULT_RATES["extraction"] >= 0.85   # near-lossless for exact tasks


# --- token protection ("retain as much context as possible") --------------- #
def test_protect_tokens_includes_identifiers_and_numbers():
    prompt = "Build a function calculateTotal that returns 42.50 for user_id 1001"
    prot = _protect_tokens(prompt)
    assert "calculateTotal" in prot
    assert "user_id" in prot
    assert "42.50" in prot or "42" in " ".join(prot)


# --- router behavior + fail-safe ------------------------------------------- #
def test_router_classifies_and_failsafes_to_lossless_without_llmlingua():
    r = TaskCompressionRouter()
    res = r.route("Make me a marketing reel for our new product. " * 10)
    assert res.task == "creative"
    assert res.rate == _DEFAULT_RATES["creative"]
    # without the [promptopt] extra installed, must fall back to lossless (never crash, never lossy)
    if res.optimization.method == "lossless":
        assert res.optimization.lossy is False
        assert "LLMLingua" in res.optimization.note
    else:
        assert res.optimization.lossy is True
    assert res.optimization.tokens_after <= res.optimization.tokens_before


def test_router_counts_code_blocks_for_code_tasks():
    prompt = ("Make me a frontend component for this:\n"
              "```jsx\nfunction Btn(){ return <button>Go</button> }\n```\n"
              "Style it nicely and keep it accessible.")
    res = TaskCompressionRouter().route(prompt)
    assert res.task == "code"
    assert res.protected_code_blocks == 1
    # the code fence must survive verbatim regardless of compression
    assert "function Btn(){ return <button>Go</button> }" in res.optimization.optimized


def test_custom_rates():
    r = TaskCompressionRouter(rates={**_DEFAULT_RATES, "creative": 0.3})
    res = r.route("Write a punchy ad reel script. " * 8)
    assert res.rate == 0.3
