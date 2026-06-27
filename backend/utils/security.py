import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_jwt_token(subject: str, expires_delta: Optional[timedelta] = None, extra: Optional[Dict[str, Any]] = None) -> str:
    expires_delta = expires_delta or timedelta(minutes=settings.jwt_expiration_minutes)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + expires_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_jwt_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as error:
        raise error

    if not payload.get("sub"):
        raise JWTError("JWT payload missing subject")
    return payload


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    if not authorization_header:
        return None
    if not authorization_header.lower().startswith("bearer "):
        return None
    return authorization_header.split(" ", 1)[1].strip()


def get_client_ip(scope: Dict[str, Any]) -> str:
    client = scope.get("client")
    if not client:
        return "unknown"
    return client[0]


def get_websocket_token(query_params: Dict[str, Any]) -> Optional[str]:
    token_values = query_params.get("token")
    if not token_values:
        return None
    if isinstance(token_values, list):
        return token_values[0]
    return token_values


def safe_compare(value_a: str, value_b: str) -> bool:
    return hmac.compare_digest(value_a, value_b)


def generate_api_key() -> str:
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
