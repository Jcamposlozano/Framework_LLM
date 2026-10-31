"""Synthetic phase 2 behavior, policy enforcement and durable blind reading."""

import inspect
import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from extracteval.adapters.models.verification_mock import MockVerifierModel
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.comparison import compare_extractions
from extracteval.application.configuration import load_configuration
from extracteval.application.pipeline import run_verification
from extracteval.application.reconciliation import reconcile
from extracteval.application.verification import IndependentVerifier, evidence_findings
from extracteval.core.documents import Document, DocumentSection, Evidence, EvidenceAssessment
from extracteval.core.exceptions import ProviderFailure
from extracteval.core.hashing import content_hash
from extracteval.core.results import OperationStatus, TechnicalError
from extracteval.core.specification import (
    CategoryValue,
    DateValue,
    DocumentaryReviewRule,
    NormalizationRule,
    OperationalDictionary,
)
from extracteval.core.verification import (
    ExtractionSnapshot,
    ReconciledExtraction,
    ReconciliationPolicy,
    ReplacementRule,
    SemanticState,
    VariableVerification,
    VerificationInput,
    VerificationPayload,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup_phase2():
    _, dictionary, policy, config = load_configuration(
        ROOT / "configs/epoc/phase2.json", {}, "mock"
    )
    inputs = VerificationInput.model_validate_json(
        (ROOT / "examples/phase2/input.json").read_bytes()
    )
    payload = VerificationPayload.model_validate_json(
        (ROOT / "examples/phase2/mock_verification.json").read_bytes()
    )
    return dictionary, policy, config, inputs, payload


def run_case(setup_phase2, payload=None, document=None):
    dictionary, policy, config, inputs, fixture = setup_phase2
    model = MockVerifierModel([fixture if payload is None else payload])
    verifier = IndependentVerifier(model)
    verification = verifier.verify_independently(document or inputs.document, dictionary, config)
    return verification, model


@pytest.mark.parametrize(
    ("text", "key", "value", "state", "flags"),
    [
        (
            "Exacerbación actual explícita.",
            "exacerbacion_actual",
            CategoryValue(value="true"),
            "value",
            (),
        ),
        (
            "Antecedente de exacerbación documentado.",
            "exacerbacion_previa",
            CategoryValue(value="true"),
            "value",
            (),
        ),
        (
            "Niega exacerbaciones actuales.",
            "exacerbacion_actual",
            CategoryValue(value="false"),
            "documented_absence",
            (),
        ),
        (
            "Tos crónica sin evidencia suficiente de exacerbación.",
            "estado_paciente",
            CategoryValue(value="sintomatico"),
            "value",
            ("insufficient_evidence",),
        ),
        (
            "Inicio del episodio el 2026-10-01.",
            "fecha_indice_evento",
            DateValue(value=date(2026, 10, 1)),
            "value",
            (),
        ),
        (
            "Inicio hace varias semanas.",
            "fecha_indice_evento",
            None,
            "indeterminate",
            ("ambiguous_date",),
        ),
        (
            "Consulta 2026-10-19, sin fecha de inicio.",
            "fecha_indice_evento",
            None,
            "indeterminate",
            ("onset_inference_not_authorized",),
        ),
        (
            "ANÁLISIS: estable. SUBJETIVO: refiere episodio agudo.",
            "estado_paciente",
            CategoryValue(value="indeterminado"),
            "indeterminate",
            ("contradictory_sections",),
        ),
    ],
)
def test_synthetic_document_scenarios(setup_phase2, text, key, value, state, flags):
    # Scripted proposals test the flow, not a fake demonstration of clinical accuracy.
    dictionary, policy, config, inputs, _ = setup_phase2
    document = Document(
        document_id=inputs.document.document_id,
        text=text,
        sections=(DocumentSection(name="analisis", start=0, end=len(text)),),
    )
    evidence = Evidence(
        document_id=document.document_id, quote=text, section="analisis", start=0, end=len(text)
    )
    proposal = VariableVerification(
        variable_id=key,
        proposed_value=value,
        semantic_state=state,
        evidence=(evidence,),
        evidence_type="literal",
        uncertainty_flags=flags,
        requires_human_review=bool(flags),
    )
    payload = VerificationPayload(variables=(proposal,))
    verification, _ = run_case(setup_phase2, payload, document)
    assert verification.audit.error is None
    assert verification.payload.variables[0] == proposal
    assert verification.evidence_findings[key] == ()
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, document)
    final = reconcile(document, inputs.extraction_a, verification, comparison, policy, dictionary)
    assert all(d.action != "REPLACE_WITH_VERIFIED" for d in final.decisions)
    assert not final.clinically_validated
    if key == "fecha_indice_evento" and value is None:
        assert next(d for d in final.decisions if d.variable_id == key).resulting_value is None


