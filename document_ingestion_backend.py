import json
import tempfile
import hashlib
import os
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import chromadb
import requests
from chromadb.config import Settings

from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID
from acquittify.chunking import chunk_text as chunk_text_impl, chunk_text_with_offsets
from acquittify.chroma_utils import get_or_create_collection, upsert_or_add
from acquittify.ingest.metadata_utils import augment_chunk_metadata
OLLAMA_URL = os.getenv("ACQUITTIFY_INGESTION_OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("ACQUITTIFY_INGESTION_MODEL", "qwen-acquittify-ingestion14b")

ALLOWED_METADATA_FIELDS = {
    "title",
    "path",
    "chunk_index",
    "source_type",
    "taxonomy",
    "doc_id",
    "document_type",
    "case",
    "date",
    "witnesses",
    "bates_number",
    "case_name",
    "parties",
    "source",
    "author",
    "statutes_or_rules_cited",
    "evidence_type",
    "summary_of_document",
    "keywords",
    "section_headings",
    "custodian",
    "collection_source",
    "document_role",
    "confidentiality_level",
    "privilege_type",
    "relevance_rating",
    "issue_tags",
    "chronology_position",
    "potential_use",
    "linked_entities",
    "mentions_defendant",
    "mentions_key_witness",
    "redaction_required",
    "language",
    "citations",
    "bluebook_citations",
    "bluebook_case_citations",
    "statutes",
    "bluebook_statutes",
    "rules",
    "citation_count",
    "bluebook_citation_count",
    "bluebook_case_citation_count",
    "statute_count",
    "bluebook_statute_count",
    "rule_count",
    "authority_weight",
    "court",
    "court_level",
    "year",
    "document_citation",
    "legal_area",
    "legal_areas_flat",
    "authority_tier",
    "binding_circuit",
    "case_citation_method",
    "case_citation_is_synthetic",
    "char_start",
    "char_end",
    "file_hash",
    "original_filename",
    "reporter_slug",
    "volume",
    "page",
    "decision_date",
    "docket_number",
    "cap_id",
    "opinion_text_type",
    "download_url",
    "sha256_raw_file",
    "taxonomy_version",
    "taxonomy_agent",
    "stage",
}

try:
    from taxonomy_embedding_agent import (
        extract_pdf_text,
        chunk_text,
        ingest_new_documents,
        analyze_chunk,
        infer_source_type,
        build_metadata,
        embedding_model,
    )
except Exception:
    from pypdf import PdfReader
    from sentence_transformers import SentenceTransformer

    def extract_pdf_text(path: Path) -> str:
        try:
            reader = PdfReader(str(path))
        except Exception:
            return ""
        pages = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages).strip()

    def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 400):
        del chunk_size, overlap
        return chunk_text_impl(text)

    def ingest_new_documents(paths):
        return None

    def analyze_chunk(chunk: str):
        return {}

    def infer_source_type(path: Path) -> str:
        return "Unknown"

    def build_metadata(doc_id: str, title: str, chunk_index: int, taxonomy: dict):
        meta = {"title": title, "chunk_index": chunk_index}
        meta.update(taxonomy or {})
        return meta

    embedding_model = SentenceTransformer(EMBEDDING_MODEL_ID)


def _chunk_with_optional_offsets(text: str):
    if os.getenv("ACQ_CHUNK_WITH_OFFSETS") == "1":
        payloads = chunk_text_with_offsets(text)
        chunks = [p.get("text", "") for p in payloads]
        return chunks, payloads
    return chunk_text(text), None

def process_uploaded_pdf(uploaded_file, case_name, add_to_chroma):
    # Save uploaded file to a temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = Path(tmp.name)
    # Extract text and chunk
    text = extract_pdf_text(tmp_path)
    if not text:
        return False, "Could not extract text from PDF."
    chunks, _ = _chunk_with_optional_offsets(text)
    # Save to case-specific corpus directory
    case_dir = Path("Corpus/Processed") / case_name.replace(" ", "_")
    case_dir.mkdir(parents=True, exist_ok=True)
    for i, chunk in enumerate(chunks):
        with open(case_dir / f"chunk_{i}.txt", "w", encoding="utf-8") as f:
            f.write(chunk)
    # Optionally ingest to Chroma
    if add_to_chroma:
        ingest_new_documents([tmp_path])
    return True, f"Document processed. {len(chunks)} chunks created.{' Added to Chroma.' if add_to_chroma else ''}"


