#!/usr/bin/env python3
import argparse
import os

import psycopg

DEFAULT_DSN = "postgresql://acquittify@localhost:5432/courtlistener"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply taxonomy review decision")
    parser.add_argument("--queue-id", type=int, required=True)
    parser.add_argument("--action", required=True, choices=["ADD_NODE", "ADD_SYNONYMS_ONLY", "DEFER", "REJECT"])
    parser.add_argument("--by", required=True, help="Reviewer identifier")
    parser.add_argument("--notes", default=None)
    parser.add_argument("--confirm-distinct", action="store_true")
    parser.add_argument("--confirm-nonredundant", action="store_true")
    parser.add_argument("--confirm-defense-utility", action="store_true")
    args = parser.parse_args()

    dsn = os.getenv("COURTLISTENER_DB_DSN") or DEFAULT_DSN

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT freq_30d, freq_90d, top_phrase_ratio FROM derived.taxonomy_review_queue WHERE id = %s",
                (args.queue_id,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit("queue item not found")

            freq_30d, freq_90d, top_phrase_ratio = row

            if args.action == "ADD_NODE":
                if not (freq_30d >= 25 or freq_90d >= 50):
                    raise SystemExit("ADD_NODE disallowed: frequency threshold not met")
                if top_phrase_ratio is None or top_phrase_ratio < 0.70:
                    raise SystemExit("ADD_NODE disallowed: semantic coherence threshold not met")
                if not (args.confirm_distinct and args.confirm_nonredundant and args.confirm_defense_utility):
                    raise SystemExit("ADD_NODE disallowed: required confirmations missing")

            status = {
                "ADD_NODE": "ACCEPTED",
                "ADD_SYNONYMS_ONLY": "ACCEPTED",
                "DEFER": "DEFERRED",
                "REJECT": "REJECTED",
            }[args.action]

            cur.execute(
                """
                UPDATE derived.taxonomy_review_queue
                SET status = %s,
                    decision_action = %s,
                    decision_by = %s,
                    decision_at = NOW(),
                    decision_notes = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, args.action, args.by, args.notes, args.queue_id),
            )
            conn.commit()


if __name__ == "__main__":
    main()
