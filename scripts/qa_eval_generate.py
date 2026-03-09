import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
import requests
from chromadb.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.config import CHROMA_COLLECTION, CHUNK_MIN_CHARS
from acquittify.chroma_utils import get_or_create_collection
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"

_RULE_PATTERN = re.compile(r"\b(?:Fed\.\s+R\.|Rule\s+\d+|U\.S\.C\.|\b§\s*\d+)\b")
_DATE_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,}\b")


def _create_client(chroma_dir: Path):
    try:
        return chromadb.PersistentClient(path=str(chroma_dir))
    except Exception:
        try:
            settings = Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False)
            return chromadb.Client(settings)
        except Exception:
            return chromadb.Client()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _detect_targets(text: str) -> Dict[str, bool]:
    return {
        "has_rule_or_statute": bool(_RULE_PATTERN.search(text)),
        "has_date": bool(_DATE_PATTERN.search(text)),
        "has_entity": bool(_ENTITY_PATTERN.search(text)),
    }


def _select_required_targets(detected: Dict[str, bool]) -> Optional[Dict[str, bool]]:
    required = {
        "must_include_rule_or_statute": False,
        "must_include_date": False,
        "must_include_entity": False,
    }
    if detected.get("has_rule_or_statute") and detected.get("has_entity"):
        required["must_include_rule_or_statute"] = True
        required["must_include_entity"] = True
    elif detected.get("has_rule_or_statute") and detected.get("has_date"):
        required["must_include_rule_or_statute"] = True
        required["must_include_date"] = True
    elif detected.get("has_entity") and detected.get("has_date"):
        required["must_include_entity"] = True
        required["must_include_date"] = True
    elif detected.get("has_rule_or_statute"):
        required["must_include_rule_or_statute"] = True
    elif detected.get("has_date"):
        required["must_include_date"] = True
    elif detected.get("has_entity"):
        required["must_include_entity"] = True
    else:
        return None
    return required


def _required_targets_satisfied(answer: str, required: Dict[str, bool]) -> bool:
    if required.get("must_include_rule_or_statute") and not _RULE_PATTERN.search(answer):
        return False
    if required.get("must_include_date") and not _DATE_PATTERN.search(answer):
        return False
    if required.get("must_include_entity") and not _ENTITY_PATTERN.search(answer):
        return False
    return True


def _call_ollama_structured(
    chunk: str,
    required: Dict[str, bool],
    model: str,
    url: str,
    timeout: float,
) -> Optional[Dict[str, str]]:
    requirements = []
    if required.get("must_include_rule_or_statute"):
        requirements.append("a rule or statute citation")
    if required.get("must_include_date"):
        requirements.append("a date or year")
    if required.get("must_include_entity"):
        requirements.append("an entity name")
    req_text = ", ".join(requirements) if requirements else "at least one target"

    system = (
        "You create concise QA pairs strictly grounded in the excerpt. "
        "Return JSON with keys question and answer. "
        "The answer must be a short verbatim span (<= 30 words). "
        "The answer must include " + req_text + "."
    )
    user = (
        "Excerpt:\n"
        f"{chunk}\n\n"
        "Create exactly one question answerable only from the excerpt. "
        "The answer must be a single contiguous quote from the excerpt. "
        "Return JSON: {\"question\": ..., \"answer\": ...}."
    )

    schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "answer": {"type": "string"},
        },
        "required": ["question", "answer"],
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.2},
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    content = None
    if isinstance(data, dict):
        message = data.get("message") or {}
        content = message.get("content")

    parsed = _extract_json(content or "")
    if not parsed:
        return None

    question = (parsed.get("question") or "").strip()
    answer = (parsed.get("answer") or "").strip()
    if not question or not answer:
        return None

    return {"question": question, "answer": answer}


def _heuristic_qa(chunk: str, required: Dict[str, bool]) -> Optional[Dict[str, str]]:
    sentences = re.split(r"(?<=[.!?])\s+", _normalize_text(chunk))
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if not _required_targets_satisfied(sent, required):
            continue
        answer = sent
        question = "What does the excerpt state about the specific item mentioned?"
        return {"question": question, "answer": answer}
    return None


def _load_collection(chroma_dir: Path):
    client = _create_client(chroma_dir)
    return get_or_create_collection(client, name=CHROMA_COLLECTION)


def _collect_chunks(collection, limit: Optional[int] = None) -> Tuple[List[str], List[str], List[dict]]:
    try:
        snapshot = collection.get(include=["documents", "metadatas"])
        ids = snapshot.get("ids") or []
        docs = snapshot.get("documents") or []
        metas = snapshot.get("metadatas") or []
    except Exception:
        return [], [], []

    if limit and len(ids) > limit:
        ids = ids[:limit]
        docs = docs[:limit]
        metas = metas[:limit]
    return ids, docs, metas


def _collect_chunks_from_export(chroma_dir: Path, limit: Optional[int] = None) -> Tuple[List[str], List[str], List[dict]]:
    export_path = chroma_dir / "export" / "collection_export.json"
    if not export_path.exists():
        return [], [], []
    try:
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        ids = payload.get("ids") or []
        docs = payload.get("documents") or []
        metas = payload.get("metadatas") or []
    except Exception:
        return [], [], []
    if limit and len(ids) > limit:
        ids = ids[:limit]
        docs = docs[:limit]
        metas = metas[:limit]
    return ids, docs, metas


