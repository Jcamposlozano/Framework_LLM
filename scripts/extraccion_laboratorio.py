"""Prepare A independently and exercise the existing A/V/B pipeline on synthetic data."""

import hashlib
import json
import os
from pathlib import Path

from laboratorio_yaml_json import LabError, read_json
from verificacion_laboratorio import (
    REPOSITORY,
    config_root,
    ensure_current_source,
    immutable_json,
    register_original,
)

from extracteval.adapters.models.verification_mock import MockExtractorModel, MockVerifierModel
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import load_configuration
from extracteval.application.extraction import ExtractorSettings, extract_document, load_extractor
from extracteval.application.pipeline import run_verification
from extracteval.application.verification import IndependentVerifier
from extracteval.core.documents import Document, DocumentSection, Evidence
from extracteval.core.hashing import content_hash
from extracteval.core.specification import CategoryValue, OperationalDictionary
from extracteval.core.verification import (
    VariableVerification,
    VerificationInput,
    VerificationPayload,
)
from extracteval.extraction_cli import main as extract_cli


def extraction_root(laboratory: Path, version: str = "v1") -> Path:
    config_root(laboratory, version)  # Existing version/path validation.
    return laboratory / "configuraciones/extraccion" / version


def synthetic_extraction(dictionary: OperationalDictionary) -> tuple[Document, VerificationPayload]:
    """Explicit scripted fixture; not an algorithm deriving clinical categories."""
    text = (
        "ANÁLISIS: EPOC estable, sin exacerbación actual. "
        "Antecedentes inciertos. Fecha de inicio desconocida."
    )
    document = Document(
        document_id="demo-extractor-epoc-001",
        text=text,
        sections=(DocumentSection(name="analisis", start=0, end=len(text)),),
    )
    values = {
        "estado_paciente": "estable",
        "exacerbacion_actual": "false",
        "exacerbacion_previa": "indeterminado",
        "fecha_indice_evento": None,
        "precision_temporal": "indeterminada",
        "metodo_fecha": "no_determinable",
    }
    quote = "EPOC estable, sin exacerbación actual."
    evidence = Evidence(
        document_id=document.document_id,
        quote=quote,
        section="analisis",
        start=text.index(quote),
        end=text.index(quote) + len(quote),
    )
    variables = []
    for definition in dictionary.variables:
        key, value = definition.variable_id, values[definition.variable_id]
        certain = key in {"estado_paciente", "exacerbacion_actual"}
        proposal = VariableVerification(
            variable_id=key,
            proposed_value=CategoryValue(value=value) if value else None,
            semantic_state="value" if certain else "indeterminate",
            evidence=(evidence,) if certain else (),
            evidence_type="literal" if certain else "none",
            uncertainty_flags=() if certain else ("insufficient_documentation",),
            requires_human_review=not certain,
        )
        if proposal.proposed_value:
            definition.validate_value(proposal.proposed_value)
        variables.append(proposal)
    return document, VerificationPayload(variables=tuple(variables))


def prepare_extraction(laboratory: Path, version: str = "v1") -> Path:
    verifier_root = ensure_current_source(laboratory, version)
    _, dictionary, _, _ = load_configuration(verifier_root / "config.json", {}, "mock")
    root = extraction_root(laboratory, version)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "config.json").exists():
        existing = ExtractorSettings.model_validate_json((root / "config.json").read_bytes())
        if existing.prompt_version != "clinical-extractor.v2":
            raise LabError(
                "El prompt A está versionado; crea otro laboratorio o versión explícita."
            )
    prompt = (REPOSITORY / "prompts/clinical-extractor.v2.txt").read_bytes()
    prompt_path = root / "extractor_v2.txt"
    if prompt_path.exists() and prompt_path.read_bytes() != prompt:
        raise LabError("El prompt A cambió; prepara otra versión.")
    if not prompt_path.exists():
        with prompt_path.open("xb") as stream:
            stream.write(prompt)
    document, payload = synthetic_extraction(dictionary)
    immutable_json(root / "demo-documento.json", document.model_dump(mode="json"))
    immutable_json(root / "demo-respuesta.json", payload.model_dump(mode="json"))
    settings = ExtractorSettings(
        version="lab-extractor-" + version,
        dictionary_path=os.path.relpath(verifier_root / "diccionario.json", root),
        dictionary=dictionary.artifact,
        prompt_path="extractor_v2.txt",
        prompt_version="clinical-extractor.v2",
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        mock_payload_path="demo-respuesta.json",
    )
    immutable_json(root / "config.json", settings.model_dump(mode="json"))
    print("Extractor A preparado; ningún documento del corpus ha sido procesado.")
    return root / "config.json"


