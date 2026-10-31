"""Synthetic clinical fixtures exercise mechanics, never clinical model accuracy."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extraccion_laboratorio import (  # noqa: E402
    demo_extraction,
    prepare_extraction,
    synthetic_extraction,
)
from laboratorio_yaml_json import (  # noqa: E402
    LabError,
    create_simple,
    prepare_specification,
)
from verificacion_laboratorio import prepare_verification, register_original  # noqa: E402

from extracteval.adapters.models.openai import OpenAIResponsesModel  # noqa: E402
from extracteval.adapters.models.verification_mock import (  # noqa: E402
    MockExtractorModel,
    MockVerifierModel,
)
from extracteval.adapters.storage.json_store import JSONRunStore  # noqa: E402
from extracteval.application.configuration import (
    GovernanceAuthorization,  # noqa: E402
    load_configuration,  # noqa: E402
)
from extracteval.application.extraction import (  # noqa: E402
    ExtractionExecution,
    extract_document,
    load_extractor,
)
from extracteval.application.pipeline import run_verification  # noqa: E402
from extracteval.application.verification import IndependentVerifier  # noqa: E402
from extracteval.cli import main  # noqa: E402
from extracteval.core.documents import DocumentSection  # noqa: E402
from extracteval.core.exceptions import ProviderFailure  # noqa: E402
from extracteval.core.hashing import content_hash  # noqa: E402
from extracteval.core.verification import (  # noqa: E402
    ExtractionSnapshot,
    ReconciledExtraction,
    VerificationInput,
    VerificationPayload,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup_a(tmp_path):
    lab = tmp_path / "lab"
    create_simple(lab)
    definitions = json.loads((ROOT / "configs/epoc/dictionary.v1.json").read_bytes())
    source = {
        "dictionary_id": "synthetic-epoc",
        "version": "draft.v1",
        "status": "pending",
        "variables": {
            v["variable_id"]: {
                "type": v["data_type"],
                "definition": v["operational_definition"],
                "allowed_values": v["categories"],
                "information_policy": v["information_policy"],
                "correctness_criteria": v["correctness_criteria"],
            }
            for v in definitions["variables"]
        },
    }
    (lab / "01_especificacion/especificacion.yaml").write_text(yaml.safe_dump(source))
    prepare_specification(lab)
    prepare_verification(lab)
    config = prepare_extraction(lab)
    settings, dictionary, prompt = load_extractor(config, {})
    document, payload = synthetic_extraction(dictionary)
    return lab, config, settings, dictionary, prompt, document, payload


def run_a(setup_a, tmp_path, payload=None, model=None, name="a"):
    _, _, settings, dictionary, prompt, document, fixture = setup_a
    chosen = fixture if payload is None else payload
    adapter = model if model is not None else MockExtractorModel([chosen])
    store = JSONRunStore(tmp_path / name)
    result = extract_document(
        document,
        dictionary,
        settings,
        prompt,
        adapter,
        store,
        mock_payload_hash=content_hash(chosen) if not isinstance(chosen, Exception) else None,
    )
    return result, adapter, store


def test_six_values_null_negation_evidence_and_trace(setup_a, tmp_path):
    execution, model, store = run_a(setup_a, tmp_path)
    snapshot = execution.extraction_a
    assert len(snapshot.results) == 6
    results = {r.trace.variable_id: r for r in snapshot.results}
    assert results["exacerbacion_actual"].value.value == "false"
    assert results["exacerbacion_previa"].value.value == "indeterminado"
    assert results["fecha_indice_evento"].value is None
    assert snapshot.semantic_states["fecha_indice_evento"] == "indeterminate"
    assert results["exacerbacion_actual"].evidence.items[0].quote in setup_a[5].text
    for result in snapshot.results:
        result.validate_against(setup_a[3])
        result.trace.validate_config(execution.effective_configuration)
        assert result.trace.document_id == setup_a[5].document_id
    assert ExtractionSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert store.get("execution", ExtractionExecution) == execution
    assert len(model.requests) == 1
    assert "provenance" in json.loads(model.requests[0].content)["document"]
    assert json.loads(model.requests[0].content)["document"]["provenance"] == {}


def changed_payload(setup_a, key, **updates):
    raw = setup_a[6].model_dump(mode="json")
    next(v for v in raw["variables"] if v["variable_id"] == key).update(updates)
    return VerificationPayload.model_validate_json(json.dumps(raw))


def test_explicit_date_preserved(setup_a, tmp_path):
    fixture = list(setup_a)
    document = setup_a[5]
    text = document.text.replace("Fecha de inicio desconocida.", "Fecha de inicio: 2024-01-03.")
    fixture[5] = document.model_copy(
        update={
            "text": text,
            "sections": (DocumentSection(name="analisis", start=0, end=len(text)),),
        }
    )
    quote = "Fecha de inicio: 2024-01-03."
    payload = changed_payload(
        setup_a,
        "fecha_indice_evento",
        proposed_value={"kind": "date", "value": "2024-01-03"},
        semantic_state="value",
        evidence=[
            {
                "document_id": document.document_id,
                "quote": quote,
                "section": "analisis",
                "start": text.index(quote),
                "end": text.index(quote) + len(quote),
            }
        ],
        evidence_type="literal",
    )
    execution, _, _ = run_a(tuple(fixture), tmp_path, payload)
    value = next(
        r.value
        for r in execution.extraction_a.results
        if r.trace.variable_id == "fecha_indice_evento"
    )
    assert value.model_dump(mode="json")["value"] == "2024-01-03"


def test_abstention_is_separate_from_indetermination(setup_a, tmp_path):
    payload = changed_payload(
        setup_a,
        "fecha_indice_evento",
        semantic_state="abstain",
        uncertainty_flags=["insufficient_evidence"],
    )
    execution, _, _ = run_a(setup_a, tmp_path, payload)
    result = next(
        r for r in execution.extraction_a.results if r.trace.variable_id == "fecha_indice_evento"
    )
    assert result.value is None and result.abstention.reason == "insufficient_evidence"
    assert result.technical_error is None


def test_invalid_literal_evidence_is_flagged_without_changing_value(setup_a, tmp_path):
    raw = setup_a[6].model_dump(mode="json")
    raw["variables"][0]["evidence"][0]["quote"] = "CITA INEXISTENTE"
    execution, _, _ = run_a(setup_a, tmp_path, VerificationPayload.model_validate(raw))
    result = execution.extraction_a.results[0]
    assert result.value.value == "estable"
    assert "evidence_offset_mismatch" in {f.code for f in result.findings}


@pytest.mark.parametrize(
    "damage",
    ["missing", "extra", "duplicate", "boolean", "category", "date", "wrong_doc", "abstain_reason"],
)
def test_invalid_response_yields_six_technical_results(setup_a, tmp_path, damage):
    raw = setup_a[6].model_dump(mode="json")
    if damage == "missing":
        raw["variables"].pop()
    elif damage == "extra":
        raw["variables"].append(raw["variables"][0] | {"variable_id": "extra"})
    elif damage == "duplicate":
        raw["variables"].append(raw["variables"][0])
    elif damage == "boolean":
        raw["variables"][1]["proposed_value"] = {"kind": "boolean", "value": False}
    elif damage == "category":
        raw["variables"][0]["proposed_value"]["value"] = "otra"
    elif damage == "date":
        raw["variables"][3]["proposed_value"] = {"kind": "date", "value": "2024-99-99"}
    elif damage == "wrong_doc":
        raw["variables"][0]["evidence"][0]["document_id"] = "foreign"
    else:
        raw["variables"][3]["semantic_state"] = "abstain"
        raw["variables"][3]["uncertainty_flags"] = []
    execution, _, _ = run_a(setup_a, tmp_path, json.dumps(raw))
    assert execution.audit.error.code == "invalid_response"
    assert len(execution.extraction_a.results) == 6
    assert execution.extraction_a.semantic_states == {}
    assert all(r.operation == "failed" and r.value is None for r in execution.extraction_a.results)


@pytest.mark.parametrize("code", ["timeout", "unavailable", "invalid_response"])
def test_provider_failure_preserves_operational_error(setup_a, tmp_path, code):
    execution, _, _ = run_a(setup_a, tmp_path, ProviderFailure(code))
    assert all(r.technical_error.code == code for r in execution.extraction_a.results)
    assert execution.audit.response is None


def test_resume_no_second_call_and_tamper_rejected(setup_a, tmp_path):
    execution, model, store = run_a(setup_a, tmp_path)
    _, _, settings, dictionary, prompt, document, payload = setup_a
    resumed = extract_document(
        document,
        dictionary,
        settings,
        prompt,
        model,
        store,
        mock_payload_hash=content_hash(payload),
    )
    assert resumed == execution and len(model.requests) == 1
    with pytest.raises(ValueError, match="resume"):
        extract_document(
            document.model_copy(update={"text": "otra nota", "sections": ()}),
            dictionary,
            settings,
            prompt,
            model,
            store,
            mock_payload_hash=content_hash(payload),
        )
    raw = json.loads((store.root / "extraction_a.json").read_bytes())
    raw["base_extraction_id"] = "tampered"
    (store.root / "extraction_a.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="integrity"):
        extract_document(
            document,
            dictionary,
            settings,
            prompt,
            model,
            store,
            mock_payload_hash=content_hash(payload),
        )


def test_interrupted_execution_is_not_repeated(setup_a, tmp_path):
    _, model, store = run_a(setup_a, tmp_path)
    (store.root / "manifest.json").unlink()
    with pytest.raises(ValueError, match="Interrupted"):
        run_a(setup_a, tmp_path, model=model)
    assert len(model.requests) == 1


def test_registration_independence_comparison_reconciliation(setup_a, tmp_path):
    lab, _, _, dictionary, _, document, payload = setup_a
    execution, _, store = run_a(setup_a, tmp_path)
    original_bytes = (store.root / "extraction_a.json").read_bytes()
    entry = register_original(
        lab,
        document_id=document.document_id,
        source=store.root / "extraction_a.json",
        document=document,
    )
    inputs = VerificationInput.model_validate_json(entry.read_bytes())
    assert inputs.extraction_a == execution.extraction_a
    assert (entry.parent / "a-original.json").read_bytes() == original_bytes
    _, _, policy, config = load_configuration(
        lab / "configuraciones/verificacion/v1/config.json", {}, "mock"
    )
    # A-only marker must never enter V, including in nested auxiliary metadata.
    inputs.extraction_a.auxiliary["marker"] = "EXCLUSIVO_A_001"
    model_v = MockVerifierModel([payload])
    output = JSONRunStore(tmp_path / "b")
    before = inputs.extraction_a.model_dump_json()
    manifest = run_verification(
        inputs, dictionary, policy, config, output, IndependentVerifier(model_v)
    )
    assert "EXCLUSIVO_A_001" not in model_v.requests[0].content
    assert "EXCLUSIVO_A_001" not in model_v.requests[0].instructions
    assert inputs.extraction_a.model_dump_json() == before
    b = output.get("extraction_b", ReconciledExtraction)
    assert len(b.decisions) == 6
    assert b.base_extraction_hash == manifest.base_extraction_hash
    assert all(d.action in ("KEEP_A", "HUMAN_REVIEW") for d in b.decisions)
    assert (store.root / "extraction_a.json").read_bytes() == original_bytes
    assert run_verification(inputs, dictionary, policy, config, output, None) == manifest
    assert len(model_v.requests) == 1
    with pytest.raises(LabError):
        register_original(
            lab,
            document_id=document.document_id,
            source=store.root / "extraction_a.json",
            document=document.model_copy(update={"text": "nota distinta"}),
        )


def test_independent_settings_and_prompt_integrity(setup_a):
    _, config, settings, _, _, _, _ = setup_a
    changed, _, _ = load_extractor(config, {"EXTRACTEVAL_VERIFIER_MODEL": "other"})
    assert changed.model == settings.model
    changed, _, _ = load_extractor(config, {"EXTRACTEVAL_EXTRACTOR_MODEL": "gpt-4.1-mini"})
    assert changed.model == "gpt-4.1-mini"
    prompt_path = config.parent / "extractor_v1.txt"
    prompt_path.write_text("alterado")
    with pytest.raises(ValueError, match="prompt integrity"):
        load_extractor(config, {})


def test_cli_mock_resume_real_blocked_and_dry_run(setup_a, tmp_path):
    _, config, _, _, _, _, _ = setup_a
    args = [
        "extract",
        "--config",
        str(config),
        "--input",
        str(config.parent / "demo-documento.json"),
        "--output",
        str(tmp_path / "cli"),
    ]
    assert main(args + ["--dry-run"]) == 0
    assert not (tmp_path / "cli").exists()
    assert main(args + ["--mode", "real"]) == 2
    assert main(args) == 0
    assert main(args) == 0


def test_lab_demo_reuses_A_and_preserves_V_and_corpus(setup_a):
    lab = setup_a[0]
    v_files = {
        p: p.read_bytes()
        for p in (lab / "configuraciones/verificacion/v1").iterdir()
        if p.is_file()
    }
    corpus = (lab / "datos/documentos.json").read_bytes()
    first = demo_extraction(lab)
    assert first["a_mock_calls_this_invocation"] == 1
    second = demo_extraction(lab)
    assert second["base_extraction_id"] == first["base_extraction_id"]
    assert second["a_mock_calls_this_invocation"] == 0
    assert second["v_mock_calls_this_invocation"] == 0
    assert (lab / "datos/documentos.json").read_bytes() == corpus
    assert all(p.read_bytes() == data for p, data in v_files.items())


def test_existing_openai_adapter_separate_schema_and_effective_identity(setup_a, tmp_path):
    class Transport:
        def __init__(self):
            self.calls = []

        def request(self, method, path, payload, timeout):
            self.calls.append((method, path, payload))
            if method == "GET":
                return {"id": "gpt-4.1-mini"}
            return {
                "id": "synthetic-provider-id",
                "status": "completed",
                "model": "gpt-4.1-mini-2025-04-14",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": setup_a[6].model_dump_json()}],
                    }
                ],
            }

    _, _, settings, dictionary, prompt, document, _ = setup_a
    transport = Transport()
    model = OpenAIResponsesModel(settings.model, transport, schema_name="clinical_extraction")
    result = extract_document(
        document,
        dictionary,
        settings,
        prompt,
        model,
        JSONRunStore(tmp_path / "fake-http"),
        mode="real",
    )
    assert result.audit.error is None
    assert result.requested_configuration.extractor.model.model_id == "gpt-4.1-mini"
    assert result.effective_configuration.extractor.model.model_id == "gpt-4.1-mini-2025-04-14"
    for variable in result.extraction_a.results:
        variable.trace.validate_config(result.effective_configuration)
    body = transport.calls[1][2]
    assert body["text"]["format"]["name"] == "clinical_extraction"
    assert "temperature" not in body and "seed" not in body
    assert result.audit.response.usage is None


@pytest.mark.parametrize("v_status", ["completed", "incomplete", "refusal"])
def test_real_cli_route_with_fake_transport_and_no_credentials(
    setup_a, tmp_path, monkeypatch, v_status
):
    """Exercise real-mode guards and both CLIs, without constructing an HTTP client."""
    lab, config_a, _, dictionary, _, document, fixture = setup_a
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = {"A": [], "V": []}
    constructions = []

    def transport_for(role):
        class Transport:
            def request(self, method, path, payload, timeout):
                calls[role].append((method, path, payload, timeout))
                if method == "GET":
                    return {"id": "gpt-4.1-mini"}
                content = [{"type": "output_text", "text": fixture.model_dump_json()}]
                if role == "V" and v_status == "refusal":
                    content = [{"type": "refusal", "refusal": "synthetic refusal"}]
                return {
                    "id": "synthetic-response-" + role,
                    "model": "gpt-4.1-mini-2025-04-14",
                    "temperature": 1.0,
                    "status": "incomplete"
                    if role == "V" and v_status == "incomplete"
                    else "completed",
                    "output": [{"type": "message", "content": content}],
                    "usage": {"input_tokens": 111, "output_tokens": 61},
                }

        def factory(api_key):
            assert api_key == ""
            constructions.append(role)
            return Transport()

        return factory

    monkeypatch.setattr("extracteval.extraction_cli.OpenAIHTTPTransport", transport_for("A"))
    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", transport_for("V"))
    governance = GovernanceAuthorization(
        document_hash=content_hash(document),
        authorization_reference="synthetic-test-only",
        institutional_authorization=True,
        personal_data_processing_authorized=True,
        appropriately_deidentified=True,
        retention_and_access_reviewed=True,
        provider_transfer_authorized=True,
    )
    government_path = tmp_path / "synthetic-authorization.json"
    government_path.write_text(governance.model_dump_json())
    a_root, v_root = tmp_path / "a-real-route", tmp_path / "v-real-route"
    args_a = [
        "extract",
        "--config",
        str(config_a),
        "--input",
        str(config_a.parent / "demo-documento.json"),
        "--output",
        str(a_root),
        "--mode",
        "real",
        "--authorize-real",
        "--governance",
        str(government_path),
    ]
    assert main(args_a) == 0
    original_bytes = (a_root / "extraction_a.json").read_bytes()
    a = JSONRunStore(a_root).get("extraction_a", ExtractionSnapshot)
    input_v = tmp_path / "verification-input.json"
    input_v.write_text(VerificationInput(document=document, extraction_a=a).model_dump_json())
    args_v = [
        "verify",
        "--config",
        str(lab / "configuraciones/verificacion/v1/config.json"),
        "--input",
        str(input_v),
        "--output",
        str(v_root),
        "--mode",
        "real",
        "--authorize-real",
        "--governance",
        str(government_path),
    ]
    expected_exit = 0 if v_status == "completed" else 2
    assert main(args_v) == expected_exit
    v = json.loads((v_root / "verification.json").read_bytes())
    b = JSONRunStore(v_root).get("extraction_b", ReconciledExtraction)
    assert len(b.decisions) == len(dictionary.variables) == 6
    assert b.base_extraction_hash == content_hash(a)
    assert v["audit"]["response"]["usage"]["input_tokens"] == 111
    assert v["audit"]["response"]["model"]["model_id"] == "gpt-4.1-mini-2025-04-14"
    assert (v["audit"]["error"] is None) == (v_status == "completed")
    assert all(d.action in ("KEEP_A", "HUMAN_REVIEW") for d in b.decisions)
    if v_status != "completed":
        assert v["audit"]["error"]["code"] == "invalid_response"
        assert all(d.reason == "technical_failure" for d in b.decisions)
    for role, schema_name in (("A", "clinical_extraction"), ("V", "independent_verification")):
        assert [call[0] for call in calls[role]] == ["GET", "POST"]
        body = calls[role][1][2]
        assert body["model"] == "gpt-4.1-mini" and body["store"] is False
        assert body["text"]["format"]["name"] == schema_name
        assert "oneOf" not in json.dumps(body["text"]["format"]["schema"])
        assert a.base_extraction_id not in body["input"]
        assert "synthetic-response-A" not in body["input"]
    assert constructions == ["A", "V"]
    before = {str(p): p.read_bytes() for root in (a_root, v_root) for p in root.glob("*.json")}
    assert main(args_a) == 0 and main(args_v) == expected_exit
    assert all(Path(p).read_bytes() == content for p, content in before.items())
    assert constructions == ["A", "V"]
    assert (a_root / "extraction_a.json").read_bytes() == original_bytes
    execution = JSONRunStore(a_root).get("execution", ExtractionExecution)
    assert execution.model_record.effective_parameters.temperature == 1.0
    assert execution.requested_configuration.extractor.parameters.temperature is None


@pytest.mark.parametrize("command", ["extract", "verify"])
@pytest.mark.parametrize("damage", ["not_authorized", "wrong_document", "missing_flag"])
def test_real_cli_authorization_rejects_before_transport(
    setup_a, tmp_path, monkeypatch, command, damage
):
    lab, config_a, _, _, _, document, _ = setup_a
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Authorization must be checked before transport construction")

    monkeypatch.setattr("extracteval.extraction_cli.OpenAIHTTPTransport", forbidden)
    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", forbidden)
    authorization = GovernanceAuthorization(
        document_hash="0" * 64 if damage == "wrong_document" else content_hash(document),
        authorization_reference="synthetic-test-only",
        institutional_authorization=True,
        personal_data_processing_authorized=True,
        appropriately_deidentified=True,
        retention_and_access_reviewed=True,
        provider_transfer_authorized=damage != "not_authorized",
    )
    governance = tmp_path / "synthetic-authorization.json"
    governance.write_text(authorization.model_dump_json())
    config = (
        config_a if command == "extract" else lab / "configuraciones/verificacion/v1/config.json"
    )
    input_path = config_a.parent / "demo-documento.json"
    if command == "verify":
        input_path = tmp_path / "independent-input.json"
        input_path.write_text(VerificationInput(document=document).model_dump_json())
    output = tmp_path / "blocked-output"
    args = [
        command,
        "--config",
        str(config),
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--mode",
        "real",
        "--governance",
        str(governance),
    ]
    if command == "verify":
        args.extend(["--stage", "independent"])
    if damage != "missing_flag":
        args.append("--authorize-real")
    assert main(args) == 2
    assert not output.exists()


def test_study_yaml_binding_and_no_scientific_authorization():
    lab = ROOT / "laboratorios/mi_estudio_001"
    if not lab.exists():
        pytest.skip("Local ignored study is not part of a distributed checkout")
    plan = yaml.safe_load((lab / "02_diseno/diseno.yaml").read_bytes())
    base = plan["configuraciones_comparadas"]["extractor_base"]
    assert all(base.values())
    candidate = next(c for c in plan["validacion_prompts"]["candidatos"] if c["rol"] == "extractor")
    prompt = lab / candidate["instrucciones_ruta"]
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == base["instrucciones_sha256"]
    assert candidate["aprobacion_cientifica"] is False
    assert all(value is False for value in plan["autorizacion_operativa"].values())
