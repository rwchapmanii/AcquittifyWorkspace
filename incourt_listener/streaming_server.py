from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from case_manager import get_case_paths_by_id
from incourt_listener.analysis import analyze_window
from incourt_listener.asr import get_asr_engine, warm_asr_engine
from incourt_listener.context import load_case_context
from incourt_listener.session import append_jsonl, append_transcript_text, load_recent_jsonl, session_paths
from incourt_listener.summary import filter_segments_by_window, summarize_window


logger = logging.getLogger(__name__)
SUMMARY_EXECUTOR = ThreadPoolExecutor(max_workers=2)
SUMMARY_STATE = {
    "lock": threading.Lock(),
    "last_run": {},
    "inflight": set(),
}

app = FastAPI(title="In-Court Listener Streaming Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _env_flag(name: str, default: str = "0") -> bool:
    value = (os.getenv(name, default) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _record_metrics(paths: dict, payload: dict) -> None:
    try:
        append_jsonl(paths["metrics"], payload)
    except Exception as exc:
        logger.warning("Unable to record metrics: %s", exc)


def _warm_asr_in_background() -> None:
    try:
        warm_asr_engine()
        logger.info("ASR warm-up complete.")
    except Exception as exc:
        logger.warning("ASR warm-up failed: %s", exc)


@app.on_event("startup")
def _startup() -> None:
    if _env_flag("INCOURT_ASR_WARMUP", "1"):
        threading.Thread(target=_warm_asr_in_background, daemon=True).start()


def _now_ts() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_summary_window(paths: dict, window_sec: int, max_segments: int) -> list[dict]:
    segments = load_recent_jsonl(paths["transcript"], limit=max_segments)
    return filter_segments_by_window(segments, window_sec=window_sec)


def _write_summary(paths: dict, payload: dict) -> None:
    append_jsonl(paths["summary"], payload)
    try:
        paths["summary_latest"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Unable to write summary_latest: %s", exc)


def _generate_summary(
    paths: dict,
    case_id: str,
    session_id: str,
    metrics_enabled: bool,
) -> None:
    t0 = time.perf_counter()
    window_sec = int(os.getenv("INCOURT_SUMMARY_WINDOW_SEC", "60"))
    max_segments = int(os.getenv("INCOURT_SUMMARY_MAX_SEGMENTS", "80"))
    max_bullets = int(os.getenv("INCOURT_SUMMARY_MAX_BULLETS", "4"))
    target_chars = int(os.getenv("INCOURT_SUMMARY_TARGET_CHARS", "600"))
    use_llm = _env_flag("INCOURT_SUMMARY_USE_LLM", "1")
    source = "rule"
    summary_payload: dict | None = None
    try:
        segments = _load_summary_window(paths, window_sec=window_sec, max_segments=max_segments)
        summary_payload = summarize_window(
            segments=segments,
            max_bullets=max_bullets,
            target_chars=target_chars,
            use_llm=use_llm,
        )
        source = summary_payload.get("source", "rule") if summary_payload else "rule"
        if summary_payload and summary_payload.get("summary"):
            summary_payload["case_id"] = case_id
            summary_payload["session_id"] = session_id
            summary_payload["window_sec"] = window_sec
            summary_payload["segments"] = len(segments)
            _write_summary(paths, summary_payload)
    except Exception as exc:
        logger.exception("Summary generation failed: %s", exc)
    finally:
        if metrics_enabled:
            _record_metrics(
                paths,
                {
                    "ts": _now_ts(),
                    "case_id": case_id,
                    "session_id": session_id,
                    "phase": "summary",
                    "summary_source": source,
                    "t_summary_s": time.perf_counter() - t0,
                },
            )
        with SUMMARY_STATE["lock"]:
            SUMMARY_STATE["inflight"].discard(session_id)
            SUMMARY_STATE["last_run"][session_id] = time.time()


def _maybe_schedule_summary(
    paths: dict,
    case_id: str,
    session_id: str,
    metrics_enabled: bool,
) -> None:
    if not _env_flag("INCOURT_ENABLE_SUMMARY", "1"):
        return
    interval = float(os.getenv("INCOURT_SUMMARY_INTERVAL_SEC", "8"))
    now = time.time()
    with SUMMARY_STATE["lock"]:
        if session_id in SUMMARY_STATE["inflight"]:
            return
        last_run = SUMMARY_STATE["last_run"].get(session_id, 0.0)
        if now - last_run < interval:
            return
        SUMMARY_STATE["inflight"].add(session_id)
    SUMMARY_EXECUTOR.submit(_generate_summary, paths, case_id, session_id, metrics_enabled)


def _guess_ext(upload: UploadFile) -> str:
    if upload.filename and "." in upload.filename:
        return upload.filename.rsplit(".", 1)[-1].lower()
    if upload.content_type and "webm" in upload.content_type:
        return "webm"
    if upload.content_type and "wav" in upload.content_type:
        return "wav"
    if upload.content_type and "mp3" in upload.content_type:
        return "mp3"
    if upload.content_type and "ogg" in upload.content_type:
        return "ogg"
    return "bin"


def _merge_segments(segments: list[dict]) -> list[dict]:
    cleaned = [seg for seg in segments if seg.get("text")]
    if len(cleaned) <= 1:
        return cleaned
    merged_text = " ".join(seg.get("text", "").strip() for seg in cleaned if seg.get("text"))
    merged_text = " ".join(merged_text.split())
    confidences = [seg.get("confidence") for seg in cleaned if isinstance(seg.get("confidence"), (int, float))]
    confidence = sum(confidences) / len(confidences) if confidences else 0.5
    return [
        {
            "start": cleaned[0].get("start", 0.0),
            "end": cleaned[-1].get("end", cleaned[0].get("end", 0.0)),
            "text": merged_text,
            "confidence": confidence,
        }
    ]


def _process_audio_bytes(
    case_id: str,
    session_id: str,
    data: bytes,
    ext: str,
) -> tuple[int, str | None]:
    case_paths = get_case_paths_by_id(case_id)
    paths = session_paths(case_paths.root, session_id)
    metrics_enabled = _env_flag("INCOURT_ENABLE_METRICS", "1")
    t0 = time.perf_counter()
    asr_init_s = 0.0
    transcribe_s = 0.0
    merge_s = 0.0
    analysis_s = 0.0
    append_s = 0.0
    error_msg = None
    audio_dir = paths["root"] / "audio_chunks"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if not data or len(data) < 1024:
        return 0, None

    chunk_id = uuid4().hex[:8]
    audio_path = audio_dir / f"chunk_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{chunk_id}.{ext}"
    audio_path.write_bytes(data)

    try:
        t_asr = time.perf_counter()
        asr = get_asr_engine()
        asr_init_s = time.perf_counter() - t_asr
        t_tx = time.perf_counter()
        segments = asr.transcribe_file(audio_path, language=os.getenv("INCOURT_ASR_LANGUAGE"))
        transcribe_s = time.perf_counter() - t_tx
    except Exception as exc:
        error_msg = str(exc)
        if metrics_enabled:
            _record_metrics(
                paths,
                {
                    "ts": _now_ts(),
                    "case_id": case_id,
                    "session_id": session_id,
                    "audio_bytes": len(data),
                    "ext": ext,
                    "error": error_msg,
                    "phase": "asr",
                    "t_total_s": time.perf_counter() - t0,
                    "t_asr_init_s": asr_init_s,
                    "t_transcribe_s": transcribe_s,
                },
            )
        logger.exception("ASR failed for %s: %s", audio_path, exc)
        return 0, error_msg

    merge_enabled = os.getenv("INCOURT_MERGE_SEGMENTS", "1").strip().lower() not in {"0", "false", "no"}
    if merge_enabled:
        t_merge = time.perf_counter()
        segments = _merge_segments(segments)
        merge_s = time.perf_counter() - t_merge

    enable_analysis = os.getenv("INCOURT_ENABLE_ANALYSIS", "").lower() in {"1", "true", "yes"}
    context = load_case_context(case_paths.root) if enable_analysis else {}
    for seg in segments:
        segment_id = f"seg_{datetime.utcnow().strftime('%H%M%S_%f')}"
        transcript_entry = {
            "segment_id": segment_id,
            "case_id": case_id,
            "case_name": case_id,
            "ts_start": _now_ts(),
            "ts_end": _now_ts(),
            "speaker": "unknown",
            "confidence": seg.get("confidence", 0.5),
            "text": seg.get("text", "").strip(),
        }
        t_append = time.perf_counter()
        append_jsonl(paths["transcript"], transcript_entry)
        append_transcript_text(paths["transcript_text"], transcript_entry["text"])
        append_transcript_text(paths["case_transcript_text"], transcript_entry["text"])
        append_s += time.perf_counter() - t_append
        if enable_analysis:
            t_analysis = time.perf_counter()
            window = load_recent_jsonl(paths["transcript"], limit=6)
            try:
                analysis = analyze_window(
                    context=context,
                    transcript_window=window,
                    use_llm=True,
                    chroma_dir=str(Path("Corpus") / "Chroma"),
                )
            except Exception as exc:
                logger.exception("Analysis failed for %s: %s", segment_id, exc)
                analysis = {"notes": [], "alerts": []}
            for note in analysis.get("notes", []):
                append_jsonl(paths["notes"], note)
            for alert in analysis.get("alerts", []):
                append_jsonl(paths["alerts"], alert)
            analysis_s += time.perf_counter() - t_analysis

    _maybe_schedule_summary(paths, case_id, session_id, metrics_enabled)

    if metrics_enabled:
        _record_metrics(
            paths,
            {
                "ts": _now_ts(),
                "case_id": case_id,
                "session_id": session_id,
                "audio_bytes": len(data),
                "ext": ext,
                "segments": len(segments),
                "merge_segments": merge_enabled,
                "analysis_enabled": enable_analysis,
                "asr_model": os.getenv("INCOURT_ASR_MODEL", "base"),
                "asr_device": os.getenv("INCOURT_ASR_DEVICE", "auto"),
                "asr_compute_type": os.getenv("INCOURT_ASR_COMPUTE_TYPE", "int8"),
                "t_total_s": time.perf_counter() - t0,
                "t_asr_init_s": asr_init_s,
                "t_transcribe_s": transcribe_s,
                "t_merge_s": merge_s,
                "t_append_s": append_s,
                "t_analysis_s": analysis_s,
            },
        )

    return len(segments), None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/session/{case_id}/{session_id}/audio")
async def ingest_audio(case_id: str, session_id: str, file: UploadFile = File(...)) -> JSONResponse:
    ext = _guess_ext(file)
    data = await file.read()
    count, error = _process_audio_bytes(case_id, session_id, data, ext)
    if error:
        return JSONResponse(status_code=500, content={"error": error})
    return JSONResponse(content={"status": "ok", "segments": count})


@app.websocket("/session/{case_id}/{session_id}/audio/ws")
async def ingest_audio_ws(websocket: WebSocket, case_id: str, session_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            count, error = _process_audio_bytes(case_id, session_id, data, "webm")
            if error:
                await websocket.send_json({"status": "error", "error": error})
            else:
                await websocket.send_json({"status": "ok", "segments": count})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("WebSocket error: %s", exc)
        try:
            await websocket.send_json({"status": "error", "error": str(exc)})
        except Exception:
            return
