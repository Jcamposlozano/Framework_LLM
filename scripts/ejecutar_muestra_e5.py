"""Ejecutar A → V → B en la muestra E5 registrada, de forma reanudable."""

import argparse
import hashlib
import json
import os
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path

from laboratorio_yaml_json import LabError, read_json
from pydantic import ValidationError
from verificacion_laboratorio import ensure_current_source, immutable_json

from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import GovernanceAuthorization, load_configuration
from extracteval.application.extraction import ExtractionExecution, load_extractor
from extracteval.cli import main as extracteval_cli
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.verification import (
    ExtractionSnapshot,
    ReconciledExtraction,
    VerificationInput,
    VerificationRunManifest,
)

VERSION = "e5-b-negacion-v1"
OVERRIDES = (
    "EXTRACTEVAL_EXTRACTOR_MODEL",
    "EXTRACTEVAL_EXTRACTOR_MAX_OUTPUT_TOKENS",
    "EXTRACTEVAL_EXTRACTOR_REQUEST_TIMEOUT",
    "EXTRACTEVAL_VERIFIER_MODEL",
    "EXTRACTEVAL_RECONCILER_MODEL",
    "EXTRACTEVAL_MAX_OUTPUT_TOKENS",
    "EXTRACTEVAL_REQUEST_TIMEOUT",
)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def documents_for_e5(lab: Path) -> list[Document]:
    draw = lab / "02_diseno/muestra_expertos_361/registro_sorteo.json"
    ids = read_json(draw)["document_ids"]
    if len(ids) != 361 or len(set(ids)) != len(ids):
        raise LabError("El sorteo debe identificar 361 notas únicas.")
    reference = lab / "04_referencia/referencia_consolidada_e4.json"
    plan = read_json(lab / "05_validez/plan_puntuacion_e5.json")
    sources = read_json(reference)["fuentes"]
    if plan["referencia_e4_sha256"] != file_digest(reference) or sources[
        "sorteo_sha256"
    ] != file_digest(draw):
        raise LabError("El sorteo, la referencia E4 y el plan E5 no coinciden.")
    if (
        plan["estado"] != "regla_de_puntuacion_aprobada"
        or plan["denominador_comun_pgec"] != 1809
        or {pair["document_id"] for pair in plan["pares"]} != set(ids)
    ):
        raise LabError("La cobertura del plan E5 difiere del sorteo.")
    if sources["especificacion_sha256"] != file_digest(
        lab / "01_especificacion/especificacion.json"
    ):
        raise LabError("La especificación E1 difiere de la usada en E4.")

    source = lab / "datos/documentos.json"
    expected_hash = read_json(lab / "02_diseno/caracterizacion-documental.json")["source"]["sha256"]
    source_bytes = source.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != expected_hash:
        raise LabError("El corpus difiere de la versión caracterizada en E2.")
    selected = set(ids)
    rows = [row for row in json.loads(source_bytes) if row["document_id"] in selected]
    documents = {row["document_id"]: Document.model_validate(row) for row in rows}
    if len(rows) != len(ids) or selected != documents.keys():
        raise LabError("El corpus no contiene exactamente una copia de cada nota del sorteo.")
    if any(not doc.text or not doc.text.strip() for doc in documents.values()):
        raise LabError("La muestra incluye notas sin texto local.")
    return [documents[doc_id] for doc_id in ids]