def _collect_chunks_from_documents(chroma_dir: Path, limit: Optional[int] = None) -> Tuple[List[str], List[str], List[dict]]:
    docs_root = chroma_dir / "documents"
    if not docs_root.exists():
        return [], [], []
    ids: List[str] = []
    docs: List[str] = []
    metas: List[dict] = []
    for doc_dir in sorted(docs_root.iterdir()):
        if not doc_dir.is_dir():
            continue
        try:
            meta_list = json.loads((doc_dir / "metadatas.json").read_text(encoding="utf-8"))
        except Exception:
            meta_list = []
        chunk_files = sorted([p for p in doc_dir.glob("chunk_*.txt")])
        for idx, chunk_path in enumerate(chunk_files):
            try:
                text = chunk_path.read_text(encoding="utf-8")
            except Exception:
                text = ""
            meta = meta_list[idx] if idx < len(meta_list) else {}
            ids.append(f"{doc_dir.name}_{idx}")
            docs.append(text)
            metas.append(meta if isinstance(meta, dict) else {})
            if limit and len(ids) >= limit:
                return ids, docs, metas
    return ids, docs, metas


def _answer_in_chunk(answer: str, chunk: str) -> bool:
    norm_answer = _normalize_text(answer)
    norm_chunk = _normalize_text(chunk)
    return norm_answer in norm_chunk


def _build_metadata(meta: dict) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    out = {}
    for key in ("circuit", "year", "posture"):
        if meta.get(key) is not None:
            out[key] = meta.get(key)
    return out


def _taxonomy_value(meta: dict) -> Optional[str]:
    if not isinstance(meta, dict):
        return None
    taxonomy = meta.get("taxonomy")
    if isinstance(taxonomy, str):
        return taxonomy
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate QA eval set from Chroma chunks.")
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA_DIR), help="Path to Chroma directory")
    parser.add_argument("--count", type=int, default=200, help="Number of QA pairs to generate")
    parser.add_argument("--min-chars", type=int, default=CHUNK_MIN_CHARS, help="Minimum characters in a chunk")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "eval" / "qa_eval.jsonl"), help="Output JSONL")
    parser.add_argument("--source-type", default=None, help="Filter by metadata source_type")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/chat", help="Ollama chat endpoint")
    parser.add_argument("--ollama-model", default="qwen2.5:32b-instruct", help="Ollama model name")
    parser.add_argument("--ollama-timeout", type=float, default=30.0, help="Ollama request timeout seconds")
    parser.add_argument("--no-ollama", action="store_true", help="Disable Ollama and use heuristic QA")
    parser.add_argument("--max-retries", type=int, default=2, help="Max Ollama retries per chunk")
    args = parser.parse_args()

    chroma_dir = Path(args.chroma_dir)
    collection = _load_collection(chroma_dir)
    ids, docs, metas = _collect_chunks(collection)
    if not ids:
        ids, docs, metas = _collect_chunks_from_export(chroma_dir)
    if not ids:
        ids, docs, metas = _collect_chunks_from_documents(chroma_dir)
    if not ids:
        raise SystemExit("No chunks found in the Chroma collection or backups.")

    rng = random.Random(args.seed)
    indices = list(range(len(ids)))
    rng.shuffle(indices)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for idx in indices:
            if total >= args.count:
                break
            chunk = docs[idx] if idx < len(docs) else ""
            meta = metas[idx] if idx < len(metas) else {}
            if not chunk or len(chunk) < args.min_chars:
                skipped += 1
                continue
            if args.source_type and isinstance(meta, dict):
                if (meta.get("source_type") or "") != args.source_type:
                    skipped += 1
                    continue

            detected = _detect_targets(chunk)
            required_targets = _select_required_targets(detected)
            if not required_targets:
                skipped += 1
                continue

            qa = None
            if not args.no_ollama:
                for _ in range(max(1, args.max_retries)):
                    qa = _call_ollama_structured(
                        chunk,
                        required_targets,
                        args.ollama_model,
                        args.ollama_url,
                        args.ollama_timeout,
                    )
                    if qa:
                        break
            if qa is None:
                qa = _heuristic_qa(chunk, required_targets)
            if qa is None:
                skipped += 1
                continue

            answer = qa.get("answer", "")
            if not _answer_in_chunk(answer, chunk):
                skipped += 1
                continue
            if len(answer.split()) > 30:
                skipped += 1
                continue
            if not _required_targets_satisfied(answer, required_targets):
                skipped += 1
                continue

            record = {
                "id": f"eval_{total:05d}",
                "taxonomy": _taxonomy_value(meta),
                "question": qa.get("question"),
                "gold_answer": answer,
                "required_targets": required_targets,
                "gold_chunk_id": ids[idx],
                "gold_case_id": (meta.get("case_id") or meta.get("case") or meta.get("case_name")) if isinstance(meta, dict) else None,
                "metadata": _build_metadata(meta),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            total += 1

    print(f"Wrote {total} QA pairs to {output_path} (skipped {skipped})")


if __name__ == "__main__":
    main()
