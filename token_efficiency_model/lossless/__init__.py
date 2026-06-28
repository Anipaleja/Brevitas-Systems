"""Lossless token-saving levers for Brevitas, each implementing a published algorithm.

Importable service (3 lines):
    from token_efficiency_model.lossless import BrevitasClient
    client = BrevitasClient(provider="openai", api_key="sk-...")
    response, savings = client.chat(messages=[...], model="gpt-4o", session_id="agent-1")

Levers: content-addressed dedup (IPFS/LBFS), delta (Myers/VCDIFF/rsync), retrieval
(DPR/ColBERTv2), RLM, provider-native caching — orchestrated by an auto-router that learns
each provider's real cache behavior and picks the cheapest lossless strategy per call.
"""

from .content_store import ContentStore, RabinChunker, cid
from .dropin import BrevitasClient, BrevitasDropIn, SavingsReport
from .router import BrevitasRouter, RouteDecision
from .prompt_optimizer import optimize_prompt, normalize_prompt, PromptOptimization
from .task_router import TaskCompressionRouter, classify_task, TaskCompressionResult

__all__ = [
    "BrevitasClient", "BrevitasDropIn", "SavingsReport",
    "BrevitasRouter", "RouteDecision",
    "ContentStore", "RabinChunker", "cid",
    "optimize_prompt", "normalize_prompt", "PromptOptimization",
    "TaskCompressionRouter", "classify_task", "TaskCompressionResult",
]
