import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from websocket_manager import WebSocketManager
from services.notification_service import NotificationService
from services.summary_service import SummaryService

logger = logging.getLogger("backend.services.live_stream_service")


class LiveStreamService:
    def __init__(
        self,
        websocket_manager: Optional[WebSocketManager] = None,
        notification_service: Optional[NotificationService] = None,
        summary_service: Optional[SummaryService] = None,
    ) -> None:
        self.websocket_manager = websocket_manager or WebSocketManager()
        self.notification_service = notification_service or NotificationService()
        self.summary_service = summary_service or SummaryService()
        self.typing_sessions: Dict[str, bool] = {}
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: Any, user_payload: Dict[str, Any]) -> None:
        await self.websocket_manager.connect(session_id, websocket)
        await self.broadcast_event(session_id, "participant.connected", {"user": user_payload.get("sub"), "timestamp": self._now()})
        logger.info("Connected websocket session=%s user=%s", session_id, user_payload.get("sub"))

    async def disconnect(self, session_id: str, websocket: Any) -> None:
        await self.websocket_manager.disconnect(session_id, websocket)
        await self.broadcast_event(session_id, "participant.disconnected", {"timestamp": self._now()})
        logger.info("Disconnected websocket session=%s", session_id)

    async def send_typing_indicator(self, session_id: str, active: bool = True) -> None:
        async with self.lock:
            self.typing_sessions[session_id] = active
        await self.websocket_manager.send_message(session_id, {"type": "typing_indicator", "active": active, "timestamp": self._now()})
        logger.debug("Typing indicator session=%s active=%s", session_id, active)

    async def stream_transcript_chunk(self, session_id: str, chunk: str, user_id: int, source: str = "voice") -> None:
        event_payload = {
            "type": "transcript_chunk",
            "source": source,
            "chunk": chunk,
            "timestamp": self._now(),
        }
        await self.websocket_manager.send_message(session_id, event_payload)
        logger.debug("Streamed transcript chunk session=%s size=%s", session_id, len(chunk))

        if len(chunk) > 64:
            await self.notification_service.create_smart_notification(
                user_id=user_id,
                transcript=chunk,
                event_type="realtime_transcript",
                metadata={"session_id": session_id, "source": source},
            )

    async def publish_realtime_event(self, session_id: str, event_name: str, data: Dict[str, Any]) -> None:
        payload = {"type": event_name, "data": data, "timestamp": self._now()}
        await self.websocket_manager.send_message(session_id, payload)
        logger.info("Realtime event published session=%s event=%s", session_id, event_name)

    async def broadcast_event(self, session_id: str, event_name: str, data: Dict[str, Any]) -> None:
        payload = {"type": event_name, "data": data, "timestamp": self._now()}
        await self.websocket_manager.send_message(session_id, payload)

    async def finalize_session(self, session_id: str, user_id: int) -> Dict[str, Any]:
        summary = await self.summary_service.generate_call_summary(session_id, user_id)
        await self.websocket_manager.send_message(session_id, {"type": "session_summary", "summary": summary, "timestamp": self._now()})
        await self.notification_service.dispatch_notification(
            user_id=user_id,
            event_type="session.summary",
            payload={"session_id": session_id, "summary": summary},
            channel="email",
        )
        logger.info("Finalized session %s with AI summary", session_id)
        return summary

    async def auto_follow_up(self, session_id: str, user_id: int, instructions: str, delay_seconds: int = 300) -> None:
        await self.notification_service.schedule_follow_up(
            user_id=user_id,
            event_type="auto_follow_up",
            payload={"session_id": session_id, "instructions": instructions},
            delay_seconds=delay_seconds,
            channel="email",
        )
        logger.info("Scheduled auto follow-up session=%s delay=%s", session_id, delay_seconds)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
