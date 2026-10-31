"""Organización YAML/JSON e importación local; no ejecuta extracción ni análisis científico."""

import csv
import hashlib
import hmac
import io
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from diseno_validaciones import ACTIONS, DesignError, assess_design, require_operation
from pydantic import ValidationError

from extracteval.core.base import ArtifactRef
from extracteval.core.documents import Document
from extracteval.core.specification import (
    InformationPolicy,
    OperationalDictionary,
    VariableDefinition,
)


class LabError(ValueError):
    """Error con mensaje seguro, sin narrativas ni identificadores de origen."""


def load_yaml(path: Path) -> dict[str, Any]:
    # Dependencia opcional de herramientas, nunca importada por el núcleo científico.
    try:
        import yaml
    except ImportError:
        raise LabError("Instala el extra lab: python -m pip install '.[lab]'.") from None

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader: Any, node: Any) -> dict[str, Any]:
        pairs = loader.construct_pairs(node)
        result: dict[str, Any] = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise LabError("El YAML debe usar claves de texto únicas.")
            result[key] = value
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
        if not isinstance(value, dict):
            raise LabError("El YAML debe contener un objeto en su raíz.")
        # Rechazar valores que no puedan representarse sin ambigüedad en JSON.
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except LabError:
        raise
    except (yaml.YAMLError, TypeError, ValueError):
        raise LabError("YAML inválido: revisa estructura, tipos y fechas entre comillas.") from None
    return value


