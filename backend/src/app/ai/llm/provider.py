"""LLM provider: `anthropic` (live Claude) or `offline` (deterministic fallbacks). No model output is ever a price.

Every call uses structured outputs (`messages.parse(output_format=<Pydantic model>)`), so the response is
schema-validated before any code sees it. User-supplied text is passed as DATA inside a delimited block,
never concatenated into instructions. Any failure (timeout, rate limit, refusal, schema error) returns None
and the caller uses its deterministic fallback; the traveller path never waits on this module.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import TypeVar

from pydantic import BaseModel

from app.config import PROMPTS_DIR, get_settings

log = logging.getLogger("pixelminds.llm")
T = TypeVar("T", bound=BaseModel)

MODEL_FAST = os.environ.get("LLM_MODEL_FAST", "claude-haiku-4-5-20251001")   # A2 narration, A5 summaries
MODEL_SMART = os.environ.get("LLM_MODEL_SMART", "claude-sonnet-5")           # A3 extraction, A4 what-if parsing
MAX_CALLS_PER_MINUTE = 30

_client = None
_client_lock = threading.Lock()
_calls: deque[float] = deque()


def available() -> bool:
    return get_settings().llm_provider == "anthropic"


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            import anthropic

            _client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=1)
        return _client


def _allow_call() -> bool:
    now = time.monotonic()
    with _client_lock:
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
        if len(_calls) >= MAX_CALLS_PER_MINUTE:
            return False
        _calls.append(now)
        return True


def prompt(name: str) -> tuple[str, str]:
    """Load a versioned prompt file: returns (version, text)."""
    path = PROMPTS_DIR / f"{name}.v1.md"
    return "v1", path.read_text(encoding="utf-8")


def structured(model: str, system: str, user_data: str, schema: type[T], timeout_s: float, max_tokens: int = 1024) -> T | None:
    """One schema-constrained call. Returns a validated `schema` instance, or None on any failure."""
    if not available() or not _allow_call():
        return None
    import anthropic

    try:
        client = _get_client().with_options(timeout=timeout_s)
        response = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": f"<data>\n{user_data}\n</data>"}],
            output_format=schema,
        )
    except anthropic.RateLimitError:
        log.warning("llm rate limited")
        return None
    except anthropic.APITimeoutError:
        log.warning("llm timeout after %ss", timeout_s)
        return None
    except anthropic.APIStatusError as e:
        log.warning("llm status error %s", e.status_code)
        return None
    except anthropic.APIConnectionError:
        log.warning("llm connection error")
        return None
    except Exception:  # noqa: BLE001 - schema validation or SDK parsing errors: fall back, never crash
        log.exception("llm structured output failed")
        return None
    if response.stop_reason == "refusal":
        log.warning("llm refused")
        return None
    return response.parsed_output
