from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime


def sanitize_case_title(case_title: str) -> str:
    safe = "".join(c for c in case_title if c.isalnum() or c in {" ", "-"}).strip()
    safe = " ".join(safe.split())
    return safe or "case"


def get_case_folder(base_dir: Path, case_title: str) -> Path:
    return base_dir / f"{sanitize_case_title(case_title)} Transcripts"


def _chunk_id(index: int) -> str:
    return f"chunk_{index:06d}"


def store_transcript_chunks(
    base_dir: Path,
    case_title: str,
    docket_number: str | None,
    source_file: str,
    chunks: List[Dict],
    witness_types: Dict[str, str],
) -> Dict:
    case_dir = get_case_folder(base_dir, case_title)
    chunks_dir = case_dir / "chunks"
    sources_dir = case_dir / "sources"
    case_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    index_path = case_dir / "index.json"
    if index_path.exists():
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index_data = {
            "case_title": case_title,
            "docket_number": docket_number,
            "sources": [],
            "chunks": {},
            "witness_roster": {},
            "page_ranges": [],
        }

    chunk_payloads = []

    # Save chunks
    start_index = len(index_data.get("chunks", {})) + 1
    for i, chunk in enumerate(chunks, start=start_index):
        chunk_id = _chunk_id(i)
        witness = chunk.get("witness")
        witness_type = witness_types.get(witness, "fact") if witness else None
        chunk_payload = {
            "chunk_id": chunk_id,
            "case_title": case_title,
            "docket_number": docket_number,
            "document_type": "trial_transcript",
            "source_file": source_file,
            "witness": witness,
            "witness_type": witness_type,
            "exam": chunk.get("exam"),
            "questioner": chunk.get("questioner"),
            "transcript_page": chunk.get("transcript_page"),
            "page_id": chunk.get("page_id"),
            "text": chunk.get("text"),
            "citation": chunk.get("citation"),
        }
        chunk_payloads.append(chunk_payload)
        chunk_file = chunks_dir / f"{chunk_id}.json"
        chunk_file.write_text(json.dumps(chunk_payload, indent=2), encoding="utf-8")
        index_data["chunks"][chunk_id] = {
            k: chunk_payload.get(k)
            for k in [
                "chunk_id",
                "source_file",
                "witness",
                "witness_type",
                "exam",
                "questioner",
                "transcript_page",
                "page_id",
                "citation",
            ]
        }

        if witness:
            index_data.setdefault("witness_roster", {})
            index_data["witness_roster"].setdefault(witness, {"count": 0, "witness_type": witness_type})
            index_data["witness_roster"][witness]["count"] += 1
            index_data["witness_roster"][witness]["witness_type"] = witness_type

        if chunk.get("page_start") and chunk.get("page_end"):
            index_data.setdefault("page_ranges", []).append({
                "source_file": source_file,
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
            })

    index_data.setdefault("sources", []).append({
        "file": source_file,
        "ingested_at": datetime.utcnow().isoformat() + "Z",
        "chunks": len(chunks),
    })

    index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
    return {
        "case_dir": case_dir,
        "chunks_saved": len(chunks),
        "index_path": index_path,
        "chunk_payloads": chunk_payloads,
    }


def save_source_file(base_dir: Path, case_title: str, filename: str, data: bytes) -> Path:
    case_dir = get_case_folder(base_dir, case_title)
    sources_dir = case_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    target = sources_dir / filename
    target.write_bytes(data)
    return target
