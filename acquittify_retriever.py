"""ChromaDB retriever for Acquittify.

Provides a simple API to query the local Chroma collection and return raw
chunks with metadata. This module does NOT summarize or format results.
"""
from typing import List, Dict, Optional, Any
from pathlib import Path
import os
import json
import re
import chromadb
from chromadb.config import Settings

# Taxonomy helpers
from acquittify_taxonomy import TAXONOMY, TAXONOMY_SET, HIERARCHY, normalize_area
from acquittify.config import CHROMA_COLLECTION, EMBEDDING_MODEL_ID, CHROMA_METADATA_EMBEDDING_KEY
from acquittify.chroma_utils import get_or_create_collection
from acquittify.authority import compute_authority_weight
from acquittify.metadata_extract import extract_citation_data


KEYWORDS = {
    "Search and Seizure": ["search", "warrant", "vehicle", "stop", "frisk", "exigent", "seizure"],
    "Evidence": ["hearsay", "chain of custody", "authentication", "expert testimony", "evidence"],
    "Sentencing": ["guideline", "sentencing", "term of imprisonment", "Guidelines"],
}
import numpy as np
from sentence_transformers import SentenceTransformer


# load embedding model lazily
_EMBED_MODEL = None


def _build_result_doc(text: str, meta: Optional[Dict[str, Any]], score: Optional[float], doc_id: str) -> Dict[str, Any]:
    meta = meta or {}
    return {
        "text": text,
        "source_type": meta.get("source_type", "Unknown"),
        "title": meta.get("title", ""),
        "path": meta.get("path", ""),
        "chunk_index": meta.get("chunk_index", None),
        "score": float(score) if score is not None else 0.0,
        "id": doc_id,
        "doc_id": meta.get("doc_id"),
        "source_id": meta.get("source_id") or meta.get("source_opinion_id"),
        "source_ids": meta.get("source_ids"),
        "court": meta.get("court") or meta.get("court_level"),
        "circuit": meta.get("circuit"),
        "year": meta.get("year"),
        "posture": meta.get("posture"),
        "taxonomy": meta.get("taxonomy"),
        "taxonomy_version": meta.get("taxonomy_version"),
        "is_holding": meta.get("is_holding"),
        "is_dicta": meta.get("is_dicta"),
        "standard_of_review": meta.get("standard_of_review"),
        "burden": meta.get("burden"),
        "favorability": meta.get("favorability"),
        "authority_weight": meta.get("authority_weight"),
        "document_citation": meta.get("document_citation") or meta.get("citation"),
        "legal_area": meta.get("legal_area"),
        "legal_areas_flat": meta.get("legal_areas_flat"),
        "authority_tier": meta.get("authority_tier"),
        "binding_circuit": meta.get("binding_circuit"),
        "case_citation_method": meta.get("case_citation_method"),
        "case_citation_is_synthetic": meta.get("case_citation_is_synthetic"),
        "char_start": meta.get("char_start"),
        "char_end": meta.get("char_end"),
        "citations": meta.get("citations"),
        "bluebook_citations": meta.get("bluebook_citations"),
        "bluebook_case_citations": meta.get("bluebook_case_citations"),
        "statutes": meta.get("statutes"),
        "bluebook_statutes": meta.get("bluebook_statutes"),
        "rules": meta.get("rules"),
        "citation_count": meta.get("citation_count"),
        "bluebook_citation_count": meta.get("bluebook_citation_count"),
        "bluebook_case_citation_count": meta.get("bluebook_case_citation_count"),
        "statute_count": meta.get("statute_count"),
        "bluebook_statute_count": meta.get("bluebook_statute_count"),
        "rule_count": meta.get("rule_count"),
    }


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer(EMBEDDING_MODEL_ID)
    return _EMBED_MODEL


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9']+", (text or "").lower())


