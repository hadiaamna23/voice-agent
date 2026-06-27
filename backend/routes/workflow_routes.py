from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from config import settings
from database import crud
from services.workflow_service import WorkflowService

router = APIRouter()
security = HTTPBearer()
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


class CreateWorkflowRequest(BaseModel):
    name: str
    trigger_type: str
    action_type: str
    config: Dict[str, Any]


class TriggerWorkflowRequest(BaseModel):
    trigger_type: str
    payload: Dict[str, Any]


@router.post("/api/workflows", response_model=Dict[str, Any])
async def create_workflow(request: CreateWorkflowRequest, user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    workflow = workflow_service.create_workflow(request.name, request.trigger_type, request.action_type, request.config)
    return workflow


@router.get("/api/workflows", response_model=List[Dict[str, Any]])
async def list_workflows(user: Any = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return workflow_service.list_workflows()


@router.get("/api/workflows/{workflow_id}", response_model=Dict[str, Any])
async def get_workflow(workflow_id: str, user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.post("/api/workflows/{workflow_id}/trigger", response_model=Dict[str, Any])
async def trigger_workflow(workflow_id: str, payload: Dict[str, Any], user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    result = workflow_service.execute_trigger(workflow["trigger_type"], payload)
    return {"workflow_id": workflow_id, "results": result}


@router.post("/api/workflows/trigger", response_model=Dict[str, Any])
async def trigger_generic_workflow(request: TriggerWorkflowRequest, user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    results = workflow_service.execute_trigger(request.trigger_type, request.payload)
    return {"trigger_type": request.trigger_type, "results": results}
