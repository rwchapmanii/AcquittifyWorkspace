"""Pydantic extraction models and graph-projection helpers for Acquittify.

Target stack:
- Python 3.11+
- Pydantic v2
- Neo4j 5.x

The nested models validate extracted YAML. The graph projection helpers flatten
selected fields into node and relationship payloads that Neo4j can store
directly. Nested structures and rich provenance should still be archived in
object/document storage.

Important schema repairs applied here:
- Case -> Opinion is modeled with HAS_OPINION
- Case -> Topic is modeled with HAS_TOPIC
- Case -> Motion is modeled with HAS_MOTION

Derived similarity edges such as SAME_ISSUE, SAME_PROVISION, and
SAME_FACT_CLUSTER are not emitted by a single-case extraction by default.
They should be created in a batch analytics pass after multiple cases are
loaded, because they require cross-case comparisons.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from hashlib import sha1
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != [] and value != {}
    }


def _stable_hash(*parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def _make_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{_stable_hash(prefix, *parts)}"


def _json_string(value: Any) -> str | None:
    if value in (None, [], {}):
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return str(self.value)


class CourtLevel(StrEnum):
    trial = "trial"
    appellate = "appellate"
    supreme = "supreme"


class JurisdictionSystem(StrEnum):
    federal = "federal"
    state = "state"


class PublicationStatus(StrEnum):
    published_precedential = "published_precedential"
    unpublished = "unpublished"
    memorandum = "memorandum"
    order = "order"
    per_curiam = "per_curiam"


class OpinionType(StrEnum):
    majority = "majority"
    plurality = "plurality"
    concurrence = "concurrence"
    concurrence_in_judgment = "concurrence_in_judgment"
    dissent = "dissent"
    per_curiam = "per_curiam"
    memorandum = "memorandum"
    order = "order"
    other = "other"


class JudgeRole(StrEnum):
    author = "author"
    join = "join"
    concur = "concur"
    dissent = "dissent"
    panel_member = "panel_member"


class ProvisionType(StrEnum):
    statute = "statute"
    regulation = "regulation"
    constitution = "constitution"
    rule = "rule"
    common_law = "common_law"
    treaty = "treaty"
    other = "other"


class RuleSourceType(StrEnum):
    statute = "statute"
    precedent = "precedent"
    regulation = "regulation"
    constitution = "constitution"
    common_law = "common_law"


class AnalogyRelation(StrEnum):
    similar = "similar"
    distinguishable = "distinguishable"
    stronger = "stronger"
    weaker = "weaker"


class AuthorityTreatment(StrEnum):
    followed = "followed"
    applied = "applied"
    distinguished = "distinguished"
    limited = "limited"
    criticized = "criticized"
    overruled = "overruled"
    questioned = "questioned"
    cited = "cited"


class Direction(StrEnum):
    liberal = "liberal"
    conservative = "conservative"
    mixed = "mixed"
    unknown = "unknown"


class PrecedentialEffectType(StrEnum):
    created_rule = "created_rule"
    clarified_rule = "clarified_rule"
    limited_prior_case = "limited_prior_case"
    overruled_prior_case = "overruled_prior_case"


class AcquittifyBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("*", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    def clean_dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class GraphNodeUpsert(AcquittifyBaseModel):
    label: str
    id: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_id_property(self) -> "GraphNodeUpsert":
        self.properties["id"] = self.id
        return self


class GraphRelationshipUpsert(AcquittifyBaseModel):
    rel_type: str
    edge_id: str
    start_label: str
    start_id: str
    end_label: str
    end_id: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_edge_id_property(self) -> "GraphRelationshipUpsert":
        self.properties["edge_id"] = self.edge_id
        return self


class GraphDocument(AcquittifyBaseModel):
    nodes: list[GraphNodeUpsert] = Field(default_factory=list)
    relationships: list[GraphRelationshipUpsert] = Field(default_factory=list)

    def deduplicate(self) -> "GraphDocument":
        node_map: dict[tuple[str, str], GraphNodeUpsert] = {}
        for node in self.nodes:
            key = (node.label, node.id)
            if key in node_map:
                node_map[key].properties.update(node.properties)
            else:
                node_map[key] = node

        rel_map: dict[tuple[str, str], GraphRelationshipUpsert] = {}
        for rel in self.relationships:
            key = (rel.rel_type, rel.edge_id)
            if key in rel_map:
                rel_map[key].properties.update(rel.properties)
            else:
                rel_map[key] = rel

        self.nodes = list(node_map.values())
        self.relationships = list(rel_map.values())
        return self


class ExternalIds(AcquittifyBaseModel):
    courtlistener_id: str | None = None
    cap_id: str | None = None
    scdb_id: str | None = None
    docket_id: str | None = None
    reporter_citation: str | None = None
    neutral_citation: str | None = None


class Caption(AcquittifyBaseModel):
    short: str
    full: str | None = None

    @model_validator(mode="after")
    def _fill_full(self) -> "Caption":
        if not self.full:
            self.full = self.short
        return self


class JurisdictionRef(AcquittifyBaseModel):
    system: JurisdictionSystem
    state: str | None = None
    circuit: str | None = None
    jurisdiction_id: str | None = None

    @model_validator(mode="after")
    def _fill_jurisdiction_id(self) -> "JurisdictionRef":
        if not self.jurisdiction_id:
            self.jurisdiction_id = _make_id(
                "jurisdiction",
                self.system,
                self.state,
                self.circuit,
            )
        return self


class CourtRef(AcquittifyBaseModel):
    court_id: str | None = None
    court_name: str
    court_level: CourtLevel
    jurisdiction: JurisdictionRef

    @model_validator(mode="after")
    def _fill_court_id(self) -> "CourtRef":
        if not self.court_id:
            self.court_id = _make_id(
                "court",
                self.court_name,
                self.court_level,
                self.jurisdiction.jurisdiction_id,
            )
        return self


class CaseDates(AcquittifyBaseModel):
    argued: date | None = None
    decided: date
    published: date | None = None


class Procedure(AcquittifyBaseModel):
    procedural_posture: str
    standard_of_review: str | None = None
    posture_tags: list[str] = Field(default_factory=list)
    appealed_from_case_id: str | None = None


class Publication(AcquittifyBaseModel):
    precedential_status: PublicationStatus = PublicationStatus.published_precedential
    opinion_types: list[OpinionType] = Field(default_factory=list)


class JudgePanelMember(AcquittifyBaseModel):
    judge_id: str | None = None
    name: str | None = None
    role: JudgeRole = JudgeRole.panel_member

    @model_validator(mode="after")
    def _fill_judge_id(self) -> "JudgePanelMember":
        if not self.judge_id and self.name:
            self.judge_id = _make_id("judge", self.name)
        return self


class OpinionRecord(AcquittifyBaseModel):
    opinion_id: str | None = None
    case_id: str | None = None
    opinion_type: OpinionType = OpinionType.majority
    author_judge_id: str | None = None
    author_name: str | None = None
    text: str
    joined_by_judge_ids: list[str] = Field(default_factory=list)
    concurring_judge_ids: list[str] = Field(default_factory=list)
    dissenting_judge_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_ids(self) -> "OpinionRecord":
        if not self.author_judge_id and self.author_name:
            self.author_judge_id = _make_id("judge", self.author_name)
        return self


class PartyRecord(AcquittifyBaseModel):
    party_id: str | None = None
    name: str
    normalized_name: str | None = None
    role: str | None = None
    party_type: str

    @model_validator(mode="after")
    def _fill_party_id(self) -> "PartyRecord":
        if not self.normalized_name:
            self.normalized_name = self.name.lower()
        if not self.party_id:
            self.party_id = _make_id("party", self.normalized_name, self.party_type)
        return self


class IssueTaxonomy(AcquittifyBaseModel):
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None

    def taxonomy_key(self) -> str:
        parts = [part for part in [self.level_1, self.level_2, self.level_3] if part]
        return " > ".join(parts)


class LegalIssueRecord(AcquittifyBaseModel):
    issue_id: str | None = None
    issue_text: str
    taxonomy: IssueTaxonomy = Field(default_factory=IssueTaxonomy)
    target_elements: list[str] = Field(default_factory=list)
    taxonomy_key: str | None = None

    @model_validator(mode="after")
    def _fill_fields(self) -> "LegalIssueRecord":
        if not self.taxonomy_key:
            self.taxonomy_key = self.taxonomy.taxonomy_key() or "unclassified"
        if not self.issue_id:
            self.issue_id = _make_id("issue", self.taxonomy_key, self.issue_text)
        return self


class ClaimsAndIssues(AcquittifyBaseModel):
    causes_of_action: list[str] = Field(default_factory=list)
    legal_issues: list[LegalIssueRecord] = Field(default_factory=list)


class LegalProvisionRecord(AcquittifyBaseModel):
    provision_id: str | None = None
    provision_type: ProvisionType
    citation: str
    section: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def _fill_provision_id(self) -> "LegalProvisionRecord":
        if not self.provision_id:
            self.provision_id = _make_id("provision", self.provision_type, self.citation, self.section)
        return self


class LawRecord(AcquittifyBaseModel):
    statutes: list[LegalProvisionRecord] = Field(default_factory=list)
    regulations: list[LegalProvisionRecord] = Field(default_factory=list)
    constitutional_provisions: list[LegalProvisionRecord] = Field(default_factory=list)
    prior_cases_cited: list[str] = Field(default_factory=list)

    def all_provisions(self) -> list[LegalProvisionRecord]:
        return self.statutes + self.regulations + self.constitutional_provisions


class FactEvent(AcquittifyBaseModel):
    event_id: str | None = None
    actor: str | None = None
    action: str
    object: str | None = None
    time: str | None = None
    location: str | None = None
    mental_state: str | None = None

    @model_validator(mode="after")
    def _fill_event_id(self) -> "FactEvent":
        if not self.event_id:
            self.event_id = _make_id(
                "event",
                self.actor,
                self.action,
                self.object,
                self.time,
                self.location,
            )
        return self


class FactVector(AcquittifyBaseModel):
    conduct: list[str] = Field(default_factory=list)
    injury: list[str] = Field(default_factory=list)
    intent: list[str] = Field(default_factory=list)
    causation: list[str] = Field(default_factory=list)
    procedure: list[str] = Field(default_factory=list)


class FactsRecord(AcquittifyBaseModel):
    fact_id: str | None = None
    fact_summary: str | None = None
    fact_events: list[FactEvent] = Field(default_factory=list)
    fact_vector: FactVector = Field(default_factory=FactVector)
    fact_cluster: str | None = None

    @model_validator(mode="after")
    def _fill_fact_id(self) -> "FactsRecord":
        if not self.fact_id:
            self.fact_id = _make_id(
                "facts",
                self.fact_summary,
                _json_string([event.clean_dump() for event in self.fact_events]),
            )
        return self


class RuleStatementRecord(AcquittifyBaseModel):
    rule_id: str | None = None
    rule_text: str
    source_type: RuleSourceType
    test_elements: list[str] = Field(default_factory=list)
    binding_scope: str | None = None

    @model_validator(mode="after")
    def _fill_rule_id(self) -> "RuleStatementRecord":
        if not self.rule_id:
            self.rule_id = _make_id("rule", self.source_type, self.rule_text)
        return self


class AnalogyRecord(AcquittifyBaseModel):
    cited_case_id: str
    relation: AnalogyRelation
    explanation: str | None = None


class AuthorityRecord(AcquittifyBaseModel):
    cited_case_id: str
    cited_opinion_id: str | None = None
    source_opinion_id: str | None = None
    source_holding_id: str | None = None
    cited_holding_id: str | None = None
    treatment: AuthorityTreatment = AuthorityTreatment.cited
    quoted_passages: list[str] = Field(default_factory=list)
    citation_context: str | None = None
    doctrinal_relevance_score: float | None = None
    citation_count: int | None = None
    context_strength: float | None = None
    depth: int | None = None


class ReasoningRecord(AcquittifyBaseModel):
    rule_statements: list[RuleStatementRecord] = Field(default_factory=list)
    analogies: list[AnalogyRecord] = Field(default_factory=list)
    policy_considerations: list[str] = Field(default_factory=list)
    interpretive_methods: list[str] = Field(default_factory=list)
    authorities: list[AuthorityRecord] = Field(default_factory=list)


class BindingScope(AcquittifyBaseModel):
    jurisdiction: str | None = None
    court_level: str | None = None
    subject_scope: list[str] = Field(default_factory=list)


class HoldingRecord(AcquittifyBaseModel):
    holding_id: str | None = None
    issue_id: str | None = None
    holding_text: str
    rule_disposition: str | None = None
    binding_scope: BindingScope = Field(default_factory=BindingScope)
    precedential_weight: float | None = None
    doctrine_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_holding_id(self) -> "HoldingRecord":
        if not self.holding_id:
            self.holding_id = _make_id("holding", self.issue_id, self.holding_text)
        return self


class DictumRecord(AcquittifyBaseModel):
    dictum_id: str | None = None
    dictum_text: str

    @model_validator(mode="after")
    def _fill_dictum_id(self) -> "DictumRecord":
        if not self.dictum_id:
            self.dictum_id = _make_id("dictum", self.dictum_text)
        return self


class DoctrineRecord(AcquittifyBaseModel):
    doctrine_id: str | None = None
    doctrine_name: str
    description: str | None = None

    @model_validator(mode="after")
    def _fill_doctrine_id(self) -> "DoctrineRecord":
        if not self.doctrine_id:
            self.doctrine_id = _make_id("doctrine", self.doctrine_name)
        return self


class TopicRecord(AcquittifyBaseModel):
    topic_id: str | None = None
    topic_label: str

    @model_validator(mode="after")
    def _fill_topic_id(self) -> "TopicRecord":
        if not self.topic_id:
            self.topic_id = _make_id("topic", self.topic_label)
        return self


class MotionRecord(AcquittifyBaseModel):
    motion_id: str | None = None
    motion_type: str
    disposition: str | None = None

    @model_validator(mode="after")
    def _fill_motion_id(self) -> "MotionRecord":
        if not self.motion_id:
            self.motion_id = _make_id("motion", self.motion_type, self.disposition)
        return self


class RemedyRecord(AcquittifyBaseModel):
    remedy_id: str | None = None
    remedy_type: str
    granted: bool | None = None

    @model_validator(mode="after")
    def _fill_remedy_id(self) -> "RemedyRecord":
        if not self.remedy_id:
            self.remedy_id = _make_id("remedy", self.remedy_type)
        return self


class Relief(AcquittifyBaseModel):
    granted: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)


class PrecedentEffect(AcquittifyBaseModel):
    created_rule: bool = False
    clarified_rule: bool = False
    limited_prior_case: list[str] = Field(default_factory=list)
    overruled_prior_case: list[str] = Field(default_factory=list)


class OutcomeRecord(AcquittifyBaseModel):
    outcome_id: str | None = None
    disposition: str
    winner: str | None = None
    decision_direction: Direction = Direction.unknown
    relief: Relief = Field(default_factory=Relief)
    precedent_effect: PrecedentEffect = Field(default_factory=PrecedentEffect)

    @model_validator(mode="after")
    def _fill_outcome_id(self) -> "OutcomeRecord":
        if not self.outcome_id:
            self.outcome_id = _make_id(
                "outcome",
                self.disposition,
                self.winner,
                self.decision_direction,
            )
        return self


class Embeddings(AcquittifyBaseModel):
    text_embedding_id: str | None = None
    facts_embedding_id: str | None = None
    holdings_embedding_id: str | None = None
    graph_embedding_id: str | None = None
    text_embedding: list[float] | None = None
    facts_embedding: list[float] | None = None
    holdings_embedding: list[float] | None = None
    graph_embedding: list[float] | None = None


class CentralityMetrics(AcquittifyBaseModel):
    pagerank: float | None = None
    indegree: int | None = None
    betweenness: float | None = None


class ConfidenceScores(AcquittifyBaseModel):
    extraction_confidence: float | None = None
    holding_confidence: float | None = None
    edge_confidence: float | None = None


class DerivedMetrics(AcquittifyBaseModel):
    authority_score: float | None = None
    temporal_decay_score: float | None = None
    subject_similarity_cluster: str | None = None
    centrality: CentralityMetrics = Field(default_factory=CentralityMetrics)
    precedential_reliance_index: float | None = None
    distinguishability_score: float | None = None
    confidence_scores: ConfidenceScores = Field(default_factory=ConfidenceScores)


class Provenance(AcquittifyBaseModel):
    source_system: str
    source_url: str | None = None
    parser_version: str | None = None
    extraction_timestamp: datetime
    reviewed_by_human: bool = False
    review_notes: str | None = None


class TextBlocks(AcquittifyBaseModel):
    syllabus_text: str | None = None
    procedural_history_text: str | None = None
    facts_text: str | None = None
    issues_text: str | None = None
    reasoning_text: str | None = None
    holding_text: str | None = None
    disposition_text: str | None = None
    full_text: str | None = None


class CaseExtraction(AcquittifyBaseModel):
    schema_version: str = "1.0"
    case_id: str
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    caption: Caption
    court: CourtRef
    dates: CaseDates
    procedure: Procedure
    publication: Publication = Field(default_factory=Publication)
    opinions: list[OpinionRecord] = Field(default_factory=list)
    panel: list[JudgePanelMember] = Field(default_factory=list)
    parties: list[PartyRecord] = Field(default_factory=list)
    claims_and_issues: ClaimsAndIssues = Field(default_factory=ClaimsAndIssues)
    law: LawRecord = Field(default_factory=LawRecord)
    facts: FactsRecord = Field(default_factory=FactsRecord)
    reasoning: ReasoningRecord = Field(default_factory=ReasoningRecord)
    holdings: list[HoldingRecord] = Field(default_factory=list)
    dicta: list[DictumRecord] = Field(default_factory=list)
    doctrines: list[DoctrineRecord] = Field(default_factory=list)
    topics: list[TopicRecord] = Field(default_factory=list)
    motions: list[MotionRecord] = Field(default_factory=list)
    remedies: list[RemedyRecord] = Field(default_factory=list)
    outcome: OutcomeRecord
    embeddings: Embeddings = Field(default_factory=Embeddings)
    derived_metrics: DerivedMetrics = Field(default_factory=DerivedMetrics)
    provenance: Provenance
    text_blocks: TextBlocks = Field(default_factory=TextBlocks)

    TREATMENT_TO_REL: ClassVar[dict[AuthorityTreatment, str | None]] = {
        AuthorityTreatment.followed: "FOLLOWS",
        AuthorityTreatment.applied: "FOLLOWS",
        AuthorityTreatment.distinguished: "DISTINGUISHES",
        AuthorityTreatment.limited: "LIMITS",
        AuthorityTreatment.criticized: "QUESTIONS",
        AuthorityTreatment.overruled: "OVERRULES",
        AuthorityTreatment.questioned: "QUESTIONS",
        AuthorityTreatment.cited: None,
    }

    @model_validator(mode="after")
    def _fill_internal_ids(self) -> "CaseExtraction":
        if not self.opinions and self.text_blocks.full_text:
            default_author = next(
                (judge.judge_id for judge in self.panel if judge.role == JudgeRole.author and judge.judge_id),
                None,
            )
            self.opinions.append(
                OpinionRecord(
                    opinion_id=f"{self.case_id}:opinion:1",
                    case_id=self.case_id,
                    opinion_type=self.publication.opinion_types[0]
                    if self.publication.opinion_types
                    else OpinionType.majority,
                    author_judge_id=default_author,
                    text=self.text_blocks.full_text,
                )
            )

        for index, opinion in enumerate(self.opinions, start=1):
            if not opinion.case_id:
                opinion.case_id = self.case_id
            if not opinion.opinion_id:
                opinion.opinion_id = f"{self.case_id}:opinion:{index}"

        if not self.publication.opinion_types and self.opinions:
            self.publication.opinion_types = [opinion.opinion_type for opinion in self.opinions]

        issue_ids = [issue.issue_id for issue in self.claims_and_issues.legal_issues]
        default_issue_id = issue_ids[0] if issue_ids else None
        for holding in self.holdings:
            if not holding.issue_id and default_issue_id:
                holding.issue_id = default_issue_id

        if self.outcome.outcome_id and not self.outcome.outcome_id.startswith("outcome:"):
            self.outcome.outcome_id = _make_id("outcome", self.case_id, self.outcome.outcome_id)

        return self

    @property
    def jurisdiction_id(self) -> str:
        return self.court.jurisdiction.jurisdiction_id or _make_id(
            "jurisdiction",
            self.court.jurisdiction.system,
            self.court.jurisdiction.state,
            self.court.jurisdiction.circuit,
        )

    def as_yaml_payload(self) -> dict[str, Any]:
        return self.clean_dump()

    def _case_node(self) -> GraphNodeUpsert:
        props = _compact_dict(
            {
                "case_id": self.case_id,
                "case_name": self.caption.short,
                "caption_short": self.caption.short,
                "caption_full": self.caption.full,
                "court_id": self.court.court_id,
                "court_name": self.court.court_name,
                "court_level": self.court.court_level,
                "jurisdiction_id": self.jurisdiction_id,
                "jurisdiction_system": self.court.jurisdiction.system,
                "jurisdiction_state": self.court.jurisdiction.state,
                "jurisdiction_circuit": self.court.jurisdiction.circuit,
                "argued_date": self.dates.argued,
                "decision_date": self.dates.decided,
                "published_date": self.dates.published,
                "procedural_posture": self.procedure.procedural_posture,
                "standard_of_review": self.procedure.standard_of_review,
                "posture_tags": self.procedure.posture_tags,
                "appealed_from_case_id": self.procedure.appealed_from_case_id,
                "precedential_status": self.publication.precedential_status,
                "publication_status": self.publication.precedential_status,
                "opinion_types": [str(op) for op in self.publication.opinion_types],
                "disposition": self.outcome.disposition,
                "winner": self.outcome.winner,
                "direction": self.outcome.decision_direction,
                "fact_summary": self.facts.fact_summary,
                "facts_text": self.text_blocks.facts_text,
                "issues_text": self.text_blocks.issues_text,
                "reasoning_text": self.text_blocks.reasoning_text,
                "holding_text": self.text_blocks.holding_text,
                "full_text": self.text_blocks.full_text,
                "subject_similarity_cluster": self.derived_metrics.subject_similarity_cluster,
                "fact_cluster": self.facts.fact_cluster,
                "authority_score": self.derived_metrics.authority_score,
                "temporal_decay_score": self.derived_metrics.temporal_decay_score,
                "precedential_reliance_index": self.derived_metrics.precedential_reliance_index,
                "distinguishability_score": self.derived_metrics.distinguishability_score,
                "pagerank": self.derived_metrics.centrality.pagerank,
                "indegree": self.derived_metrics.centrality.indegree,
                "betweenness": self.derived_metrics.centrality.betweenness,
                "extraction_confidence": self.derived_metrics.confidence_scores.extraction_confidence,
                "holding_confidence": self.derived_metrics.confidence_scores.holding_confidence,
                "edge_confidence": self.derived_metrics.confidence_scores.edge_confidence,
                "courtlistener_id": self.external_ids.courtlistener_id,
                "cap_id": self.external_ids.cap_id,
                "scdb_id": self.external_ids.scdb_id,
                "docket_id": self.external_ids.docket_id,
                "reporter_citation": self.external_ids.reporter_citation,
                "neutral_citation": self.external_ids.neutral_citation,
                "text_embedding_id": self.embeddings.text_embedding_id,
                "facts_embedding_id": self.embeddings.facts_embedding_id,
                "holdings_embedding_id": self.embeddings.holdings_embedding_id,
                "graph_embedding_id": self.embeddings.graph_embedding_id,
                "text_embedding": self.embeddings.text_embedding,
                "facts_embedding": self.embeddings.facts_embedding,
            }
        )
        return GraphNodeUpsert(label="Case", id=self.case_id, properties=props)

    def _court_node(self) -> GraphNodeUpsert:
        props = _compact_dict(
            {
                "court_id": self.court.court_id,
                "court_name": self.court.court_name,
                "court_level": self.court.court_level,
                "jurisdiction_id": self.jurisdiction_id,
                "jurisdiction_system": self.court.jurisdiction.system,
                "jurisdiction_state": self.court.jurisdiction.state,
                "jurisdiction_circuit": self.court.jurisdiction.circuit,
            }
        )
        return GraphNodeUpsert(label="Court", id=self.court.court_id, properties=props)

    def _judge_node(self, judge_id: str, name: str | None = None) -> GraphNodeUpsert:
        return GraphNodeUpsert(
            label="Judge",
            id=judge_id,
            properties=_compact_dict({"judge_id": judge_id, "name": name}),
        )

    def _add_node(self, nodes: list[GraphNodeUpsert], node: GraphNodeUpsert) -> None:
        nodes.append(node)

    def _add_rel(
        self,
        relationships: list[GraphRelationshipUpsert],
        rel_type: str,
        start_label: str,
        start_id: str,
        end_label: str,
        end_id: str,
        *,
        canonical_undirected: bool = False,
        **properties: Any,
    ) -> None:
        if canonical_undirected:
            endpoints = sorted([(start_label, start_id), (end_label, end_id)], key=lambda item: (item[0], item[1]))
            start_label, start_id = endpoints[0]
            end_label, end_id = endpoints[1]
        edge_id = _make_id(rel_type.lower(), start_label, start_id, end_label, end_id, _json_string(properties))
        relationships.append(
            GraphRelationshipUpsert(
                rel_type=rel_type,
                edge_id=edge_id,
                start_label=start_label,
                start_id=start_id,
                end_label=end_label,
                end_id=end_id,
                properties=_compact_dict(properties),
            )
        )

    def to_graph_document(self, include_stub_cases: bool = True) -> GraphDocument:
        nodes: list[GraphNodeUpsert] = []
        relationships: list[GraphRelationshipUpsert] = []

        self._add_node(nodes, self._case_node())
        self._add_node(nodes, self._court_node())

        self._add_rel(
            relationships,
            "ISSUED_BY",
            "Case",
            self.case_id,
            "Court",
            self.court.court_id,
        )

        for judge in self.panel:
            if not judge.judge_id:
                continue
            self._add_node(nodes, self._judge_node(judge.judge_id, judge.name))

        for opinion in self.opinions:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Opinion",
                    id=opinion.opinion_id,
                    properties=_compact_dict(
                        {
                            "opinion_id": opinion.opinion_id,
                            "case_id": self.case_id,
                            "opinion_type": opinion.opinion_type,
                            "author_judge_id": opinion.author_judge_id,
                            "text": opinion.text,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "HAS_OPINION",
                "Case",
                self.case_id,
                "Opinion",
                opinion.opinion_id,
            )
            if opinion.author_judge_id:
                self._add_node(nodes, self._judge_node(opinion.author_judge_id, opinion.author_name))
                self._add_rel(
                    relationships,
                    "DECIDED_BY",
                    "Opinion",
                    opinion.opinion_id,
                    "Judge",
                    opinion.author_judge_id,
                    role="author",
                )

        for party in self.parties:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Party",
                    id=party.party_id,
                    properties=_compact_dict(
                        {
                            "party_id": party.party_id,
                            "name": party.name,
                            "normalized_name": party.normalized_name,
                            "role": party.role,
                            "party_type": party.party_type,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "INVOLVES_PARTY",
                "Case",
                self.case_id,
                "Party",
                party.party_id,
                role=party.role,
                party_type=party.party_type,
            )

        for issue in self.claims_and_issues.legal_issues:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="LegalIssue",
                    id=issue.issue_id,
                    properties=_compact_dict(
                        {
                            "issue_id": issue.issue_id,
                            "issue_text": issue.issue_text,
                            "taxonomy_key": issue.taxonomy_key,
                            "taxonomy_level_1": issue.taxonomy.level_1,
                            "taxonomy_level_2": issue.taxonomy.level_2,
                            "taxonomy_level_3": issue.taxonomy.level_3,
                            "target_elements": issue.target_elements,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "HAS_ISSUE",
                "Case",
                self.case_id,
                "LegalIssue",
                issue.issue_id,
            )

        for provision in self.law.all_provisions():
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="LegalProvision",
                    id=provision.provision_id,
                    properties=_compact_dict(
                        {
                            "provision_id": provision.provision_id,
                            "provision_type": provision.provision_type,
                            "citation": provision.citation,
                            "section": provision.section,
                            "title": provision.title,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "INTERPRETS",
                "Case",
                self.case_id,
                "LegalProvision",
                provision.provision_id,
                provision_type=provision.provision_type,
            )

        self._add_node(
            nodes,
            GraphNodeUpsert(
                label="FactPattern",
                id=self.facts.fact_id,
                properties=_compact_dict(
                    {
                        "fact_id": self.facts.fact_id,
                        "case_id": self.case_id,
                        "fact_summary": self.facts.fact_summary,
                        "event_count": len(self.facts.fact_events),
                        "event_sequence_json": _json_string(
                            [event.clean_dump() for event in self.facts.fact_events]
                        ),
                        "conduct": self.facts.fact_vector.conduct,
                        "injury": self.facts.fact_vector.injury,
                        "intent": self.facts.fact_vector.intent,
                        "causation": self.facts.fact_vector.causation,
                        "procedure": self.facts.fact_vector.procedure,
                        "fact_cluster": self.facts.fact_cluster,
                        "facts_embedding_id": self.embeddings.facts_embedding_id,
                        "facts_embedding": self.embeddings.facts_embedding,
                    }
                ),
            ),
        )
        self._add_rel(
            relationships,
            "HAS_FACT_PATTERN",
            "Case",
            self.case_id,
            "FactPattern",
            self.facts.fact_id,
        )

        for rule in self.reasoning.rule_statements:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="RuleStatement",
                    id=rule.rule_id,
                    properties=_compact_dict(
                        {
                            "rule_id": rule.rule_id,
                            "case_id": self.case_id,
                            "rule_text": rule.rule_text,
                            "source_type": rule.source_type,
                            "test_elements": rule.test_elements,
                            "binding_scope": rule.binding_scope,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "APPLIES_RULE",
                "Case",
                self.case_id,
                "RuleStatement",
                rule.rule_id,
                source_type=rule.source_type,
            )

        default_opinion_id = self.opinions[0].opinion_id if self.opinions else None
        for holding in self.holdings:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Holding",
                    id=holding.holding_id,
                    properties=_compact_dict(
                        {
                            "holding_id": holding.holding_id,
                            "case_id": self.case_id,
                            "issue_id": holding.issue_id,
                            "holding_text": holding.holding_text,
                            "rule_disposition": holding.rule_disposition,
                            "binding_jurisdiction": holding.binding_scope.jurisdiction,
                            "binding_court_level": holding.binding_scope.court_level,
                            "subject_scope": holding.binding_scope.subject_scope,
                            "precedential_weight": holding.precedential_weight,
                            "embedding": self.embeddings.holdings_embedding,
                            "holdings_embedding_id": self.embeddings.holdings_embedding_id,
                        }
                    ),
                ),
            )
            if default_opinion_id:
                self._add_rel(
                    relationships,
                    "STATES_HOLDING",
                    "Opinion",
                    default_opinion_id,
                    "Holding",
                    holding.holding_id,
                )
            for doctrine_id in holding.doctrine_ids:
                self._add_rel(
                    relationships,
                    "BELONGS_TO_DOCTRINE",
                    "Holding",
                    holding.holding_id,
                    "Doctrine",
                    doctrine_id,
                )

        for dictum in self.dicta:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Dictum",
                    id=dictum.dictum_id,
                    properties=_compact_dict(
                        {
                            "dictum_id": dictum.dictum_id,
                            "case_id": self.case_id,
                            "dictum_text": dictum.dictum_text,
                        }
                    ),
                ),
            )
            if default_opinion_id:
                self._add_rel(
                    relationships,
                    "STATES_DICTUM",
                    "Opinion",
                    default_opinion_id,
                    "Dictum",
                    dictum.dictum_id,
                )

        for doctrine in self.doctrines:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Doctrine",
                    id=doctrine.doctrine_id,
                    properties=_compact_dict(
                        {
                            "doctrine_id": doctrine.doctrine_id,
                            "doctrine_name": doctrine.doctrine_name,
                            "description": doctrine.description,
                        }
                    ),
                ),
            )

        for topic in self.topics:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Topic",
                    id=topic.topic_id,
                    properties=_compact_dict(
                        {
                            "topic_id": topic.topic_id,
                            "topic_label": topic.topic_label,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "HAS_TOPIC",
                "Case",
                self.case_id,
                "Topic",
                topic.topic_id,
            )

        for motion in self.motions:
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Motion",
                    id=motion.motion_id,
                    properties=_compact_dict(
                        {
                            "motion_id": motion.motion_id,
                            "motion_type": motion.motion_type,
                            "disposition": motion.disposition,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "HAS_MOTION",
                "Case",
                self.case_id,
                "Motion",
                motion.motion_id,
            )

        remedy_map = {remedy.remedy_type: remedy for remedy in self.remedies}
        for remedy_type in self.outcome.relief.granted:
            remedy_map.setdefault(remedy_type, RemedyRecord(remedy_type=remedy_type, granted=True))
        for remedy_type in self.outcome.relief.denied:
            remedy_map.setdefault(remedy_type, RemedyRecord(remedy_type=remedy_type, granted=False))

        for remedy in remedy_map.values():
            self._add_node(
                nodes,
                GraphNodeUpsert(
                    label="Remedy",
                    id=remedy.remedy_id,
                    properties=_compact_dict(
                        {
                            "remedy_id": remedy.remedy_id,
                            "remedy_type": remedy.remedy_type,
                            "granted": remedy.granted,
                        }
                    ),
                ),
            )
            self._add_rel(
                relationships,
                "SEEKS_REMEDY",
                "Case",
                self.case_id,
                "Remedy",
                remedy.remedy_id,
                granted=remedy.granted,
            )

        self._add_node(
            nodes,
            GraphNodeUpsert(
                label="Outcome",
                id=self.outcome.outcome_id,
                properties=_compact_dict(
                    {
                        "outcome_id": self.outcome.outcome_id,
                        "case_id": self.case_id,
                        "disposition": self.outcome.disposition,
                        "winner": self.outcome.winner,
                        "direction": self.outcome.decision_direction,
                        "relief_granted": self.outcome.relief.granted,
                        "relief_denied": self.outcome.relief.denied,
                        "created_rule": self.outcome.precedent_effect.created_rule,
                        "clarified_rule": self.outcome.precedent_effect.clarified_rule,
                        "limited_prior_case": self.outcome.precedent_effect.limited_prior_case,
                        "overruled_prior_case": self.outcome.precedent_effect.overruled_prior_case,
                    }
                ),
            ),
        )
        self._add_rel(
            relationships,
            "RESULTS_IN",
            "Case",
            self.case_id,
            "Outcome",
            self.outcome.outcome_id,
        )

        if self.procedure.appealed_from_case_id:
            if include_stub_cases:
                self._add_node(
                    nodes,
                    GraphNodeUpsert(
                        label="Case",
                        id=self.procedure.appealed_from_case_id,
                        properties={"case_id": self.procedure.appealed_from_case_id, "is_stub": True},
                    ),
                )
            self._add_rel(
                relationships,
                "APPEAL_FROM",
                "Case",
                self.case_id,
                "Case",
                self.procedure.appealed_from_case_id,
            )

        for cited_case_id in self.law.prior_cases_cited:
            if include_stub_cases:
                self._add_node(
                    nodes,
                    GraphNodeUpsert(
                        label="Case",
                        id=cited_case_id,
                        properties={"case_id": cited_case_id, "is_stub": True},
                    ),
                )
            self._add_rel(
                relationships,
                "CITES_CASE",
                "Case",
                self.case_id,
                "Case",
                cited_case_id,
                treatment=AuthorityTreatment.cited.value,
            )

        for authority in self.reasoning.authorities:
            if include_stub_cases:
                self._add_node(
                    nodes,
                    GraphNodeUpsert(
                        label="Case",
                        id=authority.cited_case_id,
                        properties={"case_id": authority.cited_case_id, "is_stub": True},
                    ),
                )
            self._add_rel(
                relationships,
                "CITES_CASE",
                "Case",
                self.case_id,
                "Case",
                authority.cited_case_id,
                treatment=authority.treatment,
                citation_context=authority.citation_context,
                quoted_passages=authority.quoted_passages,
                doctrinal_relevance_score=authority.doctrinal_relevance_score,
                citation_count=authority.citation_count,
                context_strength=authority.context_strength,
                depth=authority.depth,
            )
            typed_rel = self.TREATMENT_TO_REL.get(authority.treatment)
            if typed_rel:
                self._add_rel(
                    relationships,
                    typed_rel,
                    "Case",
                    self.case_id,
                    "Case",
                    authority.cited_case_id,
                    citation_context=authority.citation_context,
                    doctrinal_relevance_score=authority.doctrinal_relevance_score,
                )
            if authority.source_opinion_id and authority.cited_opinion_id:
                if include_stub_cases:
                    self._add_node(
                        nodes,
                        GraphNodeUpsert(
                            label="Opinion",
                            id=authority.cited_opinion_id,
                            properties={"opinion_id": authority.cited_opinion_id, "is_stub": True},
                        ),
                    )
                self._add_rel(
                    relationships,
                    "CITES",
                    "Opinion",
                    authority.source_opinion_id,
                    "Opinion",
                    authority.cited_opinion_id,
                    treatment=authority.treatment,
                    citation_context=authority.citation_context,
                    quoted_passages=authority.quoted_passages,
                    citation_count=authority.citation_count,
                    context_strength=authority.context_strength,
                    depth=authority.depth,
                )
            if authority.source_holding_id and authority.cited_holding_id:
                self._add_rel(
                    relationships,
                    "RELIES_ON",
                    "Holding",
                    authority.source_holding_id,
                    "Holding",
                    authority.cited_holding_id,
                    treatment=authority.treatment,
                    doctrinal_relevance_score=authority.doctrinal_relevance_score,
                )

        for limited_case_id in self.outcome.precedent_effect.limited_prior_case:
            if include_stub_cases:
                self._add_node(
                    nodes,
                    GraphNodeUpsert(
                        label="Case",
                        id=limited_case_id,
                        properties={"case_id": limited_case_id, "is_stub": True},
                    ),
                )
            self._add_rel(
                relationships,
                "LIMITS",
                "Case",
                self.case_id,
                "Case",
                limited_case_id,
                effect=PrecedentialEffectType.limited_prior_case.value,
            )

        for overruled_case_id in self.outcome.precedent_effect.overruled_prior_case:
            if include_stub_cases:
                self._add_node(
                    nodes,
                    GraphNodeUpsert(
                        label="Case",
                        id=overruled_case_id,
                        properties={"case_id": overruled_case_id, "is_stub": True},
                    ),
                )
            self._add_rel(
                relationships,
                "OVERRULES",
                "Case",
                self.case_id,
                "Case",
                overruled_case_id,
                effect=PrecedentialEffectType.overruled_prior_case.value,
            )

        return GraphDocument(nodes=nodes, relationships=relationships).deduplicate()

class CaseExtractionEnvelope(AcquittifyBaseModel):
    schema_version: str = "1.0"
    schema_name: str = "us_case_law_graph_schema"
    case: CaseExtraction

    def as_yaml_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schema_name": self.schema_name,
            "case": self.case.as_yaml_payload(),
        }

    def to_graph_document(self, include_stub_cases: bool = True) -> GraphDocument:
        return self.case.to_graph_document(include_stub_cases=include_stub_cases)
