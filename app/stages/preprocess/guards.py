"""
Stage 1 security guards: regex fast-path + Llama Guard via Ollama.

Design: two-layer defense.
  Layer 1: compiled regex patterns catch well-known injection strings in < 1ms.
  Layer 2: Llama Guard (llama-guard3 via Ollama) classifies content safety.
           Degrades gracefully (fail-open) if Ollama is not reachable.

The combined check_safety() is called from preprocess_input().
"""
import re

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

# ── Regex injection patterns ──────────────────────────────────────────────────
_INJECTION_RE: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"forget\s+(everything|all|your\s+instructions?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"(act|pretend|roleplay)\s+as\s+", re.I),
    re.compile(r"\bsystem\s+prompt\b", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"reveal\s+(your|the)\s+(system\s+)?prompt", re.I),
    re.compile(r"disregard\s+(all|previous|your)\s+", re.I),
    re.compile(r"new\s+instruction[s]?\s*:", re.I),
]


def _check_regex(text: str) -> tuple[bool, str]:
    """Fast regex injection detection. Returns (is_safe, reason)."""
    for pattern in _INJECTION_RE:
        if pattern.search(text):
            return False, f"injection_pattern: {pattern.pattern}"
    return True, ""


# ── Llama Guard via Ollama ────────────────────────────────────────────────────
# Llama Guard 3 uses a specific prompt format: user turn only, assistant responds
# "safe" or "unsafe\n<category>".
_LLAMA_GUARD_PROMPT = (
    "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
    "{text}"
    "<|eot_id|><|start_header_id|>assistant<|end_header_id|>"
)


async def _check_llama_guard(text: str) -> tuple[bool, str]:
    """Call Llama Guard 3 via Ollama. Returns (is_safe, reason).

    Fails open (returns True) if Ollama is unreachable or the model is not
    pulled -- regex is the primary guard; Llama Guard is defense-in-depth.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ollama_host}/api/generate",
                json={
                    "model": "llama-guard3:8b",
                    "prompt": _LLAMA_GUARD_PROMPT.format(text=text),
                    "stream": False,
                },
            )
            resp.raise_for_status()
            response_text = resp.json().get("response", "").strip()
            if response_text.lower().startswith("unsafe"):
                category = response_text.split("\n")[1].strip() if "\n" in response_text else ""
                return False, f"llama_guard: {category}"
            return True, ""
    except Exception as exc:
        log.warning("guards.llama_guard.unavailable", error=str(exc))
        return True, ""   # fail open -- regex layer already caught injections


# ── Public API ────────────────────────────────────────────────────────────────

async def check_safety(text: str) -> tuple[bool, str]:
    """Combined safety check.

    1. Regex fast-path (sync, < 1ms).
    2. Llama Guard LLM check for messages longer than 20 chars (async, ~100ms).

    Returns (is_safe: bool, reason: str).
    """
    is_safe, reason = _check_regex(text)
    if not is_safe:
        log.warning("guards.injection_detected", reason=reason, text=text[:80])
        return False, reason

    if len(text) > 20:
        is_safe, reason = await _check_llama_guard(text)
        if not is_safe:
            log.warning("guards.llama_guard_flagged", reason=reason, text=text[:80])

    return is_safe, reason
