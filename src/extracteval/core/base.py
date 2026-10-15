"""Shared validation and versioned artifact references."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$"
    ),
]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]


class Contract(BaseModel):
    """Reject unknown fields and keep input contents out of exception strings.

    Structured validation diagnostics must use errors(include_input=False).
    Frozen models prevent attribute replacement, not mutation of nested dictionaries.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    contract_version: Literal["1.0"] = "1.0"


class ArtifactRef(Contract):
    artifact_id: Identifier
    version: Identifier
    sha256: Digest
