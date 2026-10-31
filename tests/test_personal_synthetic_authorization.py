"""All notes here are invented, including fixtures that simulate real-data classification."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from auditar_integracion import prepare_lab
from extraccion_laboratorio import synthetic_extraction

from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.authorization import (
    DEMO_DOCUMENT_SHA256,
    PersonalSyntheticAuthorization,
    load_extraction_authorization,
)
from extracteval.application.configuration import GovernanceAuthorization
from extracteval.application.extraction import ExtractionExecution, load_extractor
from extracteval.application.stability import RealAuthorization
from extracteval.cli import main
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.verification import VerificationInput

ROOT = Path(__file__).resolve().parents[1]


def documented_python_blocks():
    guide = (ROOT / "docs/primera-extraccion-personal-sintetica.md").read_text()
    return re.findall(r"\.venv/bin/python - <<'PY'\n(.*?)\nPY", guide, re.DOTALL)


def consent(document):
    return {
        "mode": "personal_synthetic_development",
        "authorization_reference": "personal-test-consent",
        "fixture_id": "extracteval.demo-extractor-epoc.v1",
        "document_id": "demo-extractor-epoc-001",
        "document_hash": content_hash(document),
        "operation": "extract_a",
        "provider": "openai",
        "model_id": "gpt-4.1-mini",
        "external_calls_authorized": True,
    }


def institutional(document):
    return {
        "document_hash": content_hash(document),
        "authorization_reference": "simulated-institutional-test-only",
        "institutional_authorization": True,
        "personal_data_processing_authorized": True,
        "appropriately_deidentified": True,
        "retention_and_access_reviewed": True,
        "provider_transfer_authorized": True,
    }


@pytest.fixture
def prepared(tmp_path):
    lab = prepare_lab(tmp_path / "lab")
    config = lab / "configuraciones/extraccion/v1/config.json"
    _, dictionary, _ = load_extractor(config, {})
    document, payload = synthetic_extraction(dictionary)
    return lab, config, document, payload


def write_authorization(path, values):
    path.write_text(json.dumps(values))
    return path


def test_bundled_fixture_is_pinned_and_explicitly_identified(prepared, tmp_path):
    _, config, document, _ = prepared
    assert content_hash(document) == DEMO_DOCUMENT_SHA256
    assert (
        Document.model_validate_json((config.parent / "demo-documento.json").read_bytes())
        == document
    )
    path = write_authorization(tmp_path / "personal.json", consent(document))
    authorization = load_extraction_authorization(path, document, "gpt-4.1-mini")
    assert isinstance(authorization, PersonalSyntheticAuthorization)
    assert authorization.verification_method == "bundled_fixture_sha256"
    assert "institutional_authorization" not in authorization.model_dump()


@pytest.mark.parametrize(
    "change",
    [
        {"text": "Texto inventado distinto; simula una nota que no pertenece al fixture."},
        {"document_id": "another-synthetic-document"},
        {"entity_id": "simulated-patient"},
        {"provenance": {"synthetic": True}},
        {"provenance": {"classification": "simulated_real_clinical"}},
        {"provenance": {"classification": "simulated_anonymized_clinical"}},
        {"provenance": {"classification": "simulated_pseudonymized_clinical"}},
        {"allowed_context": {"synthetic": True, "note": "Invented additional context"}},
        {"document_date": "2026-10-31"},
        {"sections": []},
    ],
)
def test_self_declaration_or_recomputed_hash_cannot_bless_other_data(prepared, tmp_path, change):
    document = prepared[2]
    raw = document.model_dump(mode="json") | change
    if "text" in change:
        raw["sections"] = []
    modified = Document.model_validate_json(json.dumps(raw))
    # Even a matching caller-supplied hash cannot change the trusted package hash.
    path = write_authorization(tmp_path / "personal.json", consent(modified))
    with pytest.raises(ValueError):
        load_extraction_authorization(path, modified, "gpt-4.1-mini")


@pytest.mark.parametrize(
    "change",
    [
        {"document_hash": "0" * 64},
        {"external_calls_authorized": False},
        {"external_calls_authorized": "true"},
        {"external_calls_authorized": 1},
        {"mode": "unrecognized_mode"},
        {"fixture_id": "caller-supplied-fixture"},
        {"operation": "verify"},
        {"provider": "other-provider"},
        {"model_id": "gpt-other-mini"},
        {"institutional_authorization": True},
    ],
)
def test_personal_authorization_fails_closed(prepared, tmp_path, change):
    document = prepared[2]
    path = write_authorization(tmp_path / "personal.json", consent(document) | change)
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-4.1-mini")


def test_missing_consent_and_different_configured_model_rejected(prepared, tmp_path):
    document = prepared[2]
    values = consent(document)
    values.pop("external_calls_authorized")
    path = write_authorization(tmp_path / "personal.json", values)
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-4.1-mini")
    write_authorization(path, consent(document))
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-other-mini")


@pytest.mark.parametrize(
    "missing_check",
    [
        "institutional_authorization",
        "personal_data_processing_authorized",
        "appropriately_deidentified",
        "retention_and_access_reviewed",
        "provider_transfer_authorized",
    ],
)
def test_clinical_classification_still_requires_all_institutional_checks(
    prepared, tmp_path, missing_check
):
    raw = prepared[2].model_dump(mode="json")
    raw["provenance"] = {"classification": "simulated_real_clinical"}
    document = Document.model_validate_json(json.dumps(raw))
    values = institutional(document)
    path = write_authorization(tmp_path / "institutional.json", values)
    assert isinstance(
        load_extraction_authorization(path, document, "gpt-4.1-mini"), GovernanceAuthorization
    )
    write_authorization(path, values | {missing_check: False})
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-4.1-mini")
    write_authorization(path, values | {"document_hash": "0" * 64})
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-4.1-mini")


@pytest.mark.parametrize("authorization_type", ["personal", "institutional"])
def test_real_A_cli_with_fake_transport_audits_consent_and_resumes(
    prepared, tmp_path, monkeypatch, authorization_type
):
    lab, config, document, fixture = prepared
    if authorization_type == "institutional":
        raw = document.model_dump(mode="json")
        raw["provenance"] = {"classification": "simulated_real_clinical"}
        document = Document.model_validate_json(json.dumps(raw))
    source = tmp_path / "invented-document.json"
    source.write_text(document.model_dump_json())
    path = write_authorization(
        tmp_path / "authorization.json",
        consent(document) if authorization_type == "personal" else institutional(document),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []

    class Transport:
        def request(self, method, route, payload, timeout):
            calls.append((method, route, payload))
            if method == "GET":
                return {"id": "gpt-4.1-mini"}
            return {
                "id": "synthetic-transport-response",
                "model": "gpt-4.1-mini-2025-04-14",
                "status": "completed",
                "temperature": 1.0,
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": fixture.model_dump_json()}],
                    }
                ],
                "usage": {"input_tokens": 101, "output_tokens": 51},
            }

    def factory(key):
        assert key == ""
        return Transport()

    monkeypatch.setattr("extracteval.extraction_cli.OpenAIHTTPTransport", factory)
    output = (
        lab / "ejecuciones/primera-a-personal-001"
        if authorization_type == "personal"
        else tmp_path / "run"
    )
    args = [
        "extract",
        "--config",
        str(config),
        "--input",
        str(source),
        "--output",
        str(output),
        "--mode",
        "real",
        "--authorize-real",
        "--governance",
        str(path),
    ]
    assert main(args) == 0
    execution = JSONRunStore(output).get("execution", ExtractionExecution)
    assert execution.document_hash == content_hash(document)
    assert execution.audit.error is None and len(execution.extraction_a.results) == 6
    assert execution.audit.response.usage.input_tokens == 101
    assert execution.audit.response.model.model_id == "gpt-4.1-mini-2025-04-14"
    saved = json.loads((output / "governance.json").read_bytes())
    if authorization_type == "personal":
        assert saved["mode"] == "personal_synthetic_development"
        assert saved["verification_method"] == "bundled_fixture_sha256"
        assert saved["external_calls_authorized"] is True
        assert "institutional_authorization" not in saved
    else:
        assert saved["institutional_authorization"] is True
    before = {p.name: p.read_bytes() for p in output.glob("*.json")}
    assert main(args) == 0
    assert before == {p.name: p.read_bytes() for p in output.glob("*.json")}
    assert [call[0] for call in calls] == ["GET", "POST"]
    if authorization_type == "personal":
        monkeypatch.setenv("LAB", str(lab))
        blocks = documented_python_blocks()
        assert len(blocks) == 3
        exec(compile(blocks[2], "documented_result_inspection", "exec"), {})
        assert [call[0] for call in calls] == ["GET", "POST"]


@pytest.mark.parametrize("damage", ["no_flag", "no_authorization", "other_note", "false_consent"])
def test_personal_cli_rejects_before_transport(prepared, tmp_path, monkeypatch, damage):
    _, config, document, _ = prepared

    def forbidden(*args, **kwargs):
        pytest.fail("Transport must never be constructed without valid consent and fixture")

    monkeypatch.setattr("extracteval.extraction_cli.OpenAIHTTPTransport", forbidden)
    if damage == "other_note":
        raw = document.model_dump(mode="json")
        raw["text"] = "INVENTADO: simula contenido clínico ajeno al fixture autorizado."
        raw["sections"] = []
        raw["provenance"] = {"synthetic": True}
        document = Document.model_validate_json(json.dumps(raw))
    source = tmp_path / "invented-input.json"
    source.write_text(document.model_dump_json())
    values = consent(document)
    if damage == "false_consent":
        values["external_calls_authorized"] = False
    path = write_authorization(tmp_path / "personal.json", values)
    output = tmp_path / "blocked"
    args = [
        "extract",
        "--config",
        str(config),
        "--input",
        str(source),
        "--output",
        str(output),
        "--mode",
        "real",
    ]
    if damage != "no_flag":
        args.append("--authorize-real")
    if damage != "no_authorization":
        args.extend(["--governance", str(path)])
    assert main(args) == 2
    assert not output.exists()


def test_documented_preparation_starts_without_consent(tmp_path, monkeypatch):
    lab = tmp_path / "documented-lab"
    monkeypatch.setenv("LAB", str(lab))
    blocks = documented_python_blocks()
    assert len(blocks) == 3
    exec(compile(blocks[0], "documented_preparation", "exec"), {})
    document = Document.model_validate_json(
        (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
    )
    pending = lab / "consentimiento.pendiente.json"
    assert json.loads(pending.read_bytes())["external_calls_authorized"] is False
    with pytest.raises(ValueError):
        load_extraction_authorization(pending, document, "gpt-4.1-mini")
    exec(compile(blocks[1], "documented_explicit_consent", "exec"), {})
    authorization = load_extraction_authorization(
        lab / "consentimiento.personal.json", document, "gpt-4.1-mini"
    )
    assert authorization.external_calls_authorized is True
    assert not (lab / "ejecuciones/primera-a-personal-001").exists()


def test_mock_remains_default_and_personal_does_not_authorize_V(prepared, tmp_path, monkeypatch):
    lab, config, document, _ = prepared

    def forbidden(*args, **kwargs):
        pytest.fail("No HTTP client may be constructed")

    monkeypatch.setattr("extracteval.extraction_cli.OpenAIHTTPTransport", forbidden)
    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", forbidden)
    path = write_authorization(tmp_path / "personal.json", consent(document))
    with pytest.raises(ValueError):
        RealAuthorization.model_validate(
            {
                "plan_hash": "0" * 64,
                "documents_hash": "0" * 64,
                "reference": "simulated-test-only",
                "authorized": True,
                "governance": [consent(document)],
            }
        )
    output = tmp_path / "mock"
    assert (
        main(
            [
                "extract",
                "--config",
                str(config),
                "--input",
                str(config.parent / "demo-documento.json"),
                "--output",
                str(output),
                "--governance",
                str(path),
            ]
        )
        == 0
    )
    assert JSONRunStore(output).get("execution", ExtractionExecution).mode == "mock"
    input_v = tmp_path / "input-v.json"
    input_v.write_text(VerificationInput(document=document).model_dump_json())
    blocked = tmp_path / "blocked-v"
    assert (
        main(
            [
                "verify",
                "--config",
                str(lab / "configuraciones/verificacion/v1/config.json"),
                "--input",
                str(input_v),
                "--output",
                str(blocked),
                "--mode",
                "real",
                "--stage",
                "independent",
                "--authorize-real",
                "--governance",
                str(path),
            ]
        )
        == 2
    )
    assert not blocked.exists()
