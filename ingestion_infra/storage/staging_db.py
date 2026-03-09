"""Postgres-compatible staging database interface."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any, Dict

import psycopg

LOGGER = logging.getLogger(__name__)


@dataclass
class StagingRecord:
    source: str
    entity_type: str
    record_id: str
    record_hash: str
    record_json: Dict[str, Any]
    snapshot_id: str | None


class StagingDB:
    """Staging database with idempotent upserts."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def init_schema(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS staging_records (
                        source TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        record_hash TEXT NOT NULL,
                        record_json JSONB NOT NULL,
                        snapshot_id TEXT,
                        fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (source, entity_type, record_id)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
                        source TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        object_key TEXT,
                        position BIGINT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (source, entity_type, object_key)
                    );
                    """
                )
                cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
                for table_name in ("opinion_clusters", "opinions", "opinion_texts"):
                    cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS raw.{table_name} (
                            record_id TEXT PRIMARY KEY,
                            record_hash TEXT NOT NULL,
                            record_json JSONB NOT NULL,
                            snapshot_id TEXT,
                            source TEXT NOT NULL,
                            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )
            conn.commit()

    def upsert_record(
        self,
        source: str,
        entity_type: str,
        record_id: str,
        record_hash: str,
        record_json: Dict[str, Any],
        snapshot_id: str | None,
    ) -> bool:
        """Insert or update a staging record. Returns True if changed."""
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO staging_records (
                        source, entity_type, record_id, record_hash, record_json, snapshot_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source, entity_type, record_id)
                    DO UPDATE SET
                        record_hash = EXCLUDED.record_hash,
                        record_json = EXCLUDED.record_json,
                        snapshot_id = EXCLUDED.snapshot_id,
                        fetched_at = NOW()
                    WHERE staging_records.record_hash IS DISTINCT FROM EXCLUDED.record_hash
                    RETURNING 1;
                    """,
                    (
                        source,
                        entity_type,
                        record_id,
                        record_hash,
                        json.dumps(record_json),
                        snapshot_id,
                    ),
                )
                changed = cur.fetchone() is not None
            conn.commit()
        return changed

    def upsert_raw_record(
        self,
        entity_type: str,
        record_id: str,
        record_hash: str,
        record_json: Dict[str, Any],
        snapshot_id: str | None,
        source: str,
    ) -> bool:
        """Insert or update a raw record in the raw schema. Returns True if changed."""
        def normalize_value(value: Any) -> Any:
            if value == "":
                return None
            return value

        table_name = {
            "opinion-clusters": "opinion_clusters",
            "opinions": "opinions",
            "opinion-texts": "opinion_texts",
        }.get(entity_type)
        if not table_name:
            raise ValueError(f"Unsupported raw entity type: {entity_type}")
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                if entity_type == "opinion-clusters":
                    cur.execute(
                        """
                        INSERT INTO raw.opinion_clusters (
                            id, date_filed, court_id, record_json
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            date_filed = EXCLUDED.date_filed,
                            court_id = EXCLUDED.court_id,
                            record_json = EXCLUDED.record_json,
                            updated_at = NOW()
                        WHERE raw.opinion_clusters.record_json IS DISTINCT FROM EXCLUDED.record_json
                        RETURNING 1;
                        """,
                        (
                            normalize_value(record_id),
                            normalize_value(record_json.get("date_filed")),
                            normalize_value(record_json.get("court_id")),
                            json.dumps(record_json),
                        ),
                    )
                elif entity_type == "opinions":
                    cur.execute(
                        """
                        INSERT INTO raw.opinions (
                            id,
                            cluster_id,
                            plain_text,
                            opinion_text,
                            html_with_citations,
                            html,
                            date_created,
                            record_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            cluster_id = EXCLUDED.cluster_id,
                            plain_text = EXCLUDED.plain_text,
                            opinion_text = EXCLUDED.opinion_text,
                            html_with_citations = EXCLUDED.html_with_citations,
                            html = EXCLUDED.html,
                            date_created = EXCLUDED.date_created,
                            record_json = EXCLUDED.record_json,
                            updated_at = NOW()
                        WHERE raw.opinions.record_json IS DISTINCT FROM EXCLUDED.record_json
                        RETURNING 1;
                        """,
                        (
                            normalize_value(record_id),
                            normalize_value(record_json.get("cluster_id")),
                            normalize_value(record_json.get("plain_text")),
                            normalize_value(record_json.get("opinion_text")),
                            normalize_value(record_json.get("html_with_citations")),
                            normalize_value(record_json.get("html")),
                            normalize_value(record_json.get("date_created")),
                            json.dumps(record_json),
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO raw.opinion_texts (
                            record_id, record_hash, record_json, snapshot_id, source
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (record_id)
                        DO UPDATE SET
                            record_hash = EXCLUDED.record_hash,
                            record_json = EXCLUDED.record_json,
                            snapshot_id = EXCLUDED.snapshot_id,
                            source = EXCLUDED.source,
                            ingested_at = NOW()
                        WHERE raw.opinion_texts.record_hash IS DISTINCT FROM EXCLUDED.record_hash
                        RETURNING 1;
                        """,
                        (
                            record_id,
                            record_hash,
                            json.dumps(record_json),
                            snapshot_id,
                            source,
                        ),
                    )
                changed = cur.fetchone() is not None
            conn.commit()
        return changed

    def record_checkpoint(self, source: str, entity_type: str, object_key: str | None, position: int) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_checkpoints (source, entity_type, object_key, position)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source, entity_type, object_key)
                    DO UPDATE SET position = EXCLUDED.position, updated_at = NOW();
                    """,
                    (source, entity_type, object_key, position),
                )
            conn.commit()
