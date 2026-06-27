from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, CallLog, Conversation, Workflow
from app.db.session import AsyncSessionLocal


class AnalyticsService:
    async def get_summary(self, user_id: int) -> dict:
        async with AsyncSessionLocal() as session:
            total_calls = await session.scalar(select(func.count()).select_from(CallLog).where(CallLog.user_id == user_id))
            total_messages = await session.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id))
            average_duration = await session.scalar(select(func.coalesce(func.avg(CallLog.duration_seconds), 0.0)).where(CallLog.user_id == user_id))
            languages = await session.execute(
                select(CallLog.language, func.count()).where(CallLog.user_id == user_id).group_by(CallLog.language)
            )
            workflow_count = await session.scalar(select(func.count()).select_from(Workflow).where(Workflow.user_id == user_id, Workflow.active == True))
            language_map = {row[0]: row[1] for row in languages.all()}

        return {
            "total_calls": int(total_calls or 0),
            "total_messages": int(total_messages or 0),
            "average_call_duration": float(average_duration or 0.0),
            "languages": language_map,
            "workflows_executed": int(workflow_count or 0),
        }

    async def record_event(self, user_id: int, event_type: str, metadata: dict | None = None) -> None:
        async with AsyncSessionLocal() as session:
            session.add(AnalyticsEvent(user_id=user_id, event_type=event_type, metadata=metadata or {}))
            await session.commit()
