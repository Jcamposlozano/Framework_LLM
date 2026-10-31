"""Neutral requests, responses and explicitly declared capabilities."""

import json
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, StrictStr, model_validator

from extracteval.core.base import Contract, Identifier
from extracteval.core.exceptions import UnsupportedConfigurationError


class ResponseFormat(StrEnum):
    TEXT = "text"
    STRUCTURED = "structured"


class ModelIdentity(Contract):
    engine: Identifier
    model_id: Identifier
    model_version: Identifier | None = None


class ModelParameters(Contract):
    seed: int | None = Field(default=None, strict=True)
    temperature: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    max_output_tokens: int | None = Field(default=None, gt=0, strict=True)
    response_format: ResponseFormat = ResponseFormat.TEXT


class ModelCapabilities(Contract):
    seed: bool = False
    temperature: bool = False
    max_output_tokens: bool = False
    structured_output: bool = False
    exact_reproducibility: bool = False

    def validate_parameters(self, parameters: ModelParameters) -> None:
        incompatible = (
            (parameters.seed is not None and not self.seed)
            or (parameters.temperature is not None and not self.temperature)
            or (parameters.max_output_tokens is not None and not self.max_output_tokens)
            or (
                parameters.response_format == ResponseFormat.STRUCTURED
                and not self.structured_output
            )
        )
        if incompatible:
            raise UnsupportedConfigurationError()

    def used_by(self, parameters: ModelParameters) -> tuple[str, ...]:
        self.validate_parameters(parameters)
        used: list[str] = []
        if parameters.seed is not None:
            used.append("seed")
        if parameters.temperature is not None:
            used.append("temperature")
        if parameters.max_output_tokens is not None:
            used.append("max_output_tokens")
        if parameters.response_format == ResponseFormat.STRUCTURED:
            used.append("structured_output")
        return tuple(used)


class ModelRequest(Contract):
    execution_id: Identifier
    request_id: Identifier
    instructions: str = Field(repr=False)
    content: str = Field(repr=False)
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    response_schema: dict[str, JsonValue] | None = Field(default=None, repr=False)
    timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)


class TokenUsage(Contract):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    reasoning_tokens: int | None = Field(default=None, ge=0, strict=True)


class ModelResponse(Contract):
    execution_id: Identifier
    request_id: Identifier
    provider_request_id: Identifier | None = None
    model: ModelIdentity
    effective_parameters: ModelParameters
    capabilities_used: tuple[str, ...] = ()
    text: StrictStr = Field(repr=False)
    # Keep neutral structured output as serialized JSON; no provider-specific object types.
    structured_json: str | None = Field(default=None, repr=False)
    usage: TokenUsage | None = None
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Identifier | None = None
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    retry_count: int = Field(default=0, ge=0, strict=True)
    diagnostic_error_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_payload(self) -> Self:
        structured = self.effective_parameters.response_format == ResponseFormat.STRUCTURED
        if structured != (self.structured_json is not None):
            raise ValueError("Response payload must match the effective response format")
        if self.structured_json is not None:
            try:
                json.loads(self.structured_json, parse_constant=_reject_json_constant)
            except ValueError:
                raise ValueError("Structured response must contain valid JSON") from None
        if (self.cost is None) != (self.currency is None):
            raise ValueError("Cost and currency must be supplied together")
        return self


def _reject_json_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are unsupported")
