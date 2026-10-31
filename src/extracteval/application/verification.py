"""Blind documentary reading. This use case has no extraction-A argument."""

import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import JsonValue, ValidationError

from extracteval.core.documents import Document, Evidence
from extracteval.core.exceptions import ModelError, ProviderFailure
from extracteval.core.hashing import content_hash
from extracteval.core.models import ModelRequest, ModelResponse
from extracteval.core.ports import ModelPort
from extracteval.core.results import TechnicalError
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import (
    CallAudit,
    IndependentVerification,
    VerificationConfig,
    VerificationPayload,
)


def evidence_findings(document: Document, evidence: tuple[Evidence, ...]) -> tuple[str, ...]:
    if not evidence:
        return ("evidence_missing",)
    findings: set[str] = set()
    for item in evidence:
        if item.document_id != document.document_id:
            findings.add("evidence_wrong_document")
        if document.text is None or not item.quote:
            findings.add("evidence_unverifiable")
            continue
        if item.start is not None and item.end is not None:
            if document.text[item.start : item.end] != item.quote or item.end > len(document.text):
                findings.add("evidence_offset_mismatch")
        elif item.quote not in document.text:
            findings.add("evidence_quote_not_found")
        if not item.section:
            findings.add("evidence_section_missing")
        else:
            section = next((s for s in document.sections if s.name == item.section), None)
            if section is None:
                findings.add("evidence_section_unverifiable")
            elif item.start is not None and item.end is not None:
                if not (section.start <= item.start < item.end <= section.end):
                    findings.add("evidence_section_mismatch")
            elif item.quote not in document.text[section.start : section.end]:
                findings.add("evidence_section_mismatch")
    return tuple(sorted(findings))


def strict_schema(schema: dict[str, Any]) -> dict[str, JsonValue]:
    """Convert Pydantic defaults to the supported strict object schema subset."""

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def independent_request(
    document: Document,
    dictionary: OperationalDictionary,
    config: VerificationConfig,
) -> ModelRequest:
    if document.text is None:
        raise ValueError("Resolve secure document references locally before verification")
    # Only explicitly permitted metadata crosses the port; provenance/entity_id are excluded.
    safe_document = Document(
        document_id=document.document_id,
        text=document.text,
        document_date=document.document_date,
        sections=document.sections,
        allowed_context={
            k: v for k, v in document.allowed_context.items() if k in config.allowed_metadata_keys
        },
    )
    content = json.dumps(
        {
            "document": safe_document.model_dump(mode="json"),
            "dictionary": dictionary.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    request_hash = content_hash({"content": content, "config": config.model_dump(mode="json")})
    return ModelRequest(
        execution_id="independent-" + request_hash[:24],
        request_id="request-" + request_hash[:24],
        instructions=config.prompt,
        content=content,
        parameters=config.parameters,
        response_schema=strict_schema(VerificationPayload.model_json_schema()),
        timeout_seconds=config.timeout_seconds,
    )


class IndependentVerifier:
    def __init__(self, model: ModelPort) -> None:
        self.model = model

    def verify_independently(
        self,
        document: Document,
        dictionary: OperationalDictionary,
        verifier_config: VerificationConfig,
    ) -> IndependentVerification:
        request = independent_request(document, dictionary, verifier_config)
        started = perf_counter()
        response: ModelResponse | None = None
        error = None
        retries = 0
        errors: tuple[str, ...] = ()
        payload = VerificationPayload(variables=())
        try:
            if self.model.identity.model_id != verifier_config.model_id:
                raise ValueError("Configured and bound verifier models differ")
            self.model.capabilities.validate_parameters(request.parameters)
            response = self.model.generate(request)
            retries = response.retry_count
            errors = response.diagnostic_error_codes
            if (
                response.execution_id != request.execution_id
                or response.request_id != request.request_id
            ):
                raise ValueError("Provider response identifiers do not match request")
            if response.structured_json is None:
                raise ValueError("Structured response required")
            payload = VerificationPayload.model_validate_json(response.structured_json)
            for variable in payload.variables:
                definition = dictionary.variable(variable.variable_id)
                if variable.proposed_value is not None:
                    definition.validate_value(variable.proposed_value)
        except ProviderFailure as exc:
            error = TechnicalError(code=exc.code, retryable=exc.code in ("timeout", "unavailable"))
            retries, errors = exc.retry_count, exc.errors
        except (ValidationError, ValueError, KeyError):
            error = TechnicalError(code="invalid_response")
        except ModelError:
            error = TechnicalError(code="unavailable", retryable=True)
        except Exception:
            # A provider implementation must never leak raw exception text into run logs.
            error = TechnicalError(code="internal_error")
        if error is not None:
            # An invalid payload is never partially promoted to clinical categories.
            payload = VerificationPayload(variables=())
            errors = (*errors, error.code)
        findings = {
            v.variable_id: evidence_findings(document, v.evidence) for v in payload.variables
        }
        request_hash = content_hash(request)
        return IndependentVerification(
            verification_id="verification-" + uuid4().hex,
            document_id=document.document_id,
            document_hash=content_hash(document),
            dictionary=dictionary.artifact,
            prompt_version=verifier_config.prompt_version,
            model_config_version=verifier_config.version,
            input_hash=request_hash,
            payload=payload,
            evidence_findings=findings,
            audit=CallAudit(
                requested_model=verifier_config.model_id,
                requested_parameters=verifier_config.parameters,
                response=response,
                error=error,
                elapsed_seconds=perf_counter() - started,
                retry_count=retries,
                errors=errors,
            ),
        )
