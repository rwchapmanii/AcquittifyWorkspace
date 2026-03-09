"""Precedential ontology compilation primitives."""

from .config import OntologyConfig
from .ids import (
    build_case_id,
    build_holding_id,
    build_issue_id,
    case_note_filename,
    holding_note_filename,
    issue_note_filename,
)
from .citation_extract import CitationMention, extract_citation_mentions
from .citation_resolver import CitationResolver, ResolvedCitation
from .citation_roles import CitationRoleAssignment, classify_citation_roles
from .canonicalize import CanonicalizationDecision, CanonicalizationOutcome, canonicalize_issues, load_issue_index
from .extractor import (
    ExtractionEnvelope,
    ExtractionValidationError,
    extract_structures,
    parse_extraction_json,
)
from .metrics import DEFAULT_PARAMS, MetricsBundle, apply_metrics, load_params
from .relations import RelationBuildResult, build_relation_nodes
from .vault_writer import VaultWriter
from .schemas import SecondaryNode, SourceLink, SourceNode, SourceType

__all__ = [
    "OntologyConfig",
    "CitationMention",
    "CitationResolver",
    "ResolvedCitation",
    "CitationRoleAssignment",
    "CanonicalizationDecision",
    "CanonicalizationOutcome",
    "ExtractionEnvelope",
    "ExtractionValidationError",
    "DEFAULT_PARAMS",
    "MetricsBundle",
    "RelationBuildResult",
    "SourceNode",
    "SecondaryNode",
    "SourceLink",
    "SourceType",
    "VaultWriter",
    "build_case_id",
    "build_holding_id",
    "build_issue_id",
    "case_note_filename",
    "holding_note_filename",
    "issue_note_filename",
    "extract_citation_mentions",
    "classify_citation_roles",
    "canonicalize_issues",
    "load_issue_index",
    "extract_structures",
    "parse_extraction_json",
    "load_params",
    "apply_metrics",
    "build_relation_nodes",
]
