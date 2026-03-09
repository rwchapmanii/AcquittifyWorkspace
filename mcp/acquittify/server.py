from __future__ import annotations

import os
from typing import Annotated, Any

import requests
from mcp.server.fastmcp import FastMCP

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30

mcp = FastMCP("acquittify")


def _api_url(path: str) -> str:
    base = (
        os.getenv("PEREGRINE_API_URL")
        or os.getenv("ACQUITTIFY_API_URL")
        or DEFAULT_API_URL
    )
    return base.rstrip("/") + path


def _headers() -> dict[str, str]:
    token = (
        os.getenv("PEREGRINE_API_TOKEN")
        or os.getenv("ACQUITTIFY_API_TOKEN")
        or os.getenv("PEREGRINE_API_KEY")
    )
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            _api_url(path),
            params=params,
            json=payload,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to reach Peregrine API: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        if len(detail) > 800:
            detail = detail[:800] + "…"
        raise RuntimeError(
            f"Peregrine API error {response.status_code}: {detail or 'No response body'}"
        )

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


@mcp.tool()
def list_matters(
    limit: Annotated[int | None, "Optional max number of matters to return."] = None,
) -> dict[str, Any]:
    """List matters from the Peregrine API."""
    data = _request("GET", "/matters")
    if limit is not None:
        data["matters"] = data.get("matters", [])[: max(0, limit)]
    return data


@mcp.tool()
def get_matter(
    matter_id: Annotated[str, "Matter UUID or external_id."],
) -> dict[str, Any]:
    """Fetch a single matter by UUID or external_id."""
    return _request("GET", f"/matters/{matter_id}")


@mcp.tool()
def get_matter_document_status(
    matter_id: Annotated[str, "Matter UUID or external_id."],
) -> dict[str, Any]:
    """Get document status counts for a matter."""
    return _request("GET", f"/matters/{matter_id}/documents/status")


@mcp.tool()
def list_matter_documents(
    matter_id: Annotated[str, "Matter UUID or external_id."],
    limit: Annotated[int | None, "Max number of documents (1-500)."] = None,
    offset: Annotated[int | None, "Pagination offset."] = None,
    status: Annotated[str | None, "Document status (e.g., READY)."] = None,
    q: Annotated[str | None, "Search query over filename, doc type, or proponent."] = None,
    doc_type: Annotated[str | None, "Document type (supports ILIKE)."] = None,
    priority_code: Annotated[str | None, "Priority code (e.g., P1, P2, P3)."] = None,
    witness: Annotated[str | None, "Witness name filter."] = None,
    proponent: Annotated[str | None, "Proponent filter (ILIKE)."] = None,
    date_from: Annotated[str | None, "YYYY-MM-DD lower bound."] = None,
    date_to: Annotated[str | None, "YYYY-MM-DD upper bound."] = None,
) -> dict[str, Any]:
    """List documents for a matter with optional filters."""
    params = {
        "limit": limit,
        "offset": offset,
        "status": status,
        "q": q,
        "doc_type": doc_type,
        "priority_code": priority_code,
        "witness": witness,
        "proponent": proponent,
        "date_from": date_from,
        "date_to": date_to,
    }
    params = {key: value for key, value in params.items() if value is not None}
    return _request("GET", f"/matters/{matter_id}/documents", params=params)


@mcp.tool()
def list_document_metadata(
    matter_id: Annotated[str, "Matter UUID or external_id."],
    limit: Annotated[int | None, "Max metadata rows (1-2000)."] = None,
) -> dict[str, Any]:
    """Return ingestion metadata rows for a matter."""
    params = {"limit": limit} if limit is not None else None
    return _request("GET", f"/matters/{matter_id}/documents/metadata", params=params)


@mcp.tool()
def get_document(
    document_id: Annotated[str, "Document UUID."],
) -> dict[str, Any]:
    """Fetch document metadata by document ID."""
    return _request("GET", f"/documents/{document_id}")


@mcp.tool()
def get_document_text(
    document_id: Annotated[str, "Document UUID."],
    max_chars: Annotated[int | None, "Optional max characters to return."] = 20000,
) -> dict[str, Any]:
    """Fetch extracted text for a document (optionally truncated)."""
    data = _request("GET", f"/documents/{document_id}/text")
    text = data.get("text", "")
    truncated = False
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\n\n[truncated]"
        truncated = True
    return {
        "document_id": document_id,
        "text": text,
        "text_length": len(data.get("text", "")),
        "truncated": truncated,
    }


if __name__ == "__main__":
    mcp.run()
