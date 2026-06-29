"""Remote compression fallback — call a hosted LLMLingua service when local is unavailable.

When local LLMLingua-2 isn't installed (e.g. machines without torch), this module allows
the pip package to offload compression to a cloud service, so users still get real lossy
compression via a simple HTTP call instead of falling back to lossless-only.

Fail-safe: any network/config error returns None, so the caller can gracefully degrade.
"""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .prompt_optimizer import PromptOptimization


def remote_available() -> bool:
    """Check if a remote compression service URL is configured."""
    return bool(os.environ.get("BREVITAS_COMPRESS_URL"))


def remote_optimize(
    text: str,
    rate: float,
    force_tokens: Optional[list] = None,
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 30,
) -> Optional[PromptOptimization]:
    """Call a remote compression service and return a PromptOptimization.

    Args:
        text: the prompt to compress.
        rate: target keep-ratio (0.1–1.0).
        force_tokens: tokens the service must never drop (e.g. ["\n", "."]).
        url: service URL. Defaults to env BREVITAS_COMPRESS_URL.
        token: Bearer token for auth. Defaults to env BREVITAS_COMPRESS_TOKEN.
        timeout: request timeout in seconds.

    Returns:
        A PromptOptimization built from the service response, or None on any error
        (missing URL, network failure, bad response, etc.).
    """
    url = url or os.environ.get("BREVITAS_COMPRESS_URL")
    if not url:
        return None

    token = token or os.environ.get("BREVITAS_COMPRESS_TOKEN")

    payload = {
        "prompt": text,
        "rate": rate,
    }
    if force_tokens:
        payload["force_tokens"] = force_tokens

    try:
        req = Request(
            f"{url}/v1/optimize",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        with urlopen(req, timeout=timeout) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        # Build PromptOptimization from response.
        return PromptOptimization(
            original=text,
            optimized=response_data.get("compressed_prompt", text),
            tokens_before=response_data.get("tokens_before", 0),
            tokens_after=response_data.get("tokens_after", 0),
            saved_pct=response_data.get("saved_pct", 0.0),
            method=response_data.get("method", "unknown"),
            lossy=response_data.get("lossy", True),
            note="Remote LLMLingua-2 (cloud); verify output on critical prompts.",
        )
    except (URLError, json.JSONDecodeError, KeyError, ValueError, TimeoutError):
        # Network error, bad JSON, missing fields, or timeout — fail safe.
        return None
    except Exception:
        # Catch-all for any unexpected error.
        return None
