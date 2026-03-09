# In-Court Listener (MVP Scaffold)

This document describes the local-first, real-time courtroom listening feature and how the current scaffold is wired.

## Current MVP Scope

- Case selection required before starting a session.
- Case Context Pack inferred from existing casefiles (stored at `Casefiles/<case_id>/case_context.json` when available).
- Live transcript is streamed from the microphone via the local FastAPI server.
- Live summary is generated from recent transcript segments and refreshed frequently.
- Optional issue detection + local LLM analysis (Ollama) when `INCOURT_ENABLE_ANALYSIS=1`.
- Case-law retrieval via existing Chroma corpus (Equitable Case Law DB).
- Session artifacts stored locally under `Casefiles/<case_id>/incourt_listener/`.
- UI embedded in Streamlit under **In-Court Listener**.

## What’s Not Yet Implemented

- Live microphone capture + streaming ASR pipeline.
- AudioWorklet resampling/VAD.
- Real-time WebRTC device switching.
- Diarization.
- Automated permission deep-linking beyond UI guidance.

## Running the UI

Open the Streamlit app and navigate to **In-Court Listener**.
Use the microphone selector in the listener panel to pick the input device.

## LLM Requirements

Local Qwen via Ollama is expected:

- `INCOURT_LLM_URL` (default: `http://localhost:11434/api/chat`)
- `INCOURT_LLM_MODEL` (default: `qwen2.5:32b-instruct`)

If the LLM is unavailable, rule-based detection still runs.

## Analysis (Optional)

Set `INCOURT_ENABLE_ANALYSIS=1` to generate rolling notes and issue alerts alongside the transcript.

## ASR Engine (faster-whisper)

The ASR scaffold uses faster-whisper for local transcription of uploaded clips.

Environment variables:
- `INCOURT_ASR_MODEL` (default: `base`)
- `INCOURT_ASR_DEVICE` (default: `auto`)
- `INCOURT_ASR_COMPUTE_TYPE` (default: `int8`)
- `INCOURT_ASR_LANGUAGE` (optional, e.g., `en`)
- `INCOURT_ASR_WARMUP` (default: `1`) preloads the ASR model in the background on server startup.
- `INCOURT_ENABLE_METRICS` (default: `1`) writes per-chunk timing metrics to `metrics.jsonl`.

Install:

```
pip install faster-whisper
```

## Streaming Server (Live Microphone)

The live microphone stream is handled by a local FastAPI service:

```
./scripts/run_incourt_listener_server.sh
```

Windows:

```
./scripts/run_incourt_listener_server.ps1
```

or

```
scripts\\run_incourt_listener_server.bat
```

Default URL: `http://localhost:8777` (override with `INCOURT_SERVER_URL` in Streamlit).

Client streaming tuning:
- `INCOURT_CHUNK_MS` (default: `4000`) controls the microphone chunk size sent to the server.
- `INCOURT_DISPLAY_FROM_JSONL` (default: `1`) uses `transcript.jsonl` for smoother live display.

## Live Summary

Environment variables:
- `INCOURT_ENABLE_SUMMARY` (default: `1`) toggles summary generation.
- `INCOURT_SUMMARY_INTERVAL_SEC` (default: `8`) controls how often summaries refresh.
- `INCOURT_SUMMARY_WINDOW_SEC` (default: `60`) controls how much recent audio is summarized.
- `INCOURT_SUMMARY_MAX_SEGMENTS` (default: `80`) caps the number of segments used for each summary.
- `INCOURT_SUMMARY_USE_LLM` (default: `1`) uses the local LLM when available.
- `INCOURT_SUMMARY_LLM_URL` / `INCOURT_SUMMARY_LLM_MODEL` / `INCOURT_SUMMARY_LLM_TEMPERATURE` override summary LLM settings.
- `INCOURT_SUMMARY_MAX_BULLETS` (default: `4`) limits bullet count for rule-based summaries.
- `INCOURT_SUMMARY_TARGET_CHARS` (default: `600`) limits summary length.
- `INCOURT_SUMMARY_REFRESH_SEC` (default: `2`) controls UI refresh cadence.

## Session Files

```
Casefiles/<case_id>/incourt_listener/<session_id>/
  session.json
  transcript.jsonl
  transcript.txt
  summary.jsonl
  summary_latest.json
  metrics.jsonl (per-chunk timing data when metrics are enabled)
  notes.jsonl (only when analysis enabled)
  alerts.jsonl (only when analysis enabled)

Casefiles/<case_id>/incourt_listener/<session_id>.txt
  Plain-text running transcript at the case level for each session.
```

## Next Implementation Steps

1. Replace manual transcript input with streaming ASR.
2. Add AudioWorklet capture and resampling.
3. Implement alert throttling + dedupe persistence.
4. Add export bundle (PDF/DOCX/JSON).
