"""Validaciones de parametrización; no implementa ni ejecuta análisis estadísticos."""

import hashlib
import math
from typing import Any

PARTITIONS = {"development", "reliability_fit", "calibration", "evaluation"}
ACTIONS = ("congelar", "muestreo", "particionado", "extraccion", "evaluacion", "calibracion")
SIZE_OBJECTIVES = (
    "pgec",
    "diferencia_pareada",
    "dependencia_paciente",
    "categorias_infrecuentes",
    "calibracion",
)


class DesignError(ValueError):
    """Mensaje técnico sin documentos ni identificadores de pacientes."""


def policy_defaults() -> dict[str, Any]:
    """Reglas genéricas y campos pendientes; no incorpora variables de dominio."""
    return {
        "version_validaciones": "2.0",
        "poblacion": {
            "fuente": {
                "descripcion": None,
                "institucion_o_fuente": None,
                "periodo_inicio": None,
                "periodo_fin": None,
                "marco_muestral": None,
            },
            "elegible": {
                "descripcion": None,
                "criterios_inclusion_aprobados": [],
                "criterios_exclusion_aprobados": [],
                "documentos_totales": None,
                "entidades_totales": None,
            },
            "inferencia": {
                "descripcion": None,
                "relacion_con_elegible": None,
                "justificacion_transportabilidad": None,
            },
            "regla_previa": "No seleccionar ni excluir documentos por acierto observado de A/B.",
        },
        "particiones_planificadas": [
            {
                "id": role,
                "nombre": label,
                "uso": use,
                "proporcion": None,
                "numero_entidades": None,
                "asignadas": False,
            }
            for role, label, use in [
                (
                    "development",
                    "desarrollo",
                    "Selección de instrucciones, reglas y configuración antes de confirmar.",
                ),
                (
                    "reliability_fit",
                    "ajuste_fiabilidad",
                    "Ajuste del estimador e hiperparámetros; sin seleccionar prompts.",
                ),
                (
                    "calibration",
                    "calibracion",
                    "Calibración y políticas autorizadas; sin ajustar extractor o prompts.",
                ),
                (
                    "evaluation",
                    "evaluacion_final",
                    "Evaluación reservada; sin selección, ajuste ni elección de umbrales.",
                ),
            ]
        ],
        "separacion_particiones": {
            "unidad": "entidad_de_agrupacion",
            "roles_disjuntos": True,
            "justificacion_tamanos": None,
            "asignaciones_verificadas": False,
        },
        "validacion_prompts": {
            "particiones_para_seleccion": ["development"],
            "acceso_etiquetas_finales": False,
            "seleccionar_con_referencia_independiente": True,
            "candidatos": [],
            "criterio_seleccion_predefinido": (
                "PGEC en desarrollo con criterios aprobados; secundarios como restricciones "
                "preespecificadas."
            ),
            "regla_desempate": None,
            "presupuesto_iteraciones": None,
            "validacion_interna_por_entidad": True,
            "extractor_seleccionado": None,
            "verificador_seleccionado": None,
            "congelacion": {
                "estado": "pendiente",
                "fecha": None,
                "aprobador": None,
                "versiones_y_sha256": None,
            },
            "regla_cambios_posteriores": (
                "Crear nueva versión y nueva evaluación independiente; no reutilizar la "
                "confirmación original para ajustar."
            ),
        },
        "configuraciones_comparadas": {
            "extractor_base": {
                "modelo_y_parametros": None,
                "instrucciones_version": None,
                "instrucciones_sha256": None,
                "esquema_version": None,
                "reglas_posprocesamiento_version": None,
            },
            "A": {
                "descripcion": "Extracción base original",
                "extractor_base_ref": "extractor_base",
            },
            "B": {
                "descripcion": "Verificación y reconciliación sobre exactamente la salida de A",
                "extractor_base_ref": "extractor_base",
                "reutiliza_exactamente_salida_A": True,
                "repite_extraccion": False,
                "modelo_verificador_y_parametros": None,
                "instrucciones_version": None,
                "politica_reconciliacion_version": None,
                "lectura_independiente_verificador": True,
            },
            "mismos_documentos": True,
            "mismas_variables": True,
            "misma_referencia_independiente": True,
            "misma_definicion_pares_evaluables": True,
            "salidas_originales_separadas": True,
            "trazabilidad_pareada": {
                "mismo_base_extraction_id": True,
                "mismo_base_output_sha256": True,
                "mismo_extractor_config_sha256": True,
                "original_A_inmutable": True,
            },
        },
        "experimentos_secundarios": {
            "resultados_separados": True,
            "combinar_con_contraste_principal": False,
            "seleccion_configuraciones_en": ["development"],
            "experimentos": [],
            "condiciones_fijas": [
                "corpus",
                "referencia",
                "diccionario",
                "evaluabilidad",
                "particiones",
                "metodo_estadistico",
            ],
            "regla_atribucion": (
                "Si modelo y proveedor no pueden aislarse, describir el cambio conjunto; no "
                "atribuirlo exclusivamente al proveedor."
            ),
        },
        "metricas_secundarias": {
            "por_variable": [],
            "por_categoria": [],
            "grupos_relacionados": [],
            "naturaleza": "secundarias_descriptivas_pre_especificadas",
            "multiplicidad": (
                "Preespecificar ajuste si se añaden contrastes confirmatorios; no "
                "seleccionar resultados por significación."
            ),
        },
        "justificacion_muestral_multicriterio": {
            "objetivos": {
                key: {"insumos": None, "criterio_suficiencia": None, "justificacion": None}
                for key in SIZE_OBJECTIVES
            },
            "sintesis_tamano": None,
            "metodo_planificado": None,
            "pseudoetiquetas_como_verdad_experta": False,
            "fuentes_permitidas": (
                "Referencia independiente en desarrollo o evidencia externa documentada; "
                "nunca estimaciones LLM tratadas como verdad."
            ),
        },
        "aprobacion_estructura": {
            "estado": "borrador",
            "autoriza_congelacion": False,
            "autoriza_ejecucion": False,
        },
        "autorizacion_operativa": {action: False for action in ACTIONS},
    }


