"""Complete a single synthetic A/V/B pilot using an existing, immutable A.

Preparation and inspection are offline. Real execution requires --mode real and
--autorizar-v-real; only the exact bundled synthetic fixture is accepted.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from extraccion_laboratorio import synthetic_extraction
from verificacion_laboratorio import ensure_current_source, immutable_json

from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.authorization import (
    DEMO_DOCUMENT_SHA256,
    PersonalSyntheticAuthorization,
)
from extracteval.application.comparison import compare_extractions
from extracteval.application.configuration import Phase2Config, load_configuration
from extracteval.application.extraction import ExtractionExecution, ExtractionManifest
from extracteval.application.reconciliation import reconcile
from extracteval.application.verification import evidence_findings
from extracteval.cli import main as verify_cli
from extracteval.core.documents import Document, Evidence
from extracteval.core.hashing import content_hash
from extracteval.core.verification import (
    ComparisonResult,
    ExtractionSnapshot,
    IndependentVerification,
    ReconciledExtraction,
    VerificationInput,
    VerificationRunManifest,
)


def locate_quote(document: Document, evidence: Evidence) -> dict[str, Any]:
    """Audit candidate offsets without changing evidence, A, V or B."""
    result: dict[str, Any] = {
        "original": evidence.model_dump(mode="json"),
        "findings": evidence_findings(document, (evidence,)),
        "candidate": None,
    }
    if evidence.document_id != document.document_id or document.text is None or not evidence.quote:
        result["status"] = "unverifiable"
        return result
    text, quote = document.text, evidence.quote
    positions, start = [], 0
    while (position := text.find(quote, start)) != -1:
        positions.append(position)
        start = position + 1  # Count overlapping matches too.
    if len(positions) != 1:
        result["status"] = "not_found" if not positions else "ambiguous"
        return result
    start, end = positions[0], positions[0] + len(quote)
    sections = [s.name for s in document.sections if s.start <= start < end <= s.end]
    if evidence.section not in sections:
        result["status"] = "section_mismatch"
        return result
    result["candidate"] = {"start": start, "end": end, "section": evidence.section}
    result["status"] = (
        "verified" if (evidence.start, evidence.end) == (start, end) else "unique_match"
    )
    return result


def context(lab: Path, source_a: Path, mode: str) -> dict[str, Any]:
    if not source_a.is_dir():
        raise ValueError("The existing A directory is required")
    source = JSONRunStore(source_a)
    manifest = source.get("manifest", ExtractionManifest)
    if source.artifact_hashes() != manifest.artifact_hashes:
        raise ValueError("A manifest integrity mismatch")
    execution = source.get("execution", ExtractionExecution)
    a = source.get("extraction_a", ExtractionSnapshot)
    config_root = ensure_current_source(lab, "v1")
    cfg, dictionary, policy, verifier = load_configuration(
        config_root / "config.json", os.environ, mode
    )
    document = Document.model_validate_json(
        (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
    )
    if (
        content_hash(document) != DEMO_DOCUMENT_SHA256
        or execution.document_hash != content_hash(document)
        or execution.input_hash != manifest.input_hash
        or execution.extraction_a != a
        or a.document_id != document.document_id
        or a.dictionary != dictionary.artifact
        or execution.audit.error is not None
        or (mode == "real" and execution.mode != "real")
        or {r.trace.variable_id for r in a.results} != {v.variable_id for v in dictionary.variables}
    ):
        raise ValueError("A must be a completed extraction of the exact synthetic fixture")
    if mode == "real" and verifier.model_id != "gpt-4.1-mini":
        raise ValueError("The personal synthetic pilot is limited to gpt-4.1-mini")
    for result in a.results:
        if result.operation != "completed":
            raise ValueError("A contains technical failures")
        result.validate_against(dictionary)
        result.trace.validate_config(execution.effective_configuration)
    source_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_a.glob("*.json")
    }
    fingerprint = content_hash(
        {
            "source": source_hashes,
            "document": document.model_dump(mode="json"),
            "dictionary": dictionary.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "verifier": verifier.model_dump(mode="json"),
            "mode": mode,
        }
    )
    return dict(
        document=document,
        a=a,
        execution=execution,
        cfg=cfg,
        dictionary=dictionary,
        policy=policy,
        verifier=verifier,
        config_root=config_root,
        source_hashes=source_hashes,
        fingerprint=fingerprint,
    )


def prepare(lab: Path, source_a: Path, destination: Path, mode: str) -> dict[str, Any]:
    if (
        destination == source_a
        or destination.is_relative_to(source_a)
        or source_a.is_relative_to(destination)
    ):
        raise ValueError("The new pilot and original A directories must not overlap")
    ctx = context(lab, source_a, mode)
    immutable_json(
        destination / "preparacion.json",
        {
            "mode": mode,
            "input_hash": ctx["fingerprint"],
            "base_extraction_hash": content_hash(ctx["a"]),
            "source_a_file_hashes": ctx["source_hashes"],
            "clinically_validated": False,
        },
    )
    immutable_json(
        destination / "entrada.json",
        VerificationInput(document=ctx["document"], extraction_a=ctx["a"]).model_dump(mode="json"),
    )
    immutable_json(
        destination / "revision-evidencia-a.json",
        {
            "applies_changes": False,
            "base_extraction_hash": content_hash(ctx["a"]),
            "variables": {
                r.trace.variable_id: [locate_quote(ctx["document"], e) for e in r.evidence.items]
                for r in ctx["a"].results
            },
        },
    )
    # The mock verifier fixture is independent of A's responses.
    fixture_doc, fixture = synthetic_extraction(ctx["dictionary"])
    if fixture_doc != ctx["document"]:
        raise ValueError("Mock fixture document mismatch")
    immutable_json(destination / "respuesta-v-mock.json", fixture.model_dump(mode="json"))
    cfg: Phase2Config = ctx["cfg"]
    config = cfg.model_dump(mode="json") | {
        "dictionary_path": str((ctx["config_root"] / cfg.dictionary_path).resolve()),
        "policy_path": str((ctx["config_root"] / cfg.policy_path).resolve()),
        "prompt_path": str((ctx["config_root"] / cfg.prompt_path).resolve()),
        "mock_payload_path": "respuesta-v-mock.json",
    }
    immutable_json(destination / "configuracion-v.json", config)
    immutable_json(destination / "integridad-preparacion.json", preparation_hashes(destination))
    return ctx


def preparation_hashes(destination: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
        for name in (
            "preparacion.json",
            "entrada.json",
            "revision-evidencia-a.json",
            "respuesta-v-mock.json",
            "configuracion-v.json",
        )
    }


def inspect_result(ctx: dict[str, Any], destination: Path) -> dict[str, Any]:
    integrity = json.loads((destination / "integridad-preparacion.json").read_bytes())
    if integrity != preparation_hashes(destination):
        raise ValueError("Prepared input or configuration integrity mismatch")
    saved = json.loads((destination / "preparacion.json").read_bytes())
    if saved["input_hash"] != ctx["fingerprint"]:
        raise ValueError("Pilot inputs or original A changed")
    if not (destination / "vb").is_dir():
        raise ValueError("There is no V/B execution to inspect")
    store = JSONRunStore(destination / "vb")
    manifest = store.get("manifest-all", VerificationRunManifest)
    if manifest.artifact_hashes != store.artifact_hashes() or manifest.output_hash != content_hash(
        manifest.artifact_hashes
    ):
        raise ValueError("V/B artifact integrity mismatch")
    verification = store.get("verification", IndependentVerification)
    comparison = store.get("comparison", ComparisonResult)
    b = store.get("extraction_b", ReconciledExtraction)
    if comparison != compare_extractions(
        ctx["a"], verification, ctx["dictionary"], ctx["document"]
    ) or b != reconcile(
        ctx["document"], ctx["a"], verification, comparison, ctx["policy"], ctx["dictionary"]
    ):
        raise ValueError("Saved comparison or B differs from deterministic recomputation")
    response = verification.audit.response
    summary = {
        "mode": manifest.mode,
        "status": manifest.status,
        "base_extraction_id": ctx["a"].base_extraction_id,
        "a_unchanged": b.base_extraction_hash == content_hash(ctx["a"]),
        "v_model": response.model.model_dump(mode="json") if response else None,
        "v_usage": response.usage.model_dump(mode="json") if response and response.usage else None,
        "v_error": verification.audit.error.model_dump(mode="json")
        if verification.audit.error
        else None,
        "v_evidence_findings": verification.evidence_findings,
        "b_decisions": [d.model_dump(mode="json") for d in b.decisions],
        "clinically_validated": False,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preparar", "ejecutar", "inspeccionar"))
    parser.add_argument("--laboratorio", type=Path, required=True)
    parser.add_argument("--extraccion-a", type=Path)
    parser.add_argument("--destino", type=Path, required=True)
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--autorizar-v-real", action="store_true")
    args = parser.parse_args(argv)
    lab, destination = args.laboratorio.resolve(), args.destino.resolve()
    source_a = (args.extraccion_a or lab / "ejecuciones/primera-a-personal-003").resolve()
    try:
        if args.autorizar_v_real and args.mode != "real":
            raise ValueError("Real consent cannot be mixed with mock mode")
        if args.action == "inspeccionar":
            summary = inspect_result(context(lab, source_a, args.mode), destination)
        else:
            if args.action == "ejecutar" and args.mode == "real" and not args.autorizar_v_real:
                raise ValueError("Separate explicit consent for real V is required")
            ctx = prepare(lab, source_a, destination, args.mode)
            if args.action == "preparar":
                print(
                    json.dumps(
                        {
                            "status": "prepared",
                            "provider_calls": 0,
                            "directory": str(destination),
                            "mode": args.mode,
                        }
                    )
                )
                return 0
            cli_args = [
                "verify",
                "--config",
                str(destination / "configuracion-v.json"),
                "--input",
                str(destination / "entrada.json"),
                "--output",
                str(destination / "vb"),
                "--mode",
                args.mode,
            ]
            if args.mode == "real":
                consent = PersonalSyntheticAuthorization(
                    mode="personal_synthetic_development",
                    authorization_reference="personal-synthetic-verification",
                    fixture_id="extracteval.demo-extractor-epoc.v1",
                    document_id="demo-extractor-epoc-001",
                    document_hash=content_hash(ctx["document"]),
                    operation="verify_v",
                    provider="openai",
                    model_id="gpt-4.1-mini",
                    external_calls_authorized=True,
                )
                immutable_json(
                    destination / "consentimiento-v.json", consent.model_dump(mode="json")
                )
                cli_args += [
                    "--authorize-real",
                    "--governance",
                    str(destination / "consentimiento-v.json"),
                ]
            code = verify_cli(cli_args)
            # Always check the original A again after the call or recovery.
            ctx = context(lab, source_a, args.mode)
            if not (destination / "vb/manifest-all.json").exists():
                return code or 2
            summary = inspect_result(ctx, destination)
            immutable_json(destination / "resultado.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2 if summary["status"] == "technical_failure" else 0
    except (OSError, ValueError, KeyError):
        print(json.dumps({"status": "error", "code": "invalid_pilot_input_consent_or_integrity"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
