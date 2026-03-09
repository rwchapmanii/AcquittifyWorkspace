from datetime import datetime
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import psycopg

from .auth import authenticate_user, get_current_user, require_role, _hash_password
from .db import get_conn
from .taxonomy_utils import compute_coverage
from acquittify.ingest.unified import ingest_pdf_paths
from acquittify.paths import CHROMA_DIR, RAW_CORPUS_DIR
import secrets
import logging
from collections import Counter, defaultdict
from case_manager import list_all_chats, load_chat

app = FastAPI(title="Acquittify Admin Review UI", docs_url=None, redoc_url=None)
logger = logging.getLogger("acquittify.admin_ui")

templates = Jinja2Templates(directory="admin_ui/templates")
app.mount("/static", StaticFiles(directory="admin_ui/static"), name="static")

DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_UI_DEFAULT_USERNAME", "rwchapmanii")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_UI_DEFAULT_PASSWORD", "Chapman1")


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: dict = Depends(get_current_user)):
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_view(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=401,
        )
    if "session" in request.scope:
        request.session["user"] = {"id": user["id"], "username": user["username"], "role": user["role"]}
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/logout")
def logout_action(request: Request):
    if "session" in request.scope:
        request.session.pop("user", None)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_view(request: Request, user: dict = Depends(get_current_user)):
    summary = None
    taxonomy = None
    try:
        summary = _chroma_summary(sample_limit=3000)
    except Exception:
        summary = None
    try:
        if summary:
            taxonomy = _taxonomy_coverage(summary.get("taxonomy_codes", set()))
    except Exception:
        taxonomy = None
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "summary": summary, "taxonomy": taxonomy},
    )


@app.get("/ingestion", response_class=HTMLResponse)
def ingestion_view(request: Request, user: dict = Depends(require_role("admin_reviewer"))):
    return templates.TemplateResponse(
        "ingestion.html",
        {"request": request, "user": user, "message": None, "errors": []},
    )


@app.post("/ingestion", response_class=HTMLResponse)
def ingestion_action(
    request: Request,
    files: List[UploadFile] = File(...),
    user: dict = Depends(require_role("admin_reviewer")),
):
    upload_dir = RAW_CORPUS_DIR / "AdminUploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []
    errors: List[str] = []

    for up in files:
        if not up.filename.lower().endswith(".pdf"):
            errors.append(f"{up.filename}: unsupported file type")
            continue
        target = upload_dir / up.filename
        try:
            content = up.file.read()
            target.write_bytes(content)
            saved_paths.append(target)
        except Exception as exc:
            errors.append(f"{up.filename}: {exc}")

    message = None
    if saved_paths:
        try:
            ingest_pdf_paths(saved_paths, CHROMA_DIR, use_taxonomy=True, skip_summary=False)
            message = f"Ingested {len(saved_paths)} document(s) into the main corpus."
        except Exception as exc:
            errors.append(f"Ingestion failed: {exc}")

    return templates.TemplateResponse(
        "ingestion.html",
        {"request": request, "user": user, "message": message, "errors": errors},
    )


@app.get("/corpus", response_class=HTMLResponse)
def corpus_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
    offset: int = 0,
    limit: int = 50,
):
    items = []
    total = 0
    error = None
    try:
        collection = _get_chroma_collection()
        total = collection.count()
        res = collection.get(limit=limit, offset=offset, include=["metadatas", "documents"])
        ids = res.get("ids") or []
        metas = res.get("metadatas") or []
        docs = res.get("documents") or []
        for idx, doc_id in enumerate(ids):
            meta = metas[idx] if idx < len(metas) else {}
            doc = docs[idx] if idx < len(docs) else ""
            items.append({
                "id": doc_id,
                "title": meta.get("title"),
                "source_type": meta.get("source_type"),
                "chunk_index": meta.get("chunk_index"),
                "authority_weight": meta.get("authority_weight"),
                "citation_count": meta.get("citation_count"),
                "statute_count": meta.get("statute_count"),
                "rule_count": meta.get("rule_count"),
                "path": meta.get("path"),
                "preview": (doc or "")[:280],
            })
    except Exception as exc:
        error = str(exc)

    return templates.TemplateResponse(
        "corpus.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "error": error,
        },
    )


@app.get("/embeddings", response_class=HTMLResponse)
def embeddings_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
    sample_limit: int = 5000,
):
    summary = None
    taxonomy = None
    error = None
    try:
        summary = _chroma_summary(sample_limit=sample_limit)
        taxonomy = _taxonomy_coverage(summary.get("taxonomy_codes", set()))
    except Exception as exc:
        error = str(exc)
    return templates.TemplateResponse(
        "embeddings.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "taxonomy": taxonomy,
            "error": error,
        },
    )


