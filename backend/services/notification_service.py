import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("backend.services.notification_service")

NotificationHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class NotificationService:
    def __init__(self, default_channel: str = "email") -> None:
        self.default_channel = default_channel
        self.senders: Dict[str, NotificationHandler] = {}
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()

    def register_sender(self, channel: str, handler: NotificationHandler) -> None:
        self.senders[channel] = handler
        logger.info("Registered notification sender for channel=%s", channel)

    async def dispatch_notification(
        self,
        user_id: int,
        event_type: str,
        payload: Dict[str, Any],
        channel: Optional[str] = None,
        priority: str = "normal",
    ) -> None:
        channel = channel or self.default_channel
        notification = self._build_payload(user_id, event_type, payload, priority)
        await self._deliver(channel, notification)

    async def schedule_follow_up(
        self,
        user_id: int,
        event_type: str,
        payload: Dict[str, Any],
        delay_seconds: int = 300,
        channel: Optional[str] = None,
    ) -> None:
        schedule_key = f"followup:{user_id}:{event_type}:{int(datetime.utcnow().timestamp())}"
        channel = channel or self.default_channel

        async def _task() -> None:
            try:
                await asyncio.sleep(delay_seconds)
                await self.dispatch_notification(user_id, event_type, payload, channel, priority="low")
            except asyncio.CancelledError:
                logger.warning("Cancelled scheduled follow-up %s", schedule_key)
            except Exception as exc:
                logger.exception("Error running scheduled follow-up %s: %s", schedule_key, exc)

        task = asyncio.create_task(_task())
        async with self.lock:
            self.scheduled_tasks[schedule_key] = task
        logger.info("Scheduled follow-up %s delay=%ss channel=%s", schedule_key, delay_seconds, channel)

    async def create_smart_notification(
        self,
        user_id: int,
        transcript: str,
        event_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        channel: Optional[str] = None,
    ) -> None:
        metadata = metadata or {}
        channel = channel or self._select_channel(transcript)
        payload = {
            "event_type": event_type,
            "summary": self._summarize_transcript(transcript),
            "severity": self._build_severity_score(transcript),
            "metadata": metadata,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self.dispatch_notification(user_id, event_type, payload, channel)

    async def revoke_scheduled(self, schedule_key: str) -> None:
        async with self.lock:
            task = self.scheduled_tasks.pop(schedule_key, None)
        if task and not task.done():
            task.cancel()

    async def _deliver(self, channel: str, notification: Dict[str, Any]) -> None:
        sender = self.senders.get(channel)
        if not sender:
            logger.warning("No registered sender for channel=%s. Logging fallback used.", channel)
            logger.info("Notification fallback user_id=%s event_type=%s payload=%s", notification["user_id"], notification["event_type"], notification["payload"])
            return

        try:
            await sender(notification)
            logger.info("Dispatched notification channel=%s user_id=%s event_type=%s", channel, notification["user_id"], notification["event_type"])
        except Exception as exc:
            logger.exception("Failed to deliver notification channel=%s user_id=%s: %s", channel, notification["user_id"], exc)

    def _build_payload(
        self,
        user_id: int,
        event_type: str,
        payload: Dict[str, Any],
        priority: str,
    ) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "event_type": event_type,
            "payload": payload,
            "priority": priority,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    def _select_channel(self, transcript: str) -> str:
        normalized = transcript.lower()
        if any(keyword in normalized for keyword in ["urgent", "escalate", "critical", "failed"]):
            return "sms"
        if any(keyword in normalized for keyword in ["billing", "invoice", "renewal"]):
            return "email"
        return self.default_channel

    def _summarize_transcript(self, transcript: str) -> str:
        lines = [line.strip() for line in transcript.splitlines() if line.strip()]
        if not lines:
            return "No transcript available to summarize."
        return lines[0][:240]

    def _build_severity_score(self, transcript: str) -> int:
        normalized = transcript.lower()
        score = 1
        if "urgent" in normalized or "immediately" in normalized:
            score += 2
        if "escalate" in normalized or "critical" in normalized:
            score += 3
        if "follow up" in normalized or "next steps" in normalized:
            score += 1
        return min(score, 5)
