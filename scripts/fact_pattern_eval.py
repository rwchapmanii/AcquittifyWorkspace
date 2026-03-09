#!/usr/bin/env python3
"""Generate responses for fact patterns and evaluate QA compliance.

This script:
- Loads fact patterns from eval/fact_patterns.jsonl
- Retrieves sources from Chroma without taxonomy filtering
- Calls the local Ollama model (if available)
- Checks response compliance (IRAC headings, Authority Ladder, citations)
- Writes JSON + Markdown reports under eval/
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.citation_utils import has_citations
from acquittify_retriever import retrieve

FACT_PATTERNS = PROJECT_ROOT / "eval" / "fact_patterns.jsonl"
REPORT_JSON = PROJECT_ROOT / "eval" / "fact_pattern_report.json"
REPORT_MD = PROJECT_ROOT / "eval" / "fact_pattern_report.md"
CHROMA_DIR = PROJECT_ROOT / "Corpus" / "Chroma"

OLLAMA_URL = os.getenv("ACQUITTIFY_OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("ACQUITTIFY_OLLAMA_MODEL", "qwen2.5:32b-instruct")
TIMEOUT = float(os.getenv("ACQUITTIFY_OLLAMA_TIMEOUT", "180"))
TOP_K = int(os.getenv("ACQUITTIFY_FACT_EVAL_TOP_K", "5"))


def load_system_prompt() -> str:
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    marker = 'SYSTEM_PROMPT = """'
    if marker not in app_text:
        return ""
    tail = app_text.split(marker, 1)[1]
    return tail.split('"""', 1)[0]


def _append_meta_line(lines: list[str], label: str, value) -> None:
    if value is None:
        return
    if isinstance(value, (list, tuple, set)):
        rendered = "; ".join(str(v) for v in value if v)
    else:
        rendered = str(value).strip()
    if rendered:
        lines.append(f"{label}: {rendered}")


def build_sources_message_from_docs(docs: list[dict]) -> Dict[str, str]:
    if not docs:
        return {
            "role": "system",
            "content": (
                "You are a legal AI assistant. No direct SOURCES have been provided for this query. Proceed as follows:\n"
                "- Rely on established knowledge of federal criminal law only where you are confident.\n"
                "- You may mention well-known authorities by name without citation, but do NOT invent details.\n"
                "- Do not fabricate case names, dates, or statutory numbers.\n"
                "- If unsure or if a point requires authority, state that additional sources are needed.\n"
                "- Do not assume facts not in the user’s question.\n"
                "- In the Rule section, explicitly state that no SOURCES were provided and note the gap."
            ),
        }

    lines = [
        "You are a legal AI assistant with access to the following SOURCES, which are authoritative excerpts relevant to the user’s question. Use ONLY these sources for analysis and citations.",
        "- Ground all claims in SOURCES: Every statement of law or fact must be supported by the provided sources.",
        "- Cite appropriately: Use Bluebook-formatted authority from the provided CITATIONS/STATUTES/RULES lines only.",
        "- Comprehensive use of sources: Incorporate all relevant sources; if a detail is missing, acknowledge the gap.",
        "If multiple citation types are present, use this order: Case → Statute → Regulation → Treatise.",
        "",
    ]

    for idx, d in enumerate(docs, start=1):
        excerpt_lines = [
            f"SOURCE EXCERPT {idx:04d}",
            f"TITLE: {d.get('title','')}",
            f"SOURCE_TYPE: {d.get('source_type','')}",
            f"PATH: {d.get('path','')}",
            f"CHUNK_INDEX: {d.get('chunk_index','')}",
        ]
        _append_meta_line(excerpt_lines, "DOC_ID", d.get("doc_id"))
        _append_meta_line(excerpt_lines, "SOURCE_ID", d.get("source_id") or d.get("source_opinion_id"))
        _append_meta_line(excerpt_lines, "SOURCE_IDS", d.get("source_ids"))
        _append_meta_line(excerpt_lines, "COURT", d.get("court"))
        _append_meta_line(excerpt_lines, "CIRCUIT", d.get("circuit"))
        _append_meta_line(excerpt_lines, "YEAR", d.get("year"))
        _append_meta_line(excerpt_lines, "POSTURE", d.get("posture"))
        _append_meta_line(excerpt_lines, "TAXONOMY_VERSION", d.get("taxonomy_version"))
        _append_meta_line(excerpt_lines, "TAXONOMY", d.get("taxonomy"))
        _append_meta_line(excerpt_lines, "IS_HOLDING", d.get("is_holding"))
        _append_meta_line(excerpt_lines, "IS_DICTA", d.get("is_dicta"))
        _append_meta_line(excerpt_lines, "STANDARD_OF_REVIEW", d.get("standard_of_review"))
        _append_meta_line(excerpt_lines, "BURDEN", d.get("burden"))
        _append_meta_line(excerpt_lines, "FAVORABILITY", d.get("favorability"))
        _append_meta_line(
            excerpt_lines,
            "CITATIONS",
            d.get("bluebook_case_citations") or d.get("bluebook_citations") or d.get("citations"),
        )
        _append_meta_line(excerpt_lines, "STATUTES", d.get("bluebook_statutes") or d.get("statutes"))
        _append_meta_line(excerpt_lines, "RULES", d.get("rules"))
        excerpt_lines.extend([
            "----",
            d.get("text", ""),
            "",
        ])
        lines.extend(excerpt_lines)

    return {"role": "system", "content": "\n".join(lines)}


