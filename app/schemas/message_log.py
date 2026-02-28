from datetime import datetime

from pydantic import BaseModel

from app.models.message_log import MessageType


class MessageLogRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    from_phone: str
    to_phones: list[str]
    content: str
    msg_type: MessageType
    created_at: datetime


class MessageSendRequest(BaseModel):
    """Captain-initiated individual SMS."""
    to_phone: str
    content: str
    msg_type: MessageType = MessageType.system


class MessageBroadcastRequest(BaseModel):
    """Captain-initiated group SMS blast."""
    to_phones: list[str]
    content: str
    msg_type: MessageType = MessageType.blast