def test_independent_interface_and_metadata_isolation(setup_phase2):
    dictionary, _, config, inputs, payload = setup_phase2
    document = inputs.document.model_copy(
        update={
            "provenance": {"a_prediction": "SECRET_A"},
            "entity_id": "SECRET_ENTITY",
            "allowed_context": {"expert_label": "SECRET_LABEL", "locale": "es"},
        }
    )
    config = config.model_copy(update={"allowed_metadata_keys": ("locale",)})
    model = MockVerifierModel([payload])
    verification = IndependentVerifier(model).verify_independently(document, dictionary, config)
    request = model.requests[0]
    assert list(inspect.signature(IndependentVerifier.verify_independently).parameters) == [
        "self",
        "document",
        "dictionary",
        "verifier_config",
    ]
    assert not any(
        secret in request.content for secret in ["SECRET_A", "SECRET_ENTITY", "SECRET_LABEL"]
    )
    assert json.loads(request.content)["document"]["allowed_context"] == {"locale": "es"}
    assert not any(
        key in type(request).model_fields for key in ["extraction_a", "reference", "reconciled"]
    )
    assert verification.audit.requested_parameters == config.parameters


def test_evidence_literal_offsets_and_sections(setup_phase2):
    document = setup_phase2[3].document
    good = setup_phase2[4].variables[1].evidence[0]
    assert evidence_findings(document, (good,)) == ()
    bad = good.model_copy(update={"quote": "Una cita que no existe.", "start": None, "end": None})
    assert "evidence_quote_not_found" in evidence_findings(document, (bad,))
    assert "evidence_offset_mismatch" in evidence_findings(
        document, (good.model_copy(update={"start": 1, "end": 2}),)
    )
    assert "evidence_section_unverifiable" in evidence_findings(
        document, (good.model_copy(update={"section": "otra"}),)
    )
    assert "evidence_wrong_document" in evidence_findings(
        document, (good.model_copy(update={"document_id": "other"}),)
    )


def test_difference_and_agreement_without_evidence(setup_phase2):
    dictionary, policy, _, inputs, payload = setup_phase2
    verification, _ = run_case(setup_phase2)
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    assert comparison.variables[1].relation == "value_difference"
    assert comparison.variables[0].relation == "exact_match"
    assert "verifier:evidence_missing" in comparison.variables[0].findings
    final = reconcile(
        inputs.document, inputs.extraction_a, verification, comparison, policy, dictionary
    )
    assert all(d.requires_human_review for d in final.decisions)
    assert all(d.resulting_value == d.previous_value for d in final.decisions)


@pytest.mark.parametrize(
    "payload",
    [
        ProviderFailure("timeout", retry_count=2),
        "{invalid-json",
        "{}",
        '{"variables":[{"variable_id":"unknown"}]}',
    ],
)
def test_provider_and_schema_errors_are_not_clinical_values(setup_phase2, payload):
    dictionary, policy, _, inputs, _ = setup_phase2
    verification, _ = run_case(setup_phase2, payload)
    assert verification.audit.error is not None
    assert verification.payload.variables == ()
    assert verification.audit.error.code in ("timeout", "invalid_response")
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    assert {v.relation for v in comparison.variables} == {"technical_error"}
    final = reconcile(
        inputs.document, inputs.extraction_a, verification, comparison, policy, dictionary
    )
    assert {d.reason for d in final.decisions} == {"technical_failure"}
    assert all(d.resulting_value == d.previous_value for d in final.decisions)


