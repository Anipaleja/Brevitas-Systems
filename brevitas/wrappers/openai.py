"""
Wraps openai.OpenAI so chat.completions.create() applies LOSSLESS token savings
(auto-router: provider caching vs retrieval) before forwarding to OpenAI/DeepSeek.

Usage:
    import openai, brevitas
    client = brevitas.wrap(openai.OpenAI(api_key="sk-..."))
    response = client.chat.completions.create(model="gpt-4o", messages=[...])
"""
from __future__ import annotations

from typing import Any

from .._compress import report_usage
from ..config import get as _bvt_cfg
from ..labels import resolve_labels
from ..session import BrevitasSession
from token_efficiency_model.lossless.engine import optimize_request, record_usage
from token_efficiency_model.lossless.router import BrevitasRouter


class _BrevitasCompletions:
    def __init__(self, completions_obj: Any, session: BrevitasSession,
                 router: BrevitasRouter) -> None:
        self._orig = completions_obj
        self._session = session
        self._router = router

    def create(self, *, messages: list[dict], model: str = "", **kwargs: Any) -> Any:
        sid = kwargs.pop("_brevitas_session", self._session.session_id)
        labels = resolve_labels(kwargs.pop("_brevitas_meta", None))  # pipeline/agent/run_id
        provider = "deepseek" if "deepseek" in (model or "").lower() else "openai"
        body = {"messages": list(messages), "model": model, **kwargs}
        optimize_request(body, provider, self._router, sid,
                         optimize_prompts=_bvt_cfg().get("optimize_prompts", True))
        response = self._orig.create(**body)
        try:
            text = response.choices[0].message.content or ""
            self._session.record_response(text)
            details = getattr(response.usage, "prompt_tokens_details", None) or {}
            cached = details.get("cached_tokens", 0) if isinstance(details, dict) \
                else getattr(details, "cached_tokens", 0)
            prompt = response.usage.prompt_tokens
            usage = {"prompt_tokens": prompt, "prompt_tokens_details": {"cached_tokens": cached}}
            s = record_usage(usage, provider, self._router, sid)
            # emit labeled usage for per-pipeline/agent/run tracking + billing.
            # baseline = full prompt tokens (uncached); optimized = tokens still billed fresh.
            report_usage(provider, model, prompt, prompt - cached, self._session,
                         pipeline=labels["pipeline"], agent=labels["agent"],
                         run_id=labels["run_id"])
        except (AttributeError, IndexError):
            pass
        self._session.advance()
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._orig, name)


class _BrevitasChat:
    def __init__(self, chat_obj: Any, session: BrevitasSession, router: BrevitasRouter) -> None:
        self._orig = chat_obj
        self.completions = _BrevitasCompletions(chat_obj.completions, session, router)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._orig, name)


class BrevitasOpenAIClient:
    def __init__(self, client: Any, session: BrevitasSession | None = None) -> None:
        self._client = client
        self._session = session or BrevitasSession()
        self._router = BrevitasRouter(provider="openai")
        self.chat = _BrevitasChat(client.chat, self._session, self._router)

    @property
    def session(self) -> BrevitasSession:
        return self._session

    def new_session(self) -> None:
        self._session = BrevitasSession()
        self.chat = _BrevitasChat(self._client.chat, self._session, self._router)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
