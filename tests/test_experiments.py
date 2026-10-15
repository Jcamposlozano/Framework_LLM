from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from extracteval.adapters.models.mock import ConstantModel, ScriptedModel
from extracteval.core.experiments import (
    ConfigRef,
    ExperimentConfig,
    ModelBinding,
    ModelRunRecord,
    RunManifest,
)
from extracteval.core.models import ModelCapabilities, ModelParameters


def manifest(config, **changes):
    data = dict(
        execution_id="internal-run",
        config=ConfigRef.from_config(config),
        package_version="0.1.0",
        started_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    data.update(changes)
    return RunManifest(**data)


def test_config_hash_is_stable_and_version_sensitive(config):
    restored = ExperimentConfig.model_validate_json(config.model_dump_json())
    assert restored.fingerprint() == config.fingerprint()
    data = config.model_dump()
    data["version"] = "2"
    assert ExperimentConfig.model_validate(data).fingerprint() != config.fingerprint()
    data = dict(reversed(config.model_dump().items()))
    assert ExperimentConfig.model_validate(data).fingerprint() == config.fingerprint()


def test_manifest_roundtrip_and_config_tamper_detection(config):
    run = manifest(config)
    run.validate_against(config)
    assert RunManifest.model_validate_json(run.model_dump_json()) == run
    data = config.model_dump()
    data["version"] = "2"
    with pytest.raises(ValueError, match="configuration"):
        run.validate_against(ExperimentConfig.model_validate(data))
    with pytest.raises(ValueError, match="repetition"):
        manifest(config, repetition=2).validate_against(config)


def test_separate_extractor_verifier_bindings_and_records(config, artifact):
    extractor = ConstantModel("synthetic")
    verifier = ScriptedModel(["synthetic"])
    data = config.model_dump()
    data.update(
        extractor=ModelBinding(adapter_id="constant", model=extractor.identity),
        verifier=ModelBinding(
            adapter_id="scripted", model=verifier.identity, parameters=ModelParameters(seed=10)
        ),
        extractor_instructions=artifact,
        verifier_instructions=artifact,
    )
    config = ExperimentConfig.model_validate(data)
    records = tuple(
        ModelRunRecord(
            role=role,
            binding=binding,
            capabilities=model.capabilities,
            effective_parameters=binding.parameters,
        )
        for role, binding, model in [
            ("extractor", config.extractor, extractor),
            ("verifier", config.verifier, verifier),
        ]
    )
    run = manifest(config, models=records)
    run.validate_against(config)
    assert records[0].binding.model != records[1].binding.model
    changed = config.model_dump()
    changed["extractor"]["adapter_id"] = "other"
    # Match the config hash, but preserve the inconsistent model run record.
    other = ExperimentConfig.model_validate(changed)
    with pytest.raises(ValueError, match="binding"):
        manifest(other, models=records).validate_against(other)


def test_non_determinism_limitation_required():
    binding = ModelBinding(adapter_id="synthetic", model=ConstantModel("x").identity)
    with pytest.raises(ValueError, match="limitation"):
        ModelRunRecord(
            role="extractor",
            binding=binding,
            capabilities=ModelCapabilities(),
            effective_parameters=ModelParameters(),
        )
    record = ModelRunRecord(
        role="extractor",
        binding=binding,
        capabilities=ModelCapabilities(),
        effective_parameters=ModelParameters(),
        limitations=("exact_reproducibility_not_guaranteed",),
    )
    assert record.limitations


def test_time_and_unknown_manifest_fields(config):
    with pytest.raises(ValidationError):
        manifest(config, started_at=datetime(2026, 10, 15))
    with pytest.raises(ValidationError):
        manifest(config, finished_at=datetime(2026, 10, 14, tzinfo=UTC))
    for field in ["api_key", "document_text", "prompt", "metadata"]:
        with pytest.raises(ValidationError) as error:
            manifest(config, **{field: "SYNTHETIC_PRIVATE_CONTENT"})
        assert "SYNTHETIC_PRIVATE_CONTENT" not in str(error.value)
    valid = manifest(config, finished_at=datetime(2026, 10, 15, tzinfo=UTC) + timedelta(seconds=1))
    assert "SYNTHETIC_PRIVATE_CONTENT" not in valid.model_dump_json()


def test_binding_requires_versioned_instructions(config):
    data = config.model_dump()
    data["extractor"] = ModelBinding(adapter_id="constant", model=ConstantModel("x").identity)
    with pytest.raises(ValidationError, match="instruction"):
        ExperimentConfig.model_validate(data)


def test_unknown_model_version_is_explicit():
    from extracteval.core.models import ModelIdentity

    binding = ModelBinding(adapter_id="synthetic", model=ModelIdentity(engine="mock", model_id="x"))
    with pytest.raises(ValueError, match="Missing model version"):
        ModelRunRecord(
            role="extractor",
            binding=binding,
            capabilities=ModelCapabilities(),
            effective_parameters=ModelParameters(),
            limitations=("exact_reproducibility_not_guaranteed",),
        )
    record = ModelRunRecord(
        role="extractor",
        binding=binding,
        capabilities=ModelCapabilities(),
        effective_parameters=ModelParameters(),
        limitations=("exact_reproducibility_not_guaranteed", "model_version_unavailable"),
    )
    assert record.binding.model.model_version is None


def test_result_trace_checks_configuration(trace, config):
    trace.validate_config(config)
    data = trace.model_dump()
    data["output_schema"]["version"] = "2"
    with pytest.raises(ValueError, match="provenance"):
        type(trace).model_validate(data).validate_config(config)


def test_manifest_rejects_duplicate_model_role(config, artifact):
    model = ConstantModel("x")
    binding = ModelBinding(adapter_id="constant", model=model.identity)
    record = ModelRunRecord(
        role="extractor",
        binding=binding,
        capabilities=model.capabilities,
        effective_parameters=ModelParameters(),
    )
    with pytest.raises(ValidationError, match="once"):
        manifest(config, models=(record, record))
