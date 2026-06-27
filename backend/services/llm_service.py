import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger("backend.services.llm_service")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

STRUCTURED_RESPONSE_SCHEMA = {
    "conversation_summary": str,
    "recommendations": list,
    "language": str,
    "emotion": str,
}


class LLMService:
    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_MODEL) -> None:
        self.api_key = api_key or OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment")
        self.model = model
        self.max_retries = 3
        self.timeout = 120.0

    async def stream_chat_response(
        self,
        user_id: int,
        session_id: str,
        messages: List[Dict[str, str]],
        tone: str = "professional",
        language: str = "en",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, tone, language),
            "temperature": 0.75,
            "stream": True,
            "max_tokens": 800,
        }
        stream_url = "https://api.openai.com/v1/chat/completions"

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream("POST", stream_url, headers=self._headers(), json=payload) as response:
                        response.raise_for_status()
                        collected_text = ""
                        async for raw_line in response.aiter_lines():
                            if not raw_line or raw_line.strip() == "data: [DONE]":
                                continue
                            if raw_line.startswith("data:"):
                                event_data = raw_line[len("data:"):].strip()
                                try:
                                    event = json.loads(event_data)
                                except json.JSONDecodeError:
                                    continue
                                delta = event.get("choices", [])[0].get("delta", {})
                                chunk = delta.get("content", "")
                                if chunk:
                                    collected_text += chunk
                                    yield {"type": "partial", "text": chunk}
                        structured = self._structure_output(collected_text, language)
                        yield {"type": "complete", "text": collected_text, "structured": structured}
                        return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as exc:
                logger.warning("LLM request attempt %s failed: %s", attempt, exc)
                if attempt == self.max_retries:
                    logger.error("LLM request failed after retries")
                    raise
                await asyncio.sleep(2 ** attempt)

    def _build_messages(self, messages: List[Dict[str, str]], tone: str, language: str) -> List[Dict[str, str]]:
        context = [
            {
                "role": "system",
                "content": (
                    "You are an enterprise-grade conversational voice agent. "
                    "Respond in the requested language. "
                    "Use structured JSON output when possible. "
                    "Include emotional tone and actionable recommendations."
                ),
            }
        ]
        context.extend(messages)
        context.append(
            {
                "role": "system",
                "content": (
                    f"Adapt the emotional tone to be {tone}. "
                    f"If the user appears upset or confused, escalate politely and offer clarity. "
                    f"Respond using {language} when asked."
                ),
            }
        )
        return context

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _structure_output(self, text: str, language: str) -> Dict[str, Any]:
        if not text:
            return {
                "conversation_summary": "",
                "recommendations": [],
                "language": language,
                "emotion": "neutral",
            }
        summary = self._extract_summary(text)
        emotion = self._detect_emotion(text)
        recommendations = self._extract_recommendations(text)
        return {
            "conversation_summary": summary,
            "recommendations": recommendations,
            "language": language,
            "emotion": emotion,
        }

    def _extract_summary(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(sentences[:2]).strip()

    def _detect_emotion(self, text: str) -> str:
        lower_text = text.lower()
        if any(word in lower_text for word in ["angry", "frustrated", "upset", "unhappy"]):
            return "angry"
        if any(word in lower_text for word in ["happy", "great", "glad", "pleased"]):
            return "happy"
        if any(word in lower_text for word in ["confused", "unclear", "unsure"]):
            return "confused"
        return "neutral"

    def _extract_recommendations(self, text: str) -> List[str]:
        recommendations = re.findall(r"(?i)(?:recommend|suggest|you should|consider)\s+([^\.\n]+)", text)
        return [item.strip() for item in recommendations if item.strip()][:3]

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)
