"""Offline stability integration and independently calculated denominators."""

import copy
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from estabilidad_laboratorio import execute_stability, load_stability, prepare_stability
from extraccion_laboratorio import prepare_extraction
from laboratorio_yaml_json import LabError, create_simple, prepare_specification
from verificacion_laboratorio import prepare_verification

from extracteval.application.stability import Budget, StabilityPlan, VariantRecord, authorize_real
from extracteval.application.stability_analysis import WARNING, compare_repetitions, render_report

ROOT = Path(__file__).resolve().parents[1]


def make_lab(path):
    create_simple(path)
    dictionary = json.loads((ROOT / "configs/epoc/dictionary.v1.json").read_bytes())
    spec = {
        "dictionary_id": "synthetic-stability",
        "version": "draft.v1",
        "status": "pending",
        "variables": {
            v["variable_id"]: {
                "type": v["data_type"],
                "definition": v["operational_definition"],
                "allowed_values": v["categories"],
                "information_policy": v["information_policy"],
                "correctness_criteria": v["correctness_criteria"],
            }
            for v in dictionary["variables"]
        },
    }
    (path / "01_especificacion/especificacion.yaml").write_text(yaml.safe_dump(spec))
    prepare_specification(path)
    prepare_verification(path)
    prepare_extraction(path)
    prepare_stability(path)
    return path