def _positive_number(value: Any, name: str, *, integer: bool = False) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise DesignError(f"Valor positivo requerido en {name}.")
    if integer and not isinstance(value, int):
        raise DesignError(f"Se requiere entero en {name}.")


def validate_policy(plan: dict[str, Any], context: dict[str, Any]) -> None:
    """Rechazar contradicciones, sin calcular resultados ni completar decisiones."""
    try:
        if plan["version_validaciones"] != "2.0":
            raise DesignError("Actualiza el diseño al esquema de validaciones 2.0.")
        if not {"fuente", "elegible", "inferencia"}.issubset(plan["poblacion"]):
            raise DesignError("Separar población fuente, elegible y de inferencia.")
        primary = plan["estimando_primario"]
        if (
            primary.get("nombre") != "PGEC"
            or primary.get("contraste_principal") != "PGEC_B - PGEC_A"
        ):
            raise DesignError("Conservar PGEC primario y su diferencia pareada B menos A.")
        parts = plan["particiones_planificadas"]
        if len(parts) != 4 or {p["id"] for p in parts} != PARTITIONS:
            raise DesignError(
                "Se requieren cuatro roles separados: desarrollo, ajuste, calibración y final."
            )
        if plan["separacion_particiones"]["roles_disjuntos"] is not True:
            raise DesignError("La separación por entidad entre roles debe ser explícita.")
        for part in parts:
            _positive_number(part.get("numero_entidades"), "numero_entidades", integer=True)
            value = part.get("proporcion")
            _positive_number(value, "proporcion")
            if value is not None and value >= 1:
                raise DesignError("Cada proporción debe ser menor que uno.")
        if all(p.get("proporcion") is not None for p in parts):
            if not math.isclose(sum(p["proporcion"] for p in parts), 1, abs_tol=1e-9):
                raise DesignError("Las proporciones declaradas deben sumar uno.")
        level = plan["metodo_ic95"].get("nivel_confianza")
        if level is not None and (
            isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 < level < 1
        ):
            raise DesignError("El nivel de confianza debe estar entre cero y uno.")
        for field in ["margen_error_pgec", "precision_diferencia_pareada"]:
            value = plan["tamano_muestra_justificacion"].get(field)
            _positive_number(value, field)
            if value is not None and value > 1:
                raise DesignError("La precisión debe expresarse en escala de proporción.")
        prompts = plan["validacion_prompts"]
        if (
            prompts["particiones_para_seleccion"] != ["development"]
            or prompts["acceso_etiquetas_finales"] is not False
        ):
            raise DesignError(
                "La selección de prompts usa exclusivamente desarrollo, sin etiquetas finales."
            )
        if prompts["seleccionar_con_referencia_independiente"] is not True:
            raise DesignError("La selección necesita referencia independiente de desarrollo.")
        for candidate in prompts.get("candidatos", []):
            if candidate.get("particion") != "development":
                raise DesignError("Cada candidato de prompt debe validarse solo en desarrollo.")
        comparison = plan["configuraciones_comparadas"]
        allowed_a = {"descripcion", "extractor_base_ref"}
        allowed_b = {
            "descripcion",
            "extractor_base_ref",
            "reutiliza_exactamente_salida_A",
            "repite_extraccion",
            "modelo_verificador_y_parametros",
            "instrucciones_version",
            "instrucciones_sha256",
            "politica_reconciliacion_version",
            "lectura_independiente_verificador",
        }
        if set(comparison["A"]) - allowed_a or set(comparison["B"]) - allowed_b:
            raise DesignError("No se permiten sobrescrituras locales del extractor A/B.")
        for role in ["A", "B"]:
            if comparison[role]["extractor_base_ref"] != "extractor_base":
                raise DesignError("A y B deben referenciar el mismo extractor base.")
        if (
            comparison["B"]["reutiliza_exactamente_salida_A"] is not True
            or comparison["B"]["repite_extraccion"] is not False
        ):
            raise DesignError(
                "B debe reutilizar exactamente la salida de A sin repetir extracción."
            )
        for key in [
            "mismos_documentos",
            "mismas_variables",
            "misma_referencia_independiente",
            "misma_definicion_pares_evaluables",
            "salidas_originales_separadas",
        ]:
            if comparison[key] is not True:
                raise DesignError(
                    "El contraste principal requiere condiciones y referencia comunes."
                )
        lineage = comparison["trazabilidad_pareada"]
        if set(lineage) != {
            "mismo_base_extraction_id",
            "mismo_base_output_sha256",
            "mismo_extractor_config_sha256",
            "original_A_inmutable",
        } or not all(v is True for v in lineage.values()):
            raise DesignError(
                "La reutilización de A necesita identificador, huella y configuración comunes."
            )
        secondary = plan["experimentos_secundarios"]
        if (
            secondary["resultados_separados"] is not True
            or secondary["combinar_con_contraste_principal"] is not False
        ):
            raise DesignError(
                "Los experimentos secundarios deben conservar resultados separados del principal."
            )
        if secondary["seleccion_configuraciones_en"] != ["development"]:
            raise DesignError("No se seleccionan modelos/proveedores con etiquetas finales.")
        required_fixed = {
            "corpus",
            "referencia",
            "diccionario",
            "evaluabilidad",
            "particiones",
            "metodo_estadistico",
        }
        if not required_fixed.issubset(secondary["condiciones_fijas"]):
            raise DesignError("Preespecificar las condiciones fijas de comparaciones secundarias.")
        ids = set()
        for experiment in secondary["experimentos"]:
            identifier = experiment.get("id")
            if not identifier or identifier == plan["diseno_id"] or identifier in ids:
                raise DesignError(
                    "Identificadores secundarios únicos y distintos del principal requeridos."
                )
            ids.add(identifier)
            if (
                len(experiment.get("factores_modificados", [])) != 1
                or experiment.get("resultados_separados") is not True
            ):
                raise DesignError(
                    "Cada experimento secundario declara un factor y resultados separados."
                )
        sizes = plan["justificacion_muestral_multicriterio"]
        if (
            set(sizes["objetivos"]) != set(SIZE_OBJECTIVES)
            or sizes["pseudoetiquetas_como_verdad_experta"] is not False
        ):
            raise DesignError(
                "Justificar cinco objetivos de tamaño sin pseudoetiquetas como verdad."
            )
        for name in ["documentos_requeridos", "pacientes_requeridos"]:
            _positive_number(plan["tamano_muestra_justificacion"].get(name), name, integer=True)
        metrics = plan["metricas_secundarias"]
        if {m["variable_id"] for m in metrics["por_variable"]} != set(context["variable_ids"]):
            raise DesignError(
                "Preespecificar métricas secundarias para todas las variables seleccionadas."
            )
        for item in metrics["por_variable"]:
            if not item.get("metricas"):
                raise DesignError("Cada variable necesita métricas secundarias identificadas.")
        for variable, categories in context["categories"].items():
            matches = [m for m in metrics["por_categoria"] if m["variable_id"] == variable]
            if (
                len(matches) != 1
                or set(matches[0]["categorias"]) != set(categories)
                or not matches[0].get("metricas")
            ):
                raise DesignError(
                    "Preespecificar métricas y categorías sin omitir indeterminación."
                )
        for group in metrics["grupos_relacionados"]:
            if not set(group["variables"]).issubset(context["variable_ids"]) or not group.get(
                "metricas"
            ):
                raise DesignError("Grupo secundario con variables o métricas incompatibles.")
        if context["date_variables"] and not any(
            g.get("tipo") == "temporal" and set(context["date_variables"]).issubset(g["variables"])
            for g in metrics["grupos_relacionados"]
        ):
            raise DesignError("Las variables de fecha requieren un grupo temporal preespecificado.")
        if set(plan["autorizacion_operativa"]) != set(ACTIONS):
            raise DesignError("Registrar autorización explícita para cada operación.")
        if any(type(v) is not bool for v in plan["autorizacion_operativa"].values()):
            raise DesignError("Las autorizaciones operativas deben ser booleanas.")
    except DesignError:
        raise
    except (KeyError, TypeError, AttributeError):
        raise DesignError(
            "Diseño incompleto de controles: revisa el esquema 2.0 y sus secciones."
        ) from None


