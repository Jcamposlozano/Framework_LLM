"""No network: fake HTTP transport checks actual Responses requests and retries."""

from copy import deepcopy
from pathlib import Path

import pytest

from extracteval.adapters.models.openai import OpenAIResponsesModel, TransportFailure
from extracteval.application.configuration import GovernanceAuthorization, load_configuration
from extracteval.application.verification import IndependentVerifier, strict_schema
from extracteval.cli import main
from extracteval.core.exceptions import UnsupportedConfigurationError
from extracteval.core.hashing import content_hash
from extracteval.core.models import ModelParameters
from extracteval.core.verification import VerificationInput, VerificationPayload

ROOT = Path(__file__).resolve().parents[1]


class FakeTransport:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = []

    def request(self, method, path, payload, timeout):
        self.calls.append((method, path, payload, timeout))
        result = next(self.actions)
        if isinstance(result, Exception):
            raise result
        return result


def api_setup():
    _, dictionary, _, config = load_configuration(ROOT / "configs/epoc/phase2.json", {}, "real")
    inputs = VerificationInput.model_validate_json(
        (ROOT / "examples/phase2/input.json").read_bytes()
    )
    payload = VerificationPayload.model_validate_json(
        (ROOT / "examples/phase2/mock_verification.json").read_bytes()
    )
    response = {
        "id": "resp-synthetic",
        "status": "completed",
        "model": "gpt-4.1-mini-2025-04-14",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": payload.model_dump_json()}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 60,
            "output_tokens_details": {"reasoning_tokens": 10},
        },
    }
    return dictionary, config, inputs, response


def test_openai_checks_model_schema_and_audit():
    dictionary, config, inputs, response = api_setup()
    transport = FakeTransport([{"id": config.model_id}, response])
    verification = IndependentVerifier(
        OpenAIResponsesModel(config.model_id, transport)
    ).verify_independently(inputs.document, dictionary, config)
    assert verification.audit.error is None
    assert transport.calls[0][:3] == ("GET", "models/gpt-4.1-mini", None)
    payload = transport.calls[1][2]
    assert "temperature" not in payload and "seed" not in payload
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["max_output_tokens"] == config.parameters.max_output_tokens
    assert transport.calls[1][3] == config.timeout_seconds

    def check_schema(node):
        if isinstance(node, dict):
            assert "default" not in node
            assert "oneOf" not in node and "discriminator" not in node
            if "properties" in node:
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
            for value in node.values():
                check_schema(value)
        if isinstance(node, list):
            for value in node:
                check_schema(value)

    check_schema(payload["text"]["format"]["schema"])
    audit = verification.audit
    assert audit.requested_model == "gpt-4.1-mini"
    assert audit.response.model.model_id == response["model"]
    assert audit.response.provider_request_id == "resp-synthetic"
    assert audit.response.usage.reasoning_tokens == 10
    assert audit.response.usage.input_tokens == 100
    assert audit.cost_estimate is None
    assert audit.response.cost is None


def test_strict_schema_preserves_public_schema_and_tagged_nullable_union():
    original = VerificationPayload.model_json_schema()
    before = deepcopy(original)
    converted = strict_schema(original)
    assert original == before
    proposal = converted["$defs"]["VariableVerification"]["properties"]["proposed_value"]
    variants, null = proposal["anyOf"]
    assert null == {"type": "null"}
    assert len(variants["anyOf"]) == 5
    for variant in variants["anyOf"]:
        name = variant["$ref"].split("/")[-1]
        assert "const" in converted["$defs"][name]["properties"]["kind"]


def test_rate_limit_retries_preserve_telemetry():
    dictionary, config, inputs, response = api_setup()
    transport = FakeTransport(
        [{"id": config.model_id}, TransportFailure("rate_limit", True), response]
    )
    sleeps = []
    verifier = IndependentVerifier(
        OpenAIResponsesModel(config.model_id, transport, sleep=sleeps.append)
    )
    verification = verifier.verify_independently(inputs.document, dictionary, config)
    assert verification.audit.retry_count == 1 and verification.audit.errors == ("rate_limit",)
    assert verification.audit.error is None
    assert sleeps == [1]
    assert len(transport.calls) == 3
    assert transport.calls[1][2] == transport.calls[2][2]


