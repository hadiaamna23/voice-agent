import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import CallLog, Conversation
from services.llm_service import LLMService

logger = logging.getLogger("backend.services.summary_service")


class SummaryService:
    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self.llm_service = llm_service or LLMService()

    async def generate_call_summary(self, session_id: str, user_id: int) -> Dict[str, Any]:
        transcript = await self._load_transcript_text(session_id, user_id)
        call_description = await self._load_call_description(session_id, user_id)

        if not transcript and not call_description:
            logger.warning("No transcript or call log found for summary session=%s user=%s", session_id, user_id)
            return {
                "conversation_summary": "No transcript available.",
                "recommendations": [],
                "language": "en",
                "emotion": "neutral",
            }

        messages = self._build_summary_messages(session_id, transcript, call_description)
        summary_text = ""
        structured_output: Dict[str, Any] = {
            "conversation_summary": "",
            "recommendations": [],
            "language": "en",
            "emotion": "neutral",
        }

        async for chunk in self.llm_service.stream_chat_response(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            tone="professional",
            language="en",
        ):
            if chunk["type"] == "partial":
                summary_text += chunk.get("text", "")
            elif chunk["type"] == "complete":
                structured_output = chunk.get("structured", structured_output)
                summary_text += chunk.get("text", "")

        if not structured_output.get("conversation_summary"):
            structured_output["conversation_summary"] = self._fallback_summary(summary_text)

        logger.info("Generated AI summary for session=%s user=%s", session_id, user_id)
        return structured_output

    async def generate_auto_follow_up(self, session_id: str, user_id: int, transcript: str) -> str:
        messages = [
            {"role": "user", "content": "Read the transcript and suggest one clear next step for the agent and one follow-up email."},
            {"role": "assistant", "content": transcript},
        ]
        follow_up_text = ""

        async for chunk in self.llm_service.stream_chat_response(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            tone="friendly",
            language="en",
        ):
            if chunk["type"] == "partial":
                follow_up_text += chunk.get("text", "")
            elif chunk["type"] == "complete":
                follow_up_text += chunk.get("text", "")

        follow_up = follow_up_text.strip() or "Follow up with the customer based on the latest conversation."
        logger.info("Generated auto follow-up for session=%s user=%s", session_id, user_id)
        return follow_up

    async def _load_transcript_text(self, session_id: str, user_id: int) -> str:
        async with AsyncSessionLocal() as session:
            query = select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.session_id == session_id,
                Conversation.role == "user",
            ).order_by(Conversation.created_at)
            result = await session.execute(query)
            transcripts = [item.content for item in result.scalars().all()]
        return "\n".join(transcripts)

    async def _load_call_description(self, session_id: str, user_id: int) -> str:
        async with AsyncSessionLocal() as session:
            query = select(CallLog).where(CallLog.user_id == user_id, CallLog.session_id == session_id).order_by(CallLog.created_at.desc()).limit(1)
            result = await session.execute(query)
            call_record = result.scalars().first()
        if not call_record:
            return ""
        return f"Call with duration {call_record.duration_seconds}s and confidence {round(call_record.speech_confidence or 0, 2)}."

    def _build_summary_messages(self, session_id: str, transcript: str, call_description: str) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are a voice agent summarization service for an enterprise platform. "
                    "Produce a concise call summary, highlight sentiment, identify next best actions, and keep the output structured."
                ),
            },
            {
                "role": "user",
                "content": "Create a smart summary for the following call session.",
            },
        ]

        if call_description:
            messages.append({"role": "assistant", "content": call_description})

        if transcript:
            messages.append({"role": "assistant", "content": transcript})

        return messages

    def _fallback_summary(self, text: str) -> str:
        if not text:
            return "No summary could be generated from the available content."
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return " ".join(sentences[:2]).strip()
