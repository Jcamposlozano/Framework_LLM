"""Generar una hoja de anotación independiente desde el diccionario E1 local."""

import argparse
import csv
import json
import os
import textwrap
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from extracteval.core.specification import OperationalDictionary


def set_text(cell, value):
    if len(value) > 32767:
        raise ValueError("Un campo de texto excede el límite de Excel.")
    cell.value = value
    cell.data_type = "s"


def load_notes(laboratory, csv_path):
    corpus = json.loads((laboratory / "datos/documentos.json").read_bytes())
    by_id = {item["document_id"]: item for item in corpus}
    notes = []
    seen = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        if not {"document_id", "estrato", "texto_clinico"} <= set(reader.fieldnames or []):
            raise ValueError("El CSV debe incluir document_id, estrato y texto_clinico.")
        for row in reader:
            doc_id = row["document_id"]
            if doc_id in seen or doc_id not in by_id:
                raise ValueError("El CSV contiene un ID repetido o ausente del corpus.")
            seen.add(doc_id)
            document = by_id[doc_id]
            if row["texto_clinico"] != document.get("text"):
                raise ValueError("El texto de una nota del CSV difiere del corpus.")
            document_date = document.get("document_date")
            notes.append(
                (
                    doc_id,
                    row["estrato"],
                    date.fromisoformat(document_date) if document_date else None,
                    document["text"],
                )
            )
    if not notes:
        raise ValueError("El CSV no contiene documentos.")
    return notes


def header(sheet):
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="1F415C")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[1].height = 30


def add_list(workbook, sheet, options, target, number):
    lists = workbook["Listas"]
    for row, code in enumerate(options, 1):
        set_text(lists.cell(row, number), code)
    column = get_column_letter(number)
    name = f"Opciones_{number}"
    workbook.defined_names.add(
        DefinedName(name, attr_text=f"'Listas'!${column}$1:${column}${len(options)}")
    )
    validation = DataValidation(type="list", formula1=f"={name}", allow_blank=True)
    validation.errorTitle = "Valor fuera del diccionario"
    validation.error = "Selecciona una opción de la lista."
    validation.errorStyle = "stop"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    validation.add(target)