def _keyword_overlap_score(query: str, text: str) -> float:
    q_terms = set(_tokenize(query))
    if not q_terms:
        return 0.0
    t_terms = set(_tokenize(text))
    return float(len(q_terms & t_terms)) / float(len(q_terms))


def _extract_taxonomy_codes(meta: dict) -> List[str]:
    codes: List[str] = []
    if not isinstance(meta, dict):
        return codes
    taxonomy = meta.get("taxonomy")
    if isinstance(taxonomy, dict):
        for _, vals in taxonomy.items():
            if isinstance(vals, list):
                codes.extend([v for v in vals if isinstance(v, str)])
    elif isinstance(taxonomy, str) and taxonomy.strip():
        try:
            parsed = json.loads(taxonomy)
            if isinstance(parsed, dict):
                for _, vals in parsed.items():
                    if isinstance(vals, list):
                        codes.extend([v for v in vals if isinstance(v, str)])
        except Exception:
            pass
    return codes


def _authority_score(meta: dict, text: str) -> float:
    if isinstance(meta, dict):
        weight = meta.get("authority_weight")
        if weight is not None:
            try:
                return float(weight)
            except Exception:
                pass
    try:
        return float(compute_authority_weight(meta or {}, text or ""))
    except Exception:
        return 0.0


