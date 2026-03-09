from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable

import yaml


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the",
    "of",
    "and",
    "or",
    "to",
    "in",
    "on",
    "for",
    "a",
    "an",
    "by",
    "with",
    "without",
    "from",
    "general",
}


@dataclass(frozen=True)
class TaxonomyNode:
    code: str
    label: str
    phrases: tuple[str, ...]
    tokens: tuple[str, ...]


def _normalize_text(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\\s]", " ", text)
    return re.sub(r"\\s+", " ", text).strip()


def _phrase_tokens(phrase: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(_normalize_text(phrase)) if token and token not in _STOPWORDS]


def _load_taxonomy_nodes_uncached(taxonomy_path: Path, aliases_path: Path | None = None) -> list[TaxonomyNode]:
    if not taxonomy_path.exists():
        return []

    payload = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    nodes_raw = payload.get("nodes") or []
    alias_map = {}
    if aliases_path and aliases_path.exists():
        alias_payload = yaml.safe_load(aliases_path.read_text(encoding="utf-8"))
        if isinstance(alias_payload, dict):
            alias_map = alias_payload.get("aliases") or {}

    nodes: list[TaxonomyNode] = []
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        label = str(item.get("label") or "").strip()
        if not code or not label:
            continue
        synonyms = item.get("synonyms") or []
        phrases = [label] + [str(s).strip() for s in synonyms if str(s).strip()]
        token_set = []
        for phrase in phrases:
            token_set.extend(_phrase_tokens(phrase))
        tokens = tuple(sorted(set(token_set)))
        nodes.append(TaxonomyNode(code=alias_map.get(code, code), label=label, phrases=tuple(phrases), tokens=tokens))
    return nodes


@lru_cache(maxsize=8)
def _load_taxonomy_nodes_cached(taxonomy_path_str: str, aliases_path_str: str | None) -> tuple[TaxonomyNode, ...]:
    taxonomy_path = Path(taxonomy_path_str)
    aliases_path = Path(aliases_path_str) if aliases_path_str else None
    return tuple(_load_taxonomy_nodes_uncached(taxonomy_path, aliases_path))


def _load_taxonomy_nodes(taxonomy_path: Path, aliases_path: Path | None = None) -> list[TaxonomyNode]:
    taxonomy_key = str(taxonomy_path.resolve())
    aliases_key = str(aliases_path.resolve()) if aliases_path else None
    return list(_load_taxonomy_nodes_cached(taxonomy_key, aliases_key))


def _match_score(text: str, node: TaxonomyNode) -> int:
    lower = _normalize_text(text)
    if not lower:
        return 0
    tokens = set(_TOKEN_RE.findall(lower))
    score = 0
    for phrase in node.phrases:
        phrase_norm = _normalize_text(phrase)
        if not phrase_norm or len(phrase_norm) < 4:
            continue
        if phrase_norm in lower:
            score += 2 if " " in phrase_norm else 1
            if score >= 2:
                return score
    if node.tokens:
        overlap = len(set(node.tokens).intersection(tokens))
        if overlap >= 2:
            score += 1
    return score


def map_case_taxonomies(
    *,
    title: str,
    case_summary: str,
    essential_holding: str,
    opinion_text: str,
    taxonomy_path: Path,
    aliases_path: Path | None = None,
    max_results: int = 12,
) -> list[dict[str, str]]:
    nodes = _load_taxonomy_nodes(taxonomy_path, aliases_path)
    if not nodes:
        return []

    text = "\\n".join(
        [
            str(title or ""),
            str(case_summary or ""),
            str(essential_holding or ""),
            str(opinion_text or "")[:20000],
        ]
    )

    scored: list[tuple[int, TaxonomyNode]] = []
    for node in nodes:
        score = _match_score(text, node)
        if score >= 2:
            scored.append((score, node))

    scored.sort(key=lambda item: (-item[0], item[1].code))
    selected = scored[: max(1, int(max_results))]
    return [{"code": node.code, "label": node.label} for _, node in selected]
