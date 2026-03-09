import json
import re
from pathlib import Path

import requests

PROJECT_ROOT = Path("/Users/ronaldchapman/Desktop/Acquittify")
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "acquittify-qwen"
QUERY = "Draft a legal memo about Hobbs Act robbery statutes and caselaw."


def load_system_prompt() -> str:
    app_text = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    marker = 'SYSTEM_PROMPT = """'
    if marker not in app_text:
        return ""
    tail = app_text.split(marker, 1)[1]
    return tail.split('"""', 1)[0]


def build_sources_from_paths(paths: list[Path]) -> list[str]:
    excerpts: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        excerpts.append(
            "\n".join(
                [
                    f"TITLE: {path.parent.name}",
                    "SOURCE_TYPE: corpus_backup",
                    f"PATH: {path}",
                    f"CHUNK_INDEX: {path.stem.replace('chunk_', '')}",
                    "----",
                    text,
                ]
            )
        )
    return excerpts


def build_sources_message(excerpts: list[str]) -> dict:
    if not excerpts:
        return {
            "role": "system",
            "content": (
                "SOURCES:\n"
                "(No relevant authority was retrieved from the Acquittify corpus for this query.)\n\n"
                "You may NOT cite any case, statute, or authority.\n"
                "Use [TBV] where verification is required and specify what documents must be added."
            ),
        }

    lines = [
        "SOURCES (authoritative excerpts from Acquittify corpus):",
        "You may rely ONLY on the excerpts below and must cite them as [SRC: DOC####].",
        "Use any CITATIONS/STATUTES/RULES lines in the excerpts as authority hints, but still cite with [SRC: DOC####].",
        "",
    ]
    for idx, src in enumerate(excerpts, start=1):
        lines.append(f"[SRC: DOC{idx:04d}]")
        lines.append(src)
        lines.append("")
    return {"role": "system", "content": "\n".join(lines)}


def run() -> None:
    system_prompt = load_system_prompt()
    sources = build_sources_from_paths(
        [
            PROJECT_ROOT
            / "Corpus"
            / "Chroma"
            / "documents"
            / "Federal Sentencing Guidelines "
            / "chunk_240.txt",
            PROJECT_ROOT
            / "Corpus"
            / "Chroma"
            / "documents"
            / "Federal Sentencing Guidelines "
            / "chunk_370.txt",
            PROJECT_ROOT
            / "Corpus"
            / "Chroma"
            / "documents"
            / "2022 Term Scotus Cases "
            / "chunk_136.txt",
            PROJECT_ROOT
            / "Corpus"
            / "Chroma"
            / "documents"
            / "2022 Term Scotus Cases "
            / "chunk_60.txt",
        ]
    )
    sources_msg = build_sources_message(sources)

    messages = [
        {"role": "system", "content": system_prompt},
        sources_msg,
        {"role": "user", "content": QUERY},
    ]

    def _call(msgs):
        payload = {
            "model": MODEL,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        response = requests.post(OLLAMA_URL, json=payload, timeout=240)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")

    reply = _call(messages)

    print("=== MEMO OUTPUT (start) ===")
    print(reply[:2000])
    print("\n=== CHECKS ===")
    heads = ["Issue", "Rule", "Analysis", "Conclusion"]
    head_ok = all(re.search(rf"^\s*{h}\s*$", reply, re.M) for h in heads)
    has_src = bool(re.search(r"\[SRC: DOC\d{4}\]", reply))
    ladder = bool(re.search(r"Authority Ladder", reply))
    follow = bool(re.search(r"Conclusion[\s\S]*?\n\s*\d+\.\s+", reply))

    if not head_ok or not has_src or not ladder:
        repair = (
            "Format/citation violations detected. "
            "Rewrite the response so that headings are exactly: Issue, Rule, Analysis, Conclusion "
            "(standalone lines, no punctuation). "
            "Include an 'Authority Ladder' list in the Rule section. "
            "Cite every sourced statement using [SRC: DOC####]. "
            "Do not add any other headings or prefaces."
        )
        retry_messages = messages[:-1] + [{"role": "system", "content": repair}] + [messages[-1]]
        reply = _call(retry_messages)
        head_ok = all(re.search(rf"^\s*{h}\s*$", reply, re.M) for h in heads)
        has_src = bool(re.search(r"\[SRC: DOC\d{4}\]", reply))
        ladder = bool(re.search(r"Authority Ladder", reply))

    print(
        json.dumps(
            {
                "headings_ok": head_ok,
                "has_src_cites": has_src,
                "authority_ladder_ok": ladder,
                "followup_questions_ok": follow,
                "sources_count": len(sources),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
