from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OntologyConfig:
    project_root: Path
    vault_root: Path
    citation_cache_path: Path
    unresolved_queue_path: Path
    courtlistener_citation_lookup_url: str
    courtlistener_api_token: str | None
    request_timeout_seconds: int
    resolver_enabled: bool

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "OntologyConfig":
        root = project_root or Path(__file__).resolve().parents[2]

        vault_root_raw = os.getenv("ACQ_ONTOLOGY_VAULT_ROOT", str(root / "Obsidian" / "precedent_vault"))
        vault_root = Path(vault_root_raw)
        if not vault_root.is_absolute():
            vault_root = root / vault_root

        cache_raw = os.getenv(
            "ACQ_CITATION_CACHE_PATH",
            str(root / "acquittify-data" / "cache" / "citation_resolution.sqlite"),
        )
        citation_cache_path = Path(cache_raw)
        if not citation_cache_path.is_absolute():
            citation_cache_path = root / citation_cache_path

        lookup_url = os.getenv(
            "ACQ_COURTLISTENER_CITATION_LOOKUP_URL",
            "https://www.courtlistener.com/api/rest/v4/citation-lookup/",
        ).strip()

        token = os.getenv("ACQ_COURTLISTENER_API_TOKEN") or os.getenv("COURTLISTENER_API_TOKEN")
        timeout = int(os.getenv("ACQ_ONTOLOGY_REQUEST_TIMEOUT", "20"))
        resolver_enabled = os.getenv("ACQ_ONTOLOGY_RESOLVER_ENABLED", "1") == "1"

        unresolved_queue_path = vault_root / "indices" / "unresolved_queue.md"

        return cls(
            project_root=root,
            vault_root=vault_root,
            citation_cache_path=citation_cache_path,
            unresolved_queue_path=unresolved_queue_path,
            courtlistener_citation_lookup_url=lookup_url,
            courtlistener_api_token=token,
            request_timeout_seconds=timeout,
            resolver_enabled=resolver_enabled,
        )
