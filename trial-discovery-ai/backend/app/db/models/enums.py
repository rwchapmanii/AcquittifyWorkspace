from enum import Enum


class DocumentStatus(str, Enum):
    NEW = "NEW"
    PREPROCESSED = "PREPROCESSED"
    INDEXED = "INDEXED"
    READY = "READY"
    ERROR = "ERROR"


class ArtifactKind(str, Enum):
    PAGE_IMAGE = "PAGE_IMAGE"
    EXTRACTED_TEXT = "EXTRACTED_TEXT"
    OCR_TEXT = "OCR_TEXT"
    EMAIL_JSON = "EMAIL_JSON"
    THUMBNAIL = "THUMBNAIL"


class PassStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    REPAIRED = "REPAIRED"


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORG = "ORG"


class DocumentEntityRole(str, Enum):
    AUTHOR = "AUTHOR"
    SENDER = "SENDER"
    RECIPIENT = "RECIPIENT"
    MENTIONED = "MENTIONED"
    SIGNATORY = "SIGNATORY"


class ExhibitPurpose(str, Enum):
    IMPEACHMENT = "IMPEACHMENT"
    TIMELINE = "TIMELINE"
    BIAS = "BIAS"
    SUBSTANTIVE = "SUBSTANTIVE"
    FOUNDATION = "FOUNDATION"


class UserActionType(str, Enum):
    VIEW = "VIEW"
    MARK_HOT = "MARK_HOT"
    UNMARK_HOT = "UNMARK_HOT"
    PRIORITY_OVERRIDE = "PRIORITY_OVERRIDE"
    MARK_EXHIBIT = "MARK_EXHIBIT"
    UNMARK_EXHIBIT = "UNMARK_EXHIBIT"
    EXPORT = "EXPORT"
    EVIDENCE_ADD = "EVIDENCE_ADD"
    EVIDENCE_REMOVE = "EVIDENCE_REMOVE"
