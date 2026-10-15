"""Two interchangeable offline models for contract and consumer tests."""

import json
from collections.abc import Sequence
from time import perf_counter

from extracteval.core.exceptions import ModelExecutionError
from extracteval.core.models import ModelCapabilities, ModelIdentity, ModelRequest, ModelResponse


def _response(
    request: ModelRequest,
    identity: ModelIdentity,
    capabilities: ModelCapabilities,
    text: str,
    structured_json: str | None,
    started: float,
) -> ModelResponse:
    return ModelResponse(
        execution_id=request.execution_id,
        request_id=request.request_id,
        model=identity,
        effective_parameters=request.parameters,
        capabilities_used=capabilities.used_by(request.parameters),
        text=text,
        structured_json=structured_json,
        elapsed_seconds=perf_counter() - started,
    )


class ConstantModel:
    """Text-only deterministic model; execution parameters are unsupported."""

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(engine="mock", model_id="constant", model_version="1")

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(exact_reproducibility=True)

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        self.capabilities.validate_parameters(request.parameters)
        return _response(request, self.identity, self.capabilities, self._text, None, started)


class ScriptedModel:
    """Finite response sequence; seed/temperature accepted but do not alter the script.

    Reproducibility requires a fresh instance with the same script and call order.
    No stochastic sampling, token limiting, network or actual token usage is simulated.
    """

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(engine="mock", model_id="scripted", model_version="1")

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            seed=True, temperature=True, structured_output=True, exact_reproducibility=True
        )

    def __init__(self, responses: Sequence[str | None]) -> None:
        self._responses = tuple(responses)
        self._index = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        self.capabilities.validate_parameters(request.parameters)
        if self._index >= len(self._responses):
            raise ModelExecutionError()
        text = self._responses[self._index]
        if text is None:
            self._index += 1
            raise ModelExecutionError()
        structured_json = None
        if request.parameters.response_format.value == "structured":
            try:
                json.loads(text, parse_constant=_reject_constant)
            except (ValueError, TypeError):
                raise ModelExecutionError() from None
            structured_json = text
        self._index += 1
        return _response(request, self.identity, self.capabilities, text, structured_json, started)


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are unsupported")
