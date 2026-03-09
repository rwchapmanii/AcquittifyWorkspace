from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class NormativeStrength(str, Enum):
    binding_core = "binding_core"
    binding_narrow = "binding_narrow"
    persuasive = "persuasive"
    dicta = "dicta"


class CitationType(str, Enum):
    controlling = "controlling"
    persuasive = "persuasive"
    background = "background"


class RelationType(str, Enum):
    applies = "applies"
    clarifies = "clarifies"
    extends = "extends"
    distinguishes = "distinguishes"
    limits = "limits"
    overrules = "overrules"
    questions = "questions"


class CitationRole(str, Enum):
    controlling = "controlling"
    persuasive = "persuasive"
    background = "background"


class PredicateValue(BaseModel):
    predicate: str
    value: Any


class FactDimension(BaseModel):
    dimension: str
    value: Any


class BurdenInfo(BaseModel):
    party: str | None = None
    level: str | None = None


class AuthorityInfo(BaseModel):
    base_weight: float = 1.0
    modifiers: dict[str, float] = Field(default_factory=dict)
    final_weight: float = 1.0


class DoctrinalRoot(BaseModel):
    root_case_id: str | None = None
    root_holding_id: str | None = None


class SourceType(str, Enum):
    constitution = "constitution"
    statute = "statute"
    reg = "reg"
    secondary = "secondary"
    other = "other"


class SourceLink(BaseModel):
    source_id: str
    weight: float | None = None
    role: str | None = None


class CitationAnchor(BaseModel):
    raw_text: str
    normalized_text: str
    resolved_case_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    start_char: int | None = None
    end_char: int | None = None
    role: CitationRole | None = None


class AuthorityAnchor(BaseModel):
    raw_text: str
    normalized_text: str
    source_id: str
    source_type: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    start_char: int | None = None
    end_char: int | None = None
    extractor: str | None = None


class CaseNode(BaseModel):
    type: Literal["case"] = "case"
    case_id: str
    title: str
    court: str
    court_level: str
    jurisdiction: str
    date_decided: str
    publication_status: str | None = None
    opinion_type: str | None = None
    originating_circuit: str | None = None
    originating_circuit_label: str | None = None
    judges: dict[str, Any] = Field(default_factory=dict)
    citations_in_text: list[str] = Field(default_factory=list)
    case_summary: str = ""
    essential_holding: str = ""
    case_taxonomies: list[dict[str, str]] = Field(default_factory=list)
    citation_anchors: list[CitationAnchor] = Field(default_factory=list)
    authority_anchors: list[AuthorityAnchor] = Field(default_factory=list)
    interpretive_edges: list[dict[str, Any]] = Field(default_factory=list)
    sources: dict[str, Any] = Field(default_factory=dict)


class HoldingNode(BaseModel):
    type: Literal["holding"] = "holding"
    holding_id: str
    case_id: str
    normative_source: list[str] = Field(default_factory=list)
    holding_text: str
    if_condition: list[PredicateValue] = Field(default_factory=list)
    then_consequence: list[PredicateValue] = Field(default_factory=list)
    normative_strength: NormativeStrength = NormativeStrength.binding_core
    standard_of_review: str | None = None
    burden: BurdenInfo | None = None
    fact_vector: list[FactDimension] = Field(default_factory=list)
    authority: AuthorityInfo = Field(default_factory=AuthorityInfo)
    anchors: dict[str, DoctrinalRoot] | None = None
    source_links: list[SourceLink] = Field(default_factory=list)
    citations_supporting: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class IssueNode(BaseModel):
    type: Literal["issue"] = "issue"
    issue_id: str
    normalized_form: str
    taxonomy: dict[str, str] = Field(default_factory=dict)
    anchors: dict[str, Any] = Field(default_factory=dict)
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    linked_holdings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class RelationEvidence(BaseModel):
    start_char: int | None = None
    end_char: int | None = None
    quote: str | None = None


class RelationNode(BaseModel):
    type: Literal["relation"] = "relation"
    relation_id: str
    source_holding_id: str
    target_holding_id: str
    relation_type: RelationType
    citation_type: CitationType = CitationType.controlling
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    weight_modifier: float = 1.0
    evidence_span: RelationEvidence = Field(default_factory=RelationEvidence)


class SourceNode(BaseModel):
    type: Literal["source"] = "source"
    source_id: str
    source_type: SourceType
    title: str | None = None
    authority_weight: float | None = None
    topic_tags: list[str] = Field(default_factory=list)


class SecondaryNode(BaseModel):
    type: Literal["secondary"] = "secondary"
    source_id: str
    title: str
    authority_weight: float = 0.3
    topic_tags: list[str] = Field(default_factory=list)
