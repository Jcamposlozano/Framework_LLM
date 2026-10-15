"""Plantilla editable para validar UN valor propio con contratos de la Fase 1.

No extrae información: VALOR_REGISTRADO lo suministra el usuario. No llama a LLM.
Editar el bloque indicado y ejecutar con --salida apuntando a una carpeta nueva.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from extracteval import __version__
from extracteval.core.base import ArtifactRef, Contract
from extracteval.core.documents import (
    Document,
    Evidence,
    EvidenceAssessment,
    EvidenceAvailability,
    EvidenceSufficiency,
)
from extracteval.core.experiments import ConfigRef, ExperimentConfig, RunManifest
from extracteval.core.results import ExtractionResult, OperationStatus, ResultTrace
from extracteval.core.specification import (
    CategoryValue,
    InformationPolicy,
    OperationalDictionary,
    SemanticValue,
    VariableDefinition,
)

# ================= EDITA ESTE BLOQUE PARA TU PRUEBA =================
DOCUMENTO_ID = "mi-documento-001"  # Pseudónimo, sin espacios ni datos identificables.
TEXTO = "Documento ficticio. El estado de la solicitud es aprobado."
VARIABLE = VariableDefinition(
    variable_id="estado_solicitud",
    version="1",
    data_type="categorical",
    categories=("aprobado", "denegado", "indeterminado"),
    operational_definition="Estado de la solicitud expresamente indicado en el documento.",
    interpretation_rules=("No deducir aprobación por ausencia de una denegación.",),
    correctness_criteria=("Coincidencia de categoría con una referencia independiente.",),
    information_policy=InformationPolicy(
        absent="No registrar valor cuando no se informa el estado.",
        indeterminate="Usar indeterminado si el documento expresa incertidumbre.",
        not_applicable="Definir una representación externa si procede en el estudio.",
    ),
)
# Escribe aquí el valor que quieres VALIDAR. El programa no lo obtiene del texto.
VALOR_REGISTRADO: SemanticValue | None = CategoryValue(value="aprobado")
# Una cita es evidencia declarada por ti; el programa no la localiza ni la verifica.
# Usa None para dejar la evidencia como no evaluada.
CITA: str | None = "El estado de la solicitud es aprobado."
VERSION_DICCIONARIO = "1"
VERSION_CONFIGURACION = "1"
# ================= FIN DEL BLOQUE EDITABLE ==========================


def encode(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact(name: str, version: str, content: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name, version=version, sha256=hashlib.sha256(content).hexdigest()
    )


def run(output: Path) -> None:
    started = datetime.now(UTC)
    definitions = encode({"variables": [VARIABLE.model_dump(mode="json")]})
    dictionary_ref = artifact("mi-diccionario", VERSION_DICCIONARIO, definitions)
    dictionary = OperationalDictionary(artifact=dictionary_ref, variables=(VARIABLE,))
    schema = encode(ExtractionResult.model_json_schema())
    schema_ref = artifact("esquema-resultados", "1", schema)
    config = ExperimentConfig(
        config_id="mi-prueba-manual",
        version=VERSION_CONFIGURACION,
        dictionary=dictionary_ref,
        output_schema=schema_ref,
    )
    document = Document(document_id=DOCUMENTO_ID, text=TEXTO)
    evidence = EvidenceAssessment(
        availability=(
            EvidenceAvailability.AVAILABLE
            if CITA is not None
            else EvidenceAvailability.NOT_ASSESSED
        ),
        sufficiency=EvidenceSufficiency.NOT_ASSESSED,
        items=(Evidence(document_id=document.document_id, quote=CITA),) if CITA is not None else (),
    )
    # Identificador nuevo por ejecución; no se usa un identificador de proveedor.
    from uuid import uuid4

    execution_id = f"manual-{uuid4().hex}"
    result = ExtractionResult(
        result_id=f"resultado-{uuid4().hex}",
        trace=ResultTrace(
            document_id=document.document_id,
            variable_id=VARIABLE.variable_id,
            dictionary=dictionary_ref,
            config=ConfigRef.from_config(config),
            execution_id=execution_id,
            output_schema=schema_ref,
            # No se declara un modelo porque esta prueba registra un valor manual.
        ),
        operation=OperationStatus.COMPLETED,
        value=VALOR_REGISTRADO,
        evidence=evidence,
    )
    result.validate_against(dictionary)
    result.trace.validate_config(config)
    result_content = encode(result.model_dump(mode="json"))
    document_content = encode(document.model_dump(mode="json"))
    manifest = RunManifest(
        execution_id=execution_id,
        config=ConfigRef.from_config(config),
        package_version=__version__,
        started_at=started,
        finished_at=datetime.now(UTC),
        inputs=(dictionary_ref, schema_ref, artifact("documento", "1", document_content)),
        outputs=(artifact("resultado", "1", result_content),),
    )
    manifest.validate_against(config)
    # Se valida todo antes de crear la carpeta; un valor fuera del dominio no deja una ejecución.
    files = {
        "dictionary-payload.json": definitions,
        "output-schema.json": schema,
        "document.json": document_content,
        "extraction.json": result_content,
    }
    contracts: dict[str, Contract] = {
        "dictionary.json": dictionary,
        "config.json": config,
        "manifest.json": manifest,
    }
    files.update({name: encode(obj.model_dump(mode="json")) for name, obj in contracts.items()})
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        with (output / name).open("xb") as stream:
            stream.write(content)
    recovered = ExtractionResult.model_validate_json((output / "extraction.json").read_bytes())
    recovered.validate_against(dictionary)
    recovered.trace.validate_config(config)
    assert recovered == result
    print("PRUEBA DE CONTRATOS CORRECTA")
    print(f"Variable validada: {VARIABLE.variable_id}")
    print(f"Archivos guardados: {len(files)}")
    print(f"Carpeta: {output.resolve()}")
    print("El valor fue suministrado por ti. No se ejecutó extracción ni se midió exactitud.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", required=True, type=Path, help="Carpeta nueva para esta prueba")
    args = parser.parse_args()
    if args.salida.exists():
        parser.error("La carpeta ya existe. Elige otra para no sobrescribir resultados.")
    run(args.salida)


if __name__ == "__main__":
    main()
