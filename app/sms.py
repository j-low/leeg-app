"""
Twilio SMS utilities: outbound sending and inbound signature validation.

Outbound functions are no-ops when TWILIO_ACCOUNT_SID is not configured,
so local development works without a real Twilio account.
"""
import structlog
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import settings

log = structlog.get_logger(__name__)


def _client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_sms(to: str, body: str) -> str | None:
    """Send an SMS to a single number. Returns the Twilio message SID, or None
    if Twilio is not configured (local dev)."""
    if not settings.twilio_account_sid:
        log.info("sms.send.skipped", to=to, reason="TWILIO_ACCOUNT_SID not set")
        return None
    msg = _client().messages.create(
        body=body,
        from_=settings.twilio_phone_number,
        to=to,
    )
    log.info("sms.sent", sid=msg.sid, to=to)
    return msg.sid


def send_group_sms(to_phones: list[str], body: str) -> list[str]:
    """Broadcast the same SMS to multiple numbers. Returns list of SIDs."""
    return [sid for to in to_phones if (sid := send_sms(to, body)) is not None]


def validate_twilio_signature(signature: str, url: str, params: dict) -> bool:
    """Return True if the request genuinely came from Twilio.

    Pass the full request URL (with https scheme) and the raw form-encoded
    params dict.  The validator computes HMAC-SHA1 over the sorted params
    and compares against the X-Twilio-Signature header.
    """
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, params, signature)
