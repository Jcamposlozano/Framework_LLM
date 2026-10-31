"""Scripted blind verifier. It asserts the same interface as the real adapter."""

from collections.abc import Sequence

from extracteval.core.exceptions import ProviderFailure
from extracteval.core.models import ModelCapabilities, ModelIdentity, ModelRequest, ModelResponse
from extracteval.core.verification import VerificationPayload


class MockVerifierModel:
    def __init__(self, payloads: Sequence[VerificationPayload | ProviderFailure | str]) -> None:
        self._payloads = iter(payloads)
        self.requests: list[ModelRequest] = []

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(engine="mock", model_id="mock-verifier", model_version="1")

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            max_output_tokens=True, structured_output=True, exact_reproducibility=True
        )

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.capabilities.validate_parameters(request.parameters)
        self.requests.append(request)
        try:
            payload = next(self._payloads)
        except StopIteration:
            raise ProviderFailure("unavailable") from None
        if isinstance(payload, ProviderFailure):
            raise payload
        text = payload if isinstance(payload, str) else payload.model_dump_json()
        # Malformed JSON is simulated as an invalid structured value while retaining raw output.
        import json

        try:
            json.loads(text)
            structured = text
        except ValueError:
            structured = "null"
        return ModelResponse(
            execution_id=request.execution_id,
            request_id=request.request_id,
            model=self.identity,
            effective_parameters=request.parameters,
            capabilities_used=self.capabilities.used_by(request.parameters),
            text=text,
            structured_json=structured,
            elapsed_seconds=0,
        )


class MockExtractorModel(MockVerifierModel):
    """The same scripted transport, with a distinct A identity; no clinical inference."""

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(engine="mock", model_id="mock-extractor", model_version="1")
