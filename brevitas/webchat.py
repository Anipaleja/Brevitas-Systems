"""Web frontend for 'chat with your PDF' with a live token-savings meter.

A small FastAPI app: upload a PDF/text doc, ask questions against it, and watch the per-turn
and cumulative token/cost savings (the doc is cached by the provider, so turns 2+ are cheap).
Launch with `brevitas chat --web`.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse

from .chat import read_document, _load_key, _base_url


@dataclass
class Session:
    doc: str = ""
    doc_tokens: int = 0
    name: str = ""
    history: List[dict] = field(default_factory=list)
    cum_uncached: float = 0.0
    cum_actual: float = 0.0
    cached_total: int = 0
    client: object = None
    model: str = ""


_SESSIONS: Dict[str, Session] = {}


_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".java", ".rs", ".c", ".cpp",
             ".h", ".css", ".html", ".json", ".md", ".txt", ".sh", ".yml", ".yaml", ".vue", ".php"}


def _raw_chat(provider, model, key, messages, max_tokens=500):
    """Direct provider call (NO Brevitas) — same usage shape, so we can compare honestly."""
    import json, urllib.request
    url = _base_url(provider).rstrip("/") + "/chat/completions"
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    u = d.get("usage", {})
    prompt = int(u.get("prompt_tokens", 0))
    cached = int(u.get("prompt_tokens_details", {}).get("cached_tokens", 0) or u.get("prompt_cache_hit_tokens", 0))
    disc = 0.1 if provider in ("deepseek", "anthropic") else 0.5
    uncached_cost = prompt * 1.0
    actual_cost = (prompt - cached) * 1.0 + cached * disc
    saved = round(100 * (1 - actual_cost / uncached_cost), 2) if uncached_cost else 0.0
    return d["choices"][0]["message"]["content"], cached, uncached_cost, actual_cost, saved


def create_app(provider: str = "deepseek", api_key: str = "", brevitas_enabled: bool = True) -> FastAPI:
    from brevitas import BrevitasClient
    from token_efficiency_model.lossless.provider_cache import count_tokens

    app = FastAPI(title="Brevitas Chat", docs_url=None, redoc_url=None)
    key = _load_key(provider, api_key)
    model = {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini"}.get(provider, "gpt-4o-mini")
    mode = "ON" if brevitas_enabled else "OFF"

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _HTML.replace("__PROVIDER__", f"{provider} / {model}").replace("__MODE__", mode)

    @app.post("/api/upload")
    async def upload(files: List[UploadFile] = File(...), session: str = Form("default")):
        # build one big context from all uploaded files (a codebase or a single doc)
        parts, names = [], []
        for f in files:
            raw = await f.read()
            ext = os.path.splitext(f.filename or "")[1].lower()
            if ext == ".pdf":
                with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as tmp:
                    tmp.write(raw); p = tmp.name
                try:
                    txt = read_document(p)
                finally:
                    os.unlink(p)
            elif ext in _CODE_EXT or not ext:
                txt = raw.decode("utf-8", "ignore")
            else:
                continue
            parts.append(f"// ===== FILE: {f.filename} =====\n{txt}")
            names.append(f.filename)
        if not parts:
            return JSONResponse({"error": "No readable code/text/PDF files found."}, status_code=400)
        if not key:
            return JSONResponse({"error": f"No API key for {provider}. Set its env var."}, status_code=400)
        doc = "\n\n".join(parts)
        label = names[0] if len(names) == 1 else f"{len(names)} files"
        s = Session(doc=doc, doc_tokens=count_tokens(doc), name=label, model=model,
                    client=BrevitasClient(provider=provider, api_key=key, base_url=_base_url(provider)))
        _SESSIONS[session] = s
        return {"name": s.name, "tokens": s.doc_tokens, "files": len(names)}

    @app.post("/api/ask")
    async def ask(question: str = Form(...), session: str = Form("default")):
        s = _SESSIONS.get(session)
        if not s or not s.doc:
            return JSONResponse({"error": "Upload a codebase or document first."}, status_code=400)
        system = ("You are a senior engineer. Answer using the codebase/document below as the "
                  "source of truth.\n\n=== CONTEXT ===\n" + s.doc + "\n=== END CONTEXT ===")
        messages = [{"role": "system", "content": system}] + s.history + [
            {"role": "user", "content": question}]
        try:
            if brevitas_enabled:
                resp, sav = s.client.chat(messages=messages, model=s.model, session_id=session, max_tokens=500)
                answer = resp.choices[0].message.content
                cached, unc, act, saved = sav.cached_tokens, sav.uncached_cost, sav.actual_cost, sav.savings_pct
            else:
                answer, cached, unc, act, saved = _raw_chat(provider, s.model, key, messages)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        s.history += [{"role": "user", "content": question},
                      {"role": "assistant", "content": answer}]
        s.cum_uncached += unc
        s.cum_actual += act
        s.cached_total += cached
        total = round(100 * (1 - s.cum_actual / s.cum_uncached), 1) if s.cum_uncached else 0.0
        return {"answer": answer, "cached_tokens": cached, "turn_saved_pct": saved,
                "cumulative_saved_pct": total, "cached_total": s.cached_total,
                "turns": len(s.history) // 2, "brevitas": brevitas_enabled}

    return app


_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brevitas · Chat with your PDF</title>
<style>
:root{--bg:#0b0f17;--panel:#121826;--line:#1f2937;--accent:#34d399;--accent2:#60a5fa;--text:#e5e7eb;--dim:#9ca3af}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex}
.side{width:300px;border-right:1px solid var(--line);padding:20px;display:flex;flex-direction:column;gap:16px;background:var(--panel)}
.main{flex:1;display:flex;flex-direction:column}
h1{font-size:18px;margin:0}.sub{color:var(--dim);font-size:13px}
.drop{border:1.5px dashed var(--line);border-radius:12px;padding:22px;text-align:center;cursor:pointer;transition:.15s}
.drop:hover{border-color:var(--accent2)}.drop input{display:none}
.meter{background:#0e1422;border:1px solid var(--line);border-radius:12px;padding:14px}
.meter .big{font-size:30px;font-weight:700;color:var(--accent)}
.row{display:flex;justify-content:space-between;font-size:13px;color:var(--dim);margin-top:6px}
.row b{color:var(--text)}
#msgs{flex:1;overflow:auto;padding:24px;display:flex;flex-direction:column;gap:14px}
.m{max-width:760px;padding:12px 14px;border-radius:12px;white-space:pre-wrap}
.me{align-self:flex-end;background:#1d4ed8}.bot{align-self:flex-start;background:#111827;border:1px solid var(--line)}
.tag{align-self:flex-start;font-size:12px;color:var(--dim)}
.bar{display:flex;gap:10px;padding:16px;border-top:1px solid var(--line);background:var(--panel)}
input.q{flex:1;background:#0e1422;border:1px solid var(--line);color:var(--text);border-radius:10px;padding:12px 14px;font-size:15px}
button{background:var(--accent);border:0;color:#06281d;font-weight:700;border-radius:10px;padding:0 18px;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.pill{font-size:12px;background:#0e1422;border:1px solid var(--line);border-radius:999px;padding:3px 10px;color:var(--accent)}
</style></head><body>
<div class="side">
  <div><h1>⚡ Brevitas</h1><div class="sub">Chat with a codebase · __PROVIDER__</div>
    <div class="pill" style="margin-top:6px;display:inline-block">Brevitas: __MODE__</div></div>
  <label class="drop"><input type="file" id="file" multiple webkitdirectory>
    <div id="dropText">📁 Upload a codebase folder<br><span class="sub">(or pick files)</span></div>
  </label>
  <div class="meter">
    <div class="sub">Total input-cost saved</div>
    <div class="big" id="saved">—</div>
    <div class="row"><span>This turn</span><b id="turn">—</b></div>
    <div class="row"><span>Tokens from cache</span><b id="cached">0</b></div>
    <div class="row"><span>Turns</span><b id="turns">0</b></div>
    <div class="row"><span>Context size</span><b id="dtok">—</b></div>
  </div>
  <div class="sub">The codebase is re-sent each turn, but the provider caches it — so every
  question after the first is cheaper. The more you ask, the more you save.</div>
</div>
<div class="main">
  <div id="msgs"><div class="tag">Upload a document to begin.</div></div>
  <div class="bar">
    <input class="q" id="q" placeholder="Ask a question about the document…" disabled>
    <button id="send" disabled>Ask</button>
  </div>
</div>
<script>
const $=id=>document.getElementById(id); let ready=false;
function add(cls,txt){const d=document.createElement('div');d.className='m '+cls;d.textContent=txt;$('msgs').appendChild(d);$('msgs').scrollTop=1e9;return d;}
$('file').onchange=async e=>{
  const files=[...e.target.files]; if(!files.length)return;
  $('dropText').innerHTML='⏳ Reading '+files.length+' files…';
  const fd=new FormData();
  // skip junk dirs to keep the context lean
  const skip=/(^|\/)(node_modules|\.git|dist|build|__pycache__|\.venv|venv)(\/|$)/;
  let n=0;
  for(const f of files){ if(skip.test(f.webkitRelativePath||f.name))continue; fd.append('files',f); n++; if(n>=400)break; }
  fd.append('session','default');
  const r=await fetch('/api/upload',{method:'POST',body:fd}); const j=await r.json();
  if(j.error){$('dropText').innerHTML='⚠️ '+j.error;return;}
  $('dropText').innerHTML='✅ '+j.name+'<br><span class="sub">'+j.tokens.toLocaleString()+' tokens</span>';
  $('dtok').textContent=j.tokens.toLocaleString()+' tok';
  $('msgs').innerHTML='<div class="tag">Loaded '+j.name+' ('+j.tokens.toLocaleString()+' tokens). Ask away.</div>';
  ready=true;$('q').disabled=false;$('send').disabled=false;$('q').focus();
};
async function ask(){
  const q=$('q').value.trim(); if(!q||!ready)return;
  $('q').value='';$('send').disabled=true; add('me',q);
  const tag=document.createElement('div');tag.className='tag';tag.textContent='thinking…';$('msgs').appendChild(tag);
  const fd=new FormData();fd.append('question',q);fd.append('session','default');
  try{
    const r=await fetch('/api/ask',{method:'POST',body:fd}); const j=await r.json();
    tag.remove();
    if(j.error){add('bot','⚠️ '+j.error);}else{
      add('bot',j.answer);
      $('saved').textContent=j.cumulative_saved_pct+'%';
      $('turn').textContent=Math.round(j.turn_saved_pct)+'% · '+j.cached_tokens.toLocaleString()+' cached';
      $('cached').textContent=j.cached_total.toLocaleString();
      $('turns').textContent=j.turns;
    }
  }catch(e){tag.remove();add('bot','⚠️ '+e);}
  $('send').disabled=false;$('q').focus();
}
$('send').onclick=ask;$('q').addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
</script></body></html>"""
