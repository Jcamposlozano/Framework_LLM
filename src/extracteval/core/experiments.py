"""Versioned configuration and content-safe execution manifests."""

import hashlib
import json
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from extracteval.core.base import ArtifactRef, Contract, Digest, Identifier
from extracteval.core.models import ModelCapabilities, ModelIdentity, ModelParameters


class ModelBinding(Contract):
    adapter_id: Identifier
    model: ModelIdentity
    parameters: ModelParameters = Field(default_factory=ModelParameters)


class ExperimentConfig(Contract):
    config_id: Identifier
    version: Identifier
    dictionary: ArtifactRef
    output_schema: ArtifactRef
    extractor_instructions: ArtifactRef | None = None
    verifier_instructions: ArtifactRef | None = None
    extractor: ModelBinding | None = None
    verifier: ModelBinding | None = None
    reconciliation_policy: ArtifactRef | None = None
    partition: ArtifactRef | None = None
    repetitions: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def instructions_for_models(self) -> Self:
        if self.extractor is not None and self.extractor_instructions is None:
            raise ValueError("Extractor binding requires an instruction reference")
        if self.verifier is not None and self.verifier_instructions is None:
            raise ValueError("Verifier binding requires an instruction reference")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ConfigRef(Contract):
    config_id: Identifier
    version: Identifier
    sha256: Digest

    @classmethod
    def from_config(cls, config: ExperimentConfig) -> "ConfigRef":
        return cls(config_id=config.config_id, version=config.version, sha256=config.fingerprint())


class ModelRunRecord(Contract):
    role: Literal["extractor", "verifier"]
    binding: ModelBinding
    capabilities: ModelCapabilities
    effective_parameters: ModelParameters
    limitations: tuple[
        Literal["exact_reproducibility_not_guaranteed", "model_version_unavailable"], ...
    ] = ()

    @model_validator(mode="after")
    def valid_parameters(self) -> Self:
        self.capabilities.validate_parameters(self.binding.parameters)
        # Capabilities constrain requests, not provider-reported defaults. For example,
        # Responses can report temperature=1 even when this adapter never requests it.
        # ModelParameters still validates the observed values and they remain auditable.
        if (
            not self.capabilities.exact_reproducibility
            and "exact_reproducibility_not_guaranteed" not in self.limitations
        ):
            raise ValueError("A reproducibility limitation must be recorded")
        if self.binding.model.model_version is None:
            if "model_version_unavailable" not in self.limitations:
                raise ValueError("Missing model version must be recorded as a limitation")
            if self.capabilities.exact_reproducibility:
                raise ValueError("Exact reproducibility requires a versioned model identity")
        return self


class RunManifest(Contract):
    execution_id: Identifier
    config: ConfigRef
    package_version: Identifier
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    repetition: int = Field(default=1, ge=1, strict=True)
    models: tuple[ModelRunRecord, ...] = ()
    inputs: tuple[ArtifactRef, ...] = ()
    outputs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def valid_run(self) -> Self:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("Run completion must not precede its start")
        roles = [record.role for record in self.models]
        if len(roles) != len(set(roles)):
            raise ValueError("Each model role must be recorded once")
        return self

    def validate_against(self, config: ExperimentConfig) -> None:
        if self.config != ConfigRef.from_config(config):
            raise ValueError("Manifest configuration reference does not match")
        if self.repetition > config.repetitions:
            raise ValueError("Run repetition exceeds configured repetitions")
        for record in self.models:
            binding = config.extractor if record.role == "extractor" else config.verifier
            if record.binding != binding:
                raise ValueError("Model run binding does not match configuration")
