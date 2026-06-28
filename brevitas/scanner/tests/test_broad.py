"""Tests for the language-agnostic API-call scanner + per-call strategy."""

from brevitas.scanner.broad import analyze_path, scan_text
from brevitas.scanner.models import Strategy


def test_detects_openai_sdk_call_python():
    src = '''
import openai
client = openai.OpenAI()
client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write a punchy marketing reel script for Instagram"}],
)
'''
    calls = scan_text("a.py", src)
    assert any(c.provider == "openai" and c.transport == "sdk" for c in calls)
    # creative prompt -> optimize
    c = [c for c in calls if c.strategy is not Strategy.UNKNOWN][0]
    assert c.strategy is Strategy.OPTIMIZE


def test_detects_raw_http_endpoint_javascript():
    src = '''
const res = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  body: JSON.stringify({ messages: [{ role: "user", content: "Summarize this article in bullets" }] }),
});
'''
    calls = scan_text("a.js", src)
    assert any(c.provider == "anthropic" and c.transport == "http" for c in calls)


def test_complex_code_prompt_routes_lossless():
    src = '''
client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "system", content: "You are a senior engineer. Implement this React component and refactor the function calculateTotal" }],
});
'''
    calls = scan_text("a.ts", src)
    coded = [c for c in calls if c.strategy is not Strategy.UNKNOWN]
    assert coded and coded[0].strategy is Strategy.LOSSLESS
    assert coded[0].complexity == "complex"


def test_no_prompt_text_is_unknown_not_crash():
    src = "client.messages.create(req)\n"
    calls = scan_text("a.py", src)
    assert calls and calls[0].strategy is Strategy.UNKNOWN


def test_walks_directory_and_skips_node_modules(tmp_path):
    (tmp_path / "app.js").write_text(
        'fetch("https://api.deepseek.com/v1/chat/completions", {body: "{\\"content\\":\\"make a marketing reel\\"}"})')
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "lib.js").write_text('fetch("https://api.openai.com/v1/chat/completions")')
    rep = analyze_path(str(tmp_path))
    paths = [c.path for c in rep.calls]
    assert any("app.js" in p for p in paths)
    assert not any("node_modules" in p for p in paths)   # skipped


def test_report_buckets_optimize_vs_lossless():
    src = (
        'fetch("https://api.openai.com/v1/chat/completions", {body:"write a fun instagram caption tagline"})\n'
        'fetch("https://api.openai.com/v1/chat/completions", {body:"extract the exact invoice total verbatim"})\n'
    )
    calls = scan_text("x.js", src)
    strategies = {c.strategy for c in calls if c.strategy is not Strategy.UNKNOWN}
    assert Strategy.OPTIMIZE in strategies and Strategy.LOSSLESS in strategies
