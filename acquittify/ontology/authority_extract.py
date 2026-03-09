from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AuthorityMention:
    raw_text: str
    normalized_text: str
    source_id: str
    source_type: str
    start_char: int
    end_char: int
    confidence: float
    extractor: str = "regex"


_USC_RE = re.compile(
    r"(?P<title>\d{1,3})\s*U\.?\s*S\.?\s*C(?:\.?A\.?|\.?S\.?)?\.?\s*(?:§{1,2}|Sec(?:tion)?\.?)\s*(?P<sections>[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*(?:\s*(?:,|and|&)\s*[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*)*(?:\s*et\s+seq\.?)?)",
    flags=re.IGNORECASE,
)
_USC_NO_TITLE_RE = re.compile(
    r"U\.?\s*S\.?\s*C(?:\.?A\.?|\.?S\.?)?\.?\s*(?:§{1,2}|Sec(?:tion)?\.?)\s*(?P<sections>[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*(?:\s*(?:,|and|&)\s*[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*)*(?:\s*et\s+seq\.?)?)",
    flags=re.IGNORECASE,
)
_USC_TITLE_SECTION_RE = re.compile(
    r"Title\s+(?P<title>\d{1,3})\b[^.\n;]{0,140}?\b(?:Section|Sec\.?|§)\s*(?P<section>[0-9A-Za-z][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*)",
    flags=re.IGNORECASE,
)
_USC_SHORTHAND_SECTION_RE = re.compile(
    r"\b(?:Section|Sec\.?)\s*(?P<section>\d{2,5}[A-Za-z0-9.\-]*(?:\([A-Za-z0-9]+\))*)|\B§{1,2}\s*(?P<section_symbol>\d{2,5}[A-Za-z0-9.\-]*(?:\([A-Za-z0-9]+\))*)",
    flags=re.IGNORECASE,
)

_CFR_RE = re.compile(
    r"(?P<title>\d{1,3})\s*C\.?\s*F\.?\s*R\.?\s*(?:§{1,2}|Sec(?:tion)?\.?)\s*(?P<sections>[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*(?:\s*(?:,|and|&)\s*[0-9][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*)*)",
    flags=re.IGNORECASE,
)
_CFR_PART_RE = re.compile(
    r"(?P<title>\d{1,3})\s*C\.?\s*F\.?\s*R\.?\s*(?:pt\.?|part)\s*(?P<part>\d+(?:\.\d+)*)",
    flags=re.IGNORECASE,
)
_CFR_APPENDIX_RE = re.compile(
    r"(?P<title>\d{1,3})\s*C\.?\s*F\.?\s*R\.?\s*(?:pt\.?|part)\s*(?P<part>\d+(?:\.\d+)*)\s*,\s*App\.?\s*(?P<appendix>[A-Za-z0-9]+)",
    flags=re.IGNORECASE,
)

_FED_RULE_RE = re.compile(
    r"Fed\.?\s*R\.?\s*(?P<set>Crim|Civ|Evid|App)\.?\s*(?:P\.?\s*)?(?P<rule>\d+[A-Za-z]?(?:\([0-9A-Za-z]+\))*)",
    flags=re.IGNORECASE,
)
_FED_RULE_ABBR_RE = re.compile(
    r"\b(?P<abbr>FRCP|FRCrP|FRE|FRAP)\s*(?P<rule>\d+[A-Za-z]?(?:\([0-9A-Za-z]+\))*)",
    flags=re.IGNORECASE,
)
_FED_RULE_SHORTHAND_RE = re.compile(
    r"\bRule\s+(?P<rule>\d+[A-Za-z]?(?:\([0-9A-Za-z]+\))*)",
    flags=re.IGNORECASE,
)

_USSG_RE = re.compile(
    r"(?:U\.?\s*S\.?\s*S\.?\s*G\.?|Guideline)\s*§\s*(?P<section>[0-9A-Za-z][0-9A-Za-z.\-]*(?:\([0-9A-Za-z]+\))*)(?:\s*(?:cmt\.|comment\.?)\s*(?:n\.?|note)?\s*(?P<comment>[0-9A-Za-z().-]+))?",
    flags=re.IGNORECASE,
)
_USSG_SECTION_SHORTHAND_RE = re.compile(
    r"\bSection\s+(?P<section>[1-9][A-Za-z][0-9]+\.[0-9]+)\s+(?:departure|adjustment|enhancement)\b",
    flags=re.IGNORECASE,
)