def make_workbook(dictionary, notes):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Anotación"
    guide = workbook.create_sheet("Guía")
    workbook.create_sheet("Listas").sheet_state = "hidden"
    variables = dictionary.variables
    columns = ["document_id", "estrato", "fecha_atencion", "texto_clinico"]
    columns += [f"{variable.variable_id}_valor" for variable in variables]
    columns += [f"{variable.variable_id}_cita" for variable in variables]
    dates = [variable for variable in variables if variable.data_type == "date"]
    for variable in dates:
        columns += [f"{variable.variable_id}_estado", f"{variable.variable_id}_motivo"]
    sheet.append(columns)
    header(sheet)
    sheet.freeze_panes = "B2"
    sheet.sheet_view.zoomScale = 85
    style_text = Alignment(wrap_text=True, vertical="top")
    for number, label in enumerate(columns, 1):
        column = get_column_letter(number)
        sheet.column_dimensions[column].width = (
            92
            if label == "texto_clinico"
            else 37
            if label.endswith(("_cita", "_motivo"))
            else 25
            if label == "document_id"
            else 22
        )
    for row, (doc_id, stratum, consultation, text) in enumerate(notes, 2):
        for column, value in ((1, doc_id), (2, stratum), (4, text)):
            set_text(sheet.cell(row, column), value)
        sheet.cell(row, 3).value = consultation
        sheet.cell(row, 3).number_format = "yyyy-mm-dd"
        sheet.cell(row, 4).alignment = style_text
        sheet.row_dimensions[row].height = min(
            195,
            max(
                45,
                15 * sum(max(1, len(textwrap.wrap(line, width=85))) for line in text.splitlines()),
            ),
        )
    last_row = len(notes) + 1 if notes else 1001
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last_row}"
    for number, variable in enumerate(variables, 1):
        column = get_column_letter(4 + number)
        start = f"{column}2"
        target = f"{start}:{column}{last_row}"
        if variable.data_type == "categorical":
            add_list(workbook, sheet, variable.categories, target, number)
            for row in range(2, last_row + 1):
                sheet.cell(row, 4 + number).number_format = "@"
        elif variable.data_type == "date":
            validation = DataValidation(
                type="custom",
                formula1=f'OR({start}="",AND(ISNUMBER({start}),{start}=INT({start}),'
                f"{start}>=DATE(1900,1,1),{start}<=DATE(9999,12,31)))",
                allow_blank=True,
                showErrorMessage=True,
                errorStyle="stop",
                error="Escribe una fecha de calendario o deja el valor vacío.",
            )
            sheet.add_data_validation(validation)
            validation.add(target)
            for row in range(2, last_row + 1):
                sheet.cell(row, 4 + number).number_format = "yyyy-mm-dd"
    for number, variable in enumerate(dates, len(variables) + 1):
        column = get_column_letter(columns.index(f"{variable.variable_id}_estado") + 1)
        add_list(
            workbook,
            sheet,
            ("fecha_registrada", "sin_fecha_determinable"),
            f"{column}2:{column}{last_row}",
            number,
        )

    guide.append(["Campo", "Aspecto", "Instrucción"])
    header(guide)
    guide.freeze_panes = "A2"
    guide.column_dimensions["A"].width = 30
    guide.column_dimensions["B"].width = 27
    guide.column_dimensions["C"].width = 100

    def guide_row(field, aspect, instruction):
        row = guide.max_row + 1
        for column, value in enumerate((field, aspect, instruction), 1):
            cell = guide.cell(row, column)
            set_text(cell, value)
            cell.alignment = style_text
        guide.row_dimensions[row].height = min(
            390, max(30, 16 * (len(textwrap.wrap(instruction, width=90)) + 1))
        )

    artifact = dictionary.artifact
    guide_row(
        "Diccionario E1",
        "Versión y huella",
        f"{artifact.artifact_id} · {artifact.version} · {artifact.sha256}",
    )
    status = (
        "Aprobación registrada"
        if dictionary.clinically_approved
        else "Borrador, aprobación clínica pendiente"
    )
    guide_row("Diccionario E1", "Estado", status)
    guide_row(
        "Anotación",
        "Valor y evidencia",
        "Registra el valor según E1. Si el protocolo pide evidencia, copia "
        "el fragmento literal de la nota en la columna _cita.",
    )
    guide_row(
        "Fecha",
        "Estado de captura",
        "Deja el estado vacío si todavía no revisaste la fecha. "
        "Marca fecha_registrada si anotaste una fecha. Si el protocolo indica que "
        "no puede establecerse, marca sin_fecha_determinable y consigna el motivo.",
    )
    for variable in variables:
        key = variable.variable_id
        guide_row(key, "Definición", variable.operational_definition)
        guide_row(
            key,
            "Formato",
            ", ".join(variable.categories)
            or (
                "AAAA-MM-DD (fecha de Excel)"
                if variable.data_type == "date"
                else variable.data_type
            ),
        )
        for rule in variable.interpretation_rules:
            guide_row(key, "Interpretación", rule)
        for rule in variable.correctness_criteria:
            guide_row(key, "Criterio de corrección", rule)
        for label, rule in (
            ("Ausencia documental", variable.information_policy.absent),
            ("Indeterminación", variable.information_policy.indeterminate),
            ("No aplicabilidad", variable.information_policy.not_applicable),
        ):
            guide_row(key, label, rule)
    return workbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--laboratorio", type=Path)
    source.add_argument("--diccionario", type=Path, help="Generar una plantilla vacía.")
    parser.add_argument(
        "--csv", type=Path, help="Reemplazar el CSV maestro por un CSV de la muestra."
    )
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    if args.salida.suffix.lower() != ".xlsx" or (args.csv and not args.laboratorio):
        parser.error("Usa salida .xlsx y proporciona --laboratorio si indicas --csv.")
    if args.salida.exists():
        parser.exit(2, "La salida ya existe. Elige otro nombre.\n")
    try:
        if args.laboratorio:
            spec = args.laboratorio / "01_especificacion/especificacion.json"
            dictionary = OperationalDictionary.model_validate(
                json.loads(spec.read_bytes())["diccionario_framework"]
            )
            csv_path = args.csv or args.laboratorio / "02_diseno/corpus_elegible_anotacion.csv"
            notes = load_notes(args.laboratorio, csv_path)
        else:
            dictionary = OperationalDictionary.model_validate_json(args.diccionario.read_bytes())
            notes = []
        workbook = make_workbook(dictionary, notes)
        with NamedTemporaryFile(dir=args.salida.parent, suffix=".xlsx") as temporary:
            workbook.save(temporary.name)
            os.link(temporary.name, args.salida)
    except (KeyError, OSError, ValueError, csv.Error):
        parser.exit(
            2,
            "No se creó el Excel. Revisa las rutas, el formato del CSV "
            "y la correspondencia con el corpus.\n",
        )
    print(
        f"Excel creado: {args.salida.resolve()} | Notas: {len(notes)} "
        f"| Variables: {len(dictionary.variables)}"
    )


if __name__ == "__main__":
    main()
