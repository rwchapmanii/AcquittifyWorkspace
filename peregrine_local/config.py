from __future__ import annotations

import os
from pathlib import Path

from acquittify.paths import OBSIDIAN_ROOT

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_VAULT = str(OBSIDIAN_ROOT)

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

VAULT_PATH = Path(os.getenv("PEREGRINE_VAULT_PATH", DEFAULT_VAULT)).expanduser()
INDEX_PATH = Path(
    os.getenv("PEREGRINE_INDEX_PATH", str(PROJECT_ROOT / "index"))
).expanduser()

OLLAMA_BASE_URL = os.getenv("PEREGRINE_OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = os.getenv("PEREGRINE_OLLAMA_CHAT_URL", f"{OLLAMA_BASE_URL}/api/chat")
OLLAMA_EMBED_URL = os.getenv(
    "PEREGRINE_OLLAMA_EMBED_URL", f"{OLLAMA_BASE_URL}/api/embeddings"
)

MODEL_NAME = os.getenv("PEREGRINE_MODEL", "Qwen_peregrine")
EMBED_MODEL = os.getenv("PEREGRINE_EMBED_MODEL", "nomic-embed-text")

CHUNK_SIZE = int(os.getenv("PEREGRINE_CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("PEREGRINE_CHUNK_OVERLAP", "200"))
MAX_FILE_MB = float(os.getenv("PEREGRINE_MAX_FILE_MB", "10"))
INDEX_INTERVAL = int(os.getenv("PEREGRINE_INDEX_INTERVAL", "300"))

SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
    ".eml",
    ".html",
    ".htm",
    ".pdf",
}