def json_data(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (ValueError, UnicodeError):
        raise LabError("JSON inválido; no se mostró su contenido.") from None


def write_json(
    path: Path, value: object, *, exclusive: bool = False, private: bool = False
) -> None:
    content = json_data(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600 if private else 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    else:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if private:
        path.chmod(0o600)


def create_simple(destination: Path) -> None:
    template = Path(__file__).resolve().parents[1] / "templates/laboratorio_yaml_json"
    if destination.exists():
        raise LabError("La carpeta ya existe; no se sobrescribe el laboratorio.")
    files = [(p.relative_to(template), p.read_bytes()) for p in template.rglob("*") if p.is_file()]
    if not files or any(relative.suffix not in {".yaml", ".json"} for relative, _ in files):
        raise LabError("La plantilla YAML/JSON está incompleta o contiene otro formato.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    for relative, content in files:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(content)
    write_json(
        destination / "control/creacion.json",
        {
            "version_plantilla": "2.0",
            "laboratorio_id": f"lab-{uuid4().hex}",
            "fecha_creacion_utc": datetime.now(UTC).isoformat(),
            "tipo": "creacion_estructura_no_experimento",
            "etapas_ejecutadas": [],
        },
        exclusive=True,
    )
    print(f"Laboratorio YAML/JSON creado: {destination.resolve()}")
    print("Siete etapas pendientes. Edita 01_especificacion/especificacion.yaml.")


def prepare_specification(laboratory: Path) -> None:
    source = laboratory / "01_especificacion/especificacion.yaml"
    raw = load_yaml(source)
    if not isinstance(raw.get("variables"), dict) or not raw["variables"]:
        raise LabError(
            "Completa las variables de especificacion.yaml antes de preparar el contrato."
        )
    missing = "PENDIENTE DE APROBACIÓN: definir esta política antes de la evaluación confirmatoria."
    definitions = []
    try:
        for identifier, variable in raw["variables"].items():
            if not isinstance(variable, dict):
                raise LabError("Cada variable debe contener una definición estructurada.")
            rules = list(raw.get("principles", [])) + list(variable.get("interpretation_rules", []))
            categories = variable.get("categories", {})
            if isinstance(categories, dict):
                rules.extend(f"Categoría {key}: {value}" for key, value in categories.items())
            if variable.get("null_policy"):
                rules.append(variable["null_policy"])
            policies = variable.get("information_policy", {})
            data_type = variable["type"]
            definitions.append(
                VariableDefinition(
                    variable_id=identifier,
                    version=variable.get("version", raw["version"]),
                    data_type="date" if data_type == "date_or_null" else data_type,
                    categories=tuple(variable.get("allowed_values", [])),
                    operational_definition=variable["definition"],
                    interpretation_rules=tuple(rules),
                    correctness_criteria=tuple(variable.get("correctness_criteria", [missing])),
                    information_policy=InformationPolicy(
                        absent=policies.get("absent", variable.get("null_policy", missing)),
                        indeterminate=policies.get("indeterminate", missing),
                        not_applicable=policies.get("not_applicable", missing),
                    ),
                    normalization_rules=tuple(variable.get("normalization_rules", [])),
                )
            )
        dictionary = OperationalDictionary(
            artifact=ArtifactRef(
                artifact_id=raw["dictionary_id"],
                version=raw["version"],
                sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            ),
            variables=tuple(definitions),
        )
    except (ValidationError, KeyError, TypeError, ValueError):
        raise LabError(
            "Especificación incompatible: revisa nombres, tipos, categorías y versiones."
        ) from None
    snapshot = laboratory / ".historial/especificacion" / f"{dictionary.artifact.sha256}.yaml"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    content = source.read_bytes()
    if snapshot.exists():
        if snapshot.read_bytes() != content:
            raise LabError("La instantánea histórica no coincide; no se reemplaza.")
    else:
        descriptor = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
    output = laboratory / "01_especificacion/especificacion.json"
    if output.exists():
        previous = read_json(output)
        if previous.get("diccionario_framework") is not None:
            backup = laboratory / ".historial/especificacion" / f"{uuid4().hex}.json"
            write_json(backup, previous, exclusive=True, private=True)
    write_json(
        output,
        {
            "formato": "especificacion_compilada_v2",
            "estado_declarado": raw.get("status", "borrador"),
            "revision_clinica_verificada": False,
            "reglas_ejecutadas": False,
            "fuente": {
                "ruta": "01_especificacion/especificacion.yaml",
                "sha256": dictionary.artifact.sha256,
            },
            "especificacion_completa": raw,
            "diccionario_framework": dictionary.model_dump(mode="json"),
            "nota": "Validez estructural; no acredita aprobación ni ejecuta extracción.",
        },
    )
    print(f"Especificación preparada: {len(definitions)} variables. Reglas no ejecutadas.")


def assess_design_files(laboratory: Path) -> dict[str, Any]:
    """Leer fuentes actuales sin escribir ni ejecutar operaciones del estudio."""
    plan = load_yaml(laboratory / "02_diseno/diseno.yaml")
    specification = read_json(laboratory / "01_especificacion/especificacion.json")
    source = laboratory / "01_especificacion/especificacion.yaml"
    if specification.get("especificacion_completa") != load_yaml(source):
        raise LabError("Especificación modificada: prepara su JSON antes de validar el diseño.")
    try:
        dictionary = OperationalDictionary.model_validate(specification["diccionario_framework"])
    except ValidationError:
        raise LabError("Diccionario compilado inválido; prepara la especificación.") from None
    imported = read_json(laboratory / "datos/informe_importacion.json")
    context = {
        "variable_ids": [v.variable_id for v in dictionary.variables],
        "categories": {
            v.variable_id: list(v.categories) for v in dictionary.variables if v.categories
        },
        "date_variables": [v.variable_id for v in dictionary.variables if v.data_type == "date"],
        "patient_grouping_available": imported.get("agrupacion_por_paciente_disponible") is True,
        "document_date_available": imported.get("fecha_documental_disponible") is True,
        "clinical_criteria_approved": specification.get("revision_clinica_verificada") is True,
        # Esta interfaz está autorizada exclusivamente para parametrizar. Cambiar el YAML
        # no habilita autorización humana ni crea ejecutores científicos inexistentes.
        "authorized_actions": dict.fromkeys(ACTIONS, False),
        "available_actions": dict.fromkeys(ACTIONS, False),
    }
    if plan["estimando_primario"]["variables"] != context["variable_ids"]:
        raise LabError("Las variables del diseño deben corresponder al diccionario preparado.")
    if plan["corpus_disponible"]["documentos_importados"] != imported["documentos_importados"]:
        raise LabError("La cantidad cargada debe coincidir con el informe de importación.")
    try:
        return assess_design(plan, context)
    except DesignError as error:
        raise LabError(str(error)) from None


def check_design(laboratory: Path, action: str) -> None:
    assessment = assess_design_files(laboratory)
    print(f"Decisiones pendientes: {len(assessment['decisiones_pendientes'])}.")
    for item in assessment["decisiones_pendientes"]:
        print(f"{item['id']}: {item['motivo']}")
    print(f"{action}: bloqueada; sin autorización operativa ni ejecutor en esta fase.")
    require_operation(assessment, action)


def prepare_design(laboratory: Path) -> None:
    """Serializar un plan preespecificado; no calcular muestra, particiones o métricas."""
    source = laboratory / "02_diseno/diseno.yaml"
    plan = load_yaml(source)
    try:
        reference = ArtifactRef(
            artifact_id=plan["diseno_id"],
            version=plan["version"],
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        specification = read_json(laboratory / "01_especificacion/especificacion.json")
        dictionary = OperationalDictionary.model_validate(specification["diccionario_framework"])
        variable_ids = [variable.variable_id for variable in dictionary.variables]
        if plan["estimando_primario"]["variables"] != variable_ids:
            raise LabError("Las variables del diseño deben corresponder al diccionario preparado.")
        conditions = plan["configuraciones_comparadas"]
        for field in [
            "mismos_documentos",
            "misma_referencia_independiente",
            "misma_definicion_pares_evaluables",
        ]:
            if conditions[field] is not True:
                raise LabError(
                    "La comparación principal requiere pares y referencia comunes para A/B."
                )
        level = plan["metodo_ic95"]["nivel_confianza"]
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 < level < 1:
            raise LabError("El nivel de confianza debe estar entre cero y uno.")
        imported = read_json(laboratory / "datos/informe_importacion.json")
        if plan["corpus_disponible"]["documentos_importados"] != imported["documentos_importados"]:
            raise LabError("La cantidad cargada debe coincidir con el informe de importación.")
    except LabError:
        raise
    except (KeyError, TypeError, ValidationError):
        raise LabError(
            "Completa el diseño y prepara primero la especificación; revisa sus campos."
        ) from None

    assessment = assess_design_files(laboratory)
    missing = assessment["decisiones_pendientes"]
    if plan["congelacion"].get("estado") == "congelado":
        require_operation(assessment, "congelar")

    output = laboratory / "02_diseno/resultados.json"
    previous = read_json(output)
    arrays = ["muestra", "particiones", "pesos", "controles_fuga"]
    if not isinstance(previous, dict) or any(
        not isinstance(previous.get(key, []), list) for key in arrays
    ):
        raise LabError("El JSON del diseño debe conservar sus listas de registros.")
    previous_hash = previous.get("fuente_plan", {}).get("sha256")
    if any(previous.get(key) for key in arrays):
        if previous_hash != reference.sha256:
            raise LabError(
                "Ya existen registros del diseño; no se sustituye su plan por uno distinto."
            )
        print(
            "El plan coincide con los registros existentes; no se modificó el JSON de resultados."
        )
        return
    history = laboratory / ".historial/diseno"
    history.mkdir(parents=True, exist_ok=True)
    snapshot = history / f"{reference.sha256}.yaml"
    if not snapshot.exists():
        with snapshot.open("xb") as stream:
            stream.write(source.read_bytes())
    elif snapshot.read_bytes() != source.read_bytes():
        raise LabError("La instantánea del plan no coincide; no se reemplaza.")
    write_json(history / f"{uuid4().hex}.json", previous, exclusive=True, private=True)
    generated = dict(previous)
    generated.update(
        {
            "estado": "plan_parametrizado_sin_ejecucion",
            "nota": "Plan registrado; sin muestreo, particionado ni cálculo estadístico.",
            "fuente_plan": reference.model_dump(mode="json"),
            "ruta_plan": "02_diseno/diseno.yaml",
            "plan_estadistico": plan,
            "especificacion_utilizada": {
                "ruta": "01_especificacion/especificacion.json",
                "diccionario": dictionary.artifact.model_dump(mode="json"),
                "sha256_json": hashlib.sha256(
                    (laboratory / "01_especificacion/especificacion.json").read_bytes()
                ).hexdigest(),
            },
            "evidencia_disponible": {
                "documentos_importados": imported["documentos_importados"],
                "agrupacion_por_paciente_disponible": imported.get(
                    "agrupacion_por_paciente_disponible"
                ),
                "fecha_documental_disponible": imported.get("fecha_documental_disponible"),
                "rol_del_corpus_confirmado": bool(
                    plan["corpus_disponible"].get("rol_en_el_estudio")
                ),
            },
            "decisiones_pendientes": missing,
            "validacion_protocolo": assessment,
            "aprobacion_metodologica_verificada": False,
            "muestreo_ejecutado": False,
            "particiones_asignadas_por_este_comando": False,
            "metricas_calculadas": False,
        }
    )
    for key in arrays:
        generated.setdefault(key, [])
    write_json(output, generated)
    print(
        f"Diseño preparado con {len(missing)} decisiones pendientes; no se calcularon resultados."
    )


def parse_tsv(path: Path, id_column: str, text_column: str) -> tuple[list[tuple[str, str]], str]:
    content = path.read_bytes()
    try:
        text = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        header = next(reader)
        if len(header) != len(set(header)) or id_column not in header or text_column not in header:
            raise LabError("Faltan columnas o hay nombres duplicados; revisa importacion.yaml.")
        id_index, text_index = header.index(id_column), header.index(text_column)
        records = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(header) or not row[id_index].strip() or not row[text_index].strip():
                raise LabError(
                    "Registro incompleto o columnas inconsistentes; revisa el archivo de origen."
                )
            records.append((row[id_index], row[text_index]))
        if not records:
            raise LabError("El archivo no contiene registros documentales.")
    except (UnicodeError, csv.Error, StopIteration):
        raise LabError(
            "No se pudo leer la tabla UTF-8 tabulada; revisa comillas y encabezados."
        ) from None
    return records, hashlib.sha256(content).hexdigest()


def import_documents(laboratory: Path, source: Path, *, replace_with_backup: bool = False) -> None:
    from importacion_tabular import SourceRecord, TableImportError, parse_xlsx

    settings = load_yaml(laboratory / "datos/importacion.yaml")
    source_format = settings.get("formato_entrada")
    if source_format not in {"tsv", "xlsx"}:
        raise LabError("Declara formato_entrada: tsv o xlsx en importacion.yaml.")
    if settings.get("campo_entidad") is not None:
        raise LabError("No hay mapeo validado de entidad; ingreso no se tratará como paciente.")
    date_column = settings.get("campo_fecha")
    if date_column and (
        source_format != "xlsx" or settings.get("significado_fecha") != "fecha_atencion"
    ):
        raise LabError("El mapeo de fecha requiere XLSX y significado_fecha: fecha_atencion.")
    output = laboratory / "datos/documentos.json"
    report_path = laboratory / "datos/informe_importacion.json"
    map_path = laboratory / ".privado/correspondencia_origen.json"
    existing = read_json(output) if output.exists() else []
    previous_report = read_json(report_path) if report_path.exists() else {}
    prior_import = (
        existing != []
        or map_path.exists()
        or (previous_report.get("documentos_importados") or 0) > 0
    )
    if prior_import and not replace_with_backup:
        raise LabError(
            "Ya hay documentos. Usa --reemplazar-con-respaldo para cambiar el corpus activo."
        )
    extra: dict[str, Any] = {}
    if source_format == "xlsx":
        try:
            records, digest, extra = parse_xlsx(
                source,
                settings["columna_identificador"],
                settings["columna_texto"],
                sheet=settings.get("hoja_entrada"),
                date_column=date_column,
                date_format=settings.get("formato_fecha_texto", "%d/%m/%Y"),
            )
        except TableImportError as error:
            raise LabError(str(error)) from None
    else:
        rows, digest = parse_tsv(
            source, settings["columna_identificador"], settings["columna_texto"]
        )
        records = [
            SourceRecord(identifier, text, None, index + 1)
            for index, (identifier, text) in enumerate(rows, 1)
        ]
    private = laboratory / ".privado"
    key_path = private / "clave_pseudonimos.json"
    key = (
        bytes.fromhex(read_json(key_path)["clave_hex"])
        if key_path.exists()
        else secrets.token_bytes(32)
    )
    documents = []
    correspondence = []
    for index, record in enumerate(records, 1):
        pseudonym = hmac.new(key, record.source_id.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        record_key = f"{digest}:{index}:{record.source_id}"
        doc_id = "doc-" + hmac.new(key, record_key.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        try:
            document = Document(
                document_id=doc_id,
                entity_id=None,
                text=record.text,
                document_date=record.document_date,
                provenance={
                    "source_sha256": digest,
                    "source_record_number": index,
                    "source_row_number": record.row_number,
                    "source_record_id": "origen-" + pseudonym,
                    "source_record_kind": settings.get("tipo_identificador", "no_definido"),
                    "patient_grouping_available": False,
                    "source_sheet": extra.get("hoja"),
                    "document_date_meaning": "fecha_atencion" if date_column else None,
                    "date_inferred_from_text": False,
                },
            )
        except ValidationError:
            raise LabError("Un documento no cumple el contrato; no se mostró el texto.") from None
        documents.append(document.model_dump(mode="json"))
        correspondence.append({"document_id": doc_id, "identificador_origen": record.source_id})
    # All source records have been validated before replacing any active data.
    map_path = private / "correspondencia_origen.json"
    backup = None
    previous = {
        path: path.read_bytes() for path in (output, report_path, map_path) if path.exists()
    }
    if prior_import:
        backup = laboratory / ".historial/importaciones" / uuid4().hex
        backup.mkdir(parents=True, mode=0o700)
        backup.chmod(0o700)
        for original, data in previous.items():
            target = backup / original.name
            target.write_bytes(data)
            target.chmod(0o600)
        (backup / "importacion.yaml").write_bytes(
            (laboratory / "datos/importacion.yaml").read_bytes()
        )
        (backup / "importacion.yaml").chmod(0o600)
    private.mkdir(mode=0o700, exist_ok=True)
    private.chmod(0o700)
    if not key_path.exists():
        write_json(
            key_path,
            {"algoritmo": "HMAC-SHA256", "clave_hex": key.hex()},
            exclusive=True,
            private=True,
        )
    dated = sum(record.document_date is not None for record in records)
    report = {
        "estado": "importado_sin_ejecutar_modelos",
        "documentos_importados": len(documents),
        "formato_entrada": source_format,
        "source_sha256": digest,
        "campos_origen": [settings["columna_identificador"], settings["columna_texto"]]
        + ([date_column] if date_column else []),
        "identificadores_sustituidos_por_pseudonimos": True,
        "narrativa_anonimizada": False,
        "saltos_de_linea_conservados": True,
        "fecha_documental_disponible": dated > 0,
        "documentos_con_fecha": dated,
        "documentos_sin_fecha": len(documents) - dated,
        "significado_fecha": "fecha_atencion" if date_column else None,
        "fecha_inicio_exacerbacion_inferida": False,
        "agrupacion_por_paciente_disponible": False,
        "extraccion_ejecutada": False,
        "respaldo_anterior": str(backup.relative_to(laboratory)) if backup else None,
        "corpus_anterior_disponible": output in previous,
        "documentos_previos_reportados": previous_report.get("documentos_importados", 0),
        "fecha_utc": datetime.now(UTC).isoformat(),
        **extra,
    }
    try:
        write_json(map_path, {"source_sha256": digest, "registros": correspondence}, private=True)
        write_json(output, documents, private=True)
        write_json(report_path, report, private=True)
    except OSError:
        for path in (map_path, output, report_path):
            if path in previous:
                temporary = path.with_name("." + path.name + ".restore-" + uuid4().hex)
                temporary.write_bytes(previous[path])
                temporary.chmod(0o600)
                os.replace(temporary, path)
            else:
                path.unlink(missing_ok=True)
        raise
    print(f"Importación local terminada: {len(documents)} documentos. No se ejecutó ningún modelo.")
    print(
        f"Fechas de atención disponibles: {dated}. "
        "No se infirió inicio de exacerbación ni paciente."
    )
    if backup:
        print(
            f"Carga anterior: archivos disponibles respaldados en {backup.relative_to(laboratory)}"
        )
    print("Identificadores sustituidos; narrativas conservadas, sin anonimización automática.")


def status_simple(laboratory: Path) -> bool:
    status = read_json(laboratory / "control/estado.json")
    stages = status["etapas"]
    if len(stages) != 7 or {stage["id"] for stage in stages} != {f"E{i}" for i in range(1, 8)}:
        raise LabError("El tablero debe contener las siete etapas sin duplicados.")
    valid_states = {"pendiente", "en_curso", "bloqueado", "completado", "no_aplica"}
    issues = []
    print("CONTROL MANUAL: no ejecuta etapas ni detecta procesos activos.")
    for stage in stages:
        if stage["estado"] not in valid_states:
            raise LabError("Estado desconocido en el tablero.")
        tasks = stage["lista_chequeo"]
        if any(task["estado"] not in valid_states for task in tasks):
            raise LabError("Estado desconocido en la lista de chequeo.")
        completed = sum(task["estado"] == "completado" for task in tasks)
        print(
            f"{stage['id']} | {stage['nombre']} | {stage['estado']} | "
            f"{completed}/{len(tasks)} actividades"
        )
        print(f"  Producto: {stage['producto_esperado']}")
        print(f"  Resultado: {stage.get('resultado_obtenido') or 'sin resultado registrado'}")
        print(f"  Software: {stage['soporte_software']}")
        if stage["estado"] == "completado" and any(
            task["estado"] not in {"completado", "no_aplica"} for task in tasks
        ):
            issues.append(f"{stage['id']}: hay actividades pendientes.")
        for task in tasks:
            if task["estado"] == "no_aplica" and not task.get("observaciones"):
                issues.append(f"{task['id']}: exclusión sin justificar.")
            if task["estado"] == "completado" and not task.get("evidencia_real"):
                issues.append(f"{task['id']}: falta evidencia.")
        if stage["estado"] == "no_aplica" and not stage.get("justificacion"):
            issues.append(f"{stage['id']}: exclusión sin justificar.")
        if stage["estado"] == "completado":
            if not stage.get("ruta_evidencia"):
                issues.append(f"{stage['id']}: falta ruta de evidencia del resultado.")
            if not stage.get("resultado_obtenido"):
                issues.append(f"{stage['id']}: falta resultado registrado.")
        for reference in [
            stage.get("ruta_evidencia"),
            *(task.get("evidencia_real") for task in tasks),
        ]:
            if reference:
                path = (laboratory / reference).resolve()
                if not path.is_relative_to(laboratory.resolve()) or not path.is_file():
                    issues.append(f"{stage['id']}: ruta de evidencia inválida.")
    for issue in issues:
        print(f"REVISAR: {issue}")
    print("Archivos preparados no equivalen a etapas científicas completadas.")
    return not issues