@app.get("/activity", response_class=HTMLResponse)
def activity_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
):
    retrieval_log = _load_jsonl(Path("Casefiles/retrieval_log.jsonl"), limit=100)
    empty_log = _load_jsonl(Path("Casefiles/retrieval_empty.jsonl"), limit=100)
    llm_log = _load_jsonl(Path("Casefiles/llm_log.jsonl"), limit=100)
    return templates.TemplateResponse(
        "activity.html",
        {
            "request": request,
            "user": user,
            "retrieval_log": retrieval_log,
            "empty_log": empty_log,
            "llm_log": llm_log,
        },
    )


@app.get("/agent-trace", response_class=HTMLResponse)
def agent_trace_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
    limit: int = 200,
):
    events = list(reversed(_load_jsonl(Path("Casefiles/agent_trace.jsonl"), limit=limit)))
    for ev in events:
        models = ev.get("models") or {}
        ev["models_display"] = (
            f"intent={models.get('intent') or 'default'}, "
            f"rewriter={models.get('rewriter') or 'default'}, "
            f"memo={models.get('memo') or 'default'}, "
            f"citation={models.get('citation') or 'default'}, "
            f"final={models.get('final') or models.get('memo') or 'default'}"
        )
        stats = ev.get("retrieval_stats") or {}
        ev["retrieval_display"] = (
            f"total={stats.get('total_sources', 0)} "
            f"(selected={stats.get('selected_doc_sources', 0)}, "
            f"corpus={stats.get('corpus_sources', 0)})"
        )
        issues = ev.get("citation_issues") or {}
        ev["citation_display"] = (
            f"needs_cites={issues.get('needs_cites')}, "
            f"needs_headings={issues.get('needs_headings')}, "
            f"needs_ladder={issues.get('needs_ladder')}, "
            f"needs_allowlist={issues.get('needs_allowlist')}"
        )
        prompt = (ev.get("prompt") or "").strip()
        ev["prompt_preview"] = prompt if len(prompt) <= 240 else prompt[:240] + "…"
        ev["query_display"] = ev.get("rewritten_query") or ev.get("expanded_query") or ""
        case_name = ev.get("case_name") or ""
        case_id = ev.get("case_id") or ""
        ev["case_display"] = case_name or case_id or "Unknown"

    return templates.TemplateResponse(
        "agent_trace.html",
        {
            "request": request,
            "user": user,
            "events": events,
            "limit": limit,
        },
    )


@app.get("/courtlistener-ingest", response_class=HTMLResponse)
def courtlistener_ingest_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
):
    log_path = Path("Casefiles/courtlistener_ingest_log.jsonl")
    state_path = Path("Casefiles/courtlistener_opinion_state.json")
    events = _load_jsonl(log_path, limit=500)
    summaries = [e for e in events if e.get("event") == "run_summary"]
    docs = [e for e in events if e.get("event") == "document"]
    summaries = list(reversed(summaries))[:50]
    docs = list(reversed(docs))[:200]

    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    return templates.TemplateResponse(
        "courtlistener_ingest.html",
        {
            "request": request,
            "user": user,
            "summaries": summaries,
            "documents": docs,
            "state": state,
            "log_path": str(log_path),
            "state_path": str(state_path),
        },
    )


@app.get("/chats", response_class=HTMLResponse)
def chats_view(
    request: Request,
    user: dict = Depends(require_role("admin_reviewer")),
):
    rows = []
    for chat_path in list_all_chats()[:200]:
        data = load_chat(chat_path)
        for msg in data.get("messages", [])[-6:]:
            rows.append({
                "chat": chat_path.name,
                "role": msg.get("role"),
                "content": (msg.get("content") or "")[:400],
            })
    rows = rows[-200:]
    return templates.TemplateResponse(
        "chats.html",
        {"request": request, "user": user, "rows": rows},
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in {"/login"}:
            return await call_next(request)
        user = request.session.get("user") if "session" in request.scope else None
        if not user:
            if path.startswith("/api/"):
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            return RedirectResponse(url="/login")
        request.state.user = user
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("ADMIN_UI_SESSION_SECRET", "change-me"),
    same_site="lax",
)


def _render_error_page(request: Request, message: str, status_code: int = 500):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": message},
        status_code=status_code,
    )


@app.exception_handler(psycopg.OperationalError)
async def _handle_db_operational_error(request: Request, exc: psycopg.OperationalError):
    detail = "Database unavailable. Verify ACQUITTIFY_DB_DSN and that Postgres is running."
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=503, content={"detail": detail})
    return _render_error_page(request, detail, status_code=503)


