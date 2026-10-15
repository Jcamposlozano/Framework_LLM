"""Tutorial sintético de Fase 1; no ejecuta un extractor ni llama a proveedores.

Uso: python examples/guia_paso_a_paso.py --salida /tmp/extracteval-tutorial-01
La carpeta de salida debe ser nueva. No se sobrescribe ninguna ejecución.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from extracteval import __version__
from extracteval.adapters.models.mock import ScriptedModel
from extracteval.core.base import ArtifactRef, Contract
from extracteval.core.documents import (
    Document,
    Evidence,
    EvidenceAssessment,
    EvidenceAvailability,
    EvidenceSufficiency,
)
from extracteval.core.experiments import (
    ConfigRef,
    ExperimentConfig,
    ModelBinding,
    ModelRunRecord,
    RunManifest,
)
from extracteval.core.models import ModelParameters, ModelRequest, ResponseFormat
from extracteval.core.ports import ModelPort
from extracteval.core.reference import AdjudicatedReference, ExpertAnnotation
from extracteval.core.results import ExtractionResult, OperationStatus, ResultTrace
from extracteval.core.specification import (
    CategoryValue,
    InformationPolicy,
    OperationalDictionary,
    VariableDefinition,
)


def json_bytes(value: object) -> bytes:
    """Convención del tutorial: JSON UTF-8 ordenado, indentado y con salto final."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def contract_bytes(value: Contract) -> bytes:
    return json_bytes(value.model_dump(mode="json"))


def reference_for(artifact_id: str, content: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id, version="1", sha256=hashlib.sha256(content).hexdigest()
    )


def write_new(path: Path, content: bytes) -> None:
    # Modo exclusivo: incluso dentro de una carpeta nueva, nunca reemplaza un archivo.
    with path.open("xb") as stream:
        stream.write(content)