def test_deterministic_comparison_and_a_immutability(setup_phase2):
    dictionary, policy, _, inputs, _ = setup_phase2
    before = inputs.extraction_a.model_dump_json()
    verification, _ = run_case(setup_phase2)
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    assert comparison == compare_extractions(
        inputs.extraction_a, verification, dictionary, inputs.document
    )
    final = reconcile(
        inputs.document, inputs.extraction_a, verification, comparison, policy, dictionary
    )
    assert inputs.extraction_a.model_dump_json() == before
    assert final.base_extraction_hash == content_hash(inputs.extraction_a)
    assert final.base_extraction_id == inputs.extraction_a.base_extraction_id
    assert final.auxiliary == inputs.extraction_a.auxiliary
    final.auxiliary["new"] = "isolated"
    assert "new" not in inputs.extraction_a.auxiliary


def test_keep_a_with_literal_support_is_not_expert_validation(setup_phase2):
    dictionary, policy, _, inputs, payload = setup_phase2
    proposal = payload.variables[1]
    old = inputs.extraction_a.results[1]
    result = old.model_copy(
        update={
            "value": proposal.proposed_value,
            "evidence": EvidenceAssessment(
                availability="available", sufficiency="undetermined", items=proposal.evidence
            ),
        }
    )
    original = inputs.extraction_a.model_copy(
        update={
            "results": (inputs.extraction_a.results[0], result, *inputs.extraction_a.results[2:])
        }
    )
    verification, _ = run_case(setup_phase2)
    comparison = compare_extractions(original, verification, dictionary, inputs.document)
    final = reconcile(inputs.document, original, verification, comparison, policy, dictionary)
    assert final.decisions[1].action == "KEEP_A"
    assert final.expert_reference_status == "not_provided"
    assert final.clinically_validated is False