def _ingest_case_chroma(pdf_path: Path, chroma_dir: Path, case_name: str) -> None:
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    text = extract_pdf_text(pdf_path)
    if not text:
        return
    file_hash = _hash_file(pdf_path)
    chunks, offsets = _chunk_with_optional_offsets(text)
    source_type = infer_source_type(pdf_path)
    title = pdf_path.stem.replace("_", " ")
    embeddings = _encode_embeddings(chunks)
    if embeddings is None:
        raise RuntimeError("Embedding model unavailable; cannot store vectors.")

    ids = []
    metadatas = []
    case_slug = case_name.replace(" ", "_")
    for i, chunk in enumerate(chunks):
        doc_id = f"{case_slug}_{pdf_path.stem}_{i}"
        taxonomy = analyze_chunk(chunk)
        meta = build_metadata(doc_id, title, i, taxonomy)
        meta.update({
            "title": title,
            "source_type": source_type,
            "path": str(pdf_path),
            "case_name": case_name,
            "file_hash": file_hash,
            "original_filename": pdf_path.name,
        })
        if offsets and i < len(offsets):
            meta["char_start"] = offsets[i].get("char_start")
            meta["char_end"] = offsets[i].get("char_end")
        meta = augment_chunk_metadata(meta, chunk)
        ids.append(doc_id)
        metadatas.append(_clean_metadata(meta))

    batch_size = 1000
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        if embeddings is None:
            continue
        upsert_or_add(
            collection,
            ids=ids[i:end],
            documents=chunks[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end]
        )

    try:
        doc_dir = chroma_dir / "documents" / pdf_path.stem
        doc_dir.mkdir(parents=True, exist_ok=True)
        for i, chunk in enumerate(chunks):
            (doc_dir / f"chunk_{i}.txt").write_text(chunk, encoding="utf-8")
        (doc_dir / "metadatas.json").write_text(json.dumps(metadatas), encoding="utf-8")
        np.save(doc_dir / "embeddings.npy", np.array(embeddings, dtype=object), allow_pickle=True)
    except Exception:
        pass

    try:
        client.persist()
    except AttributeError:
        pass


def process_uploaded_pdf_for_case(uploaded_file, case_name: str, case_root: Path):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = Path(tmp.name)

    text = extract_pdf_text(tmp_path)
    if not text:
        return False, "Could not extract text from PDF."

    file_hash = _hash_file(tmp_path)
    if _has_duplicate_file(collection, file_hash):
        return False, f"Duplicate file detected (hash match): {uploaded_file.name}"

    chunks, _ = _chunk_with_optional_offsets(text)

    documents_dir = case_root / "documents"
    processed_dir = case_root / "processed"
    chroma_dir = case_root / "chroma"
    documents_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    original_name = uploaded_file.name
    saved_pdf = documents_dir / original_name
    saved_pdf.write_bytes(tmp_path.read_bytes())

    for i, chunk in enumerate(chunks):
        (processed_dir / f"chunk_{i}.txt").write_text(chunk, encoding="utf-8")

    _ingest_case_chroma(saved_pdf, chroma_dir, case_name)

    return True, f"Document processed. {len(chunks)} chunks created for case."


def _call_ollama(messages: List[Dict], timeout: int = 120) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _encode_embeddings(chunks: List[str]) -> list | None:
    if embedding_model is None:
        return None
    try:
        return embedding_model.encode(chunks, batch_size=64, show_progress_bar=False).tolist()
    except Exception:
        return None


def _clean_metadata(meta: Dict) -> Dict:
    if not isinstance(meta, dict):
        return {}
    cleaned = {}
    for key, value in meta.items():
        if key not in ALLOWED_METADATA_FIELDS:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if isinstance(value, (list, dict)):
            cleaned[key] = json.dumps(value, ensure_ascii=False)
            continue
        cleaned[key] = value
    return cleaned


def _hash_file(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _has_duplicate_file(collection, file_hash: str) -> bool:
    try:
        res = collection.get(where={"file_hash": file_hash}, limit=1)
        ids = res.get("ids") or []
        return bool(ids)
    except Exception:
        return False


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_v{i}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:8]}{suffix}")


def _is_safe_zip_member(member: str) -> bool:
    if not member:
        return False
    if member.startswith("/") or member.startswith("\\"):
        return False
    parts = Path(member).parts
    if any(part in {"..", "~"} for part in parts):
        return False
    return True


