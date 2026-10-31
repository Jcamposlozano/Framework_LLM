"""Descriptive within-document agreement. No reference labels, accuracy or PGEC."""

import json
from collections import Counter
from datetime import date
from itertools import combinations
from typing import Any

from extracteval.application.comparison import original_state
from extracteval.core.hashing import canonical_bytes
from extracteval.core.verification import ExtractionSnapshot, ReconciledExtraction

WARNING = "RESULTADOS SINTÉTICOS DE PRUEBA — NO CONSTITUYEN EVIDENCIA DE ESTABILIDAD DEL LLM."


def observations(a: ExtractionSnapshot, b: ReconciledExtraction) -> dict[str, Any]:
    """Extract neutral outcomes from the persisted contracts, without copying note text."""
    left = {}
    for item in a.results:
        state = original_state(a, item.trace.variable_id)
        left[item.trace.variable_id] = {
            "value": item.value.model_dump(mode="json") if item.value else None,
            "state": state.value if state else None,
            "error": item.technical_error.code if item.technical_error else None,
            "evidence_available": bool(item.evidence.items),
            "abstention_reason": item.abstention.reason if item.abstention else None,
        }
    right = {}
    for decision in b.decisions:
        # B is a decision artifact, not a second independent evidence extraction.
        right[decision.variable_id] = {
            "value": decision.resulting_value.model_dump(mode="json")
            if decision.resulting_value
            else None,
            "state": decision.resulting_state.value if decision.resulting_state else None,
            "error": decision.technical_error.code if decision.technical_error else None,
            "evidence_available": left[decision.variable_id]["evidence_available"]
            if decision.action in ("KEEP_A", "HUMAN_REVIEW")
            else None,
            "decision": decision.action.value,
            "reason": decision.reason,
        }
    return {"A": left, "B": right}


def signature(outcome: dict[str, Any]) -> bytes:
    return canonical_bytes({k: outcome[k] for k in ("value", "state", "error")})


def eligible(outcome: dict[str, Any]) -> bool:
    return outcome["error"] is None and outcome["state"] not in (None, "no_response")


def fraction(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerador": numerator,
        "denominador": denominator,
        "proporcion": numerator / denominator if denominator else None,
    }


