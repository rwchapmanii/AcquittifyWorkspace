from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _from_env(env_name: str, default: Path) -> Path:
    return Path(os.getenv(env_name, str(default))).expanduser()


def _legacy_repo_data_present() -> bool:
    legacy_dirs = (
        "Corpus",
        "acquittify-data",
        "Obsidian",
        "Acquittify Storage",
        "finetune",
    )
    return any((PROJECT_ROOT / name).exists() for name in legacy_dirs)


DEFAULT_DATA_ROOT = PROJECT_ROOT if _legacy_repo_data_present() else (Path.home() / "AcquittifyData")
DATA_ROOT = _from_env("ACQUITTIFY_DATA_ROOT", DEFAULT_DATA_ROOT)

CORPUS_ROOT = _from_env("ACQUITTIFY_CORPUS_ROOT", DATA_ROOT / "Corpus")
RAW_CORPUS_DIR = _from_env("ACQUITTIFY_RAW_CORPUS_DIR", CORPUS_ROOT / "Raw")
CHROMA_DIR = _from_env("CHROMA_DIR", CORPUS_ROOT / "Chroma")

ACQUITTIFY_DATASET_DIR = _from_env("ACQUITTIFY_DATASET_DIR", DATA_ROOT / "acquittify-data")
OBSIDIAN_ROOT = _from_env("ACQUITTIFY_OBSIDIAN_ROOT", DATA_ROOT / "Obsidian")
PRECEDENT_VAULT_ROOT = _from_env(
    "ACQUITTIFY_PRECEDENT_VAULT_ROOT",
    OBSIDIAN_ROOT / "Ontology" / "precedent_vault",
)

STORAGE_ROOT = _from_env("ACQUITTIFY_STORAGE_ROOT", DATA_ROOT / "Acquittify Storage")
FINETUNE_ROOT = _from_env("ACQUITTIFY_FINETUNE_ROOT", DATA_ROOT / "finetune")
REPORTS_ROOT = _from_env("ACQUITTIFY_REPORTS_ROOT", PROJECT_ROOT / "reports")
