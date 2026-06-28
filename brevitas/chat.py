"""`brevitas chat` — chat with a big document, with live token tracking.

The big document is pinned as the system context and re-sent every turn (like Claude Code
keeping a codebase in context). Brevitas keeps that prefix byte-identical so the provider
caches it: turn 1 pays full price (cache write), turns 2+ read the doc from cache at a deep
discount. You watch the per-turn + cumulative token/cost savings.
"""

from __future__ import annotations

import os
from typing import List, Optional


def read_document(path: str) -> str:
    """Read a document as text. Supports PDF (textbooks/papers) and plain text/markdown."""
    if path.lower().endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except ImportError:
            pass
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        except ImportError:
            raise SystemExit(
                "Reading PDFs needs a PDF library. Install one:\n"
                "  pip install \"brevitas-systems[pdf]\"   (or: pip install pymupdf)")
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _load_key(provider: str, explicit: str) -> str:
    if explicit:
        return explicit
    names = {
        "deepseek": ["DEEPSEEK_API_KEY", "Deepseek_api_key"],
        "openai": ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
    }.get(provider, [])
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    # try .env / .env.local in CWD
    for fn in (".env.local", ".env"):
        if os.path.exists(fn):
            for line in open(fn):
                for n in names:
                    if line.startswith(n + "="):
                        return line.split("=", 1)[1].strip()
    return ""


def _base_url(provider: str) -> str:
    return {
        "deepseek": "https://api.deepseek.com/v1",
        "openai": "https://api.openai.com/v1",
    }.get(provider, "https://api.openai.com/v1")


def run_chat(doc_path: str, provider: str = "deepseek", model: str = "",
             api_key: str = "", printer=print) -> None:
    from brevitas import BrevitasClient
    from token_efficiency_model.lossless.provider_cache import count_tokens

    document = read_document(doc_path)
    doc_tokens = count_tokens(document)

    key = _load_key(provider, api_key)
    if not key:
        printer(f"No API key for {provider}. Set its env var or pass --api-key.")
        return
    model = model or {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini",
                      "anthropic": "claude-sonnet-4-6"}.get(provider, "gpt-4o-mini")

    client = BrevitasClient(provider=provider, api_key=key, base_url=_base_url(provider))
    system = ("Answer questions using the following document as the source of truth.\n\n"
              "=== DOCUMENT ===\n" + document + "\n=== END DOCUMENT ===")

    printer(f"\nLoaded '{doc_path}' as context: ~{doc_tokens:,} tokens.")
    printer(f"Provider: {provider}/{model}. The document is re-sent each turn; the provider "
            f"caches it so turns 2+ are cheaper. Type a question (or 'exit').\n")

    history: List[dict] = []
    turn = 0
    cum_uncached = cum_actual = cum_cached = 0.0

    while True:
        try:
            q = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            printer("")
            break
        if not q or q.lower() in ("exit", "quit", ":q"):
            break
        turn += 1

        messages = [{"role": "system", "content": system}] + history + [
            {"role": "user", "content": q}]
        try:
            resp, sav = client.chat(messages=messages, model=model,
                                    session_id="brevitas-chat", max_tokens=400)
            answer = resp.choices[0].message.content
        except Exception as e:
            printer(f"  [error: {e}]")
            continue

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        cum_uncached += sav.uncached_cost
        cum_actual += sav.actual_cost
        cum_cached += sav.cached_tokens

        printer(f"\nbot › {answer}\n")
        printer(f"  [turn {turn}] cached {sav.cached_tokens:,} tok · "
                f"this turn {sav.savings_pct:.0f}% saved · "
                f"strategy={sav.cache_placement.get('strategy', '?')}")
        if cum_uncached > 0:
            total_saved = round(100 * (1 - cum_actual / cum_uncached), 1)
            printer(f"  [running] {total_saved}% input-cost saved across {turn} turns "
                    f"({int(cum_cached):,} cached tokens so far)\n")

    printer("session ended.")


def run_demo(doc_path: str, questions: List[str], provider: str = "deepseek",
             model: str = "", api_key: str = "", printer=print) -> dict:
    """Non-interactive: ask a fixed list of questions about a doc; report per-turn + total
    token savings. Used to demonstrate the caching effect of a pinned document."""
    from brevitas import BrevitasClient
    from token_efficiency_model.lossless.provider_cache import count_tokens

    document = read_document(doc_path)
    doc_tokens = count_tokens(document)
    key = _load_key(provider, api_key)
    if not key:
        raise SystemExit(f"No API key for {provider}.")
    model = model or {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini"}.get(provider, "gpt-4o-mini")

    client = BrevitasClient(provider=provider, api_key=key, base_url=_base_url(provider))
    system = ("Answer using the document below as the source of truth.\n\n=== DOCUMENT ===\n"
              + document + "\n=== END DOCUMENT ===")
    printer(f"Document '{os.path.basename(doc_path)}': ~{doc_tokens:,} tokens, re-sent each turn.")
    printer(f"Provider {provider}/{model}\n")

    history: List[dict] = []
    cum_uncached = cum_actual = 0.0
    cached_total = 0
    for i, q in enumerate(questions, 1):
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": q}]
        resp, sav = client.chat(messages=messages, model=model, session_id="demo", max_tokens=120)
        ans = resp.choices[0].message.content
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans}]
        cum_uncached += sav.uncached_cost
        cum_actual += sav.actual_cost
        cached_total += sav.cached_tokens
        printer(f"[turn {i}] Q: {q[:48]}")
        printer(f"         cached={sav.cached_tokens:,} tok · this-turn saved {sav.savings_pct:.0f}%")
    total = round(100 * (1 - cum_actual / cum_uncached), 1) if cum_uncached else 0.0
    printer(f"\n=== {len(questions)} turns: {total}% total input-cost saved · "
            f"{cached_total:,} tokens served from cache ===")
    return {"turns": len(questions), "total_saved_pct": total, "cached_tokens": cached_total}