def compare_repetitions(rows: list[dict[str, Any]], variable_ids: list[str]) -> dict[str, Any]:
    """Never pool modalities. Pairs are unordered and always within one document."""
    profiles, concordance = [], []
    for modality in sorted({r["modalidad"] for r in rows}):
        selected = [r for r in rows if r["modalidad"] == modality]
        doc_ids = sorted({r["document_id"] for r in selected})
        summaries: dict[str, dict[str, Any]] = {"A": {}, "B": {}}
        for system in ("A", "B"):
            for key in variable_ids:
                exact = pair_count = operational_matches = all_pairs = invariant = eligible_docs = 0
                outcomes: list[dict[str, Any]] = []
                date_pairs = date_matches = 0
                for doc_id in doc_ids:
                    values = [
                        r["observaciones"][system][key]
                        for r in selected
                        if r["document_id"] == doc_id
                    ]
                    outcomes.extend(values)
                    signatures = [signature(v) for v in values]
                    dates = [
                        date.fromisoformat(v["value"]["value"])
                        for v in values
                        if v["value"] and v["value"]["kind"] == "date" and eligible(v)
                    ]
                    valid = [v for v in values if eligible(v)]
                    if len(values) >= 2 and len(valid) == len(values):
                        eligible_docs += 1
                        invariant += len(set(signatures)) == 1
                    for a, b in combinations(values, 2):
                        all_pairs += 1
                        operational_matches += signature(a) == signature(b)
                        if eligible(a) and eligible(b):
                            pair_count += 1
                            exact += signature(a) == signature(b)
                    for a, b in combinations(dates, 2):
                        date_pairs += 1
                        date_matches += a == b
                    profiles.append(
                        {
                            "modalidad": modality,
                            "sistema": system,
                            "document_id": doc_id,
                            "variable_id": key,
                            "repeticiones": len(values),
                            "resultados_distintos": len(set(signatures)),
                            "valores_distintos": len(
                                {
                                    canonical_bytes(v["value"])
                                    for v in values
                                    if v["value"] is not None
                                }
                            ),
                            "fechas_distintas": len(set(dates)),
                            "rango_fechas_dias": (max(dates) - min(dates)).days if dates else None,
                            "fechas_validas": len(dates),
                        }
                    )
                n = len(outcomes)
                distribution = Counter(
                    v["value"]["value"]
                    for v in outcomes
                    if v["value"] and v["value"]["kind"] == "categorical"
                )
                summaries[system][key] = {
                    "acuerdo_exacto": fraction(exact, pair_count),
                    "acuerdo_operativo_incluye_fallos": fraction(operational_matches, all_pairs),
                    "documentos_invariables": fraction(invariant, eligible_docs),
                    "distribucion_categorias": dict(distribution),
                    "denominador_categorias": sum(distribution.values()),
                    "indeterminacion": fraction(
                        sum(v["state"] == "indeterminate" for v in outcomes), n
                    ),
                    "abstencion": fraction(sum(v["state"] == "abstain" for v in outcomes), n),
                    "fallo_tecnico": fraction(sum(v["error"] is not None for v in outcomes), n),
                    "falta_respuesta": fraction(
                        sum(v["state"] == "no_response" for v in outcomes), n
                    ),
                    "evidencia_disponible": fraction(
                        sum(v["evidence_available"] is True for v in outcomes), n
                    ),
                    "acuerdo_fechas_validas": fraction(date_matches, date_pairs),
                    "fecha_no_determinada": fraction(sum(v["value"] is None for v in outcomes), n)
                    if key == "fecha_indice_evento"
                    else None,
                    "por_diseno": system == "A" and modality == "A_fija",
                }
        full = {}
        decisions_changed = decisions_pairs = categories_changed = category_pairs = 0
        variables_changing: Counter[str] = Counter()
        for system in ("A", "B"):
            matches = denominator = 0
            for doc_id in doc_ids:
                group = [r for r in selected if r["document_id"] == doc_id]
                for a, b in combinations(group, 2):
                    if all(
                        eligible(row["observaciones"][system][k])
                        for row in (a, b)
                        for k in variable_ids
                    ):
                        denominator += 1
                        changed = [
                            k
                            for k in variable_ids
                            if signature(a["observaciones"][system][k])
                            != signature(b["observaciones"][system][k])
                        ]
                        matches += not changed
                        variables_changing.update(system + ":" + k for k in changed)
            full[system] = {
                "acuerdo_registro_completo": fraction(matches, denominator),
                "cambio_alguna_variable": fraction(denominator - matches, denominator),
                "por_diseno": modality == "A_fija" and system == "A",
            }
        for doc_id in doc_ids:
            group = [r for r in selected if r["document_id"] == doc_id]
            for a, b in combinations(group, 2):
                for key in variable_ids:
                    decisions_pairs += 1
                    decisions_changed += (
                        a["observaciones"]["B"][key]["decision"]
                        != b["observaciones"]["B"][key]["decision"]
                    )
            for row in group:
                for key in variable_ids:
                    a, b = row["observaciones"]["A"][key], row["observaciones"]["B"][key]
                    if all(
                        v["value"] and v["value"]["kind"] == "categorical" and eligible(v)
                        for v in (a, b)
                    ):
                        category_pairs += 1
                        categories_changed += a["value"] != b["value"]
        delta = {}
        paired = {}
        for key in variable_ids:
            common = matches_a = matches_b = 0
            for doc_id in doc_ids:
                group = [r for r in selected if r["document_id"] == doc_id]
                for first, second in combinations(group, 2):
                    if all(
                        eligible(row["observaciones"][system][key])
                        for row in (first, second)
                        for system in ("A", "B")
                    ):
                        common += 1
                        matches_a += signature(first["observaciones"]["A"][key]) == signature(
                            second["observaciones"]["A"][key]
                        )
                        matches_b += signature(first["observaciones"]["B"][key]) == signature(
                            second["observaciones"]["B"][key]
                        )
            paired[key] = {"A": fraction(matches_a, common), "B": fraction(matches_b, common)}
            delta[key] = (matches_b - matches_a) / common if common else None
        concordance.append(
            {
                "modalidad": modality,
                "documentos": len(doc_ids),
                "por_variable": summaries,
                "registro_completo": full,
                "diferencia_descriptiva_B_menos_A": delta,
                "contraste_pareado": paired,
                "cambio_decision_B": fraction(decisions_changed, decisions_pairs),
                "cambio_categoria_A_B": fraction(categories_changed, category_pairs),
                "variables_que_cambian": dict(variables_changing),
            }
        )
    return {
        "perfiles": profiles,
        "concordancia": concordance,
        "denominadores": {
            "acuerdo_exacto": (
                "Pares no ordenados de repeticiones del mismo documento, sin fallo técnico ni "
                "falta de respuesta; incluye estados semánticos y abstenciones explícitas."
            ),
            "acuerdo_operativo": (
                "Todos los pares intradocumento; incluye coincidencias "
                "de errores. No representa acuerdo clínico."
            ),
            "documentos_invariables": (
                "Documentos con al menos dos repeticiones y todas "
                "sin fallo técnico ni falta de respuesta."
            ),
            "tasas": "Todos los resultados documento-repetición de la modalidad y sistema.",
            "registro_completo": (
                "Pares intradocumento con seis resultados elegibles en ambas repeticiones."
            ),
            "fechas": (
                "Pares intradocumento con dos fechas válidas. "
                "Rango en días calculado por documento."
            ),
            "categorias": (
                "Valores categóricos no nulos observados; consultar su denominador específico."
            ),
            "cambio_decision": "Pares intradocumento multiplicados por las seis variables.",
            "delta": (
                "Diferencia descriptiva sobre exactamente los mismos pares elegibles A/B. "
                "A_fija es constante por diseño; no estima repetibilidad empírica de A."
            ),
        },
    }


