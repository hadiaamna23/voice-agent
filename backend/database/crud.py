from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from db import AsyncSessionLocal
from models import CallLog, Conversation, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


async def get_user_by_email(email: str) -> Optional[User]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def create_user(email: str, password: str, tenant_id: str) -> User:
    async with AsyncSessionLocal() as session:
        user = User(email=email, hashed_password=hash_password(password), tenant_id=tenant_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def create_conversation(session_id: str, user_id: int, role: str, content: str, language: str) -> Conversation:
    async with AsyncSessionLocal() as session:
        conversation = Conversation(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            language=language,
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return conversation


async def list_conversations(user_id: int, session_id: Optional[str] = None, limit: int = 50) -> List[Conversation]:
    async with AsyncSessionLocal() as session:
        query = select(Conversation).where(Conversation.user_id == user_id)
        if session_id:
            query = query.where(Conversation.session_id == session_id)
        query = query.order_by(Conversation.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return result.scalars().all()


async def create_call_log(user_id: int, session_id: str, duration_seconds: float, transcript: str) -> CallLog:
    async with AsyncSessionLocal() as session:
        call_log = CallLog(user_id=user_id, session_id=session_id, duration_seconds=int(duration_seconds), transcript=transcript)
        session.add(call_log)
        await session.commit()
        await session.refresh(call_log)
        return call_log
