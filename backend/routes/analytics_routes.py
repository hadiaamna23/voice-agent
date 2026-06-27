from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from database import crud
from services.analytics_service import AnalyticsService

router = APIRouter()
security = HTTPBearer()
analytics_service = AnalyticsService()


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


@router.get("/api/analytics/summary", response_model=Dict[str, Any])
async def analytics_summary(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return await analytics_service.get_call_analytics(user.id)


@router.get("/api/analytics/live", response_model=Dict[str, Any])
async def analytics_live(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return await analytics_service.get_live_metrics(user.id)


@router.get("/api/analytics/sentiment", response_model=Dict[str, Any])
async def analytics_sentiment(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return await analytics_service.get_sentiment_tracking(user.id)


@router.get("/api/analytics/transcripts", response_model=Dict[str, Any])
async def transcript_insights(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return await analytics_service.get_transcript_insights(user.id)
