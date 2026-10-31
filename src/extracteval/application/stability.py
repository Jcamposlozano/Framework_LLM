"""Repeated execution of existing A/V/B cases with durable experimental identities."""

import fcntl
import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from extracteval.adapters.models.verification_mock import MockExtractorModel, MockVerifierModel
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.configuration import GovernanceAuthorization
from extracteval.application.extraction import ExtractorSettings, extract_document
from extracteval.application.pipeline import run_verification
from extracteval.application.stability_analysis import compare_repetitions, observations
from extracteval.application.verification import IndependentVerifier
from extracteval.core.base import ArtifactRef, Contract, Digest, Identifier
from extracteval.core.documents import Document
from extracteval.core.exceptions import ProviderFailure
from extracteval.core.hashing import content_hash
from extracteval.core.models import ModelCapabilities, ModelIdentity, ModelRequest, ModelResponse
from extracteval.core.ports import ModelPort
from extracteval.core.specification import OperationalDictionary
from extracteval.core.verification import (
    IndependentVerification,
    ReconciledExtraction,
    ReconciliationPolicy,
    VerificationConfig,
    VerificationInput,
    VerificationPayload,
)

Modality = Literal["completa", "A_fija"]


class FileReference(Contract):
    ruta: str
    sha256: Digest
    version: str


class Subset(Contract):
    tipo: Literal["sintetico", "local"]
    documentos_objetivo: int = Field(gt=0, strict=True)
    documentos_ids: tuple[Identifier, ...]
    archivo: FileReference
    criterio_seleccion: str
    uso: Literal["desarrollo_tecnico"] = "desarrollo_tecnico"


class ModalitySpec(Contract):
    id: Modality
    regenerar_A: bool
    regenerar_V: Literal[True] = True
    reconciliar_B: Literal[True] = True

    @model_validator(mode="after")
    def semantics(self) -> Self:
        if self.regenerar_A != (self.id == "completa"):
            raise ValueError("Modality and A regeneration disagree")
        return self


class Repetitions(Contract):
    cantidad_por_documento: int = Field(gt=1, strict=True)
    modalidades: tuple[ModalitySpec, ...] = Field(min_length=1)
    ejecuciones_independientes: Literal[True] = True
    reanudacion_no_cuenta_como_repeticion: Literal[True] = True

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({m.id for m in self.modalidades}) != len(self.modalidades):
            raise ValueError("Duplicate modalities")
        return self


class FixedConfiguration(Contract):
    extractor: FileReference
    verificador: FileReference
    archivos: dict[str, FileReference]
    diccionario: ArtifactRef
    contratos: dict[str, Any]
    modelos_solicitados: dict[str, str]
    reconciliacion_version: str
    verificar_hashes: Literal[True] = True


class Budget(Contract):
    max_llamadas: int = Field(gt=0, strict=True)
    reintentos_automaticos: Literal[0] = 0
    limite_gasto_estimado: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    moneda: str | None = None
    precio_entrada_por_millon: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    precio_salida_por_millon: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fuente_precios: ArtifactRef | None = None
    max_tokens_entrada_por_llamada: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def pricing(self) -> Self:
        if self.limite_gasto_estimado is not None and any(
            v is None
            for v in (
                self.moneda,
                self.precio_entrada_por_millon,
                self.precio_salida_por_millon,
                self.fuente_precios,
                self.max_tokens_entrada_por_llamada,
            )
        ):
            raise ValueError(
                "A spending estimate needs explicit versioned pricing and token limits"
            )
        return self


class StabilityPlan(Contract):
    estudio_id: Identifier
    version: Identifier
    modo: Literal["mock", "real"] = "mock"
    finalidad: Literal["piloto_tecnico_no_confirmatorio"] = "piloto_tecnico_no_confirmatorio"
    subconjunto: Subset
    repeticiones: Repetitions
    configuracion_fija: FixedConfiguration
    perturbaciones: tuple[dict[str, Any], ...] = ()
    condiciones_constantes: tuple[str, ...]
    metricas_planificadas: tuple[str, ...]
    incertidumbre: dict[str, Any]
    presupuesto: Budget
    ejecucion_real_habilitada: bool = False

    @model_validator(mode="after")
    def boundaries(self) -> Self:
        ids = self.subconjunto.documentos_ids
        if len(ids) != len(set(ids)) or len(ids) != self.subconjunto.documentos_objetivo:
            raise ValueError("Explicit unique document selection required")
        if self.perturbaciones:
            raise ValueError("Perturbation execution is disabled pending approval")
        if self.modo == "mock" and self.subconjunto.tipo != "sintetico":
            raise ValueError("Mock pilots require an explicitly synthetic corpus")
        if self.modo == "mock" and self.ejecucion_real_habilitada:
            raise ValueError("A mock plan cannot enable real calls")
        if self.incertidumbre.get("intervalos_confianza") != "no_calcular_en_piloto":
            raise ValueError("Confirmatory intervals are not supported in this pilot")
        return self

    def calls_required(self) -> int:
        n, r = self.subconjunto.documentos_objetivo, self.repeticiones.cantidad_por_documento
        return n * sum(
            2 * r if m.id == "completa" else 1 + r for m in self.repeticiones.modalidades
        )


