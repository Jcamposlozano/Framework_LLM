"""Offline example: interchangeable models and independently serializable contracts."""

from datetime import UTC, datetime

from extracteval import __version__
from extracteval.adapters.models.mock import ConstantModel, ScriptedModel
from extracteval.core.base import ArtifactRef
from extracteval.core.documents import (
    Document,
    Evidence,
    EvidenceAssessment,
    EvidenceAvailability,
    EvidenceSufficiency,
)
from extracteval.core.experiments import ConfigRef, ExperimentConfig, ModelBinding, RunManifest
from extracteval.core.models import ModelRequest, ModelResponse
from extracteval.core.ports import ModelPort
from extracteval.core.reference import ExpertAnnotation
from extracteval.core.results import ExtractionResult, OperationStatus, ResultTrace
from extracteval.core.specification import (
    CategoryValue,
    InformationPolicy,
    OperationalDictionary,
    VariableDefinition,
)


def consume(model: ModelPort, request: ModelRequest) -> ModelResponse:
    return model.generate(request)


def main() -> None:
    # Placeholder hashes identify synthetic fixtures; no files are read or written.
    dictionary_ref = ArtifactRef(artifact_id="dictionary", version="1", sha256="a" * 64)
    schema_ref = ArtifactRef(artifact_id="schema", version="1", sha256="b" * 64)
    instructions_ref = ArtifactRef(artifact_id="instructions", version="1", sha256="c" * 64)
    dictionary = OperationalDictionary(
        artifact=dictionary_ref,
        variables=(
            VariableDefinition(
                variable_id="decision",
                version="1",
                data_type="categorical",
                categories=("yes", "no", "indeterminado"),
                operational_definition="Decision explicitly documented in a synthetic notice",
                correctness_criteria=("Exact semantic category match",),
                information_policy=InformationPolicy(
                    absent="No value",
                    indeterminate="Use indeterminado",
                    not_applicable="No value",
                ),
            ),
        ),
    )
    document = Document(document_id="doc-1", entity_id="entity-1", text="Decision: yes.")
    request = ModelRequest(
        execution_id="run-1",
        request_id="request-1",
        instructions="Return the documented decision",
        content=document.text or "",
    )
    first: ModelPort = ConstantModel("yes")
    second: ModelPort = ScriptedModel(["yes"])
    response = consume(first, request)
    assert response.text == consume(second, request).text
    config = ExperimentConfig(
        config_id="example",
        version="1",
        dictionary=dictionary_ref,
        output_schema=schema_ref,
        extractor_instructions=instructions_ref,
        extractor=ModelBinding(adapter_id="constant", model=first.identity),
    )
    evidence = EvidenceAssessment(
        availability=EvidenceAvailability.AVAILABLE,
        sufficiency=EvidenceSufficiency.SUFFICIENT,
        items=(Evidence(document_id=document.document_id, quote="Decision: yes."),),
    )
    outcome = ExtractionResult(
        result_id="result-1",
        operation=OperationStatus.COMPLETED,
        value=CategoryValue(value=response.text),
        evidence=evidence,
        trace=ResultTrace(
            document_id=document.document_id,
            variable_id="decision",
            dictionary=dictionary_ref,
            config=ConfigRef.from_config(config),
            execution_id=request.execution_id,
            output_schema=schema_ref,
            model=response.model,
            instructions=instructions_ref,
            request_id=response.request_id,
            provider_request_id=response.provider_request_id,
        ),
    )
    outcome.validate_against(dictionary)
    outcome.trace.validate_config(config)
    annotation = ExpertAnnotation(
        annotation_id="annotation-1",
        document_id=document.document_id,
        variable_id="decision",
        evaluator_id="expert-1",
        dictionary=dictionary_ref,
        partition="evaluation",
        blinded_to_system_output=True,
        status="evaluable",
        value=CategoryValue(value="yes"),
        evidence=evidence,
    )
    annotation.validate_against(dictionary)
    for obj in (outcome, annotation):
        assert type(obj).model_validate_json(obj.model_dump_json()) == obj
    manifest = RunManifest(
        execution_id=request.execution_id,
        config=ConfigRef.from_config(config),
        package_version=__version__,
        started_at=datetime.now(UTC),
    )
    manifest.validate_against(config)
    print("Two interchangeable models; extraction and expert annotation JSON round-trips OK.")


if __name__ == "__main__":
    main()