@pytest.fixture
def lab(tmp_path):
    path = make_lab(tmp_path / "lab")
    file = path / "03_estabilidad/estabilidad.yaml"
    plan = yaml.safe_load(file.read_text())
    plan["subconjunto"]["documentos_objetivo"] = 2
    plan["subconjunto"]["documentos_ids"] = plan["subconjunto"]["documentos_ids"][:2]
    fixture = path / plan["subconjunto"]["archivo"]["ruta"]
    fixture.write_text(json.dumps(json.loads(fixture.read_bytes())[:2]))
    plan["subconjunto"]["archivo"]["sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
    plan["repeticiones"]["cantidad_por_documento"] = 3
    file.write_text(yaml.safe_dump(plan))
    return path


@pytest.fixture(scope="module")
def full_experiment(tmp_path_factory):
    original = socket.socket.connect

    def blocked(*args, **kwargs):
        raise AssertionError("No provider connectivity allowed")

    socket.socket.connect = blocked
    try:
        path = make_lab(tmp_path_factory.mktemp("stability-full") / "lab")
        result = execute_stability(path)
    finally:
        socket.socket.connect = original
    return path, result


def test_both_modalities_and_provenance(full_experiment):
    _, result = full_experiment
    assert len(result["ejecuciones"]) == 100
    assert len({r["repetition_id"] for r in result["ejecuciones"]}) == 100
    assert result["consumo"]["intentos_generate"] == 160
    assert result["consumo"]["llamadas_externas"] == 0
    assert result["consumo"]["respuestas_registradas"] == 157
    assert sum(r["estado"] == "technical_failure" for r in result["ejecuciones"]) == 3
    assert len(result["concordancia"]) == 2 and len(result["perfiles"]) == 240


def test_fixed_A_and_full_A(full_experiment):
    _, result = full_experiment
    for doc in {r["document_id"] for r in result["ejecuciones"]}:
        fixed = [
            r
            for r in result["ejecuciones"]
            if r["document_id"] == doc and r["modalidad"] == "A_fija"
        ]
        full = [
            r
            for r in result["ejecuciones"]
            if r["document_id"] == doc and r["modalidad"] == "completa"
        ]
        assert len({r["base_extraction_id"] for r in fixed}) == 1
        assert len({r["base_extraction_hash"] for r in fixed}) == 1
        assert len({r["base_extraction_id"] for r in full}) == 5
    summary = next(c for c in result["concordancia"] if c["modalidad"] == "A_fija")
    assert all(v["por_diseno"] for v in summary["por_variable"]["A"].values())


def test_A_byte_hashes_and_B_trace(full_experiment):
    lab, result = full_experiment
    root = lab / "ejecuciones/estabilidad/piloto-mock-v1"
    for row in result["ejecuciones"]:
        raw = (root / row["a_artifacts"] / "extraction_a.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["base_extraction_hash"]
        b = json.loads((root / row["vb_artifacts"] / "extraction_b.json").read_bytes())
        assert b["base_extraction_hash"] == row["base_extraction_hash"]
        if any(v["error"] for v in row["observaciones"]["A"].values()):
            assert all(
                v["error"] == "timeout" and v["state"] is None
                for v in row["observaciones"]["A"].values()
            )


def test_json_report_dates_and_no_clinical_claims(full_experiment):
    lab, result = full_experiment
    assert json.loads((lab / "03_estabilidad/resultados.json").read_bytes()) == result
    report = (lab / "03_estabilidad/informe.md").read_text()
    assert WARNING in report and "A_fija es constante por diseño" in report
    assert "Denominadores" in report
    profiles = [
        p
        for p in result["perfiles"]
        if p["document_id"] == "synthetic-stability-003"
        and p["modalidad"] == "completa"
        and p["variable_id"] == "fecha_indice_evento"
    ]
    assert all(p["rango_fechas_dias"] == 2 and p["fechas_distintas"] == 2 for p in profiles)
    assert result["conclusiones"] is None and result["clinicamente_validado"] is False
    assert render_report(result) == report


def test_resume_without_model_calls(full_experiment, monkeypatch):
    lab, first = full_experiment

    def forbidden(*args, **kwargs):
        raise AssertionError("No new call on resume")

    monkeypatch.setattr(
        "extracteval.adapters.models.verification_mock.MockExtractorModel.generate", forbidden
    )
    monkeypatch.setattr(
        "extracteval.adapters.models.verification_mock.MockVerifierModel.generate", forbidden
    )
    assert execute_stability(lab) == first


def test_independence_V(lab, monkeypatch):
    from extracteval.adapters.models.verification_mock import MockVerifierModel
    from extracteval.application import stability

    original_extract = stability.extract_document

    def marker(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        result.extraction_a.auxiliary["marker"] = "A_ONLY_SECRET_MARKER"
        return result

    monkeypatch.setattr(stability, "extract_document", marker)
    original_generate = MockVerifierModel.generate
    seen = []

    def spy(self, request):
        if self.identity.model_id == "mock-verifier":
            seen.append(request)
            assert "A_ONLY_SECRET_MARKER" not in request.content + request.instructions
        return original_generate(self, request)

    monkeypatch.setattr(MockVerifierModel, "generate", spy)
    assert len(execute_stability(lab)["ejecuciones"]) == 12
    assert len(seen) == 12


def test_interrupted_between_A_V_resumes_without_duplicates(lab, monkeypatch):
    from extracteval.application import stability

    original = stability.run_verification
    count = 0

    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("simulated interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(stability, "run_verification", interrupted)
    with pytest.raises(RuntimeError):
        execute_stability(lab)
    monkeypatch.setattr(stability, "run_verification", original)
    result = execute_stability(lab)
    assert len(result["ejecuciones"]) == 12
    assert result["consumo"]["intentos_generate"] == 20
    assert len({r["repetition_id"] for r in result["ejecuciones"]}) == 12


def test_file_hash_validation(lab):
    path = lab / "03_estabilidad/estabilidad.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["configuracion_fija"]["extractor"]["sha256"] = "0" * 64
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(LabError):
        load_stability(lab)


def test_artifact_integrity_on_resume(lab):
    result = execute_stability(lab)
    artifact = (
        lab
        / "ejecuciones/estabilidad/piloto-mock-v1"
        / result["ejecuciones"][0]["a_artifacts"]
        / "extraction_a.json"
    )
    artifact.write_text("{}")
    with pytest.raises(LabError, match="Integridad"):
        execute_stability(lab)


@pytest.mark.parametrize(
    "damage", ["duplicates", "perturbations", "mode", "intervals", "modality", "count"]
)
def test_invalid_plan(lab, damage):
    raw = yaml.safe_load((lab / "03_estabilidad/estabilidad.yaml").read_text())
    if damage == "duplicates":
        raw["subconjunto"]["documentos_ids"][1] = raw["subconjunto"]["documentos_ids"][0]
    elif damage == "perturbations":
        raw["perturbaciones"] = [{"tipo": "unapproved"}]
    elif damage == "mode":
        raw["ejecucion_real_habilitada"] = True
    elif damage == "intervals":
        raw["incertidumbre"]["intervalos_confianza"] = "confirmatory"
    elif damage == "modality":
        raw["repeticiones"]["modalidades"][0]["regenerar_A"] = False
    else:
        raw["repeticiones"]["cantidad_por_documento"] = 1
    with pytest.raises(ValueError):
        StabilityPlan.model_validate(raw)


def test_real_cannot_be_activated_by_mock_or_credentials(lab, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "NEVER_USE_THIS_VALUE")
    with pytest.raises(LabError):
        execute_stability(lab, mode="real", activate_real=True)
    with pytest.raises(LabError):
        execute_stability(lab, activate_real=True)
    plan, cases = load_stability(lab)
    with pytest.raises(ValueError):
        authorize_real(plan, [c.document for c in cases], None, False)
    assert not (lab / "ejecuciones/estabilidad").exists()


def test_budgets(lab):
    path = lab / "03_estabilidad/estabilidad.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["presupuesto"]["max_llamadas"] = 1
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="call budget"):
        execute_stability(lab)
    with pytest.raises(ValueError):
        Budget(max_llamadas=20, limite_gasto_estimado=1)


def outcome(value=None, state="indeterminate", error=None):
    return {
        "value": value,
        "state": state,
        "error": error,
        "evidence_available": False,
        "decision": "HUMAN_REVIEW",
    }


def row(rep, a, b=None):
    return {
        "document_id": "doc",
        "modalidad": "completa",
        "repeticion": rep,
        "observaciones": {
            "A": {"fecha_indice_evento": a},
            "B": {"fecha_indice_evento": b if b is not None else copy.deepcopy(a)},
        },
    }


def test_known_date_pairs():
    values = [
        outcome({"kind": "date", "value": d}, "value")
        for d in ("2024-01-01", "2024-01-01", "2024-01-03")
    ]
    result = compare_repetitions([row(i, v) for i, v in enumerate(values)], ["fecha_indice_evento"])
    m = result["concordancia"][0]["por_variable"]["A"]["fecha_indice_evento"]
    assert m["acuerdo_exacto"] == {"numerador": 1, "denominador": 3, "proporcion": 1 / 3}
    assert m["acuerdo_fechas_validas"]["proporcion"] == 1 / 3
    assert result["perfiles"][0]["rango_fechas_dias"] == 2
    assert result["perfiles"][0]["fechas_distintas"] == 2


def test_null_states_and_errors_are_distinct():
    values = [
        outcome(state="indeterminate"),
        outcome(state="abstain"),
        outcome(state="no_response"),
        outcome(state=None, error="timeout"),
        outcome(state=None, error="timeout"),
    ]
    result = compare_repetitions([row(i, v) for i, v in enumerate(values)], ["fecha_indice_evento"])
    m = result["concordancia"][0]["por_variable"]["A"]["fecha_indice_evento"]
    assert m["acuerdo_exacto"]["denominador"] == 1 and m["acuerdo_exacto"]["numerador"] == 0
    assert m["acuerdo_operativo_incluye_fallos"]["numerador"] == 1
    assert m["fallo_tecnico"]["proporcion"] == 2 / 5 and m["abstencion"]["proporcion"] == 1 / 5


def test_all_errors_do_not_inflate_agreement():
    results = compare_repetitions(
        [row(i, outcome(state=None, error="timeout")) for i in range(3)], ["fecha_indice_evento"]
    )
    m = results["concordancia"][0]["por_variable"]["A"]["fecha_indice_evento"]
    assert m["acuerdo_exacto"]["proporcion"] is None
    assert m["acuerdo_operativo_incluye_fallos"]["proporcion"] == 1


def test_variant_provenance_requires_approval():
    with pytest.raises(ValueError):
        VariantRecord(
            original_document_id="doc",
            variant_id="v",
            transformation_type="format",
            transformation_version="v1",
            original_hash="0" * 64,
            transformed_hash="1" * 64,
            transformation_record={},
        )


def test_scientific_design_unchanged(lab):
    path = lab / "02_diseno/diseno.yaml"
    before = path.read_bytes()
    execute_stability(lab)
    assert path.read_bytes() == before


def test_category_distribution_and_complete_record_denominator():
    values = [
        outcome({"kind": "categorical", "value": v}, "value")
        for v in ("estable", "estable", "sintomatico")
    ]
    rows = [row(i, v) for i, v in enumerate(values)]
    # The generic comparator does not require a particular clinical category list.
    result = compare_repetitions(rows, ["fecha_indice_evento"])
    summary = result["concordancia"][0]
    metrics = summary["por_variable"]["A"]["fecha_indice_evento"]
    assert metrics["distribucion_categorias"] == {"estable": 2, "sintomatico": 1}
    assert metrics["denominador_categorias"] == 3
    assert summary["registro_completo"]["A"]["acuerdo_registro_completo"]["proporcion"] == 1 / 3


def test_paired_contrast_uses_identical_pairs_not_equal_counts():
    valid = outcome({"kind": "date", "value": "2024-01-01"}, "value")
    error = outcome(state=None, error="timeout")
    rows = [row(0, valid, error), row(1, valid, valid), row(2, error, valid)]
    result = compare_repetitions(rows, ["fecha_indice_evento"])["concordancia"][0]
    assert result["por_variable"]["A"]["fecha_indice_evento"]["acuerdo_exacto"]["denominador"] == 1
    assert result["por_variable"]["B"]["fecha_indice_evento"]["acuerdo_exacto"]["denominador"] == 1
    assert result["contraste_pareado"]["fecha_indice_evento"]["A"]["denominador"] == 0
    assert result["diferencia_descriptiva_B_menos_A"]["fecha_indice_evento"] is None


def test_mock_execution_never_constructs_HTTP_transport(lab, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No HTTP transport may be created by the mock runner")

    monkeypatch.setattr(
        "extracteval.adapters.models.openai.OpenAIHTTPTransport.__init__", forbidden
    )
    monkeypatch.setenv("OPENAI_API_KEY", "UNUSED_TEST_MARKER")
    result = execute_stability(lab)
    assert result["consumo"]["llamadas_externas"] == 0


def test_saved_V_response_recovered_without_second_generation(lab, monkeypatch):
    from extracteval.application.verification import IndependentVerifier

    original = IndependentVerifier.verify_independently
    once = True

    def interrupted(self, *args, **kwargs):
        nonlocal once
        value = original(self, *args, **kwargs)
        if once:
            once = False
            raise RuntimeError("crash after model response before V persistence")
        return value

    monkeypatch.setattr(IndependentVerifier, "verify_independently", interrupted)
    with pytest.raises(RuntimeError):
        execute_stability(lab)
    monkeypatch.setattr(IndependentVerifier, "verify_independently", original)
    result = execute_stability(lab)
    assert result["consumo"]["intentos_generate"] == 20
    assert all(r["estado"] == "completed" for r in result["ejecuciones"])


def test_actual_real_plan_rejected_without_authorization(lab, monkeypatch):
    path = lab / "03_estabilidad/estabilidad.yaml"
    raw = yaml.safe_load(path.read_text())
    # Use a separate explicit plan and document-only source for the future real path.
    fixture = lab / raw["subconjunto"]["archivo"]["ruta"]
    cases = json.loads(fixture.read_bytes())
    fixture.write_text(json.dumps([c["document"] for c in cases]))
    raw["subconjunto"]["archivo"]["sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
    raw["modo"] = "real"
    raw["subconjunto"]["tipo"] = "local"
    raw["ejecucion_real_habilitada"] = True
    path.write_text(yaml.safe_dump(raw))

    def forbidden(*args, **kwargs):
        raise AssertionError("No provider constructed before authorization")

    monkeypatch.setattr(
        "extracteval.adapters.models.openai.OpenAIHTTPTransport.__init__", forbidden
    )
    with pytest.raises(LabError):
        execute_stability(lab)
    with pytest.raises(LabError):
        execute_stability(lab, mode="real")
    assert not (lab / "ejecuciones/estabilidad").exists()
