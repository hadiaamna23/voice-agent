from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from database import crud
from services.crm_service import CRMService
from services.workflow_service import WorkflowService

router = APIRouter()
security = HTTPBearer()
crm_service = CRMService()
workflow_service = WorkflowService()


def decode_access_token(token: str) -> Any:
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


@router.post("/api/webhooks/{provider}")
async def receive_webhook(provider: str, request: Request, user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    payload = await request.json()
    if provider.lower() == "crm":
        result = crm_service.save_lead_webhook(payload)
    elif provider.lower() == "workflow":
        result = workflow_service.execute_trigger(payload.get("trigger_type", ""), payload.get("payload", {}))
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook provider not supported")
    return {"provider": provider, "result": result}
