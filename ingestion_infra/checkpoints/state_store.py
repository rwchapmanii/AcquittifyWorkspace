"""Local JSON state store for ingestion checkpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class StateStore:
    """Persist incremental progress for API and bulk ingest."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.state: Dict[str, Dict] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"api": {}, "bulk": {}}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, indent=2))

    def get_api_checkpoint(self, entity: str) -> int | None:
        return self.state.get("api", {}).get(entity)

    def set_api_checkpoint(self, entity: str, page: int) -> None:
        self.state.setdefault("api", {})[entity] = page

    def get_bulk_checkpoint(self, entity: str, key: str) -> int | None:
        return self.state.get("bulk", {}).get(entity, {}).get(key)

    def set_bulk_checkpoint(self, entity: str, key: str, row: int) -> None:
        self.state.setdefault("bulk", {}).setdefault(entity, {})[key] = row
