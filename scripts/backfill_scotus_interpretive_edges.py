from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from acquittify.ontology.anchor_scope import extract_authority_mentions_syllabus_first
from acquittify.paths import PRECEDENT_VAULT_ROOT, REPORTS_ROOT

DEFAULT_VAULT_ROOT = PRECEDENT_VAULT_ROOT
DEFAULT_REPORT_PATH = REPORTS_ROOT / "scotus_interpretive_edge_backfill_latest.json"
SYLLABUS_AUTHORITY_MIN_MENTIONS = 3


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    close_idx = text.find("\n---\n", 4)
    if close_idx == -1:
        return {}, text
    frontmatter_text = text[4:close_idx]
    body = text[close_idx + 5 :]
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return payload, body


def _render_frontmatter(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000000).strip()


def _compact(value: str, max_len: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max(0, max_len - 1)].rstrip()}…"


def _first_sentence(value: str, max_len: int = 380) -> str:
    text = _compact(value, max_len=max_len * 2)
    if not text:
        return ""
    sentences = re.findall(r"[^.!?]+[.!?]", text)
    for sentence in sentences:
        cleaned = _compact(sentence, max_len=max_len)
        if len(cleaned) < 28:
            continue
        if re.search(r"\bv\.$", cleaned.lower()):
            continue
        return cleaned
    match = re.search(r"^(.+?[.!?])(?:\s+|$)", text)
    if match:
        candidate = _compact(match.group(1), max_len=max_len)
        if len(candidate) >= 28 and not re.search(r"\bv\.$", candidate.lower()):
            return candidate
    return _compact(text, max_len=max_len)


def _extract_year(date_decided: str) -> str:
    match = re.search(r"(\d{4})", str(date_decided or ""))
    return match.group(1) if match else "0000"


def _fallback_summary(title: str, date_decided: str, citation: str) -> str:
    year = _extract_year(date_decided)
    name = _compact(title or "This case", 160)
    cite = _compact(citation, 120)
    if cite:
        return f"{name} ({year}) addresses issues reflected in {cite}; structured summary was backfilled from available metadata."
    return f"{name} ({year}) addresses questions identified in the opinion record; structured summary was backfilled from available metadata."


def _read_opinion_text(data: dict[str, Any], case_note_path: Path) -> str:
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    opinion_url = str((sources or {}).get("opinion_url") or data.get("opinion_url") or "").strip()
    if opinion_url:
        candidate = Path(opinion_url).expanduser()
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
    try:
        return case_note_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _context_span(text: str, start_char: int | None, end_char: int | None, fallback: str) -> str:
    if not text:
        return _compact(fallback, 320)
    start = max(0, int(start_char or 0))
    end = max(start, int(end_char or start))
    if start >= len(text):
        return _compact(fallback, 320)

    left = start
    while left > 0 and text[left - 1] not in ".!?\n":
        left -= 1
    right = min(len(text), max(end + 1, start + 1))
    while right < len(text) and text[right] not in ".!?\n":
        right += 1
    if right < len(text):
        right += 1

    snippet = _compact(text[left:right], 320)
    if snippet:
        return snippet
    return _compact(fallback, 320)


def _is_strong_interpretive_context(context: str) -> bool:
    ctx = context.lower()
    patterns = [
        r"\bwe hold\b",
        r"\bwe interpret\b",
        r"\bplain meaning\b",
        r"\blegislative history\b",
        r"\brule of lenity\b",
        r"\bconstitutional avoidance\b",
        r"\bambiguous\b",
        r"\bunconstitutional\b",
        r"\bunder the\b",
        r"\bviolates\b",
        r"\bdue process\b",
        r"\bequal protection\b",
        r"\boverrul",
        r"\bquestion(?:s|ed)?\b",
        r"\bdistinguish",
        r"\bclarif",
        r"\bconstrue",
    ]
    return any(re.search(pattern, ctx) for pattern in patterns)


@dataclass
class EdgeDecision:
    edge_type: str
    confidence: float