_US_CONST_AMEND_RE = re.compile(
    r"U\.?\s*S\.?\s*Const\.?\s*amend\.?\s*(?P<amend>[IVXLCM]+|\d+)",
    flags=re.IGNORECASE,
)
_US_CONST_ART_RE = re.compile(
    r"U\.?\s*S\.?\s*Const\.?\s*art\.?\s*(?P<article>[IVXLCM]+|\d+)(?:,\s*§\s*(?P<section>\d+))?(?:,\s*cl\.?\s*(?P<clause>\d+))?",
    flags=re.IGNORECASE,
)
_TEXTUAL_AMEND_RE = re.compile(
    r"\b(?P<name>First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|Eighteenth|Nineteenth|Twentieth|Twenty-First|Twenty First|Twenty-Second|Twenty Second|Twenty-Third|Twenty Third|Twenty-Fourth|Twenty Fourth|Twenty-Fifth|Twenty Fifth|Twenty-Sixth|Twenty Sixth|Twenty-Seventh|Twenty Seventh)\s+Amendment\b",
    flags=re.IGNORECASE,
)
_ORDINAL_AMEND_RE = re.compile(
    r"\b(?P<num>\d{1,2})(?:st|nd|rd|th)\s+Amendment\b",
    flags=re.IGNORECASE,
)
_SHORT_AMEND_RE = re.compile(
    r"\bAmend(?:ment)?\.?\s*(?P<amend>[IVXLCM]+|\d+)\b",
    flags=re.IGNORECASE,
)
_COMMERCE_CLAUSE_RE = re.compile(r"\bCommerce Clause\b", flags=re.IGNORECASE)

_PUB_LAW_RE = re.compile(r"Pub\.?\s*L\.?\s*No\.?\s*(?P<number>\d{1,3}\s*-\s*\d{1,4})", flags=re.IGNORECASE)
_STAT_AT_LARGE_RE = re.compile(r"\b(?P<volume>\d{1,4})\s+Stat\.?\s+(?P<page>\d{1,5})\b", flags=re.IGNORECASE)

_USC_CONTEXT_RE = re.compile(r"(\d{1,3})\s*U\.?\s*S\.?\s*C", flags=re.IGNORECASE)
_USC_TITLE_CONTEXT_RE = re.compile(r"Title\s+(\d{1,3})", flags=re.IGNORECASE)
_CFR_CONTEXT_RE = re.compile(r"(\d{1,3})\s*C\.?\s*F\.?\s*R", flags=re.IGNORECASE)
_RULE_CONTEXT_RE = re.compile(r"Fed\.?\s*R\.?\s*(Crim|Civ|Evid|App)\.?\s*P\.?", flags=re.IGNORECASE)
_USSG_CONTEXT_RE = re.compile(r"(U\.?\s*S\.?\s*S\.?\s*G\.?|Guideline)", flags=re.IGNORECASE)

_KNOWN_SHORTHAND_USC_TITLE = {
    "1983": "42",
    "2254": "28",
    "2255": "28",
}

_AMENDMENT_NAME_TO_NUM = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twenty-first": 21,
    "twenty first": 21,
    "twenty-second": 22,
    "twenty second": 22,
    "twenty-third": 23,
    "twenty third": 23,
    "twenty-fourth": 24,
    "twenty fourth": 24,
    "twenty-fifth": 25,
    "twenty fifth": 25,
    "twenty-sixth": 26,
    "twenty sixth": 26,
    "twenty-seventh": 27,
    "twenty seventh": 27,
}


def _roman_to_int(value: str) -> int | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.isdigit():
        try:
            return int(text)
        except Exception:
            return None
    roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for char in reversed(text):
        current = roman_map.get(char)
        if current is None:
            return None
        if current < prev:
            total -= current
        else:
            total += current
            prev = current
    return total if total > 0 else None


def _int_to_roman(value: int) -> str:
    number = int(value)
    if number <= 0:
        return str(value)
    table = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    parts: list[str] = []
    remaining = number
    for unit, token in table:
        while remaining >= unit:
            parts.append(token)
            remaining -= unit
    return "".join(parts)


