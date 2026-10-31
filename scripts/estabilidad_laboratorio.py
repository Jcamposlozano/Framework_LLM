"""Phase 3 lab bridge: checked YAML, synthetic fixtures, explicit future real activation."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from laboratorio_yaml_json import LabError, load_yaml, write_json
from verificacion_laboratorio import REPOSITORY, config_root, ensure_current_source, immutable_json

from extracteval.adapters.models.verification_mock import MockExtractorModel, MockVerifierModel
from extracteval.application.configuration import load_configuration
from extracteval.application.extraction import (
    extraction_schema_ref,
    load_extractor,
    postprocessing_ref,
)
from extracteval.application.stability import (
    FileReference,
    RealAuthorization,
    ScriptedResponse,
    StabilityPlan,
    SyntheticCase,
    authorize_real,
    run_stability,
)
from extracteval.application.stability_analysis import render_report
from extracteval.core.documents import Document, DocumentSection
from extracteval.core.exceptions import ProviderFailure
from extracteval.core.experiments import ExperimentConfig, ModelBinding
from extracteval.core.hashing import content_hash
from extracteval.core.ports import ModelPort
from extracteval.core.results import ExtractionResult
from extracteval.core.verification import (
    ExtractionSnapshot,
    ReconciledExtraction,
    VerificationPayload,
)


def file_reference(path: Path, laboratory: Path, version: str) -> dict[str, str]:
    import os

    return {
        "ruta": os.path.relpath(path, laboratory),
        "version": version,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def contract_inventory() -> dict[str, Any]:
    inventory = {
        contract.__name__: {
            "contract_version": "1.0",
            "sha256_canonico": content_hash(contract.model_json_schema()),
        }
        for contract in (
            Document,
            ExtractionResult,
            ExtractionSnapshot,
            ExperimentConfig,
            ModelBinding,
            ReconciledExtraction,
        )
    }
    inventory["respuesta_estructurada"] = extraction_schema_ref().model_dump(mode="json")
    inventory["posprocesamiento"] = postprocessing_ref().model_dump(mode="json")
    return inventory


def synthetic_cases() -> list[SyntheticCase]:
    """Ten invented scenarios and explicitly programmed variation, never inference."""
    from extraccion_laboratorio import synthetic_extraction

    from extracteval.application.configuration import load_configuration

    _, dictionary, _, _ = load_configuration(REPOSITORY / "configs/epoc/phase2.json", {}, "mock")
    cases = []
    for number in range(10):
        doc, base = synthetic_extraction(dictionary)
        text = (doc.text or "") + f" Caso inventado {number + 1}."
        if number == 2:
            text += " Referencias documentales ambiguas: 2024-01-01 y 2024-01-03."
        document = Document(
            document_id=f"synthetic-stability-{number + 1:03d}",
            text=text,
            document_date="2024-02-01",
            provenance={"synthetic": True, "fixture_version": "stability-fixtures.v1"},
            sections=(DocumentSection(name="analisis", start=0, end=len(text)),),
        )
        sequences: dict[str, list[ScriptedResponse]] = {"A": [], "V": []}
        for role in sequences:
            for repetition in range(5):
                raw = base.model_dump(mode="json")
                for item in raw["variables"]:
                    for evidence in item["evidence"]:
                        evidence["document_id"] = document.document_id
                values = {v["variable_id"]: v for v in raw["variables"]}
                if number == 1 and repetition % 2 and role == "A":
                    values["estado_paciente"]["proposed_value"]["value"] = "sintomatico"
                if number == 2:
                    item = values["fecha_indice_evento"]
                    item.update(
                        proposed_value={
                            "kind": "date",
                            "value": "2024-01-03" if repetition % 2 else "2024-01-01",
                        },
                        semantic_state="value",
                    )
                if number == 4 and repetition % 2:
                    values["fecha_indice_evento"].update(
                        semantic_state="abstain", uncertainty_flags=["insufficient_evidence"]
                    )
                if number == 7 and repetition == 1:
                    values["fecha_indice_evento"].update(
                        semantic_state="no_response", uncertainty_flags=["missing_response"]
                    )
                if number == 8 and repetition == 2:
                    values["estado_paciente"]["evidence"][0]["quote"] = (
                        "Cita inexistente programada para prueba"
                    )
                if number == 9 and repetition % 2 and role == "V":
                    values["exacerbacion_actual"]["proposed_value"]["value"] = "true"
                if (number, repetition, role) in {(5, 2, "A"), (6, 3, "V")}:
                    sequences[role].append(ScriptedResponse(error="timeout"))
                else:
                    sequences[role].append(
                        ScriptedResponse(
                            payload=VerificationPayload.model_validate_json(json.dumps(raw))
                        )
                    )
        cases.append(
            SyntheticCase(document=document, a=tuple(sequences["A"]), v=tuple(sequences["V"]))
        )
    return cases


def prepare_stability(laboratory: Path) -> Path:
    root_v = ensure_current_source(laboratory, "v1")
    a_path = laboratory / "configuraciones/extraccion/v1/config.json"
    settings, dictionary, _ = load_extractor(a_path, {})
    cfg_v, dictionary_v, policy, verifier = load_configuration(root_v / "config.json", {}, "mock")
    if dictionary != dictionary_v:
        raise LabError("A y V deben compartir el diccionario existente.")
    stage = laboratory / "03_estabilidad"
    stage.mkdir(parents=True, exist_ok=True)
    fixture = stage / "documentos_sinteticos.v1.json"
    immutable_json(fixture, [c.model_dump(mode="json") for c in synthetic_cases()])
    source_spec = laboratory / "01_especificacion/especificacion.yaml"
    references = {
        "prompt_A": file_reference(
            a_path.parent / settings.prompt_path, laboratory, settings.prompt_version
        ),
        "prompt_V": file_reference(root_v / cfg_v.prompt_path, laboratory, cfg_v.prompt_version),
        "diccionario": file_reference(
            root_v / cfg_v.dictionary_path, laboratory, dictionary.artifact.version
        ),
        "politica": file_reference(root_v / cfg_v.policy_path, laboratory, policy.version),
        "especificacion_fuente": file_reference(
            source_spec, laboratory, dictionary.artifact.version
        ),
        "posprocesamiento_A": file_reference(
            REPOSITORY / "src/extracteval/application/extraction.py",
            laboratory,
            settings.postprocessing_version,
        ),
        "coordinador": file_reference(
            REPOSITORY / "src/extracteval/application/stability.py", laboratory, "stability.v1"
        ),
        "analisis": file_reference(
            REPOSITORY / "src/extracteval/application/stability_analysis.py",
            laboratory,
            "stability-analysis.v1",
        ),
    }
    ids = [f"synthetic-stability-{n + 1:03d}" for n in range(10)]
    plan = {
        "estudio_id": "epoc-stability-technical",
        "version": "stability-pilot.v1",
        "modo": "mock",
        "finalidad": "piloto_tecnico_no_confirmatorio",
        "subconjunto": {
            "tipo": "sintetico",
            "documentos_objetivo": 10,
            "documentos_ids": ids,
            "archivo": file_reference(fixture, laboratory, "stability-fixtures.v1"),
            "criterio_seleccion": (
                "Diez casos inventados con guiones explícitos de variación; sin datos reales."
            ),
            "uso": "desarrollo_tecnico",
        },
        "repeticiones": {
            "cantidad_por_documento": 5,
            "modalidades": [
                {"id": "completa", "regenerar_A": True, "regenerar_V": True, "reconciliar_B": True},
                {"id": "A_fija", "regenerar_A": False, "regenerar_V": True, "reconciliar_B": True},
            ],
            "ejecuciones_independientes": True,
            "reanudacion_no_cuenta_como_repeticion": True,
        },
        "configuracion_fija": {
            "extractor": file_reference(a_path, laboratory, settings.version),
            "verificador": file_reference(root_v / "config.json", laboratory, cfg_v.version),
            "archivos": references,
            "diccionario": dictionary.artifact.model_dump(mode="json"),
            "contratos": contract_inventory(),
            "modelos_solicitados": {"A": settings.model, "V": cfg_v.verifier_model},
            "reconciliacion_version": policy.version,
            "verificar_hashes": True,
        },
        "perturbaciones": [],
        "condiciones_constantes": [
            "mismo_documento_por_repeticion",
            "misma_configuracion_de_modelos",
            "mismos_prompts_y_diccionario",
            "mismo_esquema_de_salida",
            "misma_politica_de_reconciliacion",
            "verificacion_independiente",
            "A_inmutable_en_cada_ejecucion",
        ],
        "metricas_planificadas": [
            "acuerdo_exacto_por_variable",
            "acuerdo_registro_completo",
            "documentos_invariables",
            "categorias_observadas",
            "variacion_fecha_indice",
            "tasa_abstencion",
            "tasa_fallos_tecnicos",
            "frecuencia_cambio_decisiones_B",
            "diferencia_estabilidad_A_B",
        ],
        "incertidumbre": {
            "estado": "pendiente_diseno_confirmatorio",
            "unidad_agrupacion": "documento",
            "repeticiones_no_independientes": True,
            "intervalos_confianza": "no_calcular_en_piloto",
            "nota": (
                "10 documentos y 5 repeticiones son valores operativos provisionales, "
                "no un cálculo muestral."
            ),
        },
        "presupuesto": {
            "max_llamadas": 160,
            "reintentos_automaticos": 0,
            "limite_gasto_estimado": None,
        },
        "ejecucion_real_habilitada": False,
    }
    StabilityPlan.model_validate(plan)
    path = stage / "estabilidad.yaml"
    # Existing manual draft is backed up, never silently replaced after a run.
    content = yaml.safe_dump(plan, sort_keys=False, allow_unicode=True, width=100)
    if path.exists() and path.read_text() != content:
        if (stage / "resultados.json").exists() and json.loads(
            (stage / "resultados.json").read_bytes()
        ).get("ejecuciones"):
            raise LabError(
                "El piloto ya tiene resultados; conserva su plan o crea otra versión explícita."
            )
        history = laboratory / ".historial/estabilidad"
        history.mkdir(parents=True, exist_ok=True)
        backup = history / (hashlib.sha256(path.read_bytes()).hexdigest() + ".yaml")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    path.write_text(content)
    return path


def checked_path(laboratory: Path, reference: FileReference) -> Path:
    path = laboratory / reference.ruta
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != reference.sha256:
        raise LabError("No coincide un archivo versionado del plan de estabilidad.")
    return path


def artifact_tree(root: Path) -> dict[str, str]:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != ".reservation.lock")
    if any(p.is_symlink() for p in root.rglob("*")):
        raise LabError("No se permiten enlaces simbólicos en los artefactos del experimento.")
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
        if p != root / "integridad.json"
    }


def load_stability(laboratory: Path) -> tuple[StabilityPlan, list[SyntheticCase] | list[Document]]:
    plan = StabilityPlan.model_validate(load_yaml(laboratory / "03_estabilidad/estabilidad.yaml"))
    cfg = plan.configuracion_fija
    for ref in [cfg.extractor, cfg.verificador, *cfg.archivos.values()]:
        checked_path(laboratory, ref)
    if cfg.contratos != contract_inventory():
        raise LabError("Los contratos o el posprocesamiento no coinciden con el plan.")
    settings, dictionary, _ = load_extractor(laboratory / cfg.extractor.ruta, {})
    cfg_v, dictionary_v, policy, _ = load_configuration(
        laboratory / cfg.verificador.ruta, {}, plan.modo
    )
    if (
        dictionary != dictionary_v
        or dictionary.artifact != cfg.diccionario
        or cfg.modelos_solicitados != {"A": settings.model, "V": cfg_v.verifier_model}
        or cfg.reconciliacion_version != policy.version
        or cfg.extractor.version != settings.version
        or cfg.verificador.version != cfg_v.version
        or cfg.archivos["prompt_A"].version != settings.prompt_version
        or cfg.archivos["prompt_V"].version != cfg_v.prompt_version
    ):
        raise LabError("Las identidades/versiones configuradas no coinciden con el plan.")
    source = checked_path(laboratory, plan.subconjunto.archivo)
    raw = json.loads(source.read_bytes())
    if plan.modo == "mock":
        cases = [SyntheticCase.model_validate_json(json.dumps(case)) for case in raw]
        if any(
            len(c.a) < plan.repeticiones.cantidad_por_documento
            or len(c.v) < plan.repeticiones.cantidad_por_documento
            for c in cases
        ):
            raise LabError("El guion no cubre todas las repeticiones planificadas.")
        selected: list[SyntheticCase] | list[Document] = cases
        ids = [c.document.document_id for c in cases]
    else:
        documents = [Document.model_validate_json(json.dumps(d)) for d in raw]
        selected = documents
        ids = [d.document_id for d in documents]
    if ids != list(plan.subconjunto.documentos_ids):
        raise LabError(
            "Los identificadores y el orden deben coincidir con el subconjunto explícito."
        )
    return plan, selected


def execute_stability(
    laboratory: Path,
    execution: str = "piloto-mock-v1",
    *,
    mode: str = "mock",
    activate_real: bool = False,
    authorization_path: Path | None = None,
) -> dict[str, Any]:
    config_root(laboratory, execution)  # Existing safe folder-name validation.
    plan, selected = load_stability(laboratory)
    if plan.modo != mode:
        raise LabError("Modo CLI y plan distintos; no se activa el modo real automáticamente.")
    cases = {c.document.document_id: c for c in selected if isinstance(c, SyntheticCase)}
    documents = [c.document if isinstance(c, SyntheticCase) else c for c in selected]
    authorization = None
    if mode == "real":
        if not activate_real or authorization_path is None:
            raise LabError("La ruta real exige activación y autorización separadas.")
        authorization = RealAuthorization.model_validate_json(authorization_path.read_bytes())
        authorize_real(plan, documents, authorization, activate_real)
    elif activate_real or authorization_path is not None:
        raise LabError("Un plan mock no puede activar llamadas externas.")
    settings, dictionary, prompt = load_extractor(
        checked_path(laboratory, plan.configuracion_fija.extractor), {}
    )
    _, v_dictionary, policy, verifier = load_configuration(
        checked_path(laboratory, plan.configuracion_fija.verificador), {}, plan.modo
    )
    if dictionary != v_dictionary:
        raise LabError("Diccionarios de A/V distintos.")

    def factory(role: Literal["A", "V"], document: Document, repetition: int) -> ModelPort:
        if mode == "mock":
            scripted = (
                cases[document.document_id].a if role == "A" else cases[document.document_id].v
            )
            response = scripted[repetition]
            payload = ProviderFailure(response.error) if response.error else response.payload
            assert payload is not None
            return MockExtractorModel([payload]) if role == "A" else MockVerifierModel([payload])
        # Never imported, constructed or provided credentials in a mock execution.
        import os

        from extracteval.adapters.models.openai import OpenAIHTTPTransport, OpenAIResponsesModel

        return OpenAIResponsesModel(
            settings.model if role == "A" else verifier.model_id,
            OpenAIHTTPTransport(os.environ.get("OPENAI_API_KEY", "")),
            max_retries=0,
            schema_name="clinical_extraction" if role == "A" else "independent_verification",
        )

    root = laboratory / "ejecuciones/estabilidad" / execution
    if (root / "integridad.json").exists():
        expected = json.loads((root / "integridad.json").read_bytes())
        if artifact_tree(root) != expected:
            raise LabError("Integridad de la ejecución de estabilidad inválida.")
    result = run_stability(
        plan,
        documents,
        dictionary,
        settings,
        prompt,
        verifier,
        policy,
        root,
        factory,
        script_hash=plan.subconjunto.archivo.sha256,
        script_responses=cases if mode == "mock" else None,
        activate_real=activate_real,
        authorization=authorization,
    )
    immutable_json(root / "resultados.json", result)
    report = render_report(result)
    report_path = root / "informe.md"
    if report_path.exists() and report_path.read_text() != report:
        raise LabError("El informe de la ejecución ya existe con otro contenido.")
    report_path.write_text(report)
    immutable_json(root / "integridad.json", artifact_tree(root))
    target = laboratory / "03_estabilidad/resultados.json"
    if target.exists():
        previous = json.loads(target.read_bytes())
        if previous.get("ejecuciones") and previous.get("experiment_id") != result["experiment_id"]:
            raise LabError("Hay resultados de otro experimento; no se reemplazan automáticamente.")
    write_json(target, result, private=True)
    (laboratory / "03_estabilidad/informe.md").write_text(report)
    return result
