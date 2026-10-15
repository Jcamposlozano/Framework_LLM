import socket

import pytest

from extracteval.core.base import ArtifactRef
from extracteval.core.documents import EvidenceAssessment
from extracteval.core.experiments import ConfigRef, ExperimentConfig
from extracteval.core.results import ResultTrace
from extracteval.core.specification import (
    InformationPolicy,
    OperationalDictionary,
    VariableDefinition,
)


@pytest.fixture
def artifact() -> ArtifactRef:
    return ArtifactRef(artifact_id="dictionary", version="1", sha256="a" * 64)


@pytest.fixture
def dictionary(artifact: ArtifactRef) -> OperationalDictionary:
    return OperationalDictionary(
        artifact=artifact,
        variables=(
            VariableDefinition(
                variable_id="decision",
                version="1",
                data_type="categorical",
                categories=("yes", "no", "indeterminado", "not_applicable"),
                operational_definition="Documented administrative decision",
                correctness_criteria=("Exact agreement with the independent reference",),
                information_policy=InformationPolicy(
                    absent="No semantic value",
                    indeterminate="Use indeterminado",
                    not_applicable="Use not_applicable",
                ),
            ),
        ),
    )


@pytest.fixture
def config(artifact: ArtifactRef) -> ExperimentConfig:
    return ExperimentConfig(
        config_id="experiment",
        version="1",
        dictionary=artifact,
        output_schema=artifact,
    )


@pytest.fixture
def trace(artifact: ArtifactRef, config: ExperimentConfig) -> ResultTrace:
    return ResultTrace(
        document_id="doc-1",
        variable_id="decision",
        dictionary=artifact,
        config=ConfigRef.from_config(config),
        execution_id="run-1",
        output_schema=artifact,
    )


@pytest.fixture
def absent_evidence() -> EvidenceAssessment:
    return EvidenceAssessment(availability="absent", sufficiency="insufficient")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in synthetic unit tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