@app.exception_handler(RuntimeError)
async def _handle_runtime_error(request: Request, exc: RuntimeError):
    msg = str(exc)
    if "Missing database DSN" in msg:
        detail = "Database DSN is missing. Set ACQUITTIFY_DB_DSN (or *_READONLY / *_WRITE)."
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=500, content={"detail": detail})
        return _render_error_page(request, detail, status_code=500)
    detail = "Internal server error."
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": detail})
    return _render_error_page(request, detail, status_code=500)


@app.on_event("startup")
def ensure_default_admin() -> None:
    try:
        with get_conn(write=True) as conn:
            row = conn.execute(
                "SELECT id FROM derived.admin_user WHERE username = %s",
                (DEFAULT_ADMIN_USERNAME,),
            ).fetchone()
            if row:
                return
            salt = secrets.token_hex(16)
            digest = _hash_password(DEFAULT_ADMIN_PASSWORD, salt)
            stored = f"{salt}${digest}"
            conn.execute(
                """
                INSERT INTO derived.admin_user (username, password_hash, role)
                VALUES (%s, %s, %s)
                """,
                (DEFAULT_ADMIN_USERNAME, stored, "admin_reviewer"),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Admin UI startup skipped default admin creation: %s", exc)


def _latest_version(conn) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(version) FROM derived.taxonomy_node"
    ).fetchone()
    return row[0] if row and row[0] else None


def _load_jsonl(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _get_chroma_collection():
    try:
        import chromadb
    except Exception as exc:
        raise RuntimeError(f"chromadb unavailable: {exc}")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name="acquittify_corpus")


def _chroma_summary(sample_limit: int = 5000) -> Dict[str, Any]:
    collection = _get_chroma_collection()
    total = collection.count()
    sample_size = min(sample_limit, total)
    batch = 1000
    seen_keys = Counter()
    missing = Counter()
    hist = defaultdict(Counter)
    code_set = set()

    for offset in range(0, sample_size, batch):
        limit = min(batch, sample_size - offset)
        res = collection.get(limit=limit, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            for k in meta.keys():
                seen_keys[k] += 1
            for k in [
                "title","path","source_type","doc_id","chunk_index","taxonomy",
                "citations","bluebook_citations","bluebook_case_citations","statutes","bluebook_statutes","rules",
                "citation_count","bluebook_citation_count","bluebook_case_citation_count","statute_count","bluebook_statute_count",
                "rule_count","authority_weight","court","year","date_filed","citation",
            ]:
                if meta.get(k) is None:
                    missing[k] += 1
                else:
                    if k in ("citation_count","bluebook_citation_count","bluebook_case_citation_count","statute_count","bluebook_statute_count","rule_count","authority_weight","year"):
                        try:
                            hist[k][int(meta.get(k))] += 1
                        except Exception:
                            hist[k][str(meta.get(k))] += 1
            tax = meta.get("taxonomy")
            if isinstance(tax, str) and tax.strip():
                try:
                    parsed = json.loads(tax)
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict):
                    for codes in parsed.values():
                        if isinstance(codes, list):
                            for code in codes:
                                if code:
                                    code_set.add(code)

    hist_out = {}
    for key, counter in hist.items():
        hist_out[key] = dict(sorted(counter.items(), key=lambda x: x[0]))
    for key in ("authority_weight", "citation_count", "statute_count", "rule_count"):
        hist_out.setdefault(key, {})

    return {
        "total": total,
        "sample_size": sample_size,
        "seen_keys": seen_keys,
        "missing": missing,
        "hist": hist_out,
        "taxonomy_codes": code_set,
    }


def _taxonomy_coverage(code_set: set) -> Dict[str, Any]:
    code_set_norm = {c for c in code_set if isinstance(c, str)}
    if any(c.startswith("FCD.") for c in code_set_norm):
        try:
            from acquittify_taxonomy import TAXONOMY_SET
        except Exception:
            TAXONOMY_SET = set()
        return compute_coverage(code_set_norm, TAXONOMY_SET, "FCD-1.0", "local")

    try:
        with get_conn(write=False) as conn:
            version = _latest_version(conn)
            if not version:
                return compute_coverage(code_set_norm, set(), None, "db")
            rows = conn.execute(
                "SELECT code FROM derived.taxonomy_node WHERE version = %s",
                (version,),
            ).fetchall()
            node_codes = {r[0] for r in rows}
    except Exception:
        return compute_coverage(code_set_norm, set(), None, "db")

    return compute_coverage(code_set_norm, node_codes, version, "db")


def _parse_taxonomy_codes(meta: dict) -> List[str]:
    if not isinstance(meta, dict):
        return []
    raw = meta.get("taxonomy")
    if not raw:
        return []
    parsed = None
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        raw_str = raw.strip()
        if not raw_str or raw_str in {"{}", "[]", "null"}:
            return []
        try:
            parsed = json.loads(raw_str)
        except Exception:
            return []
    if not isinstance(parsed, dict):
        return []
    codes: List[str] = []
    for value in parsed.values():
        if isinstance(value, list):
            codes.extend([str(item) for item in value if item])
    return codes


