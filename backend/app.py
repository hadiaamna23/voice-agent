import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings
from database import crud
from database.db import init_db
from database.schemas import (
    CallLogCreate,
    CallLogRead,
    ConversationCreate,
    ConversationRead,
    HealthResponse,
    TokenResponse,
    UserCreate,
)
from backend.utils.logger import configure_logging, logger
from backend.websocket_manager import WebSocketManager

app = FastAPI(
    title="AI Voice Agent Platform",
    description="Production-ready FastAPI backend with websocket support for voice agents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
ws_manager = WebSocketManager()


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.jwt_expiration_minutes))
    payload = {"sub": subject, "exp": expire, "iat": datetime.utcnow()}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return str(data.get("sub"))
    except JWTError:
        return None


class MessagePayload(BaseModel):
    session_id: str
    message: str
    language: Optional[str] = "en"


@app.on_event("startup")
async def startup_event() -> None:
    configure_logging()
    logger.info("Starting backend application")
    await init_db()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Any:
    token = credentials.credentials
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await crud.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.environment)


@app.post("/api/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate) -> TokenResponse:
    existing_user = await crud.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    tenant_id = user_data.tenant_id or f"tenant_{user_data.email.split('@')[0]}"
    user = await crud.create_user(user_data.email, user_data.password, tenant_id)
    access_token = create_access_token(subject=user.email)
    return TokenResponse(access_token=access_token)


@app.post("/api/auth/token", response_model=TokenResponse)
async def login(user_data: UserCreate) -> TokenResponse:
    user = await crud.get_user_by_email(user_data.email)
    if not user or not crud.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(subject=user.email)
    return TokenResponse(access_token=access_token)


@app.post("/api/conversations", response_model=ConversationRead)
async def create_conversation(conversation: ConversationCreate, user: Any = Depends(get_current_user)) -> ConversationRead:
    created = await crud.create_conversation(
        session_id=conversation.session_id,
        user_id=user.id,
        role=conversation.role,
        content=conversation.content,
        language=conversation.language,
    )
    return ConversationRead.from_orm(created)


@app.get("/api/conversations/history", response_model=list[ConversationRead])
async def history(session_id: Optional[str] = None, limit: int = 25, user: Any = Depends(get_current_user)) -> list[ConversationRead]:
    conversations = await crud.list_conversations(user.id, session_id=session_id, limit=limit)
    return [ConversationRead.from_orm(item) for item in conversations]


@app.post("/api/call_logs", response_model=CallLogRead)
async def add_call_log(call_log: CallLogCreate, user: Any = Depends(get_current_user)) -> CallLogRead:
    created = await crud.create_call_log(
        user_id=user.id,
        session_id=call_log.session_id,
        duration_seconds=call_log.duration_seconds,
        transcript=call_log.transcript,
    )
    return CallLogRead.from_orm(created)


@app.websocket("/api/ws/conversation")
async def websocket_conversation(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    session_id = websocket.query_params.get("session_id")
    if not token or not session_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    email = decode_access_token(token)
    if not email:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await crud.get_user_by_email(email)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(session_id, websocket)
    logger.info("WebSocket connected session=%s user=%s", session_id, user.email)
    try:
        while True:
            payload = await websocket.receive_text()
            data = json.loads(payload)
            message = MessagePayload(**data)
            await crud.create_conversation(
                session_id=message.session_id,
                user_id=user.id,
                role="user",
                content=message.message,
                language=message.language or "en",
            )
            response = {
                "session_id": message.session_id,
                "message": f"Received message at {datetime.utcnow().isoformat()}.",
                "language": message.language,
            }
            await ws_manager.send_message(session_id, response)
    except WebSocketDisconnect:
        await ws_manager.disconnect(session_id, websocket)
        logger.info("WebSocket disconnected session=%s user=%s", session_id, user.email)
    except Exception as error:
        logger.exception("WebSocket error for session %s: %s", session_id, error)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
