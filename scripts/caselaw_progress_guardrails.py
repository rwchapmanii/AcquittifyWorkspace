#!/usr/bin/env python3
"""Build caselaw ingest progress/guardrail report from CloudWatch logs."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def run_aws(args: list[str]) -> dict[str, Any]:
    cmd = ["aws", "--no-cli-pager", *args]
    raw = subprocess.check_output(cmd, text=True)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return {}
    return payload


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass
class Summary:
    log_stream: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    scanned: int
    inserted: int
    skipped_non_criminal: int
    step_count: int
    backfill_cursor_date: str


def load_summaries(log_group: str, max_streams: int) -> list[Summary]:
    streams_payload = run_aws(
        [
            "logs",
            "describe-log-streams",
            "--log-group-name",
            log_group,
            "--order-by",
            "LastEventTime",
            "--descending",
            "--max-items",
            str(max_streams),
        ]
    )
    streams = streams_payload.get("logStreams") or []
    out: list[Summary] = []

    for entry in streams:
        stream = str(entry.get("logStreamName") or "").strip()
        if not stream:
            continue
        events = run_aws(
            [
                "logs",
                "get-log-events",
                "--log-group-name",
                log_group,
                "--log-stream-name",
                stream,
                "--limit",
                "10",
            ]
        ).get("events") or []
        if not events:
            continue
        for ev in events:
            message = str(ev.get("message") or "").strip()
            if not message.startswith("{"):
                continue
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if payload.get("event") != "ecs_caselaw_nightly_summary":
                continue
            started_at = parse_iso(str(payload.get("started_at") or ""))
            if started_at is None:
                continue
            out.append(
                Summary(
                    log_stream=stream,
                    started_at=started_at,
                    finished_at=parse_iso(str(payload.get("finished_at") or "")),
                    status=str(payload.get("status") or ""),
                    scanned=int(payload.get("scanned") or 0),
                    inserted=int(payload.get("inserted") or 0),
                    skipped_non_criminal=int(payload.get("skipped_non_criminal") or 0),
                    step_count=int(payload.get("step_count") or 0),
                    backfill_cursor_date=str(payload.get("backfill_cursor_date") or ""),
                )
            )
            break

    out.sort(key=lambda x: x.started_at, reverse=True)
    return out


def build_report(summaries: list[Summary], lookback_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, lookback_hours))
    recent = [s for s in summaries if s.started_at >= cutoff]

    def safe_ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(float(numerator) / float(denominator), 4)

    consecutive_zero = 0
    for s in summaries:
        if s.inserted == 0:
            consecutive_zero += 1
        else:
            break

    cursor_movement = None
    if len(summaries) >= 2:
        latest = summaries[0].backfill_cursor_date
        older = summaries[1].backfill_cursor_date
        if latest and older:
            cursor_movement = {"latest": latest, "previous": older, "changed": latest != older}

    total_scanned = sum(s.scanned for s in recent)
    total_inserted = sum(s.inserted for s in recent)
    total_skipped = sum(s.skipped_non_criminal for s in recent)

    guards = {
        "zero_insert_3x": consecutive_zero >= 3,
        "high_skip_ratio": safe_ratio(total_skipped, total_scanned) > 0.9 if total_scanned > 0 else False,
        "cursor_stalled": bool(cursor_movement and not cursor_movement["changed"]),
    }

    return {
        "generated_at": now.isoformat(),
        "lookback_hours": lookback_hours,
        "recent_run_count": len(recent),
        "recent_totals": {
            "scanned": total_scanned,
            "inserted": total_inserted,
            "skipped_non_criminal": total_skipped,
            "insert_rate": safe_ratio(total_inserted, total_scanned),
            "skip_ratio": safe_ratio(total_skipped, total_scanned),
        },
        "consecutive_zero_insert_runs": consecutive_zero,
        "cursor_movement": cursor_movement,
        "guardrails": guards,
        "latest_runs": [
            {
                "started_at": s.started_at.isoformat(),
                "status": s.status,
                "scanned": s.scanned,
                "inserted": s.inserted,
                "skipped_non_criminal": s.skipped_non_criminal,
                "step_count": s.step_count,
                "backfill_cursor_date": s.backfill_cursor_date,
                "log_stream": s.log_stream,
            }
            for s in summaries[:10]
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    rec = report.get("recent_totals", {})
    guards = report.get("guardrails", {})
    lines = [
        "# Caselaw Progress Guardrails",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Lookback hours: {report.get('lookback_hours')}",
        f"Recent runs: {report.get('recent_run_count')}",
        "",
        "## Totals",
        f"- Scanned: {rec.get('scanned', 0)}",
        f"- Inserted: {rec.get('inserted', 0)}",
        f"- Skipped non-criminal: {rec.get('skipped_non_criminal', 0)}",
        f"- Insert rate: {rec.get('insert_rate', 0)}",
        f"- Skip ratio: {rec.get('skip_ratio', 0)}",
        "",
        "## Guardrails",
        f"- zero_insert_3x: {guards.get('zero_insert_3x', False)}",
        f"- high_skip_ratio: {guards.get('high_skip_ratio', False)}",
        f"- cursor_stalled: {guards.get('cursor_stalled', False)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate caselaw ingest progress guardrails report")
    parser.add_argument("--log-group", default="/ecs/acquittify-prod/caselaw-ingest")
    parser.add_argument("--max-streams", type=int, default=80)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summaries = load_summaries(args.log_group, args.max_streams)
    report = build_report(summaries, args.lookback_hours)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(args.md_out, report)
    print(json.dumps({"json": str(args.json_out), "md": str(args.md_out), "runs": len(summaries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

