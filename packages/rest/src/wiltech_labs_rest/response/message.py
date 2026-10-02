from enum import Enum

from pydantic import BaseModel


class MessageType(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class Message(BaseModel):
    """One entry in `_messages`: something useful to tell the client or user."""
    type: MessageType
    value: str
