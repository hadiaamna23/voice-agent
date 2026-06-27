from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config import settings
from database import crud
from services.call_service import CallService

router = APIRouter()
security = HTTPBearer()
call_service = CallService()


def decode_access_token(token: str) -> Optional[str]:
    from jose import JWTError, jwt

    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return str(data.get("sub"))
    except JWTError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Any:
    token = credentials.credentials
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await crud.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


class CallInitiateRequest(BaseModel):
    target: str
    metadata: Optional[Dict[str, Any]] = None


class CallRetryRequest(BaseModel):
    delay_seconds: int = 60
    max_retries: int = 3


class CallResponse(BaseModel):
    call_id: str
    direction: str
    status: str
    target: Optional[str]
    created_at: str
    last_updated: str
    metadata: Dict[str, Any]

    class Config:
        orm_mode = True


@router.post("/api/calls/inbound", response_model=CallResponse)
async def inbound_call(request: CallInitiateRequest, user: Any = Depends(get_current_user)) -> CallResponse:
    record = await call_service.initiate_inbound_call(request.target, request.metadata)
    return CallResponse(**record.to_dict())


@router.post("/api/calls/outbound", response_model=CallResponse)
async def outbound_call(request: CallInitiateRequest, user: Any = Depends(get_current_user)) -> CallResponse:
    record = await call_service.initiate_outbound_call(request.target, request.metadata)
    return CallResponse(**record.to_dict())


@router.post("/api/calls/{call_id}/complete", response_model=CallResponse)
async def complete_call(call_id: str, audio_file: UploadFile = File(...), user: Any = Depends(get_current_user)) -> CallResponse:
    file_bytes = await audio_file.read()
    record = await call_service.complete_call(call_id, audio_bytes=file_bytes, content_type=audio_file.content_type)
    return CallResponse(**record.to_dict())


@router.post("/api/calls/{call_id}/retry", response_model=Dict[str, Any])
async def retry_call(call_id: str, request: CallRetryRequest, user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    await call_service.retry_call(call_id, delay_seconds=request.delay_seconds, max_retries=request.max_retries)
    return {"status": "retry_scheduled", "call_id": call_id}


@router.get("/api/calls/{call_id}", response_model=CallResponse)
async def get_call(call_id: str, user: Any = Depends(get_current_user)) -> CallResponse:
    record = call_service.state.get(call_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    return CallResponse(**record.to_dict())


@router.get("/api/calls", response_model=List[CallResponse])
async def list_calls(user: Any = Depends(get_current_user)) -> List[CallResponse]:
    return [CallResponse(**record.to_dict()) for record in call_service.state.values()]
