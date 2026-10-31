"""Phase 2 contracts. Agreement and documentary support do not imply clinical truth."""

from enum import StrEnum
from typing import Literal, Protocol, Self, TypeVar

from pydantic import Field, JsonValue, model_validator

from extracteval.core.base import ArtifactRef, Contract, Digest, Identifier
from extracteval.core.documents import Document, Evidence
from extracteval.core.models import ModelParameters, ModelResponse
from extracteval.core.results import ExtractionResult, TechnicalError
from extracteval.core.specification import SemanticValue


class SemanticState(StrEnum):
    VALUE = "value"
    INDETERMINATE = "indeterminate"
    DOCUMENTED_ABSENCE = "documented_absence"
    NOT_APPLICABLE = "not_applicable"
    ABSTAIN = "abstain"
    NO_RESPONSE = "no_response"


class VariableVerification(Contract):
    variable_id: Identifier
    proposed_value: SemanticValue | None = Field(default=None, repr=False)
    semantic_state: SemanticState
    evidence: tuple[Evidence, ...] = ()
    evidence_type: Literal["literal", "rule_derived", "none"]
    applied_rule_ids: tuple[Identifier, ...] = ()
    uncertainty_flags: tuple[Identifier, ...] = ()
    requires_human_review: bool = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.semantic_state == SemanticState.VALUE and self.proposed_value is None:
            raise ValueError("A semantic value requires a proposal")
        if self.semantic_state in (SemanticState.ABSTAIN, SemanticState.NO_RESPONSE):
            if self.proposed_value is not None:
                raise ValueError("Abstention or missing response cannot carry a value")
        if (self.evidence_type == "none") != (not self.evidence):
            raise ValueError("Evidence type must match the supplied evidence")
        return self


class VerificationPayload(Contract):
    variables: tuple[VariableVerification, ...]

    @model_validator(mode="after")
    def unique(self) -> Self:
        ids = [v.variable_id for v in self.variables]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate variable proposals")
        return self


class VerificationConfig(Contract):
    version: Identifier
    model_id: Identifier
    reconciler_model_id: Identifier | None = None
    parameters: ModelParameters
    timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)
    prompt: str = Field(repr=False, min_length=1)
    prompt_version: Identifier
    allowed_metadata_keys: tuple[Identifier, ...] = ()


class CallAudit(Contract):
    requested_model: Identifier
    requested_parameters: ModelParameters
    response: ModelResponse | None = None
    error: TechnicalError | None = None
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    retry_count: int = Field(default=0, ge=0)
    # Sanitized codes only; never exception messages or raw provider bodies.
    errors: tuple[Identifier, ...] = ()
    cost_estimate: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    pricing_table: ArtifactRef | None = None

    @model_validator(mode="after")
    def price_provenance(self) -> Self:
        if self.cost_estimate is not None and self.pricing_table is None:
            raise ValueError("A cost estimate requires a versioned pricing table")
        return self


