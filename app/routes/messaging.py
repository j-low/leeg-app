"""
Captain-initiated outbound messaging endpoints.

All endpoints require JWT captain auth.  They send SMS (if Twilio is
configured) and persist a MessageLog record regardless, so the audit trail
is always populated even in local dev without real Twilio credentials.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.message_log import MessageLog, MessageType
from app.models.player import Player
from app.models.survey import SurveyResponse
from app.models.user import User
from app.schemas import (
    MessageBroadcastRequest,
    MessageLogRead,
    MessageSendRequest,
    SurveyBlastRequest,
)
from app.sms import send_group_sms, send_sms

router = APIRouter(prefix="/api/messages", tags=["messaging"])


def _from_phone(captain: User) -> str:
    """Prefer captain's own phone; fall back to Twilio sender number."""
    from app.config import settings
    return captain.phone or settings.twilio_phone_number or "unknown"


@router.post("/send", response_model=MessageLogRead, status_code=status.HTTP_201_CREATED)
async def send_message(
    body: MessageSendRequest,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Send a single SMS to one player and log it."""
    send_sms(to=body.to_phone, body=body.content)

    log = MessageLog(
        from_phone=_from_phone(captain),
        to_phones=[body.to_phone],
        content=body.content,
        msg_type=body.msg_type,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.post("/broadcast", response_model=MessageLogRead, status_code=status.HTTP_201_CREATED)
async def broadcast(
    body: MessageBroadcastRequest,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Broadcast an SMS to a list of phone numbers and log it."""
    send_group_sms(to_phones=body.to_phones, body=body.content)

    log = MessageLog(
        from_phone=_from_phone(captain),
        to_phones=body.to_phones,
        content=body.content,
        msg_type=body.msg_type,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.post("/survey", status_code=status.HTTP_201_CREATED)
async def survey_blast(
    body: SurveyBlastRequest,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Send a survey question to players and create SurveyResponse placeholders.

    Each player gets an SMS with the question.  A SurveyResponse row is
    created for each player (answer=None) so the pipeline can later match
    their inbound reply to the correct survey_id.
    """
    # Resolve target players
    stmt = select(Player).where(Player.team_id == body.team_id)
    if body.player_ids:
        stmt = stmt.where(Player.id.in_(body.player_ids))
    result = await db.execute(stmt)
    players = result.scalars().all()

    survey_id = str(uuid.uuid4())
    phones = [p.phone for p in players]

    # Create placeholder response rows (answer filled later via inbound SMS)
    for player in players:
        db.add(SurveyResponse(
            survey_id=survey_id,
            player_id=player.id,
            question=body.question,
            answer=None,
            scope=body.scope,
        ))

    # Send the question to each player
    send_group_sms(to_phones=phones, body=body.question)

    # Audit log
    db.add(MessageLog(
        from_phone=_from_phone(captain),
        to_phones=phones,
        content=body.question,
        msg_type=MessageType.survey,
    ))

    await db.commit()
    return {"survey_id": survey_id, "sent_to": len(players)}
