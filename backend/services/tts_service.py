import io
import logging
import os
from typing import AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger("backend.services.tts_service")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

VOICE_PROFILES: Dict[str, Dict[str, str]] = {
    "alex_male": {"voice_id": "male_1", "gender": "male"},
    "lara_female": {"voice_id": "female_1", "gender": "female"},
    "simon_male": {"voice_id": "male_2", "gender": "male"},
    "maya_female": {"voice_id": "female_2", "gender": "female"},
}
EMOTION_PRESETS: Dict[str, Dict[str, float]] = {
    "neutral": {"stability": 0.55, "similarity_boost": 0.5},
    "happy": {"stability": 0.45, "similarity_boost": 0.75},
    "angry": {"stability": 0.25, "similarity_boost": 0.9},
    "sad": {"stability": 0.35, "similarity_boost": 0.6},
}


class TTSService:
    def __init__(self) -> None:
        if not ELEVENLABS_API_KEY:
            raise ValueError("ELEVENLABS_API_KEY environment variable is required")
        self.headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }

    def list_voices(self) -> List[Dict[str, str]]:
        return [
            {"name": name, "voice_id": profile["voice_id"], "gender": profile["gender"]}
            for name, profile in VOICE_PROFILES.items()
        ]

    async def synthesize_audio(
        self,
        text: str,
        voice_name: str = "alex_male",
        emotion: str = "neutral",
        language: str = "en",
    ) -> Dict[str, object]:
        voice_settings = EMOTION_PRESETS.get(emotion.lower(), EMOTION_PRESETS["neutral"])
        profile = VOICE_PROFILES.get(voice_name, VOICE_PROFILES["alex_male"])
        url = f"{ELEVENLABS_API_URL}/{profile['voice_id']}"
        payload = {
            "text": text,
            "voice_settings": voice_settings,
            "metadata": {"language": language, "emotion": emotion},
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            audio_bytes = response.content

        logger.info("Synthesized audio for voice=%s emotion=%s", voice_name, emotion)
        return {"audio_bytes": audio_bytes, "voice_id": profile["voice_id"], "language": language, "emotion": emotion}

    async def stream_audio(
        self,
        text: str,
        voice_name: str = "alex_male",
        emotion: str = "neutral",
        language: str = "en",
    ) -> AsyncGenerator[bytes, None]:
        voice_settings = EMOTION_PRESETS.get(emotion.lower(), EMOTION_PRESETS["neutral"])
        profile = VOICE_PROFILES.get(voice_name, VOICE_PROFILES["alex_male"])
        url = f"{ELEVENLABS_API_URL}/{profile['voice_id']}"
        payload = {
            "text": text,
            "voice_settings": voice_settings,
            "metadata": {"language": language, "emotion": emotion},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=self.headers, json=payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk

    def voice_selection(self, gender: Optional[str] = None) -> Dict[str, str]:
        if gender:
            for name, profile in VOICE_PROFILES.items():
                if profile["gender"] == gender.lower():
                    return {"name": name, "voice_id": profile["voice_id"], "gender": profile["gender"]}
        return {"name": "alex_male", "voice_id": VOICE_PROFILES["alex_male"]["voice_id"], "gender": "male"}