def execute_extraction(
    laboratory: Path,
    *,
    document_id: str,
    execution: str,
    version: str = "v1",
    mode: str = "mock",
    authorize_real: bool = False,
    governance: Path | None = None,
) -> int:
    ensure_current_source(laboratory, version)
    config_root(laboratory, execution)
    root = extraction_root(laboratory, version)
    records = read_json(laboratory / "datos/documentos.json")
    matches = [r for r in records if r.get("document_id") == document_id]
    if len(matches) != 1:
        raise LabError("Selecciona un único documento por su identificador.")
    document = Document.model_validate(matches[0])
    destination = laboratory / "ejecuciones/extraccion" / execution
    immutable_json(destination / "document.json", document.model_dump(mode="json"))
    args = [
        "--config",
        str(root / "config.json"),
        "--input",
        str(destination / "document.json"),
        "--output",
        str(destination / "a"),
        "--mode",
        mode,
    ]
    if authorize_real:
        args.append("--authorize-real")
    if governance:
        args.extend(["--governance", str(governance)])
    result = extract_cli(args)
    if (destination / "a/manifest.json").exists():
        register_original(
            laboratory,
            document_id=document_id,
            source=destination / "a/extraction_a.json",
            version=version,
        )
    return result


def demo_extraction(laboratory: Path, version: str = "v1") -> dict[str, object]:
    config_path = prepare_extraction(laboratory, version)
    settings, dictionary, prompt = load_extractor(config_path, {})
    document, payload_a = synthetic_extraction(dictionary)
    # Separately declared V fixture. No access to the generated snapshot or its audit.
    _, payload_v = synthetic_extraction(dictionary)
    root = laboratory / "ejecuciones/fase2" / ("demo-extractor-" + version)
    model_a = MockExtractorModel([payload_a])
    store_a = JSONRunStore(root / "a")
    a = extract_document(
        document,
        dictionary,
        settings,
        prompt,
        model_a,
        store_a,
        mock_payload_hash=content_hash(payload_a),
    )
    entry = register_original(
        laboratory,
        document_id=document.document_id,
        source=root / "a/extraction_a.json",
        version=version,
        document=document,
    )
    inputs = VerificationInput.model_validate_json(entry.read_bytes())
    _, _, policy, config_v = load_configuration(
        config_root(laboratory, version) / "config.json", {}, "mock"
    )
    model_v = MockVerifierModel([payload_v])
    before = (root / "a/extraction_a.json").read_bytes()
    manifest = run_verification(
        inputs,
        dictionary,
        policy,
        config_v,
        JSONRunStore(root / "b"),
        IndependentVerifier(model_v),
        mock_payload_hash=content_hash(payload_v),
    )
    if before != (root / "a/extraction_a.json").read_bytes():
        raise LabError("A cambió durante la verificación.")
    report: dict[str, object] = {
        "mode": "mock",
        "provider_calls": 0,
        "corpus_processed": False,
        "base_extraction_id": a.extraction_a.base_extraction_id,
        "base_extraction_hash": content_hash(a.extraction_a),
        "run_id": manifest.run_id,
        "variables": len(a.extraction_a.results),
        "a_immutable": True,
        "clinically_validated": False,
        "a_mock_calls_this_invocation": len(model_a.requests),
        "v_mock_calls_this_invocation": len(model_v.requests),
    }
    immutable_json(
        root / "demostracion.json",
        {k: v for k, v in report.items() if not k.endswith("this_invocation")},
    )
    print(json.dumps(report, ensure_ascii=False))
    return report