def _classify_constitution(context: str) -> EdgeDecision:
    ctx = context.lower()
    if re.search(r"\boverrul\w*\b", ctx):
        return EdgeDecision("OVERRULES_PRECEDENT_UNDER", 0.92)
    if re.search(r"\bquestion\w*\b|\bviability\b|\bdoubt\w*\b", ctx):
        return EdgeDecision("QUESTIONS_PRECEDENT_UNDER", 0.86)
    if re.search(r"\bunconstitutional\b", ctx) and re.search(r"\b(regulation|rule|c\.f\.r)\b", ctx):
        return EdgeDecision("INVALIDATES_REGULATION_UNDER", 0.9)
    if re.search(r"\bunconstitutional\b", ctx):
        return EdgeDecision("INVALIDATES_STATUTE_UNDER", 0.88)
    if re.search(r"\breject\w*\b.*\bconstitutional challenge\b|\bconstitutional challenge\b.*\breject\w*\b", ctx):
        return EdgeDecision("REJECTS_CONSTITUTIONAL_CHALLENGE", 0.84)
    if re.search(r"\buphold\w*\b.*\b(statute|act|law)\b", ctx):
        return EdgeDecision("UPHOLDS_STATUTE_AGAINST", 0.82)
    if re.search(r"\brecogniz\w*\b.*\bright\b|\bnew right\b", ctx):
        return EdgeDecision("RECOGNIZES_RIGHT_UNDER", 0.84)
    if re.search(r"\blimit\w*\b.*\bscope\b|\bscope\b.*\blimit\w*\b", ctx):
        return EdgeDecision("LIMITS_AMENDMENT_SCOPE", 0.8)
    if re.search(r"\bnarrow\w*\b", ctx):
        return EdgeDecision("NARROWS_AMENDMENT", 0.78)
    if re.search(r"\bbroaden\w*\b|\bexpand\w*\b", ctx):
        return EdgeDecision("BROADENS_AMENDMENT", 0.78)
    if re.search(r"\bextend\w*\b", ctx):
        return EdgeDecision("EXTENDS_AMENDMENT", 0.76)
    if re.search(r"\bclarif\w*\b|\bdoctrine\b", ctx):
        return EdgeDecision("CLARIFIES_DOCTRINE", 0.75)
    if re.search(r"\bmean\w*\b|\bexplains?\b", ctx):
        return EdgeDecision("EXPLAINS_AMENDMENT", 0.72)
    return EdgeDecision("APPLIES_AMENDMENT", 0.68)


def _classify_statute_like(context: str, default_edge: str = "INTERPRETS_STATUTE") -> EdgeDecision:
    ctx = context.lower()
    if re.search(r"\brule of lenity\b|\blenity\b", ctx):
        return EdgeDecision("APPLIES_LENITY", 0.9)
    if re.search(r"\bconstrue\w*\b.*\bavoid\b.*\bconstitutional\b", ctx):
        return EdgeDecision("CONSTRUES_TO_AVOID_CONSTITUTIONAL_ISSUE", 0.9)
    if re.search(r"\bconstitutional avoidance\b|\bavoid\b.*\bconstitutional\b", ctx):
        return EdgeDecision("APPLIES_CONSTITUTIONAL_AVOIDANCE", 0.87)
    if re.search(r"\bplain meaning\b|\btext and structure\b", ctx):
        return EdgeDecision("APPLIES_PLAIN_MEANING", 0.86)
    if re.search(r"\blegislative history\b|\bcongress intended\b", ctx):
        return EdgeDecision("USES_LEGISLATIVE_HISTORY", 0.82)
    if re.search(r"\bambiguous\b", ctx):
        return EdgeDecision("FINDS_STATUTE_AMBIGUOUS", 0.82)
    if re.search(r"\bresolve\w*\b.*\bambigu", ctx):
        return EdgeDecision("RESOLVES_STATUTORY_AMBIGUITY", 0.82)
    if re.search(r"\bunconstitutional\b", ctx):
        return EdgeDecision("INVALIDATES_STATUTE", 0.85)
    if re.search(r"\bsever\w*\b", ctx):
        return EdgeDecision("SEVERS_PROVISION", 0.82)
    if re.search(r"\bdistinguish\w*\b", ctx):
        return EdgeDecision("DISTINGUISHES_STATUTE", 0.79)
    if re.search(r"\breject\w*\b.*\bexpansive\b|\bdecline\w*\b.*\bbroad\b", ctx):
        return EdgeDecision("REJECTS_EXPANSIVE_READING", 0.8)
    if re.search(r"\bnarrow\w*\b|\bconstrue\w*\b.*\bnarrow", ctx):
        return EdgeDecision("NARROWS_STATUTE", 0.79)
    if re.search(r"\bbroaden\w*\b|\bexpand\w*\b", ctx):
        return EdgeDecision("BROADENS_STATUTE", 0.79)
    if re.search(r"\bextend\w*\b", ctx):
        return EdgeDecision("EXTENDS_STATUTE", 0.78)
    if default_edge == "CLARIFIES_DOCTRINE":
        return EdgeDecision("CLARIFIES_DOCTRINE", 0.66)
    return EdgeDecision("INTERPRETS_STATUTE", 0.7)


