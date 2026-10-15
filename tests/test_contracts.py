import json
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from extracteval.core.base import ArtifactRef
from extracteval.core.documents import Document, Evidence, EvidenceAssessment
from extracteval.core.reference import AdjudicatedReference, ExpertAnnotation
from extracteval.core.results import Abstention, ExtractionResult, ResultTrace, TechnicalError
from extracteval.core.specification import (
    SEMANTIC_VALUE_ADAPTER,
    BooleanValue,
    CategoryValue,
    DateValue,
    NumberValue,
    OperationalDictionary,
    TextValue,
)


def result(trace, evidence, **kwargs):
    return ExtractionResult(
        result_id="r-1", trace=trace, operation="completed", evidence=evidence, **kwargs
    )


def annotation(trace, evidence, **kwargs):
    data = dict(
        annotation_id="a-1",
        document_id=trace.document_id,
        variable_id=trace.variable_id,
        dictionary=trace.dictionary,
        evaluator_id="expert-1",
        partition="evaluation",
        blinded_to_system_output=True,
        status="evaluable",
        value=CategoryValue(value="yes"),
        evidence=evidence,
    )
    data.update(kwargs)
    return ExpertAnnotation(**data)


def test_indeterminate_is_a_successful_semantic_category(trace, absent_evidence, dictionary):
    outcome = result(trace, absent_evidence, value=CategoryValue(value="indeterminado"))
    outcome.validate_against(dictionary)
    assert outcome.operation.value == "completed"
    assert outcome.abstention is None
    assert outcome.technical_error is None
    assert ExtractionResult.model_validate_json(outcome.model_dump_json()) == outcome
    assert ExtractionResult.model_validate(outcome.model_dump()) == outcome


def test_absence_abstention_and_failure_are_distinct(trace, absent_evidence):
    absence = result(trace, absent_evidence)
    abstained = result(trace, absent_evidence, abstention=Abstention(reason="policy"))
    failed = ExtractionResult(
        result_id="failure",
        trace=trace,
        operation="failed",
        evidence=absent_evidence,
        technical_error=TechnicalError(code="timeout", retryable=True),
    )
    assert absence.value is None and absence.abstention is None
    assert abstained.abstention is not None and abstained.technical_error is None
    assert failed.technical_error is not None and failed.abstention is None
    for outcome in [absence, abstained, failed]:
        assert ExtractionResult.model_validate_json(outcome.model_dump_json()) == outcome


@pytest.mark.parametrize(
    "changes",
    [
        {"operation": "failed"},
        {
            "operation": "failed",
            "technical_error": {"code": "timeout"},
            "value": {"kind": "boolean", "value": False},
        },
        {"technical_error": {"code": "internal_error"}},
        {"abstention": {"reason": "policy"}, "value": {"kind": "text", "value": "x"}},
    ],
)
def test_incoherent_operational_outcomes_rejected(trace, absent_evidence, changes):
    data = dict(result_id="r", trace=trace, operation="completed", evidence=absent_evidence)
    data.update(changes)
    with pytest.raises(ValidationError):
        ExtractionResult(**data)


def test_dictionary_domain_and_identity_checks(trace, absent_evidence, dictionary):
    with pytest.raises(ValueError, match="outside"):
        result(trace, absent_evidence, value=CategoryValue(value="unknown")).validate_against(
            dictionary
        )
    with pytest.raises(ValueError, match="type"):
        result(trace, absent_evidence, value=BooleanValue(value=False)).validate_against(dictionary)
    bad = trace.model_dump()
    bad["dictionary"]["version"] = "2"
    with pytest.raises(ValueError, match="reference"):
        result(ResultTrace.model_validate(bad), absent_evidence).validate_against(dictionary)
    bad = trace.model_dump()
    bad["variable_id"] = "unknown"
    with pytest.raises(KeyError):
        result(ResultTrace.model_validate(bad), absent_evidence).validate_against(dictionary)


@pytest.mark.parametrize(
    "value",
    [
        CategoryValue(value="indeterminado"),
        BooleanValue(value=False),
        NumberValue(value=0),
        NumberValue(value=1.25),
        DateValue(value=date(2026, 10, 15)),
        TextValue(value="synthetic"),
    ],
)
def test_all_semantic_types_roundtrip_and_match_definition(dictionary, value):
    recovered = SEMANTIC_VALUE_ADAPTER.validate_json(SEMANTIC_VALUE_ADAPTER.dump_json(value))
    assert recovered == value
    data = dictionary.variables[0].model_dump()
    data.update(
        data_type=value.kind, categories=("indeterminado",) if value.kind == "categorical" else ()
    )
    definition = type(dictionary.variables[0]).model_validate(data)
    definition.validate_value(recovered)


@pytest.mark.parametrize(
    "factory,value",
    [
        (BooleanValue, "false"),
        (BooleanValue, 0),
        (NumberValue, True),
        (NumberValue, "1.2"),
        (NumberValue, float("nan")),
        (NumberValue, float("inf")),
        (TextValue, 1),
        (DateValue, datetime(2026, 1, 1)),
        (DateValue, "2026-01-01"),
    ],
)
def test_semantic_types_do_not_silently_coerce(factory, value):
    with pytest.raises(ValidationError):
        factory(value=value)


