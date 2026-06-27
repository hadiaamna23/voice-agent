import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("backend.services.recording_service")
BASE_STORAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "recordings"
BASE_STORAGE_PATH.mkdir(parents=True, exist_ok=True)


class RecordingService:
    def __init__(self) -> None:
        self.storage_path = BASE_STORAGE_PATH

    def save_audio(self, call_id: str, audio_bytes: bytes, file_name: Optional[str] = None, content_type: str = "audio/wav") -> Path:
        extension = self._select_extension(content_type)
        file_name = file_name or f"{call_id}.{extension}"
        audio_path = self.storage_path / file_name
        audio_path.write_bytes(audio_bytes)
        logger.info("Saved audio recording for call=%s file=%s", call_id, audio_path.name)
        return audio_path

    def save_transcript(self, call_id: str, transcript: str, metadata: Optional[Dict[str, object]] = None) -> Path:
        transcript_name = f"{call_id}.json"
        transcript_path = self.storage_path / transcript_name
        payload = {
            "call_id": call_id,
            "transcript": transcript,
            "metadata": metadata or {},
            "saved_at": datetime.utcnow().isoformat(),
        }
        transcript_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved transcript for call=%s", call_id)
        return transcript_path

    def save_metadata(self, call_id: str, metadata: Dict[str, object]) -> Path:
        metadata_path = self.storage_path / f"{call_id}.meta.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved metadata for call=%s", call_id)
        return metadata_path

    def export_recording(self, call_id: str, export_format: str = "zip") -> bytes:
        if export_format != "zip":
            raise ValueError("Only zip export is supported")
        export_path = self.storage_path / f"{call_id}.zip"
        with zipfile.ZipFile(export_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in self.storage_path.glob(f"{call_id}.*"):
                archive.write(file, arcname=file.name)
        logger.info("Exported recording archive for call=%s", call_id)
        return export_path.read_bytes()

    def get_recording_metadata(self, call_id: str) -> Dict[str, object]:
        metadata_path = self.storage_path / f"{call_id}.meta.json"
        if not metadata_path.exists():
            return {}
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _select_extension(self, content_type: str) -> str:
        if "mpeg" in content_type or "mp3" in content_type:
            return "mp3"
        if "ogg" in content_type:
            return "ogg"
        return "wav"
