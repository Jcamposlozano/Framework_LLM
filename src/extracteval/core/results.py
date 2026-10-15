"""Extraction outcomes with orthogonal semantic and operational dimensions."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from extracteval.core.base import ArtifactRef, Contract, Identifier
from extracteval.core.documents import EvidenceAssessment
from extracteval.core.experiments import ConfigRef, ExperimentConfig
from extracteval.core.models import ModelIdentity
from extracteval.core.specification import OperationalDictionary, SemanticValue


class OperationStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class Abstention(Contract):
    reason: Literal["insufficient_evidence", "policy", "unsupported_input"]
    policy: ArtifactRef | None = None


class TechnicalError(Contract):
    code: Literal["timeout", "unavailable", "invalid_response", "internal_error"]
    retryable: bool = False


class ValidationFinding(Contract):
    code: Identifier
    severity: Literal["warning", "contradiction", "invalidating_error"]
    rule: ArtifactRef | None = None


class ResultTrace(Contract):
    document_id: Identifier
    variable_id: Identifier
    dictionary: ArtifactRef
    config: ConfigRef
    execution_id: Identifier
    output_schema: ArtifactRef
    model: ModelIdentity | None = None
    instructions: ArtifactRef | None = None
    request_id: Identifier | None = None
    provider_request_id: Identifier | None = None

    @model_validator(mode="after")
    def model_provenance(self) -> Self:
        if self.model is None and (
            self.request_id is not None
            or self.provider_request_id is not None
            or self.instructions is not None
        ):
            raise ValueError("Model request provenance requires a model identity")
        if self.model is not None and (self.instructions is None or self.request_id is None):
            raise ValueError(
                "Model results require instructions and an internal request identifier"
            )
        return self

    def validate_config(
        self, config: ExperimentConfig, role: Literal["extractor", "verifier"] = "extractor"
    ) -> None:
        if (
            self.config != ConfigRef.from_config(config)
            or self.dictionary != config.dictionary
            or self.output_schema != config.output_schema
        ):
            raise ValueError("Result provenance does not match experiment configuration")
        if self.model is not None:
            binding = config.extractor if role == "extractor" else config.verifier
            instructions = (
                config.extractor_instructions
                if role == "extractor"
                else config.verifier_instructions
            )
            if binding is None or binding.model != self.model or instructions != self.instructions:
                raise ValueError("Result model provenance does not match configured role")


class ExtractionResult(Contract):
    result_id: Identifier
    trace: ResultTrace
    operation: OperationStatus
    value: SemanticValue | None = Field(default=None, repr=False)
    evidence: EvidenceAssessment
    abstention: Abstention | None = None
    technical_error: TechnicalError | None = None
    findings: tuple[ValidationFinding, ...] = ()

    @model_validator(mode="after")
    def coherent_outcome(self) -> Self:
        if self.operation == OperationStatus.FAILED:
            if (
                self.technical_error is None
                or self.value is not None
                or self.abstention is not None
            ):
                raise ValueError("Failed operations require only a technical error outcome")
        elif self.technical_error is not None:
            raise ValueError("Completed operations cannot contain a technical error")
        if self.abstention is not None and self.value is not None:
            raise ValueError("Abstention cannot contain an extracted value")
        if any(item.document_id != self.trace.document_id for item in self.evidence.items):
            raise ValueError("Evidence must refer to the result document")
        return self

    def validate_against(self, dictionary: OperationalDictionary) -> None:
        if self.trace.dictionary != dictionary.artifact:
            raise ValueError("Result dictionary reference does not match")
        definition = dictionary.variable(self.trace.variable_id)
        if self.value is not None:
            definition.validate_value(self.value)