class ScriptedResponse(Contract):
    payload: VerificationPayload | None = None
    error: Literal["timeout", "unavailable", "invalid_response", "internal_error"] | None = None

    @model_validator(mode="after")
    def one(self) -> Self:
        if (self.payload is None) == (self.error is None):
            raise ValueError("Supply one scripted payload or technical failure")
        return self


class SyntheticCase(Contract):
    document: Document
    a: tuple[ScriptedResponse, ...]
    v: tuple[ScriptedResponse, ...]


class VariantRecord(Contract):
    """Provenance for future externally approved variants; no transformations run here."""

    original_document_id: Identifier
    variant_id: Identifier
    transformation_type: Identifier
    transformation_version: Identifier
    original_hash: Digest
    transformed_hash: Digest
    transformation_record: dict[str, Any]
    approval: ArtifactRef


class RealAuthorization(Contract):
    plan_hash: Digest
    documents_hash: Digest
    reference: Identifier
    authorized: Literal[True]
    governance: tuple[GovernanceAuthorization, ...]


class ExperimentIndex(Contract):
    experiment_id: Identifier
    input_hash: Digest
    mode: Literal["mock", "real"]
    plan: StabilityPlan


class CallIntent(Contract):
    slot: str
    role: Literal["A", "V"]
    request_hash: Digest
    mode: Literal["mock", "real"]


class CallReceipt(Contract):
    request_hash: Digest
    response_hash: Digest


