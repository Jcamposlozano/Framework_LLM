"""Versioned, external configuration; no environment access in the domain core."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field

from extracteval.core.base import Contract, Digest, Identifier
from extracteval.core.hashing import content_hash
from extracteval.core.models import ModelParameters, ResponseFormat
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import ReconciliationPolicy, VerificationConfig


class Phase2Config(Contract):
    version: Identifier
    dictionary_path: str
    policy_path: str
    prompt_path: str
    prompt_version: Identifier
    verifier_model: Identifier = "gpt-4.1-mini"
    reconciler_model: Identifier | None = None
    max_output_tokens: int = Field(default=4096, gt=0)
    request_timeout: float = Field(default=60, gt=0, allow_inf_nan=False)
    allowed_metadata_keys: tuple[Identifier, ...] = ()
    mock_payload_path: str | None = None
    reconciler_engine: Literal["deterministic"] = "deterministic"


class GovernanceAuthorization(Contract):
    document_hash: Digest
    authorization_reference: Identifier
    institutional_authorization: bool
    personal_data_processing_authorized: bool
    appropriately_deidentified: bool
    retention_and_access_reviewed: bool
    provider_transfer_authorized: bool

    def validate_authorization(self, document_hash: str) -> None:
        checks = (
            self.institutional_authorization,
            self.personal_data_processing_authorized,
            self.appropriately_deidentified,
            self.retention_and_access_reviewed,
            self.provider_transfer_authorized,
        )
        if self.document_hash != document_hash or not all(checks):
            raise ValueError("Complete governance authorization bound to this document is required")


def load_configuration(
    path: Path,
    environment: Mapping[str, str],
    mode: Literal["mock", "real"],
) -> tuple[Phase2Config, OperationalDictionary, ReconciliationPolicy, VerificationConfig]:
    config = Phase2Config.model_validate_json(path.read_bytes())
    root = path.resolve().parent
    import json

    raw_dictionary = json.loads((root / config.dictionary_path).read_bytes())
    if not isinstance(raw_dictionary, dict):
        raise ValueError("Dictionary must be a JSON object")
    dictionary = OperationalDictionary.model_validate(raw_dictionary)
    digest = content_hash({k: v for k, v in raw_dictionary.items() if k != "artifact"})
    if digest != dictionary.artifact.sha256:
        raise ValueError("Dictionary content does not match its versioned digest")
    policy = ReconciliationPolicy.model_validate_json((root / config.policy_path).read_bytes())
    prompt = (root / config.prompt_path).read_text(encoding="utf-8")
    verifier_config = VerificationConfig(
        version=config.version,
        model_id=(
            "mock-verifier"
            if mode == "mock"
            else environment.get("EXTRACTEVAL_VERIFIER_MODEL", config.verifier_model)
        ),
        reconciler_model_id=environment.get(
            "EXTRACTEVAL_RECONCILER_MODEL", config.reconciler_model
        ),
        parameters=ModelParameters(
            max_output_tokens=int(
                environment.get("EXTRACTEVAL_MAX_OUTPUT_TOKENS", config.max_output_tokens)
            ),
            response_format=ResponseFormat.STRUCTURED,
        ),
        timeout_seconds=float(
            environment.get("EXTRACTEVAL_REQUEST_TIMEOUT", config.request_timeout)
        ),
        prompt=prompt,
        prompt_version=config.prompt_version,
        allowed_metadata_keys=config.allowed_metadata_keys,
    )
    return config, dictionary, policy, verifier_config
