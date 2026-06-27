import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import CallLog, Conversation

MEMORY_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "memory_store.json"
MEMORY_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


class MemoryService:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.storage_path = MEMORY_STORAGE_PATH

    async def get_short_term_memory(self, user_id: int, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id, Conversation.session_id == session_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )
            return [
                {"role": row.role, "content": row.content, "language": row.language}
                for row in result.scalars().all()[::-1]
            ]

    async def get_long_term_memory(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLog)
                .where(CallLog.user_id == user_id)
                .order_by(CallLog.created_at.desc())
                .limit(limit)
            )
            return [
                {"session_id": row.session_id, "transcript": row.transcript, "created_at": row.created_at.isoformat()}
                for row in result.scalars().all()[::-1]
            ]

    async def load_memory_store(self) -> Dict[str, Any]:
        async with self.lock:
            if not self.storage_path.exists():
                return {}
            with open(self.storage_path, "r", encoding="utf-8") as handle:
                return json.load(handle)

    async def persist_memory(self, user_id: int, session_id: str, memory: str, memory_type: str = "short_term") -> None:
        async with self.lock:
            store = await self.load_memory_store()
            user_entry = store.setdefault(str(user_id), {})
            session_entry = user_entry.setdefault(session_id, {})
            session_entry.setdefault(memory_type, []).append({
                "memory": memory,
                "timestamp": datetime.utcnow().isoformat(),
            })
            with open(self.storage_path, "w", encoding="utf-8") as handle:
                json.dump(store, handle, indent=2, ensure_ascii=False)

    async def summarize_session(self, user_id: int, session_id: str, max_sentences: int = 3) -> str:
        messages = await self.get_short_term_memory(user_id, session_id, limit=50)
        transcript = " ".join(item["content"] for item in messages)
        if not transcript:
            return "No recent session activity available."
        sentences = transcript.split(".")
        summary = ". ".join(sentence.strip() for sentence in sentences[:max_sentences]).strip()
        summary = summary if summary.endswith(".") else summary + "."
        await self.persist_memory(user_id, session_id, summary, memory_type="summary")
        return summary

    async def store_call_history(self, user_id: int, session_id: str, transcript: str) -> None:
        await self.persist_memory(user_id, session_id, transcript, memory_type="call_history")

    async def build_context(self, user_id: int, session_id: str) -> Dict[str, Any]:
        short_term = await self.get_short_term_memory(user_id, session_id)
        long_term = await self.get_long_term_memory(user_id)
        store = await self.load_memory_store()
        return {
            "short_term_memory": short_term,
            "long_term_memory": long_term,
            "persistent_memory": store.get(str(user_id), {}).get(session_id, {}),
        }
