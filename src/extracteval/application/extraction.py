"""Document extraction A using existing contracts; no embedded clinical rules."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError

from extracteval.application.verification import evidence_findings, strict_schema
from extracteval.core.base import ArtifactRef, Contract, Digest, Identifier
from extracteval.core.documents import (
    Document,
    EvidenceAssessment,
    EvidenceAvailability,
    EvidenceSufficiency,
)
from extracteval.core.exceptions import ModelError, ProviderFailure
from extracteval.core.experiments import ConfigRef, ExperimentConfig, ModelBinding, ModelRunRecord
from extracteval.core.hashing import content_hash
from extracteval.core.models import ModelParameters, ModelRequest, ModelResponse, ResponseFormat
from extracteval.core.ports import ModelPort
from extracteval.core.results import (
    Abstention,
    ExtractionResult,
    OperationStatus,
    ResultTrace,
    TechnicalError,
    ValidationFinding,
)
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import (
    CallAudit,
    ExtractionSnapshot,
    SemanticState,
    VerificationPayload,
    VerificationStore,
)

POSTPROCESSING_VERSION: Literal["extraction-mapping.v1"] = "extraction-mapping.v1"


class ExtractorSettings(Contract):
    """Application configuration, separate from V and from scientific approval."""

    version: Identifier
    dictionary_path: str
    dictionary: ArtifactRef
    prompt_path: str
    prompt_version: Identifier
    prompt_sha256: Digest
    model: Identifier = "gpt-4.1-mini"
    max_output_tokens: int = Field(default=4096, gt=0)
    request_timeout: float = Field(default=60, gt=0, allow_inf_nan=False)
    allowed_metadata_keys: tuple[Identifier, ...] = ()
    postprocessing_version: Literal["extraction-mapping.v1"] = POSTPROCESSING_VERSION
    mock_payload_path: str | None = None


class ExtractionExecution(Contract):
    input_hash: Digest
    document_hash: Digest
    extraction_a: ExtractionSnapshot
    configured_settings: ExtractorSettings
    requested_configuration: ExperimentConfig
    effective_configuration: ExperimentConfig
    model_record: ModelRunRecord | None
    audit: CallAudit
    response_schema: ArtifactRef
    postprocessing: ArtifactRef
    mode: Literal["mock", "real"]
    clinically_validated: Literal[False] = False


class ExtractionManifest(Contract):
    input_hash: Digest
    artifact_hashes: dict[str, str]


def load_extractor(
    path: Path, environment: Mapping[str, str]
) -> tuple[ExtractorSettings, OperationalDictionary, str]:
    settings = ExtractorSettings.model_validate_json(path.read_bytes())
    # Only A-specific overrides are accepted; V overrides cannot affect A.
    updates: dict[str, object] = {}
    for env, name, convert in (
        ("EXTRACTEVAL_EXTRACTOR_MODEL", "model", str),
        ("EXTRACTEVAL_EXTRACTOR_MAX_OUTPUT_TOKENS", "max_output_tokens", int),
        ("EXTRACTEVAL_EXTRACTOR_REQUEST_TIMEOUT", "request_timeout", float),
    ):
        if env in environment:
            updates[name] = convert(environment[env])
    settings = ExtractorSettings.model_validate(settings.model_dump() | updates)
    root = path.resolve().parent
    dictionary = OperationalDictionary.model_validate_json(
        (root / settings.dictionary_path).read_bytes()
    )
    if (
        dictionary.artifact != settings.dictionary
        or content_hash(dictionary.model_dump(mode="json", exclude={"artifact"}))
        != dictionary.artifact.sha256
    ):
        raise ValueError("Extractor dictionary integrity mismatch")
    prompt_bytes = (root / settings.prompt_path).read_bytes()
    if hashlib.sha256(prompt_bytes).hexdigest() != settings.prompt_sha256:
        raise ValueError("Extractor prompt integrity mismatch")
    prompt = prompt_bytes.decode("utf-8")
    if not prompt.strip():
        raise ValueError("Extractor prompt is empty")
    return settings, dictionary, prompt


def extraction_schema_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="extracteval.core.verification.VerificationPayload",
        version="1.0",
        sha256=content_hash(strict_schema(VerificationPayload.model_json_schema())),
    )


def postprocessing_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="extracteval.application.extraction",
        version=POSTPROCESSING_VERSION,
        sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )


def extract_document(
    document: Document,
    dictionary: OperationalDictionary,
    settings: ExtractorSettings,
    prompt: str,
    model: ModelPort | None,
    store: VerificationStore,
    *,
    mode: Literal["mock", "real"] = "mock",
    mock_payload_hash: Digest | None = None,
) -> ExtractionExecution:
    """One completed A per store. Interrupted attempts are never silently rerun."""
    if document.text is None:
        raise ValueError("Resolve document text locally first")
    if (
        dictionary.artifact != settings.dictionary
        or content_hash(dictionary.model_dump(mode="json", exclude={"artifact"}))
        != dictionary.artifact.sha256
    ):
        raise ValueError("Extractor dictionary mismatch")
    if hashlib.sha256(prompt.encode()).hexdigest() != settings.prompt_sha256:
        raise ValueError("Extractor prompt mismatch")
    safe_document = Document(
        document_id=document.document_id,
        text=document.text,
        document_date=document.document_date,
        sections=document.sections,
        allowed_context={
            k: v for k, v in document.allowed_context.items() if k in settings.allowed_metadata_keys
        },
    )
    parameters = ModelParameters(
        max_output_tokens=settings.max_output_tokens, response_format=ResponseFormat.STRUCTURED
    )
    schema_ref, mapper_ref = extraction_schema_ref(), postprocessing_ref()
    input_hash = content_hash(
        {
            "document": document.model_dump(mode="json"),
            "dictionary": dictionary.model_dump(mode="json"),
            "settings": settings.model_dump(mode="json"),
            "schema": schema_ref.model_dump(mode="json"),
            "mapper": mapper_ref.model_dump(mode="json"),
            "mode": mode,
            "mock_payload_hash": mock_payload_hash,
        }
    )
    if store.exists("manifest"):
        manifest = store.get("manifest", ExtractionManifest)
        hashes = store.artifact_hashes()
        if manifest.input_hash != input_hash or hashes != manifest.artifact_hashes:
            raise ValueError("Extraction resume integrity mismatch")
        return store.get("execution", ExtractionExecution)
    if store.exists("request"):
        raise ValueError(
            "Interrupted extraction: inspect saved artifacts; no automatic second call"
        )
    if model is None:
        raise ValueError("An extractor model is required for a new execution")
    if mode == "real" and model.identity.model_id != settings.model:
        raise ValueError("Configured and bound extractor models differ")
    model.capabilities.validate_parameters(parameters)
    run_id = "extraction-" + uuid4().hex
    request = ModelRequest(
        execution_id=run_id,
        request_id="request-" + uuid4().hex,
        instructions=prompt,
        content=json.dumps(
            {
                "document": safe_document.model_dump(mode="json"),
                "dictionary": dictionary.model_dump(mode="json"),
            },
            ensure_ascii=False,
        ),
        parameters=parameters,
        response_schema=strict_schema(VerificationPayload.model_json_schema()),
        timeout_seconds=settings.request_timeout,
    )
    result_schema = ArtifactRef(
        artifact_id="extracteval.core.results.ExtractionResult",
        version="1.0",
        sha256=content_hash(ExtractionResult.model_json_schema()),
    )
    requested = ExperimentConfig(
        config_id="extractor-a",
        version=settings.version,
        dictionary=dictionary.artifact,
        output_schema=result_schema,
        extractor_instructions=ArtifactRef(
            artifact_id="extractor-prompt",
            version=settings.prompt_version,
            sha256=settings.prompt_sha256,
        ),
        extractor=ModelBinding(
            adapter_id="openai-responses" if mode == "real" else "mock",
            model=model.identity,
            parameters=parameters,
        ),
    )
    # Durable intent before generation prevents a silent retry after process interruption.
    store.put("request", request)
    response: ModelResponse | None = None
    error: TechnicalError | None = None
    payload = VerificationPayload(variables=())
    retries = 0
    errors: tuple[str, ...] = ()
    started = perf_counter()
    try:
        response = model.generate(request)
        retries, errors = response.retry_count, response.diagnostic_error_codes
        if (response.execution_id, response.request_id) != (run_id, request.request_id):
            raise ValueError("Response trace mismatch")
        if response.structured_json is None:
            raise ValueError("Structured output required")
        payload = VerificationPayload.model_validate_json(response.structured_json)
        expected = {v.variable_id for v in dictionary.variables}
        if {v.variable_id for v in payload.variables} != expected:
            raise ValueError("Exactly one proposal per dictionary variable required")
        for item in payload.variables:
            if any(e.document_id != document.document_id for e in item.evidence):
                raise ValueError("Evidence document mismatch")
            if item.proposed_value is not None:
                dictionary.variable(item.variable_id).validate_value(item.proposed_value)
            if item.semantic_state == SemanticState.ABSTAIN and not (
                {"insufficient_evidence", "policy", "unsupported_input"}
                & set(item.uncertainty_flags)
            ):
                raise ValueError("Abstention requires an explicit reason code")
    except ProviderFailure as exc:
        error = TechnicalError(code=exc.code, retryable=exc.code in ("timeout", "unavailable"))
        retries, errors = exc.retry_count, exc.errors
    except (ValueError, KeyError, ValidationError):
        error = TechnicalError(code="invalid_response")
    except ModelError:
        error = TechnicalError(code="unavailable", retryable=True)
    except Exception:
        error = TechnicalError(code="internal_error")
    if error:
        payload = VerificationPayload(variables=())
        errors = (*errors, error.code)
    assert requested.extractor is not None
    effective = requested
    record = None
    if response is not None:
        binding = requested.extractor.model_copy(update={"model": response.model})
        effective = requested.model_copy(update={"extractor": binding})
        limitations: list[
            Literal["exact_reproducibility_not_guaranteed", "model_version_unavailable"]
        ] = []
        if not model.capabilities.exact_reproducibility:
            limitations.append("exact_reproducibility_not_guaranteed")
        if response.model.model_version is None:
            limitations.append("model_version_unavailable")
        record = ModelRunRecord(
            role="extractor",
            binding=binding,
            capabilities=model.capabilities,
            effective_parameters=response.effective_parameters,
            limitations=tuple(limitations),
        )
    proposals = {v.variable_id: v for v in payload.variables}
    results, states = [], {}
    for definition in dictionary.variables:
        key = definition.variable_id
        proposal = proposals.get(key)
        items = proposal.evidence if proposal else ()
        findings = (
            [
                ValidationFinding(code=code, severity="warning")
                for code in evidence_findings(document, items)
            ]
            if proposal
            else []
        )
        abstention = None
        if proposal:
            states[key] = proposal.semantic_state
            findings.extend(
                ValidationFinding(code="uncertainty:" + code, severity="warning")
                for code in proposal.uncertainty_flags
            )
            if proposal.requires_human_review:
                findings.append(
                    ValidationFinding(code="human_review_requested", severity="warning")
                )
            if proposal.semantic_state == SemanticState.ABSTAIN:
                reason = next(
                    code
                    for code in ("policy", "unsupported_input", "insufficient_evidence")
                    if code in proposal.uncertainty_flags
                )
                abstention = Abstention.model_validate({"reason": reason})
        result = ExtractionResult(
            result_id=run_id + "/" + key,
            trace=ResultTrace(
                document_id=document.document_id,
                variable_id=key,
                dictionary=dictionary.artifact,
                config=ConfigRef.from_config(effective),
                execution_id=run_id,
                output_schema=result_schema,
                model=effective.extractor.model if response and effective.extractor else None,
                instructions=effective.extractor_instructions if response else None,
                request_id=request.request_id if response else None,
                provider_request_id=response.provider_request_id if response else None,
            ),
            operation=OperationStatus.FAILED if error else OperationStatus.COMPLETED,
            value=proposal.proposed_value if proposal else None,
            evidence=EvidenceAssessment(
                availability=EvidenceAvailability.AVAILABLE
                if items
                else (EvidenceAvailability.NOT_ASSESSED if error else EvidenceAvailability.ABSENT),
                sufficiency=EvidenceSufficiency.NOT_ASSESSED
                if error
                else EvidenceSufficiency.UNDETERMINED,
                items=items,
            ),
            abstention=abstention,
            technical_error=error,
            findings=tuple(findings),
        )
        result.validate_against(dictionary)
        result.trace.validate_config(effective)
        results.append(result)
    snapshot = ExtractionSnapshot(
        base_extraction_id=run_id,
        document_id=document.document_id,
        dictionary=dictionary.artifact,
        results=tuple(results),
        semantic_states=states,
        auxiliary={
            "document_hash": content_hash(document),
            "proposal_details": payload.model_dump(mode="json"),
            "postprocessing": mapper_ref.model_dump(mode="json"),
        },
    )
    execution = ExtractionExecution(
        input_hash=input_hash,
        document_hash=content_hash(document),
        extraction_a=snapshot,
        configured_settings=settings,
        requested_configuration=requested,
        effective_configuration=effective,
        model_record=record,
        response_schema=schema_ref,
        postprocessing=mapper_ref,
        mode=mode,
        audit=CallAudit(
            requested_model=model.identity.model_id,
            requested_parameters=parameters,
            response=response,
            error=error,
            elapsed_seconds=perf_counter() - started,
            retry_count=retries,
            errors=errors,
        ),
    )
    store.put("execution", execution)
    store.put("extraction_a", snapshot)
    store.put(
        "manifest",
        ExtractionManifest(input_hash=input_hash, artifact_hashes=store.artifact_hashes()),
    )
    return execution
