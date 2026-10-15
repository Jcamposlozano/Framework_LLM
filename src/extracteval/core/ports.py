"""Structural interfaces with no dependency on infrastructure implementations."""

from typing import Protocol, runtime_checkable

from extracteval.core.base import ArtifactRef
from extracteval.core.models import ModelCapabilities, ModelIdentity, ModelRequest, ModelResponse
from extracteval.core.results import ExtractionResult


@runtime_checkable
class ModelPort(Protocol):
    @property
    def identity(self) -> ModelIdentity: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def generate(self, request: ModelRequest) -> ModelResponse: ...


class DocumentResolver(Protocol):
    def resolve(self, text_ref: str) -> str: ...


class ResultRepository(Protocol):
    """Implementations must reject duplicate result identifiers, never overwrite."""

    def add(self, result: ExtractionResult) -> None: ...

    def get(self, result_id: str) -> ExtractionResult: ...


class ArtifactStore(Protocol):
    """Implementations verify digests and never overwrite an artifact version."""

    def put(self, reference: ArtifactRef, content: bytes) -> None: ...

    def get(self, reference: ArtifactRef) -> bytes: ...
