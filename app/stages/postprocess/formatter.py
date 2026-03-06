"""
Stage 4: Channel-specific response formatting.

Handles SMS length constraints and encoding normalization, plus structured
payload assembly for the dashboard channel.

SMS limits:
  - 160 chars: single segment (no carrier segmentation, no extra cost)
  - 1600 chars: Twilio's multi-part SMS maximum (10 segments × 160)

GSM-7 encoding:
  Many Unicode characters (curly quotes, em-dashes, ellipsis, etc.) force
  Twilio to switch from GSM-7 to UCS-2 encoding, which halves the effective
  character limit per segment (from 160 to 70 chars). _normalize_encoding()
  replaces the most common offenders with ASCII equivalents.
"""
import textwrap

SMS_SOFT_LIMIT: int = 160   # target: single SMS segment, no segmentation cost
SMS_HARD_LIMIT: int = 1600  # Twilio absolute maximum for multi-part SMS

# Mapping of common non-GSM-7 chars → ASCII equivalents
_GSM7_REPLACEMENTS: dict[str, str] = {
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark
    "\u201c": '"',   # left double quotation mark
    "\u201d": '"',   # right double quotation mark
    "\u2013": "-",   # en-dash
    "\u2014": "-",   # em-dash
    "\u2026": "...", # horizontal ellipsis
    "\u00a0": " ",   # non-breaking space
    "\u2022": "*",   # bullet
}


# ── Public API ────────────────────────────────────────────────────────────────

def format_for_sms(text: str) -> tuple[str, bool]:
    """Format text for SMS delivery.

    Steps:
    1. Normalize non-GSM-7 characters to ASCII equivalents.
    2. If within SMS_SOFT_LIMIT (160), return as-is.
    3. If within SMS_HARD_LIMIT (1600), return as-is with was_truncated=False
       (multi-part SMS, slightly higher cost but allowed).
    4. If over SMS_HARD_LIMIT, truncate to 157 chars + "..." (hard Twilio limit).

    Args:
        text: The PII-redacted text to format.

    Returns:
        (formatted_text, was_truncated)
    """
    text = _normalize_encoding(text)

    if len(text) <= SMS_HARD_LIMIT:
        return text, False

    # Truncate to hard limit — use textwrap.shorten to avoid mid-word cuts
    truncated = textwrap.shorten(text, width=SMS_HARD_LIMIT - 3, placeholder="...")
    return truncated, True


def format_for_dashboard(text: str, raw_output: dict) -> tuple[str, dict]:
    """Format text for dashboard delivery.

    No length restriction on the dashboard channel. Returns both the text
    and a structured payload containing the Stage 3 agent metadata for the
    dashboard UI to display (tool call indicators, iteration count, etc.).

    Args:
        text:       The PII-redacted text to display.
        raw_output: The raw dict from run_agent() — used to populate payload.

    Returns:
        (text, dashboard_payload)
        dashboard_payload: {
            "answer":      str,
            "tool_calls":  list[dict],  # [{name, input, result|error}, ...]
            "iterations":  int,
            "stop_reason": str,
        }
    """
    dashboard_payload = {
        "answer":      text,
        "tool_calls":  raw_output.get("tool_calls", []),
        "iterations":  raw_output.get("iterations", 0),
        "stop_reason": raw_output.get("stop_reason", ""),
    }
    return text, dashboard_payload


# ── Private helpers ───────────────────────────────────────────────────────────

def _normalize_encoding(text: str) -> str:
    """Replace common non-GSM-7 Unicode characters with ASCII equivalents.

    Prevents Twilio from switching to UCS-2 encoding (which halves the
    effective chars-per-segment from 160 to 70).
    """
    for char, replacement in _GSM7_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text
