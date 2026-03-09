import json
import re
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.llm.client import LLMClient
from app.core.config import get_settings
from app.core.llm.prompts import (
    PASS1_PROMPT_ID,
    PASS1_REPAIR_PROMPT_ID,
    build_pass1_prompt,
    build_pass1_repair_prompt,
)
from app.core.llm.schemas import Pass1Schema
from app.core.llm.validate import repair_json_with_llm, validate_json
from app.db.models.artifact import Artifact
from app.db.models.document import Document
from app.db.models.enums import ArtifactKind, PassStatus
from app.db.models.pass_run import PassRun
from app.services.preprocess import preprocess_document
from app.storage.s3 import S3Client


def run_pass1(*, session: Session, document_id: str) -> PassRun:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")

    artifact = _fetch_extracted_artifact(session, document_id=document_id)
    preprocess_error: str | None = None
    if not artifact:
        preprocess_error = _try_preprocess(session=session, document_id=document_id)
        artifact = _fetch_extracted_artifact(session, document_id=document_id)

    s3 = S3Client()
    extracted: dict | None = None
    if artifact:
        try:
            extracted = _load_json(s3, artifact.uri)
        except ClientError as exc:
            if not _is_missing_s3_object(exc):
                raise
            preprocess_error = _try_preprocess(session=session, document_id=document_id)
            artifact = _fetch_extracted_artifact(session, document_id=document_id)
            if artifact:
                extracted = _load_json(s3, artifact.uri)

    if extracted is None:
        extracted = {"pages": []}

    text = _join_pages(extracted)

    meta_payload = {
        "document": {
            "source_path": document.source_path,
            "original_filename": document.original_filename,
            "mime_type": document.mime_type,
            "sha256": document.sha256,
            "file_size": document.file_size,
            "page_count": document.page_count or extracted.get("page_count"),
        },
        "extracted_meta": extracted.get("meta"),
    }
    metadata_hint = json.dumps(meta_payload, ensure_ascii=False, default=str)
    prompt = build_pass1_prompt(text, metadata_hint=metadata_hint)
    settings = get_settings()
    llm_error: str | None = None
    client: LLMClient | None = None
    try:
        client = LLMClient()
    except Exception as exc:  # noqa: BLE001
        llm_error = str(exc)

    if not text.strip():
        raw_text = "{}"
        llm_error = llm_error or preprocess_error or "empty_document_text"
    elif client is None:
        raw_text = "{}"
    else:
        try:
            raw_text = client.complete_text(
                prompt=prompt, model=settings.llm_model, temperature=0.0
            )
        except Exception as exc:  # noqa: BLE001
            raw_text = "{}"
            llm_error = str(exc)

    schema = Pass1Schema.model_json_schema()
    response_json = _safe_json_loads(raw_text) or {}
    validation = validate_json(response_json, schema)

    status = PassStatus.SUCCESS
    prompt_id = PASS1_PROMPT_ID
    prompt_hash = LLMClient.prompt_hash(prompt)
    model_id = settings.llm_model

    if llm_error or not validation.ok:
        _insert_pass_run(
            session=session,
            document_id=document_id,
            model_id=settings.llm_model,
            prompt_id=PASS1_PROMPT_ID,
            prompt_hash=prompt_hash,
            status=PassStatus.FAIL,
            output_json={
                "raw_text": raw_text,
                "error": llm_error or validation.error or "invalid_json",
            },
            input_hash=artifact.content_hash if artifact else "",
            is_latest=False,
        )

        if not llm_error:
            try:
                repaired = repair_json_with_llm(
                    raw_text=raw_text,
                    schema=schema,
                    model=settings.llm_repair_model,
                    pass_num=1,
                )
                repaired_validation = validate_json(repaired, schema)
            except Exception as exc:  # noqa: BLE001
                repaired = {}
                repaired_validation = validate_json(repaired, schema)
            if repaired_validation.ok:
                response_json = repaired
                status = PassStatus.REPAIRED
                prompt_id = PASS1_REPAIR_PROMPT_ID
                prompt_hash = LLMClient.prompt_hash(
                    build_pass1_repair_prompt(raw_text, json.dumps(schema))
                )
                model_id = settings.llm_repair_model
            else:
                status = PassStatus.REPAIRED
        else:
            status = PassStatus.REPAIRED

    text_snippet = _build_text_snippet(extracted)
    response_json = _normalize_pass1_response(
        document=document,
        extracted=extracted,
        response_json=response_json,
        text_snippet=text_snippet,
    )
    parsed = Pass1Schema.model_validate(response_json)

    _clear_latest(session, document_id=document_id, pass_num=1)
    pass_run = _insert_pass_run(
        session=session,
        document_id=document_id,
        model_id=model_id,
        prompt_id=prompt_id,
        prompt_hash=prompt_hash,
        status=status,
        output_json=json.loads(parsed.model_dump_json()),
        input_hash=artifact.content_hash if artifact else "",
        is_latest=True,
    )
    return pass_run