def run_document(
    document: Document,
    output: Path,
    authorization: GovernanceAuthorization,
    a_config: Path,
    v_config: Path,
) -> None:
    document_path = output / "documento.json"
    governance_path = output / "gobierno.json"
    immutable_json(document_path, document.model_dump(mode="json"))
    scoped = authorization.model_copy(update={"document_hash": content_hash(document)})
    immutable_json(governance_path, scoped.model_dump(mode="json"))
    common = ["--mode", "real", "--authorize-real", "--governance", str(governance_path)]

    a_dir = output / "a"
    if extracteval_cli(
        [
            "extract",
            "--config",
            str(a_config),
            "--input",
            str(document_path),
            "--output",
            str(a_dir),
            *common,
        ]
    ):
        raise LabError("A terminó con un fallo o quedó interrumpida. Revisa su manifiesto.")
    a_store = JSONRunStore(a_dir)
    a = a_store.get("extraction_a", ExtractionSnapshot)
    extraction = a_store.get("execution", ExtractionExecution)
    if extraction.extraction_a != a or extraction.document_hash != scoped.document_hash:
        raise LabError("A no coincide con la nota y la ejecución persistidas.")

    entry = output / "entrada-vb.json"
    immutable_json(
        entry, VerificationInput(document=document, extraction_a=a).model_dump(mode="json")
    )
    vb_dir = output / "vb"
    if extracteval_cli(
        [
            "verify",
            "--config",
            str(v_config),
            "--input",
            str(entry),
            "--output",
            str(vb_dir),
            "--stage",
            "all",
            *common,
        ]
    ):
        raise LabError("V/B terminó con un fallo o quedó interrumpida. Revisa sus artefactos.")

    store = JSONRunStore(vb_dir)
    manifest = store.get("manifest-all", VerificationRunManifest)
    b = store.get("extraction_b", ReconciledExtraction)
    if (
        store.get("extraction_a", ExtractionSnapshot) != a
        or manifest.mode != "real"
        or manifest.status != "completed"
        or b.document_hash != scoped.document_hash
        or b.base_extraction_id != a.base_extraction_id
        or b.base_extraction_hash != content_hash(a)
        or manifest.base_extraction_hash != b.base_extraction_hash
        or manifest.document_id != b.document_id
        or manifest.reconciliation_id != b.reconciliation_id
    ):
        raise LabError("El manifiesto no acredita el vínculo de B con la A guardada.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laboratorio", type=Path, required=True)
    parser.add_argument("--gobierno-base", type=Path, required=True)
    parser.add_argument("--ejecutar", action="store_true", help="Ejecutar A y V en OpenAI.")
    parser.add_argument("--limite", type=int, default=361, help="Primeras N notas del sorteo.")
    args = parser.parse_args()
    if not 1 <= args.limite <= 361:
        parser.error("--limite debe estar entre 1 y 361.")
    lab = args.laboratorio.resolve()
    output = lab / "ejecuciones" / VERSION
    position = None
    try:
        if any(name in os.environ for name in OVERRIDES):
            raise LabError(
                "Hay variables que sobrescriben la configuración. Usa la versión fijada."
            )
        documents = documents_for_e5(lab)
        authorization = GovernanceAuthorization.model_validate_json(args.gobierno_base.read_bytes())
        authorization.validate_authorization(content_hash(documents[0]))

        v_root = ensure_current_source(lab, VERSION)
        v_config = v_root / "config.json"
        a_config = lab / "configuraciones/extraccion" / VERSION / "config.json"
        settings, dictionary, _ = load_extractor(a_config, {})
        _, v_dictionary, policy, verifier = load_configuration(v_config, {}, "real")
        source = read_json(v_root / "fuente.json")
        reference = read_json(lab / "04_referencia/referencia_consolidada_e4.json")
        if (
            dictionary != v_dictionary
            or source["source_dictionary"] != reference["diccionario"]
            or not dictionary.clinically_approved
            or policy.version != "epoc-negacion-explicita.v1"
            or not source.get("replacement_policy_sha256")
        ):
            raise LabError("La configuración no corresponde al perfil aprobado de A/B.")

        print(f"Muestra E5 verificada: {len(documents)} notas.")
        print(f"Modelos configurados: A={settings.model}; V={verifier.model_id}.")
        if not args.ejecutar:
            print("Ensayo local completado. Llamadas externas: 0.")
            return
        if not os.environ.get("OPENAI_API_KEY"):
            raise LabError("Falta OPENAI_API_KEY en el entorno local.")

        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (output / ".ejecucion.lock").open("a", encoding="utf-8") as lock:
            try:
                flock(lock, LOCK_EX | LOCK_NB)
            except BlockingIOError:
                raise LabError("Ya hay una ejecución activa para esta versión.") from None
            immutable_json(
                output / "lote.json",
                {
                    "version": VERSION,
                    "documentos": [content_hash(doc) for doc in documents],
                    "config_a_sha256": file_digest(a_config),
                    "config_v_sha256": file_digest(v_config),
                    "huellas_config": file_digest(v_root / "fuente.json"),
                    "gobierno_base_sha256": content_hash(authorization),
                    "plan_e5_sha256": file_digest(lab / "05_validez/plan_puntuacion_e5.json"),
                },
            )
            for position, document in enumerate(documents[: args.limite], 1):
                run_document(
                    document, output / f"nota-{position:03d}", authorization, a_config, v_config
                )
                print(f"Notas completadas o recuperadas: {position}/{args.limite}", flush=True)
    except LabError as error:
        location = f"Nota {position}. " if position is not None else ""
        parser.exit(2, f"{location}{error}\n")
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        parser.exit(2, "No se pudo validar o completar el lote. Revisa los artefactos locales.\n")


if __name__ == "__main__":
    main()
