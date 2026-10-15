"""Safe boundary errors: no raw request, document or provider exception text."""


class ModelError(Exception):
    """Base error at the model boundary."""


class UnsupportedConfigurationError(ModelError):
    def __init__(self) -> None:
        super().__init__("Requested model configuration is not supported")


class ModelExecutionError(ModelError):
    def __init__(self) -> None:
        super().__init__("Simulated model execution failed")
