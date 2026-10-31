"""Personal consent for a bundled synthetic fixture; clinical governance is unchanged."""

import json
from pathlib import Path
from typing import Literal

from pydantic import StrictBool

from extracteval.application.configuration import GovernanceAuthorization
from extracteval.core.base import Contract, Digest, Identifier
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash

# Reviewed, invented fixture from scripts/extraccion_laboratorio.synthetic_extraction.
# This is the canonical hash of the ENTIRE Document, including all metadata and sections.
# Never accept a caller-supplied fixture registry, expected hash or synthetic flag.
DEMO_DOCUMENT_SHA256 = "ec6d1883c667b563cb0801e3941481abc831d3a30d6fdaf7bd746b90fbf3421a"


class PersonalSyntheticAuthorization(Contract):
    mode: Literal["personal_synthetic_development"]
    authorization_reference: Identifier
    fixture_id: Literal["extracteval.demo-extractor-epoc.v1"]
    document_id: Literal["demo-extractor-epoc-001"]
    document_hash: Digest
    operation: Literal["extract_a"]
    provider: Literal["openai"]
    model_id: Literal["gpt-4.1-mini"]
    external_calls_authorized: StrictBool
    verification_method: Literal["bundled_fixture_sha256"] = "bundled_fixture_sha256"

    def validate_document(self, document: Document, model_id: str) -> None:
        actual_hash = content_hash(document)
        if (
            not self.external_calls_authorized
            or self.model_id != model_id
            or document.document_id != self.document_id
            or actual_hash != DEMO_DOCUMENT_SHA256
            or self.document_hash != actual_hash
        ):
            raise ValueError("Personal consent requires the exact bundled synthetic document")


def load_extraction_authorization(
    path: Path, document: Document, model_id: str
) -> GovernanceAuthorization | PersonalSyntheticAuthorization:
    """Personal consent applies only to A; V and stability retain institutional gates.

    Legacy institutional files deliberately retain their existing format and validator.
    Unknown modes and mixed institutional/personal fields fail closed.
    """
    raw = json.loads(path.read_bytes())
    if isinstance(raw, dict) and raw.get("mode") == "personal_synthetic_development":
        personal = PersonalSyntheticAuthorization.model_validate(raw)
        personal.validate_document(document, model_id)
        return personal
    institutional = GovernanceAuthorization.model_validate(raw)
    institutional.validate_authorization(content_hash(document))
    return institutional