def _bm25_scores(query: str, documents: List[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    if not documents:
        return []
    doc_tokens = [_tokenize(d) for d in documents]
    doc_lens = [len(toks) for toks in doc_tokens]
    avgdl = sum(doc_lens) / max(len(doc_lens), 1)
    # document frequencies
    df = {}
    for toks in doc_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    q_terms = _tokenize(query)
    scores = []
    for toks, dl in zip(doc_tokens, doc_lens):
        term_counts = {}
        for t in toks:
            term_counts[t] = term_counts.get(t, 0) + 1
        score = 0.0
        for term in q_terms:
            if term not in term_counts:
                continue
            n_q = df.get(term, 0)
            idf = max(0.0, (len(doc_tokens) - n_q + 0.5) / (n_q + 0.5))
            tf = term_counts[term]
            denom = tf + k1 * (1 - b + b * (dl / avgdl))
            score += idf * (tf * (k1 + 1)) / denom
        scores.append(score)
    return scores


def _query_citation_terms(query: str) -> List[str]:
    data = extract_citation_data(query or "")
    terms: List[str] = []
    terms.extend(data.get("citations", []) or [])
    terms.extend(data.get("statutes", []) or [])
    terms.extend(data.get("rules", []) or [])
    return [t for t in terms if t]


def _citation_match_boost(query_terms: List[str], text: str) -> float:
    if not query_terms or not text:
        return 0.0
    matches = sum(1 for term in query_terms if term in text)
    return min(matches, 3) / 3.0


def _build_where_clause(area: Optional[str]) -> Optional[Dict[str, Any]]:
    if not area:
        return None
    normalized = normalize_area(area)
    return {
        "$or": [
            {"legal_area": normalized},
            {"legal_area": area},
            {"legal_areas": {"$in": [normalized, area]}},
        ]
    }


def _local_fallback_search(query: str, k: int, chroma_dir: Optional[Path], legal_area: Optional[str]):
    """Search the on-disk `Corpus/Chroma/documents` backups using saved embeddings.

    This is a best-effort fallback when the Chroma collection is empty or unavailable.
    """
    docs = []
    if chroma_dir is None:
        return docs

    docs_root = Path(chroma_dir) / "documents"
    if not docs_root.exists():
        return docs

    model = _get_embed_model()
    q_emb = model.encode([query])[0]

    candidates = []  # tuples (score, text, meta, doc_id)
    for doc_dir in docs_root.iterdir():
        if not doc_dir.is_dir():
            continue
        # load chunks
        try:
            metas = json.loads((doc_dir / 'metadatas.json').read_text(encoding='utf-8'))
        except Exception:
            metas = None
        # load embeddings
        try:
            arr = np.load(doc_dir / 'embeddings.npy', allow_pickle=True)
            # arr may be object dtype containing lists
            emb_list = [np.array(x, dtype=float) for x in arr.tolist()]
        except Exception:
            emb_list = None

        # load chunk texts
        chunk_files = sorted([p for p in doc_dir.glob('chunk_*.txt')])
        for i, chunk_file in enumerate(chunk_files):
            try:
                text = chunk_file.read_text(encoding='utf-8')
            except Exception:
                text = ''
            meta = (metas[i] if metas and i < len(metas) else {}) if metas else {}
            doc_id = None
            if isinstance(meta, dict):
                doc_id = meta.get("doc_id")
            if not doc_id:
                doc_id = f"{doc_dir.name}_{i}"

            score = None
            if emb_list and i < len(emb_list):
                try:
                    vec = emb_list[i]
                    # cosine similarity
                    num = float(np.dot(q_emb, vec))
                    denom = float(np.linalg.norm(q_emb) * np.linalg.norm(vec))
                    score = num / denom if denom != 0 else 0.0
                except Exception:
                    score = 0.0
            else:
                # fallback: keyword match
                s = text.lower()
                kws = KEYWORDS.get(legal_area or '', [])
                score = sum(1.0 for kw in kws if kw in s)

            candidates.append((score, text, meta, doc_id))

    # hybrid rerank with BM25 + keyword overlap
    texts = [c[1] for c in candidates]
    bm25 = _bm25_scores(query, texts)
    reranked = []
    for (score, text, meta, doc_id), bm in zip(candidates, bm25):
        overlap = _keyword_overlap_score(query, text)
        authority = _authority_score(meta or {}, text or "")
        authority_norm = min(authority, 8.0) / 8.0
        citation_norm = min(float((meta or {}).get("citation_count", 0) or 0), 3.0) / 3.0
        combined = (bm * 0.6) + (overlap * 0.2) + (authority_norm * 0.15) + (citation_norm * 0.05)
        reranked.append((combined, text, meta, doc_id))
    reranked.sort(key=lambda x: x[0], reverse=True)

    for score, text, meta, doc_id in reranked[:k]:
        docs.append(_build_result_doc(text, meta if isinstance(meta, dict) else {}, score, doc_id))

    return docs


def _local_exact_citation_scan(query_terms: List[str], k: int, chroma_dir: Optional[Path]):
    if not query_terms or chroma_dir is None:
        return []
    docs_root = Path(chroma_dir) / "documents"
    if not docs_root.exists():
        return []

    candidates = []
    for doc_dir in docs_root.iterdir():
        if not doc_dir.is_dir():
            continue
        try:
            metas = json.loads((doc_dir / "metadatas.json").read_text(encoding="utf-8"))
        except Exception:
            metas = None
        chunk_files = sorted([p for p in doc_dir.glob("chunk_*.txt")])
        for i, chunk_file in enumerate(chunk_files):
            try:
                text = chunk_file.read_text(encoding="utf-8")
            except Exception:
                text = ""
            if not text:
                continue
            if not any(term in text for term in query_terms):
                continue
            meta = (metas[i] if metas and i < len(metas) else {}) if metas else {}
            doc_id = meta.get("doc_id") if isinstance(meta, dict) else None
            if not doc_id:
                doc_id = f"{doc_dir.name}_{i}"
            authority = _authority_score(meta or {}, text)
            authority_norm = min(authority, 8.0) / 8.0
            score = 0.7 + (authority_norm * 0.3)
            candidates.append((score, text, meta, doc_id))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [_build_result_doc(t, m if isinstance(m, dict) else {}, s, i) for s, t, m, i in candidates[:k]]


def _create_client(chroma_dir: Optional[Path]):
    """Create a chromadb client, prefer Settings with persist_directory.

    Fall back to default client() if the Settings-based constructor fails
    (compatibility across chromadb versions).
    """
    if chroma_dir is None:
        try:
            return chromadb.Client()
        except Exception:
            raise

    try:
        return chromadb.PersistentClient(path=str(chroma_dir))
    except Exception:
        try:
            settings = Settings(persist_directory=str(chroma_dir), anonymized_telemetry=False)
            return chromadb.Client(settings)
        except Exception:
            return chromadb.Client()


def retrieve(query: str, legal_area: str, k: int = 5, chroma_dir: Optional[Path] = None) -> List[Dict]:
    """Retrieve up to `k` chunks matching `query` and filtered by `legal_area`.

    Returns a list of dicts with keys: text, source_type, title, path, chunk_index.

    If metadata key for legal area is absent in the collection, this function
    falls back to an unfiltered retrieval (to avoid hallucinating metadata).
    """
    client = _create_client(chroma_dir)
    collection = get_or_create_collection(client, name=CHROMA_COLLECTION)
    try:
        collection_meta = collection.metadata or {}
    except Exception:
        collection_meta = {}
    if collection_meta.get(CHROMA_METADATA_EMBEDDING_KEY) and collection_meta.get(CHROMA_METADATA_EMBEDDING_KEY) != EMBEDDING_MODEL_ID:
        print(
            "Warning: Chroma collection embedding model mismatch:",
            collection_meta.get(CHROMA_METADATA_EMBEDDING_KEY),
            "!=",
            EMBEDDING_MODEL_ID,
        )

    def meta_matches_area(meta: dict, doc_text: Optional[str], area: str) -> bool:
        # Direct metadata fields
        if not meta:
            return False
        if "legal_area" in meta and meta.get("legal_area"):
            if normalize_area(str(meta.get("legal_area"))) == normalize_area(area):
                return True
        if "legal_areas" in meta and meta.get("legal_areas"):
            las = meta.get("legal_areas")
            if isinstance(las, (list, tuple)) and any(normalize_area(str(x)) == normalize_area(area) for x in las):
                return True
        if "legal_areas_flat" in meta and isinstance(meta.get("legal_areas_flat"), str):
            if normalize_area(area) in meta.get("legal_areas_flat"):
                return True

        # Taxonomy JSON (if present)
        taxonomy_codes = _extract_taxonomy_codes(meta or {})
        if taxonomy_codes and any(normalize_area(c) == normalize_area(area) for c in taxonomy_codes):
            return True

        # Title/path/source heuristics
        txt_sources = []
        for f in ("title", "path", "source_type"):
            v = meta.get(f)
            if isinstance(v, str):
                txt_sources.append(v.lower())

        # Check taxonomy names and hierarchy terms in title/path
        target = normalize_area(area).lower()
        for s in txt_sources:
            if target in s:
                return True
        # Check hierarchy secondary terms
        for parent, subs in HIERARCHY.items():
            if parent == area:
                for sub in subs:
                    for s in txt_sources:
                        if sub.lower() in s:
                            return True

        # Keyword scan in the chunk text if provided
        if doc_text:
            kt = KEYWORDS.get(area, [])
            low = doc_text.lower()
            for kw in kt:
                if kw.lower() in low:
                    return True

        return False

    model = _get_embed_model()
    query_embedding = None
    if model is not None:
        try:
            query_embedding = model.encode([query]).tolist()[0]
        except Exception:
            query_embedding = None
    query_terms = _query_citation_terms(query)

    def _run_query(where_clause: Optional[Dict]):
        max_results = max(k * 10, 50)
        try:
            if query_embedding is not None:
                return collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_results,
                    include=["documents", "metadatas"],
                    where=where_clause,
                )
            return collection.query(
                query_texts=[query],
                n_results=max_results,
                include=["documents", "metadatas"],
                where=where_clause,
            )
        except Exception:
            fallback_k = max(k, 10)
            if query_embedding is not None:
                return collection.query(
                    query_embeddings=[query_embedding],
                    n_results=fallback_k,
                    include=["documents", "metadatas"],
                    where=where_clause,
                )
            return collection.query(
                query_texts=[query],
                n_results=fallback_k,
                include=["documents", "metadatas"],
                where=where_clause,
            )

    where_clause = _build_where_clause(legal_area) if legal_area else None
    result = _run_query(where_clause)

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    ids = result.get("ids", [[]])[0]

    if not documents and where_clause:
        result = _run_query(None)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]

    # If the Chroma collection is empty or returned no results, fall back
    # to on-disk backups created during ingestion.
    if not documents:
        if os.getenv("ACQ_EXACT_CITATION_SCAN") == "1" and query_terms:
            exact_hits = _local_exact_citation_scan(query_terms, k, chroma_dir)
            if exact_hits:
                return exact_hits
        return _local_fallback_search(query, k, chroma_dir, legal_area)

    docs: List[Dict] = []
    bm25_scores = _bm25_scores(query, documents)
    use_citation_boost = os.getenv("ACQ_CITATION_BOOST") == "1" and bool(query_terms)

    # If a legal_area was provided, prefer results that match it (via metadata or heuristics).
    if legal_area:
        for doc, meta, bm, doc_id in zip(documents, metadatas, bm25_scores, ids):
            try:
                if meta_matches_area(meta or {}, doc, legal_area):
                    authority = _authority_score(meta or {}, doc or "")
                    authority_norm = min(authority, 8.0) / 8.0
                    citation_norm = min(float((meta or {}).get("citation_count", 0) or 0), 3.0) / 3.0
                    citation_boost = _citation_match_boost(query_terms, doc) * 0.1 if use_citation_boost else 0.0
                    score = (bm * 0.6) + (_keyword_overlap_score(query, doc) * 0.2) + (authority_norm * 0.15) + (citation_norm * 0.05) + citation_boost
                    docs.append(_build_result_doc(doc, meta or {}, score, doc_id))
                    if len(docs) >= k:
                        break
            except Exception:
                continue

        # If none matched, fall back to returning the top-k unfiltered results
        if not docs:
            for doc, meta, bm, doc_id in zip(documents, metadatas, bm25_scores, ids):
                authority = _authority_score(meta or {}, doc or "")
                authority_norm = min(authority, 8.0) / 8.0
                citation_norm = min(float((meta or {}).get("citation_count", 0) or 0), 3.0) / 3.0
                citation_boost = _citation_match_boost(query_terms, doc) * 0.1 if use_citation_boost else 0.0
                score = (bm * 0.6) + (_keyword_overlap_score(query, doc) * 0.2) + (authority_norm * 0.15) + (citation_norm * 0.05) + citation_boost
                docs.append(_build_result_doc(doc, meta or {}, score, doc_id))
                if len(docs) >= k:
                    break
    else:
        # No legal_area requested: return top-k
        for doc, meta, bm, doc_id in zip(documents, metadatas, bm25_scores, ids):
            authority = _authority_score(meta or {}, doc or "")
            authority_norm = min(authority, 8.0) / 8.0
            citation_norm = min(float((meta or {}).get("citation_count", 0) or 0), 3.0) / 3.0
            citation_boost = _citation_match_boost(query_terms, doc) * 0.1 if use_citation_boost else 0.0
            score = (bm * 0.6) + (_keyword_overlap_score(query, doc) * 0.2) + (authority_norm * 0.15) + (citation_norm * 0.05) + citation_boost
            docs.append(_build_result_doc(doc, meta or {}, score, doc_id))
            if len(docs) >= k:
                break

    docs.sort(key=lambda d: d.get("score", 0.0), reverse=True)
    if os.getenv("ACQ_EXACT_CITATION_SCAN") == "1" and query_terms:
        if not any(_citation_match_boost(query_terms, d.get("text", "")) > 0 for d in docs):
            exact_hits = _local_exact_citation_scan(query_terms, k, chroma_dir)
            if exact_hits:
                return exact_hits[:k]
    return docs[:k]