def _sanitize_token(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\bet\s+seq\.?\b", "et_seq", text, flags=re.IGNORECASE)
    text = re.sub(r"\(([^)]+)\)", lambda m: f"_{m.group(1)}", text)
    text = text.replace("§", "")
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_.-").lower()


def _normalize_section_text(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    return text.strip(".,;:")


def _split_sections(sections_text: str) -> tuple[list[str], bool]:
    text = str(sections_text or "").strip()
    et_seq = bool(re.search(r"\bet\s+seq\.?\b", text, flags=re.IGNORECASE))
    text = re.sub(r"\bet\s+seq\.?\b", "", text, flags=re.IGNORECASE).strip(" ,;.")
    parts = [item.strip() for item in re.split(r"\s*(?:,|and|&)\s*", text) if item.strip()]
    return parts, et_seq


def _trim_cross_citation_trailer(sections: list[str], follow_text: str) -> list[str]:
    items = [str(item).strip() for item in sections if str(item).strip()]
    if not items:
        return items
    if re.match(r"^\s*(?:U\.?\s*S\.?\s*C|C\.?\s*F\.?\s*R)\b", str(follow_text or ""), flags=re.IGNORECASE):
        last = items[-1]
        if re.fullmatch(r"\d{1,3}", last):
            return items[:-1]
    return items


def _infer_recent_context(pattern: re.Pattern[str], text: str, pos: int, window: int = 320) -> str | None:
    left = max(0, pos - int(window))
    snippet = text[left:pos]
    matches = list(pattern.finditer(snippet))
    if not matches:
        return None
    value = matches[-1].group(1)
    return str(value).strip() if value is not None else None


def _infer_rule_set(text: str, pos: int) -> str:
    left = max(0, pos - 240)
    right = min(len(text), pos + 90)
    snippet = text[left:right]
    explicit = list(_RULE_CONTEXT_RE.finditer(snippet))
    if explicit:
        value = explicit[-1].group(1).lower()
        return {"crim": "crim", "civ": "civ", "evid": "evid", "app": "app"}.get(value, "unknown")
    lowered = snippet.lower()
    if "criminal" in lowered:
        return "crim"
    if "civil" in lowered:
        return "civ"
    if "evidence" in lowered:
        return "evid"
    if "appellate" in lowered:
        return "app"
    return "unknown"


def _append(
    out: list[AuthorityMention],
    seen: set[tuple[int, int, str]],
    *,
    raw_text: str,
    normalized_text: str,
    source_id: str,
    source_type: str,
    start_char: int,
    end_char: int,
    confidence: float,
    extractor: str = "regex",
) -> None:
    key = (int(start_char), int(end_char), str(source_id))
    if not source_id or key in seen:
        return
    seen.add(key)
    out.append(
        AuthorityMention(
            raw_text=raw_text,
            normalized_text=normalized_text,
            source_id=source_id,
            source_type=source_type,
            start_char=int(start_char),
            end_char=int(end_char),
            confidence=max(0.0, min(1.0, float(confidence))),
            extractor=extractor,
        )
    )


def extract_authority_mentions(text: str) -> list[AuthorityMention]:
    body = str(text or "")
    mentions: list[AuthorityMention] = []
    seen: set[tuple[int, int, str]] = set()

    for match in _USC_RE.finditer(body):
        title = str(match.group("title") or "").strip()
        sections_text = str(match.group("sections") or "")
        sections, et_seq = _split_sections(sections_text)
        sections = _trim_cross_citation_trailer(sections, body[match.end() : match.end() + 24])
        for section in sections:
            normalized_section = _normalize_section_text(section)
            if not normalized_section:
                continue
            source_id = f"statute.usc.{int(title)}"
            normalized = f"{int(title)} U.S.C. § {normalized_section}"
            if et_seq:
                normalized = f"{normalized} et seq."
            _append(
                mentions,
                seen,
                raw_text=match.group(0),
                normalized_text=normalized,
                source_id=source_id,
                source_type="statute",
                start_char=match.start(),
                end_char=match.end(),
                confidence=0.98,
            )

    for match in _USC_NO_TITLE_RE.finditer(body):
        title = _infer_recent_context(_USC_CONTEXT_RE, body, match.start()) or _infer_recent_context(
            _USC_TITLE_CONTEXT_RE, body, match.start()
        )
        if not title:
            continue
        sections_text = str(match.group("sections") or "")
        sections, et_seq = _split_sections(sections_text)
        sections = _trim_cross_citation_trailer(sections, body[match.end() : match.end() + 24])
        for section in sections:
            normalized_section = _normalize_section_text(section)
            if not normalized_section:
                continue
            source_id = f"statute.usc.{int(title)}"
            normalized = f"{int(title)} U.S.C. § {normalized_section}"
            if et_seq:
                normalized = f"{normalized} et seq."
            _append(
                mentions,
                seen,
                raw_text=match.group(0),
                normalized_text=normalized,
                source_id=source_id,
                source_type="statute",
                start_char=match.start(),
                end_char=match.end(),
                confidence=0.9,
            )

    for match in _USC_TITLE_SECTION_RE.finditer(body):
        title = str(match.group("title") or "").strip()
        section = _normalize_section_text(match.group("section") or "")
        if not title or not section:
            continue
        source_id = f"statute.usc.{int(title)}"
        normalized = f"{int(title)} U.S.C. § {section}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="statute",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.92,
        )

    for match in _USC_SHORTHAND_SECTION_RE.finditer(body):
        immediate_context = body[max(0, match.start() - 40) : match.start()]
        if re.search(r"U\.?\s*S\.?\s*C", immediate_context, flags=re.IGNORECASE):
            continue
        section = _normalize_section_text(match.group("section") or match.group("section_symbol") or "")
        if not section:
            continue
        if "." in section and re.search(r"C\.?\s*F\.?\s*R", body[max(0, match.start() - 120) : match.start()], flags=re.IGNORECASE):
            continue
        section_prefix = re.match(r"[0-9]+", section)
        section_base = section_prefix.group(0) if section_prefix else section
        known_title = _KNOWN_SHORTHAND_USC_TITLE.get(section_base)
        title = _infer_recent_context(_USC_CONTEXT_RE, body, match.start()) or _infer_recent_context(
            _USC_TITLE_CONTEXT_RE, body, match.start()
        )
        if known_title:
            title = known_title
        if not title:
            continue
        source_id = f"statute.usc.{int(title)}"
        normalized = f"{int(title)} U.S.C. § {section}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="statute",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.76,
            extractor="regex_context",
        )

    for match in _CFR_RE.finditer(body):
        title = str(match.group("title") or "").strip()
        sections_text = str(match.group("sections") or "")
        sections, _ = _split_sections(sections_text)
        sections = _trim_cross_citation_trailer(sections, body[match.end() : match.end() + 24])
        for section in sections:
            normalized_section = _normalize_section_text(section)
            if not normalized_section:
                continue
            source_id = f"reg.cfr.{int(title)}"
            normalized = f"{int(title)} C.F.R. § {normalized_section}"
            _append(
                mentions,
                seen,
                raw_text=match.group(0),
                normalized_text=normalized,
                source_id=source_id,
                source_type="reg",
                start_char=match.start(),
                end_char=match.end(),
                confidence=0.97,
            )

    for match in _CFR_PART_RE.finditer(body):
        title = str(match.group("title") or "").strip()
        part = _normalize_section_text(match.group("part") or "")
        if not part:
            continue
        source_id = f"reg.cfr.{int(title)}"
        normalized = f"{int(title)} C.F.R. pt. {part}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="reg",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.95,
        )

    for match in _CFR_APPENDIX_RE.finditer(body):
        title = str(match.group("title") or "").strip()
        part = _normalize_section_text(match.group("part") or "")
        appendix = _sanitize_token(match.group("appendix") or "")
        if not part or not appendix:
            continue
        source_id = f"reg.cfr.{int(title)}"
        normalized = f"{int(title)} C.F.R. pt. {part}, App. {appendix.upper()}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="reg",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.94,
        )

    for match in _FED_RULE_RE.finditer(body):
        set_name = str(match.group("set") or "").strip().lower()
        rule_token = _sanitize_token(match.group("rule") or "")
        if not rule_token:
            continue
        rule_set = {"crim": "crim", "civ": "civ", "evid": "evid", "app": "app"}.get(set_name, "unknown")
        source_id = f"rule.federal.{rule_set}.{rule_token}"
        normalized = f"Fed. R. {rule_set.title()}. P. {match.group('rule')}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="rule",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.96,
        )

    for match in _FED_RULE_ABBR_RE.finditer(body):
        abbr = str(match.group("abbr") or "").upper()
        rule_token = _sanitize_token(match.group("rule") or "")
        if not rule_token:
            continue
        rule_set = {"FRCP": "civ", "FRCRP": "crim", "FRE": "evid", "FRAP": "app"}.get(abbr, "unknown")
        source_id = f"rule.federal.{rule_set}.{rule_token}"
        normalized = f"Fed. R. {rule_set.title()}. P. {match.group('rule')}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="rule",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.92,
        )

    for match in _FED_RULE_SHORTHAND_RE.finditer(body):
        immediate_context = body[max(0, match.start() - 30) : match.start()]
        if re.search(r"Fed\.?\s*R\.?", immediate_context, flags=re.IGNORECASE):
            continue
        rule_value = str(match.group("rule") or "").strip()
        rule_token = _sanitize_token(rule_value)
        if not rule_token:
            continue
        rule_set = _infer_rule_set(body, match.start())
        source_id = f"rule.federal.{rule_set}.{rule_token}"
        normalized = f"Fed. R. {rule_set.title()}. P. {rule_value}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="rule",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.74 if rule_set != "unknown" else 0.6,
            extractor="regex_context",
        )

    for match in _USSG_RE.finditer(body):
        section = str(match.group("section") or "").strip()
        if not section:
            continue
        source_id = f"reg.ussg.{_sanitize_token(section)}"
        normalized = f"U.S.S.G. § {section}"
        comment = str(match.group("comment") or "").strip()
        if comment:
            normalized = f"{normalized} cmt. {comment}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="guideline",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.96,
        )

    for match in _USSG_SECTION_SHORTHAND_RE.finditer(body):
        section = str(match.group("section") or "").strip()
        source_id = f"reg.ussg.{_sanitize_token(section)}"
        normalized = f"U.S.S.G. § {section}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="guideline",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.72,
            extractor="regex_context",
        )

    for match in _US_CONST_AMEND_RE.finditer(body):
        amendment_raw = str(match.group("amend") or "").strip()
        amendment_num = _roman_to_int(amendment_raw)
        if amendment_num is None:
            continue
        source_id = f"constitution.us.amendment.{int(amendment_num)}"
        normalized = f"U.S. Const. amend. {_int_to_roman(amendment_num)}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.98,
        )

    for match in _TEXTUAL_AMEND_RE.finditer(body):
        key = str(match.group("name") or "").strip().lower()
        number = _AMENDMENT_NAME_TO_NUM.get(key)
        if number is None:
            continue
        source_id = f"constitution.us.amendment.{number}"
        normalized = f"U.S. Const. amend. {_int_to_roman(number)}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.82,
            extractor="regex_context",
        )

    for match in _ORDINAL_AMEND_RE.finditer(body):
        number = _roman_to_int(match.group("num") or "")
        if number is None:
            continue
        source_id = f"constitution.us.amendment.{number}"
        normalized = f"U.S. Const. amend. {_int_to_roman(number)}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.8,
            extractor="regex_context",
        )

    for match in _SHORT_AMEND_RE.finditer(body):
        context = body[max(0, match.start() - 40) : match.start()].lower()
        if "const" not in context and "constitution" not in context:
            continue
        amendment_raw = str(match.group("amend") or "").strip()
        amendment_num = _roman_to_int(amendment_raw)
        if amendment_num is None:
            continue
        source_id = f"constitution.us.amendment.{int(amendment_num)}"
        normalized = f"U.S. Const. amend. {_int_to_roman(amendment_num)}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.78,
            extractor="regex_context",
        )

    for match in _US_CONST_ART_RE.finditer(body):
        article_num = _roman_to_int(match.group("article") or "")
        if article_num is None:
            continue
        section = str(match.group("section") or "").strip()
        clause = str(match.group("clause") or "").strip()
        source_id = f"constitution.us.article.{int(article_num)}"
        normalized = f"U.S. Const. art. {_int_to_roman(article_num)}"
        if section:
            source_id = f"{source_id}.section.{_sanitize_token(section)}"
            normalized = f"{normalized}, § {section}"
        if clause:
            source_id = f"{source_id}.clause.{_sanitize_token(clause)}"
            normalized = f"{normalized}, cl. {clause}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.97,
        )

    for match in _COMMERCE_CLAUSE_RE.finditer(body):
        source_id = "constitution.us.article.1.section.8.clause.3"
        normalized = "U.S. Const. art. I, § 8, cl. 3 (Commerce Clause)"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="constitution",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.7,
            extractor="regex_context",
        )

    for match in _PUB_LAW_RE.finditer(body):
        number = re.sub(r"\s+", "", str(match.group("number") or ""))
        source_id = f"statute.public_law.{_sanitize_token(number)}"
        normalized = f"Pub. L. No. {number}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="public_law",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.94,
        )

    for match in _STAT_AT_LARGE_RE.finditer(body):
        volume = str(match.group("volume") or "").strip()
        page = str(match.group("page") or "").strip()
        if not volume or not page:
            continue
        source_id = f"statute.statutes_at_large.{_sanitize_token(volume)}.{_sanitize_token(page)}"
        normalized = f"{int(volume)} Stat. {int(page)}"
        _append(
            mentions,
            seen,
            raw_text=match.group(0),
            normalized_text=normalized,
            source_id=source_id,
            source_type="statutes_at_large",
            start_char=match.start(),
            end_char=match.end(),
            confidence=0.93,
        )

    mentions.sort(key=lambda item: (item.start_char, item.end_char, item.source_id))
    return mentions
