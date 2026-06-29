"""
Wraps anthropic.Anthropic so messages.create()/stream() apply LOSSLESS token savings
(auto-router: cache_control breakpoints vs retrieval) before forwarding to Anthropic.

Usage:
    import anthropic, brevitas
    client = brevitas.wrap(anthropic.Anthropic(api_key="sk-ant-..."))
    response = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024, messages=[...])
"""
from __future__ import annotations

from typing import Any

from .._compress import report_usage
from ..config import get as _bvt_cfg
from ..labels import resolve_labels
from ..session import BrevitasSession
from token_efficiency_model.lossless.engine import optimize_request, record_usage
from token_efficiency_model.lossless.router import BrevitasRouter

_PROVIDER = "anthropic"


class _BrevitasMessages:
    def __init__(self, messages_obj: Any, session: BrevitasSession,
                 router: BrevitasRouter) -> None:
        self._orig = messages_obj
        self._session = session
        self._router = router

    def _optimize(self, messages, model, kwargs):
        sid = kwargs.pop("_brevitas_session", self._session.session_id)
        labels = resolve_labels(kwargs.pop("_brevitas_meta", None))
        body = {"messages": list(messages), "model": model, **kwargs}
        optimize_request(body, _PROVIDER, self._router, sid,
                         optimize_prompts=_bvt_cfg().get("optimize_prompts", True))
        return body, sid, labels

    def create(self, *, messages: list[dict], model: str = "", **kwargs: Any) -> Any:
        body, sid, labels = self._optimize(messages, model, kwargs)
        response = self._orig.create(**body)
        try:
            block = response.content[0]
            self._session.record_response(getattr(block, "text", ""))
            u = response.usage
            fresh = getattr(u, "input_tokens", 0)
            write = getattr(u, "cache_creation_input_tokens", 0)
            read = getattr(u, "cache_read_input_tokens", 0)
            usage = {"input_tokens": fresh, "cache_creation_input_tokens": write,
                     "cache_read_input_tokens": read}
            record_usage(usage, _PROVIDER, self._router, sid)
            # labeled usage for tracking: baseline = all input tokens; optimized = fresh+write
            # (read tokens are cache hits billed at ~10%).
            total_in = fresh + write + read
            report_usage(_PROVIDER, model, total_in, fresh + write, self._session,
                         pipeline=labels["pipeline"], agent=labels["agent"],
                         run_id=labels["run_id"])
        except (AttributeError, IndexError):
            pass
        self._session.advance()
        return response

    def stream(self, *, messages: list[dict], model: str = "", **kwargs: Any):
        body, _, _ = self._optimize(messages, model, kwargs)
        return self._orig.stream(**body)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._orig, name)


class BrevitasAnthropicClient:
    def __init__(self, client: Any, session: BrevitasSession | None = None) -> None:
        self._client = client
        self._session = session or BrevitasSession()
        self._router = BrevitasRouter(provider="anthropic")
        self.messages = _BrevitasMessages(client.messages, self._session, self._router)

    @property
    def session(self) -> BrevitasSession:
        return self._session

    def new_session(self) -> None:
        """Start a fresh pipeline run (clears cross-hop context)."""
        self._session = BrevitasSession()
        self.messages = _BrevitasMessages(self._client.messages, self._session, self._router)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
