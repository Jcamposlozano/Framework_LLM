"""Validar las entregas y calcular concordancia previa a la adjudicación."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from statistics import median
from tempfile import mkdtemp

from openpyxl import load_workbook


def normalized_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() else None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value).isoformat()
        except ValueError:
            return None
        return parsed if parsed == value else None
    return None


def validate(content, expected, dictionary, corpus):
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
    issues, seen, records, row_numbers = [], [], {}, {}
    uncited = Counter()
    try:
        identity = dictionary["artifact"]
        signature = " · ".join(identity[key] for key in ("artifact_id", "version", "sha256"))
        if book["Guía"]["C2"].value != signature:
            return records, row_numbers, uncited, [(None, "E1", "Versión de diccionario distinta")]
        rows = book["Anotación"].values
        headers = next(rows, ())
        variables = dictionary["variables"]
        fields = {"document_id", "texto_clinico"}
        for variable in variables:
            key = variable["variable_id"]
            fields.update({key + "_valor", key + "_cita"})
            if variable["data_type"] == "date":
                fields.update({key + "_estado", key + "_motivo"})
        if any(headers.count(field) != 1 for field in fields):
            return records, row_numbers, uncited, [(None, "hoja", "Encabezados inválidos")]

        for number, cells in enumerate(rows, 2):
            if all(cell is None for cell in cells):
                continue
            row = dict(zip(headers, cells, strict=True))
            doc_id = row["document_id"]
            seen.append(doc_id)
            if doc_id not in corpus or row["texto_clinico"] != corpus[doc_id]:
                issues.append((number, "documento", "ID inesperado o texto distinto del corpus"))
                continue
            answers = {}
            for variable in variables:
                key = variable["variable_id"]
                value, quote = row[key + "_valor"], row[key + "_cita"]
                if variable["data_type"] == "date":
                    state, reason = row[key + "_estado"], row[key + "_motivo"]
                    parsed = normalized_date(value)
                    if state == "sin_fecha_determinable":
                        valid = value is None and isinstance(reason, str) and bool(reason.strip())
                    else:
                        valid = state == "fecha_registrada" and parsed is not None
                    value = parsed
                else:
                    valid = value in variable["categories"]
                if not valid:
                    issues.append((number, key, "Valor pendiente, inválido o fecha inconsistente"))
                answers[key] = value
                if quote is None or (isinstance(quote, str) and not quote.strip()):
                    uncited[key] += 1
                elif not isinstance(quote, str) or quote not in corpus[doc_id]:
                    issues.append((number, key, "La cita no coincide literalmente"))
            records[doc_id], row_numbers[doc_id] = answers, number
        if Counter(seen) != Counter(expected):
            issues.append((None, "muestra", "IDs faltantes, adicionales o repetidos"))
    finally:
        book.close()
    return records, row_numbers, uncited, issues


def categorical(pairs):
    n = len(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    observed = sum(left == right for left, right in pairs)
    expected = sum(left_counts[key] * right_counts[key] for key in left_counts)
    denominator = n * n - expected
    return {
        "pares": n,
        "acuerdos": observed,
        "acuerdo": observed / n,
        "kappa_cohen_no_ponderado": (n * observed - expected) / denominator
        if denominator
        else None,
        "frecuencias_experto_01": dict(left_counts),
        "frecuencias_experto_02": dict(right_counts),
    }


def dates(pairs):
    availability = categorical([(left is not None, right is not None) for left, right in pairs])
    # Convert category labels to text rather than letting the JSON encoder rename booleans.
    for field in ("frecuencias_experto_01", "frecuencias_experto_02"):
        counts = availability[field]
        availability[field] = {
            "fecha_registrada": counts.get(True, 0),
            "sin_fecha_determinable": counts.get(False, 0),
        }
    differences = [
        abs((date.fromisoformat(left) - date.fromisoformat(right)).days)
        for left, right in pairs
        if left is not None and right is not None
    ]
    exact = differences.count(0)
    return {
        "disponibilidad": availability,
        "ambos_con_fecha": len(differences),
        "ambos_sin_fecha": sum(left is None and right is None for left, right in pairs),
        "solo_experto_01_con_fecha": sum(
            left is not None and right is None for left, right in pairs
        ),
        "solo_experto_02_con_fecha": sum(
            left is None and right is not None for left, right in pairs
        ),
        "fechas_exactas": exact,
        "acuerdo_exacto_entre_pares_con_fecha": exact / len(differences) if differences else None,
        "mediana_diferencia_absoluta_dias": median(differences) if differences else None,
    }


def write_csv(path, header, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laboratorio", type=Path, required=True)
    parser.add_argument("--muestra", type=Path)
    args = parser.parse_args()
    lab = args.laboratorio
    run = args.muestra or lab / "02_diseno/muestra_expertos_361"
    spec = (lab / "01_especificacion/especificacion.json").read_bytes()
    draw = (run / "registro_sorteo.json").read_bytes()
    dictionary = json.loads(spec)["diccionario_framework"]
    expected = json.loads(draw)["document_ids"]
    expected_ids = set(expected)
    corpus = {
        doc["document_id"]: doc["text"]
        for doc in json.loads((lab / "datos/documentos.json").read_bytes())
        if doc["document_id"] in expected_ids
    }
    if not expected or len(expected) != len(expected_ids) or expected_ids != corpus.keys():
        parser.error("El listado de notas debe ser único y corresponder al corpus.")
    if any(var["data_type"] not in {"categorical", "date"} for var in dictionary["variables"]):
        parser.error("Esta comparación admite variables categóricas y fechas.")

    reports = {}
    capture_issues = []
    for expert in ("01", "02"):
        source = (run / f"experto_{expert}.xlsx").read_bytes()
        records, rows, uncited, issues = validate(source, expected, dictionary, corpus)
        reports[expert] = (records, rows, uncited, hashlib.sha256(source).hexdigest())
        capture_issues.extend((expert, *issue) for issue in issues)

    if capture_issues:
        output = Path(mkdtemp(prefix="revision_concordancia_", dir=run))
        write_csv(
            output / "control_captura.csv",
            ("experto", "fila_excel", "variable", "hallazgo"),
            capture_issues,
        )
        print(f"Hallazgos de captura: {len(capture_issues)}. Informe local: {output}")
        raise SystemExit(2)

    first, first_rows, first_uncited, first_hash = reports["01"]
    second, second_rows, second_uncited, second_hash = reports["02"]
    if first_hash == second_hash:
        parser.error("Los dos archivos son idénticos. Verifica que sean entregas independientes.")
    output = Path(mkdtemp(prefix="revision_concordancia_", dir=run))
    results, disagreements = {}, []
    for variable in dictionary["variables"]:
        key = variable["variable_id"]
        pairs = [(first[doc][key], second[doc][key]) for doc in expected]
        statistics = dates(pairs) if variable["data_type"] == "date" else categorical(pairs)
        results[key] = {
            "sin_cita_experto_01": first_uncited[key],
            "sin_cita_experto_02": second_uncited[key],
            **statistics,
        }
        disagreements.extend(
            (doc, key, first_rows[doc], second_rows[doc], "", "")
            for doc, (left, right) in zip(expected, pairs, strict=True)
            if left != right
        )

    result = {
        "notas": len(expected),
        "fase": "concordancia_antes_de_adjudicacion",
        "diccionario": dictionary["artifact"],
        "sorteo_sha256": hashlib.sha256(draw).hexdigest(),
        "especificacion_sha256": hashlib.sha256(spec).hexdigest(),
        "experto_01_sha256": first_hash,
        "experto_02_sha256": second_hash,
        "variables": results,
    }
    (output / "concordancia.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(
        output / "desacuerdos_para_adjudicacion.csv",
        (
            "document_id",
            "variable",
            "fila_experto_01",
            "fila_experto_02",
            "valor_adjudicado",
            "motivo",
        ),
        disagreements,
    )
    print(
        f"Notas comparadas: {len(expected)} | "
        f"Desacuerdos por documento y variable: {len(disagreements)}"
    )
    for key, stats in results.items():
        if "disponibilidad" in stats:
            print(
                f"{key}: {stats['fechas_exactas']} fechas exactas "
                f"entre {stats['ambos_con_fecha']} pares con fecha"
            )
        else:
            kappa = stats["kappa_cohen_no_ponderado"]
            label = f"{kappa:.3f}" if kappa is not None else "no estimable"
            print(f"{key}: acuerdo {stats['acuerdos']}/{stats['pares']}; kappa {label}")
    print(f"Resultados locales: {output.resolve()}")


if __name__ == "__main__":
    main()
