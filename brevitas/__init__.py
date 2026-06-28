"""
Brevitas — drop lossless token savings between your agents and the model.

Quick start (importable service — recommended):
    from brevitas import BrevitasClient

    client = BrevitasClient(provider="openai", api_key="sk-...")
    response, savings = client.chat(
        messages=[{"role": "system", "content": BRAND_PROMPT},
                  {"role": "user", "content": "Write a tweet for our oak table."}],
        model="gpt-4o", session_id="marketing-agent",
    )
    print(savings.savings_pct, savings.cache_placement["strategy"])

The client auto-routes every call (cache vs retrieve), keeps the prefix byte-identical so
provider caching fires, learns each provider's real cache-hit rate, and reports honest
savings. Lossless — never drops load-bearing content; fails safe to full context.

Quick start (SDK wrapper around an existing client):
    import anthropic, brevitas
    client = brevitas.wrap(anthropic.Anthropic(api_key="sk-ant-..."))

    # All calls are now automatically compressed
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "..."}],
    )

Quick start (zero-code proxy):
    $ brevitas start --api-key bvt_... --port 4242
    $ export ANTHROPIC_BASE_URL=http://localhost:4242
    # Your existing code works unchanged.
"""
from .config import configure, get as get_config
from .session import BrevitasSession
from .labels import start_run, agent, get_pipeline, get_agent, get_run_id, resolve_labels
from token_efficiency_model.lossless import BrevitasClient, SavingsReport, BrevitasRouter
from token_efficiency_model.lossless import optimize_prompt, PromptOptimization
from token_efficiency_model.lossless import TaskCompressionRouter, classify_task


def wrap(client, session: BrevitasSession | None = None):
    """
    Wrap an Anthropic or OpenAI client.

    Returns a drop-in replacement that compresses messages before each call
    and tracks multi-hop context within the same pipeline run.

    Args:
        client:  An anthropic.Anthropic or openai.OpenAI instance.
        session: Optional existing BrevitasSession (creates a new one if omitted).
    """
    # Anthropic detection: has .messages attribute with a .create method
    if hasattr(client, "messages") and hasattr(getattr(client, "messages", None), "create"):
        from .wrappers.anthropic import BrevitasAnthropicClient
        return BrevitasAnthropicClient(client, session=session)

    # OpenAI detection: has .chat.completions
    if hasattr(client, "chat") and hasattr(getattr(client, "chat", None), "completions"):
        from .wrappers.openai import BrevitasOpenAIClient
        return BrevitasOpenAIClient(client, session=session)

    raise TypeError(
        f"brevitas.wrap() does not recognise client type {type(client).__name__!r}. "
        "Pass an anthropic.Anthropic or openai.OpenAI instance."
    )


__all__ = ["BrevitasClient", "SavingsReport", "BrevitasRouter",
           "configure", "get_config", "wrap", "BrevitasSession",
           "start_run", "agent", "get_pipeline", "get_agent", "get_run_id", "resolve_labels",
           "optimize_prompt", "PromptOptimization", "TaskCompressionRouter", "classify_task"]
__version__ = "0.6.1"
