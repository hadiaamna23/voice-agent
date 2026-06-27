import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select

from database.db import AsyncSessionLocal
from database.models import CallLog, Conversation

logger = logging.getLogger("backend.services.analytics_service")


class AnalyticsService:
    async def get_call_analytics(self, user_id: int) -> Dict[str, object]:
        async with AsyncSessionLocal() as session:
            total_calls = await session.scalar(select(func.count()).select_from(CallLog).where(CallLog.user_id == user_id))
            total_duration = await session.scalar(select(func.coalesce(func.sum(CallLog.duration_seconds), 0)).where(CallLog.user_id == user_id))
            average_duration = await session.scalar(select(func.coalesce(func.avg(CallLog.duration_seconds), 0)).where(CallLog.user_id == user_id))
            total_transcripts = await session.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id, Conversation.role == "user"))
            language_breakdown = await session.execute(
                select(Conversation.language, func.count()).where(Conversation.user_id == user_id).group_by(Conversation.language)
            )
            language_map = {row[0]: row[1] for row in language_breakdown.all()}
        logger.debug("Computed call analytics for user=%s", user_id)
        return {
            "total_calls": int(total_calls or 0),
            "total_duration_seconds": int(total_duration or 0),
            "average_call_duration_seconds": float(average_duration or 0.0),
            "total_messages": int(total_transcripts or 0),
            "language_breakdown": language_map,
        }

    async def get_live_metrics(self, user_id: int) -> Dict[str, object]:
        now = datetime.utcnow()
        window = now - timedelta(minutes=15)
        async with AsyncSessionLocal() as session:
            recent_count = await session.scalar(select(func.count()).select_from(CallLog).where(CallLog.user_id == user_id, CallLog.created_at >= window))
            recent_conversations = await session.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id, Conversation.created_at >= window))
        logger.debug("Computed live metrics for user=%s", user_id)
        return {
            "recent_call_count": int(recent_count or 0),
            "recent_message_count": int(recent_conversations or 0),
            "active_window_minutes": 15,
        }

    async def get_sentiment_tracking(self, user_id: int) -> Dict[str, int]:
        async with AsyncSessionLocal() as session:
            conversations = await session.execute(select(Conversation).where(Conversation.user_id == user_id, Conversation.role == "user"))
            transcripts = [row.content for row in conversations.scalars().all()]
        sentiment_counters = {"angry": 0, "happy": 0, "confused": 0, "neutral": 0}
        for text in transcripts:
            emotion = self._predict_sentiment(text)
            sentiment_counters[emotion] += 1
        return sentiment_counters

    async def get_transcript_insights(self, user_id: int, limit: int = 100) -> Dict[str, object]:
        async with AsyncSessionLocal() as session:
            query = select(Conversation).where(Conversation.user_id == user_id, Conversation.role == "user").order_by(Conversation.created_at.desc()).limit(limit)
            result = await session.execute(query)
            transcripts = [item.content for item in result.scalars().all()]
        insight = {
            "average_length": round(sum(len(text.split()) for text in transcripts) / max(1, len(transcripts)), 2),
            "top_keywords": self._extract_keywords(transcripts),
            "transcript_count": len(transcripts),
        }
        logger.debug("Computed transcript insights for user=%s", user_id)
        return insight

    def _predict_sentiment(self, text: str) -> str:
        lower_text = text.lower()
        if any(word in lower_text for word in ["angry", "frustrated", "upset"]):
            return "angry"
        if any(word in lower_text for word in ["happy", "excellent", "great"]):
            return "happy"
        if any(word in lower_text for word in ["confused", "unclear", "unsure"]):
            return "confused"
        return "neutral"

    def _extract_keywords(self, transcripts: List[str]) -> List[str]:
        keyword_map: Dict[str, int] = {}
        for transcript in transcripts:
            for token in transcript.lower().split():
                cleaned = token.strip(".,!?()[]\"'")
                if len(cleaned) < 4:
                    continue
                keyword_map[cleaned] = keyword_map.get(cleaned, 0) + 1
        sorted_keywords = sorted(keyword_map.items(), key=lambda item: item[1], reverse=True)
        return [keyword for keyword, _ in sorted_keywords[:10]]
