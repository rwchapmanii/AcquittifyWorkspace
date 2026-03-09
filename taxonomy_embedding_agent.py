import json
import os
import requests
from pathlib import Path
import sys
import chromadb
from chromadb.config import Settings
from pypdf import PdfReader
from pypdf.errors import EmptyFileError
from sentence_transformers import SentenceTransformer
import re
import numpy as np

# Local imports
from acquittify_taxonomy import TAXONOMY, TAXONOMY_SET
from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID
from acquittify.chunking import chunk_text as chunk_text_impl
from acquittify.chroma_utils import get_or_create_collection, upsert_or_add
from acquittify.ingest.metadata_utils import augment_chunk_metadata
from acquittify.ingest.unified import ingest_pdf_paths
from acquittify.paths import CHROMA_DIR

# Constants
OLLAMA_URL = os.getenv("ACQUITTIFY_INGESTION_OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("ACQUITTIFY_INGESTION_MODEL", "qwen-acquittify-ingestion14b")
EMBED_MODEL_NAME = EMBEDDING_MODEL_ID

FACETS = ["STG", "ISS", "AUTH", "OFF", "CTX", "GOV", "PRAC"]
FACET_CODES = {
    facet: [code for code in TAXONOMY if code.startswith(f"FCD.{facet}.")]
    for facet in FACETS
}

# Init embedding model (allow download if not cached)
def _load_embedding_model():
    try:
        return SentenceTransformer(EMBED_MODEL_NAME)
    except Exception:
        return None


embedding_model = _load_embedding_model()

# Chroma setup
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
abs_chroma = str(CHROMA_DIR.resolve())
client = chromadb.PersistentClient(path=abs_chroma)
collection = get_or_create_collection(client, name=CHROMA_COLLECTION)

def clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def extract_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except EmptyFileError:
        return ""
    except Exception:
        return ""

    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            continue
    return clean_text("\n".join(pages))

def chunk_text(text: str):
    return chunk_text_impl(text)

def infer_source_type(path: Path) -> str:
    parts = path.parts
    if "Treatises" in parts:
        return "Treatise"
    if "Benchbooks" in parts:
        return "Benchbook"
    if "Manuals" in parts:
        return "Manual"
    return "Unknown"

def classify_taxonomy(chunk_text: str) -> dict:
    codes_block = "\n".join(
        f"{facet}: {FACET_CODES.get(facet, [])}"
        for facet in FACETS
    )
    prompt = f"""
You are a federal criminal defense expert. Analyze the following text chunk and assign relevant taxonomy codes from the FCD taxonomy.

Assign codes to the following facets, using multiple if applicable. Prefer specific codes over general.

Facets: STG, ISS, AUTH, OFF, CTX, GOV, PRAC

Use ONLY the allowed codes listed below. If none apply for a facet, return an empty list.

Allowed codes per facet:
{codes_block}

Output only JSON: {{"STG": ["FCD.STG.EXAMPLE"], "ISS": ["FCD.ISS.EXAMPLE"], ...}}

Text:

{chunk_text}

"""
    try:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No prose."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"LLM error: {response.text}")
        result = response.json()
        content = result["message"]["content"]
        taxonomy = json.loads(content)
    except (requests.exceptions.Timeout, json.JSONDecodeError, Exception):
        taxonomy = {}
    return taxonomy

def validate_taxonomy(taxonomy: dict) -> dict:
    validated = {}
    for facet, codes in taxonomy.items():
        if not isinstance(codes, list):
            continue
        valid_codes = [c for c in codes if c in TAXONOMY_SET]
        if valid_codes:
            validated[facet] = valid_codes
    return validated

def analyze_chunk(chunk_text: str) -> dict:
    raw = classify_taxonomy(chunk_text)
    return validate_taxonomy(raw)

def build_metadata(doc_id: str, source: str, chunk_index: int, taxonomy: dict) -> dict:
    meta = {
        "doc_id": doc_id,
        "source": source,
        "chunk_index": chunk_index,
        "taxonomy": json.dumps(taxonomy),
        "taxonomy_version": "FCD-1.0",
        "taxonomy_agent": "taxonomy_embedding_agent",
        "stage": json.dumps(taxonomy.get("STG", []))
    }
    return meta

def reindex_existing_chunks():
    print("Starting reindex of existing chunks...")
    results = collection.get(include=["metadatas", "documents"])
    ids = results["ids"]
    metadatas = results["metadatas"]
    documents = results["documents"]
    new_metadatas = []
    for i, doc in enumerate(documents):
        print(f"Reindexing chunk {i+1}/{len(documents)}")
        taxonomy = analyze_chunk(doc)
        # Preserve existing metadata, add/update taxonomy fields
        meta = metadatas[i].copy()
        meta.update(build_metadata(meta.get("doc_id", ids[i]), meta.get("source", "unknown"), meta.get("chunk_index", i), taxonomy))
        new_metadatas.append(meta)
    # Batch updates to stay below ChromaDB's max batch size of 5461
    MAX_BATCH_SIZE = 5000
    for i in range(0, len(ids), MAX_BATCH_SIZE):
        batch_ids = ids[i:i + MAX_BATCH_SIZE]
        batch_metadatas = new_metadatas[i:i + MAX_BATCH_SIZE]
        collection.update(ids=batch_ids, metadatas=batch_metadatas)
    print("Reindex complete.")

def ingest_new_documents(pdf_paths: list[Path]):
    print("Starting unified ingestion for new documents...")
    ingest_pdf_paths(pdf_paths, CHROMA_DIR, use_taxonomy=True, skip_summary=False)
    try:
        client.persist()
    except AttributeError:
        pass
    print("Unified ingestion complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Taxonomy Embedding Agent for Acquittify")
    parser.add_argument("mode", choices=["reindex", "new_ingest"], help="Mode: reindex existing or ingest new")
    parser.add_argument("--pdfs", nargs="*", type=Path, help="PDF paths for new_ingest")
    parser.add_argument("--dir", type=Path, help="Directory containing PDFs for new_ingest")
    args = parser.parse_args()
    if args.mode == "reindex":
        reindex_existing_chunks()
    if args.mode == "new_ingest":
        if args.dir:
            pdfs = list(args.dir.rglob("*.pdf"))
        elif args.pdfs:
            pdfs = args.pdfs
        else:
            print("Provide --pdfs or --dir")
            sys.exit(1)
        ingest_new_documents(pdfs)
