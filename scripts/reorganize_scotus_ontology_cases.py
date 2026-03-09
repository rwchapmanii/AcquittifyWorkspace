#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from acquittify.paths import PRECEDENT_VAULT_ROOT

DEFAULT_SCOTUS_CASES_ROOT = PRECEDENT_VAULT_ROOT / "cases" / "scotus"
DEFAULT_REPORT_PATH = PRECEDENT_VAULT_ROOT / "indices" / "scotus_case_reorg_report.json"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]+')
WHITESPACE_RE = re.compile(r"\s+")
US_CITATION_RE = re.compile(r"\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b", re.IGNORECASE)
US_CITE_AS_RE = re.compile(r"\bCite\s+as:\s*(\d+\s*U\.?\s*S\.?\s*[0-9_]+)\b", re.IGNORECASE)
GENERIC_REPORTER_RE = re.compile(r"\b\d+\s+[A-Za-z][A-Za-z.\s]*\s+\d+\b")
CASE_LINE_RE = re.compile(r"\bv\.?\b", re.IGNORECASE)
DOCKET_RE = re.compile(r"^\d{1,2}-\d{1,6}[a-z]*$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rename/reorganize SCOTUS ontology case notes by year and case caption.")
    parser.add_argument("--cases-root", type=Path, default=DEFAULT_SCOTUS_CASES_ROOT, help="Path to precedent_vault/cases/scotus")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH, help="JSON report output path")
    parser.add_argument("--dry-run", action="store_true", help="Print planned moves without applying them")
    return parser.parse_args()


def _split_frontmatter(raw_text: str) -> tuple[str, str]:
    text = raw_text or ""
    if not text.startswith("---\n"):
        return "", text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + len(marker) :]


def _load_frontmatter(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}
    frontmatter_text, _ = _split_frontmatter(raw_text)
    if not frontmatter_text.strip():
        return {}
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _load_note(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}, ""
    frontmatter_text, body = _split_frontmatter(raw_text)
    if not frontmatter_text.strip():
        return {}, raw_text
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
        meta = parsed if isinstance(parsed, dict) else {}
        return meta, body
    except Exception:
        return {}, body


