"""Invented XLSX fixtures test source mapping without patient data or external calls."""

import json
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest
import yaml
from openpyxl.utils.datetime import to_excel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from importacion_tabular import TableImportError, parse_document_date, parse_xlsx  # noqa: E402
from laboratorio_yaml_json import LabError, create_simple, import_documents  # noqa: E402


def xlsx_fixture(path, rows, headers=("ingreso", "analisis", "FECHA ATENCIÓN")):
    def cell(column, row, value):
        ref = f"{column}{row}"
        if value is None:
            return f'<c r="{ref}"/>'
        if isinstance(value, datetime):
            return f'<c r="{ref}" s="1"><v>{to_excel(value)}</v></c>'
        if isinstance(value, int):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if isinstance(value, tuple) and value[0] == "formula":
            return f'<c r="{ref}"><f>{escape(value[1])}</f><v>1</v></c>'
        return (
            f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'
        )

    data = "".join(
        f'<row r="{index}">'
        + "".join(cell(chr(65 + k), index, v) for k, v in enumerate(row))
        + "</row>"
        for index, row in enumerate([headers, *rows], 1)
    )
    with ZipFile(path, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>""",  # noqa: E501
        )
        z.writestr(
            "_rels/.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>""",  # noqa: E501
        )
        z.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>""",  # noqa: E501
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>""",  # noqa: E501
        )
        z.writestr(
            "xl/styles.xml",
            """<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font/></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf/><xf numFmtId="14" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>""",  # noqa: E501
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{data}</sheetData></worksheet>',
        )
    return path


def make_lab(tmp_path):
    lab = tmp_path / "lab"
    create_simple(lab)
    settings = {
        "formato_entrada": "xlsx",
        "hoja_entrada": "Hoja1",
        "columna_identificador": "ingreso",
        "columna_texto": "analisis",
        "campo_fecha": "FECHA ATENCIÓN",
        "significado_fecha": "fecha_atencion",
        "tipo_identificador": "ingreso",
        "campo_entidad": None,
        "formato_fecha_texto": "%d/%m/%Y",
    }
    (lab / "datos/importacion.yaml").write_text(yaml.safe_dump(settings, allow_unicode=True))
    return lab


def test_excel_dates_text_and_row_provenance(tmp_path, capsys):
    lab = make_lab(tmp_path)
    text = "Texto inventado\ncon espacios  y <br> literal."
    source = xlsx_fixture(
        tmp_path / "input.xlsx",
        [
            (123, text, datetime(2024, 6, 22)),
            (None, None, None),
            ("00123", "Otra nota inventada", "02/08/2023"),
        ],
    )
    before = source.read_bytes()
    import_documents(lab, source)
    docs = json.loads((lab / "datos/documentos.json").read_bytes())
    assert docs[0]["text"] == text and docs[0]["document_date"] == "2024-06-22"
    assert docs[1]["document_date"] == "2023-08-02"
    assert docs[1]["provenance"]["source_row_number"] == 4
    assert all(d["entity_id"] is None for d in docs)
    assert all(d["provenance"]["date_inferred_from_text"] is False for d in docs)
    assert source.read_bytes() == before
    report = json.loads((lab / "datos/informe_importacion.json").read_bytes())
    assert report["documentos_con_fecha"] == 2 and report["filas_vacias_omitidas"] == 1
    assert report["extraccion_ejecutada"] is False
    assert report["fecha_inicio_exacerbacion_inferida"] is False
    output = capsys.readouterr().out
    assert "Texto inventado" not in output and "00123" not in output


def test_replace_requires_flag_and_preserves_previous_data_and_map(tmp_path):
    lab = make_lab(tmp_path)
    a = xlsx_fixture(tmp_path / "a.xlsx", [(1, "Primera nota inventada", datetime(2024, 1, 1))])
    b = xlsx_fixture(tmp_path / "b.xlsx", [(2, "Segunda nota inventada", datetime(2024, 2, 1))])
    import_documents(lab, a)
    original = (lab / "datos/documentos.json").read_bytes()
    original_map = (lab / ".privado/correspondencia_origen.json").read_bytes()
    with pytest.raises(LabError):
        import_documents(lab, b)
    assert (lab / "datos/documentos.json").read_bytes() == original
    import_documents(lab, b, replace_with_backup=True)
    report = json.loads((lab / "datos/informe_importacion.json").read_bytes())
    backup = lab / report["respaldo_anterior"]
    assert (backup / "documentos.json").read_bytes() == original
    assert (backup / "correspondencia_origen.json").read_bytes() == original_map
    assert backup.stat().st_mode & 0o777 == 0o700
    assert (lab / "datos/documentos.json").stat().st_mode & 0o777 == 0o600
    assert (
        json.loads((lab / "datos/documentos.json").read_bytes())[0]["text"]
        == "Segunda nota inventada"
    )