def replacement_policy(proposal, *, approved=True):
    return ReconciliationPolicy(
        policy_id="test-policy",
        version="1",
        replacement_rules=(
            ReplacementRule(
                rule_id="authorized-quote",
                approved=approved,
                variable_id=proposal.variable_id,
                proposed_value=proposal.proposed_value,
                literal_evidence_sufficient=True,
                required_evidence_quotes=(proposal.evidence[0].quote,),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("approved_dictionary", "approved_rule", "expected"),
    [
        (False, True, "HUMAN_REVIEW"),
        (True, False, "HUMAN_REVIEW"),
        (True, True, "REPLACE_WITH_VERIFIED"),
    ],
)
def test_replacement_requires_both_approvals(
    setup_phase2, approved_dictionary, approved_rule, expected
):
    dictionary, _, _, inputs, payload = setup_phase2
    dictionary = dictionary.model_copy(update={"clinically_approved": approved_dictionary})
    verification, _ = run_case((dictionary, *setup_phase2[1:]))
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    final = reconcile(
        inputs.document,
        inputs.extraction_a,
        verification,
        comparison,
        replacement_policy(payload.variables[1], approved=approved_rule),
        dictionary,
    )
    assert final.decisions[1].action == expected
    assert final.decisions[1].previous_value.value == "false"
    assert final.decisions[1].resulting_value.value == (
        "true" if expected == "REPLACE_WITH_VERIFIED" else "false"
    )


def test_fabricated_evidence_blocks_even_authorized_replacement(setup_phase2):
    dictionary, _, config, inputs, payload = setup_phase2
    dictionary = dictionary.model_copy(update={"clinically_approved": True})
    proposal = payload.variables[1]
    forged = proposal.model_copy(
        update={
            "evidence": (
                proposal.evidence[0].model_copy(
                    update={"quote": "Inventada", "start": None, "end": None}
                ),
            )
        }
    )
    changed = payload.model_copy(
        update={"variables": (payload.variables[0], forged, *payload.variables[2:])}
    )
    verification, _ = run_case((dictionary, None, config, inputs, changed))
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    final = reconcile(
        inputs.document,
        inputs.extraction_a,
        verification,
        comparison,
        replacement_policy(forged),
        dictionary,
    )
    assert final.decisions[1].action == "HUMAN_REVIEW"


@pytest.mark.parametrize("action", ["KEEP_A", "ABSTAIN", "HUMAN_REVIEW"])
def test_unresolved_policy_actions(setup_phase2, action):
    dictionary, _, _, inputs, _ = setup_phase2
    dictionary = dictionary.model_copy(update={"clinically_approved": True})
    verification, _ = run_case((dictionary, *setup_phase2[1:]))
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    final = reconcile(
        inputs.document,
        inputs.extraction_a,
        verification,
        comparison,
        ReconciliationPolicy(policy_id="p", version="1", unresolved_action=action),
        dictionary,
    )
    assert final.decisions[1].action == action
    if action == "ABSTAIN":
        assert final.decisions[1].resulting_state == SemanticState.ABSTAIN
        assert final.decisions[1].resulting_value is None


def test_normalization_is_only_dictionary_authorized(setup_phase2):
    dictionary, _, _, inputs, payload = setup_phase2
    variable = dictionary.variables[1].model_copy(
        update={"categories": ("true", "false", "TRUE"), "normalization_rules": ("case",)}
    )
    dictionary = OperationalDictionary.model_validate(
        dictionary.model_dump()
        | {
            "clinically_approved": True,
            "variables": (dictionary.variables[0], variable, *dictionary.variables[2:]),
            "normalization": (
                NormalizationRule(rule_id="case", approved=True, operation="casefold"),
            ),
        }
    )
    old = inputs.extraction_a.results[1].model_copy(update={"value": CategoryValue(value="TRUE")})
    original = inputs.extraction_a.model_copy(
        update={"results": (inputs.extraction_a.results[0], old, *inputs.extraction_a.results[2:])}
    )
    verification, _ = run_case((dictionary, *setup_phase2[1:]))
    comparison = compare_extractions(original, verification, dictionary, inputs.document)
    assert comparison.variables[1].relation == "normalization_difference"
    assert comparison.variables[1].normalization_rule_ids == ("case",)
    pending = dictionary.model_copy(update={"clinically_approved": False})
    assert (
        compare_extractions(original, verification, pending, inputs.document).variables[1].relation
        == "value_difference"
    )


def test_external_consistency_rule_is_review_only(setup_phase2):
    dictionary, policy, _, inputs, payload = setup_phase2
    dictionary = dictionary.model_copy(
        update={
            "review_rules": (
                DocumentaryReviewRule(
                    rule_id="synthetic",
                    when={"exacerbacion_actual": CategoryValue(value="true")},
                    expected={"estado_paciente": CategoryValue(value="exacerbacion_activa")},
                ),
            )
        }
    )
    verification, _ = run_case((dictionary, *setup_phase2[1:]))
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    assert "verifier:potential_inconsistency:synthetic" in comparison.variables[0].findings
    final = reconcile(
        inputs.document, inputs.extraction_a, verification, comparison, policy, dictionary
    )
    assert final.decisions[0].requires_human_review


def test_persist_before_comparison_and_resume(setup_phase2, tmp_path):
    dictionary, policy, config, inputs, payload = setup_phase2

    class RecordingStore(JSONRunStore):
        writes = []

        def put(self, name, value):
            self.writes.append(name)
            super().put(name, value)

    store = RecordingStore(tmp_path / "run")
    model = MockVerifierModel([payload])
    verifier = IndependentVerifier(model)
    independent = run_verification(
        inputs, dictionary, policy, config, store, verifier, stage="independent"
    )
    assert not store.exists("comparison")
    run_verification(inputs, dictionary, policy, config, store, None, stage="compare")
    manifest = run_verification(inputs, dictionary, policy, config, store, None, stage="reconcile")
    assert store.writes.index("verification") < store.writes.index("comparison")
    assert len(model.requests) == 1
    before = {p.name: p.read_bytes() for p in store.root.glob("*.json")}
    assert run_verification(inputs, dictionary, policy, config, store, None) == manifest
    assert before == {p.name: p.read_bytes() for p in store.root.glob("*.json")}
    assert manifest.base_extraction_hash == independent.base_extraction_hash
    assert store.get("extraction_b", ReconciledExtraction).base_extraction_hash == content_hash(
        inputs.extraction_a
    )
    assert store.get("extraction_a", ExtractionSnapshot) == inputs.extraction_a


def test_independent_can_be_run_before_a_exists(setup_phase2, tmp_path):
    dictionary, policy, config, inputs, payload = setup_phase2
    store = JSONRunStore(tmp_path / "run")
    first = run_verification(
        inputs.model_copy(update={"extraction_a": None}),
        dictionary,
        policy,
        config,
        store,
        IndependentVerifier(MockVerifierModel([payload])),
        stage="independent",
    )
    assert first.base_extraction_id is None
    final = run_verification(inputs, dictionary, policy, config, store, None, stage="all")
    assert final.base_extraction_id == inputs.extraction_a.base_extraction_id
    assert final.run_id == first.run_id


def test_resume_rejects_tampering_and_changed_config(setup_phase2, tmp_path):
    dictionary, policy, config, inputs, payload = setup_phase2
    store = JSONRunStore(tmp_path / "run")
    run_verification(
        inputs,
        dictionary,
        policy,
        config,
        store,
        IndependentVerifier(MockVerifierModel([payload])),
        stage="independent",
    )
    with pytest.raises(ValueError):
        run_verification(
            inputs, dictionary, policy, config.model_copy(update={"prompt": "changed"}), store, None
        )
    path = store.root / "verification.json"
    raw = json.loads(path.read_bytes())
    raw["payload"]["variables"][1]["proposed_value"]["value"] = "false"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="integrity"):
        run_verification(inputs, dictionary, policy, config, store, None)
    assert not store.exists("comparison")


def test_interrupted_verifier_is_never_silently_called_again(setup_phase2, tmp_path):
    dictionary, policy, config, inputs, payload = setup_phase2
    store = JSONRunStore(tmp_path / "interrupted")

    class InterruptedModel(MockVerifierModel):
        def generate(self, request):
            super().generate(request)
            raise KeyboardInterrupt("simulated process termination after transmission")

    model = InterruptedModel([payload])
    with pytest.raises(KeyboardInterrupt):
        run_verification(inputs, dictionary, policy, config, store, IndependentVerifier(model))
    assert store.exists("verification-request") and not store.exists("verification")
    with pytest.raises(ValueError, match="Interrupted verification"):
        run_verification(inputs, dictionary, policy, config, store, IndependentVerifier(model))
    assert len(model.requests) == 1
    assert not store.exists("comparison")


def test_completed_verifier_survives_interruption_before_comparison(
    setup_phase2, tmp_path, monkeypatch
):
    dictionary, policy, config, inputs, payload = setup_phase2
    store = JSONRunStore(tmp_path / "saved-v")
    model = MockVerifierModel([payload])
    original = IndependentVerifier.verify_independently

    def interrupted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise KeyboardInterrupt("simulated interruption after durable verification")

    monkeypatch.setattr(IndependentVerifier, "verify_independently", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_verification(inputs, dictionary, policy, config, store, IndependentVerifier(model))
    assert store.exists("verification") and not store.exists("comparison")
    manifest = run_verification(inputs, dictionary, policy, config, store, None)
    assert manifest.status == "completed" and len(model.requests) == 1


def test_reconcile_rejects_stale_comparison(setup_phase2):
    dictionary, policy, _, inputs, _ = setup_phase2
    verification, _ = run_case(setup_phase2)
    comparison = compare_extractions(inputs.extraction_a, verification, dictionary, inputs.document)
    with pytest.raises(ValueError, match="Comparison"):
        reconcile(
            inputs.document,
            inputs.extraction_a,
            verification,
            comparison.model_copy(update={"base_extraction_hash": "0" * 64}),
            policy,
            dictionary,
        )


def test_document_sections_and_value_states_validate(setup_phase2):
    with pytest.raises(ValidationError):
        Document(
            document_id="d", text="short", sections=(DocumentSection(name="s", start=0, end=100),)
        )
    with pytest.raises(ValidationError):
        VariableVerification(
            variable_id="v",
            proposed_value=CategoryValue(value="x"),
            semantic_state="abstain",
            evidence_type="none",
        )
    # Semantic categories, abstention, missing answers and absent expert references are distinct.
    for state in [
        "indeterminate",
        "documented_absence",
        "not_applicable",
        "abstain",
        "no_response",
    ]:
        proposal = VariableVerification(variable_id="v", semantic_state=state, evidence_type="none")
        assert proposal.semantic_state.value == state


def test_storage_no_overwrites_or_traversal(setup_phase2, tmp_path):
    store = JSONRunStore(tmp_path / "run")
    inputs = setup_phase2[3]
    store.put("document", inputs.document)
    with pytest.raises(ValueError):
        store.put("document", inputs.document.model_copy(update={"text": "changed"}))
    with pytest.raises(ValueError):
        store.exists("../secret")
    assert (store.root / "document.json").stat().st_mode & 0o777 == 0o600


def test_a_technical_error_cannot_become_clinical_abstention(setup_phase2):
    dictionary, _, _, inputs, _ = setup_phase2
    dictionary = dictionary.model_copy(update={"clinically_approved": True})
    old = inputs.extraction_a.results[1].model_copy(
        update={
            "operation": OperationStatus.FAILED,
            "value": None,
            "technical_error": TechnicalError(code="timeout"),
        }
    )
    states = dict(inputs.extraction_a.semantic_states)
    states.pop("exacerbacion_actual")
    original = ExtractionSnapshot.model_validate(
        inputs.extraction_a.model_dump()
        | {
            "results": (inputs.extraction_a.results[0], old, *inputs.extraction_a.results[2:]),
            "semantic_states": states,
        }
    )
    verification, _ = run_case((dictionary, *setup_phase2[1:]))
    comparison = compare_extractions(original, verification, dictionary, inputs.document)
    policy = ReconciliationPolicy(policy_id="abstain", version="1", unresolved_action="ABSTAIN")
    final = reconcile(inputs.document, original, verification, comparison, policy, dictionary)
    assert final.decisions[1].technical_error.code == "timeout"
    assert final.decisions[1].resulting_state is None
    assert final.decisions[1].action == "HUMAN_REVIEW"


def test_integrity_scan_rejects_artifact_symlinks(tmp_path):
    store = JSONRunStore(tmp_path / "run")
    external = tmp_path / "external.json"
    external.write_text('{"synthetic":true}')
    (store.root / "external.json").symlink_to(external)
    with pytest.raises(ValueError, match="symlinks"):
        store.artifact_hashes()


def test_mock_a_structured_output_flows_to_b_without_second_extraction(setup_phase2, tmp_path):
    from extracteval.adapters.models.mock import ScriptedModel
    from extracteval.core.models import ModelParameters, ModelRequest

    dictionary, policy, config, inputs, payload = setup_phase2
    original = inputs.extraction_a.model_copy(deep=True)
    original.auxiliary["isolation_marker"] = "A_ONLY_SYNTHETIC_MARKER"
    extractor_mock = ScriptedModel([original.model_dump_json()])
    request = ModelRequest(
        execution_id="mock-original-a",
        request_id="mock-a-request",
        instructions="Synthetic adapter contract check; no clinical inference.",
        content=inputs.document.text,
        parameters=ModelParameters(response_format="structured"),
    )
    response = extractor_mock.generate(request)
    extraction_a = ExtractionSnapshot.model_validate_json(response.structured_json)
    for result in extraction_a.results:
        result.validate_against(dictionary)
    model_v = MockVerifierModel([payload])
    store = JSONRunStore(tmp_path / "run")
    before = extraction_a.model_dump_json()
    manifest = run_verification(
        inputs.model_copy(update={"extraction_a": extraction_a}),
        dictionary,
        policy,
        config,
        store,
        IndependentVerifier(model_v),
    )
    assert manifest.base_extraction_hash == content_hash(extraction_a)
    assert extraction_a.model_dump_json() == before
    assert "A_ONLY_SYNTHETIC_MARKER" not in model_v.requests[0].content
    assert store.get("extraction_b", ReconciledExtraction).base_extraction_hash == content_hash(
        extraction_a
    )
    # The scripted extractor has exactly one response. A second extraction would fail.