def test_retry_budget_exhaustion_remains_technical():
    dictionary, config, inputs, _ = api_setup()
    transport = FakeTransport(
        [{"id": config.model_id}, *[TransportFailure("rate_limit", True) for _ in range(3)]]
    )
    verification = IndependentVerifier(
        OpenAIResponsesModel(config.model_id, transport, sleep=lambda _: None)
    ).verify_independently(inputs.document, dictionary, config)
    assert verification.audit.error.code == "unavailable"
    assert verification.audit.retry_count == 2
    assert verification.audit.errors.count("rate_limit") == 3
    assert verification.payload.variables == ()


def test_unavailable_model_sends_no_document():
    dictionary, config, inputs, _ = api_setup()
    transport = FakeTransport([{"id": "different-model"}])
    verification = IndependentVerifier(
        OpenAIResponsesModel(config.model_id, transport)
    ).verify_independently(inputs.document, dictionary, config)
    assert verification.audit.error is not None
    assert [c[0] for c in transport.calls] == ["GET"]


@pytest.mark.parametrize("status", ["incomplete", "completed"])
def test_invalid_output_retains_usage_and_response_id(status):
    dictionary, config, inputs, response = api_setup()
    response["status"] = status
    response["output"][0]["content"][0]["text"] = "invalid-json"
    transport = FakeTransport([{"id": config.model_id}, response])
    verification = IndependentVerifier(
        OpenAIResponsesModel(config.model_id, transport)
    ).verify_independently(inputs.document, dictionary, config)
    assert verification.audit.error.code == "invalid_response"
    assert verification.audit.response.usage.input_tokens == 100
    assert verification.audit.response.provider_request_id == "resp-synthetic"


def test_openai_rejects_unsupported_temperature():
    adapter = OpenAIResponsesModel("gpt-4.1-mini", FakeTransport([]))
    with pytest.raises(UnsupportedConfigurationError):
        adapter.capabilities.validate_parameters(ModelParameters(temperature=0.0))


def test_environment_models_are_independent():
    _, _, _, config = load_configuration(
        ROOT / "configs/epoc/phase2.json",
        {
            "EXTRACTEVAL_VERIFIER_MODEL": "gpt-4.1-mini",
            "EXTRACTEVAL_RECONCILER_MODEL": "independently-configured",
            "EXTRACTEVAL_MAX_OUTPUT_TOKENS": "2000",
            "EXTRACTEVAL_REQUEST_TIMEOUT": "42",
        },
        "real",
    )
    assert config.model_id == "gpt-4.1-mini"
    assert config.reconciler_model_id == "independently-configured"
    assert config.parameters.max_output_tokens == 2000 and config.timeout_seconds == 42


def test_cli_mock_default_dryrun_resume_and_safe_errors(tmp_path, capsys):
    output = tmp_path / "run"
    args = [
        "verify",
        "--config",
        str(ROOT / "configs/epoc/phase2.json"),
        "--input",
        str(ROOT / "examples/phase2/input.json"),
        "--output",
        str(output),
    ]
    assert main([*args, "--dry-run"]) == 0
    assert not output.exists()
    assert main(args) == 0
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert main(args) == 0
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    blocked = tmp_path / "blocked"
    assert main([*args[:-1], str(blocked), "--mode", "real"]) == 2
    assert not blocked.exists()
    assert "Exacerbación" not in capsys.readouterr().out


def test_governance_is_bound_to_document():
    dictionary, config, inputs, response = api_setup()
    values = dict(
        document_hash=content_hash(inputs.document),
        authorization_reference="institutional-approval",
        institutional_authorization=True,
        personal_data_processing_authorized=True,
        appropriately_deidentified=True,
        retention_and_access_reviewed=True,
        provider_transfer_authorized=True,
    )
    GovernanceAuthorization(**values).validate_authorization(content_hash(inputs.document))
    with pytest.raises(ValueError):
        GovernanceAuthorization(**values).validate_authorization("0" * 64)
    values["appropriately_deidentified"] = False
    with pytest.raises(ValueError):
        GovernanceAuthorization(**values).validate_authorization(content_hash(inputs.document))