def _classify_prior_case(context: str, role: str) -> EdgeDecision | None:
    ctx = context.lower()
    if re.search(r"\boverrul\w*\b", ctx):
        return EdgeDecision("OVERRULES_PRECEDENT_UNDER", 0.92)
    if re.search(r"\bquestion\w*\b|\bviability\b|\bdoubt\w*\b", ctx):
        return EdgeDecision("QUESTIONS_PRECEDENT_UNDER", 0.86)
    if re.search(r"\bclarif\w*\b|\bdistinguish\w*\b|\bunder\b|\bcontrolled by\b|\bwe hold\b", ctx):
        return EdgeDecision("CLARIFIES_DOCTRINE", 0.78)
    if role == "controlling":
        return EdgeDecision("CLARIFIES_DOCTRINE", 0.74)
    return None


def _map_authority_type(source_type: str) -> str | None:
    value = str(source_type or "").strip().lower()
    if value == "constitution":
        return "CONSTITUTION"
    if value in {"statute", "statutes_at_large", "public_law"}:
        return "STATUTE"
    if value in {"reg", "guideline"}:
        return "REGULATION"
    if value == "rule":
        return "FEDERAL_RULE"
    return None


def _dedupe_edges(edges: list[dict[str, Any]], limit: int = 48) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (
            str(edge.get("authority_type") or ""),
            str(edge.get("edge_type") or ""),
            str(edge.get("target_authority") or ""),
            str(edge.get("target_case_id") or ""),
        )
        existing = by_key.get(key)
        if existing is None or float(edge.get("confidence", 0.0) or 0.0) > float(existing.get("confidence", 0.0) or 0.0):
            by_key[key] = edge
    ranked = sorted(
        by_key.values(),
        key=lambda item: (
            -float(item.get("confidence", 0.0) or 0.0),
            str(item.get("authority_type", "")),
            str(item.get("edge_type", "")),
            str(item.get("target_authority", "")),
        ),
    )
    return ranked[: max(1, int(limit))]