class BudgetedModel:
    """Durably consumes a call slot before generation. Never retries uncertain calls."""

    def __init__(
        self,
        model: ModelPort,
        ledger: Path,
        slot: str,
        role: Literal["A", "V"],
        plan: StabilityPlan,
    ) -> None:
        self.model, self.ledger, self.slot, self.role, self.plan = model, ledger, slot, role, plan

    @property
    def identity(self) -> ModelIdentity:
        return self.model.identity

    @property
    def capabilities(self) -> ModelCapabilities:
        return self.model.capabilities

    def generate(self, request: ModelRequest) -> ModelResponse:
        store = JSONRunStore(self.ledger / content_hash(self.slot)[:32])
        bound = self.plan.presupuesto.max_tokens_entrada_por_llamada
        # Conservative local byte-based admission bound, not a provider token count.
        estimated_upper = len(request.content.encode()) + len(request.instructions.encode())
        estimated_upper += len(str(request.response_schema).encode()) + 4096
        if bound is not None and estimated_upper > bound:
            raise ValueError("Input exceeds the configured conservative token admission bound")
        with (self.ledger / ".reservation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if store.exists("intent"):
                intent = store.get("intent", CallIntent)
                if intent.request_hash != content_hash(request):
                    raise ValueError("Consumed call slot has a different request")
                if store.exists("receipt"):
                    receipt = store.get("receipt", CallReceipt)
                    response = store.get("response", ModelResponse)
                    if receipt.response_hash != content_hash(response):
                        raise ValueError("Saved call response integrity mismatch")
                    return response
                raise ProviderFailure("unavailable", errors=("unavailable",))
            if len(list(self.ledger.glob("*/intent.json"))) >= self.plan.presupuesto.max_llamadas:
                raise ValueError("Call budget exhausted")
            store.put(
                "intent",
                CallIntent(
                    slot=self.slot,
                    role=self.role,
                    request_hash=content_hash(request),
                    mode=self.plan.modo,
                ),
            )
        response = self.model.generate(request)
        store.put("response", response)
        store.put(
            "receipt",
            CallReceipt(request_hash=content_hash(request), response_hash=content_hash(response)),
        )
        return response


def authorize_real(
    plan: StabilityPlan,
    documents: list[Document],
    authorization: RealAuthorization | None,
    activate: bool,
) -> None:
    if not activate or not plan.ejecucion_real_habilitada or authorization is None:
        raise ValueError("Real execution requires separate explicit activation and authorization")
    if authorization.plan_hash != content_hash(
        plan
    ) or authorization.documents_hash != content_hash(
        [d.model_dump(mode="json") for d in documents]
    ):
        raise ValueError("Real authorization does not match plan/documents")
    if len(authorization.governance) != len(documents):
        raise ValueError("Document-bound governance required for every selected document")
    for document, governance in zip(documents, authorization.governance, strict=True):
        governance.validate_authorization(content_hash(document))


def run_stability(
    plan: StabilityPlan,
    documents: list[Document],
    dictionary: OperationalDictionary,
    settings: ExtractorSettings,
    prompt: str,
    verifier_config: VerificationConfig,
    policy: ReconciliationPolicy,
    root: Path,
    factory: Callable[[Literal["A", "V"], Document, int], ModelPort],
    *,
    script_hash: Digest | None = None,
    activate_real: bool = False,
    authorization: RealAuthorization | None = None,
    script_responses: dict[str, SyntheticCase] | None = None,
) -> dict[str, Any]:
    """The factory receives document and repetition only; V cannot see A through it."""
    if [d.document_id for d in documents] != list(plan.subconjunto.documentos_ids):
        raise ValueError("Document selection/order does not match plan")
    if (
        settings.dictionary != dictionary.artifact
        or dictionary.artifact != plan.configuracion_fija.diccionario
    ):
        raise ValueError("A and V must use the same bound dictionary")
    if plan.calls_required() > plan.presupuesto.max_llamadas:
        raise ValueError("Planned experiment exceeds call budget")
    if plan.modo == "real":
        authorize_real(plan, documents, authorization, activate_real)
    elif activate_real or authorization is not None:
        raise ValueError("A mock plan cannot activate real execution")
    budget = plan.presupuesto
    if budget.limite_gasto_estimado is not None:
        assert budget.max_tokens_entrada_por_llamada is not None
        assert budget.precio_entrada_por_millon is not None
        assert budget.precio_salida_por_millon is not None
        output_limit = max(
            settings.max_output_tokens, verifier_config.parameters.max_output_tokens or 0
        )
        upper = (
            budget.max_llamadas
            * (
                budget.max_tokens_entrada_por_llamada * budget.precio_entrada_por_millon
                + output_limit * budget.precio_salida_por_millon
            )
            / 1_000_000
        )
        if upper > budget.limite_gasto_estimado:
            raise ValueError("Conservative planned spend estimate exceeds configured limit")
    fingerprint = content_hash(
        {
            "plan": plan.model_dump(mode="json"),
            "documents": [d.model_dump(mode="json") for d in documents],
            "settings": settings.model_dump(mode="json"),
            "prompt": prompt,
            "verifier": verifier_config.model_dump(mode="json"),
            "dictionary": dictionary.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "script_hash": script_hash,
            "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "analysis_implementation": hashlib.sha256(
                Path(__file__).with_name("stability_analysis.py").read_bytes()
            ).hexdigest(),
        }
    )
    index_store = JSONRunStore(root)
    if index_store.exists("index"):
        index = index_store.get("index", ExperimentIndex)
        if index.input_hash != fingerprint:
            raise ValueError("Stability resume configuration/integrity mismatch")
    else:
        index = ExperimentIndex(
            experiment_id="stability-" + uuid4().hex,
            input_hash=fingerprint,
            mode=plan.modo,
            plan=plan,
        )
        index_store.put("index", index)
    ledger = root / "calls"

    def model_for(
        role: Literal["A", "V"], document: Document, repetition: int, slot: str
    ) -> ModelPort:
        model = factory(role, document, repetition)
        if plan.modo == "mock" and type(model) not in (MockExtractorModel, MockVerifierModel):
            raise ValueError("Mock experiments accept only built-in offline scripted adapters")
        return BudgetedModel(model, ledger, slot, role, plan)

    rows: list[dict[str, Any]] = []
    for modality in plan.repeticiones.modalidades:
        for number, document in enumerate(documents):
            for repetition in range(plan.repeticiones.cantidad_por_documento):
                slot = f"{modality.id}/d{number:04d}/r{repetition:04d}"
                repeat_root = root / "repetitions" / slot
                a_slot = slot if modality.id == "completa" else f"fixed/d{number:04d}"
                a_store = JSONRunStore(root / "extractions" / a_slot)
                a_index = repetition if modality.id == "completa" else 0
                fixture = (
                    script_responses[document.document_id].a[a_index] if script_responses else None
                )
                a_hash = content_hash(fixture) if fixture else None
                if a_store.exists("request") and not a_store.exists("manifest"):
                    rows.append(
                        {
                            "repetition_id": index.experiment_id + "/" + slot,
                            "document_id": document.document_id,
                            "modalidad": modality.id,
                            "repeticion": repetition + 1,
                            "estado": "interrupted",
                            "observaciones": None,
                            "modo": plan.modo,
                        }
                    )
                    continue
                execution = extract_document(
                    document,
                    dictionary,
                    settings,
                    prompt,
                    None
                    if a_store.exists("manifest")
                    else model_for("A", document, a_index, a_slot + "/A"),
                    a_store,
                    mode=plan.modo,
                    mock_payload_hash=a_hash,
                )
                a = execution.extraction_a
                before_hash = content_hash(a)
                v_store = JSONRunStore(repeat_root / "vb")
                fixture_v = (
                    script_responses[document.document_id].v[repetition]
                    if script_responses
                    else None
                )
                manifest = run_verification(
                    VerificationInput(document=document, extraction_a=a),
                    dictionary,
                    policy,
                    verifier_config,
                    v_store,
                    None
                    if v_store.exists("verification")
                    else IndependentVerifier(model_for("V", document, repetition, slot + "/V")),
                    mode=plan.modo,
                    mock_payload_hash=content_hash(fixture_v) if fixture_v else None,
                )
                b = v_store.get("extraction_b", ReconciledExtraction)
                v = v_store.get("verification", IndependentVerification)
                if content_hash(a) != before_hash or b.base_extraction_hash != before_hash:
                    raise ValueError("A was changed during stability execution")
                row = {
                    "repetition_id": index.experiment_id + "/" + slot,
                    "document_id": document.document_id,
                    "document_hash": content_hash(document),
                    "modalidad": modality.id,
                    "repeticion": repetition + 1,
                    "modo": plan.modo,
                    "estado": "technical_failure"
                    if execution.audit.error or v.audit.error
                    else "completed",
                    "errores": {
                        "A": execution.audit.error.code if execution.audit.error else None,
                        "V": v.audit.error.code if v.audit.error else None,
                    },
                    "base_extraction_id": a.base_extraction_id,
                    "base_extraction_hash": before_hash,
                    "configuracion_A": execution.effective_configuration.model_dump(mode="json"),
                    "configuracion_V": verifier_config.model_dump(mode="json", exclude={"prompt"}),
                    "modelo_efectivo_V": v.audit.response.model.model_dump(mode="json")
                    if v.audit.response
                    else None,
                    "politica": {
                        "version": policy.version,
                        "sha256_canonico": content_hash(policy),
                    },
                    "a_artifacts": str(a_store.root.relative_to(root)),
                    "vb_artifacts": str(v_store.root.relative_to(root)),
                    "verification_id": v.verification_id,
                    "run_id": manifest.run_id,
                    "observaciones": observations(a, b),
                }
                rows.append(row)
    analysis = compare_repetitions(
        [r for r in rows if r["observaciones"] is not None],
        [v.variable_id for v in dictionary.variables],
    )
    intents = list(ledger.glob("*/intent.json"))
    responses = [
        ModelResponse.model_validate_json(p.read_bytes()) for p in ledger.glob("*/response.json")
    ]
    return {
        "estado": "resultados_tecnicos_sinteticos"
        if plan.modo == "mock"
        else "resultados_descriptivos_reales",
        "modo": plan.modo,
        "experiment_id": index.experiment_id,
        "input_hash": fingerprint,
        "documentos": len(documents),
        "ejecuciones": rows,
        **analysis,
        "configuraciones": plan.configuracion_fija.model_dump(mode="json"),
        "consumo": {
            "intentos_generate": len(intents),
            "llamadas_externas": 0 if plan.modo == "mock" else len(intents),
            "respuestas_registradas": len(responses),
            "input_tokens": sum(r.usage.input_tokens or 0 for r in responses if r.usage),
            "output_tokens": sum(r.usage.output_tokens or 0 for r in responses if r.usage),
            "tokens_reportados": any(r.usage is not None for r in responses),
            "gasto_real_verificado": None,
        },
        "conclusiones": None,
        "clinicamente_validado": False,
        "nota": "Resultados descriptivos; estabilidad no implica corrección clínica.",
    }
