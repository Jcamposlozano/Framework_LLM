"""Reproduce the technical audit in a NEW lab, with all network connections blocked.

Usage: .venv/bin/python scripts/auditar_integracion.py --destino laboratorios/auditoria-001
Uses the existing extraction, verification and stability workflows. Never activates real calls.
"""

import argparse
import hashlib
import json
import socket
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import yaml
from estabilidad_laboratorio import artifact_tree, execute_stability, prepare_stability
from extraccion_laboratorio import demo_extraction, prepare_extraction
from laboratorio_yaml_json import create_simple, prepare_specification, write_json
from verificacion_laboratorio import REPOSITORY, prepare_verification

from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import GovernanceAuthorization, load_configuration
from extracteval.application.extraction import load_extractor
from extracteval.cli import main as cli
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.verification import ReconciledExtraction


def prepare_lab(destination: Path) -> Path:
    """Copy existing definitions and unapproved review rules without clinical edits."""
    create_simple(destination)
    _, original, _, _ = load_configuration(REPOSITORY / "configs/epoc/phase2.json", {}, "mock")
    specification = {
        "dictionary_id": original.artifact.artifact_id,
        "version": original.artifact.version,
        "status": "borrador",
        "variables": {
            v.variable_id: {
                "version": v.version,
                "type": v.data_type,
                "definition": v.operational_definition,
                "allowed_values": list(v.categories),
                "interpretation_rules": list(v.interpretation_rules),
                "correctness_criteria": list(v.correctness_criteria),
                "information_policy": v.information_policy.model_dump(mode="json"),
                "normalization_rules": list(v.normalization_rules),
            }
            for v in original.variables
        },
        "consistency_checks": [
            {
                "id": rule.rule_id,
                "if": {k: v.value if v is not None else None for k, v in rule.when.items()},
                "then": {k: v.value if v is not None else None for k, v in rule.expected.items()},
            }
            for rule in original.review_rules
        ],
    }
    (destination / "01_especificacion/especificacion.yaml").write_text(
        yaml.safe_dump(specification, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    prepare_specification(destination)
    prepare_verification(destination)
    config = prepare_extraction(destination)
    _, copied, _ = load_extractor(config, {})
    if copied != original:
        raise ValueError("The audit must preserve the existing dictionary exactly")
    return destination


def audit(destination: Path) -> dict[str, object]:
    lab = prepare_lab(destination)
    first = demo_extraction(lab)
    demo_root = lab / "ejecuciones/fase2/demo-extractor-v1"
    before_demo = artifact_tree(demo_root)
    second = demo_extraction(lab)
    if (
        second["a_mock_calls_this_invocation"] != 0
        or second["v_mock_calls_this_invocation"] != 0
        or artifact_tree(demo_root) != before_demo
    ):
        raise ValueError("A/V/B resume changed artifacts or called a model")
    b = JSONRunStore(demo_root / "b").get("extraction_b", ReconciledExtraction)
    a_bytes = (demo_root / "a/extraction_a.json").read_bytes()
    if b.base_extraction_hash != hashlib.sha256(a_bytes).hexdigest():
        raise ValueError("B does not preserve A's byte hash")
    prepare_stability(lab)
    stability = execute_stability(lab)
    if (
        len(stability["ejecuciones"]) != 100
        or len({r["repetition_id"] for r in stability["ejecuciones"]}) != 100
        or stability["consumo"]["intentos_generate"] != 160
        or stability["consumo"]["respuestas_registradas"] != 157
        or stability["consumo"]["llamadas_externas"] != 0
        or Counter(r["estado"] for r in stability["ejecuciones"])
        != {"completed": 97, "technical_failure": 3}
    ):
        raise ValueError("The scripted pilot did not produce its expected technical outcomes")
    experiment_root = lab / "ejecuciones/estabilidad/piloto-mock-v1"
    before_stability = artifact_tree(experiment_root)
    if execute_stability(lab) != stability or artifact_tree(experiment_root) != before_stability:
        raise ValueError("Stability resume changed results or artifacts")
    for row in stability["ejecuciones"]:
        raw = (experiment_root / row["a_artifacts"] / "extraction_a.json").read_bytes()
        saved_b = JSONRunStore(experiment_root / row["vb_artifacts"]).get(
            "extraction_b", ReconciledExtraction
        )
        if hashlib.sha256(raw).hexdigest() != row["base_extraction_hash"] or (
            saved_b.base_extraction_hash != row["base_extraction_hash"]
        ):
            raise ValueError("A/B hash mismatch in a stability repetition")
    cfg_a = lab / "configuraciones/extraccion/v1"
    document = Document.model_validate_json((cfg_a / "demo-documento.json").read_bytes())
    governance = GovernanceAuthorization(
        document_hash=content_hash(document),
        authorization_reference="pending-synthetic-trial-review",
        institutional_authorization=False,
        personal_data_processing_authorized=False,
        appropriately_deidentified=False,
        retention_and_access_reviewed=False,
        provider_transfer_authorized=False,
    )
    # This is an unapproved template, never an authorization fabricated by the audit.
    write_json(
        lab / "primera_prueba/gobierno.pendiente.json",
        governance.model_dump(mode="json"),
        exclusive=True,
        private=True,
    )
    if (
        cli(
            [
                "extract",
                "--config",
                str(cfg_a / "config.json"),
                "--input",
                str(cfg_a / "demo-documento.json"),
                "--output",
                str(lab / "primera_prueba/a"),
                "--mode",
                "real",
                "--dry-run",
            ]
        )
        != 0
    ):
        raise ValueError("Real configuration dry run failed")
    summary = {
        "mode": "mock",
        "provider_calls": 0,
        "network_connections_blocked": True,
        "real_execution_enabled": False,
        "clinically_validated": False,
        "dictionary_preserved_exactly": True,
        "a_v_b": {
            "variables": first["variables"],
            "a_sha256": b.base_extraction_hash,
            "decisions": dict(Counter(d.action.value for d in b.decisions)),
            "resume_mock_calls": {
                "A": second["a_mock_calls_this_invocation"],
                "V": second["v_mock_calls_this_invocation"],
            },
            "artifact_hashes": before_demo,
        },
        "phase3": {
            "documents": stability["documentos"],
            "repetitions": len(stability["ejecuciones"]),
            "unique_repetition_ids": len({r["repetition_id"] for r in stability["ejecuciones"]}),
            "outcomes": dict(Counter(r["estado"] for r in stability["ejecuciones"])),
            "consumption": stability["consumo"],
            "concordance": stability["concordancia"],
            "resume_identical": True,
            "integrity_sha256": hashlib.sha256(
                (experiment_root / "integridad.json").read_bytes()
            ).hexdigest(),
        },
    }
    write_json(lab / "auditoria.json", summary, exclusive=True, private=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", required=True, type=Path)
    args = parser.parse_args()
    connection_attempts = []

    def blocked_connection(*args: object, **kwargs: object) -> None:
        connection_attempts.append(True)
        raise AssertionError("Network is forbidden in the synthetic audit")

    with (
        patch.object(socket, "create_connection", blocked_connection),
        patch.object(socket.socket, "connect", blocked_connection),
    ):
        result = audit(args.destino.resolve())
    if connection_attempts:
        raise AssertionError("The audit attempted a forbidden network connection")
    print(
        json.dumps(
            {
                "audit": str(args.destino / "auditoria.json"),
                "provider_calls": result["provider_calls"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
