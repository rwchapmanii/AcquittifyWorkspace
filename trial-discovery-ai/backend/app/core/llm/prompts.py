PASS1_PROMPT_ID = "pass1_v1"
PASS1_REPAIR_PROMPT_ID = "pass1_v1_repair"
PASS2_PROMPT_ID = "pass2_v1"
PASS2_REPAIR_PROMPT_ID = "pass2_v1_repair"
PASS4_PROMPT_ID = "pass4_v1"
PASS4_REPAIR_PROMPT_ID = "pass4_v1_repair"

PASS1_SYSTEM_PROMPT = """
You are an information extraction system. Output ONLY valid JSON that matches the Pass 1 schema.
You must be deterministic and factual. Do not infer beyond the provided text and metadata.
If a field is unknown, set it to null or an empty list as appropriate.
When determining doc_type.category, consider all common document families:
EMAIL, PDF, SCANNED_IMAGE, WORD, SPREADSHEET, PRESENTATION, CHAT, TEXT, LOG,
CODE, IMAGE, AUDIO, VIDEO, CALENDAR, DATABASE_EXPORT, PLEADING, CONTRACT,
REPORT, NOTES, OTHER. If uncertain, use OTHER and set draft_final/internal_external/domain to UNKNOWN.
If the content is non-textual or low quality, still classify the document family and set quality fields accordingly.
Use the DOCUMENT METADATA block (JSON) to improve identity fields (author/sender, dates, doc type, custodian-like hints).
If you assert identity conclusions, add identity_evidence strings (short citations like "email.subject", "pdf.title", "filename").
Additional required fields for review:
- document_type: plain-language type label (align with doc_type.category when possible).
- witnesses: list of witness names referenced or authored in the document (empty if none).
- document_date: the most explicit document date (prefer ISO-8601 if present).
- relevance: High / Medium / Low / Unknown based on explicit cues in the text; do not leave null.
- proponent: the creator/author/sender if explicitly stated; otherwise set to "Unknown" (do not leave null).
""".strip()

PASS1_REPAIR_PROMPT = """
You are a JSON repair system. Your task is to fix invalid JSON so it conforms exactly to the schema.
Return ONLY valid JSON. Do not add commentary.
""".strip()

PASS2_SYSTEM_PROMPT = """
You are an analysis system. Output ONLY valid JSON that matches the Pass 2 schema.
Be conservative. Do not infer beyond the provided text. Use nulls or empty lists when uncertain.
If the document is non-textual or low quality, keep events/statements/knowledge_signals empty and set only what is directly supported.
""".strip()

PASS2_REPAIR_PROMPT = PASS1_REPAIR_PROMPT

PASS4_SYSTEM_PROMPT = """
You are a trial-prep prioritization system. Output ONLY valid JSON that matches the Pass 4 schema.
Use conservative, citeable rationales. Do not assert facts not in the provided text.
If evidence is insufficient, prefer P3/P4 with a brief rationale stating limited usable content.
""".strip()

PASS4_REPAIR_PROMPT = PASS1_REPAIR_PROMPT


def build_pass1_prompt(document_text: str, metadata_hint: str | None = None) -> str:
    meta_block = (
        f"\n\nDOCUMENT METADATA (JSON):\n{metadata_hint}" if metadata_hint else ""
    )
    return (
        PASS1_SYSTEM_PROMPT
        + meta_block
        + "\n\nDOCUMENT TEXT:\n"
        + document_text
        + "\n\nReturn JSON only."
    )


def build_pass1_repair_prompt(raw_text: str, schema_json: str) -> str:
    return (
        PASS1_REPAIR_PROMPT
        + "\n\nSCHEMA JSON:\n"
        + schema_json
        + "\n\nRAW OUTPUT:\n"
        + raw_text
        + "\n\nReturn JSON only."
    )


def build_pass2_prompt(document_text: str) -> str:
    return (
        PASS2_SYSTEM_PROMPT
        + "\n\nDOCUMENT TEXT:\n"
        + document_text
        + "\n\nReturn JSON only."
    )


def build_pass2_repair_prompt(raw_text: str, schema_json: str) -> str:
    return (
        PASS2_REPAIR_PROMPT
        + "\n\nSCHEMA JSON:\n"
        + schema_json
        + "\n\nRAW OUTPUT:\n"
        + raw_text
        + "\n\nReturn JSON only."
    )


def build_pass4_prompt(document_text: str) -> str:
    return (
        PASS4_SYSTEM_PROMPT
        + "\n\nDOCUMENT TEXT:\n"
        + document_text
        + "\n\nReturn JSON only."
    )


def build_pass4_repair_prompt(raw_text: str, schema_json: str) -> str:
    return (
        PASS4_REPAIR_PROMPT
        + "\n\nSCHEMA JSON:\n"
        + schema_json
        + "\n\nRAW OUTPUT:\n"
        + raw_text
        + "\n\nReturn JSON only."
    )