@pytest.mark.parametrize(
    "row",
    [
        (1, "Texto secreto", "22/06/24"),
        (1, ("formula", "1+1"), datetime(2024, 1, 1)),
        (1, "Texto secreto", 99999),
        (None, "Texto secreto", datetime(2024, 1, 1)),
    ],
)
def test_invalid_cells_do_not_replace_corpus(tmp_path, row):
    lab = make_lab(tmp_path)
    source = xlsx_fixture(tmp_path / "bad.xlsx", [row])
    with pytest.raises(LabError) as error:
        import_documents(lab, source, replace_with_backup=True)
    assert "Texto secreto" not in str(error.value)
    assert json.loads((lab / "datos/documentos.json").read_bytes()) == []
    assert not (lab / ".privado").exists()


def test_blank_date_stays_missing_not_inferred_from_narrative(tmp_path):
    source = xlsx_fixture(
        tmp_path / "missing.xlsx", [(1, "Nota inventada con fecha 2024-01-01", None)]
    )
    rows, _, _ = parse_xlsx(
        source, "ingreso", "analisis", sheet="Hoja1", date_column="FECHA ATENCIÓN"
    )
    assert rows[0].document_date is None


def test_duplicate_headers_and_missing_sheet_are_rejected(tmp_path):
    source = xlsx_fixture(
        tmp_path / "duplicate.xlsx", [], headers=("ingreso", "analisis", "analisis")
    )
    with pytest.raises(TableImportError):
        parse_xlsx(source, "ingreso", "analisis", sheet="Hoja1", date_column=None)
    with pytest.raises(TableImportError):
        parse_xlsx(source, "ingreso", "analisis", sheet="Other", date_column=None)


def test_two_digit_year_does_not_choose_century():
    with pytest.raises(TableImportError):
        parse_document_date("22/06/24", "%d/%m/%y")


def test_missing_active_json_can_be_recreated_with_prior_metadata_backed_up(tmp_path):
    lab = make_lab(tmp_path)
    source = xlsx_fixture(tmp_path / "source.xlsx", [(1, "Nota inventada", datetime(2024, 1, 1))])
    import_documents(lab, source)
    (lab / "datos/documentos.json").unlink()
    mapping = (lab / ".privado/correspondencia_origen.json").read_bytes()
    with pytest.raises(LabError):
        import_documents(lab, source)
    import_documents(lab, source, replace_with_backup=True)
    report = json.loads((lab / "datos/informe_importacion.json").read_bytes())
    assert report["corpus_anterior_disponible"] is False
    assert report["documentos_previos_reportados"] == 1
    assert (
        lab / report["respaldo_anterior"] / "correspondencia_origen.json"
    ).read_bytes() == mapping


def test_write_failure_restores_active_documents_and_private_mapping(tmp_path, monkeypatch):
    import laboratorio_yaml_json as storage

    lab = make_lab(tmp_path)
    first = xlsx_fixture(
        tmp_path / "first.xlsx", [(1, "Primera nota inventada", datetime(2024, 1, 1))]
    )
    second = xlsx_fixture(
        tmp_path / "second.xlsx", [(2, "Segunda nota inventada", datetime(2024, 2, 1))]
    )
    import_documents(lab, first)
    files = [
        lab / "datos/documentos.json",
        lab / "datos/informe_importacion.json",
        lab / ".privado/correspondencia_origen.json",
    ]
    previous = {path: path.read_bytes() for path in files}
    writer = storage.write_json

    def fail_report(path, value, **kwargs):
        if path == lab / "datos/informe_importacion.json":
            raise OSError("Simulated write failure")
        writer(path, value, **kwargs)

    monkeypatch.setattr(storage, "write_json", fail_report)
    with pytest.raises(OSError):
        import_documents(lab, second, replace_with_backup=True)
    assert all(path.read_bytes() == value for path, value in previous.items())
