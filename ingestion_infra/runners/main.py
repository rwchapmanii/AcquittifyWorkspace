"""CLI entry point for CourtListener ingestion."""

from __future__ import annotations

import argparse
import logging
import time

from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.exceptions import ReadTimeoutError as BotoReadTimeoutError
from botocore.exceptions import ResponseStreamingError
from urllib3.exceptions import ReadTimeoutError as UrllibReadTimeoutError

from ingestion_infra.change_detection.hasher import hash_payload
from ingestion_infra.checkpoints.state_store import StateStore
from ingestion_infra.config import Settings
from ingestion_infra.logging_config import configure_logging
from ingestion_infra.sources.api_client import CourtListenerAPI
from ingestion_infra.sources.s3_bulk import S3BulkSource
from ingestion_infra.storage.staging_db import StagingDB

LOGGER = logging.getLogger(__name__)

ENTITIES = ["courts", "dockets", "opinion-clusters", "opinions", "opinion-texts"]
RAW_ENTITIES = {"opinion-clusters", "opinions", "opinion-texts"}


def _resolve_entities(only: list[str] | None) -> list[str]:
    if not only:
        return ENTITIES
    normalized = [value.strip() for value in only if value.strip()]
    invalid = [value for value in normalized if value not in ENTITIES]
    if invalid:
        raise ValueError(f"Unsupported entities: {', '.join(invalid)}")
    return normalized


def bulk_ingest(settings: Settings, only_entities: list[str] | None = None) -> None:
    state = StateStore(settings.state_path)
    db = StagingDB(settings.db_dsn)
    db.init_schema()

    source = S3BulkSource(settings)
    total_processed = 0

    for entity in _resolve_entities(only_entities):
        state_keys = sorted((state.state.get("bulk", {}) or {}).get(entity, {}) or {})
        try:
            keys = source.resolve_keys(entity)
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code")
            if code in {"AccessDenied", "AllAccessDisabled"}:
                if state_keys:
                    LOGGER.warning(
                        "S3 list denied for %s; using %s checkpoint key(s) from state file",
                        entity,
                        len(state_keys),
                    )
                    keys = state_keys
                else:
                    LOGGER.error(
                        "S3 list denied for %s and no checkpoint keys available; skipping entity",
                        entity,
                    )
                    continue
            else:
                raise
        for key in keys:
            LOGGER.info("Starting bulk snapshot %s for %s", key, entity)
            retries = 0
            max_retries = settings.s3_stream_max_retries
            while True:
                last_row = state.get_bulk_checkpoint(entity, key) or 0
                row_number = last_row
                start_row = last_row + 1
                if last_row:
                    LOGGER.info("Resuming %s %s from row %s", entity, key, start_row)
                try:
                    row_iter = source.iter_csv_rows(entity=entity, key=key, start_row=start_row)
                    for row_number, row in row_iter:
                        record_id = source.get_record_id(entity, row)
                        if not record_id:
                            continue
                        record_hash = hash_payload(row)
                        if entity in RAW_ENTITIES:
                            changed = db.upsert_raw_record(
                                entity_type=entity,
                                record_id=record_id,
                                record_hash=record_hash,
                                record_json=row,
                                snapshot_id=key,
                                source="bulk_csv",
                            )
                        else:
                            changed = db.upsert_record(
                                source="bulk_csv",
                                entity_type=entity,
                                record_id=record_id,
                                record_hash=record_hash,
                                record_json=row,
                                snapshot_id=key,
                            )
                        total_processed += 1
                        if total_processed % settings.checkpoint_every == 0:
                            state.set_bulk_checkpoint(entity, key, row_number)
                            state.save()
                            db.record_checkpoint("bulk_csv", entity, key, row_number)
                            LOGGER.info("Checkpointed %s %s at row %s", entity, key, row_number)
                        if changed:
                            LOGGER.debug("Detected change in %s %s", entity, record_id)
                    state.set_bulk_checkpoint(entity, key, row_number)
                    state.save()
                    db.record_checkpoint("bulk_csv", entity, key, row_number)
                    LOGGER.info("Finished bulk snapshot %s for %s", key, entity)
                    break
                except (
                    BotoReadTimeoutError,
                    UrllibReadTimeoutError,
                    ResponseStreamingError,
                    EndpointConnectionError,
                ) as exc:
                    retries += 1
                    LOGGER.warning(
                        "Timeout streaming %s %s at row %s (%s/%s): %s",
                        entity,
                        key,
                        row_number,
                        retries,
                        max_retries,
                        exc,
                    )
                    state.set_bulk_checkpoint(entity, key, row_number)
                    state.save()
                    db.record_checkpoint("bulk_csv", entity, key, row_number)
                    if retries >= max_retries:
                        raise
                    time.sleep(settings.s3_stream_retry_backoff * retries)
                    continue

    LOGGER.info("Bulk ingest completed. Total processed: %s", total_processed)

    # TODO: Trigger downstream parsing/chunking job.


def api_incremental_update(
    settings: Settings,
    since: str | None,
    only_entities: list[str] | None = None,
) -> None:
    state = StateStore(settings.state_path)
    db = StagingDB(settings.db_dsn)
    db.init_schema()

    api = CourtListenerAPI(settings)
    total_processed = 0

    for entity in _resolve_entities(only_entities):
        last_page = state.get_api_checkpoint(entity) or 1
        LOGGER.info("Starting API incremental for %s from page %s", entity, last_page)
        page_iter = api.iter_entities(entity=entity, since=since, start_page=last_page)
        for page_number, record in page_iter:
            record_id = api.get_record_id(entity, record)
            if not record_id:
                continue
            record_hash = hash_payload(record)
            changed = db.upsert_record(
                source="api",
                entity_type=entity,
                record_id=record_id,
                record_hash=record_hash,
                record_json=record,
                snapshot_id=None,
            )
            total_processed += 1
            if total_processed % settings.checkpoint_every == 0:
                state.set_api_checkpoint(entity, page_number)
                state.save()
                db.record_checkpoint("api", entity, None, page_number)
                LOGGER.info("Checkpointed %s at page %s", entity, page_number)
            if changed:
                LOGGER.debug("Detected change in %s %s", entity, record_id)
        state.set_api_checkpoint(entity, page_number)
        state.save()
        db.record_checkpoint("api", entity, None, page_number)
        LOGGER.info("Finished API incremental for %s", entity)

    LOGGER.info("API incremental completed. Total processed: %s", total_processed)

    # TODO: Trigger downstream parsing/chunking job.


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CourtListener ingestion runner")
    sub = parser.add_subparsers(dest="command", required=True)

    bulk = sub.add_parser("bulk_ingest", help="Ingest full snapshots from S3")
    bulk.add_argument(
        "--only",
        nargs="+",
        help="Limit ingestion to specific entities",
        choices=ENTITIES,
    )
    bulk.set_defaults(command="bulk_ingest")

    api = sub.add_parser("api_incremental_update", help="Ingest incremental updates from API")
    api.add_argument("--since", help="ISO date (YYYY-MM-DD) for incremental fetch")
    api.add_argument(
        "--only",
        nargs="+",
        help="Limit ingestion to specific entities",
        choices=ENTITIES,
    )
    api.set_defaults(command="api_incremental_update")

    return parser


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "bulk_ingest":
        bulk_ingest(settings, only_entities=args.only)
    elif args.command == "api_incremental_update":
        api_incremental_update(settings, since=args.since, only_entities=args.only)


if __name__ == "__main__":
    main()
