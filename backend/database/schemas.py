from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    tenant_id: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    tenant_id: str
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ConversationCreate(BaseModel):
    session_id: str
    role: str = Field(..., regex="^(user|assistant)$")
    content: str
    language: str = Field("en", min_length=2, max_length=10)


class ConversationRead(BaseModel):
    session_id: str
    role: str
    content: str
    language: str
    created_at: datetime

    class Config:
        orm_mode = True


class CallLogCreate(BaseModel):
    session_id: str
    duration_seconds: float = Field(..., ge=0)
    transcript: str


class CallLogRead(BaseModel):
    id: int
    session_id: str
    duration_seconds: float
    transcript: str
    created_at: datetime

    class Config:
        orm_mode = True


class HealthResponse(BaseModel):
    status: str
    environment: str
