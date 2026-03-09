#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION
from acquittify.local_workspace import resolve_data_root, resolve_workspace_id, workspace_root


def _resolve_target_chroma_dir(chroma_dir: str | None, data_root: str | None, workspace_id: str | None) -> Tuple[Path, str]:
    active_workspace_id = resolve_workspace_id(workspace_id)
    if chroma_dir:
        return Path(chroma_dir).expanduser().resolve(), active_workspace_id
    root = resolve_data_root(data_root, create=True)
    ws_root = workspace_root(data_root=root, workspace_id=active_workspace_id, create=True)
    return (ws_root / "corpus" / "chroma").resolve(), active_workspace_id


def _normalized_workspace(value: Any) -> str:
    return resolve_workspace_id(str(value or ""))


def _evaluate_workspace_update(meta: Dict[str, Any], target_workspace_id: str, force: bool) -> Tuple[bool, bool]:
    raw = meta.get("workspace_id")
    if raw is None or str(raw).strip() == "":
        return True, False
    if _normalized_workspace(raw) == target_workspace_id:
        return False, False
    if force:
        return True, True
    return False, True


def _backfill_chroma_collection(
    chroma_dir: Path,
    collection_name: str,
    workspace_id: str,
    batch_size: int,
    offset: int,
    limit: int | None,
    apply: bool,
    force: bool,
) -> Dict[str, Any]:
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name)
    total = collection.count()
    start = max(0, int(offset))
    end = min(total, start + int(limit)) if limit is not None else total

    processed = 0
    updated = 0
    conflicts = 0
    already_ok = 0
    errors = 0

    for batch_start in range(start, end, batch_size):
        batch_limit = min(batch_size, end - batch_start)
        try:
            result = collection.get(
                limit=batch_limit,
                offset=batch_start,
                include=["metadatas"],
            )
        except Exception as exc:
            print(f"[warn] read batch failed offset={batch_start}: {exc}")
            errors += batch_limit
            continue

        ids = result.get("ids") or []
        metas = result.get("metadatas") or []
        update_ids: List[str] = []
        update_metas: List[Dict[str, Any]] = []

        for idx, doc_id in enumerate(ids):
            processed += 1
            meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
            should_update, is_conflict = _evaluate_workspace_update(meta, workspace_id, force=force)

            if is_conflict:
                conflicts += 1
            if not should_update:
                if not is_conflict:
                    already_ok += 1
                continue

            next_meta = dict(meta)
            next_meta["workspace_id"] = workspace_id
            update_ids.append(doc_id)
            update_metas.append(next_meta)

        if not update_ids:
            continue

        if not apply:
            updated += len(update_ids)
            continue

        try:
            collection.update(ids=update_ids, metadatas=update_metas)
            updated += len(update_ids)
        except Exception as exc:
            errors += len(update_ids)
            print(f"[warn] update batch failed offset={batch_start}: {exc}")

    return {
        "collection_name": collection_name,
        "total_records": total,
        "scanned_records": processed,
        "updated_records": updated,
        "already_ok_records": already_ok,
        "conflict_records": conflicts,
        "error_records": errors,
    }


def _backfill_document_bundles(chroma_dir: Path, workspace_id: str, apply: bool, force: bool) -> Dict[str, Any]:
    docs_root = chroma_dir / "documents"
    if not docs_root.exists():
        return {
            "docs_root": str(docs_root),
            "files_scanned": 0,
            "files_changed": 0,
            "scanned_records": 0,
            "updated_records": 0,
            "already_ok_records": 0,
            "conflict_records": 0,
            "error_records": 0,
        }

    files_scanned = 0
    files_changed = 0
    scanned_records = 0
    updated_records = 0
    already_ok = 0
    conflicts = 0
    errors = 0

    for metadata_path in docs_root.rglob("metadatas.json"):
        files_scanned += 1
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors += 1
            print(f"[warn] could not parse {metadata_path}: {exc}")
            continue

        if not isinstance(payload, list):
            continue

        changed = False
        for item in payload:
            if not isinstance(item, dict):
                continue
            scanned_records += 1
            should_update, is_conflict = _evaluate_workspace_update(item, workspace_id, force=force)
            if is_conflict:
                conflicts += 1
            if not should_update:
                if not is_conflict:
                    already_ok += 1
                continue
            item["workspace_id"] = workspace_id
            updated_records += 1
            changed = True

        if not changed:
            continue

        files_changed += 1
        if not apply:
            continue
        try:
            metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            errors += 1
            print(f"[warn] could not write {metadata_path}: {exc}")

    return {
        "docs_root": str(docs_root),
        "files_scanned": files_scanned,
        "files_changed": files_changed,
        "scanned_records": scanned_records,
        "updated_records": updated_records,
        "already_ok_records": already_ok,
        "conflict_records": conflicts,
        "error_records": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill workspace_id metadata for Chroma records and local documents metadata bundles."
    )
    parser.add_argument("--chroma-dir", default=None, help="Target Chroma directory. If omitted, uses workspace corpus/chroma.")
    parser.add_argument("--data-root", default=None, help="Data root used when --chroma-dir is omitted.")
    parser.add_argument("--workspace-id", default=None, help="Target workspace id (defaults from env or 'default').")
    parser.add_argument("--collection", default=CHROMA_COLLECTION, help="Collection name to update.")
    parser.add_argument("--batch-size", type=int, default=250, help="Collection read/update batch size.")
    parser.add_argument("--offset", type=int, default=0, help="Collection offset for partial runs.")
    parser.add_argument("--limit", type=int, default=None, help="Collection record limit for partial runs.")
    parser.add_argument("--force", action="store_true", help="Overwrite conflicting workspace_id values.")
    parser.add_argument("--skip-doc-bundles", action="store_true", help="Skip documents/*/metadatas.json updates.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without this flag, script runs in dry-run mode.")
    args = parser.parse_args()

    chroma_dir, workspace_id = _resolve_target_chroma_dir(
        chroma_dir=args.chroma_dir,
        data_root=args.data_root,
        workspace_id=args.workspace_id,
    )
    chroma_dir.mkdir(parents=True, exist_ok=True)

    collection_report = _backfill_chroma_collection(
        chroma_dir=chroma_dir,
        collection_name=str(args.collection or CHROMA_COLLECTION),
        workspace_id=workspace_id,
        batch_size=max(1, int(args.batch_size)),
        offset=max(0, int(args.offset)),
        limit=args.limit if args.limit is None else max(0, int(args.limit)),
        apply=bool(args.apply),
        force=bool(args.force),
    )

    doc_report = None
    if not args.skip_doc_bundles:
        doc_report = _backfill_document_bundles(
            chroma_dir=chroma_dir,
            workspace_id=workspace_id,
            apply=bool(args.apply),
            force=bool(args.force),
        )

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "workspace_id": workspace_id,
        "chroma_dir": str(chroma_dir),
        "collection": collection_report,
        "documents_metadata": doc_report,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
