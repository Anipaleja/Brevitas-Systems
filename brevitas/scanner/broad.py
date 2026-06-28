"""Language-agnostic scan for LLM API calls + per-call strategy recommendation.

Unlike the Python-AST scanner (which targets a safe codemod), this scans ANY text file for
anything that looks like an LLM API call — SDK calls AND raw HTTP — in any language
(Python, JS/TS, Go, Ruby, shell/curl, ...). For each call it reads the nearby prompt text and
recommends a per-call strategy:

  * OPTIMIZE — simple/creative prompts (marketing copy, summaries, general gen): safe to
    compress the prompt (LLMLingua-2).
  * LOSSLESS — complex/precise prompts (code, reasoning/math, exact extraction): keep the full
    prompt; save via caching/retrieval instead.

Detection is intentionally broad (regex over source). It's a heuristic recommender, not a
parser — it errs toward surfacing call sites for a human to confirm.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .models import Strategy

# --- what an LLM API call looks like, across languages + transports --------- #
_PROVIDER_ENDPOINTS = {
    "openai": r"api\.openai\.com",
    "anthropic": r"api\.anthropic\.com",
    "deepseek": r"api\.deepseek\.com",
    "groq": r"api\.groq\.com",
    "google": r"generativelanguage\.googleapis\.com",
    "mistral": r"api\.mistral\.ai",
    "cohere": r"api\.cohere\.(ai|com)",
    "openrouter": r"openrouter\.ai",
}
# SDK call shapes (provider-agnostic verbs)
_SDK_PATTERNS = [
    ("openai",    r"\.chat\.completions\.create\b"),
    ("openai",    r"\bclient\.responses\.create\b"),
    ("anthropic", r"\.messages\.create\b"),
    ("anthropic", r"\.messages\.stream\b"),
    ("openai",    r"\bnew\s+OpenAI\b|\bOpenAI\("),
    ("anthropic", r"\bnew\s+Anthropic\b|\bAnthropic\("),
    ("google",    r"\bgenerateContent\b|GenerativeModel\("),
    ("litellm",   r"\blitellm\.(completion|acompletion)\b"),
    ("openai",    r"\bopenai\.(ChatCompletion|chat)\b"),
    ("any",       r"/v1/chat/completions|/v1/messages|/v1/responses"),
]
_SIGNAL_RE = re.compile(
    "|".join(f"(?P<ep_{k}>{v})" for k, v in _PROVIDER_ENDPOINTS.items())
    + "|" + "|".join(f"(?P<sdk_{i}>{p})" for i, (_, p) in enumerate(_SDK_PATTERNS)),
    re.IGNORECASE,
)
_SDK_PROVIDER = {f"sdk_{i}": prov for i, (prov, _) in enumerate(_SDK_PATTERNS)}

_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
              ".next", "out", "coverage", ".turbo", "vendor", ".cache"}
_TEXT_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rb", ".java",
             ".php", ".rs", ".sh", ".env", ".txt", ".md", ".json", ".yaml", ".yml", ".ipynb"}
_MAX_BYTES = 2_000_000

# pull quoted string literals out of a window of source (single/double/back-tick)
_STRINGS = re.compile(r"\"([^\"]{4,})\"|'([^']{4,})'|`([^`]{4,})`", re.DOTALL)


@dataclass
class ApiCall:
    path: str
    line: int
    provider: str
    matched: str                  # the token that triggered the hit
    transport: str                # "sdk" | "http"
    prompt_excerpt: str = ""      # nearby string literals (best-effort)
    task: str = ""
    complexity: str = ""          # "simple" | "complex" | "unknown"
    strategy: Strategy = Strategy.UNKNOWN
    reason: str = ""

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass
class BroadReport:
    calls: List[ApiCall] = field(default_factory=list)
    files_scanned: int = 0
    errors: List[tuple] = field(default_factory=list)

    @property
    def optimize(self) -> List[ApiCall]:
        return [c for c in self.calls if c.strategy is Strategy.OPTIMIZE]

    @property
    def lossless(self) -> List[ApiCall]:
        return [c for c in self.calls if c.strategy is Strategy.LOSSLESS]


_SIMPLE_TASKS = {"creative", "summarize", "general"}


def _classify(prompt_text: str):
    """prompt_text -> (task, complexity, strategy). Empty text -> UNKNOWN."""
    from token_efficiency_model.lossless.task_router import classify_task
    if not prompt_text.strip():
        return "", "unknown", Strategy.UNKNOWN
    task = classify_task(prompt_text)
    if task in _SIMPLE_TASKS:
        return task, "simple", Strategy.OPTIMIZE
    return task, "complex", Strategy.LOSSLESS


def _extract_strings(text: str) -> List[str]:
    parts = []
    for m in _STRINGS.finditer(text):
        s = next(g for g in m.groups() if g is not None)
        if not s.lower().startswith(("http", "sk-", "bearer ", "application/", "/v1/")):
            parts.append(s)
    return parts


def _nearby_prompt(lines: List[str], idx: int, radius: int = 12) -> str:
    """The call's likely prompt text. Prefer string literals on the SAME line (inline calls
    like fetch(url, {body:"..."})); only if none, widen to +/- radius lines."""
    same_line = _extract_strings(lines[idx])
    if same_line:
        return " ".join(same_line)[:4000]
    lo, hi = max(0, idx - radius), min(len(lines), idx + radius + 1)
    return " ".join(_extract_strings("\n".join(lines[lo:hi])))[:4000]


def scan_text(path: str, source: str) -> List[ApiCall]:
    lines = source.splitlines()
    out: List[ApiCall] = []
    for i, line in enumerate(lines):
        m = _SIGNAL_RE.search(line)
        if not m:
            continue
        gname = m.lastgroup or ""
        if gname.startswith("ep_"):
            provider, transport = gname[3:], "http"
        else:
            provider, transport = _SDK_PROVIDER.get(gname, "any"), "sdk"
        prompt = _nearby_prompt(lines, i)
        task, complexity, strategy = _classify(prompt)
        reason = (f"{complexity} task ({task or 'unclassified'}) -> "
                  f"{'compress prompt' if strategy is Strategy.OPTIMIZE else 'keep full + cache'}"
                  if strategy is not Strategy.UNKNOWN else "no readable prompt nearby")
        out.append(ApiCall(path=path, line=i + 1, provider=provider, matched=m.group(0),
                           transport=transport, prompt_excerpt=prompt[:200],
                           task=task, complexity=complexity, strategy=strategy, reason=reason))
    return out


def analyze_path(root: str) -> BroadReport:
    """Walk `root` (file or dir), find LLM API calls in any text file, recommend per-call strategy."""
    report = BroadReport()
    for fp in _iter_files(root):
        try:
            if os.path.getsize(fp) > _MAX_BYTES:
                continue
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()
        except OSError as exc:
            report.errors.append((fp, str(exc)))
            continue
        report.files_scanned += 1
        report.calls.extend(scan_text(fp, source))
    return report


def _iter_files(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in _TEXT_EXT or name.startswith(".env"):
                yield os.path.join(dirpath, name)
