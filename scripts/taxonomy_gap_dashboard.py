#!/usr/bin/env python3
import json
import os
from pathlib import Path

import psycopg
import streamlit as st

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"
BASE_DIR = Path(__file__).resolve().parents[1]


def _connect():
    dsn = os.getenv("COURTLISTENER_DB_DSN") or DEFAULT_DSN
    return psycopg.connect(dsn)


def _load_aliases() -> list[dict]:
    alias_path = BASE_DIR / "taxonomy" / "2026.01" / "aliases.yaml"
    if not alias_path.exists():
        return []
    data = alias_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in data.splitlines() if line.strip() and not line.strip().startswith("#")]
    aliases = []
    current = {}
    for line in lines:
        if line.startswith("version:"):
            current["version"] = line.split(":", 1)[1].strip().strip('"')
            continue
        if line.startswith("aliases:"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            aliases.append({"old_code": key.strip(), "new_code": value.strip()})
    return aliases


st.set_page_config(page_title="Taxonomy Gap Dashboard", layout="wide")

st.title("Taxonomy Gap Dashboard (Read-only)")

with _connect() as conn:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        st.header("Section 1 — Active Taxonomy Gaps")
        cur.execute(
            """
            SELECT
                fallback_code,
                domain,
                freq_30d,
                freq_90d,
                avg_primary_confidence,
                common_phrases,
                dominant_posture,
                circuits,
                status,
                last_event_at
            FROM derived.taxonomy_review_queue
            ORDER BY freq_30d DESC, freq_90d DESC, last_event_at DESC
            """
        )
        rows = cur.fetchall()
        st.dataframe(rows)

        st.header("Section 2 — High-Ambiguity Classifications")
        cur.execute(
            """
            SELECT
                created_at,
                primary_code,
                primary_confidence,
                top_candidate_code,
                top_candidate_confidence,
                second_candidate_code,
                second_candidate_confidence,
                input_text
            FROM derived.taxonomy_gap_event
            WHERE 'CLOSE_COMPETITION' = ANY(gap_reasons)
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
        st.dataframe(cur.fetchall())

        st.header("Section 3 — Expert Overrides")
        st.caption("No override data source configured.")

        st.header("Section 4 — Recent Taxonomy Changes")
        cur.execute(
            """
            SELECT version, COUNT(*) AS node_count
            FROM derived.taxonomy_node
            GROUP BY version
            ORDER BY version DESC
            """
        )
        st.subheader("Taxonomy Versions")
        st.dataframe(cur.fetchall())

        st.subheader("Alias Mappings")
        st.dataframe(_load_aliases())
