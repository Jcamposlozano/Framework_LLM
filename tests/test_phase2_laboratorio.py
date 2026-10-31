"""Lab integration uses an invented local corpus; no patient notes are fixtures."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from laboratorio_yaml_json import LabError, create_simple, prepare_specification, write_json  # noqa: E402
from verificacion_laboratorio import (  # noqa: E402
    execute_verification,
    prepare_verification,
    register_original,
    verification_status,
)

from extracteval.core.documents import Document  # noqa: E402
from extracteval.core.verification import VerificationInput  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lab(tmp_path):
    path = tmp_path / "synthetic-lab"
    create_simple(path)
    variables = {}
    dictionary = json.loads((ROOT / "configs/epoc/dictionary.v1.json").read_bytes())
    for variable in dictionary["variables"]:
        variables[variable["variable_id"]] = {
            "type": variable["data_type"],
            "definition": "Synthetic operational definition",
            "allowed_values": variable["categories"],
            "correctness_criteria": ["Pending expert approval."],
        }
    spec = {
        "dictionary_id": "synthetic-lab",
        "version": "draft.v1",
        "status": "pending",
        "principles": ["Only documented evidence."],
        "variables": variables,
        "consistency_checks": [
            {
                "id": "active",
                "if": {"estado_paciente": "exacerbacion_activa"},
                "then": {"exacerbacion_actual": "true"},
            }
        ],
    }
    (path / "01_especificacion/especificacion.yaml").write_text(yaml.safe_dump(spec))
    prepare_specification(path)
    document = Document(
        document_id="synthetic-document", text="Texto clínico inventado para prueba local."
    )
    write_json(path / "datos/documentos.json", [document.model_dump(mode="json")], private=True)
    return path


def test_lab_prepare_uses_its_dictionary_preserves_corpus_and_seven_stages(lab):
    corpus = (lab / "datos/documentos.json").read_bytes()
    state = (lab / "control/estado.json").read_bytes()
    prepare_verification(lab)
    root = lab / "configuraciones/verificacion/v1"
    executable = json.loads((root / "diccionario.json").read_bytes())
    assert executable["artifact"]["artifact_id"] == "synthetic-lab"
    assert len(executable["variables"]) == 6
    assert executable["clinically_approved"] is False
    assert len(executable["review_rules"]) == 1
    assert executable["review_rules"][0]["approved"] is False
    prepare_verification(lab)
    assert (lab / "datos/documentos.json").read_bytes() == corpus
    assert (lab / "control/estado.json").read_bytes() == state
    assert len(json.loads(state)["etapas"]) == 7


def test_lab_demo_each_stage_and_progress(lab):
    prepare_verification(lab)
    assert execute_verification(lab, stage="independent") == 0
    report = verification_status(lab)
    assert report["ejecuciones"][0]["lectura_independiente"] is True
    assert report["ejecuciones"][0]["comparacion"] is False
    assert execute_verification(lab, stage="compare") == 0
    assert execute_verification(lab, stage="reconcile") == 0
    report = verification_status(lab)
    row = report["ejecuciones"][0]
    assert row["integridad"] and row["reconciliacion"]
    assert row["discrepancias"] == 1 and row["revision_humana"] == 6
    assert report["metricas_exactitud_calculadas"] is False
    assert execute_verification(lab) == 0


def test_register_a_preserves_raw_bytes_auxiliary_and_null_semantics(lab, tmp_path):
    prepare_verification(lab)
    raw = {
        "estado_paciente": "estable",
        "exacerbacion_actual": False,
        "exacerbacion_previa": "indeterminado",
        "fecha_indice_evento": None,
        "precision_temporal": "indeterminada",
        "metodo_fecha": "no_determinable",
        "nivel_confianza": 0.8,
        "offset_estimado_dias": 7,
        "justificacion_clinica": "Texto inventado.",
        "semantic_states": {
            "fecha_indice_evento": "indeterminate",
            "exacerbacion_actual": "documented_absence",
        },
    }
    source = tmp_path / "a.json"
    source.write_text(json.dumps(raw, indent=4) + "\n")
    before = source.read_bytes()
    entry = register_original(lab, document_id="synthetic-document", source=source)
    inputs = VerificationInput.model_validate_json(entry.read_bytes())
    assert inputs.extraction_a.auxiliary["nivel_confianza"] == 0.8
    assert inputs.extraction_a.auxiliary["offset_estimado_dias"] == 7
    assert inputs.extraction_a.results[1].value.value == "false"
    assert inputs.extraction_a.semantic_states["fecha_indice_evento"] == "indeterminate"
    assert (entry.parent / "a-original.json").read_bytes() == before == source.read_bytes()
    assert inputs.extraction_a.source_sha256 == hashlib.sha256(before).hexdigest()
    from extracteval.core.hashing import content_hash
    from extracteval.core.results import ExtractionResult

    expected_schema_hash = content_hash(ExtractionResult.model_json_schema())
    assert all(
        result.trace.output_schema.sha256 == expected_schema_hash
        for result in inputs.extraction_a.results
    )
    import_config = json.loads((entry.parent / "configuracion_importacion.json").read_bytes())
    assert all(
        result.trace.config.sha256 == content_hash(import_config)
        for result in inputs.extraction_a.results
    )
    assert register_original(lab, document_id="synthetic-document", source=source) == entry


def test_lab_dryrun_no_results_and_no_real_demo(lab):
    prepare_verification(lab)
    assert execute_verification(lab, dry_run=True) == 0
    assert not (lab / "ejecuciones/fase2").exists()
    with pytest.raises(LabError):
        execute_verification(lab, mode="real")
    with pytest.raises(LabError):
        execute_verification(lab, execution="../escape")


def test_changed_spec_requires_new_version(lab):
    prepare_verification(lab)
    source = lab / "01_especificacion/especificacion.yaml"
    source.write_text(source.read_text() + "\n# changed\n")
    with pytest.raises(LabError):
        execute_verification(lab)
    with pytest.raises(LabError):
        prepare_verification(lab)
    prepare_specification(lab)
    with pytest.raises(LabError):
        prepare_verification(lab)
    prepare_verification(lab, "v2")
    assert execute_verification(lab, version="v2", execution="demo-v2") == 0


def test_lab_rejects_dictionary_detached_from_prepared_source(lab):
    from verificacion_laboratorio import ensure_current_source

    from extracteval.core.hashing import content_hash

    prepare_verification(lab)
    root = lab / "configuraciones/verificacion/v1"
    dictionary = json.loads((root / "diccionario.json").read_bytes())
    dictionary["artifact"]["version"] = "foreign-draft"
    dictionary["artifact"]["sha256"] = content_hash(
        {k: v for k, v in dictionary.items() if k != "artifact"}
    )
    (root / "foreign.json").write_text(json.dumps(dictionary))
    config = json.loads((root / "config.json").read_bytes())
    config["dictionary_path"] = "foreign.json"
    (root / "config.json").write_text(json.dumps(config))
    with pytest.raises(LabError, match="diccionario"):
        ensure_current_source(lab, "v1")


def test_lab_rejects_prompt_changed_under_existing_version(lab):
    from verificacion_laboratorio import ensure_current_source

    prepare_verification(lab)
    prompt = lab / "configuraciones/verificacion/v1/verificador.v1.txt"
    prompt.write_text(prompt.read_text() + "\n")
    with pytest.raises(LabError, match="prompt"):
        ensure_current_source(lab, "v1")


def test_technical_inventory_uses_actual_versions_and_file_hashes(lab):
    from verificacion_laboratorio import verification_technical_inventory

    prepare_verification(lab)
    before = (lab / "01_especificacion/especificacion.yaml").read_bytes()
    inventory = verification_technical_inventory(lab)
    root = lab / "configuraciones/verificacion/v1"
    assert inventory["modelo_configurado"] == "gpt-4.1-mini"
    assert (
        inventory["instrucciones"]["sha256"]
        == hashlib.sha256((root / "verificador.v1.txt").read_bytes()).hexdigest()
    )
    assert (
        inventory["politica"]["sha256"]
        == hashlib.sha256((root / "politica.json").read_bytes()).hexdigest()
    )
    assert inventory["api_consultada_por_inventario"] is False
    assert inventory["modelo_efectivo_api"] is None
    assert (lab / "01_especificacion/especificacion.yaml").read_bytes() == before
