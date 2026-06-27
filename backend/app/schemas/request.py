from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class TokenRequest(BaseModel):
    email: EmailStr
    password: str


class StreamMessage(BaseModel):
    session_id: str
    message: str
    language: str = Field("en", min_length=2, max_length=10)
    metadata: Optional[Dict[str, Any]] = None


class TranscribeRequest(BaseModel):
    language: str = Field("en", min_length=2, max_length=10)


class SynthesizeRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    language: str = Field("en", min_length=2, max_length=10)


class ConversationHistoryRequest(BaseModel):
    session_id: Optional[str]
    limit: int = Field(25, gt=0, le=100)


class CallLogCreateRequest(BaseModel):
    session_id: str
    language: str = Field("en", min_length=2, max_length=10)
    duration_seconds: float = Field(..., ge=0)
    transcript: str
    sentiment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowTriggerRequest(BaseModel):
    trigger_type: str
    payload: Dict[str, Any]


class CrmLeadRequest(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