def _has_required_headings(text: str) -> bool:
    headings = ["Issue", "Rule", "Analysis", "Conclusion"]
    return all(re.search(rf"^\s*{h}\s*$", text or "", re.M) for h in headings)


def _has_authority_ladder(text: str) -> bool:
    return bool(re.search(r"\bAuthority Ladder\b", text or ""))


def _has_followups(text: str) -> bool:
    if not text:
        return False
    match = re.search(r"^\s*Conclusion\s*$", text, flags=re.M)
    if not match:
        return False
    tail = text[match.end():]
    return bool(re.search(r"^\s*\d+\.\s+", tail, flags=re.M))


def _sources_have_authority(sources_msg: Dict[str, str]) -> bool:
    content = sources_msg.get("content", "") if isinstance(sources_msg, dict) else ""
    return any(label in content for label in ("CITATIONS:", "STATUTES:", "RULES:"))


def _ollama_available() -> bool:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": "ping"}]},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _call_llm(messages: List[Dict[str, str]]) -> Optional[str]:
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")
    except Exception:
        return None


def _call_with_retry(messages: List[Dict[str, str]], sources_msg: Dict[str, str]) -> Optional[str]:
    reply = _call_llm(messages) or ""

    for _ in range(2):
        needs_headings = not _has_required_headings(reply)
        needs_ladder = not _has_authority_ladder(reply)
        needs_followups = not _has_followups(reply)
        needs_cites = _sources_have_authority(sources_msg) and not has_citations(reply)
        if not (needs_headings or needs_ladder or needs_followups or needs_cites):
            return reply
        retry_messages = (
            messages[:-1]
            + [
                {
                    "role": "system",
                    "content": (
                        "Revision Required — Add Missing Citations and Fix Format. "
                        "Preserve the IRAC structure and wording, but ensure strict compliance as follows: "
                        "- Headings must be exactly: Issue, Rule, Analysis, Conclusion (standalone lines, no punctuation, no formatting). "
                        "- Include an 'Authority Ladder' list in the Rule section. "
                        "- End the Conclusion section with a numbered list (1., 2., 3., ...) of follow-up questions. "
                        "- Cite every legal rule, fact, and conclusion that relies on SOURCES using Bluebook format. "
                        "- Use only citations provided in SOURCES; do not invent any authority. "
                        "- If a necessary point is not covered by SOURCES, state that explicitly. "
                        "- Do not add new analysis or extra commentary; focus only on compliance."
                    ),
                }
            ]
            + [messages[-1]]
        )
        reply = _call_llm(retry_messages) or reply

    if not reply.strip():
        fallback = _call_llm(messages)
        if fallback:
            reply = fallback

    return reply or None


