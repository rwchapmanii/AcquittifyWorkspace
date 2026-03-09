from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

from acquittify.ingest.transcript_parser import parse_transcript_pdf
from acquittify.ingest.transcript_chunker import chunk_pages
from acquittify.ingest.transcript_storage import (
    store_transcript_chunks,
    save_source_file,
    get_case_folder,
    sanitize_case_title,
)
from acquittify.ingest.transcript_retrieval import upsert_transcript_chunks_to_chroma


WITNESS_TYPES = ["fact", "expert", "law_enforcement", "foundational", "defendant", "co_defendant"]
BASE_TRANSCRIPTS_DIR = Path("data/transcripts")


def _init_state() -> None:
    st.session_state.setdefault("transcript_status", {})
    st.session_state.setdefault("transcript_analysis", {})
    st.session_state.setdefault("transcript_activity", [])
    st.session_state.setdefault("transcript_witness_types", {})


def _log(message: str) -> None:
    st.session_state.transcript_activity.append(message)


def _analyze_upload(upload) -> Dict:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(upload.read())
        tmp_path = Path(tmp.name)
    result = parse_transcript_pdf(tmp_path)
    return result


def _build_status_table() -> List[Dict]:
    rows = []
    for name, status in st.session_state.transcript_status.items():
        rows.append({
            "filename": name,
            "status": status.get("status", "pending"),
            "pages": status.get("pages", 0),
            "chunks": status.get("chunks", 0),
            "errors": status.get("error", ""),
        })
    return rows


def render_transcript_ingestion_page(case_name: Optional[str] = None, show_title: bool = True) -> None:
    _init_state()

    if show_title:
        st.title("Transcript Ingestion")

    if not case_name:
        st.warning("Open a case before ingesting transcripts.")
        return

    uploads = st.file_uploader(
        "Upload transcript PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="transcript_uploads",
    )

    if uploads:
        for upload in uploads:
            st.session_state.transcript_status.setdefault(upload.name, {"status": "pending"})

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("Analyze uploads", key="analyze_transcripts_btn", disabled=not uploads):
            progress = st.progress(0)
            all_payloads = []
            for idx, upload in enumerate(uploads or []):
                try:
                    _log(f"Parsing {upload.name}")
                    analysis = _analyze_upload(upload)
                    st.session_state.transcript_analysis[upload.name] = analysis
                    st.session_state.transcript_status[upload.name] = {
                        "status": "parsed",
                        "pages": analysis.get("page_count", 0),
                        "chunks": 0,
                        "error": "",
                    }
                except Exception as exc:
                    st.session_state.transcript_status[upload.name] = {
                        "status": "error",
                        "pages": 0,
                        "chunks": 0,
                        "error": str(exc),
                    }
                    _log(f"Error parsing {upload.name}: {exc}")
                progress.progress((idx + 1) / max(len(uploads), 1))
            _log("Analysis complete.")

    st.subheader("Upload status")
    status_rows = _build_status_table()
    if status_rows:
        st.dataframe(status_rows, use_container_width=True)
    else:
        st.caption("No transcript uploads yet.")

    case_title = case_name or ""
    st.text_input("Case title", value=case_title, key="transcript_case_title", disabled=True)

    if case_title:
        preview = f"{sanitize_case_title(case_title)} Transcripts"
        st.caption(f"Case folder: data/transcripts/{preview}")

    all_payloads = []
    did_ingest = False
    if st.button("Ingest Transcripts", key="ingest_transcripts_btn", disabled=not uploads):
        if not case_title:
            st.error("Open a case before ingesting transcripts.")
        else:
            progress = st.progress(0)
            did_ingest = True
            for idx, upload in enumerate(uploads or []):
                try:
                    _log(f"Ingesting {upload.name}")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(upload.read())
                        tmp_path = Path(tmp.name)
                    analysis = parse_transcript_pdf(tmp_path)
                    pages = analysis.get("pages", [])
                    chunks = chunk_pages(
                        pages,
                        case_title=case_title,
                        docket_number=analysis.get("docket_number"),
                    )
                    save_source_file(BASE_TRANSCRIPTS_DIR, case_title, upload.name, upload.getvalue())
                    result = store_transcript_chunks(
                        base_dir=BASE_TRANSCRIPTS_DIR,
                        case_title=case_title,
                        docket_number=analysis.get("docket_number"),
                        source_file=upload.name,
                        chunks=chunks,
                        witness_types={},
                    )
                    all_payloads.extend(result.get("chunk_payloads", []))
                    st.session_state.transcript_status[upload.name] = {
                        "status": "ingested",
                        "pages": analysis.get("page_count", 0),
                        "chunks": result.get("chunks_saved", 0),
                        "error": "",
                    }
                    _log(f"Stored {result.get('chunks_saved', 0)} chunks for {upload.name}")
                except Exception as exc:
                    st.session_state.transcript_status[upload.name] = {
                        "status": "error",
                        "pages": 0,
                        "chunks": 0,
                        "error": str(exc),
                    }
                    _log(f"Error ingesting {upload.name}: {exc}")
                progress.progress((idx + 1) / max(len(uploads), 1))

            if did_ingest and all_payloads:
                upsert_transcript_chunks_to_chroma(
                    base_dir=BASE_TRANSCRIPTS_DIR,
                    case_title=case_title,
                    chunk_payloads=all_payloads,
                )
                _log("Transcript index updated in Chroma.")

    st.subheader("Activity log")
    if st.session_state.transcript_activity:
        st.text_area(
            "Transcript ingestion activity",
            value="\n".join(st.session_state.transcript_activity[-200:]),
            height=200,
        )
    else:
        st.caption("No activity yet.")
