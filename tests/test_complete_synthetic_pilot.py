"""Existing A to independent V and conservative B; no live HTTP or credentials."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from auditar_integracion import prepare_lab
from completar_piloto_sintetico import locate_quote, main
from extraccion_laboratorio import synthetic_extraction

from extracteval.adapters.models.openai import OpenAIResponsesModel, TransportFailure
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.authorization import (
    PersonalSyntheticAuthorization,
    load_extraction_authorization,
    load_verification_authorization,
)
from extracteval.application.extraction import extract_document, load_extractor
from extracteval.core.documents import Document, DocumentSection, Evidence
from extracteval.core.hashing import content_hash
from extracteval.core.verification import VerificationPayload


class FakeTransport:
    def __init__(self, payload, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def request(self, method, path, payload, timeout):
        self.calls.append((method, path, payload))
        if method == "GET":
            return {"id": "gpt-4.1-mini"}
        if self.error is not None:
            raise self.error
        return {
            "id": "synthetic-provider-response",
            "model": "gpt-4.1-mini-2025-04-14",
            "status": "completed",
            "temperature": 1.0,
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": self.payload.model_dump_json()}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 60},
        }


@pytest.fixture
def pilot(tmp_path):
    lab = prepare_lab(tmp_path / "lab")
    settings, dictionary, prompt = load_extractor(
        lab / "configuraciones/extraccion/v1/config.json", {}
    )
    document, fixture = synthetic_extraction(dictionary)
    raw = fixture.model_dump(mode="json")
    for item in raw["variables"]:
        for evidence in item["evidence"]:
            evidence.update(start=10, end=21)
    bad_offsets = VerificationPayload.model_validate_json(json.dumps(raw))
    source = lab / "ejecuciones/primera-a-personal-003"
    a_transport = FakeTransport(bad_offsets)
    execution = extract_document(
        document,
        dictionary,
        settings,
        prompt,
        OpenAIResponsesModel(settings.model, a_transport, max_retries=0),
        JSONRunStore(source),
        mode="real",
    )
    return lab, source, execution, fixture, document


def args(lab, destination, action="ejecutar", mode="mock"):
    return [action, "--laboratorio", str(lab), "--destino", str(destination), "--mode", mode]


def bytes_in(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_mock_completion_and_readonly_inspection(pilot, tmp_path, monkeypatch):
    lab, source, a, _, _ = pilot
    destination = tmp_path / "mock"
    before = bytes_in(source)

    def forbidden(*a, **kw):
        pytest.fail("No HTTP client during offline completion")

    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", forbidden)
    assert main(args(lab, destination)) == 0
    summary = json.loads((destination / "resultado.json").read_bytes())
    assert summary["mode"] == "mock" and summary["a_unchanged"] is True
    assert len(summary["b_decisions"]) == 6
    assert all(d["action"] in ("KEEP_A", "HUMAN_REVIEW") for d in summary["b_decisions"])
    review = json.loads((destination / "revision-evidencia-a.json").read_bytes())
    assert review["applies_changes"] is False
    matches = review["variables"]["estado_paciente"]
    assert matches[0]["status"] == "unique_match"
    assert matches[0]["candidate"] == {"start": 10, "end": 48, "section": "analisis"}
    assert review["base_extraction_hash"] == content_hash(a.extraction_a)
    assert before == bytes_in(source)
    saved = bytes_in(destination)
    assert main(args(lab, destination, action="inspeccionar")) == 0
    assert saved == bytes_in(destination)
    assert main(args(lab, destination)) == 0
    assert saved == bytes_in(destination)


def test_real_completion_separate_consent_independence_and_resume(pilot, tmp_path, monkeypatch):
    lab, source, a, fixture, _ = pilot
    destination = tmp_path / "real"
    transport = FakeTransport(fixture)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = bytes_in(source)

    def factory(key):
        assert key == ""
        return transport

    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", factory)
    command = args(lab, destination, mode="real") + ["--autorizar-v-real"]
    assert main(command) == 0
    assert [c[0] for c in transport.calls] == ["GET", "POST"]
    request = transport.calls[1][2]
    assert a.extraction_a.base_extraction_id not in request["input"]
    assert "synthetic-provider-response" not in request["input"]
    assert set(json.loads(request["input"])) == {"document", "dictionary"}
    consent = json.loads((destination / "vb/governance.json").read_bytes())
    assert consent["operation"] == "verify_v" and consent["external_calls_authorized"] is True
    assert "institutional_authorization" not in consent
    summary = json.loads((destination / "resultado.json").read_bytes())
    assert summary["v_usage"]["input_tokens"] == 100
    assert summary["v_model"]["model_id"] == "gpt-4.1-mini-2025-04-14"
    assert summary["status"] == "completed" and summary["a_unchanged"] is True
    saved = bytes_in(destination)
    assert main(command) == 0
    assert len(transport.calls) == 2
    assert saved == bytes_in(destination) and before == bytes_in(source)


def test_real_V_has_no_automatic_retry(pilot, tmp_path, monkeypatch):
    lab, source, _, fixture, _ = pilot
    before = bytes_in(source)
    destination = tmp_path / "failure"
    transport = FakeTransport(fixture, TransportFailure("rate_limit", True))
    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", lambda key: transport)
    assert main(args(lab, destination, mode="real") + ["--autorizar-v-real"]) == 2
    summary = json.loads((destination / "resultado.json").read_bytes())
    assert summary["v_error"]["code"] == "unavailable"
    assert [c[0] for c in transport.calls] == ["GET", "POST"]
    assert before == bytes_in(source)


def test_real_missing_consent_rejected_before_client(pilot, tmp_path, monkeypatch):
    lab = pilot[0]

    def forbidden(*a, **kw):
        pytest.fail("Client constructed before consent")

    monkeypatch.setattr("extracteval.cli.OpenAIHTTPTransport", forbidden)
    destination = tmp_path / "blocked"
    assert main(args(lab, destination, mode="real")) == 2
    assert not destination.exists()
    assert main(args(lab, destination, action="preparar", mode="real")) == 0
    assert not (destination / "consentimiento-v.json").exists()
    assert main(args(lab, tmp_path / "mixed") + ["--autorizar-v-real"]) == 2
    before = bytes_in(destination)
    assert main(args(lab, destination, action="inspeccionar", mode="real")) == 2
    assert before == bytes_in(destination)


def test_consent_operations_are_not_interchangeable(pilot, tmp_path):
    document = pilot[4]
    path = tmp_path / "consent.json"
    personal = PersonalSyntheticAuthorization(
        mode="personal_synthetic_development",
        authorization_reference="synthetic-test",
        fixture_id="extracteval.demo-extractor-epoc.v1",
        document_id=document.document_id,
        document_hash=content_hash(document),
        operation="verify_v",
        provider="openai",
        model_id="gpt-4.1-mini",
        external_calls_authorized=True,
    )
    path.write_text(personal.model_dump_json())
    assert load_verification_authorization(path, document, "gpt-4.1-mini").operation == "verify_v"
    with pytest.raises(ValueError):
        load_extraction_authorization(path, document, "gpt-4.1-mini")
    with pytest.raises(ValueError):
        load_verification_authorization(path, document, "gpt-other-mini")
    path.write_text(
        personal.model_copy(update={"external_calls_authorized": False}).model_dump_json()
    )
    with pytest.raises(ValueError):
        load_verification_authorization(path, document, "gpt-4.1-mini")
    path.write_text(personal.model_copy(update={"operation": "extract_a"}).model_dump_json())
    with pytest.raises(ValueError):
        load_verification_authorization(path, document, "gpt-4.1-mini")
    modified = document.model_copy(update={"provenance": {"synthetic": True}})
    path.write_text(
        personal.model_copy(update={"document_hash": content_hash(modified)}).model_dump_json()
    )
    with pytest.raises(ValueError):
        load_verification_authorization(path, modified, "gpt-4.1-mini")


@pytest.mark.parametrize("damage", ["a", "vb", "mode", "overlap", "input"])
def test_pilot_rejects_tampering_or_mixed_inputs(pilot, tmp_path, damage):
    lab, source, _, _, _ = pilot
    destination = tmp_path / "guard"
    if damage == "overlap":
        assert main(args(lab, source)) == 2
        return
    assert main(args(lab, destination)) == 0
    if damage == "a":
        (source / "extraction_a.json").write_text("{}")
    elif damage == "vb":
        (destination / "vb/verification.json").write_text("{}")
    elif damage == "input":
        (destination / "entrada.json").write_text("{}")
    else:
        assert main(args(lab, destination, action="preparar", mode="real")) == 2
        return
    assert main(args(lab, destination, action="inspeccionar")) == 2


@pytest.mark.parametrize(
    "text,quote,status",
    [
        ("Árbol árbol", "árbol", "unique_match"),
        ("aaaa", "aa", "ambiguous"),
        ("Nota inventada", "no existe", "not_found"),
    ],
)
def test_quote_locations_are_unicode_exact_and_never_guess(text, quote, status):
    document = Document(
        document_id="synthetic",
        text=text,
        sections=(DocumentSection(name="analysis", start=0, end=len(text)),),
    )
    evidence = Evidence(document_id="synthetic", quote=quote, section="analysis")
    before = evidence.model_dump_json()
    result = locate_quote(document, evidence)
    assert result["status"] == status
    if status == "unique_match":
        candidate = result["candidate"]
        assert text[candidate["start"] : candidate["end"]] == quote
    else:
        assert result["candidate"] is None
    assert evidence.model_dump_json() == before