def _insert_pass_run(
    *,
    session: Session,
    document_id: str,
    model_id: str,
    prompt_id: str,
    prompt_hash: str,
    status: PassStatus,
    output_json: dict,
    input_hash: str,
    is_latest: bool,
) -> PassRun:
    pass_run = PassRun(
        document_id=document_id,
        pass_num=1,
        model_id=model_id,
        model_version="",
        prompt_id=prompt_id,
        prompt_hash=prompt_hash,
        settings_json={"temperature": 0.0},
        input_artifact_hashes_json={"extracted_text": input_hash},
        output_json=output_json,
        status=status,
        created_at=datetime.now(timezone.utc),
        is_latest=is_latest,
    )
    session.add(pass_run)
    session.commit()
    return pass_run


def _clear_latest(session: Session, *, document_id: str, pass_num: int) -> None:
    session.execute(
        update(PassRun)
        .where(PassRun.document_id == document_id, PassRun.pass_num == pass_num)
        .values(is_latest=False)
    )
    session.commit()


def _safe_json_loads(raw_text: str) -> dict | None:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None




def _load_json(s3: S3Client, uri: str) -> dict:
    if not uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI")
    parts = uri.replace("s3://", "", 1).split("/", 1)
    bucket = parts[0]
    key = parts[1]
    data = s3.get_bytes(bucket=bucket, key=key).decode("utf-8")
    return json.loads(data)


def _join_pages(extracted: dict) -> str:
    pages = extracted.get("pages", [])
    return "\n\n".join(page.get("text", "") for page in pages)


def _build_text_snippet(extracted: dict, max_chars: int = 4000) -> str:
    text = _join_pages(extracted)
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) > max_chars:
        return normalized[:max_chars]
    return normalized


