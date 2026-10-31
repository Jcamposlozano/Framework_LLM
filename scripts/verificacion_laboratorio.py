"""Puente entre el laboratorio YAML/JSON y los casos de uso de fase 2.

No añade una etapa metodológica ni ejecuta extracción o evaluación clínica.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from laboratorio_yaml_json import LabError, load_yaml, read_json, write_json
from pydantic import ValidationError

from extracteval.application.configuration import Phase2Config, load_configuration
from extracteval.cli import main as verify_cli
from extracteval.core.base import ArtifactRef
from extracteval.core.documents import Document, DocumentSection, Evidence, EvidenceAssessment
from extracteval.core.experiments import ConfigRef
from extracteval.core.hashing import content_hash
from extracteval.core.results import ExtractionResult, ResultTrace, TechnicalError
from extracteval.core.specification import (
    SEMANTIC_VALUE_ADAPTER,
    CategoryValue,
    DocumentaryReviewRule,
    OperationalDictionary,
)
from extracteval.core.verification import (
    ExtractionSnapshot,
    VariableVerification,
    VerificationInput,
    VerificationPayload,
)

REPOSITORY = Path(__file__).resolve().parents[1]


def config_root(laboratory: Path, version: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", version):
        raise LabError("Usa una versión simple, sin rutas.")
    return laboratory / "configuraciones/verificacion" / version


def immutable_json(path: Path, value: object) -> None:
    if path.exists():
        if content_hash(read_json(path)) != content_hash(value):
            raise LabError("El artefacto ya existe; usa una nueva versión o ejecución.")
    else:
        write_json(path, value, exclusive=True, private=True)


def synthetic_inputs(
    dictionary: OperationalDictionary,
) -> tuple[VerificationInput, VerificationPayload]:
    text = "ANÁLISIS: Exacerbación actual de EPOC documentada. Fecha de inicio desconocida."
    document = Document(
        document_id="demo-sintetico-fase2",
        text=text,
        sections=(DocumentSection(name="analisis", start=0, end=len(text)),),
    )
    quote = "Exacerbación actual de EPOC documentada."
    evidence = Evidence(
        document_id=document.document_id,
        quote=quote,
        section="analisis",
        start=text.index(quote),
        end=text.index(quote) + len(quote),
    )
    results, proposals, states = [], [], {}
    for variable in dictionary.variables:
        # Fixture explícita, no un extractor ni una regla clínica del núcleo.
        a = v = None
        if variable.variable_id == "exacerbacion_actual":
            if "true" in variable.categories and "false" in variable.categories:
                a, v = CategoryValue(value="false"), CategoryValue(value="true")
            elif "si" in variable.categories and "no" in variable.categories:
                a, v = CategoryValue(value="no"), CategoryValue(value="si")
        state = "value" if v else "indeterminate"
        states[variable.variable_id] = state
        items = (evidence,) if v else ()
        results.append(
            ExtractionResult(
                result_id="demo-a-" + variable.variable_id,
                trace=ResultTrace(
                    document_id=document.document_id,
                    variable_id=variable.variable_id,
                    dictionary=dictionary.artifact,
                    config=ConfigRef(config_id="demo-synthetic", version="1", sha256="1" * 64),
                    execution_id="demo-original-a",
                    output_schema=ArtifactRef(
                        artifact_id="demo-schema", version="1", sha256="2" * 64
                    ),
                ),
                operation="completed",
                value=a,
                evidence=EvidenceAssessment(availability="absent", sufficiency="insufficient"),
            )
        )
        proposals.append(
            VariableVerification(
                variable_id=variable.variable_id,
                proposed_value=v,
                semantic_state=state,
                evidence=items,
                evidence_type="literal" if items else "none",
                uncertainty_flags=() if v else ("insufficient_documentation",),
                requires_human_review=v is None,
            )
        )
    original = ExtractionSnapshot(
        base_extraction_id="demo-extraccion-a",
        document_id=document.document_id,
        dictionary=dictionary.artifact,
        results=tuple(results),
        semantic_states=states,
        auxiliary={
            "offset_estimado_dias": None,
            "ventana_ambiental": None,
            "criterios_detectados": [],
            "justificacion_clinica": "Ejemplo sintético.",
            "nivel_confianza": 0.8,
        },
    )
    return VerificationInput(document=document, extraction_a=original), VerificationPayload(
        variables=tuple(proposals)
    )


def prepare_verification(laboratory: Path, version: str = "v1") -> None:
    source = laboratory / "01_especificacion/especificacion.yaml"
    compiled = read_json(laboratory / "01_especificacion/especificacion.json")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if compiled.get("fuente", {}).get("sha256") != source_hash or compiled.get(
        "especificacion_completa"
    ) != load_yaml(source):
        raise LabError("Prepara la especificación actual antes de preparar la verificación.")
    try:
        original = OperationalDictionary.model_validate(compiled["diccionario_framework"])
    except (ValidationError, KeyError):
        raise LabError(
            "Diccionario del laboratorio incompatible; prepara la especificación."
        ) from None
    # Conserva variables, categorías y reglas descriptivas. La aprobación clínica no se infiere.
    review_rules = []
    for rule in compiled["especificacion_completa"].get("consistency_checks", []):

        def typed_values(values: dict[str, Any]) -> dict[str, Any]:
            return {
                key: None
                if value is None
                else SEMANTIC_VALUE_ADAPTER.validate_json(
                    json.dumps({"kind": original.variable(key).data_type, "value": value})
                )
                for key, value in values.items()
            }

        review_rules.append(
            DocumentaryReviewRule(
                rule_id=rule["id"],
                approved=False,
                when=typed_values(rule["if"]),
                expected=typed_values(rule["then"]),
            )
        )
    dictionary = OperationalDictionary.model_validate(
        original.model_dump(mode="python")
        | {
            "clinically_approved": False,
            "review_rules": tuple(review_rules),
        }
    )
    digest = content_hash(dictionary.model_dump(mode="json", exclude={"artifact"}))
    dictionary = dictionary.model_copy(
        update={"artifact": original.artifact.model_copy(update={"sha256": digest})}
    )
    root = config_root(laboratory, version)
    provenance = {
        "source_yaml_sha256": source_hash,
        "source_dictionary": original.artifact.model_dump(mode="json"),
        "executable_dictionary": dictionary.artifact.model_dump(mode="json"),
        "clinical_approval": False,
        "transformation": "same_definitions_canonical_digest_review_only_implications",
    }
    immutable_json(root / "fuente.json", provenance)
    immutable_json(root / "diccionario.json", dictionary.model_dump(mode="json"))
    immutable_json(
        root / "mapeo-a.json",
        {
            "version": "representation.v1",
            "categorical_boolean_encoding": {
                v.variable_id: {"true": "true", "false": "false"}
                for v in dictionary.variables
                if {"true", "false"} <= set(v.categories)
            },
            "nota": "Conversión explícita de representación JSON; no infiere estados ni fechas.",
        },
    )
    immutable_json(
        root / "politica.json", read_json(REPOSITORY / "configs/epoc/conservative.v1.json")
    )
    prompt = (REPOSITORY / "prompts/independent-verifier.v1.txt").read_text(encoding="utf-8")
    immutable_json(root / "prompt.json", {"version": "independent-verifier.v1", "text": prompt})
    prompt_path = root / "verificador.v1.txt"
    if not prompt_path.exists():
        prompt_path.write_text(prompt, encoding="utf-8")
    inputs, payload = synthetic_inputs(dictionary)
    immutable_json(root / "demo-entrada.json", inputs.model_dump(mode="json"))
    immutable_json(root / "demo-verificador.json", payload.model_dump(mode="json"))
    config = Phase2Config(
        version="lab-phase2-" + version,
        dictionary_path="diccionario.json",
        policy_path="politica.json",
        prompt_path="verificador.v1.txt",
        prompt_version="independent-verifier.v1",
        mock_payload_path="demo-verificador.json",
    )
    # La configuración es editable; repetir la preparación no reemplaza ajustes del usuario.
    if not (root / "config.json").exists():
        write_json(
            root / "config.json", config.model_dump(mode="json"), exclusive=True, private=True
        )
    write_json(
        laboratory / "control/verificacion.json",
        {
            "capacidad": "fase2_disponible",
            "configuracion": str(root.relative_to(laboratory) / "config.json"),
            "diccionario_aprobado": False,
            "referencia_experta": "no_proporcionada",
            "demostracion_preparada": True,
            "preparacion_procesa_corpus": False,
            "siguiente_paso": "Ejecutar demo-verificacion y revisar sus archivos.",
        },
        private=True,
    )
    print(
        f"Fase 2 preparada: {len(dictionary.variables)} variables del laboratorio. "
        "Aprobación clínica pendiente."
    )
    print("Demostración sintética lista. El corpus importado no se ha procesado.")


def ensure_current_source(laboratory: Path, version: str) -> Path:
    root = config_root(laboratory, version)
    recorded = read_json(root / "fuente.json")
    digest = hashlib.sha256(
        (laboratory / "01_especificacion/especificacion.yaml").read_bytes()
    ).hexdigest()
    if digest != recorded["source_yaml_sha256"]:
        raise LabError("La especificación cambió; prepara una nueva versión de verificación.")
    try:
        _, dictionary, _, config = load_configuration(root / "config.json", {}, "real")
        prompt = read_json(root / "prompt.json")
    except (ValueError, KeyError):
        raise LabError("La configuración preparada no cumple los contratos de fase 2.") from None
    if dictionary.artifact.model_dump(mode="json") != recorded["executable_dictionary"]:
        raise LabError("El diccionario configurado no corresponde a la fuente preparada.")
    if config.prompt_version != prompt.get("version") or config.prompt != prompt.get("text"):
        raise LabError("El prompt o su versión cambió; prepara una nueva versión de verificación.")
    return root


def verification_technical_inventory(laboratory: Path, version: str = "v1") -> dict[str, Any]:
    """Describe existing artifacts without running models or selecting a configuration."""
    from extracteval.application.verification import strict_schema

    root = ensure_current_source(laboratory, version)
    config, dictionary, policy, verifier = load_configuration(root / "config.json", {}, "real")

    def artifact(path: Path) -> dict[str, str]:
        resolved = path.resolve()
        label = str(resolved.relative_to(laboratory.resolve()))
        return {"ruta": label, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    return {
        "configuracion": {"version": config.version, **artifact(root / "config.json")},
        "diccionario": dictionary.artifact.model_dump(mode="json"),
        "proveedor_configurado": "openai",
        "modelo_configurado": verifier.model_id,
        "parametros_solicitados": verifier.parameters.model_dump(mode="json"),
        "request_timeout": verifier.timeout_seconds,
        "metadatos_permitidos": list(verifier.allowed_metadata_keys),
        "instrucciones": {"version": config.prompt_version, **artifact(root / config.prompt_path)},
        "esquema": {
            "contrato": "extracteval.core.verification.VerificationPayload",
            "contract_version": VerificationPayload.model_fields["contract_version"].default,
            "sha256_canonico": content_hash(strict_schema(VerificationPayload.model_json_schema())),
            "origen": "Esquema generado del contrato existente; no se crea otro esquema.",
        },
        "politica": {
            "policy_id": policy.policy_id,
            "version": policy.version,
            **artifact(root / config.policy_path),
        },
        "reconciler_engine": config.reconciler_engine,
        "reconciler_model": verifier.reconciler_model_id,
        "modelo_efectivo_api": None,
        "api_consultada_por_inventario": False,
        "variables_entorno": [
            "EXTRACTEVAL_VERIFIER_MODEL",
            "EXTRACTEVAL_RECONCILER_MODEL",
            "EXTRACTEVAL_MAX_OUTPUT_TOKENS",
            "EXTRACTEVAL_REQUEST_TIMEOUT",
        ],
    }


def execute_verification(
    laboratory: Path,
    *,
    version: str = "v1",
    entry: Path | None = None,
    execution: str = "demo-v1",
    stage: str = "all",
    mode: str = "mock",
    dry_run: bool = False,
    authorize_real: bool = False,
    governance: Path | None = None,
) -> int:
    root = ensure_current_source(laboratory, version)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", execution):
        raise LabError("El nombre de ejecución no puede contener rutas.")
    source = entry if entry is not None else root / "demo-entrada.json"
    if entry is None and mode != "mock":
        raise LabError("La demostración se ejecuta exclusivamente en modo mock.")
    output = laboratory / "ejecuciones/fase2" / execution
    arguments = [
        "verify",
        "--config",
        str(root / "config.json"),
        "--input",
        str(source),
        "--output",
        str(output),
        "--stage",
        stage,
        "--mode",
        mode,
    ]
    if dry_run:
        arguments.append("--dry-run")
    if authorize_real:
        arguments.append("--authorize-real")
    if governance is not None:
        arguments += ["--governance", str(governance)]
    result = verify_cli(arguments)
    if not dry_run:
        verification_status(laboratory)
    return result


def register_original(
    laboratory: Path,
    *,
    document_id: str,
    source: Path,
    version: str = "v1",
    document: Document | None = None,
) -> Path:
    root = ensure_current_source(laboratory, version)
    _, dictionary, _, _ = load_configuration(root / "config.json", {}, "mock")
    if document is None:
        documents = read_json(laboratory / "datos/documentos.json")
        matches = [record for record in documents if record.get("document_id") == document_id]
        if len(matches) != 1:
            raise LabError("Selecciona exactamente un documento del inventario local.")
        document = Document.model_validate(matches[0])
    elif document.document_id != document_id:
        raise LabError("El documento explícito no coincide con el identificador.")
    raw_bytes = source.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    raw = json.loads(raw_bytes)
    if not isinstance(raw, dict):
        raise LabError("La extracción A debe ser un objeto JSON.")
    mapping = read_json(root / "mapeo-a.json")
    import_config = None
    try:
        if "results" in raw:
            original = ExtractionSnapshot.model_validate(raw)
            if original.auxiliary.get("document_hash", content_hash(document)) != content_hash(
                document
            ):
                raise LabError("A corresponde a otro contenido documental.")
            if original.document_id != document_id or original.dictionary != dictionary.artifact:
                raise LabError(
                    "La extracción tipada debe usar el documento y diccionario configurados."
                )
            # Un contrato registrado permanece idéntico; registro.json guarda el hash del archivo.
        else:
            values = raw.get("values", raw)
            results = []
            states = raw.get("semantic_states", {})
            output_schema = ArtifactRef(
                artifact_id="extracteval.core.results.ExtractionResult",
                version=ExtractionResult.model_fields["contract_version"].default,
                sha256=content_hash(ExtractionResult.model_json_schema()),
            )
            import_config = {
                "adapter": "scripts.verificacion_laboratorio.register_original",
                "mapping": mapping,
                "dictionary": dictionary.artifact.model_dump(mode="json"),
                "output_schema": output_schema.model_dump(mode="json"),
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
            import_ref = ConfigRef(
                config_id="import-original-a",
                version=mapping["version"],
                sha256=content_hash(import_config),
            )
            aux_names = (
                "offset_estimado_dias",
                "ventana_ambiental",
                "criterios_detectados",
                "justificacion_clinica",
                "nivel_confianza",
            )
            auxiliary = raw.get("auxiliary", {k: raw[k] for k in aux_names if k in raw})
            for variable in dictionary.variables:
                key = variable.variable_id
                if key not in values:
                    raise LabError(
                        "Incluye todas las variables; declara los estados de valores null."
                    )
                raw_value = values[key]
                if isinstance(raw_value, bool) and variable.data_type == "categorical":
                    encoding = mapping["categorical_boolean_encoding"].get(key, {})
                    encoded = encoding.get("true" if raw_value else "false")
                    if encoded not in variable.categories:
                        raise LabError("Representación booleana sin mapeo al dominio categórico.")
                    raw_value = encoded
                value = (
                    None
                    if raw_value is None
                    else SEMANTIC_VALUE_ADAPTER.validate_json(
                        json.dumps(
                            {"kind": variable.data_type, "value": raw_value}, ensure_ascii=False
                        )
                    )
                )
                if value is not None:
                    variable.validate_value(value)
                evidence = tuple(
                    Evidence.model_validate(item) for item in raw.get("evidence", {}).get(key, [])
                )
                error_data = raw.get("technical_errors", {}).get(key)
                results.append(
                    ExtractionResult(
                        result_id="import-a-" + digest[:12] + "-" + key,
                        trace=ResultTrace(
                            document_id=document_id,
                            variable_id=key,
                            dictionary=dictionary.artifact,
                            config=import_ref,
                            execution_id="import-" + digest[:24],
                            output_schema=output_schema,
                        ),
                        operation="failed" if error_data else "completed",
                        value=value,
                        technical_error=TechnicalError.model_validate(error_data)
                        if error_data
                        else None,
                        evidence=EvidenceAssessment(
                            availability="available" if evidence else "absent",
                            sufficiency="undetermined" if evidence else "insufficient",
                            items=evidence,
                        ),
                    )
                )
            original = ExtractionSnapshot(
                base_extraction_id=raw.get("base_extraction_id", "a-" + digest[:24]),
                source_sha256=digest,
                document_id=document_id,
                dictionary=dictionary.artifact,
                results=tuple(results),
                semantic_states=states,
                auxiliary=auxiliary,
            )
        for result in original.results:
            result.validate_against(dictionary)
    except (ValidationError, KeyError, TypeError, ValueError):
        raise LabError(
            "A incompatible: revisa tipos, estados, evidencia y categorías del diccionario."
        ) from None
    destination = (
        laboratory
        / "datos/verificacion"
        / ("entrada-" + content_hash({"document": document_id, "a": digest})[:24])
    )
    immutable_json(
        destination / "entrada.json",
        VerificationInput(document=document, extraction_a=original).model_dump(mode="json"),
    )
    if import_config is not None:
        immutable_json(destination / "configuracion_importacion.json", import_config)
    # Copia binaria íntegra del archivo A recibido, separada de su adaptación al contrato.
    raw_path = destination / "a-original.json"
    if raw_path.exists() and raw_path.read_bytes() != raw_bytes:
        raise LabError("La extracción fuente ya existe con contenido diferente.")
    if not raw_path.exists():
        with raw_path.open("xb") as stream:
            stream.write(raw_bytes)
        raw_path.chmod(0o600)
    immutable_json(
        destination / "registro.json",
        {
            "source_sha256": digest,
            "base_extraction_hash": content_hash(original),
            "base_extraction_id": original.base_extraction_id,
            "version": version,
        },
    )
    print("A registrada localmente; no se han realizado llamadas externas.")
    print(f"Entrada: {destination / 'entrada.json'}")
    return destination / "entrada.json"


def verification_status(laboratory: Path) -> dict[str, Any]:
    from extracteval.adapters.storage.json_store import JSONRunStore
    from extracteval.core.verification import (
        ComparisonResult,
        IndependentVerification,
        ReconciledExtraction,
        VerificationRunManifest,
    )

    runs = []
    for directory in sorted((laboratory / "ejecuciones/fase2").glob("*")):
        if not directory.is_dir():
            continue
        store = JSONRunStore(directory)
        hashes = store.artifact_hashes()
        manifests = [
            name
            for name in ("manifest-independent", "manifest-compare", "manifest-all")
            if store.exists(name)
        ]
        integrity = True
        for name in manifests:
            manifest = store.get(name, VerificationRunManifest)
            integrity = (
                integrity
                and content_hash(manifest.artifact_hashes) == manifest.output_hash
                and all(hashes.get(k) == v for k, v in manifest.artifact_hashes.items())
            )
        comparison = (
            store.get("comparison", ComparisonResult) if store.exists("comparison") else None
        )
        verification = (
            store.get("verification", IndependentVerification)
            if store.exists("verification")
            else None
        )
        final = (
            store.get("extraction_b", ReconciledExtraction)
            if store.exists("extraction_b")
            else None
        )
        row = {
            "ejecucion": directory.name,
            "integridad": integrity,
            "lectura_independiente": store.exists("verification"),
            "error_tecnico": verification.audit.error.code
            if verification and verification.audit.error
            else None,
            "comparacion": comparison is not None,
            "reconciliacion": final is not None,
            "manifiestos": manifests,
            "discrepancias": sum(v.relation != "exact_match" for v in comparison.variables)
            if comparison
            else 0,
            "revision_humana": sum(d.requires_human_review for d in final.decisions)
            if final
            else 0,
            "validacion_clinica": False,
        }
        runs.append(row)
        print(
            f"{directory.name}: lectura={row['lectura_independiente']} "
            f"comparación={row['comparacion']} "
            f"reconciliación={row['reconciliacion']} discrepancias={row['discrepancias']} "
            f"revisión_humana={row['revision_humana']} integridad={integrity}"
        )
    report = {
        "alcance": "seguimiento_tecnico_fase2_no_cierre_metodologico",
        "ejecuciones": runs,
        "referencia_experta": "no_proporcionada",
        "metricas_exactitud_calculadas": False,
    }
    write_json(laboratory / "control/progreso_verificacion.json", report, private=True)
    if not runs:
        print("Sin ejecuciones de fase 2. Prepara y ejecuta primero la demostración sintética.")
    return report
