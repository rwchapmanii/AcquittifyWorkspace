#!/usr/bin/env python3
"""Show CourtListener bulk ingestion status from checkpoints, logs, and DB."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _format_ts(ts: datetime | None) -> str:
    if not ts:
        return "unknown"
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _find_running_process() -> list[str]:
    try:
        proc = subprocess.run(
            ["ps", "axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    matches = []
    for line in proc.stdout.splitlines():
        if "ingestion_infra.runners.main bulk_ingest" in line:
            matches.append(line.strip())
    return matches


def _tail_log(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    if lines <= 0:
        return []
    return data[-lines:]


def _summarize_bulk(state: dict) -> list[str]:
    bulk = state.get("bulk", {}) if isinstance(state, dict) else {}
    lines: list[str] = []
    if not bulk:
        return lines
    for entity in sorted(bulk.keys()):
        keys = bulk.get(entity, {}) or {}
        if not isinstance(keys, dict) or not keys:
            lines.append(f"- {entity}: no checkpoints")
            continue
        sorted_keys = sorted(keys.keys())
        last_key = sorted_keys[-1]
        last_row = keys.get(last_key)
        lines.append(f"- {entity}: {len(keys)} snapshot(s), latest {last_key} @ row {last_row}")
    return lines


def _summarize_api(state: dict) -> list[str]:
    api = state.get("api", {}) if isinstance(state, dict) else {}
    lines: list[str] = []
    if not api:
        return lines
    for entity in sorted(api.keys()):
        page = api.get(entity)
        lines.append(f"- {entity}: page {page}")
    return lines


def _db_checkpoints(dsn: str) -> list[str]:
    try:
        import psycopg  # type: ignore
    except Exception:
        return ["- DB: psycopg not available; skipping database checkpoints"]
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source, entity_type, object_key, position, updated_at
                    FROM ingestion_checkpoints
                    ORDER BY updated_at DESC
                    LIMIT 8;
                    """
                )
                rows = cur.fetchall()
    except Exception as exc:
        return [f"- DB: unable to query checkpoints ({exc})"]
    if not rows:
        return ["- DB: no checkpoints found"]
    lines = ["- DB: latest checkpoints:"]
    for source, entity, obj_key, position, updated_at in rows:
        key = obj_key or "api"
        ts = _format_ts(updated_at)
        lines.append(f"  {source} {entity} {key} @ {position} ({ts})")
    return lines


def _render_text(
    now: str,
    running: list[str],
    state_path: Path,
    bulk_lines: list[str],
    api_lines: list[str],
    db_lines: list[str] | None,
    log_path: Path | None,
    tail_lines: list[str] | None,
) -> str:
    lines: list[str] = []
    lines.append(f"Time: {now}")
    if running:
        lines.append("Process: running")
        for line in running:
            lines.append(f"  {line}")
    else:
        lines.append("Process: not detected")
    lines.append(f"State: {state_path}")

    if bulk_lines:
        lines.append("Bulk checkpoints:")
        lines.extend(bulk_lines)
    else:
        lines.append("Bulk checkpoints: none")

    if api_lines:
        lines.append("API checkpoints:")
        lines.extend(api_lines)

    if db_lines is not None:
        lines.append("Database:")
        lines.extend(db_lines)

    if log_path is not None:
        lines.append(f"Log tail: {log_path}")
        if tail_lines:
            for line in tail_lines:
                lines.append(f"  {line}")
        else:
            lines.append("  (no log data)")

    return "\n".join(lines) + "\n"


def _render_markdown(
    now: str,
    running: list[str],
    state_path: Path,
    bulk_lines: list[str],
    api_lines: list[str],
    db_lines: list[str] | None,
    log_path: Path | None,
    tail_lines: list[str] | None,
) -> str:
    lines: list[str] = []
    lines.append("# CourtListener Ingestion Status")
    lines.append("")
    lines.append(f"- Time: {now}")
    if running:
        lines.append("- Process: running")
        lines.append("")
        lines.append("```text")
        lines.extend(running)
        lines.append("```")
    else:
        lines.append("- Process: not detected")
    lines.append(f"- State: `{state_path}`")
    lines.append("")

    lines.append("## Bulk Checkpoints")
    if bulk_lines:
        lines.extend(bulk_lines)
    else:
        lines.append("- none")

    if api_lines:
        lines.append("")
        lines.append("## API Checkpoints")
        lines.extend(api_lines)

    if db_lines is not None:
        lines.append("")
        lines.append("## Database Checkpoints")
        lines.extend(db_lines)

    if log_path is not None:
        lines.append("")
        lines.append("## Log Tail")
        lines.append(f"_Source_: `{log_path}`")
        lines.append("")
        lines.append("```text")
        if tail_lines:
            lines.extend(tail_lines)
        else:
            lines.append("(no log data)")
        lines.append("```")

    return "\n".join(lines) + "\n"


def _write_output(output: Path | None, content: str) -> None:
    if output is None:
        print(content, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="CourtListener ingestion status")
    parser.add_argument(
        "--state",
        default=os.getenv("COURTLISTENER_STATE_PATH", "ingestion_state.json"),
        help="Path to ingestion_state.json",
    )
    parser.add_argument(
        "--log",
        default="courtlistener_bulk_ingest.log",
        help="Path to bulk ingest log file",
    )
    parser.add_argument("--tail", type=int, default=15, help="Tail N log lines")
    parser.add_argument("--no-log", action="store_true", help="Skip log tail")
    parser.add_argument(
        "--format",
        choices=["text", "md"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        help="Write output to a file instead of stdout",
    )
    parser.add_argument(
        "--watch",
        type=int,
        default=0,
        help="Refresh every N seconds (writes repeatedly if --output is set)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Stop after N iterations when --watch is enabled (0 = run forever)",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="Query ingestion_checkpoints in Postgres",
    )
    parser.add_argument(
        "--db-dsn",
        default=os.getenv(
            "COURTLISTENER_DB_DSN",
            "postgresql://acquittify:acquittify@localhost:5432/courtlistener",
        ),
        help="Postgres DSN for checkpoint query",
    )
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None

    def render_once() -> None:
        now = _format_ts(datetime.now(timezone.utc))
        running = _find_running_process()
        state_path = Path(args.state)
        state = _read_state(state_path)
        bulk_lines = _summarize_bulk(state)
        api_lines = _summarize_api(state)
        db_lines = _db_checkpoints(args.db_dsn) if args.db else None
        log_path = None if args.no_log else Path(args.log)
        tail_lines = None
        if log_path is not None:
            tail_lines = _tail_log(log_path, args.tail)

        if args.format == "md":
            content = _render_markdown(
                now, running, state_path, bulk_lines, api_lines, db_lines, log_path, tail_lines
            )
        else:
            content = _render_text(
                now, running, state_path, bulk_lines, api_lines, db_lines, log_path, tail_lines
            )
        _write_output(output_path, content)

    if args.watch and args.watch > 0:
        remaining = args.iterations
        try:
            while True:
                render_once()
                if remaining:
                    remaining -= 1
                    if remaining <= 0:
                        break
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0
    else:
        render_once()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
