from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import yaml

from acquittify.metadata_extract import normalize_citation

from .canonicalize import load_issue_index
from .ids import holding_note_filename, issue_note_filename
from .schemas import CaseNode, HoldingNode, IssueNode, RelationNode, SecondaryNode, SourceNode, SourceType
from .yaml_utils import dump_yaml, markdown_with_frontmatter


_RELATION_FILE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class VaultWriter:
    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root
        self.indices_dir = self.vault_root / "indices"
        self.issue_index_path = self.indices_dir / "issue_index.json"
        self.unresolved_queue_path = self.indices_dir / "unresolved_queue.md"
        self.review_checklist_path = self.indices_dir / "review_checklist.md"
        self.params_path = self.indices_dir / "params.yaml"
        self.metrics_path = self.indices_dir / "metrics.yaml"

    @staticmethod
    def _model_dump(model: Any) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump()  # type: ignore[attr-defined]
        if hasattr(model, "dict"):
            return model.dict()
        return dict(model)

    @staticmethod
    def _write_if_changed(path: Path, content: str) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == content:
                return False
        path.write_text(content, encoding="utf-8")
        return True

    @staticmethod
    def _split_frontmatter(raw_text: str) -> tuple[str, str]:
        text = raw_text or ""
        if not text.startswith("---\n"):
            return "", text
        marker = "\n---\n"
        end = text.find(marker, 4)
        if end == -1:
            return "", text
        return text[4:end], text[end + len(marker) :]

    def load_existing_issues(self) -> list[IssueNode]:
        return load_issue_index(self.issue_index_path)

    def load_existing_case_citation_map(self) -> dict[str, str]:
        case_root = self.vault_root / "cases"
        if not case_root.exists():
            return {}

        mapping: dict[str, str] = {}
        ambiguous: set[str] = set()

        def remember(citation_value: str, case_id_value: str) -> None:
            normalized_value = normalize_citation(citation_value or "")
            if not case_id_value or not normalized_value or normalized_value in ambiguous:
                return
            existing = mapping.get(normalized_value)
            if not existing:
                mapping[normalized_value] = case_id_value
                return
            if existing != case_id_value:
                mapping.pop(normalized_value, None)
                ambiguous.add(normalized_value)

        for path in sorted(case_root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            if not text.startswith("---\n"):
                continue

            case_id = None
            primary_citation = None
            for raw_line in text.splitlines()[1:220]:
                line = raw_line.strip()
                if line == "---":
                    break
                if line.startswith("case_id:"):
                    case_id = line.split(":", 1)[1].strip().strip('"').strip("'")
                    continue
                if line.startswith("primary_citation:"):
                    primary_citation = line.split(":", 1)[1].strip().strip('"').strip("'")

            if not case_id:
                continue

            remember(primary_citation or "", case_id)

        index_path = self.indices_dir / "scotus_case_citation_index.json"
        if index_path.exists():
            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            unique_map = payload.get("unique_map") if isinstance(payload, dict) else {}
            if isinstance(unique_map, dict):
                for raw_citation, case_id in unique_map.items():
                    normalized = normalize_citation(str(raw_citation or ""))
                    if normalized and case_id:
                        mapping[normalized] = str(case_id)
                        ambiguous.discard(normalized)

        return mapping

    @staticmethod
    def _year_from_date(date_decided: str) -> str:
        raw = (date_decided or "").strip()
        if re.fullmatch(r"\d{4}", raw):
            return raw
        try:
            return str(datetime.fromisoformat(raw).year)
        except Exception:
            return "0000"

    @staticmethod
    def _sanitize_case_filename(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "", value or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned or "Unknown Case"

    @classmethod
    def _normalize_display_citation(cls, value: str) -> str:
        raw = re.sub(r"\s+", " ", str(value or "").strip())
        if not raw:
            return ""
        us_match = re.search(r"\b(\d+)\s*U\.?\s*S\.?\s*([0-9_]+)\b", raw, flags=re.IGNORECASE)
        if us_match:
            return f"{int(us_match.group(1))} U.S. {us_match.group(2)}"
        generic = re.search(r"\b\d+\s+[A-Za-z][A-Za-z.\s]*\s+\d+\b", raw)
        if generic:
            return re.sub(r"\s+", " ", generic.group(0).strip())
        return cls._sanitize_case_filename(raw)

    def _case_display_filename(self, case_node: CaseNode) -> tuple[str, str]:
        year = self._year_from_date(case_node.date_decided)
        title = re.sub(r"\s+", " ", (case_node.title or "").strip())
        title = title if title else case_node.case_id
        source_map = case_node.sources if isinstance(case_node.sources, dict) else {}
        citation_candidates = [
            str(source_map.get("primary_citation", "")).strip(),
        ]
        citation = ""
        for candidate in citation_candidates:
            citation = self._normalize_display_citation(candidate)
            if citation:
                break
        if not citation:
            citation = "Unknown citation"
        filename = f"{title}, {citation} ({year}).md"
        return year, self._sanitize_case_filename(filename)

    def _find_existing_case_path(self, case_id: str) -> Path | None:
        case_root = self.vault_root / "cases"
        if not case_root.exists():
            return None
        for path in sorted(case_root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not text.startswith("---\n"):
                continue
            for raw_line in text.splitlines()[1:220]:
                line = raw_line.strip()
                if line == "---":
                    break
                if line.startswith("case_id:"):
                    found = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if found == case_id:
                        return path
                    break
        return None

    def _find_case_path_by_source(self, case_node: CaseNode) -> Path | None:
        sources = case_node.sources if isinstance(case_node.sources, dict) else {}
        opinion_url = str(sources.get("opinion_url") or "").strip()
        opinion_pdf_path = str(sources.get("opinion_pdf_path") or "").strip()
        if not opinion_url and not opinion_pdf_path:
            return None

        case_root = self.vault_root / "cases"
        if not case_root.exists():
            return None

        for path in sorted(case_root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if not text.startswith("---\n"):
                continue
            frontmatter_text, _ = self._split_frontmatter(text)
            if not frontmatter_text.strip():
                continue
            try:
                payload = yaml.safe_load(frontmatter_text) or {}
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            source_map = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
            if not isinstance(source_map, dict):
                source_map = {}
            existing_opinion_url = str(source_map.get("opinion_url") or "").strip()
            existing_pdf_path = str(source_map.get("opinion_pdf_path") or "").strip()
            if opinion_url and existing_opinion_url == opinion_url:
                return path
            if opinion_pdf_path and existing_pdf_path == opinion_pdf_path:
                return path
        return None

    def load_existing_holding_ids(self) -> set[str]:
        holdings_dir = self.vault_root / "holdings"
        if not holdings_dir.exists():
            return set()

        ids: set[str] = set()
        for path in sorted(holdings_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            if not text.startswith("---\n"):
                continue

            for line in text.splitlines()[1:200]:
                if line.strip() == "---":
                    break
                if not line.startswith("holding_id:"):
                    continue
                value = line.split(":", 1)[1].strip().strip('"').strip("'")
                if value:
                    ids.add(value)
                break
        return ids

    def _court_bucket(self, case_node: CaseNode) -> str:
        level = (case_node.court_level or "").lower()
        if "supreme" in level:
            return "scotus"
        if "circuit" in level or "appeal" in level:
            return "circuits"
        return "districts"

    def write_case(self, case_node: CaseNode) -> tuple[Path, bool]:
        year, filename = self._case_display_filename(case_node)
        desired_path = self.vault_root / "cases" / self._court_bucket(case_node) / year / filename
        existing_path = self._find_existing_case_path(case_node.case_id)
        if existing_path is None:
            existing_path = self._find_case_path_by_source(case_node)
        path = existing_path if existing_path is not None else desired_path

        frontmatter = self._model_dump(case_node)
        body = f"# {case_node.title}\n\nCase ID: `{case_node.case_id}`\n"
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    def write_holding(self, holding_node: HoldingNode, index: int) -> tuple[Path, bool]:
        filename = holding_note_filename(holding_node.case_id, index)
        path = self.vault_root / "holdings" / filename

        frontmatter = self._model_dump(holding_node)
        body = f"# Holding {index}\n\n{holding_node.holding_text}\n"
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    def write_issue(self, issue_node: IssueNode) -> tuple[Path, bool]:
        filename = issue_note_filename(issue_node.issue_id)
        path = self.vault_root / "issues" / "taxonomy" / filename

        frontmatter = self._model_dump(issue_node)
        body = f"# Issue\n\n{issue_node.normalized_form}\n"
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    def write_relation(self, relation_node: RelationNode) -> tuple[Path, bool]:
        raw_name = relation_node.relation_id
        safe_name = _RELATION_FILE_RE.sub("_", raw_name).strip("_")
        path = self.vault_root / "relations" / f"{safe_name}.md"

        frontmatter = self._model_dump(relation_node)
        body = (
            f"# Relation\n\n"
            f"`{relation_node.source_holding_id}` {relation_node.relation_type.value} `{relation_node.target_holding_id}`\n"
        )
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    @staticmethod
    def _source_bucket(source_node: SourceNode | SecondaryNode) -> str:
        if getattr(source_node, "type", "") == "secondary":
            return "secondary"
        source_type = source_node.source_type if isinstance(source_node, SourceNode) else SourceType.secondary
        if source_type == SourceType.constitution:
            return "constitution"
        if source_type == SourceType.statute:
            return "statutes"
        if source_type == SourceType.reg:
            return "regs"
        if source_type == SourceType.secondary:
            return "secondary"
        return "secondary"

    def write_source(self, source_node: SourceNode | SecondaryNode) -> tuple[Path, bool]:
        safe_name = _RELATION_FILE_RE.sub("_", source_node.source_id).strip("_")
        path = self.vault_root / "sources" / self._source_bucket(source_node) / f"{safe_name}.md"

        frontmatter = self._model_dump(source_node)
        title = source_node.title if getattr(source_node, "title", None) else source_node.source_id
        body = f"# Source\n\n{title}\n"
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    def write_issue_index(self, issues: list[IssueNode]) -> bool:
        payload = [self._model_dump(issue) for issue in sorted(issues, key=lambda item: item.issue_id)]
        content = json.dumps(payload, indent=2, ensure_ascii=False)
        return self._write_if_changed(self.issue_index_path, content)

    @staticmethod
    def _severity_rank(value: str) -> int:
        ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return ranks.get((value or "").lower(), 9)

    @classmethod
    def _sorted_unresolved(cls, unresolved_items: list[dict]) -> list[dict]:
        return sorted(
            unresolved_items,
            key=lambda item: (
                cls._severity_rank(str(item.get("severity", ""))),
                str(item.get("category", "")),
                str(item.get("reason", "")),
                str(item.get("review_id", "")),
                str(item.get("normalized_citation", item.get("normalized_form", ""))),
            ),
        )

    @staticmethod
    def _severity_counts(unresolved_items: list[dict]) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for item in unresolved_items:
            key = str(item.get("severity", "medium")).lower()
            counts[key if key in counts else "medium"] += 1
        counts["total"] = len(unresolved_items)
        return counts

    def write_unresolved_queue(self, unresolved_items: list[dict]) -> bool:
        sorted_items = self._sorted_unresolved(unresolved_items)
        counts = self._severity_counts(sorted_items)

        lines = ["# Unresolved Queue", ""]
        lines.append("## Summary")
        lines.append(f"- total: {counts['total']}")
        lines.append(f"- critical: {counts['critical']}")
        lines.append(f"- high: {counts['high']}")
        lines.append(f"- medium: {counts['medium']}")
        lines.append(f"- low: {counts['low']}")
        lines.append("")
        lines.append("## Items")
        if not sorted_items:
            lines.append("- none")
        else:
            for item in sorted_items:
                review_id = item.get("review_id", "review.unknown")
                severity = str(item.get("severity", "medium")).upper()
                category = str(item.get("category", "uncategorized"))
                reason = str(item.get("reason", "unknown"))
                action = str(item.get("review_action", "manual_review"))
                status = str(item.get("status", "open")).lower()
                compact = json.dumps(item, ensure_ascii=False, sort_keys=True)
                lines.append(f"- [ ] ({severity}) `{review_id}` {category}: {reason}")
                lines.append(f"  status: {status}")
                lines.append(f"  action: {action}")
                lines.append(f"  data: {compact}")

        content = "\n".join(lines) + "\n"
        return self._write_if_changed(self.unresolved_queue_path, content)

    def write_review_checklist(self, unresolved_items: list[dict], explainability_payload: dict | None = None) -> bool:
        sorted_items = self._sorted_unresolved(unresolved_items)
        counts = self._severity_counts(sorted_items)

        lines = ["# Review Checklist", ""]
        lines.append("Use this checklist when triaging unresolved ontology items and validating PF changes.")
        lines.append("")
        lines.append("## Required Checks")
        lines.append("- [ ] Validate citation anchors for all high/critical unresolved items.")
        lines.append("- [ ] Confirm issue minimality and doctrinal fit for issue-unresolved entries.")
        lines.append("- [ ] Validate relation direction/type against evidence span for relation-unresolved entries.")
        lines.append("- [ ] Verify source-link authority assignments for holdings with low PF.")
        lines.append("- [ ] Confirm PF explainability deltas align with expected relation/source effects.")
        lines.append("")
        lines.append("## Queue Snapshot")
        lines.append(f"- total: {counts['total']}")
        lines.append(f"- critical: {counts['critical']}")
        lines.append(f"- high: {counts['high']}")
        lines.append(f"- medium: {counts['medium']}")
        lines.append(f"- low: {counts['low']}")

        holding_count = len((explainability_payload or {}).get("holdings", {}) or {})
        issue_count = len((explainability_payload or {}).get("issues", {}) or {})
        lines.append("")
        lines.append("## Explainability Snapshot")
        lines.append(f"- holding explanations: {holding_count}")
        lines.append(f"- issue explanations: {issue_count}")

        lines.append("")
        lines.append("## Open Items")
        if not sorted_items:
            lines.append("- none")
        else:
            for item in sorted_items:
                review_id = item.get("review_id", "review.unknown")
                severity = str(item.get("severity", "medium")).upper()
                category = str(item.get("category", "uncategorized"))
                reason = str(item.get("reason", "unknown"))
                lines.append(f"- [ ] ({severity}) `{review_id}` {category}: {reason}")

        content = "\n".join(lines) + "\n"
        return self._write_if_changed(self.review_checklist_path, content)

    def write_params(self, params: dict) -> bool:
        content = dump_yaml(params) + "\n"
        return self._write_if_changed(self.params_path, content)

    def write_metrics(self, metrics_payload: dict) -> bool:
        content = dump_yaml(metrics_payload) + "\n"
        return self._write_if_changed(self.metrics_path, content)

    def write_interpretation_events(self, case_node: CaseNode, events: list[dict]) -> tuple[Path, bool]:
        safe_name = _RELATION_FILE_RE.sub("_", case_node.case_id).strip("_")
        path = self.vault_root / "events" / "interpretations" / f"{safe_name}.md"
        frontmatter = {
            "type": "interpretation_event_log",
            "case_id": case_node.case_id,
            "event_count": len(events),
        }
        body_lines = [f"# Interpretation Events for {case_node.case_id}", ""]
        if events:
            for event in events:
                body_lines.append(f"- {json.dumps(event, ensure_ascii=False, sort_keys=True)}")
        else:
            body_lines.append("- none")
        body = "\n".join(body_lines) + "\n"
        content = markdown_with_frontmatter(frontmatter, body)
        changed = self._write_if_changed(path, content)
        return path, changed

    def write_all(
        self,
        *,
        case_node: CaseNode,
        holding_nodes: list[HoldingNode],
        issue_nodes: list[IssueNode],
        relation_nodes: list[RelationNode],
        source_nodes: list[SourceNode | SecondaryNode] | None = None,
        unresolved_items: list[dict],
        params: dict | None = None,
        metrics_payload: dict | None = None,
        explainability_payload: dict | None = None,
        interpretation_events: list[dict] | None = None,
    ) -> dict[str, Any]:
        written_paths: list[str] = []
        changed_count = 0

        case_path, case_changed = self.write_case(case_node)
        written_paths.append(str(case_path))
        changed_count += 1 if case_changed else 0

        for idx, holding in enumerate(holding_nodes, start=1):
            path, changed = self.write_holding(holding, index=idx)
            written_paths.append(str(path))
            changed_count += 1 if changed else 0

        for issue in issue_nodes:
            path, changed = self.write_issue(issue)
            written_paths.append(str(path))
            changed_count += 1 if changed else 0

        for relation in relation_nodes:
            path, changed = self.write_relation(relation)
            written_paths.append(str(path))
            changed_count += 1 if changed else 0

        for source in sorted(source_nodes or [], key=lambda item: item.source_id):
            path, changed = self.write_source(source)
            written_paths.append(str(path))
            changed_count += 1 if changed else 0

        if params is not None and self.write_params(params):
            changed_count += 1
        if metrics_payload is not None and self.write_metrics(metrics_payload):
            changed_count += 1

        if self.write_issue_index(issue_nodes):
            changed_count += 1
        if self.write_unresolved_queue(unresolved_items):
            changed_count += 1
        if self.write_review_checklist(unresolved_items, explainability_payload):
            changed_count += 1
        event_path, event_changed = self.write_interpretation_events(case_node, interpretation_events or [])
        written_paths.append(str(event_path))
        changed_count += 1 if event_changed else 0

        return {
            "changed_count": changed_count,
            "written_paths": written_paths,
            "case_path": str(case_path),
            "issue_count": len(issue_nodes),
            "holding_count": len(holding_nodes),
            "relation_count": len(relation_nodes),
            "source_count": len(source_nodes or []),
            "unresolved_count": len(unresolved_items),
        }