def render_report(results: dict[str, Any]) -> str:
    lines = [
        "# Informe técnico de estabilidad",
        "",
        WARNING
        if results["modo"] == "mock"
        else "RESULTADOS DESCRIPTIVOS — SIN VALIDACIÓN CLÍNICA NI INFERENCIA CONFIRMATORIA.",
        "",
        f"Documentos: {results['documentos']}. Repeticiones: {len(results['ejecuciones'])}.",
        "Completadas sin fallo: "
        f"{sum(r['estado'] == 'completed' for r in results['ejecuciones'])}; "
        "Con fallo técnico: "
        f"{sum(r['estado'] == 'technical_failure' for r in results['ejecuciones'])}; "
        f"interrumpidas: {sum(r['estado'] == 'interrupted' for r in results['ejecuciones'])}.",
        "",
        "## Configuraciones",
        "",
        "```json",
        json.dumps(results["configuraciones"], ensure_ascii=False, indent=2),
        "```",
    ]
    for summary in results["concordancia"]:
        lines += [
            "",
            "## Modalidad " + summary["modalidad"],
            "",
            "| Variable | Acuerdo A | Acuerdo B | B − A |",
            "|---|---:|---:|---:|",
        ]
        for key in summary["por_variable"]["A"]:
            values = [summary["por_variable"][s][key]["acuerdo_exacto"] for s in ("A", "B")]
            cells = [f"{v['numerador']}/{v['denominador']}" for v in values]
            lines.append(
                f"| {key} | {cells[0]} | {cells[1]} | "
                f"{summary['diferencia_descriptiva_B_menos_A'][key]} |"
            )
        lines += [
            "",
            "Registro completo: " + str(summary["registro_completo"]),
            "Cambios en decisiones B: " + str(summary["cambio_decision_B"]),
            "Variables con cambios: " + str(summary["variables_que_cambian"]),
        ]
        for system in ("A", "B"):
            lines += ["", f"### {system}: fechas, abstenciones y fallos", ""]
            for key, metrics in summary["por_variable"][system].items():
                lines.append(
                    f"- {key}: abstenciones {metrics['abstencion']}; "
                    f"fallos {metrics['fallo_tecnico']}."
                )
            temporal = [
                p
                for p in results["perfiles"]
                if p["sistema"] == system
                and p["modalidad"] == summary["modalidad"]
                and p["variable_id"] == "fecha_indice_evento"
            ]
            lines.append(
                "Rangos temporales por documento (días): "
                + str({p["document_id"]: p["rango_fechas_dias"] for p in temporal})
            )
    lines += ["", "## Denominadores", ""] + [
        f"- {k}: {v}" for k, v in results["denominadores"].items()
    ]
    lines += [
        "",
        "## Limitaciones",
        "",
        "- Los mocks reproducen guiones programados, no miden estabilidad de un LLM.",
        "- A_fija es constante por diseño; no estima repetibilidad empírica de A.",
        "- Las repeticiones no son observaciones independientes ni pacientes distintos.",
        "- No se calcula PGEC, exactitud ni intervalos confirmatorios. No hay referencia experta.",
        (
            "- La política conservadora puede preservar variación "
            "de A; estabilidad no implica corrección."
        ),
        "- Perturbaciones deshabilitadas; no se ha evaluado robustez documental.",
    ]
    return "\n".join(lines) + "\n"