def _is_missing_s3_object(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = str(error.get("Code", "")).lower()
    return code in {"nosuchkey", "404", "notfound"}


def _fetch_extracted_artifact(session: Session, *, document_id: str) -> Artifact | None:
    return session.execute(
        select(Artifact)
        .where(
            Artifact.document_id == document_id,
            Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _try_preprocess(*, session: Session, document_id: str) -> str | None:
    try:
        preprocess_document(session=session, document_id=document_id)
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _ensure_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None:
        items = []
    else:
        items = [value]

    result: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            result.append(item)
        else:
            result.append(str(item))
    return result


def _normalize_pass1_response(
    *,
    document: Document,
    extracted: dict,
    response_json: dict | None,
    text_snippet: str | None = None,
) -> dict:
    payload = response_json if isinstance(response_json, dict) else {}
    extracted_meta = extracted.get("meta") if isinstance(extracted, dict) else None

    doc_identity = payload.get("doc_identity") or {}
    doc_identity.setdefault("source_path", document.source_path)
    doc_identity.setdefault("original_filename", document.original_filename)
    doc_identity.setdefault("mime_type", document.mime_type)
    doc_identity.setdefault("sha256", document.sha256)
    doc_identity.setdefault("file_size", document.file_size)
    doc_identity.setdefault("page_count", document.page_count)
    doc_identity.setdefault("doc_title", None)
    doc_identity.setdefault("email_subject", None)
    doc_identity.setdefault("email_message_id", None)
    doc_identity.setdefault("source_system", None)
    doc_identity.setdefault("custodian", None)

    if isinstance(extracted_meta, dict):
        email_meta = extracted_meta.get("email")
        if isinstance(email_meta, dict):
            if doc_identity.get("email_subject") is None:
                doc_identity["email_subject"] = email_meta.get("subject")
            if doc_identity.get("email_message_id") is None:
                doc_identity["email_message_id"] = email_meta.get("message_id")
        pdf_meta = extracted_meta.get("pdf_metadata")
        if isinstance(pdf_meta, dict) and doc_identity.get("doc_title") is None:
            doc_identity["doc_title"] = pdf_meta.get("title") or pdf_meta.get("Title")
        docx_meta = extracted_meta.get("docx_properties")
        if isinstance(docx_meta, dict) and doc_identity.get("doc_title") is None:
            doc_identity["doc_title"] = docx_meta.get("title")
        if doc_identity.get("source_system") is None:
            if document.source_path.startswith("s3://"):
                doc_identity["source_system"] = "local_upload"
            else:
                doc_identity["source_system"] = "external"

    doc_type = payload.get("doc_type") or {}
    if not doc_type.get("category") or doc_type.get("category") == "OTHER":
        doc_type["category"] = _guess_doc_type_category(document)
    doc_type.setdefault("draft_final", "UNKNOWN")
    doc_type.setdefault("internal_external", "UNKNOWN")
    doc_type.setdefault("domain", "UNKNOWN")

    time = payload.get("time") or {}
    time.setdefault("system_created_at", None)
    time.setdefault("system_modified_at", None)
    time.setdefault("sent_at", None)
    time["dates_mentioned"] = _ensure_str_list(time.get("dates_mentioned"))

    entities_raw = payload.get("entities_raw") or {}
    entities_raw = {
        "people_mentioned": _ensure_str_list(entities_raw.get("people_mentioned")),
        "orgs_mentioned": _ensure_str_list(entities_raw.get("orgs_mentioned")),
    }

    quality = payload.get("quality") or {}
    ocr_used = quality.get("ocr_used")
    if not isinstance(ocr_used, bool):
        ocr_used = any(
            bool(page.get("ocr_used"))
            for page in extracted.get("pages", [])
            if isinstance(page, dict)
        )
    quality = {
        "ocr_used": ocr_used,
        "ocr_confidence_overall": quality.get("ocr_confidence_overall"),
        "parsing_confidence_overall": quality.get("parsing_confidence_overall"),
    }

    authorship = payload.get("authorship_transmission")
    if isinstance(authorship, dict):
        authorship = {
            "author_names": _ensure_str_list(authorship.get("author_names")),
            "sender": authorship.get("sender"),
            "recipients_to": _ensure_str_list(authorship.get("recipients_to")),
            "recipients_cc": _ensure_str_list(authorship.get("recipients_cc")),
            "recipients_bcc": _ensure_str_list(authorship.get("recipients_bcc")),
            "organizations": _ensure_str_list(authorship.get("organizations")),
        }
    else:
        authorship = None

    document_type = payload.get("document_type")
    if document_type is None:
        document_type = doc_type.get("category")
    if isinstance(document_type, (dict, list)):
        document_type = None

    witnesses = payload.get("witnesses")
    if isinstance(witnesses, str):
        witnesses = [item.strip() for item in witnesses.split(",") if item.strip()]
    elif not isinstance(witnesses, list):
        witnesses = []

    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return None

    document_date = _string_or_none(payload.get("document_date") or payload.get("date"))
    relevance = _string_or_none(payload.get("relevance"))
    proponent = _string_or_none(payload.get("proponent"))
    if proponent is None and isinstance(authorship, dict):
        proponent = _string_or_none(authorship.get("sender"))
        if proponent is None:
            authors = authorship.get("author_names") if isinstance(authorship, dict) else None
            if isinstance(authors, list) and authors:
                proponent = _string_or_none(authors[0])

    if not witnesses and text_snippet:
        witnesses = _infer_witnesses(text_snippet, document.original_filename)
    if not witnesses:
        people = entities_raw.get("people_mentioned") if isinstance(entities_raw, dict) else None
        if isinstance(people, list) and people:
            witnesses = people
        elif isinstance(authorship, dict):
            authors = authorship.get("author_names")
            if isinstance(authors, list) and authors:
                witnesses = authors

    if not relevance or str(relevance).strip().lower() == "unknown":
        relevance = _infer_relevance(document, text_snippet)
    if not proponent or str(proponent).strip().lower() == "unknown":
        proponent = _infer_proponent(document, text_snippet)
    if proponent is None:
        proponent = "Unknown"

    if document_date is None:
        document_date = _infer_document_date(text_snippet, document.original_filename)

    identity_confidence = payload.get("identity_confidence")
    if not isinstance(identity_confidence, (int, float)):
        identity_confidence = None

    identity_evidence = payload.get("identity_evidence")
    if isinstance(identity_evidence, list):
        identity_evidence = [str(item) for item in identity_evidence if item is not None]
    elif identity_evidence is None:
        identity_evidence = []
    else:
        identity_evidence = [str(identity_evidence)]

    return {
        "doc_identity": doc_identity,
        "doc_type": doc_type,
        "authorship_transmission": authorship,
        "time": time,
        "entities_raw": entities_raw,
        "quality": quality,
        "document_type": document_type,
        "witnesses": witnesses,
        "document_date": document_date,
        "relevance": relevance,
        "proponent": proponent,
        "identity_confidence": identity_confidence,
        "identity_evidence": identity_evidence,
    }


def _guess_doc_type_category(document: Document) -> str:
    filename = document.original_filename.lower()
    mime = (document.mime_type or "").lower()
    if mime == "application/pdf" or filename.endswith(".pdf"):
        return "PDF"
    if filename.endswith(".eml"):
        return "EMAIL"
    if filename.endswith(".docx") or filename.endswith(".doc"):
        return "WORD"
    if filename.endswith(".xlsx") or filename.endswith(".xls") or filename.endswith(".csv"):
        return "SPREADSHEET"
    if filename.endswith(".pptx") or filename.endswith(".ppt"):
        return "PRESENTATION"
    if filename.endswith(".txt"):
        return "TEXT"
    if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".heic")):
        return "IMAGE"
    return "OTHER"


def _infer_relevance(document: Document, text_snippet: str | None = None) -> str:
    name = (document.original_filename or "").lower()
    haystack = f"{name}\n{text_snippet or ''}".lower()
    high_tokens = (
        "motion",
        "order",
        "warrant",
        "indict",
        "judgment",
        "sentence",
        "sentencing",
        "plea",
        "response",
        "opposition",
        "brief",
        "suppression",
        "transcript",
        "testimony",
    )
    medium_tokens = (
        "memo",
        "memorandum",
        "report",
        "evaluation",
        "psr",
        "presentence",
        "affidavit",
        "declaration",
        "statement",
        "interview",
        "investigation",
    )
    if any(token in haystack for token in high_tokens):
        return "High"
    if any(token in haystack for token in medium_tokens):
        return "Medium"
    return "Unknown"


def _infer_proponent(document: Document, text_snippet: str | None = None) -> str | None:
    name = (document.original_filename or "").lower()
    haystack = f"{name}\n{text_snippet or ''}".lower()
    if any(
        token in haystack
        for token in (
            "gov",
            "government",
            "u.s.",
            "usa",
            "united states",
            "prosecution",
            "district attorney",
            "u.s. attorney",
            "assistant u.s. attorney",
            "people of",
            "state of",
        )
    ):
        return "Government"
    if any(
        token in haystack
        for token in (
            "defense",
            "defendant",
            "def.",
            "public defender",
            "counsel for defendant",
            "attorney for defendant",
        )
    ):
        return "Defense"
    return None


def _infer_document_date(text_snippet: str | None, filename: str | None) -> str | None:
    text = text_snippet or ""
    if filename:
        text = f"{text} {filename}"

    ymd_match = re.search(
        r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b",
        text,
    )
    if ymd_match:
        year, month, day = ymd_match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    mdy_match = re.search(
        r"\b(0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])[/-](20\d{2})\b",
        text,
    )
    if mdy_match:
        month, day, year = mdy_match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    month_match = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s*(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if month_match:
        month_name, day, year = month_match.groups()
        month_map = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        key = month_name.lower()
        month = month_map.get(key)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    return None


def _infer_witnesses(text_snippet: str, filename: str | None = None) -> list[str]:
    if not text_snippet:
        text_snippet = ""

    stop_phrases = {
        "united states",
        "district court",
        "court",
        "government",
        "defendant",
        "plaintiff",
        "state",
        "department",
        "office",
        "county",
        "city",
    }

    generic_tokens = {
        "motion",
        "mtn",
        "response",
        "opposition",
        "order",
        "memorandum",
        "memo",
        "report",
        "evaluation",
        "exhibit",
        "statement",
        "affidavit",
        "declaration",
        "brief",
        "warrant",
        "warrants",
        "indictment",
        "judgment",
        "sentence",
        "sentencing",
        "govt",
        "govts",
        "government",
        "defense",
        "defendant",
        "plaintiff",
        "case",
        "court",
        "district",
        "vacate",
        "modify",
        "seizure",
        "seal",
    }

    def is_stop_name(name: str) -> bool:
        lowered = name.lower()
        return any(phrase in lowered for phrase in stop_phrases)

    def clean_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z\\-\\s']", " ", name)
        cleaned = " ".join(cleaned.split())
        return cleaned

    def add_candidate(name: str, results: list[str]) -> None:
        cleaned = clean_name(name)
        if not cleaned or is_stop_name(cleaned):
            return
        if cleaned not in results:
            results.append(cleaned)

    results: list[str] = []

    keyword_pattern = re.compile(
        r"(?:witness|deponent|affiant|declarant|testimony|deposition|affidavit|declaration|statement)"
        r"(?:\\s+of|\\s+by)?\\s+([A-Z][A-Za-z'\\-]+(?:\\s+[A-Z][A-Za-z'\\-]+){1,3})",
        re.IGNORECASE,
    )
    for match in keyword_pattern.finditer(text_snippet):
        add_candidate(match.group(1), results)
        if len(results) >= 5:
            return results

    title_pattern = re.compile(
        r"\\b(?:Dr|Mr|Ms|Mrs|Judge|Hon|Officer|Detective|Agent|Special Agent)\\.?"
        r"\\s+([A-Z][A-Za-z'\\-]+(?:\\s+[A-Z][A-Za-z'\\-]+){0,2})"
    )
    for match in title_pattern.finditer(text_snippet):
        add_candidate(match.group(1), results)
        if len(results) >= 5:
            return results

    general_pattern = re.compile(
        r"\\b([A-Z][A-Za-z'\\-]+(?:\\s+[A-Z][A-Za-z'\\-]+){1,3})\\b"
    )
    for match in general_pattern.finditer(text_snippet):
        add_candidate(match.group(1), results)
        if len(results) >= 5:
            break

    if not results and filename:
        base = filename.rsplit(".", 1)[0]
        base = re.sub(r"[\\(\\)\\[\\]{}]", " ", base)
        base = re.sub(r"[_\\-]+", " ", base)
        for token in re.split(r"[^A-Za-z']+", base):
            if not token or len(token) < 3:
                continue
            token_lower = token.lower()
            if token_lower.endswith("'s"):
                token_lower = token_lower[:-2]
            if token_lower in generic_tokens:
                continue
            if token[0].isupper():
                add_candidate(token, results)
                if results:
                    break

    return results
