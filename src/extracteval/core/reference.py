"""Expert references are independent of model responses and operational review."""

from typing import Literal, Self

from pydantic import Field, model_validator

from extracteval.core.base import ArtifactRef, Contract, Identifier
from extracteval.core.documents import EvidenceAssessment
from extracteval.core.specification import OperationalDictionary, SemanticValue


class ExpertAnnotation(Contract):
    annotation_id: Identifier
    document_id: Identifier
    variable_id: Identifier
    evaluator_id: Identifier
    dictionary: ArtifactRef
    partition: Literal["development", "calibration", "evaluation"]
    blinded_to_system_output: bool
    status: Literal["evaluable", "not_evaluable"]
    value: SemanticValue | None = Field(default=None, repr=False)
    evidence: EvidenceAssessment

    @model_validator(mode="after")
    def consistent_annotation(self) -> Self:
        if (self.status == "evaluable") != (self.value is not None):
            raise ValueError("Only evaluable annotations must contain a semantic value")
        if any(item.document_id != self.document_id for item in self.evidence.items):
            raise ValueError("Evidence must refer to the annotated document")
        return self

    def validate_against(self, dictionary: OperationalDictionary) -> None:
        if self.dictionary != dictionary.artifact:
            raise ValueError("Annotation dictionary reference does not match")
        definition = dictionary.variable(self.variable_id)
        if self.value is not None:
            definition.validate_value(self.value)


class AdjudicatedReference(Contract):
    reference_id: Identifier
    annotations: tuple[ExpertAnnotation, ...] = Field(min_length=2)
    adjudicator_id: Identifier
    disagreement: bool
    status: Literal["final", "unresolved", "not_evaluable"]
    value: SemanticValue | None = Field(default=None, repr=False)
    evidence: EvidenceAssessment

    @model_validator(mode="after")
    def consistent_reference(self) -> Self:
        first = self.annotations[0]
        keys = {(a.document_id, a.variable_id, a.dictionary, a.partition) for a in self.annotations}
        if len(keys) != 1:
            raise ValueError("Adjudication requires the same field, dictionary and partition")
        if len({a.annotation_id for a in self.annotations}) != len(self.annotations):
            raise ValueError("Annotation identifiers must be unique")
        if len({a.evaluator_id for a in self.annotations}) != len(self.annotations):
            raise ValueError("Adjudication requires distinct evaluators")
        actual_disagreement = any(
            (a.status, a.value) != (first.status, first.value) for a in self.annotations[1:]
        )
        if self.disagreement != actual_disagreement:
            raise ValueError("Declared disagreement does not match annotations")
        if (self.status == "final") != (self.value is not None):
            raise ValueError("Only final references must contain a semantic value")
        if any(item.document_id != first.document_id for item in self.evidence.items):
            raise ValueError("Evidence must refer to the adjudicated document")
        return self

    def validate_against(self, dictionary: OperationalDictionary) -> None:
        for annotation in self.annotations:
            annotation.validate_against(dictionary)
        if self.value is not None:
            dictionary.variable(self.annotations[0].variable_id).validate_value(self.value)
