"""OpenAI Responses adapter using HTTP, with no OpenAI SDK dependency."""

import json
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from extracteval.core.exceptions import ProviderFailure
from extracteval.core.models import (
    ModelCapabilities,
    ModelIdentity,
    ModelParameters,
    ModelRequest,
    ModelResponse,
    TokenUsage,
)


class TransportFailure(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        self.code, self.retryable = code, retryable
        super().__init__(code)


class JSONTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]: ...


class OpenAIHTTPTransport:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self._api_key = api_key

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        data = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        )
        request = Request(
            "https://api.openai.com/v1/" + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                body = json.load(response)
            if not isinstance(body, dict):
                raise TransportFailure("invalid_response")
            return body
        except HTTPError as exc:
            if exc.code == 429:
                raise TransportFailure("rate_limit", True) from None
            if exc.code >= 500:
                raise TransportFailure("server_error", True) from None
            raise TransportFailure("unavailable") from None
        except TimeoutError:
            raise TransportFailure("timeout", True) from None
        except URLError:
            raise TransportFailure("unavailable", True) from None
        except (ValueError, UnicodeError):
            raise TransportFailure("invalid_response") from None


class OpenAIResponsesModel:
    def __init__(
        self,
        model_id: str,
        transport: JSONTransport,
        *,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        schema_name: str = "independent_verification",
    ) -> None:
        if not model_id.startswith("gpt-") or "mini" not in model_id.split("-"):
            raise ValueError("Configure a documented GPT mini model")
        if not 0 <= max_retries <= 5:
            raise ValueError("Retry budget must be between zero and five")
        self.model_id, self.transport = model_id, transport
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", schema_name):
            raise ValueError("Invalid structured schema name")
        self.schema_name = schema_name
        self.max_retries, self.sleep = max_retries, sleep

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(engine="openai", model_id=self.model_id)

    @property
    def capabilities(self) -> ModelCapabilities:
        # No temperature or seed claim: do not silently send incompatible parameters.
        return ModelCapabilities(max_output_tokens=True, structured_output=True)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.capabilities.validate_parameters(request.parameters)
        if request.response_schema is None:
            raise ProviderFailure("invalid_response")
        started = time.perf_counter()
        retries = 0
        errors: list[str] = []

        def send(method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
            nonlocal retries
            while True:
                try:
                    return self.transport.request(method, path, payload, request.timeout_seconds)
                except TransportFailure as exc:
                    errors.append(exc.code)
                    if not exc.retryable or retries >= self.max_retries:
                        code = (
                            "unavailable"
                            if exc.code in ("rate_limit", "server_error")
                            else exc.code
                        )
                        raise ProviderFailure(
                            code,
                            retry_count=retries,
                            elapsed_seconds=time.perf_counter() - started,
                            errors=tuple(errors),
                        ) from None
                    retries += 1
                    self.sleep(min(2 ** (retries - 1), 8))

        try:
            # This is account-level availability validation, before any document transmission.
            available = send("GET", "models/" + quote(self.model_id, safe=""), None)
            if available.get("id") != self.model_id:
                raise ValueError("Requested model is not available")
            payload: dict[str, Any] = {
                "model": self.model_id,
                "instructions": request.instructions,
                "input": request.content,
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": self.schema_name,
                        "strict": True,
                        "schema": request.response_schema,
                    }
                },
            }
            if request.parameters.max_output_tokens is not None:
                payload["max_output_tokens"] = request.parameters.max_output_tokens
            result = send("POST", "responses", payload)
            text = "".join(
                part["text"]
                for output in result.get("output", [])
                if output.get("type") == "message"
                for part in output.get("content", [])
                if part.get("type") == "output_text"
            )
            # Retain usage and response id even on refusals, truncation or invalid JSON.
            structured = text
            try:
                json.loads(text)
            except ValueError:
                structured = "null"
            if result.get("status") != "completed":
                structured = "null"
            usage = result.get("usage") or {}
            return ModelResponse(
                execution_id=request.execution_id,
                request_id=request.request_id,
                provider_request_id=result.get("id"),
                model=ModelIdentity(engine="openai", model_id=result["model"]),
                effective_parameters=ModelParameters(
                    max_output_tokens=result.get(
                        "max_output_tokens", request.parameters.max_output_tokens
                    ),
                    temperature=result.get("temperature"),
                    response_format=request.parameters.response_format,
                ),
                capabilities_used=self.capabilities.used_by(request.parameters),
                text=text,
                structured_json=structured,
                usage=TokenUsage(
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    reasoning_tokens=(usage.get("output_tokens_details") or {}).get(
                        "reasoning_tokens"
                    ),
                )
                if usage
                else None,
                elapsed_seconds=time.perf_counter() - started,
                retry_count=retries,
                diagnostic_error_codes=tuple(errors),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ProviderFailure(
                "invalid_response",
                retry_count=retries,
                elapsed_seconds=time.perf_counter() - started,
                errors=tuple(errors),
            ) from None
