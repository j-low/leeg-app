"""
Twilio inbound SMS webhook.

Twilio POSTs form-encoded data to POST /sms/webhook whenever a text is
received on our Twilio number.  We must respond within 5 seconds, so we
immediately queue a Celery task and return an empty TwiML response.

Signature validation is enforced when TWILIO_AUTH_TOKEN is set.
Skip it in local dev (empty TWILIO_AUTH_TOKEN) to allow curl testing.
"""
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.sms import validate_twilio_signature
from app.tasks import process_inbound_sms

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/sms", tags=["sms"])

# Minimal TwiML that tells Twilio: message received, send nothing back.
_TWIML_ACK = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/webhook", response_class=PlainTextResponse)
async def inbound_webhook(request: Request) -> str:
    """Receive inbound SMS from Twilio, validate signature, queue pipeline task."""
    form = await request.form()
    from_phone: str = form.get("From", "")
    body: str = form.get("Body", "")

    log.info("sms.webhook.received", from_phone=from_phone, body=body)

    # Validate Twilio signature when credentials are configured.
    # In local dev (TWILIO_AUTH_TOKEN=""), skip validation so curl works.
    if settings.twilio_auth_token:
        signature = request.headers.get("x-twilio-signature", "")
        if not validate_twilio_signature(signature, str(request.url), dict(form)):
            log.warning("sms.webhook.invalid_signature", from_phone=from_phone)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio signature",
            )

    if not from_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing From field",
        )

    # Dispatch to Celery -- non-blocking, returns immediately
    process_inbound_sms.delay(from_phone=from_phone, body=body)

    return _TWIML_ACK
