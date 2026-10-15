import pytest
from pydantic import ValidationError

from extracteval.adapters.models.mock import ConstantModel, ScriptedModel
from extracteval.core.exceptions import ModelExecutionError, UnsupportedConfigurationError
from extracteval.core.models import ModelParameters, ModelRequest, ModelResponse
from extracteval.core.ports import ModelPort


def consume(model: ModelPort, request: ModelRequest) -> ModelResponse:
    return model.generate(request)


def request(**parameters):
    return ModelRequest(
        execution_id="run-1",
        request_id="request-1",
        instructions="Synthetic instructions",
        content="SYNTHETIC_PRIVATE_CONTENT",
        parameters=ModelParameters(**parameters),
    )


@pytest.mark.parametrize("model", [ConstantModel("same"), ScriptedModel(["same"])])
def test_same_consumer_uses_both_models(model):
    assert isinstance(model, ModelPort)
    output = consume(model, request())
    assert output.text == "same"
    assert output.execution_id == "run-1"
    assert output.request_id == "request-1"
    assert output.provider_request_id is None
    assert output.model == model.identity
    assert output.elapsed_seconds >= 0
    assert ModelResponse.model_validate_json(output.model_dump_json()) == output


@pytest.mark.parametrize(
    "parameters",
    [
        {"seed": 1},
        {"temperature": 0.2},
        {"max_output_tokens": 10},
        {"response_format": "structured"},
    ],
)
def test_text_only_model_rejects_incompatible_capabilities(parameters):
    with pytest.raises(UnsupportedConfigurationError) as error:
        consume(ConstantModel("output"), request(**parameters))
    assert "SYNTHETIC_PRIVATE_CONTENT" not in str(error.value)


def test_scripted_capabilities_effective_parameters_and_structured_output():
    model = ScriptedModel(['{"value": false}'])
    req = request(seed=7, temperature=0.2, response_format="structured")
    response = consume(model, req)
    assert response.structured_json == '{"value": false}'
    assert response.effective_parameters == req.parameters
    assert response.capabilities_used == ("seed", "temperature", "structured_output")
    assert response.usage is None and response.cost is None


def test_unsupported_request_does_not_consume_script():
    model = ScriptedModel(["still available"])
    with pytest.raises(UnsupportedConfigurationError):
        consume(model, request(max_output_tokens=10))
    assert consume(model, request()).text == "still available"


def test_scripted_failures_are_safe_and_reproducible():
    for _ in range(2):
        model = ScriptedModel(["one", None, "three"])
        assert consume(model, request()).text == "one"
        with pytest.raises(ModelExecutionError) as error:
            consume(model, request())
        assert "SYNTHETIC_PRIVATE_CONTENT" not in str(error.value)
        assert consume(model, request()).text == "three"
        with pytest.raises(ModelExecutionError):
            consume(model, request())


@pytest.mark.parametrize("payload", ["SYNTHETIC_PRIVATE_CONTENT", "NaN", "Infinity"])
def test_invalid_scripted_structured_output_hides_content(payload):
    with pytest.raises(ModelExecutionError) as error:
        consume(ScriptedModel([payload]), request(response_format="structured"))
    assert "SYNTHETIC_PRIVATE_CONTENT" not in str(error.value)


def test_request_hides_document_in_repr():
    assert "SYNTHETIC_PRIVATE_CONTENT" not in repr(request())


@pytest.mark.parametrize(
    "fields",
    [
        {"api_key": "SYNTHETIC_SECRET"},
        {"temperature": -1},
        {"temperature": float("inf")},
        {"seed": True},
        {"max_output_tokens": 0},
    ],
)
def test_parameters_reject_unknown_or_invalid_inputs(fields):
    with pytest.raises(ValidationError) as error:
        ModelParameters(**fields)
    assert "SYNTHETIC_SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"structured_json": "{}"},
        {"cost": 0.1},
        {"effective_parameters": {"response_format": "structured"}},
        {"effective_parameters": {"response_format": "structured"}, "structured_json": "NaN"},
    ],
)
def test_response_invariants(changes):
    data = consume(ConstantModel("text"), request()).model_dump()
    data.update(changes)
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(data)
