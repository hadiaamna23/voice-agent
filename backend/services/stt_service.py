import asyncio
import audioop
import json
import logging
import os
import re
import wave
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("backend.services.stt_service")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_ENDPOINT = "https://api.deepgram.com/v1/listen"


@dataclass
class TranscriptionResult:
    transcript: str
    confidence: float
    words: List[Dict[str, object]]
    is_silence: bool
    is_interruption: bool


class STTService:
    def __init__(self) -> None:
        if not DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        self.headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/octet-stream",
        }

    async def transcribe_audio(self, audio_bytes: bytes, language: str = "en") -> TranscriptionResult:
        params = {
            "language": language,
            "punctuate": "true",
            "utterances": "false",
            "speaker_labels": "false",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(DEEPGRAM_ENDPOINT, params=params, headers=self.headers, content=audio_bytes)
            response.raise_for_status()
            payload = response.json()
        transcript = payload.get("results", {}).get("channels", [])[0].get("alternatives", [])[0].get("transcript", "")
        confidence = self._estimate_confidence(payload)
        words = payload.get("results", {}).get("channels", [])[0].get("alternatives", [])[0].get("words", [])
        is_silence = self.detect_silence(audio_bytes)
        is_interruption = self.detect_interruption(transcript, words)
        return TranscriptionResult(transcript=transcript, confidence=confidence, words=words, is_silence=is_silence, is_interruption=is_interruption)

    async def stream_transcription(
        self,
        audio_bytes: bytes,
        language: str = "en",
        chunk_size: int = 4096,
    ) -> AsyncGenerator[Dict[str, object], None]:
        params = {
            "language": language,
            "punctuate": "true",
            "utterances": "true",
            "interim_results": "true",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", DEEPGRAM_ENDPOINT, params=params, headers=self.headers, content=audio_bytes) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    transcript = payload.get("channel", {}).get("alternatives", [])[0].get("transcript")
                    if transcript:
                        segment = payload.get("channel", {}).get("alternatives", [])[0]
                        confidence = self._estimate_confidence_from_segment(segment)
                        yield {
                            "type": "transcript_chunk",
                            "text": transcript,
                            "confidence": confidence,
                            "timestamp": payload.get("start", 0.0),
                        }
        yield {"type": "transcription_complete"}

    def detect_silence(self, audio_bytes: bytes, threshold: int = 200, min_silence_duration_ms: int = 500) -> bool:
        try:
            with wave.open_bytes(audio_bytes) as wav_file:
                sample_rate = wav_file.getframerate()
                sample_width = wav_file.getsampwidth()
                num_channels = wav_file.getnchannels()
                frames = wav_file.readframes(wav_file.getnframes())
        except wave.Error:
            return False
        frame_bytes = audioop.tomono(frames, sample_width, 1, 0) if num_channels > 1 else frames
        frame_duration_ms = 1000.0 * sample_width / sample_rate
        silent_frames = 0
        for offset in range(0, len(frame_bytes), sample_width * num_channels):
            frame = frame_bytes[offset : offset + sample_width]
            rms = audioop.rms(frame, sample_width)
            if rms < threshold:
                silent_frames += 1
                if silent_frames * frame_duration_ms >= min_silence_duration_ms:
                    return True
            else:
                silent_frames = 0
        return False

    def detect_interruption(self, transcript: str, words: List[Dict[str, object]]) -> bool:
        if not transcript or len(words) < 2:
            return False
        pause_markers = sum(1 for word in words if word.get("confidence", 1.0) < 0.35)
        return pause_markers >= 2 or bool(re.search(r"\b(um|uh|ah|sorry|wait)\b", transcript.lower()))

    def _estimate_confidence(self, payload: Dict[str, object]) -> float:
        words = payload.get("results", {}).get("channels", [])[0].get("alternatives", [])[0].get("words", [])
        return self._estimate_confidence_from_words(words)

    def _estimate_confidence_from_words(self, words: List[Dict[str, object]]) -> float:
        if not words:
            return 0.0
        confidences = [float(word.get("confidence", 0.0)) for word in words if word.get("confidence") is not None]
        if not confidences:
            return 0.0
        return round(sum(confidences) / len(confidences), 2)

    def _estimate_confidence_from_segment(self, segment: Dict[str, object]) -> float:
        return round(float(segment.get("confidence", 0.0)), 2)
