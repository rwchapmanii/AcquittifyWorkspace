import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.llm.client import LLMClient
from app.core.config import get_settings
from app.core.llm.prompts import (
    PASS2_PROMPT_ID,
    PASS2_REPAIR_PROMPT_ID,
    build_pass2_prompt,
    build_pass2_repair_prompt,
)
from app.core.llm.schemas import Pass2Schema
from app.core.llm.validate import repair_json_with_llm, validate_json
from app.db.models.artifact import Artifact
from app.db.models.document import Document
from app.db.models.enums import ArtifactKind, PassStatus
from app.db.models.pass_run import PassRun
from app.storage.s3 import S3Client


def run_pass2(*, session: Session, document_id: str) -> PassRun:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")

    artifact = session.execute(
        select(Artifact).where(
            Artifact.document_id == document_id,
            Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
        )
    ).scalar_one_or_none()

    if not artifact:
        raise ValueError("Extracted text artifact not found")

    s3 = S3Client()
    extracted = _load_json(s3, artifact.uri)
    text = _join_pages(extracted)

    prompt = build_pass2_prompt(text)
    client = LLMClient()
    settings = get_settings()
    raw_text = client.complete_text(
        prompt=prompt, model=settings.llm_model, temperature=0.0
    )

    schema = Pass2Schema.model_json_schema()
    response_json = _safe_json_loads(raw_text)
    validation = validate_json(response_json, schema) if response_json else None

    if not response_json or (validation and not validation.ok):
        fail_run = _insert_pass_run(
            session=session,
            document_id=document_id,
            model_id=settings.llm_model,
            prompt_id=PASS2_PROMPT_ID,
            prompt_hash=client.prompt_hash(prompt),
            status=PassStatus.FAIL,
            output_json={"raw_text": raw_text, "error": validation.error if validation else "invalid_json"},
            input_hash=artifact.content_hash,
            is_latest=False,
        )

        repaired = repair_json_with_llm(
            raw_text=raw_text,
            schema=schema,
            model=settings.llm_repair_model,
            pass_num=2,
        )
        repaired_validation = validate_json(repaired, schema)
        if not repaired_validation.ok:
            fail_run.output_json = {
                "raw_text": raw_text,
                "error": repaired_validation.error,
            }
            session.commit()
            return fail_run

        response_json = repaired
        status = PassStatus.REPAIRED
        prompt_id = PASS2_REPAIR_PROMPT_ID
        prompt_hash = client.prompt_hash(
            build_pass2_repair_prompt(raw_text, json.dumps(schema))
        )
        model_id = settings.llm_repair_model
    else:
        status = PassStatus.SUCCESS
        prompt_id = PASS2_PROMPT_ID
        prompt_hash = client.prompt_hash(prompt)
        model_id = settings.llm_model

    parsed = Pass2Schema.model_validate(response_json)

    _clear_latest(session, document_id=document_id, pass_num=2)
    pass_run = _insert_pass_run(
        session=session,
        document_id=document_id,
        model_id=model_id,
        prompt_id=prompt_id,
        prompt_hash=prompt_hash,
        status=status,
        output_json=json.loads(parsed.model_dump_json()),
        input_hash=artifact.content_hash,
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
        pass_num=2,
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
