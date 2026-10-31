"""Pruebas sintéticas de edición YAML, documentos multilínea y organización simplificada."""

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from extracteval.core.documents import Document
from extracteval.core.specification import OperationalDictionary

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/laboratorio.py"


def command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def make_lab(tmp_path: Path) -> Path:
    path = tmp_path / "laboratorio"
    result = command("crear", "--destino", str(path))
    assert result.returncode == 0, result.stderr
    return path


def make_source(tmp_path: Path) -> tuple[Path, list[tuple[str, str]]]:
    records = [
        (
            "synthetic-id-01",
            "Texto sintético de primera línea.\nSegunda línea con tabulador:\tfin.",
        ),
        ("synthetic-id-01", 'Otra nota sintética con "comillas".'),
    ]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\r\n")
    writer.writerow(["ingreso", "analisis"])
    writer.writerows(records)
    path = tmp_path / "input.txt"
    path.write_bytes(stream.getvalue().encode("utf-8"))
    return path, records


def test_new_labs_only_contain_yaml_and_json(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    files = [path for path in lab.rglob("*") if path.is_file()]
    assert len(files) == 22
    assert {path.suffix for path in files} == {".yaml", ".json"}
    assert json.loads((lab / "datos/documentos.json").read_text()) == []
    state = json.loads((lab / "control/estado.json").read_text())
    assert all(stage["estado"] == "pendiente" for stage in state["etapas"])
    assert sum(len(stage["lista_chequeo"]) for stage in state["etapas"]) == 49
    assert command("estado", "--laboratorio", str(lab)).returncode == 0
    assert command("crear", "--destino", str(lab)).returncode == 2


def test_multiline_ingestion_preserves_content_and_pseudonymizes(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    source, records = make_source(tmp_path)
    result = command("importar-textos", "--laboratorio", str(lab), "--archivo", str(source))
    assert result.returncode == 0, result.stderr
    documents = json.loads((lab / "datos/documentos.json").read_text())
    assert [doc["text"] for doc in documents] == [record[1] for record in records]
    assert len({doc["document_id"] for doc in documents}) == 2
    assert (
        documents[0]["provenance"]["source_record_id"]
        == documents[1]["provenance"]["source_record_id"]
    )
    for item in documents:
        Document.model_validate(item)
        assert item["entity_id"] is None and item["document_date"] is None
        assert "synthetic-id" not in item["document_id"]
        assert "synthetic-id" not in json.dumps(item["provenance"])
    assert "Texto sintético" not in result.stdout + result.stderr
    assert "synthetic-id" not in result.stdout + result.stderr
    report = json.loads((lab / "datos/informe_importacion.json").read_text())
    assert report["documentos_importados"] == 2
    assert report["narrativa_anonimizada"] is False
    assert report["extraccion_ejecutada"] is False
    assert report["agrupacion_por_paciente_disponible"] is False
    if os.name == "posix":
        assert (lab / ".privado").stat().st_mode & 0o777 == 0o700
        assert (lab / ".privado/clave_pseudonimos.json").stat().st_mode & 0o777 == 0o600
        assert (lab / "datos/documentos.json").stat().st_mode & 0o777 == 0o600


def test_reimport_does_not_overwrite_existing_documents(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    source, _ = make_source(tmp_path)
    args = ("importar-textos", "--laboratorio", str(lab), "--archivo", str(source))
    assert command(*args).returncode == 0
    previous = (lab / "datos/documentos.json").read_bytes()
    assert command(*args).returncode == 2
    assert previous == (lab / "datos/documentos.json").read_bytes()


@pytest.mark.parametrize(
    "content",
    [
        "ingreso\tanalisis\nsecret-id\t\n",
        "ingreso\tanalisis\nsecret-id\tprivate text\textra\n",
        'ingreso\tanalisis\nsecret-id\t"private text\n',
        "otra\tcabecera\nsecret-id\tprivate text\n",
    ],
)
def test_invalid_input_is_safe_and_does_not_partially_import(tmp_path: Path, content: str) -> None:
    lab = make_lab(tmp_path)
    source = tmp_path / "invalid.txt"
    source.write_text(content)
    result = command("importar-textos", "--laboratorio", str(lab), "--archivo", str(source))
    assert result.returncode == 2
    assert "private text" not in result.stdout + result.stderr
    assert "secret-id" not in result.stdout + result.stderr
    assert json.loads((lab / "datos/documentos.json").read_text()) == []
    assert not (lab / ".privado").exists()


def test_yaml_source_compiles_without_losing_metadata(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    specification = {
        "dictionary_id": "synthetic",
        "version": "1-draft",
        "status": "pending_review",
        "purpose": "Synthetic use",
        "principles": ["Use documented evidence"],
        "variables": {
            "decision": {
                "type": "categorical",
                "required": True,
                "allowed_values": ["true", "false", "indeterminado"],
                "definition": "Synthetic decision",
                "categories": {"true": "Positive", "false": "Negative", "indeterminado": "Unclear"},
            },
            "event_date": {
                "type": "date_or_null",
                "definition": "Documented date",
                "null_policy": "No date if unavailable",
            },
        },
        "metadata_contract": {"document_id": "required"},
        "pending_decisions": ["Define tolerance"],
    }
    path = lab / "01_especificacion/especificacion.yaml"
    path.write_text(yaml.safe_dump(specification, allow_unicode=True, sort_keys=False))
    result = command("preparar-especificacion", "--laboratorio", str(lab))
    assert result.returncode == 0, result.stderr
    generated = json.loads((lab / "01_especificacion/especificacion.json").read_text())
    assert generated["especificacion_completa"] == specification
    dictionary = OperationalDictionary.model_validate(generated["diccionario_framework"])
    assert dictionary.variable("decision").categories == ("true", "false", "indeterminado")
    assert dictionary.variable("event_date").data_type == "date"
    assert generated["revision_clinica_verificada"] is False
    assert generated["reglas_ejecutadas"] is False
    assert command("preparar-especificacion", "--laboratorio", str(lab)).returncode == 0
    assert len(list((lab / ".historial/especificacion").glob("*.json"))) == 1


def test_duplicate_yaml_keys_and_unsafe_tags_are_rejected(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    path = lab / "01_especificacion/especificacion.yaml"
    for content in ["version: 1\nversion: 2\n", "value: !!python/object:os.system {}\n"]:
        path.write_text(content)
        result = command("preparar-especificacion", "--laboratorio", str(lab))
        assert result.returncode == 2
        assert "Traceback" not in result.stderr


def test_unknown_entity_date_mapping_is_not_inferred(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    source, _ = make_source(tmp_path)
    path = lab / "datos/importacion.yaml"
    settings = yaml.safe_load(path.read_text())
    settings["campo_entidad"] = "ingreso"
    path.write_text(yaml.safe_dump(settings))
    assert (
        command("importar-textos", "--laboratorio", str(lab), "--archivo", str(source)).returncode
        == 2
    )
    assert not (lab / ".privado").exists()


def test_completed_stage_requires_recorded_product(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    path = lab / "control/estado.json"
    state = json.loads(path.read_text())
    stage = state["etapas"][0]
    stage["estado"] = "completado"
    for task in stage["lista_chequeo"]:
        task["estado"] = "no_aplica"
        task["observaciones"] = "Justificación sintética; el alcance necesita revisión humana"
    path.write_text(json.dumps(state))
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 1
    assert "falta ruta de evidencia" in result.stdout
    assert "falta resultado registrado" in result.stdout


def prepare_design_fixture(lab: Path) -> dict[str, object]:
    specification = {
        "dictionary_id": "synthetic",
        "version": "1-draft",
        "status": "pending_review",
        "variables": {
            "decision": {
                "type": "categorical",
                "allowed_values": ["yes", "no"],
                "definition": "Synthetic documented decision",
            }
        },
    }
    (lab / "01_especificacion/especificacion.yaml").write_text(yaml.safe_dump(specification))
    assert command("preparar-especificacion", "--laboratorio", str(lab)).returncode == 0
    report = {
        "documentos_importados": 0,
        "agrupacion_por_paciente_disponible": False,
        "fecha_documental_disponible": False,
    }
    (lab / "datos/informe_importacion.json").write_text(json.dumps(report))
    plan = {
        "diseno_id": "synthetic-design",
        "version": "1-draft",
        "estimando_primario": {
            "variables": ["decision"],
            "nombre": "PGEC",
            "contraste_principal": "PGEC_B - PGEC_A",
        },
        "configuraciones_comparadas": {
            "mismos_documentos": True,
            "misma_referencia_independiente": True,
            "misma_definicion_pares_evaluables": True,
        },
        "particiones_planificadas": [
            {"id": key, "proporcion": None, "numero_entidades": None}
            for key in ["development", "calibration", "evaluation"]
        ],
        "metodo_ic95": {"nivel_confianza": 0.95, "estado": "propuesto"},
        "corpus_disponible": {"documentos_importados": 0, "rol_en_el_estudio": None},
        "poblacion": {},
        "unidades": {},
        "muestreo": {},
        "tamano_muestra_justificacion": {},
        "plan_ajuste_calibracion": {},
        "reglas_evaluabilidad": {"estado": "propuesto"},
        "tratamiento_fallos_abstenciones": {"estado": "propuesto"},
        "criterios_congelacion": {},
        "congelacion": {"estado": "no_congelado"},
    }
    sys.path.insert(0, str(SCRIPT.parent))
    from diseno_validaciones import policy_defaults

    plan.update(policy_defaults())
    plan["metricas_secundarias"]["por_variable"] = [
        {"variable_id": "decision", "metricas": ["exactitud"]}
    ]
    plan["metricas_secundarias"]["por_categoria"] = [
        {"variable_id": "decision", "categorias": ["yes", "no"], "metricas": ["sensibilidad"]}
    ]
    (lab / "02_diseno/diseno.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    return plan


def test_design_preparation_records_plan_but_computes_no_statistics(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    plan = prepare_design_fixture(lab)
    result = command("preparar-diseno", "--laboratorio", str(lab))
    assert result.returncode == 0, result.stderr
    data = json.loads((lab / "02_diseno/resultados.json").read_text())
    assert data["plan_estadistico"] == plan
    assert len(data["decisiones_pendientes"]) >= 20
    assert all(not v["permitida"] for v in data["validacion_protocolo"]["operaciones"].values())
    assert data["muestreo_ejecutado"] is False
    assert data["metricas_calculadas"] is False
    assert data["particiones_asignadas_por_este_comando"] is False
    for field in ["muestra", "particiones", "pesos", "controles_fuga"]:
        assert data[field] == []
    assert len(list((lab / "02_diseno").iterdir())) == 2


@pytest.mark.parametrize("case", ["variable", "unpaired", "frozen"])
def test_design_rejects_inconsistent_or_premature_finalization(tmp_path: Path, case: str) -> None:
    lab = make_lab(tmp_path)
    plan = prepare_design_fixture(lab)
    if case == "variable":
        plan["estimando_primario"]["variables"] = ["unknown"]
    elif case == "unpaired":
        plan["configuraciones_comparadas"]["mismos_documentos"] = False
    else:
        plan["congelacion"]["estado"] = "congelado"
    (lab / "02_diseno/diseno.yaml").write_text(yaml.safe_dump(plan))
    before = (lab / "02_diseno/resultados.json").read_bytes()
    result = command("preparar-diseno", "--laboratorio", str(lab))
    assert result.returncode == 2
    assert before == (lab / "02_diseno/resultados.json").read_bytes()


def test_design_preserves_records_and_refuses_silent_plan_replacement(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    plan = prepare_design_fixture(lab)
    assert command("preparar-diseno", "--laboratorio", str(lab)).returncode == 0
    path = lab / "02_diseno/resultados.json"
    data = json.loads(path.read_text())
    data["muestra"] = [{"document_id": "synthetic-001"}]
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    assert command("preparar-diseno", "--laboratorio", str(lab)).returncode == 0
    assert before == path.read_bytes()
    plan["version"] = "2-draft"
    (lab / "02_diseno/diseno.yaml").write_text(yaml.safe_dump(plan))
    assert command("preparar-diseno", "--laboratorio", str(lab)).returncode == 2
    assert before == path.read_bytes()


@pytest.mark.parametrize(
    "action", ["congelar", "muestreo", "particionado", "extraccion", "evaluacion", "calibracion"]
)
def test_operation_checks_are_read_only_and_blocked(tmp_path: Path, action: str) -> None:
    lab = make_lab(tmp_path)
    plan = prepare_design_fixture(lab)
    # Declarar permisos en un archivo no constituye autorización humana.
    plan["autorizacion_operativa"] = dict.fromkeys(plan["autorizacion_operativa"], True)
    (lab / "02_diseno/diseno.yaml").write_text(yaml.safe_dump(plan))
    assert command("preparar-diseno", "--laboratorio", str(lab)).returncode == 0
    before = {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}
    result = command("validar-diseno", "--laboratorio", str(lab), "--accion", action)
    assert result.returncode == 2
    assert "bloqueada" in result.stdout
    assert "D04" in result.stdout and "D10" in result.stdout and "D11" in result.stdout
    after = {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}
    assert before == after


def test_design_check_reloads_specification_instead_of_trusting_stale_json(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    prepare_design_fixture(lab)
    assert command("preparar-diseno", "--laboratorio", str(lab)).returncode == 0
    path = lab / "01_especificacion/especificacion.yaml"
    specification = yaml.safe_load(path.read_text())
    specification["version"] = "2-draft"
    path.write_text(yaml.safe_dump(specification))
    result = command("validar-diseno", "--laboratorio", str(lab), "--accion", "congelar")
    assert result.returncode == 2
    assert "Especificación modificada" in result.stderr
