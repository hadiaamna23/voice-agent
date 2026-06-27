from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatResponse(BaseModel):
    session_id: str
    message: str
    language: str
    timestamp: datetime


class TranscriptionResponse(BaseModel):
    transcript: str
    language: str
    duration_seconds: Optional[float]


class TtsResponse(BaseModel):
    audio_url: str
    voice_id: str
    language: str


class CallLogResponse(BaseModel):
    id: int
    session_id: str
    language: str
    duration_seconds: float
    transcript: str
    sentiment: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    total_calls: int
    total_messages: int
    average_call_duration: float
    languages: Dict[str, int]
    workflows_executed: int


class LeadResponse(BaseModel):
    external_id: str
    status: str


class SimpleResponse(BaseModel):
    detail: str