def test_dictionary_invalid_and_roundtrip(dictionary):
    assert OperationalDictionary.model_validate_json(dictionary.model_dump_json()) == dictionary
    data = dictionary.model_dump()
    data["variables"] *= 2
    with pytest.raises(ValidationError):
        OperationalDictionary.model_validate(data)
    data = dictionary.model_dump()
    data["variables"][0]["categories"] = ["yes", "yes"]
    with pytest.raises(ValidationError):
        OperationalDictionary.model_validate(data)
    data["variables"][0]["data_type"] = "boolean"
    with pytest.raises(ValidationError):
        OperationalDictionary.model_validate(data)


def test_document_content_source_and_redacted_repr():
    document = Document(document_id="doc", text="SYNTHETIC_PRIVATE_TEXT")
    assert "SYNTHETIC_PRIVATE_TEXT" not in repr(document)
    assert Document.model_validate_json(document.model_dump_json()) == document
    assert Document(document_id="doc", text_ref="secure:doc").text is None
    for fields in [{}, {"text": "synthetic", "text_ref": "secure:doc"}]:
        with pytest.raises(ValidationError):
            Document(document_id="doc", **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"availability": "available", "sufficiency": "sufficient"},
        {"availability": "absent", "sufficiency": "sufficient"},
        {"availability": "not_assessed", "sufficiency": "insufficient"},
        {
            "availability": "absent",
            "sufficiency": "insufficient",
            "items": [{"document_id": "doc", "quote": "synthetic"}],
        },
    ],
)
def test_evidence_assessment_consistency(fields):
    with pytest.raises(ValidationError):
        EvidenceAssessment(**fields)


def test_evidence_location_and_document_link(trace, absent_evidence):
    for fields in [{}, {"quote": "x", "start": 0}, {"quote": "x", "start": 2, "end": 1}]:
        with pytest.raises(ValidationError):
            Evidence(document_id="doc", **fields)
    evidence = EvidenceAssessment(
        availability="available",
        sufficiency="sufficient",
        items=(Evidence(document_id="another-document", quote="synthetic", start=0, end=9),),
    )
    with pytest.raises(ValidationError, match="document"):
        result(trace, evidence)


def test_expert_reference_roundtrip_without_model(trace, absent_evidence, dictionary):
    first = annotation(trace, absent_evidence)
    second = annotation(
        trace,
        absent_evidence,
        annotation_id="a-2",
        evaluator_id="expert-2",
        value=CategoryValue(value="no"),
    )
    first.validate_against(dictionary)
    ref = AdjudicatedReference(
        reference_id="ref",
        annotations=(first, second),
        adjudicator_id="expert-3",
        disagreement=True,
        status="final",
        value=CategoryValue(value="yes"),
        evidence=absent_evidence,
    )
    ref.validate_against(dictionary)
    assert ExpertAnnotation.model_validate_json(first.model_dump_json()) == first
    assert AdjudicatedReference.model_validate_json(ref.model_dump_json()) == ref
    assert AdjudicatedReference.model_validate(json.loads(ref.model_dump_json())) == ref
    assert trace.model is None


@pytest.mark.parametrize(
    "changes",
    [
        {"partition": "calibration"},
        {"evaluator_id": "expert-1"},
        {"document_id": "different"},
        {"annotation_id": "a-1"},
    ],
)
def test_adjudication_rejects_mixed_sources(trace, absent_evidence, changes):
    first = annotation(trace, absent_evidence)
    kwargs = dict(annotation_id="a-2", evaluator_id="expert-2")
    kwargs.update(changes)
    second = annotation(trace, absent_evidence, **kwargs)
    with pytest.raises(ValidationError):
        AdjudicatedReference(
            reference_id="ref",
            annotations=(first, second),
            adjudicator_id="expert-3",
            disagreement=False,
            status="final",
            value=CategoryValue(value="yes"),
            evidence=absent_evidence,
        )


def test_annotation_states_and_missing_reference(trace, absent_evidence):
    for fields in [dict(status="evaluable", value=None), dict(status="not_evaluable")]:
        with pytest.raises(ValidationError):
            annotation(trace, absent_evidence, **fields)
    non_evaluable = annotation(trace, absent_evidence, status="not_evaluable", value=None)
    assert non_evaluable.value is None
    # Extraction does not require or manufacture an expert reference.
    assert result(trace, absent_evidence).trace.document_id == "doc-1"


def test_model_provenance_requires_internal_request_and_instructions(trace):
    data = trace.model_dump()
    data["provider_request_id"] = "external-request"
    with pytest.raises(ValidationError):
        ResultTrace.model_validate(data)
    data["model"] = dict(engine="mock", model_id="constant", model_version="1")
    with pytest.raises(ValidationError):
        ResultTrace.model_validate(data)
    data["instructions"] = trace.dictionary.model_dump()
    data["request_id"] = "internal-request"
    completed = ResultTrace.model_validate(data)
    assert completed.execution_id != completed.provider_request_id
    assert completed.request_id != completed.provider_request_id


def test_validation_error_strings_hide_input():
    with pytest.raises(ValidationError) as error:
        ArtifactRef(artifact_id="sensitive text with spaces", version="1", sha256="a" * 64)
    assert "sensitive text with spaces" not in str(error.value)
    assert "sensitive text with spaces" not in str(error.value.errors(include_input=False))
