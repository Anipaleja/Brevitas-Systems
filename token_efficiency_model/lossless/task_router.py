"""Task-aware compression router — pick how hard to compress a prompt, by task.

Grounded in real, open-source prompt-compression research:
  * LLMLingua-2 (Pan et al., ACL'24, arXiv:2403.12968): per-prompt dynamic compression `rate`
    and `force_tokens` to PROTECT content that must survive. This module sets the rate per task
    and protects code/identifiers/numbers so we "retain as much context as possible".
  * LongLLMLingua (Jiang et al., ICLR'24, arXiv:2310.06839): task/question-aware compression —
    compress the parts least relevant to the task harder. We approximate this by protecting the
    fenced code / structured spans and only compressing the prose.

What's the real algorithm vs. the thin glue:
  - REAL (paper + library): the compression itself is LLMLingua-2 via the `llmlingua` package.
  - GLUE (transparent heuristic, configurable): the task classifier and the task->rate table.
    Aggressive on tasks that tolerate it (creative copy, boilerplate), light on precise tasks
    (math/extraction/legal). This is a routing policy, not a learned model — by design.

Fail-safe: if the `[promptopt]` extra (llmlingua) isn't installed, every task falls back to the
lossless normalization pass (never crashes, never lossy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .prompt_optimizer import PromptOptimization, normalize_prompt, _get_llmlingua
from .provider_cache import count_tokens

_FENCE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)


# --------------------------------------------------------------------------- #
# Task classification (transparent heuristic) + per-task compression policy
# --------------------------------------------------------------------------- #
# rate = fraction of tokens to KEEP. Lower = more compression. 1.0 = lossless only.
# Values chosen conservatively to "retain as much context as possible" while still saving on
# the tasks that tolerate it. Tune via TaskCompressionRouter(rates=...).
_DEFAULT_RATES: Dict[str, float] = {
    "creative":   0.45,   # marketing reel/copy/social — verbose briefs compress well
    "code":       0.65,   # frontend/code gen — compress prose, but PROTECT code/identifiers
    "general":    0.6,    # open-ended generation
    "summarize":  0.5,    # summarization tolerates input compression
    "reasoning":  0.85,   # math/logic/planning — light touch; details matter
    "extraction": 0.9,    # exact extraction/QA — minimal; every token may be load-bearing
}

_TASK_PATTERNS = [
    ("code",       r"\b(code|function|component|react|frontend|backend|api|css|html|"
                   r"javascript|typescript|python|build (me )?a (web|app|site)|implement|refactor)\b"),
    ("creative",   r"\b(marketing|reel|ad|caption|tagline|social( media)?|tweet|post|"
                   r"slogan|brand|story|poem|script|video|instagram|tiktok|copywrit)\b"),
    ("summarize",  r"\b(summar(y|ize|ise)|tl;?dr|condense|key points|brief)\b"),
    ("extraction", r"\b(extract|find the|what is the|list all|exact|verbatim|table of|"
                   r"pull out|return the)\b"),
    ("reasoning",  r"\b(calculate|compute|prove|solve|reason|step by step|logic|math|"
                   r"derive|why|analy(s|z)e)\b"),
]


def classify_task(prompt: str, hint: Optional[str] = None) -> str:
    """Return a task class for the prompt. `hint` (an explicit task tag) wins if given."""
    if hint and hint.lower() in _DEFAULT_RATES:
        return hint.lower()
    low = (prompt or "").lower()
    for name, pat in _TASK_PATTERNS:
        if re.search(pat, low):
            return name
    return "general"


def _protect_tokens(prompt: str) -> List[str]:
    """Tokens LLMLingua-2 must never drop: identifiers, numbers, structural punctuation.
    This is how we 'retain as much context as possible' for code/precise tasks."""
    base = ["\n", ".", "!", "?", ",", ":", ";", "(", ")", "{", "}", "[", "]", "=", "-"]
    # protect code-ish identifiers and numbers actually present in the prompt
    idents = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", prompt))
    nums = set(re.findall(r"\b\d[\d.,]*\b", prompt))
    # cap to keep the force list reasonable
    return base + list(idents)[:200] + list(nums)[:50]


@dataclass
class TaskCompressionResult:
    task: str
    rate: float
    optimization: PromptOptimization
    protected_code_blocks: int


@dataclass
class TaskCompressionRouter:
    """Classify a prompt's task and compress it at a task-appropriate rate (LLMLingua-2),
    protecting code blocks and key tokens. Fail-safe to lossless when llmlingua is absent."""

    rates: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_RATES))
    protect_code: bool = True

    def route(self, prompt: str, task_hint: Optional[str] = None) -> TaskCompressionResult:
        task = classify_task(prompt, task_hint)
        rate = self.rates.get(task, 0.6)

        # split out fenced code; for code tasks we never compress the code itself.
        segments = _FENCE.split(prompt)
        code_blocks = sum(1 for i, _ in enumerate(segments) if i % 2 == 1)

        comp = _get_llmlingua()
        if comp is None or rate >= 1.0:
            opt = self._lossless(prompt)
            if comp is None:
                opt.note = (opt.note + " " if opt.note else "") + \
                    "LLMLingua-2 unavailable (install brevitas-systems[promptopt]); lossless only."
            return TaskCompressionResult(task, rate, opt, code_blocks)

        before = count_tokens(prompt)
        force = _protect_tokens(prompt)
        out_parts: List[str] = []
        for i, seg in enumerate(segments):
            if i % 2 == 1:                       # code fence
                out_parts.append(seg if self.protect_code else seg)
                continue
            seg_norm = normalize_prompt(seg)
            if count_tokens(seg_norm) < 40:      # too short to compress meaningfully
                out_parts.append(seg_norm)
                continue
            try:
                res = comp.compress_prompt(seg_norm, rate=rate, force_tokens=force)
                out_parts.append(res.get("compressed_prompt", seg_norm))
            except Exception:
                out_parts.append(seg_norm)
        optimized = "".join(out_parts).strip()
        after = count_tokens(optimized)
        opt = PromptOptimization(
            original=prompt, optimized=optimized, tokens_before=before, tokens_after=after,
            saved_pct=round(100 * (1 - after / max(1, before)), 2),
            method="llmlingua2+lossless", lossy=True,
            note=f"task={task}, rate={rate}; code blocks protected={code_blocks}. "
                 "LLMLingua-2 (arXiv:2403.12968) — lossy; verify critical prompts.",
        )
        return TaskCompressionResult(task, rate, opt, code_blocks)

    def _lossless(self, prompt: str) -> PromptOptimization:
        before = count_tokens(prompt)
        norm = normalize_prompt(prompt)
        after = count_tokens(norm)
        return PromptOptimization(
            original=prompt, optimized=norm, tokens_before=before, tokens_after=after,
            saved_pct=round(100 * (1 - after / max(1, before)), 2),
            method="lossless", lossy=False,
        )
