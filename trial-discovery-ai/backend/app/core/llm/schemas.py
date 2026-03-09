from pydantic import BaseModel, Field


class DocIdentity(BaseModel):
    source_path: str
    original_filename: str
    mime_type: str
    sha256: str
    file_size: int
    page_count: int | None = None
    doc_title: str | None = None
    email_subject: str | None = None
    email_message_id: str | None = None
    source_system: str | None = None
    custodian: str | None = None


class DocType(BaseModel):
    category: str
    draft_final: str
    internal_external: str
    domain: str


class AuthorshipTransmission(BaseModel):
    author_names: list[str] = Field(default_factory=list)
    sender: str | None = None
    recipients_to: list[str] = Field(default_factory=list)
    recipients_cc: list[str] = Field(default_factory=list)
    recipients_bcc: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)


class TimeInfo(BaseModel):
    system_created_at: str | None = None
    system_modified_at: str | None = None
    sent_at: str | None = None
    dates_mentioned: list[str] = Field(default_factory=list)


class EntitiesRaw(BaseModel):
    people_mentioned: list[str] = Field(default_factory=list)
    orgs_mentioned: list[str] = Field(default_factory=list)


class QualityInfo(BaseModel):
    ocr_used: bool
    ocr_confidence_overall: float | None = None
    parsing_confidence_overall: float | None = None


class Pass1Schema(BaseModel):
    doc_identity: DocIdentity
    doc_type: DocType
    authorship_transmission: AuthorshipTransmission | None = None
    time: TimeInfo
    entities_raw: EntitiesRaw
    quality: QualityInfo
    document_type: str | None = None
    witnesses: list[str] = Field(default_factory=list)
    document_date: str | None = None
    relevance: str | None = None
    proponent: str | None = None
    identity_confidence: float | None = None
    identity_evidence: list[str] = Field(default_factory=list)


class EnrichedEntity(BaseModel):
    name: str
    entity_type: str
    confidence: float | None = None
    role_hypothesis: str | None = None


class EventSignal(BaseModel):
    event_type: str
    date: str | None = None
    participants: list[str] = Field(default_factory=list)
    summary: str
    confidence: float | None = None


class StatementSignal(BaseModel):
    text_span_ref: str
    statement_type: str
    speaker: str | None = None
    certainty: float | None = None
    first_hand_likelihood: float | None = None


class KnowledgeSignal(BaseModel):
    type: str
    about: str
    time_ref: str | None = None
    confidence: float | None = None


class PrivilegeSensitivity(BaseModel):
    attorney_involved: bool
    attorney_involved_confidence: float | None = None
    legal_advice_likelihood: float | None = None
    work_product_likelihood: float | None = None
    pii_flags: list[str] = Field(default_factory=list)


class TrialSignals(BaseModel):
    trial_relevance_hint: float | None = None
    govt_reliance_likelihood: float | None = None
    defense_value_likelihood: float | None = None
    redundancy_hint: float | None = None
    jury_readability_hint: float | None = None


class Pass2Schema(BaseModel):
    doc_subtype: str | None = None
    entities_enriched: list[EnrichedEntity] = Field(default_factory=list)
    events: list[EventSignal] = Field(default_factory=list)
    statements: list[StatementSignal] = Field(default_factory=list)
    knowledge_signals: list[KnowledgeSignal] = Field(default_factory=list)
    privilege_sensitivity: PrivilegeSensitivity
    generic_trial_signals: TrialSignals


class EvidenceRef(BaseModel):
    chunk_id: str | None = None
    quote: str | None = None
    page_num: int | None = None


class ExhibitCandidate(BaseModel):
    is_candidate: bool
    purposes: list[str] = Field(default_factory=list)
    foundation_needed_hint: bool | None = None
    backfire_risk_hint: float | None = None
    likely_objection_hints: list[str] = Field(default_factory=list)


class Pass4Schema(BaseModel):
    priority_code: str
    priority_rationale: list[str] = Field(default_factory=list)
    hot_doc_candidate: bool
    hot_doc_confidence: float | None = None
    exhibit_candidate: ExhibitCandidate
    similarity_hooks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