def load_fact_patterns() -> List[Dict[str, Any]]:
    rows = []
    for line in FACT_PATTERNS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def main() -> int:
    if not FACT_PATTERNS.exists():
        raise SystemExit(f"Missing fact patterns: {FACT_PATTERNS}")

    system_prompt = load_system_prompt()
    if not system_prompt:
        raise SystemExit("SYSTEM_PROMPT not found in app.py")

    rows = load_fact_patterns()
    llm_ready = _ollama_available()

    results = []
    for idx, row in enumerate(rows, start=1):
        prompt = row.get("prompt", "")
        docs = retrieve(prompt, legal_area="", k=TOP_K, chroma_dir=CHROMA_DIR)
        sources_msg = build_sources_message_from_docs(docs)
        response_text = None
        if llm_ready:
            messages = [
                {"role": "system", "content": system_prompt},
                sources_msg,
                {"role": "user", "content": prompt},
            ]
            response_text = _call_with_retry(messages, sources_msg)
            time.sleep(0.2)

        citations_expected = _sources_have_authority(sources_msg)
        has_cites = has_citations(response_text or "") if response_text else False
        result = {
            "id": row.get("id"),
            "title": row.get("title"),
            "prompt": prompt,
            "sources_count": len(docs),
            "llm_called": llm_ready,
            "response_len": len(response_text or ""),
            "headings_ok": _has_required_headings(response_text or ""),
            "authority_ladder_ok": _has_authority_ladder(response_text or ""),
            "followups_ok": _has_followups(response_text or ""),
            "citations_expected": citations_expected,
            "citations_present": has_cites,
        }
        results.append(result)
        print(f"[{idx}/{len(rows)}] {row.get('id')} sources={len(docs)} response_len={result['response_len']}")

    summary = {
        "total": len(results),
        "llm_called": llm_ready,
        "avg_sources": round(sum(r["sources_count"] for r in results) / max(len(results), 1), 2),
        "headings_ok": sum(1 for r in results if r["headings_ok"]),
        "authority_ladder_ok": sum(1 for r in results if r["authority_ladder_ok"]),
        "followups_ok": sum(1 for r in results if r["followups_ok"]),
        "citations_expected": sum(1 for r in results if r["citations_expected"]),
        "citations_present": sum(1 for r in results if r["citations_present"]),
    }

    REPORT_JSON.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")

    lines = [
        "# Fact Pattern QA Report",
        "",
        f"- Total patterns: {summary['total']}",
        f"- LLM available: {summary['llm_called']}",
        f"- Average sources retrieved: {summary['avg_sources']}",
        f"- Headings OK: {summary['headings_ok']}/{summary['total']}",
        f"- Authority Ladder OK: {summary['authority_ladder_ok']}/{summary['total']}",
        f"- Follow-up questions OK: {summary['followups_ok']}/{summary['total']}",
        f"- Citations expected: {summary['citations_expected']}",
        f"- Citations present: {summary['citations_present']}",
        "",
        "## Notable misses",
    ]

    misses = [r for r in results if r["llm_called"] and (not r["headings_ok"] or not r["authority_ladder_ok"] or (r["citations_expected"] and not r["citations_present"]))]
    if not misses:
        lines.append("- None")
    else:
        for r in misses[:15]:
            lines.append(
                f"- {r['id']} ({r['title']}): headings_ok={r['headings_ok']} ladder_ok={r['authority_ladder_ok']} citations_expected={r['citations_expected']} citations_present={r['citations_present']}"
            )

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote reports to {REPORT_JSON} and {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
