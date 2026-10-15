"""Pruebas sintéticas del organizador; no ejecutan etapas científicas."""

import csv
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/laboratorio.py"


def command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


def make_lab(tmp_path: Path) -> Path:
    lab = tmp_path / "laboratorio"
    result = command("crear", "--destino", str(lab))
    assert result.returncode == 0, result.stderr
    return lab


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def update(path: Path, row_id: str, column: str, value: str, key: str = "etapa") -> None:
    rows = read_rows(path)
    next(row for row in rows if row[key] == row_id)[column] = value
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_creates_no_data_or_fabricated_results(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    stages = read_rows(lab / "control/estado_etapas.csv")
    tasks = read_rows(lab / "control/lista_chequeo.csv")
    assert len(stages) == 7 and len(tasks) == 49
    assert all(row["estado"] == "pendiente" for row in stages + tasks)
    assert all(row["resultado_obtenido"] == "" for row in stages)
    for path in lab.rglob("*.jsonl"):
        assert path.read_bytes() == b""
    for path in (lab / "01_especificacion/prompts").glob("*.txt"):
        assert path.read_bytes() == b""
    for path in lab.rglob("*.csv"):
        if path.name not in {"estado_etapas.csv", "lista_chequeo.csv"}:
            assert read_rows(path) == [], path
    for path in lab.rglob("*.borrador.json"):
        assert json.loads(path.read_text())["estado_plantilla"] == "borrador_no_ejecutable"
    creation = json.loads((lab / "control/creacion.json").read_text())
    assert creation["etapas_ejecutadas_por_este_comando"] == []
    assert creation["resultados_cientificos_incluidos"] == 0


def test_refuses_to_overwrite_any_existing_destination(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    files = {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}
    second = command("crear", "--destino", str(lab))
    assert second.returncode == 2
    assert "no se sobrescribe" in second.stderr
    assert files == {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}
    empty = tmp_path / "empty"
    empty.mkdir()
    assert command("crear", "--destino", str(empty)).returncode == 2
    assert list(empty.iterdir()) == []


def test_status_is_read_only_and_does_not_infer_completion(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    update(lab / "control/estado_etapas.csv", "E1", "estado", "en_curso")
    # Tener un archivo completo no cambia ninguna tarea automáticamente.
    (lab / "01_especificacion/prompts/extractor_v1.txt").write_text("Prompt sintético")
    before = {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 0, result.stderr
    assert "en_curso" in result.stdout
    assert "0/8 completadas" in result.stdout
    assert "No detecta procesos" in result.stdout
    assert before == {p.relative_to(lab): p.read_bytes() for p in lab.rglob("*") if p.is_file()}


def test_warns_about_completion_without_evidence(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    update(lab / "control/estado_etapas.csv", "E1", "estado", "completado")
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 1
    assert "actividades pendientes" in result.stdout
    assert "falta ruta de evidencia" in result.stdout


def test_validates_state_names_and_na_justification(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    path = lab / "control/lista_chequeo.csv"
    update(path, "E1.01", "estado", "terminado", key="id")
    assert command("estado", "--laboratorio", str(lab)).returncode == 2
    update(path, "E1.01", "estado", "no_aplica", key="id")
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 1 and "sin justificación" in result.stdout
    update(path, "E1.01", "observaciones", "Exclusión de prueba; requiere revisión", key="id")
    assert command("estado", "--laboratorio", str(lab)).returncode == 0


def test_rejects_missing_empty_or_external_evidence(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    path = lab / "control/lista_chequeo.csv"
    update(path, "E1.01", "evidencia_real", "../externo.md", key="id")
    assert command("estado", "--laboratorio", str(lab)).returncode == 1
    update(path, "E1.01", "evidencia_real", "no_existe.md", key="id")
    assert command("estado", "--laboratorio", str(lab)).returncode == 1
    update(path, "E1.01", "evidencia_real", "01_especificacion/prompts/extractor_v1.txt", key="id")
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 1 and "está vacía" in result.stdout


def test_shows_recorded_result_without_changing_status(tmp_path: Path) -> None:
    lab = make_lab(tmp_path)
    ledger = lab / "control/estado_etapas.csv"
    update(ledger, "E1", "estado", "en_curso")
    update(ledger, "E1", "resultado_obtenido", "Borrador sintético pendiente de revisión")
    update(ledger, "E1", "ruta_evidencia", "01_especificacion/proposito.md")
    result = command("estado", "--laboratorio", str(lab))
    assert result.returncode == 0
    assert "Resultado registrado: Borrador sintético pendiente de revisión" in result.stdout
    assert "Evidencia: 01_especificacion/proposito.md" in result.stdout
    assert read_rows(ledger)[0]["estado"] == "en_curso"
