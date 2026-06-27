import base64
from typing import Dict

import httpx
from app.core.config import settings


class TTSService:
    async def synthesize_text(self, text: str, voice_id: str, language: str = "en") -> Dict[str, str]:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice_settings": {
                "stability": 0.65,
                "similarity_boost": 0.6,
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            audio_bytes = response.content
            audio_url = f"data:audio/mpeg;base64,{base64.b64encode(audio_bytes).decode()}"
            return {
                "audio_url": audio_url,
                "voice_id": voice_id,
                "language": language,
            }
