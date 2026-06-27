from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import CallLog, Conversation, User
from app.db.session import AsyncSessionLocal
from app.services.ai_agent import AIAgentService
from app.services.analytics import AnalyticsService
from app.services.crm import CRMService
from app.services.speech import SpeechService
from app.services.tts import TTSService
from app.services.workflows import WorkflowService
from app.schemas.request import (
    CallLogCreateRequest,
    CrmLeadRequest,
    SynthesizeRequest,
    StreamMessage,
    TokenRequest,
)
from app.schemas.response import (
    AnalyticsSummaryResponse,
    CallLogResponse,
    ChatResponse,
    LeadResponse,
    SimpleResponse,
    TtsResponse,
    TokenResponse,
)
from app.utils.security import hash_password, verify_password
from app.utils.token import create_access_token, decode_access_token

router = APIRouter()
security = HTTPBearer()
ai_agent = AIAgentService()
analytics_service = AnalyticsService()
crm_service = CRMService()
workflow_service = WorkflowService()
speech_service = SpeechService()
tts_service = TTSService()


async def get_user_by_email(email: str, session: AsyncSession) -> Optional[User]:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = credentials.credentials
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(subject, session)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user


@router.post("/auth/register", response_model=TokenResponse)
async def register(request: TokenRequest) -> TokenResponse:
    async with AsyncSessionLocal() as session:
        existing = await get_user_by_email(request.email, session)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        user = User(
            email=request.email,
            hashed_password=hash_password(request.password),
            tenant_id=f"tenant_{request.email.split('@')[0]}",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(subject=user.email)
        return TokenResponse(access_token=token)


@router.post("/auth/token", response_model=TokenResponse)
async def login(request: TokenRequest) -> TokenResponse:
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(request.email, session)
        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token(subject=user.email)
        return TokenResponse(access_token=token)


@router.post("/voice/transcribe", response_model=ChatResponse)
async def transcribe_voice(language: str = Query("en"), audio_file: UploadFile = File(...), current_user: User = Depends(get_current_user)) -> ChatResponse:
    audio_bytes = await audio_file.read()
    transcription = await speech_service.transcribe_audio(audio_bytes, language=language, mime_type=audio_file.content_type)
    response = await ai_agent.create_chat_response(
        current_user.id,
        session_id=f"voice-{datetime.utcnow().timestamp()}",
        user_message=transcription["transcript"],
        language=language,
    )
    return ChatResponse(**response)


@router.post("/voice/synthesize", response_model=TtsResponse)
async def synthesize(tts_request: SynthesizeRequest, current_user: User = Depends(get_current_user)) -> TtsResponse:
    audio = await tts_service.synthesize_text(
        text=tts_request.text,
        voice_id=tts_request.voice_id or settings.default_voice_id,
        language=tts_request.language,
    )
    await analytics_service.record_event(current_user.id, "tts_generated", {"language": tts_request.language})
    return TtsResponse(**audio)


@router.websocket("/ws/conversation")
async def conversation_stream(websocket: WebSocket, token: str = Query(...), session_id: str = Query(...), language: str = Query("en")) -> None:
    await websocket.accept()
    subject = decode_access_token(token)
    if not subject:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(subject, session)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            while True:
                payload = await websocket.receive_json()
                message = payload.get("message")
                if not message:
                    await websocket.send_json({"error": "Message field is required."})
                    continue
                response = await ai_agent.create_chat_response(user.id, session_id, message, language)
                await websocket.send_json(response)
        except Exception:
            await websocket.close()


@router.get("/conversations/history", response_model=list[ChatResponse])
async def conversation_history(session_id: Optional[str] = Query(None), limit: int = Query(25, gt=0, le=100), current_user: User = Depends(get_current_user)) -> list[ChatResponse]:
    async with AsyncSessionLocal() as session:
        query = select(Conversation).where(Conversation.user_id == current_user.id)
        if session_id:
            query = query.where(Conversation.session_id == session_id)
        query = query.order_by(Conversation.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return [
            ChatResponse(
                session_id=row.session_id,
                message=row.content,
                language=row.language,
                timestamp=row.created_at,
            )
            for row in result.scalars().all()
        ]


@router.get("/call_logs", response_model=list[CallLogResponse])
async def list_call_logs(current_user: User = Depends(get_current_user)) -> list[CallLogResponse]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CallLog).where(CallLog.user_id == current_user.id).order_by(CallLog.created_at.desc()).limit(100))
        return [
            CallLogResponse(
                id=row.id,
                session_id=row.metadata.get("session_id", ""),
                language=row.language,
                duration_seconds=row.duration_seconds,
                transcript=row.transcript,
                sentiment=row.sentiment,
                metadata=row.metadata,
                created_at=row.created_at,
            )
            for row in result.scalars().all()
        ]


@router.post("/call_logs", response_model=CallLogResponse)
async def create_call_log(request: CallLogCreateRequest, current_user: User = Depends(get_current_user)) -> CallLogResponse:
    async with AsyncSessionLocal() as session:
        conversation = await session.execute(
            select(Conversation).where(Conversation.user_id == current_user.id, Conversation.session_id == request.session_id)
        )
        conversation_obj = conversation.scalar_one_or_none()
        call_log = CallLog(
            user_id=current_user.id,
            conversation_id=conversation_obj.id if conversation_obj else None,
            language=request.language,
            duration_seconds=request.duration_seconds,
            transcript=request.transcript,
            sentiment=request.sentiment,
            metadata={**(request.metadata or {}), "session_id": request.session_id},
        )
        session.add(call_log)
        await session.commit()
        await analytics_service.record_event(current_user.id, "call_log_created", {"session_id": request.session_id})
        await workflow_service.execute_trigger(current_user.id, "call_completed", request.metadata or {})
        return CallLogResponse(
            id=call_log.id,
            session_id=request.session_id,
            language=call_log.language,
            duration_seconds=call_log.duration_seconds,
            transcript=call_log.transcript,
            sentiment=call_log.sentiment,
            metadata=call_log.metadata,
            created_at=call_log.created_at,
        )


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(current_user: User = Depends(get_current_user)) -> AnalyticsSummaryResponse:
    summary = await analytics_service.get_summary(current_user.id)
    return AnalyticsSummaryResponse(**summary)


@router.post("/crm/lead", response_model=LeadResponse)
async def create_crm_lead(request: CrmLeadRequest, current_user: User = Depends(get_current_user)) -> LeadResponse:
    result = await crm_service.create_lead(
        user_id=current_user.id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        company=request.company,
        metadata=request.metadata,
    )
    return LeadResponse(**result)


@router.post("/workflows/trigger", response_model=SimpleResponse)
async def trigger_workflow(request: dict, current_user: User = Depends(get_current_user)) -> SimpleResponse:
    trigger_type = request.get("trigger_type")
    payload = request.get("payload", {})
    if not trigger_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="trigger_type is required")
    await workflow_service.execute_trigger(current_user.id, trigger_type, payload)
    return SimpleResponse(detail="Workflow executed")
