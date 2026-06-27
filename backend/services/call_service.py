import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.recording_service import RecordingService
from services.sentiment_service import SentimentService
from services.stt_service import STTService

logger = logging.getLogger("backend.services.call_service")
CALL_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "call_state.json"
CALL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class CallRecord:
    call_id: str
    direction: str
    status: str
    target: Optional[str]
    created_at: str
    last_updated: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CallService:
    def __init__(self) -> None:
        self.recording_service = RecordingService()
        self.stt_service = STTService()
        self.sentiment_service = SentimentService()
        self.state: Dict[str, CallRecord] = self._load_state()
        self.event_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self.lock = asyncio.Lock()

    def register_event_handler(self, event_name: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self.event_handlers[event_name] = handler
        logger.info("Registered event handler %s", event_name)

    async def initiate_inbound_call(self, target: str, metadata: Optional[Dict[str, Any]] = None) -> CallRecord:
        return await self._new_call(direction="inbound", target=target, metadata=metadata or {})

    async def initiate_outbound_call(self, target: str, metadata: Optional[Dict[str, Any]] = None) -> CallRecord:
        return await self._new_call(direction="outbound", target=target, metadata=metadata or {})

    async def _new_call(self, direction: str, target: str, metadata: Dict[str, Any]) -> CallRecord:
        call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        record = CallRecord(
            call_id=call_id,
            direction=direction,
            status="initiated",
            target=target,
            created_at=now,
            last_updated=now,
            metadata={"direction": direction, "target": target, **metadata},
        )
        async with self.lock:
            self.state[call_id] = record
            self._persist_state()
        await self._emit_event("call_started", record.to_dict())
        return record

    async def complete_call(self, call_id: str, audio_bytes: Optional[bytes] = None, content_type: str = "audio/wav") -> CallRecord:
        record = self.state.get(call_id)
        if not record:
            raise ValueError("Call record not found")
        record.status = "completed"
        record.last_updated = datetime.now(timezone.utc).isoformat()
        async with self.lock:
            self.state[call_id] = record
            self._persist_state()
        if audio_bytes:
            audio_path = self.recording_service.save_audio(call_id, audio_bytes, content_type=content_type)
            record.metadata["recording_path"] = str(audio_path)
            transcript_result = await self.stt_service.transcribe_audio(audio_bytes)
            self.recording_service.save_transcript(call_id, transcript_result.transcript, metadata={"confidence": transcript_result.confidence})
            sentiment = self.sentiment_service.analyze(transcript_result.transcript)
            record.metadata["sentiment"] = sentiment
            voicemail = self.detect_voicemail(transcript_result.transcript, audio_path)
            record.metadata["voicemail_detected"] = voicemail
            self._persist_state()
            await self._emit_event(
                "call_completed",
                {
                    "call_id": call_id,
                    "status": record.status,
                    "transcript": transcript_result.transcript,
                    "confidence": transcript_result.confidence,
                    "sentiment": sentiment,
                    "voicemail_detected": voicemail,
                },
            )
        else:
            await self._emit_event("call_completed", record.to_dict())
        return record

    async def fail_call(self, call_id: str, reason: str) -> CallRecord:
        record = self.state.get(call_id)
        if not record:
            raise ValueError("Call record not found")
        record.status = "failed"
        record.last_updated = datetime.now(timezone.utc).isoformat()
        record.metadata["failure_reason"] = reason
        async with self.lock:
            self.state[call_id] = record
            self._persist_state()
        await self._emit_event("call_failed", record.to_dict())
        return record

    async def retry_call(self, call_id: str, delay_seconds: int = 60, max_retries: int = 3) -> None:
        record = self.state.get(call_id)
        if not record:
            raise ValueError("Call record not found")
        retry_count = record.metadata.get("retry_count", 0)
        if retry_count >= max_retries:
            logger.warning("Call %s reached max retry attempts", call_id)
            return
        record.metadata["retry_count"] = retry_count + 1
        record.status = "retry_scheduled"
        record.last_updated = datetime.now(timezone.utc).isoformat()
        self._persist_state()

        await self._emit_event("call_retry_scheduled", {"call_id": call_id, "delay_seconds": delay_seconds, "retry_count": retry_count + 1})
        await asyncio.sleep(delay_seconds)
        record.status = "retrying"
        record.last_updated = datetime.now(timezone.utc).isoformat()
        self._persist_state()
        await self._emit_event("call_retrying", {"call_id": call_id, "retry_count": retry_count + 1})

    def detect_voicemail(self, transcript: str, audio_path: Path) -> bool:
        lower = transcript.lower()
        voicemail_indicators = ["leave a message", "voicemail", "please leave", "after the beep"]
        if any(term in lower for term in voicemail_indicators):
            return True
        audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
        return audio_size_mb < 0.3 and len(transcript.split()) < 10

    async def emit_websocket_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        await self._emit_event(event_type, {"session_id": session_id, **payload})

    async def _emit_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        logger.info("Emitting event %s payload=%s", event_name, payload)
        handler = self.event_handlers.get(event_name)
        if handler:
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.exception("Error in event handler %s: %s", event_name, exc)

    def _persist_state(self) -> None:
        CALL_STATE_PATH.write_text(json.dumps({call_id: record.to_dict() for call_id, record in self.state.items()}, indent=2), encoding="utf-8")

    def _load_state(self) -> Dict[str, CallRecord]:
        if not CALL_STATE_PATH.exists():
            return {}
        raw = json.loads(CALL_STATE_PATH.read_text(encoding="utf-8"))
        return {call_id: CallRecord(**data) for call_id, data in raw.items()}