class IndependentVerification(Contract):
    verification_id: Identifier
    document_id: Identifier
    document_hash: Digest
    dictionary: ArtifactRef
    prompt_version: Identifier
    model_config_version: Identifier
    input_hash: Digest
    payload: VerificationPayload
    audit: CallAudit
    evidence_findings: dict[str, tuple[Identifier, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def failure_is_operational(self) -> Self:
        if self.audit.error is not None and self.payload.variables:
            raise ValueError("Failed verification cannot contain clinical proposals")
        if not set(self.evidence_findings) <= {v.variable_id for v in self.payload.variables}:
            raise ValueError("Evidence findings require a corresponding variable proposal")
        return self


class ExtractionSnapshot(Contract):
    """Document-wide A: reuse the original per-variable ExtractionResult contract."""

    base_extraction_id: Identifier
    source_sha256: Digest | None = None
    document_id: Identifier
    dictionary: ArtifactRef
    results: tuple[ExtractionResult, ...]
    semantic_states: dict[str, SemanticState] = Field(default_factory=dict)
    auxiliary: dict[str, JsonValue] = Field(default_factory=dict, repr=False)

    @model_validator(mode="after")
    def same_document(self) -> Self:
        ids = [v.trace.variable_id for v in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate extraction variables")
        for result in self.results:
            if (
                result.trace.document_id != self.document_id
                or result.trace.dictionary != self.dictionary
            ):
                raise ValueError("Extraction provenance mismatch")
            state = self.semantic_states.get(result.trace.variable_id)
            if state == SemanticState.VALUE and result.value is None:
                raise ValueError("A semantic value requires an extraction value")
            if (
                state in (SemanticState.ABSTAIN, SemanticState.NO_RESPONSE)
                and result.value is not None
            ):
                raise ValueError("Missing or abstained extraction cannot carry a value")
            if result.technical_error and state is not None:
                raise ValueError("Technical failure cannot have a semantic state")
        if not set(self.semantic_states) <= set(ids):
            raise ValueError("Semantic state without an extraction result")
        return self


ComparisonRelation = Literal[
    "exact_match",
    "value_difference",
    "missing_response",
    "normalization_difference",
    "technical_error",
]


class VariableComparison(Contract):
    variable_id: Identifier
    relation: ComparisonRelation
    findings: tuple[Identifier, ...] = ()
    normalization_rule_ids: tuple[Identifier, ...] = ()


class ComparisonResult(Contract):
    comparison_id: Identifier
    document_id: Identifier
    base_extraction_id: Identifier
    base_extraction_hash: Digest
    verification_id: Identifier
    verification_hash: Digest
    dictionary: ArtifactRef
    variables: tuple[VariableComparison, ...]


class DecisionAction(StrEnum):
    KEEP_A = "KEEP_A"
    REPLACE_WITH_VERIFIED = "REPLACE_WITH_VERIFIED"
    ABSTAIN = "ABSTAIN"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ReplacementRule(Contract):
    rule_id: Identifier
    approved: bool = False
    variable_id: Identifier
    proposed_value: SemanticValue
    semantic_state: SemanticState = SemanticState.VALUE
    required_rule_ids: tuple[Identifier, ...] = ()
    # Rules certify documentary sufficiency; quote existence alone never does.
    literal_evidence_sufficient: bool = False
    required_evidence_quotes: tuple[str, ...] = ()


class ReconciliationPolicy(Contract):
    policy_id: Identifier
    version: Identifier
    replacement_rules: tuple[ReplacementRule, ...] = ()
    unresolved_action: Literal["KEEP_A", "ABSTAIN", "HUMAN_REVIEW"] = "HUMAN_REVIEW"

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        ids = [rule.rule_id for rule in self.replacement_rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate policy rule identifiers")
        return self


class ReconciliationDecision(Contract):
    variable_id: Identifier
    action: DecisionAction
    reason: Identifier
    rule_id: Identifier | None = None
    previous_value: SemanticValue | None = Field(default=None, repr=False)
    resulting_value: SemanticValue | None = Field(default=None, repr=False)
    previous_state: SemanticState | None = None
    resulting_state: SemanticState | None = None
    technical_error: TechnicalError | None = None
    requires_human_review: bool

    @model_validator(mode="after")
    def coherent_decision(self) -> Self:
        if self.action in (DecisionAction.KEEP_A, DecisionAction.HUMAN_REVIEW):
            if (self.previous_value, self.previous_state) != (
                self.resulting_value,
                self.resulting_state,
            ):
                raise ValueError("Preservation decisions cannot change the original outcome")
        if self.action == DecisionAction.REPLACE_WITH_VERIFIED:
            if self.rule_id is None or self.resulting_value is None:
                raise ValueError("Replacement requires an authorized rule and a proposed value")
        if self.action == DecisionAction.ABSTAIN:
            if self.resulting_value is not None or self.resulting_state != SemanticState.ABSTAIN:
                raise ValueError("Abstention requires its own semantic state without a value")
        if self.technical_error is not None:
            if self.resulting_state is not None or self.resulting_value is not None:
                raise ValueError("A technical error cannot become a clinical outcome")
        if self.action == DecisionAction.HUMAN_REVIEW and not self.requires_human_review:
            raise ValueError("Human review decision must request human review")
        return self


class ReconciledExtraction(Contract):
    reconciliation_id: Identifier
    document_id: Identifier
    document_hash: Digest
    base_extraction_id: Identifier
    base_extraction_hash: Digest
    source_sha256: Digest | None = None
    verification_id: Identifier
    comparison_id: Identifier
    dictionary: ArtifactRef
    policy_version: Identifier
    decisions: tuple[ReconciliationDecision, ...]
    auxiliary: dict[str, JsonValue] = Field(default_factory=dict, repr=False)
    clinically_validated: Literal[False] = False
    expert_reference_status: Literal["not_provided"] = "not_provided"


class VerificationRunManifest(Contract):
    """Phase 2 run manifest complements the phase 1 experiment manifest."""

    run_id: Identifier
    document_id: Identifier
    base_extraction_id: Identifier | None
    base_extraction_hash: Digest | None
    verification_id: Identifier | None
    reconciliation_id: Identifier | None
    dictionary_version: Identifier
    prompt_version: Identifier
    model_config_version: Identifier
    policy_version: Identifier
    input_hash: Digest
    output_hash: Digest
    artifact_hashes: dict[str, str]
    status: Literal["completed", "technical_failure"]
    mode: Literal["mock", "real"]
    package_version: Identifier
    started_at: str
    finished_at: str


T = TypeVar("T", bound=Contract)


class VerificationStore(Protocol):
    """Local artifacts must be immutable and content checked when resumed."""

    def put(self, name: str, value: Contract) -> None: ...

    def get(self, name: str, contract: type[T]) -> T: ...

    def exists(self, name: str) -> bool: ...

    def artifact_hashes(self) -> dict[str, str]: ...


class VerificationInput(Contract):
    document: Document
    extraction_a: ExtractionSnapshot | None = None
