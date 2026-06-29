import os

_cfg: dict = {
    "api_key":  os.getenv("BREVITAS_API_KEY", ""),
    "base_url": os.getenv("BREVITAS_BASE_URL", "http://localhost:8000"),
    "enabled":  os.getenv("BREVITAS_ENABLED", "true").lower() != "false",
    # Shrink the prompt itself (lossless normalization always; LLMLingua-2 if the
    # [promptopt] extra is installed). This is what saves on SMALL/one-shot tasks
    # that the caching/retrieval levers (which need a large repeating prefix) skip.
    "optimize_prompts": os.getenv("BREVITAS_OPTIMIZE", "true").lower() != "false",
    "timeout":  30,
}


def configure(
    api_key: str = "",
    base_url: str = "",
    enabled: bool = True,
    optimize_prompts: bool = True,
    timeout: int = 30,
) -> None:
    if api_key:   _cfg["api_key"]  = api_key
    if base_url:  _cfg["base_url"] = base_url.rstrip("/")
    _cfg["enabled"] = enabled
    _cfg["optimize_prompts"] = optimize_prompts
    _cfg["timeout"] = timeout


def get() -> dict:
    return dict(_cfg)