def _taxonomy_heatmap(sample_limit: int = 5000) -> Dict[str, Any]:
    collection = _get_chroma_collection()
    total = collection.count()
    sample_size = min(sample_limit, total)
    batch = 1000

    facet_bucket_counts: Dict[str, Counter] = defaultdict(Counter)
    facet_counts = Counter()
    bucket_counts = Counter()

    for offset in range(0, sample_size, batch):
        limit = min(batch, sample_size - offset)
        res = collection.get(limit=limit, offset=offset, include=["metadatas"])
        metas = res.get("metadatas") or []
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            codes = _parse_taxonomy_codes(meta)
            if not codes:
                continue
            for code in codes:
                parts = code.split(".")
                if len(parts) < 3:
                    continue
                facet = parts[1]
                bucket = parts[2]
                facet_bucket_counts[facet][bucket] += 1
                facet_counts[facet] += 1
                bucket_counts[bucket] += 1

    facets = sorted(facet_bucket_counts.keys())
    buckets = sorted(bucket_counts.keys())
    matrix = []
    max_cell = 0
    for facet in facets:
        row = []
        for bucket in buckets:
            value = facet_bucket_counts[facet][bucket]
            max_cell = max(max_cell, value)
            row.append(value)
        matrix.append(row)

    return {
        "total": total,
        "sample_size": sample_size,
        "facets": facets,
        "buckets": buckets,
        "matrix": matrix,
        "max_cell": max_cell,
    }