def assess_design(plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    validate_policy(plan, context)
    pending: list[dict[str, str]] = []

    def need(code: str, field: str, ok: Any, reason: str) -> None:
        if not ok:
            pending.append({"id": code, "campo": field, "estado": "pendiente", "motivo": reason})

    need(
        "D01",
        "corpus_disponible.rol_en_el_estudio",
        plan["corpus_disponible"].get("rol_en_el_estudio"),
        "Confirmar función del corpus cargado.",
    )
    for key, fields in {
        "fuente": [
            "descripcion",
            "institucion_o_fuente",
            "periodo_inicio",
            "periodo_fin",
            "marco_muestral",
        ],
        "elegible": [
            "descripcion",
            "criterios_inclusion_aprobados",
            "criterios_exclusion_aprobados",
        ],
        "inferencia": ["descripcion", "relacion_con_elegible", "justificacion_transportabilidad"],
    }.items():
        need(
            f"POB_{key}",
            f"poblacion.{key}",
            all(plan["poblacion"][key].get(f) for f in fields),
            f"Completar población {key} y su justificación.",
        )
    need(
        "D04",
        "unidades.campo_id_paciente",
        plan["unidades"].get("campo_id_paciente")
        and context["patient_grouping_available"]
        and plan["unidades"].get("agrupacion_verificada"),
        "Identificar y verificar agrupación por paciente; ingreso no basta.",
    )
    need(
        "D05",
        "unidades.campo_fecha_consulta",
        plan["unidades"].get("campo_fecha_consulta") and context["document_date_available"],
        "Aportar fecha documental explícita para el ancla temporal.",
    )
    need(
        "D06",
        "muestreo",
        all(plan["muestreo"].get(k) for k in ["tipo", "justificacion", "marco_muestral_disponible"])
        and plan["muestreo"].get("probabilidades_inclusion") is not None
        and plan["muestreo"].get("pesos") is not None,
        "Justificar selección, probabilidades y ponderación, incluso en diseño autoponderado.",
    )
    size = plan["tamano_muestra_justificacion"]
    need(
        "D07",
        "tamano_muestra_justificacion",
        all(
            size.get(k) is not None
            for k in ["margen_error_pgec", "precision_diferencia_pareada", "pacientes_requeridos"]
        ),
        "Fijar precisión y justificar tamaño; no se calcula en esta herramienta.",
    )
    for objective, details in plan["justificacion_muestral_multicriterio"]["objetivos"].items():
        need(
            f"N_{objective}",
            f"justificacion_muestral_multicriterio.objetivos.{objective}",
            all(
                details.get(k) is not None
                for k in ["insumos", "criterio_suficiencia", "justificacion"]
            ),
            f"Documentar suficiencia para {objective}.",
        )
    need(
        "N_sintesis",
        "justificacion_muestral_multicriterio.sintesis_tamano",
        plan["justificacion_muestral_multicriterio"].get("sintesis_tamano"),
        "Integrar las exigencias de precisión, agrupación, rareza y calibración.",
    )
    parts = plan["particiones_planificadas"]
    allocation_defined = all(p.get("numero_entidades") is not None for p in parts) or all(
        p.get("proporcion") is not None for p in parts
    )
    need(
        "D08",
        "particiones_planificadas",
        allocation_defined and plan["separacion_particiones"].get("justificacion_tamanos"),
        "Justificar tamaños de cuatro roles; no fijar porcentajes arbitrarios.",
    )
    need(
        "D10",
        "diccionario",
        context["clinical_criteria_approved"],
        "Criterios clínicos y de corrección todavía no aprobados.",
    )
    need(
        "D11",
        "reglas_evaluabilidad",
        plan["reglas_evaluabilidad"].get("estado") == "aprobado"
        and plan["tratamiento_fallos_abstenciones"].get("estado") == "aprobado",
        "Aprobar denominador, indeterminación, fallos y abstenciones.",
    )
    need(
        "D12",
        "metodo_ic95",
        plan["metodo_ic95"].get("estado") == "aprobado",
        "Aprobar método respetando agrupación, emparejamiento y diseño.",
    )
    need(
        "D13",
        "criterios_congelacion.referencia_final_reservada",
        plan["criterios_congelacion"].get("referencia_final_reservada"),
        "Documentar reserva efectiva de etiquetas finales.",
    )
    prompts = plan["validacion_prompts"]
    need(
        "PROMPT_plan",
        "validacion_prompts",
        prompts.get("regla_desempate") and prompts.get("presupuesto_iteraciones"),
        "Predefinir selección y presupuesto exclusivamente en desarrollo.",
    )
    need(
        "PROMPT_freeze",
        "validacion_prompts.congelacion",
        prompts["congelacion"].get("estado") == "congelado"
        and all(prompts["congelacion"].get(k) for k in ["fecha", "aprobador", "versiones_y_sha256"])
        and prompts.get("extractor_seleccionado")
        and prompts.get("verificador_seleccionado"),
        (
            "Seleccionar, validar y congelar instrucciones antes de evaluar el contraste "
            "confirmatorio."
        ),
    )
    stability = prompts.get("estabilidad", {})
    need(
        "PROMPT_estabilidad",
        "validacion_prompts.estabilidad",
        all(
            stability.get(k) is not None
            for k in ["repeticiones", "variaciones_permitidas", "umbral_aceptacion"]
        ),
        "Predefinir repeticiones, variaciones y aceptación de estabilidad solo en desarrollo.",
    )
    base = plan["configuraciones_comparadas"]["extractor_base"]
    verifier = plan["configuraciones_comparadas"]["B"]
    need(
        "AB_config",
        "configuraciones_comparadas",
        all(
            base.get(k)
            for k in [
                "modelo_y_parametros",
                "instrucciones_version",
                "instrucciones_sha256",
                "esquema_version",
                "reglas_posprocesamiento_version",
            ]
        )
        and all(
            verifier.get(k)
            for k in [
                "modelo_verificador_y_parametros",
                "instrucciones_version",
                "politica_reconciliacion_version",
            ]
        ),
        "Fijar extractor único, verificador y reconciliación versionados.",
    )
    criteria_ready = bool(plan["criterios_congelacion"]) and all(
        v is True for v in plan["criterios_congelacion"].values()
    )
    need(
        "CIERRE",
        "criterios_congelacion",
        criteria_ready,
        "Los criterios de cierre siguen pendientes; no bastan marcas sin evidencia.",
    )
    operations = {}
    for action in ACTIONS:
        reasons = [p["id"] for p in pending]
        if not (
            plan["autorizacion_operativa"][action]
            and context.get("authorized_actions", {}).get(action) is True
        ):
            reasons.append("SIN_AUTORIZACION_USUARIO")
        if context.get("available_actions", {}).get(action) is not True:
            reasons.append("EJECUTOR_NO_IMPLEMENTADO")
        operations[action] = {"permitida": not reasons, "bloqueos": reasons}
    return {
        "version_validaciones": "2.0",
        "decisiones_pendientes": pending,
        "operaciones": operations,
        "protocolo_completo": not pending,
        "nota": (
            "Validación de parámetros, no evaluación científica ni control de acceso del "
            "sistema operativo."
        ),
    }


def require_operation(assessment: dict[str, Any], action: str) -> None:
    if action not in ACTIONS or not assessment["operaciones"][action]["permitida"]:
        raise DesignError(
            "Operación bloqueada: protocolo, autorización o implementación pendientes."
        )


def validate_partition_assignments(rows: list[dict[str, str]]) -> None:
    """Solo inspecciona asignaciones suministradas; nunca genera particiones."""
    entity_roles: dict[str, str] = {}
    documents: set[str] = set()
    for row in rows:
        entity, role, document = row.get("entity_id"), row.get("partition"), row.get("document_id")
        if not entity or role not in PARTITIONS or not document:
            raise DesignError("Asignación sin entidad, documento o rol válido.")
        if entity in entity_roles and entity_roles[entity] != role:
            raise DesignError("Una misma entidad aparece en roles incompatibles.")
        if document in documents:
            raise DesignError("Documento duplicado en las asignaciones.")
        entity_roles[entity] = role
        documents.add(document)


def validate_baseline_reuse(
    a: dict[str, str], b: dict[str, str], a_payload: bytes, b_base_payload: bytes
) -> None:
    """Validar identidad de artefactos A/B suministrados; sin llamar modelos ni medir aciertos."""
    keys = (
        "document_id",
        "variable_id",
        "base_extraction_id",
        "base_output_sha256",
        "extractor_config_sha256",
        "experiment_id",
    )
    if any(not a.get(k) or a.get(k) != b.get(k) for k in keys):
        raise DesignError("A/B no enlazan la misma extracción base y configuración.")
    digest = hashlib.sha256(a_payload).hexdigest()
    if a_payload != b_base_payload or digest != a["base_output_sha256"]:
        raise DesignError("La base consumida por B difiere de la salida original de A.")
