"""Documents and evidence, independent of any extraction engine."""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, model_validator

from extracteval.core.base import Contract, Identifier


class Document(Contract):
    document_id: Identifier
    entity_id: Identifier | None = None
    text: str | None = Field(default=None, repr=False)
    text_ref: Identifier | None = None
    document_date: date | None = None
    provenance: dict[str, JsonValue] = Field(default_factory=dict, repr=False)
    allowed_context: dict[str, JsonValue] = Field(default_factory=dict, repr=False)

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if (self.text is None) == (self.text_ref is None):
            raise ValueError("Provide exactly one document content source")
        return self


class Evidence(Contract):
    document_id: Identifier
    quote: str | None = Field(default=None, repr=False)
    source_ref: Identifier | None = None
    start: int | None = Field(default=None, ge=0, strict=True)
    end: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def valid_location(self) -> Self:
        if self.quote is None and self.source_ref is None:
            raise ValueError("Evidence requires a quote or a secure source reference")
        if (self.start is None) != (self.end is None):
            raise ValueError("Evidence offsets must be supplied together")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("Evidence end must follow start")
        return self


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    ABSENT = "absent"
    NOT_ASSESSED = "not_assessed"


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNDETERMINED = "undetermined"
    NOT_ASSESSED = "not_assessed"


class EvidenceAssessment(Contract):
    availability: EvidenceAvailability
    sufficiency: EvidenceSufficiency
    items: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.items and self.availability != EvidenceAvailability.AVAILABLE:
            raise ValueError("Evidence items require available evidence")
        if self.availability == EvidenceAvailability.AVAILABLE and not self.items:
            raise ValueError("Available evidence requires at least one evidence item")
        if (
            self.sufficiency == EvidenceSufficiency.SUFFICIENT
            and self.availability != EvidenceAvailability.AVAILABLE
        ):
            raise ValueError("Sufficient evidence must be available")
        if (
            self.availability == EvidenceAvailability.NOT_ASSESSED
            and self.sufficiency != EvidenceSufficiency.NOT_ASSESSED
        ):
            raise ValueError("Unassessed availability requires unassessed sufficiency")
        return self