def run(output: Path) -> None:
    started = datetime.now(UTC)
    # Este contenido es exclusivamente sintético. No introducir datos reales aquí.
    instructions = "Devuelve el estado documental del trámite con kind y value en JSON."
    variable = VariableDefinition(
        variable_id="estado_tramite",
        version="1",
        data_type="categorical",
        categories=("aprobado", "denegado", "indeterminado"),
        operational_definition="Estado expresamente documentado del trámite sintético.",
        interpretation_rules=("No inferir aprobación a partir de la falta de denegación.",),
        correctness_criteria=("Coincidencia con la categoría de la referencia independiente.",),
        information_policy=InformationPolicy(
            absent="Conservar ausencia de valor si el documento no informa el estado.",
            indeterminate="Usar indeterminado cuando el texto expresa incertidumbre.",
            not_applicable="Aplicar la política externa del estudio; no inventar una categoría.",
        ),
    )
    # El diccionario referencia su payload de definiciones, no sus propios bytes.
    # Esto evita intentar incluir en un archivo la huella de sí mismo.
    payload_bytes = json_bytes({"variables": [variable.model_dump(mode="json")]})
    dictionary_ref = reference_for("dictionary-payload", payload_bytes)
    dictionary = OperationalDictionary(artifact=dictionary_ref, variables=(variable,))
    dictionary = OperationalDictionary.model_validate_json(dictionary.model_dump_json())

    schema_bytes = json_bytes(ExtractionResult.model_json_schema())
    schema_ref = reference_for("result-schema", schema_bytes)
    instructions_bytes = instructions.encode("utf-8")
    instructions_ref = reference_for("instructions", instructions_bytes)

    # Este modelo devuelve una respuesta escrita de antemano. No interpreta el texto.
    model: ModelPort = ScriptedModel(['{"kind": "categorical", "value": "aprobado"}'])
    parameters = ModelParameters(
        seed=17, temperature=0.0, response_format=ResponseFormat.STRUCTURED
    )
    model.capabilities.validate_parameters(parameters)
    binding = ModelBinding(adapter_id="scripted", model=model.identity, parameters=parameters)
    config = ExperimentConfig(
        config_id="tutorial-administrativo",
        version="1",
        dictionary=dictionary_ref,
        output_schema=schema_ref,
        extractor_instructions=instructions_ref,
        extractor=binding,
    )
    config_ref = ConfigRef.from_config(config)

    document = Document(
        document_id="doc-sintetico-001",
        entity_id="entidad-sintetica-001",
        text="Documento sintético. Estado del trámite: aprobado.",
        provenance={"dataset": "tutorial-sintetico"},
    )
    request = ModelRequest(
        execution_id="ejecucion-tutorial-001",
        request_id="solicitud-interna-001",
        instructions=instructions,
        content=document.text or "",
        parameters=parameters,
    )
    response = model.generate(request)
    if response.structured_json is None:
        raise RuntimeError("El tutorial requiere una respuesta JSON simulada")
    # Conversión manual de este único ejemplo. No es un normalizador genérico.
    value = CategoryValue.model_validate_json(response.structured_json)
    dictionary.variable("estado_tramite").validate_value(value)
    evidence = EvidenceAssessment(
        availability=EvidenceAvailability.AVAILABLE,
        sufficiency=EvidenceSufficiency.SUFFICIENT,
        items=(Evidence(document_id=document.document_id, quote="Estado del trámite: aprobado."),),
    )
    result = ExtractionResult(
        result_id="resultado-001",
        trace=ResultTrace(
            document_id=document.document_id,
            variable_id="estado_tramite",
            dictionary=dictionary_ref,
            config=config_ref,
            execution_id=request.execution_id,
            output_schema=schema_ref,
            model=response.model,
            instructions=instructions_ref,
            request_id=response.request_id,
            provider_request_id=response.provider_request_id,
        ),
        operation=OperationStatus.COMPLETED,
        value=value,
        evidence=evidence,
    )
    result.validate_against(dictionary)
    result.trace.validate_config(config)

    # Anotaciones de demostración escritas independientemente de response y result.
    # En un estudio las producirían evaluadores con un procedimiento externo de cegamiento.
    first = ExpertAnnotation(
        annotation_id="anotacion-001",
        document_id=document.document_id,
        variable_id="estado_tramite",
        evaluator_id="evaluador-sintetico-01",
        dictionary=dictionary_ref,
        partition="evaluation",
        blinded_to_system_output=True,
        status="evaluable",
        value=CategoryValue(value="aprobado"),
        evidence=evidence,
    )
    second = ExpertAnnotation(
        annotation_id="anotacion-002",
        document_id=document.document_id,
        variable_id="estado_tramite",
        evaluator_id="evaluador-sintetico-02",
        dictionary=dictionary_ref,
        partition="evaluation",
        blinded_to_system_output=True,
        status="evaluable",
        value=CategoryValue(value="indeterminado"),
        evidence=EvidenceAssessment(
            availability=EvidenceAvailability.AVAILABLE,
            sufficiency=EvidenceSufficiency.UNDETERMINED,
            items=evidence.items,
        ),
    )
    reference = AdjudicatedReference(
        reference_id="referencia-001",
        annotations=(first, second),
        adjudicator_id="adjudicador-sintetico-03",
        disagreement=True,
        status="final",
        value=CategoryValue(value="aprobado"),
        evidence=evidence,
    )
    reference.validate_against(dictionary)

    # Preparación en memoria: el manifiesto solo contiene referencias a los archivos.
    inputs = {
        "dictionary-payload.json": (dictionary_ref, payload_bytes),
        "output-schema.json": (schema_ref, schema_bytes),
        "instructions.txt": (instructions_ref, instructions_bytes),
    }
    document_bytes = contract_bytes(document)
    inputs["document.json"] = (reference_for("document-snapshot", document_bytes), document_bytes)
    outputs: dict[str, tuple[ArtifactRef, bytes]] = {}
    objects: dict[str, Contract] = {
        "dictionary.json": dictionary,
        "model-response.json": response,
        "extraction.json": result,
        "annotation-1.json": first,
        "annotation-2.json": second,
        "reference.json": reference,
    }
    for filename, obj in objects.items():
        content = contract_bytes(obj)
        outputs[filename] = (reference_for(filename.removesuffix(".json"), content), content)
    manifest = RunManifest(
        execution_id=request.execution_id,
        config=config_ref,
        package_version=__version__,
        started_at=started,
        finished_at=datetime.now(UTC),
        models=(
            ModelRunRecord(
                role="extractor",
                binding=binding,
                capabilities=model.capabilities,
                effective_parameters=response.effective_parameters,
            ),
        ),
        inputs=tuple(ref for ref, _ in inputs.values()),
        outputs=tuple(ref for ref, _ in outputs.values()),
    )
    manifest.validate_against(config)
    inventory = {
        filename: ref.model_dump(mode="json")
        for filename, (ref, _) in {**inputs, **outputs}.items()
    }

    # Solo se crean archivos cuando los contratos anteriores ya son válidos.
    output.mkdir(parents=True, exist_ok=False)
    for filename, (_, content) in {**inputs, **outputs}.items():
        write_new(output / filename, content)
    write_new(output / "config.json", contract_bytes(config))
    write_new(output / "manifest.json", contract_bytes(manifest))
    write_new(output / "artifacts.json", json_bytes(inventory))

    # Recuperación real desde disco sin volver a llamar al modelo.
    recovered_dictionary = OperationalDictionary.model_validate_json(
        (output / "dictionary.json").read_bytes()
    )
    recovered_config = ExperimentConfig.model_validate_json((output / "config.json").read_bytes())
    recovered_result = ExtractionResult.model_validate_json(
        (output / "extraction.json").read_bytes()
    )
    recovered_reference = AdjudicatedReference.model_validate_json(
        (output / "reference.json").read_bytes()
    )
    recovered_manifest = RunManifest.model_validate_json((output / "manifest.json").read_bytes())
    recovered_result.validate_against(recovered_dictionary)
    recovered_result.trace.validate_config(recovered_config)
    recovered_reference.validate_against(recovered_dictionary)
    recovered_manifest.validate_against(recovered_config)
    assert recovered_result == result
    assert recovered_reference == reference
    for filename, (ref, _) in {**inputs, **outputs}.items():
        actual = hashlib.sha256((output / filename).read_bytes()).hexdigest()
        assert actual == ref.sha256
    print("Tutorial sintético completado; no se llamó a ningún proveedor.")
    print(f"Archivos creados: {len(list(output.iterdir()))}")
    print(f"Directorio: {output.resolve()}")
    print("Contratos recuperados y huellas verificadas correctamente.")
    print("No se calcularon métricas ni se implementó un flujo de extracción real.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salida", type=Path, required=True, help="Directorio nuevo para datos sintéticos"
    )
    args = parser.parse_args()
    if args.salida.exists():
        parser.error(
            "La carpeta de salida ya existe; usa otra para conservar la ejecución anterior."
        )
    run(args.salida)


if __name__ == "__main__":
    main()