def _load_taxonomy_nodes(conn, version: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            n.code,
            n.label,
            n.version,
            n.parent_code,
            n.synonyms,
            n.status,
            n.deprecated_at,
            n.replaced_by_code,
            (SELECT COUNT(*)
             FROM derived.legal_unit lu
             WHERE lu.taxonomy_version = n.version
               AND (lu.taxonomy_code = n.code OR lu.taxonomy_code LIKE n.code || '.%%')) AS primary_count,
            (SELECT COUNT(*)
             FROM derived.legal_unit lu
             WHERE lu.taxonomy_version = n.version
               AND EXISTS (
                   SELECT 1
                   FROM unnest(lu.secondary_taxonomy_ids) AS s
                   WHERE s = n.code OR s LIKE n.code || '.%%'
               )) AS secondary_count
        FROM derived.taxonomy_node n
        WHERE n.version = %s
        ORDER BY n.code
        """,
        (version,),
    ).fetchall()

    nodes = []
    for row in rows:
        primary_count = int(row[8])
        secondary_count = int(row[9])
        total = primary_count + secondary_count
        primary_pct = round((primary_count / total) * 100, 2) if total else 0.0
        secondary_pct = round((secondary_count / total) * 100, 2) if total else 0.0
        status = row[5] or "ACTIVE"
        nodes.append(
            {
                "code": row[0],
                "label": row[1],
                "version": row[2],
                "parent_code": row[3],
                "synonyms": row[4] or [],
                "status": status,
                "deprecated_at": row[6],
                "replaced_by_code": row[7],
                "active": status == "ACTIVE",
                "deprecated": status == "DEPRECATED",
                "experimental": status == "EXPERIMENTAL",
                "primary_count": primary_count,
                "secondary_count": secondary_count,
                "primary_pct": primary_pct,
                "secondary_pct": secondary_pct,
            }
        )
    return nodes


def _flatten_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_parent: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for node in nodes:
        by_parent.setdefault(node["parent_code"], []).append(node)
    for children in by_parent.values():
        children.sort(key=lambda x: x["code"])

    flat: List[Dict[str, Any]] = []

    def visit(parent: Optional[str], depth: int) -> None:
        for child in by_parent.get(parent, []):
            entry = dict(child)
            entry["depth"] = depth
            flat.append(entry)
            visit(child["code"], depth + 1)

    visit(None, 0)
    return flat


@app.get("/taxonomy", response_class=HTMLResponse)
def taxonomy_view(
    request: Request,
    version: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    with get_conn(write=False) as conn:
        taxonomy_version = version or _latest_version(conn)
        if not taxonomy_version:
            return templates.TemplateResponse(
                "taxonomy.html",
                {
                    "request": request,
                    "user": user,
                    "nodes": [],
                    "version": None,
                    "notice": "No taxonomy versions found.",
                },
            )
        nodes = _load_taxonomy_nodes(conn, taxonomy_version)
    flat_nodes = _flatten_tree(nodes)
    return templates.TemplateResponse(
        "taxonomy.html",
        {
            "request": request,
            "user": user,
            "nodes": flat_nodes,
            "version": taxonomy_version,
        },
    )


@app.get("/legal-units", response_class=HTMLResponse)
def legal_unit_view(
    request: Request,
    code: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    params = request.query_params
    unit_type = params.get("unit_type")
    created_from = params.get("created_from")
    created_to = params.get("created_to")
    reviewed = params.get("reviewed")
    circuit = params.get("circuit")
    posture = params.get("posture")
    taxonomy_status = params.get("taxonomy_status")
    ingestion_batch_id = params.get("ingestion_batch_id")
    code_param = code or params.get("code")
    code_prefix = params.get("code_prefix") == "true"
    if code_param and code_param.endswith(".*"):
        code_param = code_param[:-2]
        code_prefix = True
    units, total = _query_legal_units(
        code=code_param,
        code_prefix=code_prefix,
        unit_type=unit_type,
        circuit=circuit,
        posture=posture,
        created_from=created_from,
        created_to=created_to,
        reviewed=reviewed,
        taxonomy_status=taxonomy_status,
        ingestion_batch_id=ingestion_batch_id,
        limit=50,
        offset=0,
    )
    return templates.TemplateResponse(
        "legal_units.html",
        {
            "request": request,
            "user": user,
            "units": units,
            "total": total,
            "filters": {
                "code": code_param or "",
                "code_prefix": code_prefix,
                "unit_type": unit_type or "",
                "circuit": circuit or "",
                "posture": posture or "",
                "created_from": created_from or "",
                "created_to": created_to or "",
                "reviewed": reviewed or "",
                "taxonomy_status": taxonomy_status or "",
                "ingestion_batch_id": ingestion_batch_id or "",
            },
        },
    )


@app.get("/intent-audit", response_class=HTMLResponse)
def intent_audit_view(
    request: Request,
    user: dict = Depends(get_current_user),
):
    rows = _query_intent_audit(limit=50, offset=0)
    return templates.TemplateResponse(
        "intent_audit.html",
        {"request": request, "user": user, "rows": rows},
    )


@app.get("/taxonomy-gaps", response_class=HTMLResponse)
def taxonomy_gap_view(
    request: Request,
    user: dict = Depends(get_current_user),
):
    params = request.query_params
    gaps = _query_taxonomy_gaps(
        status=params.get("status"),
        unreviewed_only=params.get("unreviewed_only") == "true",
        reviewer=params.get("reviewer"),
        outcome=params.get("outcome"),
        limit=50,
        offset=0,
    )
    return templates.TemplateResponse(
        "taxonomy_gaps.html",
        {
            "request": request,
            "user": user,
            "gaps": gaps,
            "filters": {
                "status": params.get("status") or "",
                "unreviewed_only": params.get("unreviewed_only") == "true",
                "reviewer": params.get("reviewer") or "",
                "outcome": params.get("outcome") or "",
            },
        },
    )


@app.get("/taxonomy-gap-events", response_class=HTMLResponse)
def taxonomy_gap_events_view(
    request: Request,
    user: dict = Depends(get_current_user),
):
    params = request.query_params
    events = _query_taxonomy_gap_events(
        suggested_parent_code=params.get("suggested_parent_code"),
        frequency_threshold=_parse_int(params.get("frequency_threshold")),
        created_from=params.get("created_from"),
        created_to=params.get("created_to"),
        limit=50,
        offset=0,
    )
    return templates.TemplateResponse(
        "taxonomy_gap_events.html",
        {
            "request": request,
            "user": user,
            "events": events,
            "filters": {
                "suggested_parent_code": params.get("suggested_parent_code") or "",
                "frequency_threshold": params.get("frequency_threshold") or "",
                "created_from": params.get("created_from") or "",
                "created_to": params.get("created_to") or "",
            },
        },
    )


@app.get("/taxonomy-heatmap", response_class=HTMLResponse)
def taxonomy_heatmap_view(
    request: Request,
    user: dict = Depends(get_current_user),
    sample_limit: int = 5000,
):
    return templates.TemplateResponse(
        "taxonomy_heatmap.html",
        {"request": request, "user": user, "sample_limit": sample_limit},
    )


@app.get("/api/taxonomy-heatmap")
def taxonomy_heatmap_api(
    sample_limit: int = Query(5000, ge=500, le=20000),
    user: dict = Depends(get_current_user),
):
    try:
        return _taxonomy_heatmap(sample_limit=sample_limit)
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/taxonomy/tree")
def taxonomy_tree_api(
    version: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    with get_conn(write=False) as conn:
        taxonomy_version = version or _latest_version(conn)
        if not taxonomy_version:
            raise HTTPException(status_code=404, detail="No taxonomy versions found")
        nodes = _load_taxonomy_nodes(conn, taxonomy_version)
    return {"version": taxonomy_version, "nodes": nodes}


@app.get("/api/taxonomy/node/{code}/legal-units")
def taxonomy_node_units_api(
    code: str,
    version: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    units, total = _query_legal_units(
        code=code,
        code_prefix=True,
        version=version,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "units": units}


@app.get("/api/legal-units")
def legal_units_api(
    code: Optional[str] = None,
    code_prefix: Optional[bool] = False,
    circuit: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    posture: Optional[str] = None,
    unit_type: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    reviewed: Optional[str] = None,
    taxonomy_status: Optional[str] = None,
    ingestion_batch_id: Optional[str] = None,
    is_holding: Optional[bool] = None,
    is_dicta: Optional[bool] = None,
    favorability_min: Optional[int] = None,
    favorability_max: Optional[int] = None,
    authority_min: Optional[int] = None,
    authority_max: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    units, total = _query_legal_units(
        code=code,
        code_prefix=code_prefix,
        circuit=circuit,
        year_from=year_from,
        year_to=year_to,
        posture=posture,
        unit_type=unit_type,
        created_from=created_from,
        created_to=created_to,
        reviewed=reviewed,
        taxonomy_status=taxonomy_status,
        ingestion_batch_id=ingestion_batch_id,
        is_holding=is_holding,
        is_dicta=is_dicta,
        favorability_min=favorability_min,
        favorability_max=favorability_max,
        authority_min=authority_min,
        authority_max=authority_max,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "units": units}


@app.post("/api/legal-units/{unit_id}/flag-review")
def flag_legal_unit(
    unit_id: str,
    user: dict = Depends(require_role("admin_reviewer")),
):
    payload = {
        "action": "FLAG_LEGAL_UNIT",
        "unit_id": unit_id,
    }
    _insert_review_event(
        action_type="FLAG_LEGAL_UNIT",
        target_code=None,
        target_version=None,
        payload=payload,
        actor=user["username"],
    )
    return {"status": "ok"}


@app.get("/api/intent-audit")
def intent_audit_api(
    confidence_lt: Optional[float] = None,
    posture: Optional[str] = None,
    taxonomy_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    rows = _query_intent_audit(
        confidence_lt=confidence_lt,
        posture=posture,
        taxonomy_code=taxonomy_code,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"rows": rows}


@app.get("/api/taxonomy-gaps")
def taxonomy_gaps_api(
    status: Optional[str] = None,
    unreviewed_only: bool = False,
    reviewer: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    gaps = _query_taxonomy_gaps(
        status=status,
        unreviewed_only=unreviewed_only,
        reviewer=reviewer,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
    return {"gaps": gaps}


@app.get("/api/taxonomy-gap-events")
def taxonomy_gap_events_api(
    suggested_parent_code: Optional[str] = None,
    frequency_threshold: Optional[int] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    events = _query_taxonomy_gap_events(
        suggested_parent_code=suggested_parent_code,
        frequency_threshold=frequency_threshold,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return {"events": events}


@app.post("/api/taxonomy-gaps/{gap_id}/review-action")
def taxonomy_gap_action(
    gap_id: int,
    action_type: str,
    notes: Optional[str] = None,
    user: dict = Depends(require_role("admin_reviewer")),
):
    payload = {"gap_id": gap_id, "notes": notes}
    _insert_review_event(
        action_type=action_type,
        target_code=None,
        target_version=None,
        payload=payload,
        actor=user["username"],
    )
    return {"status": "ok"}


def _query_legal_units(
    code: Optional[str] = None,
    code_prefix: bool = False,
    version: Optional[str] = None,
    circuit: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    posture: Optional[str] = None,
    unit_type: Optional[str] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    reviewed: Optional[str] = None,
    taxonomy_status: Optional[str] = None,
    ingestion_batch_id: Optional[str] = None,
    is_holding: Optional[bool] = None,
    is_dicta: Optional[bool] = None,
    favorability_min: Optional[int] = None,
    favorability_max: Optional[int] = None,
    authority_min: Optional[int] = None,
    authority_max: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    where = []
    params: List[Any] = []
    joins = ""

    if code:
        if code_prefix:
            where.append("(taxonomy_code = %s OR taxonomy_code LIKE %s OR %s = ANY(secondary_taxonomy_ids))")
            params.extend([code, f"{code}.%", code])
        else:
            where.append("(taxonomy_code = %s OR %s = ANY(secondary_taxonomy_ids))")
            params.extend([code, code])
    if version:
        where.append("taxonomy_version = %s")
        params.append(version)
    if circuit:
        where.append("circuit = %s")
        params.append(circuit)
    if year_from is not None:
        where.append("year >= %s")
        params.append(year_from)
    if year_to is not None:
        where.append("year <= %s")
        params.append(year_to)
    if posture:
        where.append("posture = %s")
        params.append(posture)
    if unit_type:
        types = [t.strip() for t in unit_type.split(",") if t.strip()]
        if len(types) == 1:
            where.append("unit_type = %s")
            params.append(types[0])
        elif types:
            where.append("unit_type = ANY(%s)")
            params.append(types)
    if created_from:
        where.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        where.append("created_at <= %s")
        params.append(created_to)
    if ingestion_batch_id:
        where.append("ingestion_batch_id = %s")
        params.append(ingestion_batch_id)
    if is_holding is not None:
        where.append("is_holding = %s")
        params.append(is_holding)
    if is_dicta is not None:
        where.append("is_dicta = %s")
        params.append(is_dicta)
    if favorability_min is not None:
        where.append("favorability >= %s")
        params.append(favorability_min)
    if favorability_max is not None:
        where.append("favorability <= %s")
        params.append(favorability_max)
    if authority_min is not None:
        where.append("authority_weight >= %s")
        params.append(authority_min)
    if authority_max is not None:
        where.append("authority_weight <= %s")
        params.append(authority_max)

    if taxonomy_status:
        joins = " LEFT JOIN derived.taxonomy_node tn ON tn.code = derived.legal_unit.taxonomy_code AND tn.version = derived.legal_unit.taxonomy_version"
        where.append("tn.status = %s")
        params.append(taxonomy_status)

    if reviewed in ("reviewed", "unreviewed"):
        reviewed_sql = (
            "EXISTS (SELECT 1 FROM derived.taxonomy_review_event tre "
            "WHERE tre.payload->>'unit_id' = derived.legal_unit.unit_id::text)"
        )
        if reviewed == "reviewed":
            where.append(reviewed_sql)
        else:
            where.append(f"NOT {reviewed_sql}")

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    query = (
        "SELECT unit_id, unit_text, unit_type, court_level, circuit, year, posture, "
        "standard_of_review, burden, is_holding, is_dicta, favorability, authority_weight, "
        "taxonomy_code, taxonomy_version, secondary_taxonomy_ids, source_opinion_id, created_at, ingestion_batch_id "
        f"FROM derived.legal_unit{joins}{where_sql} "
        "ORDER BY year DESC, authority_weight DESC, favorability DESC "
        "LIMIT %s OFFSET %s"
    )
    count_query = f"SELECT COUNT(*) FROM derived.legal_unit{joins}{where_sql}"

    with get_conn(write=False) as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(query, params + [limit, offset]).fetchall()

    units = []
    for row in rows:
        units.append(
            {
                "unit_id": str(row[0]),
                "excerpt": (row[1] or "")[:320],
                "unit_type": row[2],
                "court_level": row[3],
                "circuit": row[4],
                "year": row[5],
                "posture": row[6],
                "standard_of_review": row[7],
                "burden": row[8],
                "is_holding": row[9],
                "is_dicta": row[10],
                "favorability": row[11],
                "authority_weight": row[12],
                "taxonomy_code": row[13],
                "taxonomy_version": row[14],
                "secondary_taxonomy_ids": row[15],
                "source_opinion_id": row[16],
                "created_at": row[17].isoformat() if isinstance(row[17], datetime) else row[17],
                "ingestion_batch_id": row[18],
            }
        )

    return units, int(total)


def _query_intent_audit(
    confidence_lt: Optional[float] = None,
    posture: Optional[str] = None,
    taxonomy_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where = []
    params: List[Any] = []

    if confidence_lt is not None:
        where.append("primary_confidence < %s")
        params.append(confidence_lt)
    if posture:
        where.append("posture = %s")
        params.append(posture)
    if taxonomy_code:
        where.append("primary_code = %s OR %s = ANY(secondary_codes)")
        params.extend([taxonomy_code, taxonomy_code])
    if date_from:
        where.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        where.append("created_at <= %s")
        params.append(date_to)

    where_sql = " WHERE " + " AND ".join(where) if where else ""

    query = (
        "SELECT created_at, input_text, signals, primary_code, primary_confidence, "
        "secondary_codes, secondary_confidences, posture, posture_confidence, routing_plan, taxonomy_version "
        f"FROM derived.intent_audit_log{where_sql} "
        "ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )

    with get_conn(write=False) as conn:
        rows = conn.execute(query, params + [limit, offset]).fetchall()

    formatted = []
    for row in rows:
        formatted.append(
            {
                "created_at": row[0].isoformat() if isinstance(row[0], datetime) else row[0],
                "input_text": row[1],
                "signals": row[2],
                "primary_code": row[3],
                "primary_confidence": float(row[4]),
                "secondary_codes": row[5],
                "secondary_confidences": row[6],
                "posture": row[7],
                "posture_confidence": float(row[8]),
                "routing_plan": row[9],
                "taxonomy_version": row[10],
            }
        )
    return formatted


def _query_taxonomy_gaps(
    status: Optional[str] = None,
    unreviewed_only: bool = False,
    reviewer: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where = []
    params: List[Any] = []
    if status:
        where.append("status = %s")
        params.append(status)
    if unreviewed_only:
        where.append("decision_action IS NULL")
    if reviewer:
        where.append("decision_by = %s")
        params.append(reviewer)
    if outcome:
        where.append("decision_action = %s")
        params.append(outcome)
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    query = (
        "SELECT id, fallback_code, domain, freq_30d, freq_90d, freq_180d, "
        "avg_primary_confidence, representative_inputs, common_phrases, posture_distribution, circuits, "
        "dominant_posture, top_phrase, top_phrase_ratio, last_event_at, status, decision_action, decision_by "
        f"FROM derived.taxonomy_review_queue{where_sql} "
        "ORDER BY freq_30d DESC NULLS LAST LIMIT %s OFFSET %s"
    )

    with get_conn(write=False) as conn:
        rows = conn.execute(query, params + [limit, offset]).fetchall()

    gaps = []
    for row in rows:
        gaps.append(
            {
                "id": row[0],
                "fallback_code": row[1],
                "domain": row[2],
                "freq_30d": row[3],
                "freq_90d": row[4],
                "freq_180d": row[5],
                "avg_primary_confidence": float(row[6]),
                "representative_inputs": row[7],
                "common_phrases": row[8],
                "posture_distribution": row[9],
                "circuits": row[10],
                "dominant_posture": row[11],
                "top_phrase": row[12],
                "top_phrase_ratio": float(row[13]) if row[13] is not None else None,
                "last_event_at": row[14].isoformat() if isinstance(row[14], datetime) else row[14],
                "status": row[15],
                "decision_action": row[16],
                "decision_by": row[17],
            }
        )
    return gaps


def _query_taxonomy_gap_events(
    suggested_parent_code: Optional[str] = None,
    frequency_threshold: Optional[int] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where = []
    params: List[Any] = []
    if suggested_parent_code:
        where.append("suggested_parent_code = %s")
        params.append(suggested_parent_code)
    if created_from:
        where.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        where.append("created_at <= %s")
        params.append(created_to)

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    freq_filter = ""
    if frequency_threshold is not None:
        freq_filter = " WHERE event_count >= %s"
        params.append(frequency_threshold)

    query = (
        "WITH base AS ("
        "  SELECT id, created_at, input_text, primary_code, primary_confidence, secondary_codes, "
        "  taxonomy_version, gap_reasons, fallback_code, domain, posture, circuit, suggested_parent_code, "
        "  COUNT(*) OVER (PARTITION BY fallback_code, domain) AS event_count "
        f"  FROM derived.taxonomy_gap_event{where_sql}"
        ") "
        "SELECT id, created_at, input_text, primary_code, primary_confidence, secondary_codes, "
        "taxonomy_version, gap_reasons, fallback_code, domain, posture, circuit, suggested_parent_code "
        f"FROM base{freq_filter} "
        "ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )

    with get_conn(write=False) as conn:
        rows = conn.execute(query, params + [limit, offset]).fetchall()

    events = []
    for row in rows:
        events.append(
            {
                "id": row[0],
                "created_at": row[1].isoformat() if isinstance(row[1], datetime) else row[1],
                "input_text": row[2],
                "primary_code": row[3],
                "primary_confidence": float(row[4]),
                "secondary_codes": row[5],
                "taxonomy_version": row[6],
                "gap_reasons": row[7],
                "fallback_code": row[8],
                "domain": row[9],
                "posture": row[10],
                "circuit": row[11],
                "suggested_parent_code": row[12],
            }
        )
    return events


def _insert_review_event(
    action_type: str,
    target_code: Optional[str],
    target_version: Optional[str],
    payload: Dict[str, Any],
    actor: str,
) -> None:
    with get_conn(write=True) as conn:
        _validate_review_code(conn, target_code, target_version, payload)
        conn.execute(
            """
            INSERT INTO derived.taxonomy_review_event
                (action_type, target_code, target_version, payload, actor)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (action_type, target_code, target_version, payload, actor),
        )
        conn.commit()


def _validate_review_code(conn, target_code: Optional[str], target_version: Optional[str], payload: Dict[str, Any]) -> None:
    candidates = []
    if target_code:
        candidates.append((target_code, target_version))
    for key in ("taxonomy_code", "proposed_code", "target_code"):
        if key in payload and payload[key]:
            candidates.append((payload[key], payload.get("taxonomy_version") or payload.get("target_version")))
    for code, version in candidates:
        if not code or not version:
            continue
        row = conn.execute(
            "SELECT status FROM derived.taxonomy_node WHERE code = %s AND version = %s",
            (code, version),
        ).fetchone()
        if row and row[0] == "DEPRECATED":
            raise HTTPException(status_code=400, detail="Cannot assign deprecated taxonomy code")


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
