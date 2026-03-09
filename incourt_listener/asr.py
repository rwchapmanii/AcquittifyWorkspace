from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache


class FasterWhisperASR:
    def __init__(
        self,
        model_size: str,
        device: str,
        compute_type: str,
    ) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency guarded
            raise RuntimeError("faster-whisper is not installed") from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe_file(self, path: Path, language: Optional[str] = None) -> List[Dict[str, object]]:
        try:
            if path.stat().st_size < 1024:
                return []
        except OSError:
            return []
        try:
            segments, _info = self._model.transcribe(
                str(path),
                language=language,
                beam_size=5,
                vad_filter=True,
            )
        except ValueError as exc:
            if "max() arg is an empty sequence" in str(exc):
                return []
            raise
        except Exception as exc:
            # PyAV throws InvalidDataError for corrupt/empty chunks.
            if exc.__class__.__name__ == "InvalidDataError":
                return []
            if "Invalid data found when processing input" in str(exc):
                return []
            raise
        results: List[Dict[str, object]] = []
        for seg in segments:
            avg_logprob = getattr(seg, "avg_logprob", None)
            confidence = None
            if isinstance(avg_logprob, (int, float)):
                confidence = max(0.0, min(1.0, (avg_logprob + 1.0)))
            results.append(
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text.strip(),
                    "confidence": confidence if confidence is not None else 0.5,
                }
            )
        return results


@lru_cache(maxsize=1)
def get_asr_engine() -> FasterWhisperASR:
    model_size = os.getenv("INCOURT_ASR_MODEL", "base")
    device = os.getenv("INCOURT_ASR_DEVICE", "auto")
    compute_type = os.getenv("INCOURT_ASR_COMPUTE_TYPE", "int8")
    return FasterWhisperASR(model_size=model_size, device=device, compute_type=compute_type)


def warm_asr_engine() -> None:
    _ = get_asr_engine()
