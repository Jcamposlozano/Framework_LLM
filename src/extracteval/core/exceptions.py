"""Safe boundary errors: no raw request, document or provider exception text."""

from typing import Literal, cast

TechnicalErrorCode = Literal["timeout", "unavailable", "invalid_response", "internal_error"]


class ModelError(Exception):
    """Base error at the model boundary."""


class UnsupportedConfigurationError(ModelError):
    def __init__(self) -> None:
        super().__init__("Requested model configuration is not supported")


class ModelExecutionError(ModelError):
    def __init__(self) -> None:
        super().__init__("Simulated model execution failed")


class ProviderFailure(ModelError):
    """Safe provider failure carrying only a closed code and operational telemetry."""

    def __init__(
        self,
        code: str,
        *,
        retry_count: int = 0,
        elapsed_seconds: float = 0,
        errors: tuple[str, ...] = (),
    ) -> None:
        safe = {"timeout", "unavailable", "invalid_response", "internal_error"}
        self.code = cast(TechnicalErrorCode, code if code in safe else "internal_error")
        self.retry_count = retry_count
        self.elapsed_seconds = elapsed_seconds
        self.errors = tuple(e for e in errors if e in safe | {"rate_limit", "server_error"})
        super().__init__(self.code)
