from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.api.authz import require_admin_access
from app.api.deps import get_db

router = APIRouter(prefix="/admin/caselaw", tags=["admin-caselaw"])


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _table_exists(session: Session, table_name: str) -> bool:
    return bool(
        session.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL AS ok"),
            {"table_name": table_name},
        ).scalar()
    )


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _as_str(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _infer_court_level(court_id: str, court_name: str) -> str:
    cid = court_id.lower()
    cname = court_name.lower()
    if cid == "scotus" or "supreme" in cname:
        return "supreme"
    if cid.startswith("ca") or "appeal" in cname or "circuit" in cname:
        return "appeals"
    if "district" in cname:
        return "district"
    return "other"


def _normalize_case_taxonomies(value: Any, fallback_codes: list[str]) -> list[dict[str, str]]:
    if isinstance(value, list):
        out: list[dict[str, str]] = []
        for entry in value:
            if isinstance(entry, dict):
                code = _as_str(entry.get("code"))
                label = _as_str(entry.get("label")) or code
            else:
                code = _as_str(entry)
                label = code
            if not code:
                continue
            out.append({"code": code, "label": label or code})
        if out:
            return out
    return [{"code": code, "label": code} for code in fallback_codes if _as_str(code)]


def _normalize_frontmatter(
    frontmatter: Any,
    *,
    case_id: Any,
    case_name: Any,
    court_id: Any,
    court_name: Any,
    date_filed: Any,
    case_type: Any,
    taxonomy_codes: Any,
    taxonomy_version: Any,
    cluster_id: Any,
    opinion_id: Any,
    primary_citation: Any,
) -> dict[str, Any]:
    fm = _as_dict(frontmatter)
    court_id_text = _as_str(court_id)
    court_name_text = _as_str(fm.get("court")) or _as_str(court_name)
    case_id_text = _as_str(case_id)
    case_title = _as_str(fm.get("title")) or _as_str(case_name) or case_id_text
    date_decided = _as_str(fm.get("date_decided")) or _as_str(_serialize_value(date_filed))
    case_type_text = _as_str(fm.get("case_type")) or _as_str(case_type)
    case_type_reason = _as_str(fm.get("case_type_reason"))
    taxonomy_codes_list = [str(code).strip() for code in (taxonomy_codes or []) if str(code).strip()]
    taxonomy_version_text = _as_str(fm.get("taxonomy_version")) or _as_str(taxonomy_version)
    primary_citation_text = _as_str(primary_citation)
    citations_in_text = _as_str_list(fm.get("citations_in_text"))
    if not citations_in_text and primary_citation_text:
        citations_in_text = [primary_citation_text]

    judges = _as_dict(fm.get("judges"))
    sources = _as_dict(fm.get("sources"))

    return {
        "type": _as_str(fm.get("type")) or "case",
        "case_id": case_id_text,
        "title": case_title,
        "court": court_name_text,
        "court_level": _as_str(fm.get("court_level")) or _infer_court_level(court_id_text, court_name_text),
        "jurisdiction": _as_str(fm.get("jurisdiction")) or "US",
        "date_decided": date_decided,
        "publication_status": _as_str(fm.get("publication_status")) or "published",
        "opinion_type": _as_str(fm.get("opinion_type")) or "majority",
        "judges": {
            "author": _as_str(judges.get("author")),
            "joining": _as_str_list(judges.get("joining")),
        },
        "citations_in_text": citations_in_text,
        "case_summary": _as_str(fm.get("case_summary")),
        "essential_holding": _as_str(fm.get("essential_holding")),
        "case_type": case_type_text,
        "case_type_reason": case_type_reason,
        "case_taxonomies": _normalize_case_taxonomies(fm.get("case_taxonomies"), taxonomy_codes_list),
        "taxonomy_version": taxonomy_version_text,
        "sources": {
            "source": _as_str(sources.get("source")) or "courtlistener",
            "courtlistener_cluster_id": sources.get("courtlistener_cluster_id", cluster_id),
            "courtlistener_opinion_id": sources.get("courtlistener_opinion_id", opinion_id),
            "opinion_url": _as_str(sources.get("opinion_url")),
            "primary_citation": _as_str(sources.get("primary_citation")) or primary_citation_text,
        },
    }


@router.get("/summary")
def get_caselaw_admin_summary(
    session: Session = Depends(get_db),
    _: AuthContext = Depends(require_admin_access),
) -> dict[str, Any]:
    case_table = "derived.caselaw_nightly_case"
    taxonomy_table = "derived.taxonomy_node"
    if not _table_exists(session, case_table):
        return {
            "exists": False,
            "reason": "missing_table:derived.caselaw_nightly_case",
            "cases": {},
            "graph": {},
        }

    case_counts = dict(
        session.execute(
            text(
                """
                SELECT
                    COUNT(*)::bigint AS total_cases,
                    COUNT(*) FILTER (WHERE last_ingested_at >= NOW() - INTERVAL '1 hour')::bigint AS touched_last_hour,
                    COUNT(*) FILTER (WHERE last_ingested_at >= NOW() - INTERVAL '24 hours')::bigint AS touched_last_24h,
                    COUNT(*) FILTER (WHERE first_ingested_at >= NOW() - INTERVAL '1 hour')::bigint AS new_last_hour,
                    COUNT(*) FILTER (WHERE first_ingested_at >= NOW() - INTERVAL '24 hours')::bigint AS new_last_24h,
                    COUNT(*) FILTER (WHERE frontmatter_json IS NOT NULL)::bigint AS with_frontmatter,
                    COALESCE(SUM(cardinality(taxonomy_codes)), 0)::bigint AS taxonomy_edges,
                    COUNT(*) FILTER (WHERE COALESCE(court_id, '') <> '')::bigint AS decided_by_edges,
                    MAX(last_ingested_at) AS latest_ingest
                FROM derived.caselaw_nightly_case
                """
            )
        ).mappings().one()
    )

    taxonomy_nodes = 0
    if _table_exists(session, taxonomy_table):
        taxonomy_nodes = int(
            session.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM derived.taxonomy_node
                    WHERE version = (SELECT MAX(version) FROM derived.taxonomy_node)
                    """
                )
            ).scalar()
            or 0
        )

    court_nodes = int(
        session.execute(
            text(
                """
                SELECT COUNT(DISTINCT court_id)::bigint
                FROM derived.caselaw_nightly_case
                WHERE COALESCE(court_id, '') <> ''
                """
            )
        ).scalar()
        or 0
    )

    total_cases = int(case_counts.get("total_cases") or 0)
    total_nodes = total_cases + taxonomy_nodes + court_nodes
    taxonomy_edges = int(case_counts.get("taxonomy_edges") or 0)
    decided_by_edges = int(case_counts.get("decided_by_edges") or 0)
    total_edges = taxonomy_edges + decided_by_edges

    return {
        "exists": True,
        "cases": {
            "total": total_cases,
            "touched_last_hour": int(case_counts.get("touched_last_hour") or 0),
            "touched_last_24h": int(case_counts.get("touched_last_24h") or 0),
            "new_last_hour": int(case_counts.get("new_last_hour") or 0),
            "new_last_24h": int(case_counts.get("new_last_24h") or 0),
            "with_frontmatter": int(case_counts.get("with_frontmatter") or 0),
            "latest_ingest": _serialize_value(case_counts.get("latest_ingest")),
        },
        "graph": {
            "nodes": total_nodes,
            "edges": total_edges,
            "node_breakdown": {
                "case": total_cases,
                "taxonomy": taxonomy_nodes,
                "court": court_nodes,
            },
            "edge_breakdown": {
                "taxonomy_edge": taxonomy_edges,
                "decided_by": decided_by_edges,
            },
        },
    }


@router.get("/cases")
def list_caselaw_cases(
    query: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_frontmatter: bool = Query(default=False),
    session: Session = Depends(get_db),
    _: AuthContext = Depends(require_admin_access),
) -> dict[str, Any]:
    if not _table_exists(session, "derived.caselaw_nightly_case"):
        return {"exists": False, "total": 0, "limit": limit, "offset": offset, "items": []}

    search = query.strip()
    params = {
        "q": f"%{search}%",
        "empty": "" if search else search,
        "limit": limit,
        "offset": offset,
    }

    total = int(
        session.execute(
            text(
                """
                SELECT COUNT(*)::bigint
                FROM derived.caselaw_nightly_case
                WHERE (
                    :empty = ''
                    OR case_id ILIKE :q
                    OR case_name ILIKE :q
                    OR COALESCE(frontmatter_json -> 'sources' ->> 'primary_citation', '') ILIKE :q
                    OR COALESCE(court_name, '') ILIKE :q
                )
                """
            ),
            params,
        ).scalar()
        or 0
    )

    rows = session.execute(
        text(
            """
            SELECT
                case_id,
                case_name,
                courtlistener_cluster_id,
                courtlistener_opinion_id,
                court_id,
                court_name,
                date_filed,
                case_type,
                taxonomy_codes,
                taxonomy_version,
                first_ingested_at,
                last_ingested_at,
                COALESCE(frontmatter_json -> 'sources' ->> 'primary_citation', '') AS primary_citation,
                frontmatter_json
            FROM derived.caselaw_nightly_case
            WHERE (
                :empty = ''
                OR case_id ILIKE :q
                OR case_name ILIKE :q
                OR COALESCE(frontmatter_json -> 'sources' ->> 'primary_citation', '') ILIKE :q
                OR COALESCE(court_name, '') ILIKE :q
            )
            ORDER BY date_filed DESC NULLS LAST, last_ingested_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "case_id": row.get("case_id"),
            "case_name": row.get("case_name"),
            "court_id": row.get("court_id"),
            "court_name": row.get("court_name"),
            "date_filed": _serialize_value(row.get("date_filed")),
            "case_type": row.get("case_type"),
            "primary_citation": row.get("primary_citation") or "",
            "first_ingested_at": _serialize_value(row.get("first_ingested_at")),
            "last_ingested_at": _serialize_value(row.get("last_ingested_at")),
        }
        if include_frontmatter:
            payload["frontmatter"] = _normalize_frontmatter(
                row.get("frontmatter_json"),
                case_id=row.get("case_id"),
                case_name=row.get("case_name"),
                court_id=row.get("court_id"),
                court_name=row.get("court_name"),
                date_filed=row.get("date_filed"),
                case_type=row.get("case_type"),
                taxonomy_codes=row.get("taxonomy_codes"),
                taxonomy_version=row.get("taxonomy_version"),
                cluster_id=row.get("courtlistener_cluster_id"),
                opinion_id=row.get("courtlistener_opinion_id"),
                primary_citation=row.get("primary_citation"),
            )
        items.append(payload)

    return {
        "exists": True,
        "query": search,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.get("/cases/{case_id:path}")
def get_caselaw_case(
    case_id: str,
    session: Session = Depends(get_db),
    _: AuthContext = Depends(require_admin_access),
) -> dict[str, Any]:
    if not _table_exists(session, "derived.caselaw_nightly_case"):
        raise HTTPException(status_code=404, detail="Caselaw dataset not initialized")

    row = session.execute(
        text(
            """
            SELECT
                case_id,
                case_name,
                courtlistener_cluster_id,
                courtlistener_opinion_id,
                court_id,
                court_name,
                date_filed,
                case_type,
                taxonomy_codes,
                taxonomy_version,
                first_ingested_at,
                last_ingested_at,
                COALESCE(frontmatter_json -> 'sources' ->> 'primary_citation', '') AS primary_citation,
                frontmatter_json
            FROM derived.caselaw_nightly_case
            WHERE case_id = :case_id
            LIMIT 1
            """
        ),
        {"case_id": case_id},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")

    return {
        "case_id": row.get("case_id"),
        "case_name": row.get("case_name"),
        "court_id": row.get("court_id"),
        "court_name": row.get("court_name"),
        "date_filed": _serialize_value(row.get("date_filed")),
        "case_type": row.get("case_type"),
        "primary_citation": row.get("primary_citation") or "",
        "first_ingested_at": _serialize_value(row.get("first_ingested_at")),
        "last_ingested_at": _serialize_value(row.get("last_ingested_at")),
        "frontmatter": _normalize_frontmatter(
            row.get("frontmatter_json"),
            case_id=row.get("case_id"),
            case_name=row.get("case_name"),
            court_id=row.get("court_id"),
            court_name=row.get("court_name"),
            date_filed=row.get("date_filed"),
            case_type=row.get("case_type"),
            taxonomy_codes=row.get("taxonomy_codes"),
            taxonomy_version=row.get("taxonomy_version"),
            cluster_id=row.get("courtlistener_cluster_id"),
            opinion_id=row.get("courtlistener_opinion_id"),
            primary_citation=row.get("primary_citation"),
        ),
    }