def _infer_pdf_path(data: dict[str, Any]) -> str:
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    existing = str((sources or {}).get("opinion_pdf_path") or data.get("opinion_pdf_path") or "").strip()
    if existing:
        return existing

    opinion_url = str((sources or {}).get("opinion_url") or data.get("opinion_url") or "").strip()
    if not opinion_url:
        return ""
    candidate = Path(opinion_url).expanduser()
    if not candidate.exists():
        return ""
    if candidate.is_file() and candidate.suffix.lower() == ".pdf":
        return str(candidate)
    if candidate.is_file() and candidate.suffix.lower() in {".md", ".txt"}:
        sibling = candidate.with_suffix(".pdf")
        if sibling.exists() and sibling.is_file():
            return str(sibling)
        try:
            siblings = sorted(item for item in candidate.parent.iterdir() if item.is_file() and item.suffix.lower() == ".pdf")
        except Exception:
            siblings = []
        if len(siblings) == 1:
            return str(siblings[0])
    return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill SCOTUS interpretive edges and hover-card metadata.")
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT, help="Path to precedent_vault")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of case files to process")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing interpretive_edges")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="Path to JSON report")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cases_root = (args.vault_root / "cases" / "scotus").resolve()
    files = sorted(cases_root.rglob("*.md"))
    if args.limit and args.limit > 0:
        files = files[: int(args.limit)]

    stats: dict[str, Any] = {
        "vault_root": str(args.vault_root),
        "scanned": 0,
        "changed": 0,
        "with_interpretive_edges_before": 0,
        "with_interpretive_edges_after": 0,
        "interpretive_edges_added_total": 0,
        "missing_hover_before": 0,
        "missing_hover_after": 0,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    edge_type_counts: dict[str, int] = defaultdict(int)
    authority_type_counts: dict[str, int] = defaultdict(int)
    authority_scope_counts: dict[str, int] = defaultdict(int)
    samples_changed: list[str] = []

    for case_path in files:
        stats["scanned"] += 1
        raw = case_path.read_text(encoding="utf-8", errors="ignore")
        data, body = _split_frontmatter(raw)
        if not data:
            continue
        case_id = str(data.get("case_id") or "").strip()
        title = str(data.get("title") or "").strip()
        date_decided = str(data.get("date_decided") or "").strip()
        sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
        primary_citation = str((sources or {}).get("primary_citation") or data.get("primary_citation") or data.get("citation") or "").strip()

        existing_edges = data.get("interpretive_edges")
        if isinstance(existing_edges, list) and existing_edges:
            stats["with_interpretive_edges_before"] += 1
        if not args.overwrite and isinstance(existing_edges, list) and existing_edges:
            # Still patch missing hover metadata if needed.
            edges_to_write = existing_edges
        else:
            opinion_text = _read_opinion_text(data, case_path)
            authority_mentions, authority_scope, _syllabus_span = extract_authority_mentions_syllabus_first(
                opinion_text,
                min_mentions_for_syllabus=SYLLABUS_AUTHORITY_MIN_MENTIONS,
            )
            authority_scope_counts[authority_scope] += 1
            grouped_authorities: dict[str, Any] = {}
            for mention in authority_mentions:
                sid = str(getattr(mention, "source_id", "") or "").strip()
                if not sid:
                    continue
                candidate = grouped_authorities.get(sid)
                conf = float(getattr(mention, "confidence", 0.0) or 0.0)
                if candidate is None or conf > candidate["confidence"]:
                    grouped_authorities[sid] = {
                        "source_id": sid,
                        "source_type": str(getattr(mention, "source_type", "") or "").strip(),
                        "normalized_text": str(getattr(mention, "normalized_text", "") or "").strip(),
                        "start_char": int(getattr(mention, "start_char", 0) or 0),
                        "end_char": int(getattr(mention, "end_char", 0) or 0),
                        "confidence": conf,
                    }

            new_edges: list[dict[str, Any]] = []
            for item in grouped_authorities.values():
                authority_type = _map_authority_type(item["source_type"])
                if not authority_type:
                    continue
                context = _context_span(opinion_text, item["start_char"], item["end_char"], item["normalized_text"])

                if authority_type == "CONSTITUTION":
                    decision = _classify_constitution(context)
                elif authority_type == "STATUTE":
                    decision = _classify_statute_like(context, default_edge="INTERPRETS_STATUTE")
                elif authority_type in {"REGULATION", "FEDERAL_RULE"}:
                    if re.search(r"\bunconstitutional\b", context.lower()) and authority_type == "REGULATION":
                        decision = EdgeDecision("INVALIDATES_REGULATION_UNDER", 0.84)
                    else:
                        decision = _classify_statute_like(context, default_edge="CLARIFIES_DOCTRINE")
                else:
                    continue

                # Keep high precision for non-constitutional non-statutory mentions.
                if authority_type in {"REGULATION", "FEDERAL_RULE"} and not _is_strong_interpretive_context(context):
                    continue

                new_edges.append(
                    {
                        "source_case": case_id,
                        "target_authority": item["normalized_text"],
                        "authority_type": authority_type,
                        "edge_type": decision.edge_type,
                        "confidence": round(max(0.0, min(1.0, decision.confidence)), 2),
                        "text_span": context,
                        "target_source_id": item["source_id"],
                    }
                )

            citation_anchors = data.get("citation_anchors") if isinstance(data.get("citation_anchors"), list) else []
            for anchor in citation_anchors:
                if not isinstance(anchor, dict):
                    continue
                target_case_id = str(anchor.get("resolved_case_id") or "").strip()
                if not target_case_id or target_case_id == case_id:
                    continue
                role = str(anchor.get("role") or "").strip().lower()
                start_char = int(anchor.get("start_char") or 0)
                end_char = int(anchor.get("end_char") or start_char)
                normalized_text = str(anchor.get("normalized_text") or anchor.get("raw_text") or "").strip()
                context = _context_span(opinion_text, start_char, end_char, normalized_text)
                decision = _classify_prior_case(context, role=role)
                if decision is None:
                    continue
                new_edges.append(
                    {
                        "source_case": case_id,
                        "target_authority": normalized_text,
                        "authority_type": "PRIOR_CASE",
                        "edge_type": decision.edge_type,
                        "confidence": round(max(0.0, min(1.0, decision.confidence)), 2),
                        "text_span": context,
                        "target_case_id": target_case_id,
                    }
                )

            edges_to_write = _dedupe_edges(new_edges, limit=48)

        for edge in edges_to_write:
            edge_type_counts[str(edge.get("edge_type") or "")] += 1
            authority_type_counts[str(edge.get("authority_type") or "")] += 1

        before_summary = str(data.get("case_summary") or "").strip()
        before_holding = str(data.get("essential_holding") or "").strip()
        before_citation = primary_citation
        if not before_summary or not before_holding or not before_citation:
            stats["missing_hover_before"] += 1

        changed = False

        if not isinstance(sources, dict):
            sources = {}
            data["sources"] = sources

        if not str(data.get("case_name") or "").strip() and title:
            data["case_name"] = title
            changed = True

        if not primary_citation:
            fallback_citation = ""
            citations_in_text = data.get("citations_in_text") if isinstance(data.get("citations_in_text"), list) else []
            if citations_in_text:
                fallback_citation = str(citations_in_text[0] or "").strip()
            if not fallback_citation:
                match = re.search(r"(\d+\s+U\.S\.\s+\d+)", case_path.name)
                fallback_citation = match.group(1) if match else ""
            if fallback_citation:
                sources["primary_citation"] = fallback_citation
                primary_citation = fallback_citation
                changed = True

        if not str(data.get("case_summary") or "").strip():
            data["case_summary"] = _fallback_summary(title, date_decided, primary_citation)
            changed = True
        existing_holding = str(data.get("essential_holding") or "").strip()
        if not existing_holding:
            data["essential_holding"] = _compact(str(data.get("case_summary") or ""), max_len=300) or "Holding text not yet extracted."
            changed = True
        elif len(existing_holding) < 20 or re.search(r"\b(?:v|u|u\.s)\.$", existing_holding.lower()):
            replacement = _compact(str(data.get("case_summary") or ""), max_len=300)
            if replacement and replacement != existing_holding:
                data["essential_holding"] = replacement
                changed = True

        inferred_pdf = _infer_pdf_path(data)
        if inferred_pdf and not str(sources.get("opinion_pdf_path") or "").strip():
            sources["opinion_pdf_path"] = inferred_pdf
            changed = True

        existing = data.get("interpretive_edges")
        if not isinstance(existing, list):
            existing = []
        if existing != edges_to_write:
            data["interpretive_edges"] = edges_to_write
            changed = True

        if isinstance(data.get("interpretive_edges"), list) and data["interpretive_edges"]:
            stats["with_interpretive_edges_after"] += 1
            stats["interpretive_edges_added_total"] += len(data["interpretive_edges"])

        after_summary = str(data.get("case_summary") or "").strip()
        after_holding = str(data.get("essential_holding") or "").strip()
        after_citation = str((data.get("sources") or {}).get("primary_citation") or data.get("primary_citation") or "").strip()
        if not after_summary or not after_holding or not after_citation:
            stats["missing_hover_after"] += 1

        if changed:
            rendered = f"---\n{_render_frontmatter(data)}\n---\n{body if body.startswith(chr(10)) else chr(10) + body}"
            case_path.write_text(rendered, encoding="utf-8")
            stats["changed"] += 1
            if len(samples_changed) < 24:
                samples_changed.append(str(case_path))

    report = {
        "stats": stats,
        "edge_type_counts": dict(sorted(edge_type_counts.items(), key=lambda kv: kv[0])),
        "authority_type_counts": dict(sorted(authority_type_counts.items(), key=lambda kv: kv[0])),
        "authority_scope_counts": dict(sorted(authority_scope_counts.items(), key=lambda kv: kv[0])),
        "sample_changed_files": samples_changed,
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
