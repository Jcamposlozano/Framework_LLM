"""Persist blind reading before comparison; resume only when fingerprints match."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from extracteval import __version__
from extracteval.application.comparison import compare_extractions
from extracteval.application.reconciliation import reconcile
from extracteval.application.verification import IndependentVerifier, independent_request
from extracteval.core.base import Contract, Digest, Identifier
from extracteval.core.hashing import content_hash
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import (
    ExtractionSnapshot,
    IndependentVerification,
    ReconciledExtraction,
    ReconciliationDecision,
    ReconciliationPolicy,
    VerificationConfig,
    VerificationInput,
    VerificationRunManifest,
    VerificationStore,
)


class RunContext(Contract):
    run_id: Identifier
    input_hash: Digest
    started_at: str


class RunConfiguration(Contract):
    dictionary: OperationalDictionary
    policy: ReconciliationPolicy
    verifier: VerificationConfig
    mode: Literal["mock", "real"]
    mock_payload_hash: str | None = None


def run_verification(
    inputs: VerificationInput,
    dictionary: OperationalDictionary,
    policy: ReconciliationPolicy,
    config: VerificationConfig,
    store: VerificationStore,
    verifier: IndependentVerifier | None,
    *,
    stage: Literal["independent", "compare", "reconcile", "all"] = "all",
    mode: Literal["mock", "real"] = "mock",
    mock_payload_hash: str | None = None,
) -> VerificationRunManifest:
    # Check earlier stages before consuming their results or producing any downstream artifact.
    for name in ("manifest-independent", "manifest-compare", "manifest-all"):
        if store.exists(name):
            previous = store.get(name, VerificationRunManifest)
            hashes = store.artifact_hashes()
            if content_hash(previous.artifact_hashes) != previous.output_hash or any(
                hashes.get(k) != v for k, v in previous.artifact_hashes.items()
            ):
                raise ValueError("Persisted artifacts failed manifest integrity check")
    document, original = inputs.document, inputs.extraction_a
    # A copy protects the caller from nested mutations; A is serialized separately, without edits.
    document = document.model_copy(deep=True)
    original = original.model_copy(deep=True) if original else None
    if original is not None:
        for result in original.results:
            result.validate_against(dictionary)
    if original is not None and (
        original.document_id != document.document_id or original.dictionary != dictionary.artifact
    ):
        raise ValueError("Original extraction does not match document and dictionary")
    request = independent_request(document, dictionary, config)
    run_config = RunConfiguration(
        dictionary=dictionary,
        policy=policy,
        verifier=config,
        mode=mode,
        mock_payload_hash=mock_payload_hash,
    )
    # Independent stage may be run before A is supplied; A is bound with create-only storage later.
    fingerprint = content_hash(
        {
            "document": document.model_dump(mode="json"),
            "configuration": run_config.model_dump(mode="json"),
        }
    )
    if store.exists("context"):
        context = store.get("context", RunContext)
        if context.input_hash != fingerprint:
            raise ValueError("Resume inputs or configuration differ from persisted run")
    else:
        context = RunContext(
            run_id="run-" + uuid4().hex,
            input_hash=fingerprint,
            started_at=datetime.now(UTC).isoformat(),
        )
        store.put("context", context)
    store.put("document", document)
    store.put("configuration", run_config)
    if original is not None:
        store.put("extraction_a", original)
    elif stage != "independent" and store.exists("extraction_a"):
        original = store.get("extraction_a", ExtractionSnapshot)
    if stage != "independent" and original is None:
        raise ValueError("Comparison and reconciliation require original extraction A")
    if store.exists("verification"):
        verification = store.get("verification", IndependentVerification)
        if (
            verification.input_hash != content_hash(request)
            or verification.document_hash != content_hash(document)
            or verification.dictionary != dictionary.artifact
        ):
            raise ValueError("Persisted verification provenance mismatch")
    elif stage in ("compare", "reconcile"):
        raise ValueError("Persist independent verification before requesting this stage")
    else:
        if verifier is None:
            raise ValueError("A verifier adapter is required for independent reading")
        verification = verifier.verify_independently(document, dictionary, config)
        store.put("verification", verification)
    # From here onward, reading is durably persisted before any comparison sees A.
    reconciled: ReconciledExtraction | None = None
    if stage != "independent":
        assert original is not None
        comparison = compare_extractions(original, verification, dictionary, document)
        store.put("comparison", comparison)
        if stage in ("reconcile", "all"):
            reconciled = reconcile(document, original, verification, comparison, policy, dictionary)
            store.put("decisions", DecisionArtifact(decisions=reconciled.decisions))
            store.put("extraction_b", reconciled)
    hashes = store.artifact_hashes()
    manifest_name = "manifest-" + ("all" if stage in ("all", "reconcile") else stage)
    if store.exists(manifest_name):
        previous = store.get(manifest_name, VerificationRunManifest)
        # Later stages may add artifacts; validate every artifact named in this stage's manifest.
        if any(hashes.get(k) != v for k, v in previous.artifact_hashes.items()):
            raise ValueError("Persisted artifacts failed manifest integrity check")
        return previous
    manifest = VerificationRunManifest(
        run_id=context.run_id,
        document_id=document.document_id,
        base_extraction_id=original.base_extraction_id if original else None,
        base_extraction_hash=content_hash(original) if original else None,
        verification_id=verification.verification_id,
        reconciliation_id=reconciled.reconciliation_id if reconciled else None,
        dictionary_version=dictionary.artifact.version,
        prompt_version=config.prompt_version,
        model_config_version=config.version,
        policy_version=policy.version,
        input_hash=fingerprint,
        output_hash=content_hash(hashes),
        artifact_hashes=hashes,
        status="technical_failure" if verification.audit.error else "completed",
        mode=mode,
        package_version=__version__,
        started_at=context.started_at,
        finished_at=datetime.now(UTC).isoformat(),
    )
    store.put(manifest_name, manifest)
    return manifest


class DecisionArtifact(Contract):
    """Separately persisted audit of policy decisions."""

    decisions: tuple[ReconciliationDecision, ...]
