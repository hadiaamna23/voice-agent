import json
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger("backend.services.translation_service")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SUPPORTED_LANGUAGES = {
    "english": "en",
    "urdu": "ur",
    "hindi": "hi",
    "arabic": "ar",
}


class TranslationService:
    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_MODEL) -> None:
        self.api_key = api_key or OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be configured")
        self.model = model
        self.api_url = "https://api.openai.com/v1/chat/completions"

    async def detect_language(self, text: str) -> str:
        request_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Detect the primary spoken language for the following text. "
                        "Return only the single language name in plain text."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.0,
            "max_tokens": 10,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.api_url, headers=self._headers(), json=request_payload)
            response.raise_for_status()
            raw = response.json()
            detected = raw.get("choices", [])[0].get("message", {}).get("content", "English").strip()
            language = detected.split("\n")[0].strip()
            logger.debug("Detected language: %s", language)
            return language

    async def translate_text(self, text: str, target_language: str = "english") -> Dict[str, str]:
        target_language = target_language.lower()
        if target_language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported target language: {target_language}")
        if not text.strip():
            return {"original_text": text, "translated_text": text, "target_language": target_language}

        prompt = (
            f"Translate the following text into {target_language.title()} while preserving meaning, tone, and formality. "
            "Return only the translated text in the target language."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.api_url, headers=self._headers(), json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 500,
            })
            response.raise_for_status()
            raw = response.json()
            translated = raw.get("choices", [])[0].get("message", {}).get("content", "").strip()
            return {
                "original_text": text,
                "translated_text": translated,
                "target_language": target_language,
            }

    async def auto_translate(self, text: str) -> Dict[str, str]:
        source_language = await self.detect_language(text)
        target_language = "english" if source_language.lower() != "english" else "english"
        translation = await self.translate_text(text, target_language=target_language)
        return {"source_language": source_language, **translation}

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