def _to_pretty_case_name(raw: str) -> str:
    value = (raw or "").replace("Â", "").replace("\u00a0", " ").strip()
    value = re.sub(r"^SUPREME COURT OF THE UNITED STATES\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b\d{1,2}[–-]\d{1,6}\b", " ", value)
    value = re.sub(r"^\d+\s+", "", value)
    value = re.sub(r"^\d{1,2}-\d{1,6}[a-z]*\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d{1,2}[a-z]\d+\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bet\s*al\.?", "et al.", value, flags=re.IGNORECASE)
    value = re.split(r"\bON WRITS?\b|\bON PETITION\b|\[", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    value = re.sub(r"\s+v\.?\s*", " v. ", value, count=1, flags=re.IGNORECASE)
    value = re.sub(r",?\s*PETITIONERS?\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r",?\s*RESPONDENTS?\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r",?\s*INDIVIDUALLY\b", "", value, flags=re.IGNORECASE)
    value = WHITESPACE_RE.sub(" ", value).strip(" ,.;")

    letters = [ch for ch in value if ch.isalpha()]
    uppercase_ratio = (sum(ch.isupper() for ch in letters) / len(letters)) if letters else 0.0
    if uppercase_ratio > 0.55:
        lowers = {"v.", "of", "and", "the", "for", "to", "in", "on", "a", "an", "et", "al."}
        words = value.lower().split()
        titled: list[str] = []
        for idx, word in enumerate(words):
            if idx > 0 and word in lowers:
                titled.append(word)
            else:
                titled.append(word.capitalize())
        value = " ".join(titled)

    value = value.replace(" V. ", " v. ")
    value = value.replace(" Vs. ", " v. ")
    value = re.sub(r"\bet al\.\b", "et al.", value, flags=re.IGNORECASE)
    value = re.sub(r"\bEt Al\.\b", "et al.", value)
    value = re.sub(r"^In Re\b", "In re", value)
    return WHITESPACE_RE.sub(" ", value).strip(" ,.;")


def _looks_like_case_name(raw: str) -> bool:
    value = (raw or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("v. "):
        return False
    if lowered.startswith("justice "):
        return False
    if DOCKET_RE.fullmatch(value):
        return False
    if re.match(r"^in re\b", value, flags=re.IGNORECASE):
        return bool(re.search(r"[A-Za-z]", value[5:]))
    if not CASE_LINE_RE.search(value):
        return False
    left, _, right = re.sub(r"\s+v\.?\s*", " v. ", value, count=1, flags=re.IGNORECASE).partition(" v. ")
    return bool(re.search(r"[A-Za-z]", left) and re.search(r"[A-Za-z]", right))


def _extract_case_name_from_text(raw_text: str) -> str:
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in (raw_text or "").splitlines()[:260]]
    marker_idx = -1
    for idx, line in enumerate(lines):
        if "SUPREME COURT OF THE UNITED STATES" in line.upper():
            marker_idx = idx
            break
    if marker_idx != -1:
        window = lines[marker_idx + 1 : marker_idx + 28]
        collected: list[str] = []
        for line in window:
            cleaned = re.sub(r"^\d+\s+", "", line).strip()
            if not cleaned:
                if collected:
                    break
                continue
            lowered = cleaned.lower()
            if lowered.startswith(("syllabus", "per curiam", "certiorari", "on petition", "no.", "argued", "decided", "held:")):
                if collected:
                    break
                continue
            if "supreme court" in lowered:
                continue
            if lowered.startswith("in re "):
                return cleaned
            if CASE_LINE_RE.search(cleaned):
                if re.match(r"^(?:\d{1,2}[–-]\d{1,6}\s*)?PETITIONERS?\s+v\.?", cleaned, flags=re.IGNORECASE):
                    prefix = ""
                    for back_idx in range(idx - 1, marker_idx, -1):
                        previous_line = re.sub(r"^\d+\s+", "", lines[back_idx]).strip()
                        if not previous_line:
                            continue
                        previous_lowered = previous_line.lower()
                        if previous_lowered.startswith(("syllabus", "per curiam", "certiorari", "on petition", "no.", "argued", "decided", "held:")):
                            break
                        if "supreme court" in previous_lowered:
                            break
                        if re.fullmatch(r"\d{1,2}[–-]\d{1,6}", previous_line):
                            continue
                        if re.search(r"[A-Za-z]", previous_line):
                            prefix = previous_line
                            break
                    if prefix:
                        cleaned = f"{prefix} {cleaned}"
                collected.append(cleaned)
                continue
            if collected:
                collected.append(cleaned)
                if len(collected) >= 3:
                    break
        if collected:
            joined = WHITESPACE_RE.sub(" ", " ".join(collected)).strip()
            joined = re.split(r"\bON PETITION\b|\bCERTIORARI\b", joined, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.;")
            if _looks_like_case_name(joined):
                return joined

    for idx, line in enumerate(lines):
        cleaned = re.sub(r"^\d+\s+", "", line).strip()
        if len(cleaned) < 10 or len(cleaned) > 150:
            continue
        if not re.search(r"\bv\.?\b", cleaned, flags=re.IGNORECASE):
            continue
        letters = [ch for ch in cleaned if ch.isalpha()]
        if not letters:
            continue
        uppercase_ratio = sum(ch.isupper() for ch in letters) / len(letters)
        if uppercase_ratio < 0.65:
            continue
        if re.search(r"\b\d{2,}\b", cleaned):
            continue
        if "CERTIORARI" in cleaned.upper() or "SUPREME COURT" in cleaned.upper():
            continue
        candidate = cleaned
        if idx + 1 < len(lines):
            next_clean = re.sub(r"^\d+\s+", "", lines[idx + 1]).strip()
            if next_clean:
                next_letters = [ch for ch in next_clean if ch.isalpha()]
                next_upper = (sum(ch.isupper() for ch in next_letters) / len(next_letters)) if next_letters else 0.0
                if next_upper >= 0.75 and not CASE_LINE_RE.search(next_clean) and "CERTIORARI" not in next_clean.upper():
                    candidate = f"{candidate} {next_clean}"
        if _looks_like_case_name(candidate):
            return candidate

    candidates: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        if not line or len(line) < 8 or len(line) > 180:
            continue
        line = re.sub(r"^\d+\s+", "", line).strip()
        if not CASE_LINE_RE.search(line):
            continue
        if not _looks_like_case_name(line):
            continue
        lowered = line.lower()
        if lowered.startswith(("see ", "certiorari ", "on petition ", "held:", "cite as:", "supreme court")):
            continue
        if "detroit timber" in lowered:
            continue
        score = len(line)
        if "petitioner" in lowered or "respondent" in lowered:
            score += 25
        if line.upper() == line:
            score += 6
        if "," in line:
            score += 2
        candidates.append((score, idx, line))
    if not candidates:
        return ""
    best = min(candidates)
    return best[2]


def _extract_case_name_from_source_note(opinion_url: str) -> str:
    source_path = Path(str(opinion_url or "").strip()).expanduser()
    if not source_path.exists() or not source_path.is_file():
        return ""
    try:
        raw_text = source_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    frontmatter_text, body = _split_frontmatter(raw_text)
    if frontmatter_text.strip():
        try:
            meta = yaml.safe_load(frontmatter_text) or {}
        except Exception:
            meta = {}
        if isinstance(meta, dict):
            caption = str(meta.get("caption", "")).strip()
            if _looks_like_case_name(caption) and not re.match(
                r"^(?:ET AL\.,\s*)?PETITIONERS?\s+v\.?",
                caption,
                flags=re.IGNORECASE,
            ):
                return caption
    return _extract_case_name_from_text(body)


def _extract_case_name_from_summary(summary_text: str) -> str:
    summary = WHITESPACE_RE.sub(" ", str(summary_text or "").replace("Â", " ").strip())
    if not summary:
        return ""
    summary = re.sub(r"\b\d{1,2}[–-]\d{1,6}\b", " ", summary)
    summary = re.sub(r"\s{2,}", " ", summary).strip()

    in_re_match = re.search(r"\bIN RE\s+([A-Z0-9’'.,&()\- ]{3,})", summary, flags=re.IGNORECASE)
    if in_re_match:
        candidate = f"In re {in_re_match.group(1).strip()}"
        candidate = re.split(r"\bON WRITS?\b|\bON PETITION\b|\[", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
        return candidate.strip(" ,.;")

    v_match = re.search(r"([A-Z][A-Z0-9’'.,&()\- ]{3,}?)\s+v\.\s+([A-Z][A-Z0-9’'.,&()\- ]{3,})", summary, flags=re.IGNORECASE)
    if not v_match:
        return ""
    left = v_match.group(1).strip()
    right = v_match.group(2).strip()
    left_lower = left.lower()
    if any(token in left_lower for token in ("justice ", "concurring", "dissent", "remand", "the court")):
        return ""
    letters = [ch for ch in f"{left} {right}" if ch.isalpha()]
    uppercase_ratio = (sum(ch.isupper() for ch in letters) / len(letters)) if letters else 0.0
    if uppercase_ratio < 0.55:
        return ""
    candidate = f"{left} v. {right}"
    candidate = re.split(r"\bON WRITS?\b|\bON PETITION\b|\[", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
    candidate = re.sub(r"\b\d{1,2}[–-]\d{1,6}\b", " ", candidate)
    return WHITESPACE_RE.sub(" ", candidate).strip(" ,.;")


def _citation_from_case_id(case_id: str) -> str:
    parts = [part.strip() for part in str(case_id or "").split(".") if part.strip()]
    if not parts:
        return ""
    token = parts[-1].lower()
    match = re.fullmatch(r"(\d+)us(\d+)", token)
    if not match:
        return ""
    return f"{int(match.group(1))} U.S. {int(match.group(2))}"


def _normalize_citation(raw: str) -> str:
    value = WHITESPACE_RE.sub(" ", str(raw or "").replace("Â", "").strip())
    if not value:
        return ""
    us_match = US_CITATION_RE.search(value)
    if us_match:
        return f"{int(us_match.group(1))} U.S. {us_match.group(2)}"
    generic_match = GENERIC_REPORTER_RE.search(value)
    if generic_match:
        return WHITESPACE_RE.sub(" ", generic_match.group(0).strip())
    return ""


def _choose_best_citation(frontmatter: dict[str, Any], source_text: str) -> str:
    sources = frontmatter.get("sources")
    source_map = sources if isinstance(sources, dict) else {}
    case_id = str(frontmatter.get("case_id", "")).strip()
    candidates: list[str] = []
    primary = str(source_map.get("primary_citation", "")).strip()
    if primary:
        candidates.append(primary)
    case_id_cite = _citation_from_case_id(case_id)
    if case_id_cite:
        candidates.append(case_id_cite)
    cite_as_match = US_CITE_AS_RE.search(source_text or "")
    if cite_as_match:
        candidates.append(cite_as_match.group(1))

    for candidate in candidates:
        normalized = _normalize_citation(candidate)
        if normalized:
            return normalized
    return "Unknown citation"


def _year_from_frontmatter(frontmatter: dict[str, Any]) -> str:
    date_decided = str(frontmatter.get("date_decided", "")).strip()
    match = re.match(r"^(\d{4})", date_decided)
    if match:
        return match.group(1)
    case_id = str(frontmatter.get("case_id", "")).strip()
    parts = case_id.split(".")
    if len(parts) >= 3 and re.fullmatch(r"\d{4}", parts[2]):
        return parts[2]
    return "0000"


def _sanitize_filename_component(value: str, max_len: int = 180) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", value or "")
    cleaned = cleaned.replace("\n", " ")
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip(" .")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .")
    return cleaned or "Unknown Case"


def _choose_case_name_candidate(*raw_candidates: str) -> str:
    for candidate in raw_candidates:
        pretty = _to_pretty_case_name(candidate)
        if _looks_like_case_name(pretty):
            return pretty
    return ""


def _desired_relative_path(file_path: Path, frontmatter: dict[str, Any]) -> tuple[Path, dict[str, str]]:
    case_id = str(frontmatter.get("case_id", "")).strip() or file_path.stem
    title = str(frontmatter.get("title", "")).strip()
    sources = frontmatter.get("sources")
    source_map = sources if isinstance(sources, dict) else {}
    opinion_url = str(source_map.get("opinion_url", "")).strip()
    source_name = _extract_case_name_from_source_note(opinion_url)
    summary_name = _extract_case_name_from_summary(str(frontmatter.get("case_summary", "")))
    case_name = _choose_case_name_candidate(title, source_name, summary_name)
    if not _looks_like_case_name(case_name):
        case_name = f"Case {case_id}"
    year = _year_from_frontmatter(frontmatter)
    source_text = ""
    if opinion_url:
        source_path = Path(opinion_url).expanduser()
        if source_path.exists() and source_path.is_file():
            try:
                source_text = source_path.read_text(encoding="utf-8", errors="ignore")[:5000]
            except Exception:
                source_text = ""
    citation = _choose_best_citation(frontmatter, source_text)
    display_name = f"{case_name}, {citation} ({year})"
    safe_name = _sanitize_filename_component(display_name) + ".md"
    rel_path = Path(year) / safe_name
    metadata = {
        "case_id": case_id,
        "case_name": case_name,
        "citation": citation,
        "year": year,
    }
    return rel_path, metadata


def _collect_case_files(cases_root: Path) -> list[Path]:
    files = [path for path in sorted(cases_root.rglob("*.md")) if path.is_file()]
    return files


def _rewrite_note_with_clean_title(path: Path, case_name: str) -> bool:
    meta, body = _load_note(path)
    if not meta:
        return False

    next_title = _sanitize_filename_component(case_name) if case_name else ""
    if not next_title:
        return False

    changed = False
    if str(meta.get("title", "")).strip() != next_title:
        meta["title"] = next_title
        changed = True

    body_lines = (body or "").splitlines()
    for idx, line in enumerate(body_lines):
        if line.startswith("# "):
            if line != f"# {next_title}":
                body_lines[idx] = f"# {next_title}"
                changed = True
            break

    if not changed:
        return False

    frontmatter_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    next_body = "\n".join(body_lines)
    if next_body and not next_body.endswith("\n"):
        next_body += "\n"
    content = f"---\n{frontmatter_text}\n---\n\n{next_body}"
    path.write_text(content, encoding="utf-8")
    return True


def _remove_empty_dirs(root: Path) -> None:
    for directory in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            continue


def main() -> None:
    args = parse_args()
    cases_root = args.cases_root.expanduser().resolve()
    if not cases_root.exists():
        raise FileNotFoundError(f"Cases root not found: {cases_root}")

    case_files = _collect_case_files(cases_root)
    planned_moves: list[dict[str, str]] = []
    taken_targets: set[Path] = set()

    for case_file in case_files:
        frontmatter = _load_frontmatter(case_file)
        desired_rel, meta = _desired_relative_path(case_file, frontmatter)
        target = (cases_root / desired_rel).resolve()
        source = case_file.resolve()

        suffix_index = 2
        while target in taken_targets or (target.exists() and target != source):
            candidate_name = target.stem + f" [{meta['case_id']}]"
            target = target.with_name(_sanitize_filename_component(candidate_name) + target.suffix)
            suffix_index += 1
            if suffix_index > 50:
                break
        taken_targets.add(target)

        planned_moves.append(
            {
                "source": str(source),
                "target": str(target),
                "target_rel": str(target.relative_to(cases_root)),
                "case_id": meta["case_id"],
                "case_name": meta["case_name"],
                "citation": meta["citation"],
                "year": meta["year"],
                "changed": str(source != target),
            }
        )

    moved_count = 0
    title_updates = 0
    if not args.dry_run:
        for item in planned_moves:
            source = Path(item["source"])
            target = Path(item["target"])
            if source == target:
                if _rewrite_note_with_clean_title(source, item["case_name"]):
                    title_updates += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved_count += 1
            if _rewrite_note_with_clean_title(target, item["case_name"]):
                title_updates += 1
        _remove_empty_dirs(cases_root)

    report_payload = {
        "cases_root": str(cases_root),
        "total_files": len(planned_moves),
        "moved_files": moved_count,
        "title_updates": title_updates,
        "dry_run": bool(args.dry_run),
        "moves": planned_moves,
    }

    report_path = args.report_path.expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    csv_path = report_path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "target_rel", "case_id", "case_name", "citation", "year", "changed"],
        )
        writer.writeheader()
        for row in planned_moves:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    print(
        json.dumps(
            {"total_files": len(planned_moves), "moved_files": moved_count, "title_updates": title_updates, "dry_run": bool(args.dry_run)},
            indent=2,
        )
    )
    print(f"report_json={report_path}")
    print(f"report_csv={csv_path}")


if __name__ == "__main__":
    main()
