"""Data model for scan results."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    CLIENT = "client"        # a client constructor call — the wrap target
    CALL_SITE = "call_site"  # a model call (.messages.create / .chat.completions.create)


class Recommendation(str, Enum):
    APPLY = "apply"    # safe to auto-wrap with brevitas.wrap(...)
    MANUAL = "manual"  # detected, but needs a human (async client, unusual shape)
    DONE = "done"      # already routed through Brevitas


class Strategy(str, Enum):
    """Per-call recommendation: how should Brevitas save tokens on THIS call?"""
    OPTIMIZE = "optimize"   # simple/creative prompt -> compress it (LLMLingua-2)
    LOSSLESS = "lossless"   # complex/precise prompt -> keep full, save via caching/retrieval
    UNKNOWN = "unknown"     # couldn't read the prompt text to classify


@dataclass
class Finding:
    path: str
    line: int
    col: int
    end_line: int
    end_col: int
    kind: Kind
    provider: str
    symbol: str                       # e.g. "anthropic.Anthropic" or "client.messages.create"
    source: str = ""                  # exact source segment
    is_async: bool = False
    var_name: str | None = None       # variable the client is bound to, if any
    recommendation: Recommendation = Recommendation.APPLY
    reason: str = ""

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}:{self.col + 1}"


@dataclass
class ScanReport:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (path, message)

    @property
    def clients(self) -> list[Finding]:
        return [f for f in self.findings if f.kind is Kind.CLIENT]

    @property
    def call_sites(self) -> list[Finding]:
        return [f for f in self.findings if f.kind is Kind.CALL_SITE]

    @property
    def applicable(self) -> list[Finding]:
        """Client constructions that can be auto-wrapped."""
        return [f for f in self.clients if f.recommendation is Recommendation.APPLY]

    @property
    def is_pipeline(self) -> bool:
        """Heuristic: ≥2 model call sites ⇒ a multi-agent / multi-hop pipeline,
        which is exactly where Brevitas earns its keep by compressing between hops."""
        return len(self.call_sites) >= 2
