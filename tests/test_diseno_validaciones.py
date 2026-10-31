"""Controles de planes y artefactos sintéticos; no ejecutan etapas del estudio."""

import copy
import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diseno_validaciones import (  # noqa: E402
    ACTIONS,
    DesignError,
    assess_design,
    policy_defaults,
    require_operation,
    validate_baseline_reuse,
    validate_partition_assignments,
    validate_policy,
)


def fixture_plan() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = policy_defaults()
    plan.update(
        {
            "diseno_id": "synthetic-plan",
            "corpus_disponible": {},
            "unidades": {},
            "muestreo": {},
            "tamano_muestra_justificacion": {},
            "reglas_evaluabilidad": {},
            "tratamiento_fallos_abstenciones": {},
            "metodo_ic95": {},
            "criterios_congelacion": {},
        }
    )
    plan["metricas_secundarias"]["por_variable"] = [
        {"variable_id": "decision", "metricas": ["exactitud"]},
        {"variable_id": "fecha", "metricas": ["coincidencia_exacta"]},
    ]
    plan["metricas_secundarias"]["por_categoria"] = [
        {
            "variable_id": "decision",
            "categorias": ["yes", "indeterminado"],
            "metricas": ["sensibilidad"],
        }
    ]
    plan["metricas_secundarias"]["grupos_relacionados"] = [
        {"tipo": "temporal", "variables": ["fecha"], "metricas": ["exactitud_conjunta"]}
    ]
    plan["estimando_primario"] = {"nombre": "PGEC", "contraste_principal": "PGEC_B - PGEC_A"}
    context = {
        "variable_ids": ["decision", "fecha"],
        "categories": {"decision": ["yes", "indeterminado"]},
        "date_variables": ["fecha"],
        "patient_grouping_available": False,
        "document_date_available": False,
        "clinical_criteria_approved": False,
    }
    return plan, context


@pytest.mark.parametrize(
    "path,value",
    [
        (("poblacion",), {"fuente": {}}),
        (("particiones_planificadas",), []),
        (("separacion_particiones", "roles_disjuntos"), False),
        (("validacion_prompts", "particiones_para_seleccion"), ["evaluation"]),
        (("validacion_prompts", "acceso_etiquetas_finales"), True),
        (("configuraciones_comparadas", "B", "repite_extraccion"), True),
        (("configuraciones_comparadas", "B", "extractor_base_ref"), "different"),
        (("configuraciones_comparadas", "B", "modelo_extractor"), "other"),
        (("experimentos_secundarios", "combinar_con_contraste_principal"), True),
        (("experimentos_secundarios", "seleccion_configuraciones_en"), ["calibration"]),
        (("justificacion_muestral_multicriterio", "objetivos"), {}),
        (("justificacion_muestral_multicriterio", "pseudoetiquetas_como_verdad_experta"), True),
        (("metricas_secundarias", "por_variable"), []),
        (("metricas_secundarias", "por_categoria"), []),
        (("metricas_secundarias", "grupos_relacionados"), []),
    ],
)
def test_rejects_contradictions(path: tuple[str, ...], value: Any) -> None:
    plan, context = fixture_plan()
    target = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(DesignError):
        validate_policy(plan, context)


@pytest.mark.parametrize("action", ACTIONS)
def test_incomplete_protocol_cannot_authorize_operations(action: str) -> None:
    plan, context = fixture_plan()
    plan["autorizacion_operativa"][action] = True
    context["authorized_actions"] = {action: True}
    context["available_actions"] = {action: True}
    assessment = assess_design(plan, context)
    codes = {p["id"] for p in assessment["decisiones_pendientes"]}
    assert {"D04", "D06", "D10", "D11", "N_pgec", "N_calibracion"} <= codes
    with pytest.raises(DesignError):
        require_operation(assessment, action)


def test_no_default_sample_sizes_and_four_roles() -> None:
    plan, _ = fixture_plan()
    assert {p["id"] for p in plan["particiones_planificadas"]} == {
        "development",
        "reliability_fit",
        "calibration",
        "evaluation",
    }
    assert all(
        p["proporcion"] is None and p["numero_entidades"] is None
        for p in plan["particiones_planificadas"]
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, float("inf")])
def test_invalid_patient_counts(value: Any) -> None:
    plan, context = fixture_plan()
    plan["tamano_muestra_justificacion"]["pacientes_requeridos"] = value
    with pytest.raises(DesignError):
        validate_policy(plan, context)


def test_secondary_model_comparison_requires_controlled_factor_and_separate_results() -> None:
    plan, context = fixture_plan()
    experiment = {
        "id": "secondary-model",
        "factores_modificados": ["modelo"],
        "resultados_separados": True,
    }
    plan["experimentos_secundarios"]["experimentos"] = [experiment]
    validate_policy(plan, context)
    experiment["factores_modificados"] = ["modelo", "prompt"]
    with pytest.raises(DesignError):
        validate_policy(plan, context)


def test_four_role_leakage_check_only_inspects_supplied_synthetic_metadata() -> None:
    rows = [
        {"entity_id": f"synthetic-{i}", "document_id": f"doc-{i}", "partition": role}
        for i, role in enumerate(["development", "reliability_fit", "calibration", "evaluation"])
    ]
    before = copy.deepcopy(rows)
    validate_partition_assignments(rows)
    assert rows == before
    rows[-1]["entity_id"] = rows[0]["entity_id"]
    with pytest.raises(DesignError):
        validate_partition_assignments(rows)


def test_baseline_reuse_requires_identical_bytes_lineage_and_configuration() -> None:
    payload = b'{"synthetic_decision":"yes"}'
    a = dict.fromkeys(
        [
            "document_id",
            "variable_id",
            "base_extraction_id",
            "extractor_config_sha256",
            "experiment_id",
        ],
        "synthetic",
    )
    a["base_output_sha256"] = hashlib.sha256(payload).hexdigest()
    b = dict(a)
    validate_baseline_reuse(a, b, payload, payload)
    with pytest.raises(DesignError):
        validate_baseline_reuse(a, b, payload, b'{"synthetic_decision":"no"}')
    b["extractor_config_sha256"] = "different"
    with pytest.raises(DesignError):
        validate_baseline_reuse(a, b, payload, payload)


def test_primary_estimand_and_prompt_candidates_cannot_change_final_design() -> None:
    plan, context = fixture_plan()
    plan["estimando_primario"]["nombre"] = "otra_metrica"
    with pytest.raises(DesignError):
        validate_policy(plan, context)
    plan, context = fixture_plan()
    plan["validacion_prompts"]["candidatos"] = [{"id": "synthetic", "particion": "evaluation"}]
    with pytest.raises(DesignError):
        validate_policy(plan, context)
