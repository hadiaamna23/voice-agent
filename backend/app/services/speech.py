import base64
from typing import Optional

import httpx
from app.core.config import settings


class SpeechService:
    async def transcribe_audio(self, audio_bytes: bytes, language: str = "en", mime_type: Optional[str] = "audio/wav") -> dict:
        headers = {
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": mime_type,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={"language": language, "punctuate": True, "model": "general"},
                headers=headers,
                content=audio_bytes,
            )
            response.raise_for_status()
            payload = response.json()
            transcript = payload.get("results", {}).get("channels", [])[0].get("alternatives", [])[0].get("transcript", "")
            duration = payload.get("metadata", {}).get("duration", 0.0)
            return {
                "transcript": transcript,
                "language": language,
                "duration_seconds": duration,
                "raw": payload,
            }

    async def generate_tts_data_uri(self, text: str, voice_id: str, language: str = "en") -> dict:
        import httpx
        import base64

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "voice_settings": {"stability": 0.75, "similarity_boost": 0.7},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            content = response.content
            encoded = base64.b64encode(content).decode("ascii")
            return {
                "audio_url": f"data:audio/mpeg;base64,{encoded}",
                "voice_id": voice_id,
                "language": language,
            }