def _extract_zip_safe(zip_path: Path, dest_dir: Path) -> List[Path]:
    extracted: List[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if not _is_safe_zip_member(member):
                continue
            target = dest_dir / member
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                dst.write(src.read())
            extracted.append(target)
    return extracted


def _ingest_case_pdf(
    *,
    source_path: Path,
    original_name: str,
    case_name: str,
    case_root: Path,
    document_type: str,
    collection,
) -> Dict:
    text = extract_pdf_text(source_path)
    if not text:
        return {"filename": original_name, "status": "error", "message": "Could not extract text from PDF."}

    file_hash = _hash_file(source_path)
    if _has_duplicate_file(collection, file_hash):
        return {"filename": original_name, "status": "duplicate", "message": "Duplicate file detected (hash match)."}

    summary, doc_metadata = summarize_and_extract_metadata(text, document_type, case_name)
    chunks, offsets = _chunk_with_optional_offsets(text)
    if not chunks:
        return {"filename": original_name, "status": "error", "message": "No text chunks created from document."}

    documents_dir = case_root / "documents"
    processed_dir = case_root / "processed"
    documents_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    saved_pdf = _unique_path(documents_dir / original_name)
    saved_pdf.write_bytes(source_path.read_bytes())

    doc_stem = saved_pdf.stem.replace(" ", "_")
    doc_processed_dir = processed_dir / doc_stem
    doc_processed_dir.mkdir(parents=True, exist_ok=True)
    (doc_processed_dir / "summary.txt").write_text(summary or "", encoding="utf-8")
    (doc_processed_dir / "metadata.json").write_text(json.dumps(doc_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    embeddings = _encode_embeddings(chunks)
    if embeddings is None:
        return {"filename": original_name, "status": "error", "message": "Embedding model unavailable; cannot store vectors."}

    taxonomy_seed = "\n\n".join(chunks[:3])
    doc_taxonomy = analyze_chunk(taxonomy_seed) if taxonomy_seed else {}

    ids = []
    metadatas = []
    case_slug = case_name.replace(" ", "_")
    doc_type_slug = document_type.replace(" ", "_").lower()
    doc_metadata["file_hash"] = file_hash
    doc_metadata["original_filename"] = original_name

    for i, chunk in enumerate(chunks):
        (doc_processed_dir / f"chunk_{i}.txt").write_text(chunk, encoding="utf-8")
        doc_id = f"{case_slug}_{doc_type_slug}_{doc_stem}_{i}"
        taxonomy = doc_taxonomy
        meta = _build_chunk_metadata(
            doc_metadata,
            title=saved_pdf.stem.replace("_", " "),
            path=str(saved_pdf),
            chunk_index=i,
            document_type=document_type,
            case_name=case_name,
            taxonomy=taxonomy,
        )
        if offsets and i < len(offsets):
            meta["char_start"] = offsets[i].get("char_start")
            meta["char_end"] = offsets[i].get("char_end")
        meta = augment_chunk_metadata(meta, chunk)
        ids.append(doc_id)
        metadatas.append(_clean_metadata(meta))

    batch_size = 1000
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        upsert_or_add(
            collection,
            ids=ids[i:end],
            documents=chunks[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end],
        )

    result = {"filename": original_name, "status": "ingested", "chunks": len(chunks)}
    if saved_pdf.name != original_name:
        result["saved_as"] = saved_pdf.name
    return result


def _fallback_summary(text: str, max_chars: int = 800) -> str:
    snippet = " ".join(text.strip().split())
    if not snippet:
        return ""
    return snippet[:max_chars].rstrip()


def _extract_section_headings(text: str, max_headings: int = 12) -> List[str]:
    headings = []
    for line in text.splitlines():
        cleaned = " ".join(line.strip().split())
        if not cleaned:
            continue
        if len(cleaned) > 80:
            continue
        if cleaned.isupper() and any(ch.isalpha() for ch in cleaned):
            headings.append(cleaned.title())
        if len(headings) >= max_headings:
            break
    return headings


def summarize_and_extract_metadata(text: str, document_type: str, case_name: str) -> Tuple[str, Dict]:
    trimmed = text[:12000]
    prompt = (
        "You are a legal document analyst. "
        "Return ONLY valid JSON. "
        "Extract metadata ONLY if explicitly stated or directly inferable with high confidence. "
        "If uncertain, omit the field entirely. Do NOT guess. "
        "Use snake_case keys from the provided schema. "
        "If the document is not in English, set language. "
        "Provide a concise, legally meaningful summary in summary_of_document when possible. "
        "Omit any field that is not supported by the text. "
        "Required fields must be included exactly as provided: document_type and case. "
        "Schema keys: document_type, case, date, witnesses, bates_number, case_name, parties, source, author, "
        "statutes_or_rules_cited, evidence_type, summary_of_document, keywords, custodian, collection_source, "
        "document_role, confidentiality_level, privilege_type, relevance_rating, issue_tags, chronology_position, "
        "potential_use, linked_entities, mentions_defendant, mentions_key_witness, redaction_required, language.\n\n"
        f"document_type: {document_type}\n"
        f"case: {case_name}\n\n"
        "Document text:\n"
        f"{trimmed}"
    )

    metadata = {}
    summary = ""
    try:
        content = _call_ollama([
            {"role": "system", "content": "You output only JSON, no prose."},
            {"role": "user", "content": prompt},
        ])
        metadata = json.loads(content)
    except Exception:
        metadata = {}

    metadata = _clean_metadata(metadata)
    metadata["document_type"] = document_type
    metadata["case"] = case_name
    metadata.setdefault("case_name", case_name)

    headings = _extract_section_headings(text)
    if headings and "section_headings" not in metadata:
        metadata["section_headings"] = headings

    summary = metadata.get("summary_of_document", "")
    if not summary:
        summary = _fallback_summary(text)
        if summary:
            metadata["summary_of_document"] = summary

    return summary, metadata


def _build_chunk_metadata(
    base_meta: Dict,
    title: str,
    path: str,
    chunk_index: int,
    document_type: str,
    case_name: str,
    taxonomy: Dict,
) -> Dict:
    meta = dict(base_meta)
    meta.update(
        {
            "title": title,
            "path": path,
            "chunk_index": chunk_index,
            "source_type": document_type,
            "document_type": document_type,
            "case": case_name,
            "case_name": case_name,
        }
    )
    if taxonomy:
        meta["taxonomy"] = json.dumps(taxonomy)
    return _clean_metadata(meta)


def process_case_record_uploads(
    uploaded_files: List,
    case_name: str,
    case_root: Path,
    document_type: str,
) -> List[Dict]:
    results = []
    chroma_dir = case_root / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    for uploaded_file in uploaded_files:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = Path(tmp.name)
            result = _ingest_case_pdf(
                source_path=tmp_path,
                original_name=uploaded_file.name,
                case_name=case_name,
                case_root=case_root,
                document_type=document_type,
                collection=collection,
            )
            results.append(result)
        except Exception as exc:
            results.append({"filename": uploaded_file.name, "status": "error", "message": str(exc)})
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    try:
        client.persist()
    except AttributeError:
        pass

    return results


def process_case_record_paths(
    pdf_paths: List[Path],
    case_name: str,
    case_root: Path,
    document_type: str,
) -> List[Dict]:
    results = []
    chroma_dir = case_root / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

    for path in pdf_paths:
        if not path.exists() or path.suffix.lower() != ".pdf":
            results.append({"filename": path.name, "status": "error", "message": "File not found or not a PDF."})
            continue
        try:
            result = _ingest_case_pdf(
                source_path=path,
                original_name=path.name,
                case_name=case_name,
                case_root=case_root,
                document_type=document_type,
                collection=collection,
            )
            results.append(result)
        except Exception as exc:
            results.append({"filename": path.name, "status": "error", "message": str(exc)})

    try:
        client.persist()
    except AttributeError:
        pass

    return results


def process_case_record_zip(
    uploaded_file,
    case_name: str,
    case_root: Path,
    document_type: str,
) -> List[Dict]:
    results: List[Dict] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        zip_path = tmp_dir_path / "upload.zip"
        zip_path.write_bytes(uploaded_file.read())

        extracted = _extract_zip_safe(zip_path, tmp_dir_path / "extracted")
        pdf_paths = [p for p in extracted if p.suffix.lower() == ".pdf"]
        if not pdf_paths:
            return [{"filename": getattr(uploaded_file, "name", "upload.zip"), "status": "error", "message": "No PDF files found in ZIP."}]

        results.extend(
            process_case_record_paths(
                pdf_paths=pdf_paths,
                case_name=case_name,
                case_root=case_root,
                document_type=document_type,
            )
        )

    return results
