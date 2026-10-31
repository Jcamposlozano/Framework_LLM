"""Crear un laboratorio vacío y consultar su control metodológico manual.

Herramienta de organización, independiente de modelos y métricas. Solo biblioteca estándar.
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "laboratorio"
STATES = {"pendiente", "en_curso", "bloqueado", "completado", "no_aplica"}


def create_legacy_lab(destination: Path) -> None:
    if destination.exists():
        raise ValueError(
            "La carpeta ya existe. Elige una nueva; no se sobrescribe ningún laboratorio."
        )
    if not TEMPLATE.is_dir():
        raise ValueError(
            "No se encuentra la plantilla. Ejecuta el script desde la copia fuente completa."
        )
    # Leer la plantilla antes de crear el destino; no contiene documentos de estudio.
    files = [
        (p.relative_to(TEMPLATE), p.read_bytes())
        for p in sorted(TEMPLATE.rglob("*"))
        if p.is_file()
    ]
    if not files:
        raise ValueError("La plantilla no contiene archivos.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    for relative, content in files:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(content)
    creation = {
        "tipo_registro": "creacion_de_estructura_no_experimento",
        "laboratorio_id": f"lab-{uuid4().hex}",
        "version_plantilla": "1.0",
        "fecha_creacion_utc": datetime.now(UTC).isoformat(),
        "etapas_ejecutadas_por_este_comando": [],
        "documentos_incluidos": 0,
        "anotaciones_incluidas": 0,
        "resultados_cientificos_incluidos": 0,
    }
    with (destination / "control" / "creacion.json").open("x", encoding="utf-8") as stream:
        json.dump(creation, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Laboratorio creado: {destination.resolve()}")
    print(f"Archivos preparados: {len(files) + 1}")
    print("7 etapas pendientes; 49 actividades pendientes. No se ejecutó ningún experimento.")
    print("Empieza por LEEME_PRIMERO.md y control/alcance.md.")


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Un archivo de control no tiene las columnas requeridas.")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Hay filas incompletas o columnas adicionales en un archivo de control.")
    return rows


def status_lab(laboratory: Path) -> bool:
    root = laboratory.resolve()
    mapping = json.loads((root / "control/mapa_etapas.json").read_text(encoding="utf-8"))
    expected = {item["id"] for item in mapping}
    stages = read_csv(
        root / "control/estado_etapas.csv",
        {"etapa", "estado", "ruta_evidencia", "justificacion", "resultado_obtenido"},
    )
    tasks = read_csv(
        root / "control/lista_chequeo.csv",
        {"id", "etapa", "estado", "evidencia_real", "observaciones"},
    )
    if len(stages) != 7 or {row["etapa"] for row in stages} != expected:
        raise ValueError("El control debe conservar exactamente las siete etapas sin duplicados.")
    if len({row["id"] for row in tasks}) != len(tasks):
        raise ValueError("Los identificadores de la lista de chequeo deben ser únicos.")
    if {row["etapa"] for row in tasks} != expected:
        raise ValueError("La lista de chequeo debe contener actividades de las siete etapas.")
    for row in stages + tasks:
        if row["estado"] not in STATES:
            raise ValueError(
                "Estado inválido: usa pendiente, en_curso, bloqueado, completado o no_aplica."
            )
    warnings: list[str] = []
    print("CONTROL METODOLÓGICO DECLARADO POR EL USUARIO")
    print("No detecta procesos en ejecución ni calcula métricas o validez científica.\n")
    for item in mapping:
        row = next(stage for stage in stages if stage["etapa"] == item["id"])
        group = [task for task in tasks if task["etapa"] == item["id"]]
        completed = sum(task["estado"] == "completado" for task in group)
        excluded = sum(task["estado"] == "no_aplica" for task in group)
        print(f"{item['id']} | {item['nombre']} | {row['estado']}")
        print(
            f"  Actividades: {completed}/{len(group)} completadas; "
            f"{excluded} no aplicables declaradas"
        )
        print(f"  Software actual: {item['soporte_software']}")
        print(f"  Producto esperado: {item['producto_esperado']}")
        result_summary = row["resultado_obtenido"].strip() or "sin resultado registrado"
        print(f"  Resultado registrado: {result_summary}")
        print(f"  Evidencia: {row['ruta_evidencia'].strip() or 'no registrada'}")
        if row["estado"] == "completado":
            if any(task["estado"] not in {"completado", "no_aplica"} for task in group):
                warnings.append(f"{item['id']}: etapa completada con actividades pendientes.")
            if not row["ruta_evidencia"].strip():
                warnings.append(f"{item['id']}: falta ruta de evidencia del resultado.")
        if row["estado"] == "no_aplica" and not row["justificacion"].strip():
            warnings.append(f"{item['id']}: no_aplica sin justificación.")
    for row in tasks:
        if row["estado"] == "no_aplica" and not row["observaciones"].strip():
            warnings.append(f"{row['id']}: no_aplica sin justificación en observaciones.")
        if row["estado"] == "completado" and not row["evidencia_real"].strip():
            warnings.append(f"{row['id']}: actividad completada sin evidencia_real.")
    for row, column, label in [
        *((row, "ruta_evidencia", row["etapa"]) for row in stages),
        *((row, "evidencia_real", row["id"]) for row in tasks),
    ]:
        reference = row[column].strip()
        if reference:
            path = (root / reference).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                warnings.append(
                    f"{label}: la evidencia debe apuntar a un archivo dentro del laboratorio."
                )
            elif path.stat().st_size == 0:
                warnings.append(f"{label}: la evidencia indicada está vacía.")
    print("\nLa existencia de archivos, encabezados o borradores no acredita una etapa completada.")
    for warning in warnings:
        print(f"REVISAR: {warning}")
    print("La suficiencia científica de la evidencia necesita revisión humana.")
    return not warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("crear", help="Preparar un laboratorio nuevo sin datos")
    create.add_argument("--destino", type=Path, required=True)
    create.add_argument("--formato", choices=["yaml-json", "legado"], default="yaml-json")
    prepare = subparsers.add_parser("preparar-especificacion", help="Generar JSON desde el YAML")
    prepare.add_argument("--laboratorio", type=Path, required=True)
    design = subparsers.add_parser(
        "preparar-diseno", help="Registrar el plan YAML sin calcular estadísticas"
    )
    design.add_argument("--laboratorio", type=Path, required=True)
    check = subparsers.add_parser(
        "validar-diseno", help="Comprobar bloqueos sin ejecutar el estudio"
    )
    check.add_argument("--laboratorio", type=Path, required=True)
    check.add_argument(
        "--accion",
        choices=["congelar", "muestreo", "particionado", "extraccion", "evaluacion", "calibracion"],
        required=True,
    )
    ingest = subparsers.add_parser(
        "importar-textos", help="Convertir tabla local a documentos JSON"
    )
    ingest.add_argument("--laboratorio", type=Path, required=True)
    ingest.add_argument("--archivo", type=Path, required=True)
    ingest.add_argument(
        "--reemplazar-con-respaldo",
        action="store_true",
        help="Respaldar corpus y correspondencia antes de reemplazar el corpus activo",
    )
    status = subparsers.add_parser("estado", help="Leer el tablero y la lista de chequeo manuales")
    status.add_argument("--laboratorio", type=Path, required=True)
    for name in (
        "preparar-estabilidad",
        "validar-estabilidad",
        "ejecutar-estabilidad",
        "informe-estabilidad",
    ):
        command = subparsers.add_parser(name, help="Piloto técnico de estabilidad A/V/B")
        command.add_argument("--laboratorio", type=Path, required=True)
        if name == "ejecutar-estabilidad":
            command.add_argument("--ejecucion", default="piloto-mock-v1")
            command.add_argument("--modo", choices=["mock", "real"], default="mock")
            command.add_argument("--activar-real", action="store_true")
            command.add_argument("--autorizacion-real", type=Path)
    for name in ("preparar-extractor", "demo-extractor", "ejecutar-extractor"):
        command = subparsers.add_parser(name, help="Extractor A independiente con trazabilidad")
        command.add_argument("--laboratorio", type=Path, required=True)
        command.add_argument("--version", default="v1")
        if name == "ejecutar-extractor":
            command.add_argument("--documento-id", required=True)
            command.add_argument("--ejecucion", required=True)
            command.add_argument("--modo", choices=["mock", "real"], default="mock")
            command.add_argument("--autorizar-real", action="store_true")
            command.add_argument("--gobierno", type=Path)
    for name, help_text in (
        ("preparar-verificacion", "Preparar fase 2 con el diccionario del laboratorio"),
        ("demo-verificacion", "Ejecutar una demostración sintética independiente del corpus"),
        ("registrar-extraccion-a", "Adaptar y preservar una extracción A de un documento"),
        ("ejecutar-verificacion", "Verificar un documento, comparar y reconciliar"),
        ("estado-verificacion", "Consultar artefactos y progreso técnico de fase 2"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--laboratorio", type=Path, required=True)
        command.add_argument("--version", default="v1")
        if name == "registrar-extraccion-a":
            command.add_argument("--documento-id", required=True)
            command.add_argument("--archivo", type=Path, required=True)
        if name in {"demo-verificacion", "ejecutar-verificacion"}:
            command.add_argument(
                "--ejecucion",
                default="demo-v1" if name == "demo-verificacion" else None,
                required=name == "ejecutar-verificacion",
            )
            command.add_argument(
                "--etapa", choices=["independent", "compare", "reconcile", "all"], default="all"
            )
            command.add_argument("--dry-run", action="store_true")
        if name == "ejecutar-verificacion":
            command.add_argument("--entrada", type=Path, required=True)
            command.add_argument("--modo", choices=["mock", "real"], default="mock")
            command.add_argument("--autorizar-real", action="store_true")
            command.add_argument("--gobierno", type=Path)
    args = parser.parse_args()
    try:
        if args.command in {
            "preparar-estabilidad",
            "validar-estabilidad",
            "ejecutar-estabilidad",
            "informe-estabilidad",
        }:
            from estabilidad_laboratorio import execute_stability, load_stability, prepare_stability

            from extracteval.application.stability_analysis import render_report

            if args.command == "preparar-estabilidad":
                print(prepare_stability(args.laboratorio))
            elif args.command == "validar-estabilidad":
                plan, _ = load_stability(args.laboratorio)
                print(
                    json.dumps(
                        {
                            "modo": plan.modo,
                            "documentos": plan.subconjunto.documentos_objetivo,
                            "repeticiones": plan.repeticiones.cantidad_por_documento,
                            "llamadas_generate_planificadas": plan.calls_required(),
                        }
                    )
                )
            elif args.command == "informe-estabilidad":
                results = json.loads(
                    (args.laboratorio / "03_estabilidad/resultados.json").read_bytes()
                )
                print(render_report(results))
            else:
                result = execute_stability(
                    args.laboratorio,
                    args.ejecucion,
                    mode=args.modo,
                    activate_real=args.activar_real,
                    authorization_path=args.autorizacion_real,
                )
                print(
                    json.dumps(
                        {
                            "modo": result["modo"],
                            "experiment_id": result["experiment_id"],
                            "repeticiones": len(result["ejecuciones"]),
                            "consumo": result["consumo"],
                        }
                    )
                )
            return
        if args.command in {"preparar-extractor", "demo-extractor", "ejecutar-extractor"}:
            from extraccion_laboratorio import (
                demo_extraction,
                execute_extraction,
                prepare_extraction,
            )

            if args.command == "preparar-extractor":
                prepare_extraction(args.laboratorio, args.version)
            elif args.command == "demo-extractor":
                demo_extraction(args.laboratorio, args.version)
            else:
                raise SystemExit(
                    execute_extraction(
                        args.laboratorio,
                        document_id=args.documento_id,
                        execution=args.ejecucion,
                        version=args.version,
                        mode=args.modo,
                        authorize_real=args.autorizar_real,
                        governance=args.gobierno,
                    )
                )
            return
        if args.command in {
            "preparar-verificacion",
            "demo-verificacion",
            "registrar-extraccion-a",
            "ejecutar-verificacion",
            "estado-verificacion",
        }:
            from verificacion_laboratorio import (
                execute_verification,
                prepare_verification,
                register_original,
                verification_status,
            )

            if args.command == "preparar-verificacion":
                prepare_verification(args.laboratorio, args.version)
            elif args.command == "estado-verificacion":
                verification_status(args.laboratorio)
            elif args.command == "registrar-extraccion-a":
                register_original(
                    args.laboratorio,
                    document_id=args.documento_id,
                    source=args.archivo,
                    version=args.version,
                )
            else:
                result = execute_verification(
                    args.laboratorio,
                    version=args.version,
                    execution=args.ejecucion,
                    stage=args.etapa,
                    dry_run=args.dry_run,
                    entry=args.entrada if args.command == "ejecutar-verificacion" else None,
                    mode=args.modo if args.command == "ejecutar-verificacion" else "mock",
                    authorize_real=args.command == "ejecutar-verificacion" and args.autorizar_real,
                    governance=args.gobierno if args.command == "ejecutar-verificacion" else None,
                )
                if result:
                    raise SystemExit(result)
        elif args.command == "crear" and args.formato == "legado":
            create_legacy_lab(args.destino)
        elif args.command == "estado" and not (args.laboratorio / "control/estado.json").exists():
            if not status_lab(args.laboratorio):
                raise SystemExit(1)
        else:
            from laboratorio_yaml_json import (
                check_design,
                create_simple,
                import_documents,
                prepare_design,
                prepare_specification,
                status_simple,
            )

            if args.command == "crear":
                create_simple(args.destino)
            elif args.command == "preparar-especificacion":
                prepare_specification(args.laboratorio)
            elif args.command == "preparar-diseno":
                prepare_design(args.laboratorio)
            elif args.command == "validar-diseno":
                check_design(args.laboratorio, args.accion)
            elif args.command == "importar-textos":
                import_documents(
                    args.laboratorio, args.archivo, replace_with_backup=args.reemplazar_con_respaldo
                )
            elif not status_simple(args.laboratorio):
                raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # No incluir contenido documental ni mensajes crudos de archivos externos.
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            parser.exit(2, f"No se pudo completar: {error}\n")
        parser.exit(
            2, "No se pudo leer o crear el laboratorio. Revisa rutas, permisos y formato.\n"
        )


if __name__ == "__main__":
    main()
